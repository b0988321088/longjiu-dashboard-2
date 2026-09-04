#!/usr/bin/env python3
"""fire_progress.py — 退休 FIRE 進度
每日自動計算被動收入 vs 實際開銷覆蓋率"""

import json
import re
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
TARGET_IDEAL_SPEND = 40_000  # 長期理想目標月花費
TARGET_EXPENSE = 162_781  # 當下真實常態開銷

def calc():
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    mdb = snap.get("monthly_dividend_breakdown", {})

    insurance_div = mdb.get("allianz", 0) + mdb.get("firstjin", 0)
    etf_div = mdb.get("etf", 0)
    fund_div = mdb.get("fund", 0)
    rent = snap.get("rent_monthly_actual", 80100)
    # 2026-09-04：租金用「當月已收」加總（同 morning_briefing），非應收 80,100
    _tm = date.today().strftime("%Y-%m")
    _rent_got = 0
    for _k, _v in (snap.get("rent_received_records", {}) or {}).items():
        if str(_k).startswith(_tm):
            if isinstance(_v, dict):
                _rent_got += sum(x for x in _v.values() if isinstance(x, (int, float)))
            elif isinstance(_v, (int, float)):
                _rent_got += _v
    if _rent_got > 0:
        rent = _rent_got
    total_income = insurance_div + etf_div + fund_div + rent
    expense = snap.get("monthly_expense", TARGET_EXPENSE)
    mortgage = snap.get("mortgage_monthly_total", 0) or 0
    other_expense = max(0, expense - mortgage)

    mdb_note = mdb.get("note", "") or ""
    _m = ""
    # 2026-09-04 動態化：note 含「N月」就標（原只認 7月/8月）
    _mm = re.search(r"(\d{1,2})月", mdb_note)
    if _mm:
        _n = _mm.group(1)
        _cur_m = str(date.today().month)
        _m = f"（{_n}月）" if _n == _cur_m else f"（{_n}月實收）"
    cov = total_income / expense * 100 if expense else 0
    lines = [
        f"🎯 **FIRE 進度{_m}**",
        f"- 被動收入{_m}：**{total_income:,}**",
        f"  （保單 {insurance_div:,} + ETF {etf_div:,} + 基金 {fund_div:,} + 房租 {rent:,}）",
        f"- 當下真實常態開銷：**{expense:,}**",
        f"  （房貸 {mortgage:,} + 生活/信用卡 {other_expense:,}）",
        f"- {'🟢' if cov >= 100 else '🔴'}當下覆蓋率：**{cov:.1f}%** {'✅（被動收入已超過真實生活花費）' if cov >= 100 else '⚠️（不足）'}",
        f"- 📌長期理想目標（月花費 {TARGET_IDEAL_SPEND:,}）：缺口 **{max(0, TARGET_IDEAL_SPEND-total_income):,}**/月",
    ]

    return "\n".join(lines)

if __name__ == "__main__":
    print(calc())
