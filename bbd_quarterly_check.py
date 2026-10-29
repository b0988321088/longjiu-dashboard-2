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
        out.append("⚠️ 利差關 UNKNOWN：缺「可持續稅後總報酬」（G3）；配息率不得代替 → 不判定通過")

    # ── ③ 借款關
    try:
        pool = sum(float(v) for v in (s.get("fund_breakdown_cathay") or {}).values())
    except Exception:
        pool = 0.0
    maint = (pool / loan * 100) if loan else 0.0
    stress = (pool * (1 - STRESS_DROP_PCT / 100) / loan * 100) if loan else 0.0
    terms = str((s.get("cathay_pledge_0911") or {}).get("契約條款_已核實") or "")
    has_written = "銀行書面" in terms and "未" not in terms.split("銀行書面")[0][-3:]
    maint_ok = stress >= MAINT_MIN_PCT
    gates["借款關"] = "PASS" if (maint_ok and has_written) else "FAIL"
    if not maint_ok:
        out.append(f"❌ 借款關：跌 {STRESS_DROP_PCT:.0f}% 後維持率 {stress:.1f}% < {MAINT_MIN_PCT:.0f}%"
                   f"（現 {maint:.1f}%；門檻為內部紀律，非銀行公式）")
    if not has_written:
        out.append("⚠️ 借款關：續約條件**無銀行書面**（G4）→ 不得視為可續約")

    # ── 到期事件倒數
    events = []
    for label, d in (("質押續約節點", (s.get("mortgage_cathay_grace") or {}).get("撥款日")),
                     ("質押到期", s.get("fund_pledge_maturity")),
                     ("國泰寬限期屆滿", (s.get("mortgage_cathay_grace") or {}).get("寬限期到期日"))):
        if not d:
            continue
        try:
            dt = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        days = (dt - today).days
        if 0 <= days <= 90:
            events.append(f"⏰ {label} {dt}（剩 {days} 天）")

    # ── 變動偵測
    prev = load(STATE, {}) or {}
    prev_gates = prev.get("gates") or {}
    changed = {k: v for k, v in gates.items() if prev_gates.get(k) != v}
    new_events = [e for e in events if e not in (prev.get("events") or [])]

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"updated": datetime.now().isoformat(timespec="seconds"),
                                 "gates": gates, "events": events,
                                 "coverage_pct": round(coverage, 1),
                                 "maint_pct": round(maint, 1),
                                 "stress_maint_pct": round(stress, 1)},
                                ensure_ascii=False, indent=1), encoding="utf-8")

    if not out and not changed and not new_events:
        return 0           # 靜默：一切未變

    print(f"【BB&D 季度檢查】{today}")
    for k in ("現金關", "利差關", "借款關"):
        print(f"  {k}：{gates[k]}")
    if coverage:
        print(f"  利息覆蓋 {coverage:.0f}%（可持續現金 {sustain:,.0f} ÷ 利息 {interest_total:,.0f}）｜維持率 {maint:.1f}%／壓力後 {stress:.1f}%")
    for ln in out:
        print("  " + ln)
    for e in new_events:
        print("  " + e)
    if changed:
        print("  （狀態變動：" + "、".join(f"{k} {prev_gates.get(k, '新')}→{v}" for k, v in changed.items()) + "）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
