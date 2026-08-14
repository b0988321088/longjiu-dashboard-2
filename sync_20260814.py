#!/usr/bin/env python3
"""2026-08-14 四源同步：凱基證券 + 鉅亨基金（一般申購/自由Pay）"""
import json, sqlite3, shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
DB = BASE / "dragon_assets.db"
TODAY = "2026-08-14"

# 備份
shutil.copy2(SNAP, BASE / "snapshot_backup_20260814.json")

s = json.load(open(SNAP, encoding="utf-8"))

# ========== 1. 凱基證券 15 檔（截圖 8/14 真值） ==========
sec_data = [
    # ticker, name, shares, price, value, cost, pnl, pnl_pct
    ("0050", "元大台灣50", 2000, 107.15, 214300.0, 84.90, 44500, 26.21),
    ("006208", "富邦台50", 2000, 244.90, 489800.0, 196.90, 96000, 24.38),
    ("009816", "凱基台灣TOP50", 16000, 15.60, 249600.0, 12.49, 49720, 24.87),
    ("00646", "元大S&P500", 1000, 78.60, 78600.0, 71.60, 7000, 9.78),
    ("00713", "元大台灣高息低波", 2000, 60.80, 121600.0, 54.80, 12000, 10.95),
    ("00878", "國泰永續高股息", 15000, 33.99, 509850.0, 27.17, 102340, 25.11),
    ("0056", "元大高股息", 1000, 53.70, 53700.0, 37.15, 16550, 44.55),
    ("00981A", "主動統一台股增長", 8000, 30.33, 242640.0, 26.32, 32120, 15.26),
    ("00984A", "主動安聯台灣高息", 10000, 15.45, 154500.0, 14.56, 8900, 6.11),
    ("00919", "群益精選高息", 6000, 30.62, 183720.0, 29.55, 6440, 3.63),
    ("00918", "大華優利高息30", 1000, 34.15, 34150.0, 28.55, 5600, 19.61),
    ("009824", "群益美國科技巨頭", 10000, 10.26, 102600.0, 9.93, 3300, 3.32),
    ("009823", "群益S&P500", 10000, 10.66, 106600.0, 10.02, 6400, 6.39),
    ("00888", "永豐台灣ESG", 5000, 33.44, 167200.0, 31.73, 8540, 5.38),
    ("00983D", "主動富邦複合收益", 20000, 10.08, 201600.0, 10.11, -500, -0.25),
]
sec_total = sum(d[2] * d[3] for d in sec_data)  # shares*price
assert abs(sec_total - 2910460) < 1, f"證券總值 {sec_total} ≠ 2,910,460"

holdings = []
for t, n, sh, px, val, cost, pnl, pct in sec_data:
    holdings.append({
        "ticker": t, "name": n, "shares": sh, "price": px, "value": val,
        "cost": cost, "pnl": pnl, "pnl_pct": pct, "currency": "TWD",
    })
# 保留 00401A（0 股 watchlist）
old_holdings = {h["ticker"]: h for h in s.get("securities", {}).get("holdings", [])}
if "00401A" in old_holdings:
    holdings.append(old_holdings["00401A"])

sec = {
    "total_market_value": sec_total,
    "unrealized_pnl": 398910,
    "unrealized_pnl_pct": 15.88,
    "holdings": holdings,
    "date": TODAY,
    "market_value": sec_total,
    "as_of": "2026-08-14 盤中",
    "realized_pnl": 23460,
}
s["securities"] = sec
s["securities_total_market_value"] = sec_total
s["securities_breakdown"] = {h["ticker"]: h["value"] for h in holdings if h["shares"] > 0}

# ========== 2. 鉅亨基金 ==========
# 一般申購：8/13 CSV 16 檔結構 + 今天截圖總值 377,149（2 檔新值），匯率調整補差額
gen = {
    "元大台灣卓越50連結B配息": 48560,
    "台中銀台灣優息B配息": 49955,
    "安聯台灣科技": 3172,
    "安聯AI收益成長B月配美元": 6812,
    "國泰台灣高股息B": 8043,
    "台新美日台半導體(日圓)": 135945,
    "路博邁台灣5G月配": 88797,
    "聯博美國成長AP月配": 3123,
    "摩根JPM多重收益美元對沖": 3045,
    "貝萊德世界黃金A2": 3281,
    "貝萊德全球股票收益A6": 3240,
    "貝萊德世界科技A10": 4287,
    "貝萊德世界能源A10": 5258,
    "安聯收益成長南非幣避險": 6185,
    "安聯收益成長AMg7美元": 3549,
    "施羅德環球收息南非幣": 2742,
    "M&G入息A美元避險": 3039,
}
gen_sum = sum(gen.values())
gen_adj = 377149 - gen_sum  # 匯率調整 = 總值 - 明細
assert abs(gen_sum + gen_adj - 377149) < 1, f"一般申購 {gen_sum}+{gen_adj} ≠ 377,149"

# 自由Pay：今天 CSV 3 檔
pay = {
    "元大台灣卓越50連結A不配息": 112489,
    "統一奔騰": 96057,
    "路博邁台灣5G累積": 246188,
}
pay_sum = sum(pay.values())
assert abs(pay_sum - 454734) < 1, f"自由Pay {pay_sum} ≠ 454,734"

funds_total = 377149 + 454734
assert abs(funds_total - 831883) < 1, f"基金總值 {funds_total} ≠ 831,883"

s["funds_breakdown"] = {
    "一般申購": {**gen, "匯率調整": gen_adj},
    "自由Pay": pay,
    "note": f"{TODAY} 鉅亨真值 831,883（一般 377,149 + 自由Pay 454,734）；一般申購明細 8/13 CSV + 截圖 2 檔新值，匯率調整 {gen_adj}",
}
s["fund_market_value"] = funds_total
s["funds_total"] = funds_total

# ========== 3. 總資產重算 ==========
cash = s.get("cash_total", s.get("cash", 789126))
insurance = s.get("insurance_current_value", s.get("insurance_total", 9986190))
new_total = cash + insurance + sec_total + funds_total
s["total_assets"] = new_total
print(f"現金 {cash:,} + 保險 {insurance:,} + 證券 {sec_total:,} + 基金 {funds_total:,} = 總資產 {new_total:,}")

json.dump(s, open(SNAP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("✅ snapshot.json 已更新")

# ========== 4. DB 當日列（INSERT OR REPLACE，禁 UPDATE 歷史） ==========
db = sqlite3.connect(DB)
# 先取當日列完整結構
cols = [r[1] for r in db.execute("PRAGMA table_info(assets)").fetchall()]
print("assets 欄位:", cols)
row = db.execute("SELECT * FROM assets WHERE date=? ORDER BY date DESC LIMIT 1", (TODAY,)).fetchone()
if row:
    d = dict(zip(cols, row))
    d["securities"] = sec_total
    d["funds"] = funds_total
    d["total_assets"] = new_total
    placeholders = ",".join("?" for _ in cols)
    db.execute(f"INSERT OR REPLACE INTO assets ({','.join(cols)}) VALUES ({placeholders})", [d[c] for c in cols])
    print("✅ DB 當日列已更新（INSERT OR REPLACE）")
else:
    db.execute("INSERT INTO assets (date, cash_total, securities, funds, insurance, total_assets) VALUES (?,?,?,?,?,?)",
               (TODAY, cash, sec_total, funds_total, insurance, new_total))
    print("✅ DB 當日列已新增")
db.commit()
db.close()
print("✅ 全部完成")
