# -*- coding: utf-8 -*-
"""2026-08-12 凱基證券截圖四源同步：snapshot holdings + DB holdings + assets"""
import json, sqlite3, datetime

SNAP = "snapshot.json"
DB = "dragon_assets.db"

# 截圖提取（ticker, name, shares, price, cost, pnl, pnl_pct, realized）
ROWS = [
    ("0050",  "元大台灣50",      2000, 105.20, 84.90, 40600, 23.91, 0),
    ("006208","富邦台50",        2000, 240.90, 196.90, 88000, 22.35, 0),
    ("009816","凱基台灣TOP50",   16000,15.26, 12.49, 44280, 22.15, 16800),
    ("00646", "元大S&P500",      1000, 78.35, 71.60, 6750, 9.43,  0),
    ("00713", "元大台灣高息低波", 2000, 61.20, 54.80, 12800, 11.68, 0),
    ("00878", "國泰永續高股息",  15000,33.52, 27.17, 95290, 23.38, 6660),
    ("0056",  "元大高股息",      1000, 52.70, 37.15, 15550, 41.86, 0),
    ("00981A","主動統一台股增長", 8000, 29.34, 26.32, 24200, 11.50, 0),
    ("00984A","主動安聯台灣高息",10000,15.31, 14.56, 7500, 5.15,  0),
    ("00919", "群益精選高息",    6000, 30.19, 29.55, 3860, 2.18,  0),
    ("00918", "大華優利高息30",  1000, 33.75, 28.55, 5200, 18.21, 0),
    ("009824","群益美優科技巨擘",10000,10.12, 9.93, 1900, 1.91,  0),
    ("009823","群益S&P500",      10000,10.62, 10.02, 6000, 5.99,  0),
    ("00888", "永豐台灣ESG",     5000, 32.61, 31.73, 4390, 2.77,  0),
    ("00983D","主動富邦複合收益",20000,10.07, 10.11, -700, -0.35, 0),
    ("00401A","摩根台灣鑫收",    0,    13.57, None,  0,    0.0,   0),  # 新增 watchlist
]
TOTAL = 2867170
UNREALIZED = 355620
UNREALIZED_PCT = 14.16
REALIZED = 23460
TODAY = "2026-08-12"
NEW_TOTAL_ASSETS = 14264173  # 14,251,163 + 13,010（證券增）

# ========== 1) snapshot.json ==========
s = json.load(open(SNAP, encoding="utf-8"))
holdings = []
for t, name, shares, price, cost, pnl, pnl_pct, realized in ROWS:
    holdings.append({
        "ticker": t, "name": name, "shares": shares, "price": price,
        "value": round(shares * price, 2) if shares else 0.0,
        "cost": cost, "pnl": pnl, "pnl_pct": pnl_pct, "currency": "TWD",
    })
sec = s.setdefault("securities", {})
sec["total_market_value"] = TOTAL
sec["market_value"] = TOTAL
sec["unrealized_pnl"] = UNREALIZED
sec["unrealized_pnl_pct"] = UNREALIZED_PCT
sec["realized_pnl"] = REALIZED
sec["holdings"] = holdings
sec["date"] = TODAY
sec["as_of"] = f"{TODAY} 盤中"
s["securities_total"] = TOTAL
s["securities_total_market_value"] = TOTAL
s["total_assets"] = NEW_TOTAL_ASSETS
json.dump(s, open(SNAP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"✅ snapshot: securities={TOTAL:,} total_assets={NEW_TOTAL_ASSETS:,} holdings={len(holdings)} 檔")

# ========== 2) DB holdings（修正舊值 + 補 00401A） ==========
db = sqlite3.connect(DB)
for t, name, shares, price, cost, pnl, pnl_pct, realized in ROWS:
    if t == "00401A":
        db.execute("INSERT OR IGNORE INTO holdings (ticker, shares, cost_price, source, updated_at) VALUES (?,?,?,?,?)",
                   (t, 0, 0.0, "app_screenshot", datetime.datetime.now().isoformat(timespec="seconds")))
        continue
    db.execute("UPDATE holdings SET shares=?, cost_price=?, source='app_screenshot', updated_at=? WHERE ticker=?",
               (shares, cost, datetime.datetime.now().isoformat(timespec="seconds"), t))
# assets 表：只更新當日 securities + total_assets
db.execute("UPDATE assets SET securities=?, total_assets=? WHERE date=?",
           (TOTAL, NEW_TOTAL_ASSETS, TODAY))
db.commit()
print("✅ DB: holdings 修正（00878/009816/00981A + 00401A 新增）+ assets securities/total_assets 更新")

# ========== 3) 驗證 ==========
sec_sum = sum(h["value"] for h in holdings)
pnl_sum = sum(h["pnl"] for h in holdings)
print(f"驗證: 市值總和={sec_sum:,} (目標 {TOTAL:,}) {'OK' if sec_sum==TOTAL else 'FAIL'}")
print(f"驗證: 未實現總和={pnl_sum:,} (目標 {UNREALIZED:,}) {'OK' if pnl_sum==UNREALIZED else 'FAIL'}")
db.close()
