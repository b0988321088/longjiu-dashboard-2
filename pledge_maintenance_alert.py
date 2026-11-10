#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pledge_maintenance_alert.py — 國泰基金質押「維持率」每日監控（2026-11-02 使用者核准）

背景（為什麼要有這支）：
    國泰世華「特金質借」以國泰直購三檔基金（富達全球動能 B／貝萊德智慧數據 B11／聯博全球多元收益 AD）
    為擔保池，實撥 590 萬。銀行級距（使用者 2026-11-02 確認）：維持率 160% = 通知、140% = 繳款（追繳）。
    這兩檔後收基金 2029/8、2029/9 才免罰 → **追繳時不能靠賣擔保品補**，唯一緩衝是可動用現金
    與提前還本。故必須在跌破 160% 之前就有預警，而不是等銀行簡訊。

算什麼（全部動態，禁寫死金額）：
    維持率 = 擔保池市值 ÷ 質押借款 × 100
    擔保池市值 = snapshot.funds_cathay_breakdown 逐檔加總（缺則回退 funds_cathay）
    質押借款   = snapshot.fund_pledge_loan（=0 視為無質押 → 靜默）
    門檻       = snapshot.cathay_pledge_0911.維持率_通知線／維持率_繳款線（字串或數字皆可）
                 ＋警示線 = 通知線 + WARN_BUFFER_PP（預設 5pp → 165%），可用 維持率_警示線 覆寫

燈號與輸出（no_agent watchdog 模式：空 stdout = 不推播）：
    🔴 已跌破繳款線（140%）：需補繳，附「補回繳款線／補回通知線」所需還本金額
    🟠 已跌破通知線（160%）：銀行會通知，先備現金
    🟡 進入警示區（165%）：提前預警，距離試算
    🟢 正常：不輸出（--always 可強制輸出）

防噪音（monitor-noise-governance）：
    同一燈號、同一日只推一次（state 檔：pledge_maintenance_state.json）。
    燈號惡化當下必推（不受同日限制）。

續約倒數（2026-11-10 新增，使用者核准）：
    合約是「只繳息＋每年續約」，銀行一年一決 → 到期不續約即一次還本。
    倒數里程碑 T-90／T-60／T-30／T-7／T-0，**每個里程碑只推一次**（記在 state 的
    renewal_announced），且與維持率燈號各自獨立觸發（綠燈日照樣可推續約倒數）。
    到期日換了（已續約）→ renewal_maturity 變動即重置清單，不會被上一輪紀錄吃掉。
    訊息為 advisory-only：只列缺口與續約必問四項，不產生還本／資金調度指令。

用法：
    python pledge_maintenance_alert.py            # cron no_agent
    python pledge_maintenance_alert.py --always    # 人工檢查，一律輸出（不寫 state）
    python pledge_maintenance_alert.py --json      # 機器可讀（含 renewal 區塊）
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
STATE = BASE / "pledge_maintenance_state.json"

WARN_BUFFER_PP = 5.0          # 警示線 = 通知線 + 5pp（刻意常數：緩衝寬度，非金額）
DEFAULT_NOTICE = 160.0        # 銀行未提供時的預設級距（使用者 2026-11-02 確認）
DEFAULT_PAY = 140.0
# 續約倒數里程碑（天）。每個里程碑一生只推一次，狀態記在 pledge_maintenance_state.json。
# 為什麼要有：合約是「只繳息＋每年續約」，銀行一年一決 → 到期不續約即一次還本，
# 這是最容易被忽略的單點（2026-11-10 使用者核准，來源：威利財經角 QA '台灣版買借死'）。
RENEWAL_MILESTONES = (90, 60, 30, 7)


