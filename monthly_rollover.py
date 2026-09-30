#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""月初校正（monthly_rollover.py）— 每月 1 日 06:45 cron 執行（no_agent，零 LLM）。

為什麼需要（2026-10-01 實例）：
  月初有 5 個欄位必須跟著換月，漏一個就會「拿上月數字冒充本月」，而且 07:00
  晨間產線的儀表板閘門（check_dashboard_sync 第 14 條）會直接擋下推送：
    · 房租待收 56,100 ≠ snapshot.rent_monthly_gap 0（本月應收口徑沒建 → 退回常態）
    · 當月實收顯示「配息 147,975（9月）＋ 房租 24,000（10月）」這種混血
  本支把可自動化的做掉；無法自動的（一次性折讓、空置、換約）大聲列出來讓人確認。

自動處理（預設 dry-run；--apply 才寫檔）：
  1. rent_receivable_by_month[本月] 缺 → 由常態 rent_breakdown 建立（既有月份永不覆寫）
  2. rent_monthly_actual（頂層＋passive_income 兩處）＝ rent_received_records[本月] 加總
  3. passive_income.dividend_actual_sum ＝ dividend_records[本月] 加總（月初為 0）
  4. rent_monthly_gap ＝ Σ max(本月應收_i − 本月已收_i, 0)   ← 與儀表板逐項待收同公式
  5. --apply 時呼叫 dividend_tracker.py（讓 dividend_month_actual／monthly_dividend_total／
     monthly_dividend／breakdown 五欄一致歸零；它不會刪既有 dividend_records）

用法：
  python monthly_rollover.py            # dry-run：只印差異，不寫檔
  python monthly_rollover.py --apply    # 寫入 snapshot.json（並跑 dividend_tracker）
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"


