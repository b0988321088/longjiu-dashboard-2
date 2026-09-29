#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-09-29 利率修正：國泰基金質押 2.77% → 2.6%（使用者口述「好像是 2.6」）。
只改「現行/真值」欄位，歷史（作廢、9/3 等敘述）字樣不動。
"""
import json
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
P = BASE / "snapshot.json"
OLD, NEW = 0.0277, 0.026

snap = json.loads(P.read_text(encoding="utf-8"))
assert snap.get("fund_pledge_loan") == 5_900_000, "請先跑 apply_pledge_disbursement_0929.py"

snap["fund_pledge_rate_old"] = OLD
snap["fund_pledge_rate"] = NEW
snap["fund_pledge_rate_note"] = ("2026-09-29 使用者口述「利率好像是 2.6」→ 由 2.77% 修正為 2.6%；"
                                 "待銀行撥款通知書／對帳單確認（若書面為 2.77% 則改回）")

p = snap["cathay_pledge_0911"]
p["利率"] = "2.6%（2026-09-29 修正；原記 2.77% 為額度核定時口述值，待銀行書面確認）"
p["月息"] = ("12,783/月（5,900,000 × 2.6% ÷ 12）；清償 500 萬後舊息 16,600/月"
             "（保單 400萬@4% = 13,333＋券商 100萬@3.92% = 3,267）→ 淨省 3,817/月（45,804/年）")
p["利率修正"] = ("2026-09-29：2.77% → 2.6%（使用者口述）。此前訊息／報告中"
                 "「現行＝540萬@2.77%」屬撥款前表定值；撥款後實際＝590萬@2.6%。")
snap["fund_pledge_note"] = snap["fund_pledge_note"].replace("@2.77%", "@2.6%（原記 2.77%）")

P.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")

amt = snap["fund_pledge_loan"]
old_m = amt * OLD / 12
new_m = amt * NEW / 12
print(f"590 萬月息：2.77% → {old_m:,.0f}/月｜2.6% → {new_m:,.0f}/月（差 {old_m-new_m:,.0f}/月）")
print(f"清償 500 萬高息（16,600/月）後淨省息：{16_600 - new_m:,.0f}/月（{(16_600-new_m)*12:,.0f}/年）")
print("fund_pledge_rate =", snap["fund_pledge_rate"])
print("cathay_pledge_0911.利率 =", p["利率"])
