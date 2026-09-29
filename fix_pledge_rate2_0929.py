#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-09-29 利率二次修正：國泰基金質押 2.6% → 2.65%（使用者「2.65」）。"""
import json
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
P = BASE / "snapshot.json"
snap = json.loads(P.read_text(encoding="utf-8"))
assert snap.get("fund_pledge_loan") == 5_900_000

snap["fund_pledge_rate_old"] = snap.get("fund_pledge_rate")
snap["fund_pledge_rate"] = 0.0265
snap["fund_pledge_rate_note"] = ("2026-09-29 使用者確認 2.65%（原記 2.77% → 2.6% → 2.65%）；"
                                 "以銀行撥款通知書／對帳單為最終依據")

p = snap["cathay_pledge_0911"]
p["利率"] = "2.65%（2026-09-29 使用者確認；原記 2.77%，待銀行書面覆核）"
p["月息"] = ("13,029/月（5,900,000 × 2.65% ÷ 12）；清償 500 萬後舊息 16,600/月"
             "（保單 400萬@4% = 13,333＋券商 100萬@3.92% = 3,267）→ 淨省 3,571/月（42,852/年）")
p["利率修正"] = ("2026-09-29：2.77% → 2.6% → 2.65%（使用者確認）。此前訊息／報告中"
                 "「現行＝540萬@2.77%」屬撥款前表定值；撥款後實際＝590萬@2.65%。")
snap["fund_pledge_note"] = snap["fund_pledge_note"].replace("@2.6%（原記 2.77%）", "@2.65%（原記 2.77%）")

P.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
amt, r = snap["fund_pledge_loan"], snap["fund_pledge_rate"]
print(f"月息 = {amt:,} × {r*100:.2f}% ÷ 12 = {amt*r/12:,.0f}/月")
print(f"清償 500 萬高息後淨省息 = 16,600 − {amt*r/12:,.0f} = {16_600-amt*r/12:,.0f}/月"
      f"（{(16_600-amt*r/12)*12:,.0f}/年）")
