#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bbd_quarterly_check.py — 每季資金策略三關檢查（使用者 2026-10-29 核准）

三關（依 2026-10-29 裁示；現階段不切換系統規則，本檔只做唯讀檢查與通知）：
  ①現金關：可動用現金 ≥ 底線，且指定款未被動用
  ②利差關：可持續稅後總報酬 − 借款稅後成本 ≥ 1.5pp
            **缺可持續收益資料時一律 UNKNOWN**（不得用配息率代替 → 不得假裝通過）
  ③借款關：壓力後維持率（擔保池 −30%）≥ 180% 且續約條件有書面
            維持率 180% 只是內部紀律，不是銀行公式 → 一律標註

輸出紀律（例外優先）：狀態全數未變且無新到期事件 → 靜默（rc=0，不發通知）。
任一關 FAIL／資料缺（UNKNOWN）變化／到期日進入 90 天內 → 才輸出。
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
if not (BASE / "snapshot.json").exists():
    _alt = Path(r"C:\Users\bot\Desktop\longjiu_system")
    if (_alt / "snapshot.json").exists():
        BASE = _alt
SNAP = BASE / "snapshot.json"
STATE = BASE / "data" / "bbd_quarterly_state.json"
SUMMARY = BASE / "data" / "gate_summary.json"   # P1：三關總表（儀表板唯讀）

CASH_FLOOR = 700_000          # 可動用現金底線（政策）
RESTRICTED_EXPECT = 900_000   # 指定還債款（不得動用）
SPREAD_MIN_PP = 1.5
MAINT_MIN_PCT = 180.0
STRESS_DROP_PCT = 30.0


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def collect_events(snap: dict, today: date, horizon_days: int = 90) -> list[str]:
    """到期事件（P2：質押一律綁 fund_pledge_maturity；房貸只取寬限期到期日）。"""
    grace = snap.get("mortgage_cathay_grace") or {}
    pairs = (
        ("質押到期／續約", snap.get("fund_pledge_maturity")),
        ("國泰寬限期屆滿", grace.get("寬限期到期日")),
    )
    events: list[str] = []
    for label, d in pairs:
        if not d:
            continue
        try:
            dt = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        days = (dt - today).days
        if 0 <= days <= horizon_days:
            events.append(f"⏰ {label} {dt}（剩 {days} 天）")
    return events


# ── P1：三關總表 ─────────────────────────────────────────────────────────────
GATE_META = {
    "G1": {"name": "資金安全", "question": "現金夠不夠？借款規則是否明確？"},
    "G2": {"name": "資產合理性", "question": "扣掉利息、稅費與風險後，利差是否值得？"},
    "G3": {"name": "整體負債", "question": "房貸＋質押＋連帶擔保合計是否可承受？"},
}
EVIDENCE_DEF = {
    # 2026-10-30 使用者裁決：本金／利率／一年期／到期日／只繳息等基本條件已確認
    # → 不列為證據缺口、不再要求使用者重複提供；僅保留真正影響風險判斷的三項（追繳、認列、續約）
    "E1": "銀行書面：維持率／預警線／追繳門檻與補繳期限（計算公式與通知方式）",
    "E2": "三檔擔保基金實際認列成數（含折價率）與擔保池單池／分池計算定義",
    "E3": "到期續約與不續約處理方式；是否允許部分還本；提前清償違約金",
    "E4": "基金近 12 個月含息報酬、配息組成、費用",
    "E5": "國泰攤還年限與永豐寬限期條件（書面）",
    "E6": "房產是否為質押連帶擔保",
}
NEXT_CHECK = {"rule": "每季首日 09:00（1/4/7/10 月）", "job_id": "bb44b28c7282",
              "next_run_at": "2027-01-01T09:00:00+08:00"}


