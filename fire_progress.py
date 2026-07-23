#!/usr/bin/env python3
"""fire_progress.py — 退休 FIRE 進度條
每日自動計算被動收入 vs 目標達成率"""

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
TARGET_IDEAL = 300_000  # 理想退休生活
TARGET_BASIC = 141_958  # 基本生活開銷

def calc():
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    mdb = snap.get("monthly_dividend_breakdown", {})
    
    insurance_div = mdb.get("allianz", 0) + mdb.get("firstjin", 0)
    etf_div = mdb.get("etf", 0)
    fund_div = mdb.get("fund", 0)
    rent = snap.get("rent_monthly_actual", 80100)
    total_income = insurance_div + etf_div + fund_div + rent
    
    lines = [
        f"🎯 **FIRE 進度條**",
        f"被動收入: **{total_income:,} TWD/月**（保單{insurance_div:,}+ETF{etf_div:,}+基金{fund_div:,}+房租{rent:,}）",
        f"",
        f"✅ **基本生活（{TARGET_BASIC:,}）**: {total_income/TARGET_BASIC*100:.1f}% — {'已達標！🎉' if total_income >= TARGET_BASIC else '還差一點'}",
        f"🔄 **理想退休（{TARGET_IDEAL:,}）**: {total_income/TARGET_IDEAL*100:.1f}% — {'已達標！🎉' if total_income >= TARGET_IDEAL else f'缺口 {TARGET_IDEAL-total_income:,}/月'}",
    ]
    
    return "\n".join(lines)

if __name__ == "__main__":
    print(calc())