def _num(v, default=None):
    """把 '160%' / 160 / '160' 一律解析成 float。"""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except Exception:
        return default


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def compute(snap: dict) -> dict:
    br = snap.get("funds_cathay_breakdown") or {}
    pool = sum(float(v or 0) for v in br.values()) if br else float(snap.get("funds_cathay") or 0)
    loan = float(snap.get("fund_pledge_loan") or 0)
    cp = snap.get("cathay_pledge_0911") or {}
    notice = _num(cp.get("維持率_通知線"), DEFAULT_NOTICE)
    pay = _num(cp.get("維持率_繳款線"), DEFAULT_PAY)
    warn = _num(cp.get("維持率_警示線"), notice + WARN_BUFFER_PP)
    ratio = (pool / loan * 100.0) if loan > 0 else None
    # 2026-11-06（使用者裁決）：LTV 內部停止線。LTV＝借款÷池市值，與銀行維持率互為倒數，不得混用。
    ltv = (loan / pool * 100.0) if pool > 0 else None
    _bands = (snap.get("thresholds_2026_0915") or {}).get("ltv分級_pct") or {}
    ltv_stop = _num(_bands.get("黃上限"), 53)
    ltv_target = _num(_bands.get("單池上限"), 50)
    return {"pool": pool, "loan": loan, "ratio": ratio,
            "ltv": ltv, "ltv_stop": ltv_stop, "ltv_target": ltv_target,
            "notice": notice, "pay": pay, "warn": warn,
            "rate": snap.get("fund_pledge_rate"), "due_day": snap.get("fund_pledge_due_day")}


def level_of(m: dict) -> str:
    if m["ratio"] is None:
        return "none"
    r = m["ratio"]
    if r <= m["pay"]:
        return "red"
    if r <= m["notice"]:
        return "orange"
    if r <= m["warn"]:
        return "yellow"
    return "green"


def renewal_info(snap: dict) -> dict:
    """續約到期日與剩餘天數。來源：snapshot.fund_pledge_maturity（缺則 cathay_pledge_0911.到期日）。

    欄位值是「2027-09-29（每年續約）」這種帶註記的字串 → 只取第一個 YYYY-MM-DD，
    取不到就回 None（不猜、不預設日期）。
    """
    raw = str(snap.get("fund_pledge_maturity") or "").strip()
    if not raw:
        raw = str((snap.get("cathay_pledge_0911") or {}).get("到期日") or "").strip()
    mt = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if not mt:
        return {"maturity": None, "days_left": None, "raw": raw}
    try:
        mat = date(int(mt.group(1)), int(mt.group(2)), int(mt.group(3)))
    except ValueError:
        return {"maturity": None, "days_left": None, "raw": raw}
    return {"maturity": mat.isoformat(), "days_left": (mat - date.today()).days, "raw": raw}


def renewal_milestone(info: dict) -> str | None:
    """回傳「已進入哪個倒數視窗」的鍵（T-90／T-60／T-30／T-7／T-0）；>90 天回 None。

    必須由小到大掃（7→30→60→90）才不會在剩 30 天時誤報 T-90（2026-11-10 自測抓到）。
    """
    d = info.get("days_left")
    if d is None:
        return None
    if d <= 0:
        return "T-0"
    for mm in sorted(RENEWAL_MILESTONES):
        if d <= mm:
            return f"T-{mm}"
    return None


def renewal_block(info: dict, m: dict, due_key: str, surplus: float | None = None) -> str:
    """續約倒數訊息。advisory-only：只顯示缺口與必問項，不產生還本／調度指令。"""
    loan = float(m.get("loan") or 0)
    rate = float(m.get("rate") or 0)
    d = int(info.get("days_left") or 0)
    head = "已到期／待補辦續約" if d <= 0 else f"剩 {d} 天"
    # 註記只取「日期以外的說明」（例：每年續約），避免與到期日重複顯示
    note = str(info.get("raw") or "").replace(str(info.get("maturity") or ""), "").strip("（）() 　")
    mat_txt = f"{info['maturity']}（{note}）" if note else str(info["maturity"])
    L = [f"🗓️ 質押續約倒數 {due_key}｜{head}",
         f"到期日 {mat_txt}",
         f"不續約＝一次還本 {loan:,.0f}（只繳息、無攤還；月息 {loan * rate / 12:,.0f}）"]
    if surplus and surplus > 0:
        L.append(f"月盈餘 {surplus:,.0f} vs 一次還本 → 缺口約 {loan / surplus:,.0f} 個月盈餘"
                 "（銀行一年一決，續約失敗時月現金流無法支應）")
    L.append(f"續約必問四項：① 維持率門檻是否調整（現 通知 {m['notice']:.0f}%／繳款 {m['pay']:.0f}%）"
             f"② 利率是否重定（現 {rate * 100:.2f}%）③ 可否部分還本 ④ 提前清償違約金")
    L.append("※ advisory：只顯示缺口與必問項，不產生還本／資金調度指令")
    return "\n".join(L)