def collect_evidence(snap: dict, *, terms_has_written: bool) -> dict:
    """證據齊備度。缺值一律 MISSING／UNKNOWN，不得因缺資料而視為通過。

    2026-10-30 使用者裁決：銀行書面（E1/E2/E3）已請求約 2 個月未回覆 → 狀態改為
    REQUESTED_UNANSWERED（已請求未回覆）。語意是「不再催件、不列待補」，**不是取得**：
    系統改以保守假設替代（追繳線 70%、單池最保守、續約不保證），門檻一律不放寬。
    """
    grace = snap.get("mortgage_cathay_grace") or {}
    grace_undecided = "未確認" in str(grace.get("期滿後月付_未定") or "")
    _ru = set((snap.get("cathay_pledge_0911") or {}).get("銀行書面_已請求未回覆") or [])

    def _st(code: str, default: str) -> str:
        return "REQUESTED_UNANSWERED" if code in _ru else default

    ev = {
        "E1": _st("E1", "PARTIAL" if terms_has_written else "MISSING"),
        "E2": _st("E2", "MISSING"),           # 銀行未提供認列成數／單池定義
        "E3": _st("E3", "PARTIAL" if terms_has_written else "MISSING"),
        "E4": ("OK" if isinstance(snap.get("bbd_sustainable_yield_after_tax"), (int, float))
               else "MISSING"),
        "E5": "MISSING" if grace_undecided else "PARTIAL",
        "E6": "UNKNOWN",                      # 尚無欄位可證，不得假設已釐清
    }
    return {k: {"status": v, "need": EVIDENCE_DEF[k]} for k, v in ev.items()}


