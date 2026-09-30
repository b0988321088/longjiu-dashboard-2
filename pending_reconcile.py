#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pending_reconcile.py — Pending 狀態由真值自動重算（使用者 2026-09-30 P0 規格）

問題（CIO 2026-09-30）：
    Pending 已經開始變成「另一個真值來源」——人工維護、與實際進度脫節
    （例：券商 100 萬 9/30 已清償，Pending 還寫「待清償」）。這是架構 bug。
目標架構（本檔負責右半邊）：
    銀行／保單／券商／市場 → 真值層 SSoT → Decision Engine → Pending 自動產生
    → 執行後重新讀真值 → 自動 CLOSED
    本檔＝「執行後重新讀真值 → 自動 CLOSED／狀態自動重算」這一段；
    「Pending 自動產生」為第二階段（需決策引擎），尚未實作 → 不得宣稱已完成。

用法：
    python pending_reconcile.py            # 預設 dry-run：只印差異，不動檔
    python pending_reconcile.py --apply    # 實際寫入（狀態重算＋自動閉環歸檔）
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys
from datetime import datetime

BASE = pathlib.Path(__file__).resolve().parent
PEND = BASE / "pending_decisions.json"
ARCH = BASE / "pending_decisions_archive.json"
SAFE_LINE = 40_000


def _load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def save(p, data, indent):
    txt = json.dumps(data, ensure_ascii=False, indent=indent).replace("\n", "\r\n")
    p.write_text(txt, encoding="utf-8", newline="")


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _aging_days(ev: dict, today: str):
    try:
        horizon = ev.get("檢視日") or ev.get("回報日") or ev.get("名目日")
        if not horizon:
            return None
        return (datetime.fromisoformat(today) - datetime.fromisoformat(str(horizon)[:10])).days
    except Exception:
        return None


def evaluate(snap: dict, st: dict, us: dict) -> dict:
    """把所有真值整理成「判定素材」——規則只讀這裡，不各自摸 snapshot。"""
    cd = snap.get("cash_detail") or {}
    cl = snap.get("cash_layers") or {}
    rc = snap.get("restricted_cash") or {}
    rows = rc.get("明細") or [] if isinstance(rc, dict) else []
    repay = snap.get("policy_repay_log") or []
    today = str(snap.get("date") or datetime.now().date().isoformat())
    try:
        gate = __import__("sot_targets").us30y_gate(snap, st)
    except Exception:
        gate = {}

    def _row_state(kw: str):
        for r in rows:
            if kw in str(r.get("項目", "")) + str(r.get("簡稱", "")):
                return str(r.get("狀態", "")), _f(r.get("金額"))
        return "", 0.0

    debt_done = sum(_f(x.get("金額")) for x in repay if str(x.get("對象")) in
                    ("securities", "policy", "policy_pledge", "券商質押", "保單質押"))
    return {
        "today": today,
         "玉山": _f(cd.get("臺幣綜存")),
        "富邦": _f(cd.get("數位活儲")),
        "永豐": _f(cd.get("營業部DAWHO活期儲蓄存款")) + _f(cd.get("市政分行活期儲蓄存款")),
        "永豐月繳": _f(snap.get("mortgage_sinopac_monthly")),
        "永豐安全線": _f(snap.get("mortgage_sinopac_monthly")) * 3,
        "可動用": _f(cl.get("unrestricted_cash")),
        "指定用途款": _f((cl.get("restricted_cash") or {}).get("total")),
        "剩餘未清償": _f(rc.get("剩餘未清償")) if isinstance(rc, dict) else 0.0,
        "已清償累計": debt_done,
        "券商質押已清": ("已清償" in _row_state("券商")[0]),
        # 2026-09-30：卡片敘述原本寫死「券商質押 100 萬」（估算值，實際 960,000）→ 改讀真值
        "券商質押已清額": _row_state("券商")[1],
        "保單質押狀態": _row_state("保單")[0],
        "保單質押未入帳": ("執行中" in _row_state("保單")[0]),
        "質押撥款餘額": _f(snap.get("fund_pledge_loan")),
        "us30y": st.get("last_rate"), "us30y_as_of": st.get("last_date"),
        "us30y_streak": st.get("streak"), "gate_status": gate.get("status"),
        "unfreeze_allowed": gate.get("unfreeze_allowed"),
        "gate_reason": gate.get("reason"),
        "檢視日": {},
    }


