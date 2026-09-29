#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-09-29 台股持倉真值（持股 App 截圖 15 檔）→ securities_* 全同步 + 逐檔 holdings。"""
import json
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
P = BASE / "snapshot.json"
snap = json.loads(P.read_text(encoding="utf-8"))

# (代號, 名稱, 股數, 成本均價, 現價, 市值, 未實現損益)
H = [
    ("0050", "元大台灣50", 2000, 84.90, 111.30, 222600, 52800),
    ("006208", "富邦台50", 2000, 196.90, 255.20, 510400, 116600),
    ("009816", "凱基台灣TOP50", 16000, 12.49, 16.40, 262400, 62520),
    ("00646", "元大S&P500", 1000, 71.60, 76.90, 76900, 5300),
    ("00713", "元大台灣高息低波", 2000, 54.80, 62.90, 125800, 16200),
    ("00878", "國泰永續高股息", 15000, 27.17, 34.83, 522450, 114940),
    ("0056", "元大高股息", 1000, 37.15, 56.55, 56550, 19400),
    ("00981A", "主動統一台灣增長", 8000, 26.32, 30.31, 242480, 31960),
    ("00984A", "主動安聯台灣高息", 10000, 14.56, 15.62, 156200, 10600),
    ("00919", "群益台灣精選高息", 6000, 29.55, 31.88, 191280, 14000),
    ("00918", "大華優利高填息30", 1000, 28.55, 33.90, 33900, 5350),
    ("009824", "群益美國科技巨頭", 10000, 9.93, 10.49, 104900, 5600),
    ("009823", "群益S&P500", 10000, 10.02, 10.43, 104300, 4100),
    ("00888", "永豐台灣ESG", 5000, 31.73, 35.85, 179250, 20590),
    ("00983D", "主動富邦複合收益", 20000, 10.11, 9.60, 192000, -10100),
]
TOTAL = sum(x[5] for x in H)
UNREAL = sum(x[6] for x in H)
print(f"逐檔市值合計 = {TOTAL:,}（截圖 2,981,410）｜未實現 = {UNREAL:,}（截圖 469,860）")
assert TOTAL == 2981410 and UNREAL == 469860, (TOTAL, UNREAL)

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
                      "note": "2026-09-29 持股 App 截圖（15 檔，14:00 前後報價）；已實現損益 23,460（+27.34%）"}
snap["holdings"] = holdings
snap["securities_breakdown"] = {t: mv for t, n, sh, cost, px, mv, pnl in H}
snap["securities_note_20260929"] = ("2026-09-29 持股截圖：持有股票市值 2,981,410｜未實現 +469,860（+18.71%）"
                                    "｜已實現 +23,460（+27.34%）")

from asset_sync import sync_snapshot_keys, rebuild_liabilities   # noqa: E402
snap = sync_snapshot_keys(snap)
snap["total_assets"] = (snap["insurance_total"] + snap["securities_total_market_value"]
                        + snap["fund_market_value"] + snap["cash_total"])
snap = rebuild_liabilities(snap)
P.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
print("--- 更新後 ---")
for k in ("cash_total", "securities_total_market_value", "insurance_total", "fund_market_value",
          "total_assets", "total_liabilities", "net_worth"):
    print(f"  {k}: {snap.get(k):,}")
