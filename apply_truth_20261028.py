#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-10-28 真值套用：國泰基金三檔（淨值日 2026/10/26）＋ 台股持股 14 檔（07:07 App 截圖）。

來源（使用者 2026-10-28 提供截圖）：
  ① 國泰「基金」頁 07:06：參考現值 11,924,797（-0.63%）／本金 12,000,000／不含息 -75,203
     富達 5,870,021（含息 -0.53%／不含息 -2.17%）
     B11  5,076,582（＋2.37%／＋1.53%）
     聯博 978,194（-0.83%／-2.18%）— 使用者 07:07 補圖，非反推
  ② 證券「持股明細」07:07：總市值 2,783,380／當日 -4,040（-0.14%）／
     未實現 +395,540（+16.56%）／已實現 +23,460（+27.34%），14 檔全數（逐檔合計＝頁首）
"""
import json
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
P = BASE / "snapshot.json"
snap = json.loads(P.read_text(encoding="utf-8"))

# ── ① 國泰基金（淨值日 2026/10/26）────────────────────────────
CATHAY = {
    "富達全球動能多元B股C月配息美元": 5870021,
    "貝萊德智慧數據收益成長B11-美元-強化穩定月配息": 5076582,
    "聯博全球多元收益AD美元月配": 978194,
}
CATHAY_TOTAL = 11924797          # 頁首參考現值（截圖）
assert sum(CATHAY.values()) == CATHAY_TOTAL, sum(CATHAY.values())
HENG_TOTAL = 821669              # 鉅亨（10/22 平台總覽，本次未更新）
FUNDS_TOTAL = CATHAY_TOTAL + HENG_TOTAL

snap["fund_breakdown_cathay"] = dict(CATHAY)
snap["funds_cathay_breakdown"] = dict(CATHAY)
snap["funds_cathay"] = CATHAY_TOTAL
snap["funds_cathay_market_value"] = CATHAY_TOTAL
for k in ("funds_total", "fund_market", "fund_market_value", "funds", "fund_total_market_value"):
    snap[k] = FUNDS_TOTAL
snap.setdefault("fund_nav_dates", {})["國泰直購（富達/聯博/B11）"] = "2026-10-26"
snap.setdefault("source_import_dates", {})["基金 國泰直購（富達/聯博/B11）"] = "2026-10-28"
snap["funds_cathay_note_1028"] = (
    "2026-10-28 國泰基金頁截圖（淨值日 2026/10/26）：參考現值 11,924,797（-0.63%）、"
    "本金 12,000,000、不含息參考報酬 -75,203。富達 5,870,021（含息 -0.53%／不含息 -2.17%）｜"
    "B11 5,076,582（+2.37%／+1.53%）｜聯博AD 978,194（-0.83%／-2.18%）；三檔逐檔合計＝頁首 ✓"
)

# ── ② 台股持股 14 檔（App 07:07）─────────────────────────────
# (代號, 股數, 成本均價, 現價, 市值, 未實現損益)
H = [
    ("0050", 2000, 84.90, 106.60, 213200, 43400),
    ("006208", 2000, 196.90, 244.60, 489200, 95400),
    ("009816", 16000, 12.49, 15.90, 254400, 54560),
    ("00646", 1000, 71.60, 78.75, 78750, 7150),
    ("00713", 2000, 54.80, 66.35, 132700, 23100),
    ("00878", 15000, 27.17, 35.40, 531000, 123450),
    ("0056", 1000, 37.15, 56.55, 56550, 19400),
    ("00981A", 8000, 26.32, 27.40, 219200, 8640),
    ("00984A", 10000, 14.56, 15.00, 150000, 4400),
    ("00919", 6000, 29.55, 32.75, 196500, 19200),
    ("00918", 1000, 28.55, 34.84, 34840, 6290),
    ("00888", 5000, 31.73, 32.12, 160600, 1950),
    ("00983D", 20000, 10.10, 9.85, 197000, -5000),
    ("00927", 2000, 37.90, 34.72, 69440, -6360),
]
TOTAL = sum(x[4] for x in H)
UNREAL = sum(x[5] for x in H)
APP_TOTAL, APP_UNREAL, APP_DAY = 2783380, 395540, -4040
print(f"逐檔市值合計 = {TOTAL:,}（App {APP_TOTAL:,}）｜未實現 = {UNREAL:,}（App {APP_UNREAL:,}）")
assert TOTAL == APP_TOTAL, TOTAL
assert abs(UNREAL - APP_UNREAL) <= 200, UNREAL   # 均價顯示截斷（00927 37.9／00983D 10.1）造成 ≤200 差

prev_total = snap.get("securities_total_market_value") or 0
names = {h["ticker"]: h.get("name", "") for h in snap.get("securities", {}).get("holdings", [])}
holdings = []
for t, sh, cost_avg, px, mv, pnl in H:
    cost = round(cost_avg * sh)
    holdings.append({
        "ticker": t, "name": names.get(t, t), "shares": sh, "price": px,
        "value": mv, "market_value": mv, "currency": "TWD",
        "cost": cost, "cost_avg": cost_avg, "pnl": pnl,
        "pnl_pct": round(pnl / cost * 100, 2),
    })

for k in ("securities_total_market_value", "securities_total", "securities_market",
          "securities_current_value", "securities_market_value", "securities_current",
          "total_stock_value"):
    snap[k] = TOTAL
snap["securities_unrealized_pnl"] = UNREAL
snap["securities_realized_pnl"] = 23460
snap["securities_realized_pnl_pct"] = 27.34
snap["securities"] = {
    "total_market_value": TOTAL,
    "unrealized_pnl": UNREAL,
    "unrealized_pnl_pct": 16.56,
    "realized_pnl": 23460,
    "realized_pnl_pct": 27.34,
    "holdings": holdings,
    "as_of": "2026-10-28",
    "source": "證券 App 持股明細截圖",
    "price_date": "2026-10-27",
    "note": ("2026-10-28 07:07 持股明細截圖（14 檔全數，逐檔合計＝頁首 2,783,380）｜"
             "當日 -4,040（-0.14%）｜未實現 +395,540（+16.56%）｜已實現 +23,460（+27.34%）"),
}
snap["holdings"] = holdings
snap["securities_breakdown"] = {t: mv for t, sh, c, px, mv, pnl in H}
snap["securities_note_20261028"] = (
    "2026-10-28 07:07 持股明細：總市值 2,783,380（14 檔）｜當日 -4,040（-0.14%）｜"
    "未實現 +395,540（+16.56%）｜已實現 +23,460（+27.34%）"
)
snap.setdefault("source_import_dates", {})["證券部位"] = "2026-10-28"

from asset_sync import sync_snapshot_keys, rebuild_liabilities   # noqa: E402
snap = sync_snapshot_keys(snap)
snap["total_assets"] = (snap["insurance_total"] + snap["securities_total_market_value"]
                        + snap["fund_market_value"] + snap["cash_total"])
snap = rebuild_liabilities(snap)
P.write_text(json.dumps(snap, ensure_ascii=False, indent=1).replace("\n", "\r\n"),
             encoding="utf-8", newline="")

print("--- 更新後 ---")
for k in ("cash_total", "securities_total_market_value", "insurance_total", "funds_cathay",
          "fund_market_value", "total_assets", "total_liabilities", "net_worth"):
    v = snap.get(k)
    print(f"  {k}: {v:,}" if isinstance(v, (int, float)) else f"  {k}: {v}")
print(f"  台股 vs 前值：{TOTAL - prev_total:+,}（前值 {prev_total:,}）")
print(f"  基金 vs 前值：{FUNDS_TOTAL - 12791770:+,}")