def main() -> int:
    apply = "--apply" in sys.argv
    snap = _load(BASE / "snapshot.json")
    try:
        st = _load(BASE / "us30y_state.json")
    except Exception:
        st = {}
    pend = _load(PEND)
    arch = _load(ARCH)
    # INC-263：寫入前快照必須在規則迴圈之前取 —— arch 會在迴圈內被 append，
    # 事後再算 len(arch) 已經是新值，會讓「守恆」斷言必然失敗（假警報）。
    n_pend0, n_arch0 = len(pend), len(arch)
    n_total0 = n_pend0 + n_arch0
    ev = evaluate(snap, st, {})
    today = ev["today"]
    actions: list[dict] = []

    # ── 規則表：每條只做「由真值可判定」的事；不可判定的不猜 ──
    def r_water_life(item):     # 生活帳戶水位（玉山／台北富邦，只扣信用卡）
        t = item.get("title", "")
        if "水位" not in t or "永豐" in t:
            return None
        low = [f"{n} {m:,.0f}" for n, m in (("玉山", ev["玉山"]), ("富邦", ev["富邦"])) if m < SAFE_LINE]
        if not low:
            return {"kind": "close", "evidence": f"玉山 {ev['玉山']:,.0f}／富邦 {ev['富邦']:,.0f} 均 ≥ 安全線 {SAFE_LINE:,}"}
        return {"kind": "update", "status": f"🔴 水位不足（{today} 真值重算）：{'／'.join(low)} < 安全線 {SAFE_LINE:,}",
                "evidence": "由 snapshot.cash_detail 重算"}

    def r_water_sinopac(item):  # 永豐（房貸扣款行）：安全線＝自身房貸月繳×3
        if "永豐" not in item.get("title", ""):
            return None
        bal, line = ev["永豐"], ev["永豐安全線"]
        if not line:
            return None
        if bal >= line:
            return {"kind": "close", "evidence": f"永豐 {bal:,.0f} ≥ 安全線 {line:,.0f}（房貸月繳×3）"}
        return {"kind": "update",
                "status": (f"🔴 水位不足（{today} 真值重算）｜永豐 {bal:,.0f} < 安全線 {line:,.0f}"
                           f"（房貸月繳 {ev['永豐月繳']:,.0f}×3）→ 缺口 {line - bal:,.0f}；房貸扣款前補足"),
                "evidence": "snapshot.cash_detail（DAWHO＋市政）＋ mortgage_sinopac_monthly×3"}

    def r_pledge(item):         # 質押撥款／對保
        if "質押" not in item.get("title", "") or "撥款" not in item.get("title", "") + item.get("status", ""):
            return None
        if ev["質押撥款餘額"] > 0:
            return {"kind": "close", "evidence": f"fund_pledge_loan {ev['質押撥款餘額']:,.0f} 已入帳（真值鍵有值）"}
        return None

    def r_repay(item):          # 高息負債清償
        if "清償" not in item.get("title", ""):
            return None
        parts = []
        if ev["券商質押已清"]:
            _sec_amt = _f(ev.get("券商質押已清額"))
            parts.append(f"券商質押 {_sec_amt:,.0f} 已清償入帳" if _sec_amt
                         else "券商質押 已清償入帳（金額待補）")
        if ev["保單質押未入帳"]:
            parts.append("保單質押仍『執行中』（未入帳，帳務不動）")
        parts.append(f"已清償累計 {ev['已清償累計']:,.0f}／剩餘未清償 {ev['剩餘未清償']:,.0f}")
        if ev["剩餘未清償"] <= 0 and ev["已清償累計"] > 0:
            return {"kind": "close", "evidence": "剩餘未清償 0（policy_repay_log 累計已足）", "extra": parts}
        return {"kind": "update",
                "status": f"🔄 執行中（{today} 真值重算）｜" + "；".join(parts) + "｜檢視日 2026-10-05",
                "evidence": "restricted_cash.明細 ＋ policy_repay_log 重算"}

    def r_us30y(item):          # 解凍/凍結條件類（僅「待條件的投資解凍」卡；設定/已實作卡不動）
        t = item.get("title", "")
        if "解凍" not in t or any(k in t for k in ("閘門", "政策", "判定條件", "預案")):
            return None
        if "已實作" in str(item.get("status", "")):
            return None
        status = (f"⏸ 條件未成立（{today} 真值重算）：US30Y {ev['us30y']}%（as_of {ev['us30y_as_of']}）"
                  f"、連續 {ev['us30y_streak']} 日 ≥ 紅線；閘門 {ev['gate_status']}"
                  f"（解凍{'許可' if ev['unfreeze_allowed'] else '不許可'}）")
        return {"kind": "update", "status": status, "evidence": ev["gate_reason"]}

    rules = [r_water_life, r_water_sinopac, r_pledge, r_repay, r_us30y]
    keep = []
    for item in pend:
        res = None
        for rule in rules:
            try:
                res = rule(item)
            except Exception as e:      # 規則壞掉不得吃掉整張卡
                res = None
            if res:
                break
        title = item.get("title", "")
        if res and res["kind"] == "close":
            item["status"] = f"✅ 自動閉環({today})：{res['evidence']}｜原狀態：{item.get('status', '')[:80]}"
            item["cleanup_reason"] = f"pending_reconcile 自動閉環：{res['evidence']}"
            arch.append(item)
            actions.append({"動作": "自動閉環", "title": title, "證據": res["evidence"]})
            continue
        if res and res["kind"] == "update" and res.get("status") != item.get("status"):
            actions.append({"動作": "狀態重算", "title": title, "舊": item.get("status", "")[:70],
                            "新": res["status"][:120], "證據": res.get("evidence")})
            item["status"] = res["status"]
        keep.append(item)

    print(f"═══ Pending 真值對帳（{today}｜{'寫入' if apply else 'dry-run'}）═══")
    print(f"Pending {len(pend)} 筆｜規則命中 {len(actions)} 筆")
    for a in actions:
        print(f"\n・{a['動作']}：{a['title'][:50]}")
        if a.get("舊"):
            print(f"   舊：{a['舊']}")
            print(f"   新：{a['新']}")
        print(f"   證據：{a['證據']}")
    if not actions:
        print("（無差異：Pending 已與真值一致）")
    if not apply:
        print("\nℹ️ dry-run：未寫入。要落地請加 --apply")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy(PEND, PEND.with_suffix(PEND.suffix + f".bak_reconcile_{stamp}"))
    shutil.copy(ARCH, ARCH.with_suffix(ARCH.suffix + f".bak_reconcile_{stamp}"))
    save(PEND, keep, 2)
    save(ARCH, arch, 1)
    # 落地後驗證（INC-263：先寫、後驗；驗證失敗一律只警告不 raise）
    # 理由：檔案已寫入，raise 會讓 cron/操作者誤判「寫入失敗」→ 重跑造成二次搬移。
    warns: list[str] = []
    n_pend1 = n_arch1 = None
    try:
        n_pend1, n_arch1 = len(_load(PEND)), len(_load(ARCH))
        if n_pend1 + n_arch1 != n_total0:
            warns.append(f"筆數不守恆（寫入前 {n_total0} → 寫入後 {n_pend1 + n_arch1}）")
        for path, label in ((PEND, "pending_decisions.json"), (ARCH, "pending_decisions_archive.json")):
            raw = path.read_bytes()
            if (raw.count(b"\n") - raw.count(b"\r\n")) != 0:
                warns.append(f"{label} CRLF 損毀")
    except Exception as e:      # 重讀/解析失敗也算警告，不得吃掉已完成的寫入
        warns.append(f"落地後重讀驗證失敗：{type(e).__name__}: {e}")
    if n_pend1 is None or n_arch1 is None:
        print(f"\n✅ 已寫入：pending {n_pend0} → {len(keep)}｜archive {n_arch0} → {len(arch)}（筆數重讀失敗）")
    else:
        print(f"\n✅ 已寫入：pending {n_pend0} → {n_pend1}｜archive {n_arch0} → {n_arch1}"
              f"（合計 {n_total0} → {n_pend1 + n_arch1}）")
    for w in warns:
        print(f"⚠️ 落地後驗證警告（檔案已寫入，請勿重跑）：{w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