def render(m: dict, lv: str, snap: dict) -> str:
    pool, loan, r = m["pool"], m["loan"], m["ratio"]
    icon = {"red": "🔴", "orange": "🟠", "yellow": "🟡", "green": "🟢"}[lv]
    head = {"red": "已跌破繳款線（銀行追繳）",
            "orange": "已跌破通知線",
            "yellow": "進入警示區",
            "green": "正常"}[lv]
    L = [f"{icon} 質押維持率 {r:.1f}% — {head}",
         f"擔保池 {pool:,.0f} ÷ 借款 {loan:,.0f}（國泰直購三檔）"]
    # 距各線距離
    L.append(f"級距：通知 {m['notice']:.0f}%／繳款 {m['pay']:.0f}%／警示 {m['warn']:.0f}%")
    for name, thr in (("通知線", m["notice"]), ("繳款線", m["pay"])):
        need = loan * thr / 100.0
        if pool > need:
            L.append(f"· 距{name}：可再跌 {abs((need / pool - 1) * 100):.1f}%（{abs(need - pool):,.0f} 元）｜門檻池值 {need:,.0f}")
        else:
            L.append(f"· {name}已破：池值需回升至 {need:,.0f}（+{need - pool:,.0f}）")
    # 補救金額（還本/補繳，把維持率拉回指定線：還本額 = loan - pool/線）
    if lv in ("red", "orange"):
        back_notice = max(0.0, loan - pool / (m["notice"] / 100.0))
        back_pay = max(0.0, loan - pool / (m["pay"] / 100.0))
        L.append(f"還本補回：至繳款線 {back_pay:,.0f}｜至通知線 {back_notice:,.0f}（後收基金不可賣，須用現金或提前還本）")
    # 敏感度與現金緩衝
    if pool > 0 and loan > 0:
        L.append(f"敏感度：池子每跌 1% = {pool * 0.01:,.0f} 元 = 維持率 -{pool * 0.01 / loan * 100:.1f}pp")
    cash_now = snap.get("cash_layers") or {}
    usable = cash_now.get("unrestricted_cash") or cash_now.get("可動用") or snap.get("cash_usable")
    if isinstance(usable, (int, float)) and usable:
        L.append(f"可動用現金 {usable:,.0f}｜月息 {loan * float(m['rate'] or 0) / 12:,.0f}（每月 {m['due_day'] or '?'} 日扣）")

    # ── 2026-11-06（使用者裁決）：LTV 內部停止線提示 ──
    # 只顯示數字與缺口，不產生任何借款／質押／資金調度指令；不取代上面 160%／140% 銀行級距。
    _ltv, _stop = m.get("ltv"), m.get("ltv_stop")
    _tgt = m.get("ltv_target") or 50
    if _ltv and _stop and pool > 0:
        _pool_at = loan / (_stop / 100.0)                      # 觸線時的池值
        _gap = pool - _pool_at                                  # 池還能跌多少錢
        L.append("")
        L.append(f"【LTV 內部停止線】{_ltv:.2f}%｜停止線 {_stop:.0f}%｜目標回 {_tgt:.0f}%"
                 f"（維持率 {r:.1f}% 為倒數，勿混用）")
        if _ltv < _stop:
            L.append(f"· 距停止線：池可再跌 {abs(_gap) / pool * 100:.2f}%（{abs(_gap):,.0f} 元）→ 觸線池值 {_pool_at:,.0f}")
            # 觸線後的補救成本（以觸線當下池值計算，供事前準備；非行動指令）
            _pay_t = max(0.0, loan - (_tgt / 100.0) * _pool_at)
            _add_t = max(0.0, loan / (_tgt / 100.0) - _pool_at)
            L.append(f"· 觸線後補救（池 {_pool_at:,.0f}）：還本 {_pay_t:,.0f} 或補擔保品 {_add_t:,.0f} → 回 {_tgt:.0f}%")
        else:
            _pay_t = max(0.0, loan - (_tgt / 100.0) * pool)
            _add_t = max(0.0, loan / (_tgt / 100.0) - pool)
            L.append(f"· ⚠️ 已達／超過停止線：還本 {_pay_t:,.0f} 或補擔保品 {_add_t:,.0f} → 回 {_tgt:.0f}%")
        if isinstance(usable, (int, float)) and usable and _pay_t > 0:
            L.append(f"· 理論補款 {_pay_t:,.0f} 元 vs 可動用現金 {usable:,.0f} 元"
                     f"（{_pay_t / usable:.2f} 倍）"
                     + ("（❗現金不足額）" if _pay_t > usable else "（現金足額）"))
        L.append("· 後收基金（富達 2029/8、B11 2029/9 前）不可低成本變現，緩衝只能靠現金或提前還本")
    return "\n".join(L)