def build_summary(snap: dict, today: date, *, legacy_gates: dict, metrics: dict,
                  evidence: dict) -> dict:
    """組三關總表。legacy_gates 為既有 現金關/利差關/借款關（保留供舊讀者）。"""
    def _g1() -> tuple[str, list[str]]:
        lines, bad = [], False
        lines.append(f"現金 {metrics['cash_unrestricted']:,.0f} ≥ 底線 {metrics['cash_floor']:,}"
                     f"｜指定款 {metrics['restricted_cash']:,.0f}")
        lines.append(f"質押 LTV {metrics['ltv_pct']:.2f}%（三檔加總口徑；單池定義未取得）"
                     f"｜跌 {metrics['stress_drop_pct']:.0f}% 後 {metrics['stress_ltv_pct']:.1f}%"
                     f"（換算維持率 {metrics['stress_maint_pct']:.1f}%，180% 僅壓力參考）")
        basics = ((snap.get("cathay_pledge_0911") or {}).get("基本條件_已確認") or {}).get("項目") or {}
        _loan = metrics.get("loan") or snap.get("fund_pledge_loan") or 0
        if basics:
            _rate = metrics.get("loan_rate_pct") or (float(snap.get("fund_pledge_rate") or 0) * 100)
            _mat = metrics.get("pledge_maturity") or snap.get("fund_pledge_maturity") or ""
            lines.append(f"基本條件 {'/'.join(basics.keys())}＝已確認"
                         f"（{_loan:,.0f}＠{_rate:.2f}%、一年期至 {_mat}）")
        renewal = (snap.get("cathay_pledge_0911") or {}).get("續約性質") or ""
        if renewal:
            lines.append("續約＝銀行每年依當時條件核准（期待續約，非保證續約）"
                         f"→ 未續約須到期一次還本 {_loan:,.0f}")
        if legacy_gates.get("現金關") != "PASS":
            bad = True
            lines.append("現金關未過（見明細）")
        _e3 = str(evidence["E3"]["status"])
        _ru = [k for k in ("E1", "E2", "E3") if str(evidence[k]["status"]) == "REQUESTED_UNANSWERED"]
        if _ru:
            lines.append(f"銀行書面（{'／'.join(_ru)}）已請求約 2 個月未回覆 → 不列待補、不再催件；"
                         "改採保守假設：追繳線 70%、單池最保守、續約不保證")
        if _e3 in ("MISSING", "UNKNOWN"):
            bad = True
            lines.append("續約／不續約／部分還本／提前清償無銀行書面（E3）→ 不得視為可續約")
        if metrics["stress_ltv_pct"] > 70:
            bad = True
            lines.append(f"壓力後 LTV {metrics['stress_ltv_pct']:.1f}% > 追繳參考 70%"
                         "（銀行公式未取得，採保守值）")
        return ("HOLD" if bad else "PASS"), lines

    def _g2() -> tuple[str, list[str]]:
        lines = [f"利息覆蓋 {metrics['coverage_interest_pct']:.0f}%"
                 f"（可持續現金 {metrics['sustainable_cash_monthly']:,.0f} ÷ 利息 {metrics['interest_monthly']:,.0f}）",
                 f"支出覆蓋 {metrics['coverage_expense_pct']}%"]
        st = legacy_gates.get("利差關")
        if st == "PASS":
            return "PASS", lines
        if st == "FAIL":
            lines.append("淨利差低於門檻")
            return "HOLD", lines
        lines.append("淨利差 UNKNOWN：缺可持續稅後總報酬（E4）；配息率不得代替")
        return "待補件", lines

    def _g3() -> tuple[str, list[str]]:
        lines = [f"房貸 {metrics['mortgage_balance']:,.0f}（月付 {metrics['mortgage_monthly']:,.0f}）"
                 f"＋質押 {metrics['loan']:,.0f}｜總負債 {metrics['total_liabilities']:,.0f}",
                 f"國泰寬限期至 {metrics['cathay_grace_end']}"]
        if evidence["E5"]["status"] == "MISSING":
            lines.append("攤還年限／寬限期條件無書面（E5）")
        if evidence["E6"]["status"] == "UNKNOWN":
            lines.append("房產是否質押連帶擔保未釐清（E6）")
        ok = evidence["E5"]["status"] in ("OK", "PARTIAL") and evidence["E6"]["status"] == "OK"
        return ("PASS" if ok else "待補件"), lines

    gates = {}
    for gid, fn in (("G1", _g1), ("G2", _g2), ("G3", _g3)):
        status, lines = fn()
        gaps = [k for k, v in evidence.items() if v["status"] in ("MISSING", "UNKNOWN")
                and ((gid == "G1" and k in ("E1", "E2", "E3"))
                     or (gid == "G2" and k == "E4")
                     or (gid == "G3" and k in ("E5", "E6")))]
        gates[gid] = {"name": GATE_META[gid]["name"], "question": GATE_META[gid]["question"],
                      "status": status, "lines": lines, "evidence_gaps": gaps}

    statuses = [g["status"] for g in gates.values()]
    verdict = "HOLD" if ("HOLD" in statuses) else ("待補件" if "待補件" in statuses else "通過待授權")

    return {
        "schema": "gate_summary/v1",
        "as_of": today.isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "verdict": verdict,
        "gates": gates,
        "metrics": metrics,
        "evidence": evidence,
        "confirmed_basics": {
            "確認日": ((snap.get("cathay_pledge_0911") or {}).get("基本條件_已確認") or {}).get("確認日"),
            "來源": ((snap.get("cathay_pledge_0911") or {}).get("基本條件_已確認") or {}).get("來源"),
            "項目": {k: v.get("值") for k, v in
                     (((snap.get("cathay_pledge_0911") or {}).get("基本條件_已確認") or {}).get("項目") or {}).items()},
            "不列缺口": True,
            "續約性質": (snap.get("cathay_pledge_0911") or {}).get("續約性質"),
        },
        "legacy_gates": legacy_gates,
        "next_check": NEXT_CHECK,
        "authorization": {"fund_action": False, "publish": False,
                          "note": "三關全過僅代表可提執行申請；資金操作與發布皆須使用者明確授權"},
        "notes": ["LTV 為三檔加總口徑；單池判定未取得銀行定義 → M1 未解除",
                  "維持率 180% 僅壓力參考，銀行公式未取得（E1）",
                  "銀行書面 E1／E2／E3 已請求約 2 個月未回覆（REQUESTED_UNANSWERED）→ 不列待補、不再催件；以保守假設替代，G1 HOLD 原因為壓力 LTV，非缺件",
                  "基本借款條件（本金/利率/一年期/到期日/只繳息）2026-10-30 已確認 → 不列證據缺口；但確認來源為使用者陳述，非銀行書面",
                  "續約為銀行每年核准，屬期待續約而非保證續約",
                  "利息覆蓋高不代表借款安全"],
    }



