#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-11-11 真值套用（使用者指示：用現有盤中資料更新即可）

來源（使用者 2026-11-11 Telegram 截圖／CSV）：
  ① 國泰轉貸專區「總庫存損益」：池 11,761,894／本金 12,000,000／含息總報酬 +0.12%
  ② 安聯 App 09:56：A 4,953,272（-1.17%）／B 2,434,962（-9.28%）／合計 7,388,234
  ③ 鉅亨 帳戶總覽 + 一般申購 CSV(37) + 自由PAY 頁：合計 713,139
  ④ 第一金人壽：帳戶價值 1,882,263／累計配息 169,024／保費 2,000,000
  ⑤ 台股持股 10:02 盤中：市值 2,696,710／未實現 +227,200（+9.20%）／已實現 +23,460
  ⑥ 匯率：USD/TWD 32.9225、JPY/TWD 0.2188（鉅亨平台）

⚠️ 台股為 10:02 盤中價（非官方收盤）→ price_type=盤中、provisional=true，
   13:30 收盤後須以官方收盤價覆蓋（check_securities_integrity 閘門屆時重新驗證）。
"""
import json
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
P = BASE / "snapshot.json"
snap = json.loads(P.read_text(encoding="utf-8"))

# ── ① 國泰擔保池（三檔）──────────────────────────────────────
CATHAY = {
    "富達全球動能多元B股C月配息美元": 5718614,
    "貝萊德智慧數據收益成長B11-美元-強化穩定月配息": 5060413,
    "聯博全球多元收益AD美元月配": 982867,
}
CATHAY_TOTAL = 11761894
assert sum(CATHAY.values()) == CATHAY_TOTAL, sum(CATHAY.values())

snap["fund_breakdown_cathay"] = dict(CATHAY)
snap["funds_cathay_breakdown"] = dict(CATHAY)
snap["funds_cathay"] = CATHAY_TOTAL
snap["funds_cathay_market_value"] = CATHAY_TOTAL
snap["funds_cathay_detail_20261111"] = {
    "富達全球動能多元B股C月配息美元": {"本金": 6000000, "現值": 5718614, "淨值USD": 11.05,
        "淨值日": "2026-11-10", "配息累計": 147427, "不含息_pct": -4.69, "含息_pct": -2.23},
    "貝萊德智慧數據收益成長B11-美元-強化穩定月配息": {"本金": 5000000, "現值": 5060413, "淨值USD": 9.93,
        "淨值日": "2026-11-09", "配息累計": 84800, "不含息_pct": 1.21, "含息_pct": 2.90},
    "聯博全球多元收益AD美元月配": {"本金": 1000000, "現值": 982867, "淨值USD": 8.83,
        "淨值日": "2026-11-10", "配息累計": 20553, "不含息_pct": -1.71, "含息_pct": 0.34},
}
snap["funds_cathay_note_1111"] = (
    "2026-11-11 國泰轉貸專區截圖：總投資本金 12,000,000、參考現值 11,761,894、"
    "未實現 -238,106（不含息 -1.98%）、累計配息 252,780、含息總報酬 +0.12%。"
    "富達 5,718,614（含息 -2.23%／不含息 -4.69%）｜B11 5,060,413（+2.90%／+1.21%）｜"
    "聯博AD 982,867（+0.34%／-1.71%）；三檔逐檔合計＝表頭 ✓"
)
snap.setdefault("fund_nav_dates", {})["國泰直購（富達/聯博/B11）"] = "2026-11-10"
snap.setdefault("source_import_dates", {})["基金 國泰直購（富達/聯博/B11）"] = "2026-11-11"

# ── ② 安聯 A/B 與 ③ 鉅亨 ────────────────────────────────────
ALLIANZ_A, ALLIANZ_B = 4953272, 2434962
ALLIANZ_TOTAL = ALLIANZ_A + ALLIANZ_B
assert ALLIANZ_TOTAL == 7388234, ALLIANZ_TOTAL
B_FUNDS = {
    "NTDEQ2640 元大台灣高股息優質龍頭基金-新台幣(B)配息": 254106,
    "NTDET0010 元大台灣卓越50": 902864,
    "USDEQ3490 安聯收益成長基金-AM穩定月收類股(美元)": 486081,
    "USDEQ5700 M&G入息基金A(美元避險月配)F": 632138,
    "USDEQ6730 貝萊德世界黃金基金 A10美元(總報酬穩定配息)": 159773,
}
assert sum(B_FUNDS.values()) == ALLIANZ_B, sum(B_FUNDS.values())

snap["policy_a_total"] = ALLIANZ_A
snap["policy_b_total"] = ALLIANZ_B
snap["allianz_combined"] = ALLIANZ_TOTAL
ib = snap["insurance_breakdown"]
ib["policy_a_total"] = ALLIANZ_A
ib["policy_b_total"] = ALLIANZ_B
ib["allianz_ab_total"] = ALLIANZ_TOTAL
ib["policy_b_funds"] = dict(B_FUNDS)
ib["firstjin_total"] = 1882263
ib["allianz_note_20261111"] = (
    "2026-11-11 09:56 安聯 App：帳戶總價值 7,388,234（A 4,953,272 -1.17%／B 2,434,962 -9.28%）；"
    "本月累積配息撥回 11,076（2 筆）；風險屬性積極型（效期 2027/01/21）。"
    "B 逐檔 5 檔合計＝2,434,962 ✓；A 逐檔本次未提供截圖 → 保留 11/10 評價值 4,950,505，"
    "僅 A 總值更新（差 2,767 為評價日差，下次 A 明細截圖時一併校正）。"
)

GEN = {
    "元大台灣卓越50ETF(0050)連結基金-台幣B配息": 45233,
    "台中銀台灣優息基金-B配息台幣": 43089,
    "安聯台灣科技基金": 2658,
    "安聯AI收益成長多重資產基金-B(月配)美元": 185,
    "國泰台灣高股息基金B": 6854,
    "台新美日台半導體基金A-日圓": 109296,      # 日圓 499,446 × 0.2188（平台表頭反推）
    "路博邁台灣5G股票基金T月配級別(台幣)": 73370,
    "聯博-全球多元收益基金AD月配美元": 2941,
    "聯博-美國成長基金AP總報酬月配美元": 2966,
    "摩根基金-JPM多重收益美元對沖A穩定月配": 2958,
    "貝萊德世界黃金A2美元": 3281,
    "貝萊德全球股票收益A6美元穩定配息": 3118,
    "貝萊德世界科技A10美元總報酬穩定配息": 3691,
    "貝萊德世界能源A10美元總報酬穩定配息": 5367,
    "貝萊德世界健康科學A10美元總報酬穩定配息": 5305,
    "貝萊德世界黃金A10美元總報酬穩定配息": 2629,
    "貝萊德全球智慧數據股票入息A11美元強化穩定配息": 3013,
    "富達全球動能多元基金A股C月配美元": 2874,
    "安聯收益成長AMg7月收總收益美元": 3376,
    "M&G入息基金A(美元避險月配)F": 3011,
}
GEN_TOTAL = 325215
assert sum(GEN.values()) == GEN_TOTAL, sum(GEN.values())
PAY = {
    "元大台灣卓越50ETF(0050)連結基金-台幣A不配息": 104771,
    "統一奔騰基金": 79255,
    "路博邁台灣5G股票基金T累積級別(台幣)": 203898,
}
PAY_TOTAL = 387924
assert sum(PAY.values()) == PAY_TOTAL, sum(PAY.values())
HENG_TOTAL = GEN_TOTAL + PAY_TOTAL
assert HENG_TOTAL == 713139, HENG_TOTAL

fb = snap["funds_breakdown"]
fb["一般申購"] = dict(GEN)
fb["自由Pay"] = dict(PAY)
fb["一般申購_平台小計"] = GEN_TOTAL
fb["自由Pay_小計"] = PAY_TOTAL
fb["鉅亨平台合計"] = HENG_TOTAL
fb["note"] = (
    "2026-11-11 鉅亨真值：一般申購 325,215（20 檔）＋ 自由PAY 387,924（3 檔）＝ 713,139，"
    "與帳戶總覽表頭一致 ✓。一般申購來源＝CSV(37)；日圓檔 499,446 円 × 0.2188 = 109,296；"
    "自由PAY＝路博邁5G T累積 203,898（含Pay +89.99%）／0050 A不配息 104,771／統一奔騰 79,255（-20.75%）。"
    "美元檔匯率 32.9225。"
)
snap["firstjin_total"] = 1882263
snap["firstjin_note_20261111"] = (
    "2026-11-11 第一金人壽 App：保單帳戶價值 1,882,263、累計總繳保費 2,000,000、累計提領 0、"
    "累計配息 169,024；投資總成本報酬率 -5.8%、總繳保費含息報酬 +2.56%（不含息 -5.89%）；"
    "100% 單一標的 ID05 M&G入息A(美元避險月配)，標的投報率 不含息 1.68%／含息 2.22% → "
    "約 8pp 為保單費用與匯差。⚠️ 走勢圖 2026/07 曾近歸零後 08 月跳回，累計提領為 0，待向第一金索取 7 月交易明細釐清。"
)

FUNDS_TOTAL = CATHAY_TOTAL + HENG_TOTAL
for k in ("funds_total", "fund_market", "fund_market_value", "funds", "fund_total_market_value"):
    snap[k] = FUNDS_TOTAL
snap["fund_market"] = FUNDS_TOTAL
snap["insurance_total"] = ALLIANZ_TOTAL + 1882263

# ── ⑤ 台股 15 檔（10:02 盤中）────────────────────────────────
PX = {"0050": 101.00, "006208": 231.70, "009816": 15.03, "00646": 78.15, "00713": 62.45,
      "00878": 33.08, "0056": 52.50, "00981A": 24.24, "00984A": 13.60, "00919": 30.96,
      "00918": 32.85, "00888": 29.27, "00983D": 9.95, "00927": 30.96, "2610": 23.05}
APP_TOTAL, APP_UNREAL = 2696710, 227200
old = snap["securities"]["holdings"]
holdings, sec_bd, tot, unr = [], {}, 0, 0
for h in old:
    t, sh, avg = h["ticker"], h["shares"], h["cost_avg"]
    px = PX[t]
    mv = round(sh * px)
    cost = round(avg * sh)
    pnl = round(mv - cost)
    tot += mv
    unr += pnl
    sec_bd[t] = mv
    holdings.append({**h, "price": px, "value": mv, "market_value": mv, "cost": cost,
                     "pnl": pnl, "pnl_pct": round(pnl / cost * 100, 2),
                     "price_date": "2026-11-11", "price_type": "盤中10:02",
                     "price_source": "券商持股即時報價截圖（盤中）"})
assert tot == APP_TOTAL, f"逐檔合計 {tot:,} ≠ 截圖 {APP_TOTAL:,}"
assert abs(unr - APP_UNREAL) <= 500, f"未實現 {unr:,} ≠ 截圖 {APP_UNREAL:,}"

for k in ("securities_total_market_value", "securities_total", "securities_market",
          "securities_current_value", "securities_market_value", "securities_current",
          "total_stock_value"):
    snap[k] = tot
snap["securities_unrealized_pnl"] = unr
snap["securities"] = {
    "total_market_value": tot, "unrealized_pnl": unr,
    "unrealized_pnl_pct": round(unr / (tot - unr) * 100, 2),
    "realized_pnl": 23460, "realized_pnl_pct": 27.34,
    "holdings": holdings, "as_of": "2026-11-11", "price_date": "2026-11-11",
    "price_type": "盤中（10:02 即時報價）", "provisional": True,
    "source": "券商持股即時報價截圖 10:02（盤中，非官方收盤）",
    "note": ("2026-11-11 10:02 盤中截圖：15 檔市值 2,696,710（逐檔合計相符 ✓）、"
             "未實現 +227,200（+9.20%）、已實現 +23,460（+27.34%）。"
             "⚠️ 盤中價非官方收盤，13:30 後須以 TWSE 收盤覆蓋並重跑 check_securities_integrity。"),
}
snap["holdings"] = holdings
snap["securities_breakdown"] = sec_bd
snap["securities_unrealized_pnl_pct"] = snap["securities"]["unrealized_pnl_pct"]

# ── ⑥ 匯率 ──────────────────────────────────────────────────
snap["fx_rates"] = {"jpy_to_twd": 0.2188, "usd_to_twd": 32.9225, "zar_to_twd": 1.74,
                    "note": "2026-11-11 鉅亨平台截圖反推（USD 32.9225；JPY 由表頭 713,139−603,658−185.17 反推 0.2188）"}

# ── 派生：同義鍵／總資產／負債 ───────────────────────────────
from asset_sync import sync_snapshot_keys, rebuild_liabilities   # noqa: E402
snap = sync_snapshot_keys(snap)
snap["total_assets"] = (snap["insurance_total"] + snap["securities_total_market_value"]
                        + snap["fund_market"] + snap["cash_total"])
snap = rebuild_liabilities(snap)
snap["generated_at"] = "2026-11-11T10:10:00"
P.write_text(json.dumps(snap, ensure_ascii=False, indent=1).replace("\n", "\r\n"),
             encoding="utf-8", newline="")

print("--- 2026-11-11 真值套用完成 ---")
for k in ("insurance_total", "securities_total_market_value", "fund_market", "cash_total",
          "total_assets", "total_liabilities", "net_worth", "funds_cathay"):
    print(f"  {k}: {snap.get(k):,}")
print(f"  台股未實現: {unr:+,}（截圖 {APP_UNREAL:,}）｜報酬率 {snap['securities']['unrealized_pnl_pct']}%")
print(f"  安聯 A/B/合計: {ALLIANZ_A:,} / {ALLIANZ_B:,} / {ALLIANZ_TOTAL:,}")
print(f"  鉅亨: 一般 {GEN_TOTAL:,} + 自由PAY {PAY_TOTAL:,} = {HENG_TOTAL:,}")
print(f"  第一金: 1,882,263｜國泰池: {CATHAY_TOTAL:,}｜LTV {5900000/CATHAY_TOTAL*100:.2f}%")