def _m(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def compute(snap: dict, month: str) -> tuple[dict, list[str]]:
    """純函式：算出本月該有的 4 個值。回傳（新值 dict, 提示清單）。不寫檔。"""
    pi = snap.setdefault("passive_income", {})
    rrb_all = snap.get("rent_receivable_by_month") or {}
    recv_all = snap.get("rent_received_records") or {}
    div_all = snap.get("dividend_records") or {}

    notes: list[str] = []
    # 1) 本月應收：缺 → 由常態 rent_breakdown 建立
    rrb_new = False
    if month in rrb_all and isinstance(rrb_all[month], dict) and rrb_all[month]:
        recv_plan = dict(rrb_all[month])
    else:
        recv_plan = dict(snap.get("rent_breakdown") or {})
        rrb_new = True
        notes.append(f"⚠️ 本月應收（rent_receivable_by_month['{month}']）不存在 → 由常態 rent_breakdown 建立；"
                     "若有一次性折讓/空置/換約，請人工覆寫該月份逐項金額（比照 9 月洲際W −3,000、10 月 −5,000）")

    # 2/4) 本月已收（逐戶）→ 實收合計、待收
    recv_got: dict[str, float] = {}
    for d, items in recv_all.items():
        if not str(d).startswith(month) or not isinstance(items, dict):
            continue
        for k, v in items.items():
            recv_got[k] = recv_got.get(k, 0.0) + _m(v)
    received = sum(recv_got.values())
    gap = sum(max(_m(v) - recv_got.get(k, 0.0), 0.0) for k, v in recv_plan.items())

    # 3) 本月配息實收
    div_actual = 0.0
    for d, items in div_all.items():
        if str(d).startswith(month) and isinstance(items, dict):
            div_actual += sum(_m(v) for v in items.values())

    values = {
        "rent_receivable_by_month": {month: recv_plan} if rrb_new else {},
        "rent_monthly_actual": received,
        "pi_rent_monthly_actual": received,
        "pi_dividend_actual_sum": div_actual,
        "rent_monthly_gap": gap,
    }

    # 提示：逐戶比對（誰還沒收、誰收超過）
    for k, v in recv_plan.items():
        got = recv_got.get(k, 0.0)
        if got < _m(v):
            notes.append(f"　⏳ {k}：應收 {_m(v):,.0f} − 已收 {got:,.0f} = 待收 {_m(v) - got:,.0f}")
        elif got > _m(v):
            notes.append(f"　⚠️ {k}：已收 {got:,.0f} > 應收 {_m(v):,.0f}（溢收，請確認口徑）")
    for k, got in recv_got.items():
        if k not in recv_plan:
            notes.append(f"　⚠️ {k}：本月有入帳 {got:,.0f} 但不在應收清單 → 確認是否漏列應收")
    if div_actual == 0:
        notes.append("　ℹ️ 本月配息實收 0（月初正常；收到後由 07:10 dividend_tracker 累積）")
    return values, notes


def main() -> int:
    ap = argparse.ArgumentParser(description="月初校正：房租/配息跨月口徑（預設 dry-run）")
    ap.add_argument("--apply", action="store_true", help="寫入 snapshot.json（否則只印差異）")
    ap.add_argument("--month", default="", help="指定月份 YYYY-MM（預設本月，測試用）")
    a = ap.parse_args()

    month = a.month or dt.date.today().strftime("%Y-%m")
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    pi = snap.get("passive_income") or {}
    values, notes = compute(snap, month)

    def _now(key, cur, new):
        return f"{key}: {cur} → {new}" if _m(cur) != _m(new) else f"{key}: {new}（不變）"

    print(f"🗓️ 月初校正 {month}{'（dry-run）' if not a.apply else '（寫入）'}")
    print("  " + _now("rent_monthly_actual（頂層）", snap.get("rent_monthly_actual"), values["rent_monthly_actual"]))
    print("  " + _now("passive_income.rent_monthly_actual", pi.get("rent_monthly_actual"), values["pi_rent_monthly_actual"]))
    print("  " + _now("passive_income.dividend_actual_sum", pi.get("dividend_actual_sum"), values["pi_dividend_actual_sum"]))
    print("  " + _now("rent_monthly_gap（本月待收）", snap.get("rent_monthly_gap"), values["rent_monthly_gap"]))
    if values["rent_receivable_by_month"]:
        plan = values["rent_receivable_by_month"][month]
        print(f"  rent_receivable_by_month['{month}'] = {json.dumps(plan, ensure_ascii=False)}（合計 {sum(plan.values()):,.0f}）")
    print("  本月應收逐項：")
    for line in notes:
        print("  " + line if not line.startswith("　") else line)

    if not a.apply:
        print("ℹ️ dry-run 結束（未寫檔）；確認無誤後加 --apply")
        return 0

    # 先讓 dividend_tracker 把 5 個配息欄位對齊（它自己讀寫 snapshot.json）
    try:
        import dividend_tracker  # noqa: PLC0415
        dividend_tracker.main()
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ dividend_tracker 執行失敗（配息五欄可能不一致）：{exc}")

    snap = json.loads(SNAP.read_text(encoding="utf-8"))   # tracker 寫過 → 重新讀
    pi = snap.setdefault("passive_income", {})
    if values["rent_receivable_by_month"]:
        rrb = snap.setdefault("rent_receivable_by_month", {})
        rrb[month] = values["rent_receivable_by_month"][month]
        snap["rent_receivable_by_month"] = {k: rrb[k] for k in sorted(rrb)}
    snap["rent_monthly_actual"] = values["rent_monthly_actual"]
    pi["rent_monthly_actual"] = values["pi_rent_monthly_actual"]
    pi["dividend_actual_sum"] = values["pi_dividend_actual_sum"]
    snap["rent_monthly_gap"] = values["rent_monthly_gap"]
    _plan_diff = {k: v for k, v in (snap.get("rent_receivable_by_month", {}).get(month) or {}).items()
                  if _m(v) != _m((snap.get("rent_breakdown") or {}).get(k))}
    _extra = ("；本月應收含一次性調整（逐項見 rent_receivable_by_month['%s']：%s）"
              % (month, json.dumps(_plan_diff, ensure_ascii=False))) if _plan_diff else ""
    pi["rent_monthly_actual_note"] = (
        f"{dt.date.today().isoformat()} 月初校正：真值＝rent_received_records 當月加總"
        f"＝{values['rent_monthly_actual']:,.0f}；常態應收仍為 rent_monthly={pi.get('rent_monthly')}{_extra}")
    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print("✅ 已寫入 snapshot.json")
    print("→ 下一步：four_source_sync.py（四源同步）→ LJ_PREPUSH=1 check_dashboard_sync.py（閘門）→ auto_push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
