#!/usr/bin/env python3
"""fire_progress.py — 退休 FIRE 進度
每日自動計算被動收入 vs 實際開銷覆蓋率"""

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
TARGET_IDEAL_SPEND = 40_000  # 長期理想目標月花費
TARGET_EXPENSE = 141_958  # 當下真實常態開銷

def calc():
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    mdb = snap.get("monthly_dividend_breakdown", {})

    insurance_div = mdb.get("allianz", 0) + mdb.get("firstjin", 0)
    etf_div = mdb.get("etf", 0)
    fund_div = mdb.get("fund", 0)
    rent = snap.get("rent_monthly_actual", 80100)
    total_income = insurance_div + etf_div + fund_div + rent
    expense = snap.get("monthly_expense", TARGET_EXPENSE)

    mdb_note = mdb.get("note", "") or ""
    _m = ""
    if "7月" in mdb_note or "2026-07" in mdb_note:
        _m = "（7月實收）"
    elif "8月" in mdb_note or "2026-08" in mdb_note:
        _m = "（8月實收）"
    cov = total_income / expense * 100 if expense else 0
    lines = [
        f"🎯 **FIRE 進度{_m}**",
        f"- 被動收入{_m}：**{total_income:,}**",
        f"- 當下真實常態開銷：**{expense:,}**",
        f"- {'🟢' if cov >= 100 else '🔴'}當下覆蓋率：**{cov:.1f}%** {'✅（被動收入已超過真實生活花費）' if cov >= 100 else '⚠️（不足）'}",
        f"- 📌長期理想目標（月花費 {TARGET_IDEAL_SPEND:,}）：缺口 **{max(0, TARGET_IDEAL_SPEND-total_income):,}**/月",
    ]

    return "\n".join(lines)

if __name__ == "__main__":
    print(calc())