def main() -> int:
    s = load(SNAP, None)
    if not s:
        print("⚠️ BB&D 季度檢查：讀不到 snapshot.json → 無法判定（fail-closed）")
        return 0

    today = date.today()
    out: list[str] = []
    gates: dict[str, str] = {}

    # ── ① 現金關
    layers = s.get("cash_layers") or {}
    unreg = float(layers.get("unrestricted_cash") or 0)
    restricted = float((layers.get("restricted_cash") or {}).get("total") or 0)
    cash_ok = unreg >= CASH_FLOOR and restricted >= RESTRICTED_EXPECT - 1
    gates["現金關"] = "PASS" if cash_ok else "FAIL"
    if not cash_ok:
        out.append(f"❌ 現金關：可動用 {unreg:,.0f}（底線 {CASH_FLOOR:,}）／指定款 {restricted:,.0f}（應 ≥ {RESTRICTED_EXPECT:,}）")

    # ── ② 利差關（缺資料 → UNKNOWN，不假裝）
    loan = float(s.get("fund_pledge_loan") or 0)
    rate = float(s.get("fund_pledge_rate") or 0)
    interest_pledge = loan * rate / 12 if loan and rate else 0.0
    outflow = s.get("monthly_cash_outflow") or {}
    interest_total = float(outflow.get("利息小計") or 0) or interest_pledge
    sustain = float((s.get("passive_income") or {}).get("total_conservative") or 0)
    coverage = (sustain / interest_total * 100) if interest_total else 0.0

    y_asset = s.get("bbd_sustainable_yield_after_tax")   # 需年化、扣費稅（G3，目前無 → None）
    y_debt = s.get("bbd_borrow_cost_after_tax")
    if isinstance(y_asset, (int, float)) and isinstance(y_debt, (int, float)):
        spread = float(y_asset) - float(y_debt)
        gates["利差關"] = "PASS" if spread >= SPREAD_MIN_PP else "FAIL"
        if gates["利差關"] == "FAIL":
            out.append(f"❌ 利差關：淨利差 {spread:.2f}pp < {SPREAD_MIN_PP}pp")
    else:
        gates["利差關"] = "UNKNOWN"
        # 明細由 G2 總表承載；此處不重複輸出（保持「狀態未變即靜默」）

    # ── ③ 借款關（P3：對外以 LTV 為主要表達；維持率僅作換算參考，門檻數值未動）
    try:
        pool = sum(float(v) for v in (s.get("fund_breakdown_cathay") or {}).values())
    except Exception:
        pool = 0.0
    ltv = (loan / pool * 100) if pool else 0.0
    stress_ltv = (loan / (pool * (1 - STRESS_DROP_PCT / 100)) * 100) if pool else 0.0
    maint = (pool / loan * 100) if loan else 0.0
    stress = (pool * (1 - STRESS_DROP_PCT / 100) / loan * 100) if loan else 0.0
    terms = str((s.get("cathay_pledge_0911") or {}).get("契約條款_已核實") or "")
    has_written = "銀行書面" in terms and "未" not in terms.split("銀行書面")[0][-3:]
    maint_ok = stress >= MAINT_MIN_PCT          # 141.5% ⟺ LTV 70.7%，同一條件的兩種表達
    gates["借款關"] = "PASS" if (maint_ok and has_written) else "FAIL"
    # 借款關明細由 G1 總表承載；狀態變動時仍會因 changed 而輸出
    # P4：M1 未解除 → 揭露已由 G1 總表 lines 承載（此處不重複輸出）

    # ── 到期事件倒數（P2：質押事件一律綁 fund_pledge_maturity）
    events = collect_events(s, today)

    # ── P1：三關總表（G1/G2/G3）＋ gate_summary.json（儀表板唯讀用）
    evidence = collect_evidence(s, terms_has_written=has_written)
    summary = build_summary(
        s, today,
        legacy_gates=gates,
        metrics={
            "cash_unrestricted": unreg,
            "cash_floor": CASH_FLOOR,
            "restricted_cash": restricted,
            "loan": loan,
            "loan_rate_pct": round(rate * 100, 3),
            "pool": pool,
            "ltv_pct": round(ltv, 2),
            "stress_drop_pct": STRESS_DROP_PCT,
            "stress_ltv_pct": round(stress_ltv, 1),
            "maint_pct": round(maint, 1),
            "stress_maint_pct": round(stress, 1),
            "interest_monthly": round(interest_total, 0),
            "sustainable_cash_monthly": round(sustain, 0),
            "coverage_interest_pct": round(coverage, 1),
            "coverage_expense_pct": ((s.get("passive_income") or {}).get("coverage_pct")),
            "mortgage_balance": (s.get("mortgage_balance") or (s.get("mortgage") or 0)),
            "mortgage_monthly": (s.get("mortgage_monthly_total") or 0),
            "total_liabilities": (s.get("total_liabilities") or 0),
            "pledge_maturity": s.get("fund_pledge_maturity"),
            "cathay_grace_end": (s.get("mortgage_cathay_grace") or {}).get("寬限期到期日"),
        },
        evidence=evidence,
    )
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── 變動偵測
    prev = load(STATE, {}) or {}
    prev_gates = prev.get("gates") or {}
    changed = {k: v for k, v in gates.items() if prev_gates.get(k) != v}
    new_events = [e for e in events if e not in (prev.get("events") or [])]

    # ── 漏跑偵測（2026-10-29 使用者驗收點）：季檢若整季沒跑到，下次執行時必須自曝
    missed = ""
    _prev_upd = str(prev.get("updated") or "")
    if _prev_upd:
        try:
            _gap = (datetime.now() - datetime.fromisoformat(_prev_upd)).days
            if _gap > 100:      # 季檢 + 寬限；>100 天代表前一季漏跑
                missed = f"⚠️ 上次季檢距今 {_gap} 天（>100）→ 上一季疑似漏跑或機器/閘道未開機"
        except ValueError:
            pass

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"updated": datetime.now().isoformat(timespec="seconds"),
                                 "gates": gates, "events": events,
                                 "coverage_pct": round(coverage, 1),
                                 "ltv_pct": round(ltv, 2),
                                 "stress_ltv_pct": round(stress_ltv, 1),
                                 "maint_pct": round(maint, 1),
                                 "stress_maint_pct": round(stress, 1)},
                                ensure_ascii=False, indent=1), encoding="utf-8")

    if not out and not changed and not new_events and not missed:
        return 0           # 靜默：一切未變

    print(f"【資金三關總表】{today}｜統一裁定 {summary['verdict']}")
    if missed:
        print("  " + missed)
    for gid in ("G1", "G2", "G3"):
        g = summary["gates"][gid]
        print(f"  {gid} {g['name']}：{g['status']}")
        for ln in g["lines"]:
            print("     · " + ln)
        if g["evidence_gaps"]:
            print("     · 證據缺：" + "、".join(g["evidence_gaps"]))
    print("  統一裁定：分項通過 ≠ 可動用資金；三關全過仍須明確授權")
    for ln in out:
        print("  " + ln)
    for e in new_events:
        print("  " + e)
    if changed:
        print("  （狀態變動：" + "、".join(f"{k} {prev_gates.get(k, '新')}→{v}" for k, v in changed.items()) + "）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
