#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-11-12 國泰轉貸專區「總庫存損益」真值套用（使用者 11/12 Telegram 截圖）

表頭：總投資本金 12,000,000｜總參考現值 11,825,959｜總投資損益 -174,041｜
      現持有基金配息 252,780｜不含息總報酬率 -1.45%｜含息總報酬率 +0.66%
逐檔（淨值日 11/11，聯博 11/10）：
  富達全球動能多元B股-美元-C月配息（0002B021）單位 15,744.5／USD 11.20／5,782,136
  貝萊德智慧數據收益成長B11（0040B024）單位 15,503.76／USD 9.96／5,063,348
  聯博全球多元收益AD-美元-月配（00120135）單位 3,386.37／USD 8.83／980,475
"""
import json
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
P = BASE / "snapshot.json"
snap = json.loads(P.read_text(encoding="utf-8"))

CATHAY = {
    "富達全球動能多元B股C月配息美元": 5782136,
    "貝萊德智慧數據收益成長B11-美元-強化穩定月配息": 5063348,
    "聯博全球多元收益AD美元月配": 980475,
}
CATHAY_TOTAL = 11825959
assert sum(CATHAY.values()) == CATHAY_TOTAL, sum(CATHAY.values())

snap["fund_breakdown_cathay"] = dict(CATHAY)
snap["funds_cathay_breakdown"] = dict(CATHAY)
snap["funds_cathay"] = CATHAY_TOTAL
snap["funds_cathay_market_value"] = CATHAY_TOTAL
snap["funds_cathay_detail_20261112"] = {
    "富達全球動能多元B股C月配息美元": {
        "代號": "0002B021", "單位數": 15744.5, "淨值USD": 11.20, "淨值日": "2026-11-11",
        "本金": 6000000, "現值": 5782136, "配息累計": 147427,
        "不含息_pct": -3.63, "含息_pct": -1.17, "含息_twd": -70437},
    "貝萊德智慧數據收益成長B11-美元-強化穩定月配息": {
        "代號": "0040B024", "單位數": 15503.76, "淨值USD": 9.96, "淨值日": "2026-11-11",
        "本金": 5000000, "現值": 5063348, "配息累計": 84800,
        "不含息_pct": 1.27, "含息_pct": 2.96, "含息_twd": 148148},
    "聯博全球多元收益AD美元月配": {
        "代號": "00120135", "單位數": 3386.37, "淨值USD": 8.83, "淨值日": "2026-11-10",
        "本金": 1000000, "現值": 980475, "配息累計": 20553,
        "不含息_pct": -1.95, "含息_pct": 0.10, "含息_twd": 1028},
}
snap["funds_cathay_note_1112"] = (
    "2026-11-12 國泰轉貸專區截圖：總投資本金 12,000,000、參考現值 11,825,959、"
    "未實現 -174,041（不含息 -1.45%）、累計配息 252,780、含息總報酬 +0.66%。"
    "富達 5,782,136（含息 -1.17%／不含息 -3.63%）｜B11 5,063,348（+2.96%／+1.27%）｜"
    "聯博AD 980,475（+0.10%／-1.95%）；三檔逐檔合計＝表頭 ✓"
)
snap.setdefault("fund_nav_dates", {})["國泰直購（富達/聯博/B11）"] = "2026-11-11"
snap.setdefault("source_import_dates", {})["基金 國泰直購（富達/聯博/B11）"] = "2026-11-12"

from asset_sync import sync_snapshot_keys, rebuild_liabilities  # noqa: E402
snap = sync_snapshot_keys(snap)
snap["funds_total"] = CATHAY_TOTAL + int(snap.get("funds_breakdown", {}).get("鉅亨平台合計") or 0)
for k in ("fund_market", "fund_market_value", "funds", "fund_total_market_value"):
    snap[k] = snap["funds_total"]
snap["total_assets"] = (snap["insurance_total"] + snap["securities_total_market_value"]
                        + snap["fund_market"] + snap["cash_total"])
snap = rebuild_liabilities(snap)
snap["generated_at"] = "2026-11-12T09:05:00"
P.write_text(json.dumps(snap, ensure_ascii=False, indent=1).replace("\n", "\r\n"),
             encoding="utf-8", newline="")

print("--- 2026-11-12 國泰池真值套用完成 ---")
print(f"  國泰池: {CATHAY_TOTAL:,}（前值 11,761,894，+{CATHAY_TOTAL-11761894:,}）")
print(f"  基金合計: {snap['funds_total']:,}")
print(f"  總資產: {snap['total_assets']:,}")
print(f"  質押 LTV: 5,900,000 / {CATHAY_TOTAL:,} = {5900000/CATHAY_TOTAL*100:.2f}%")
