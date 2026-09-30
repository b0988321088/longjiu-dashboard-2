#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-09-30 台股持倉真值（持股 App 截圖 15 檔、19:48 收盤）→ securities_* 全同步 + 逐檔 holdings。"""
import json
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
P = BASE / "snapshot.json"
snap = json.loads(P.read_text(encoding="utf-8"))

# (代號, 名稱, 股數, 成本均價, 現價, 市值, 未實現損益)
H = [
    ("0050", "元大台灣50", 2000, 84.90, 112.05, 224100, 54300),
    ("006208", "富邦台50", 2000, 196.90, 256.30, 512600, 118800),
    ("009816", "凱基台灣TOP50", 16000, 12.49, 16.49, 263840, 64000),
    ("00646", "元大S&P500", 1000, 71.60, 77.15, 77150, 5550),
    ("00713", "元大台灣高息低波", 2000, 54.80, 63.00, 126000, 16400),
    ("00878", "國泰永續高股息", 15000, 27.17, 34.90, 523500, 115950),
    ("0056", "元大高股息", 1000, 37.15, 56.95, 56950, 19800),
    ("00981A", "主動統一台灣增長", 8000, 26.32, 30.54, 244320, 33760),
    ("00984A", "主動安聯台灣高息", 10000, 14.56, 15.71, 157100, 11500),
    ("00919", "群益台灣精選高息", 6000, 29.55, 31.88, 191280, 13980),
    ("00918", "大華優利高填息30", 1000, 28.55, 33.89, 33890, 5340),
    ("009824", "群益美國科技巨頭", 10000, 9.93, 10.56, 105600, 6300),
    ("009823", "群益S&P500", 10000, 10.02, 10.47, 104700, 4500),
    ("00888", "永豐台灣ESG", 5000, 31.73, 36.16, 180800, 22150),
    ("00983D", "主動富邦複合收益", 20000, 10.11, 9.59, 191800, -10400),
]
TOTAL = sum(x[5] for x in H)
UNREAL = sum(x[6] for x in H)
PREV = 2981410          # 2026-09-29 收盤真值
APP_TOTAL, APP_UNREAL, APP_DAY = 2993630, 482080, 12220
print(f"逐檔市值合計 = {TOTAL:,}（App 總市值 2,993,630）｜未實現 = {UNREAL:,}（App 482,080）")
print(f"當日變動 = {TOTAL - PREV:+,}（App +12,220）")
assert TOTAL == APP_TOTAL, TOTAL
assert TOTAL - PREV == APP_DAY, TOTAL - PREV
assert abs(UNREAL - APP_UNREAL) <= 200, UNREAL  # 均價顯示截斷（00983D 10.1→10.11）造成 ≤200 元差

holdings = [{"ticker": t, "name": n, "shares": sh, "price": px, "cost": round(cost * sh),
             "value": mv, "market_value": mv, "pnl": pnl,
             "pnl_pct": round(pnl / (cost * sh) * 100, 2), "currency": "TWD"}
            for t, n, sh, cost, px, mv, pnl in H]

snap["securities_total_market_value"] = TOTAL
snap["securities_total"] = TOTAL
snap["securities_market"] = TOTAL
snap["securities_current_value"] = TOTAL
snap["securities_market_value"] = TOTAL
snap["total_stock_value"] = TOTAL
snap["securities_unrealized_pnl"] = UNREAL
snap["securities_realized_pnl"] = 23460
snap["securities_realized_pnl_pct"] = 27.34
snap["securities"] = {"total_market_value": TOTAL, "unrealized_pnl": UNREAL,
                      "unrealized_pnl_pct": round(UNREAL / (TOTAL - UNREAL) * 100, 2),
                      "holdings": holdings,
                      "price_date": "2026-09-30",
                      "note": "2026-09-30 持股 App 截圖（15 檔，19:48 收盤後）；當日 +12,220（+0.41%）｜未實現 +482,080（+19.19%）｜已實現 +23,460（+27.34%）"}
snap["holdings"] = holdings
snap["securities_breakdown"] = {t: mv for t, n, sh, cost, px, mv, pnl in H}
snap["securities_note_20260930"] = ("2026-09-30 持股截圖：持有股票市值 2,993,630（15 檔）｜未實現 +482,080（+19.19%）"
                                    "｜已實現 +23,460（+27.34%）｜當日 +12,220（+0.41%）")

from asset_sync import sync_snapshot_keys, rebuild_liabilities   # noqa: E402
snap = sync_snapshot_keys(snap)
snap["total_assets"] = (snap["insurance_total"] + snap["securities_total_market_value"]
                        + snap["fund_market_value"] + snap["cash_total"])
snap = rebuild_liabilities(snap)
P.write_text(json.dumps(snap, ensure_ascii=False, indent=1).replace("\n", "\r\n"),
             encoding="utf-8", newline="")
print("--- 更新後 ---")
for k in ("cash_total", "securities_total_market_value", "insurance_total", "fund_market_value",
          "total_assets", "total_liabilities", "net_worth"):
    print(f"  {k}: {snap.get(k):,}")