def main() -> int:
    always = "--always" in sys.argv
    as_json = "--json" in sys.argv
    snap = _load(SNAP)
    if not isinstance(snap, dict):
        sys.stderr.write("pledge_maintenance_alert：讀不到 snapshot.json\n")
        return 1
    m = compute(snap)
    if m["loan"] <= 0:
        # 無質押 → 靜默（避免「沒有借款也算綠燈」每天推一則廢話）
        if as_json:
            print(json.dumps({"level": "none", "reason": "fund_pledge_loan=0"}, ensure_ascii=False))
        return 0
    lv = level_of(m)
    today = date.today().isoformat()
    st = _load(STATE, {}) or {}

    # ── 續約倒數（2026-11-10 新增）：與維持率燈號各自獨立觸發 ──
    # 換了到期日（已續約、或銀行改約）→ 重置已通知清單，避免新一輪被舊紀錄吃掉。
    ren = renewal_info(snap)
    if str(st.get("renewal_maturity") or "") != str(ren.get("maturity") or ""):
        st["renewal_maturity"] = ren.get("maturity")
        st["renewal_announced"] = []
    announced = [str(x) for x in (st.get("renewal_announced") or [])]
    ms = renewal_milestone(ren)
    ren_txt = None
    if ms and ms not in announced:
        ren_txt = renewal_block(ren, m, ms, _num(snap.get("working_surplus")))
        st["renewal_announced"] = announced + [ms]

    if as_json:
        print(json.dumps({**{k: v for k, v in m.items()}, "level": lv,
                          "renewal": ren, "renewal_milestone": ms},
                         ensure_ascii=False, default=str))
        return 0

    # 防噪音：同日同燈號只推一次；燈號惡化（排序變差）當下必推
    order = {"green": 0, "yellow": 1, "orange": 2, "red": 3, "none": -1}
    worse = order.get(lv, 0) > order.get(st.get("last_level", "green"), 0)
    same = st.get("last_alert_date") == today and st.get("last_level") == lv
    maint_due = bool(always) or (lv != "green" and (worse or not same))

    if not maint_due and not ren_txt:
        if lv == "green":
            _save_state(today, lv, st.get("last_alert_date"), st)
        return 0

    parts = []
    if maint_due:
        parts.append(render(m, lv, snap))
    if ren_txt:
        parts.append(ren_txt)
    print("\n\n".join(parts))
    if not always:                        # --always 只給人看，不污染 state（否則會吃掉當日真警示）
        _save_state(today, lv, (today if maint_due and lv != "green" else st.get("last_alert_date")), st)
    return 0


def _save_state(today: str, lv: str, alert_date, st: dict | None = None) -> None:
    try:
        d = dict(st or {})
        d.update({"last_date": today, "last_level": lv, "last_alert_date": alert_date})
        STATE.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                         encoding="utf-8", newline="\n")
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
