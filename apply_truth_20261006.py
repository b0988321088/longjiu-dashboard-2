#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-10-06 真值日：現金(Moneybook 10/06) + 證券(10/06 13:30 收盤) + 國泰/鉅亨基金 + 安聯保單B"""
import json, shutil, sys
from pathlib import Path
BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
sys.path.insert(0, str(BASE))
P = BASE / "snapshot.json"
shutil.copy(P, BASE / "snapshot.backup.json")
snap = json.loads(P.read_text(encoding="utf-8"))
old = dict(snap)

# ================= 1. 證券：10/06 13:30 收盤逐檔新價 =================
PX = {"0050":116.50,"006208":265.90,"009816":17.06,"00646":77.85,"00713":62.95,"00878":35.17,
      "0056":58.10,"00981A":32.60,"00984A":16.25,"00919":31.80,"00918":34.14,"009824":10.83,
      "009823":10.56,"00888":36.87,"00983D":9.53}
holdings = []
for h in snap["securities"]["holdings"]:
    t = h["ticker"]; sh = h.get("shares", 0); cost = h.get("cost", 0)
    p = PX.get(t, h.get("price"))
    mv = round(p * sh, 2)
    pnl = round(mv - cost, 2)
    holdings.append({"ticker": t, "name": h["name"], "shares": sh, "price": p, "cost": cost,
                     "value": mv, "market_value": mv, "pnl": pnl,
                     "pnl_pct": round(pnl / cost * 100, 2) if cost else 0,
                     "currency": h.get("currency", "TWD")})
TOTAL = round(sum(h["market_value"] for h in holdings), 2)
UNREAL = round(sum(h["pnl"] for h in holdings), 2)
assert TOTAL == 3064250, f"證券逐檔合計 {TOTAL:,} != 3,064,250"
assert abs(UNREAL - 552700) <= 300, f"未實現 {UNREAL:,} 與畫面 552,700 差 >300"   # 均價顯示截斷造成 <300 元差
UNREAL = 552700  # 以 App 真值為準
for k in ("securities_total_market_value","securities_total","securities_market","securities_current_value",
          "securities_market_value","total_stock_value"):
    snap[k] = TOTAL
snap["securities_unrealized_pnl"] = UNREAL
snap["securities_realized_pnl"] = 23460
snap["securities_realized_pnl_pct"] = 27.34
snap["securities"] = {"total_market_value": TOTAL, "unrealized_pnl": UNREAL,
                      "unrealized_pnl_pct": round(UNREAL / (TOTAL - UNREAL) * 100, 2),
                      "realized_pnl": 23460, "realized_pnl_pct": 27.34,
                      "holdings": holdings, "price_date": "2026-10-06",
                      "note": "2026-10-06 13:30 收盤即時報價（15 檔）；未實現 +552,700（+22.01%）｜已實現 +23,460（+27.34%）"}
snap["holdings"] = holdings
snap["securities_breakdown"] = {h["ticker"]: h["market_value"] for h in holdings}
snap["securities_note_20261006"] = ("2026-10-06 13:30 收盤：持有股票市值 3,064,250（15 檔）"
                                    "｜未實現 +552,700（+22.01%）｜已實現 +23,460（+27.34%）")

# ================= 2. 國泰直購基金（10/01、10/05 淨值截圖）=================
CAT = {"富達全球動能多元B股C月配息美元": 5770951,
       "貝萊德智慧數據收益成長B11-美元-強化穩定月配息": 4882121,
       "聯博全球多元收益AD美元月配": 963376}
assert sum(CAT.values()) == 11616448
snap["funds_cathay"] = 11616448
snap["funds_cathay_breakdown"] = dict(CAT)
snap["fund_breakdown_cathay"] = dict(CAT)
snap["funds_breakdown"]["國泰直購"] = dict(CAT)
snap["funds_cathay_note_1006"] = ("2026-10-06 國泰基金頁截圖（三檔）：富達 5,770,951／B11 4,882,121／聯博 963,376"
                                  " ＝ 11,616,448（本金 12,000,000、不含息 −383,552、−3.20%；含息 −3.00%／−2.36%／−2.31%）")

# ================= 3. 鉅亨 Fund口袋（平台卡片等值台幣）=================
GEN = {"元大台灣卓越50ETF(0050)連結基金-台幣B配息": 52725,
       "台中銀台灣優息基金-B配息台幣": 51810, "安聯台灣科技基金": 3552,
       "安聯AI收益成長多重資產基金-B(月配)美元": 6611, "國泰台灣高股息基金B": 8994,
       "台新美日台半導體基金A-日圓": 136305, "路博邁台灣5G股票基金T月配級別(台幣)": 99738,
       "聯博-全球多元收益基金AD月配美元": 2883, "聯博-美國成長基金AP總報酬月配美元": 3053,
       "摩根基金-JPM多重收益美元對沖A穩定月配": 2922, "貝萊德世界黃金A2美元": 3089,
       "貝萊德全球股票收益A6美元穩定配息": 3122, "貝萊德世界科技A10美元總報酬穩定配息": 4454,
       "貝萊德世界能源A10美元總報酬穩定配息": 5270, "貝萊德世界健康科學A10美元總報酬穩定配息": 4641,
       "貝萊德世界黃金A10美元總報酬穩定配息": 2499, "富達全球動能多元基金A股C月配美元": 2940,
       "安聯收益成長AMg7月收總收益美元": 3368, "M&G入息基金A(美元避險月配)F": 2924}
FREE = {"元大台灣卓越50ETF(0050)連結基金-台幣A不配息": 122129,
        "統一奔騰基金": 107775, "路博邁台灣5G股票基金T累積級別(台幣)": 274750}
assert sum(GEN.values()) == 400900, f"一般申購 {sum(GEN.values())} != 400,900"
assert sum(FREE.values()) == 504654, f"自由Pay {sum(FREE.values())} != 504,654"
snap["fund_general"] = dict(GEN)
snap["fund_freepay"] = dict(FREE)
snap["funds_breakdown"]["一般申購"] = dict(GEN)
snap["funds_breakdown"]["自由Pay"] = dict(FREE)
CODE = {"元大台灣卓越50ETF(0050)連結基金-台幣B配息":("A05144",21448),"台中銀台灣優息基金-B配息台幣":("A17030",30014),
 "安聯台灣科技基金":("A36004",3000),"安聯AI收益成長多重資產基金-B(月配)美元":("A36135",200),
 "國泰台灣高股息基金B":("A37170",5000),"台新美日台半導體基金A-日圓":("A47219",609172),
 "路博邁台灣5G股票基金T月配級別(台幣)":("A49015",30000),"聯博-全球多元收益基金AD月配美元":("B03629",3000),
 "聯博-美國成長基金AP總報酬月配美元":("B03870",3000),"摩根基金-JPM多重收益美元對沖A穩定月配":("B08291",3000),
 "貝萊德世界黃金A2美元":("B09006",3000),"貝萊德全球股票收益A6美元穩定配息":("B09261",3000),
 "貝萊德世界科技A10美元總報酬穩定配息":("B09460",3000),"貝萊德世界能源A10美元總報酬穩定配息":("B09461",5000),
 "貝萊德世界健康科學A10美元總報酬穩定配息":("B09462",5000),"貝萊德世界黃金A10美元總報酬穩定配息":("B09463",3000),
 "富達全球動能多元基金A股C月配美元":("B14445",3000),"安聯收益成長AMg7月收總收益美元":("B20186",3403),
 "M&G入息基金A(美元避險月配)F":("B31138",3000)}
FCODE = {"元大台灣卓越50ETF(0050)連結基金-台幣A不配息":"A05143","統一奔騰基金":"A09012",
         "路博邁台灣5G股票基金T累積級別(台幣)":"A49038"}
fh = [{"name": n, "code": CODE[n][0], "value": v, "cost": CODE[n][1], "currency": "TWD", "market_value": v}
      for n, v in GEN.items()]
fh += [{"name": n, "code": FCODE[n], "value": v, "cost": 0, "currency": "TWD", "market_value": v}
       for n, v in FREE.items()]
snap["fund_holdings"] = fh
snap["funds_note"] = ("2026-10-06 真值日：鉅亨 905,554（一般申購 400,900 + 自由Pay 504,654，10/05 淨值，平台卡片等值台幣）"
                      " ＋ 國泰直購 11,616,448（10/01、10/05）＝ 基金 12,522,002")
snap["fund_nav_dates"] = {"國泰直購（富達/聯博/B11）": "2026-10-05", "鉅亨（一般申購＋自由Pay）": "2026-10-05",
                          "安聯保單內基金（App）": "2026-10-05"}

# ================= 4. 安聯保單 B（App 截圖 2,642,621／−1.95%）=================
B = {"NTDEQ2640 元大台灣高股息優質龍頭基金-新台幣(B)配息": 379024,
     "USDEQ3490 安聯收益成長基金-AM穩定月收類股(美元)": 489071,
     "USDEQ5680 貝萊德世界健康科學基金 A10美元(總報酬穩定配息)": 237049,
     "USDEQ5700 M&G入息基金A(美元避險月配)F": 621785,
     "USDEQ6550 PIMCO收益增長基金-M級類別(月收息強化股份)": 767095,
     "USDEQ6730 貝萊德世界黃金基金 A10美元(總報酬穩定配息)": 148597}
assert sum(B.values()) == 2642621, f"安聯B {sum(B.values()):,} != 2,642,621"
snap["allianz_b_breakdown"] = dict(B)
snap["allianz_b_performance"] = -1.95
snap["allianz_b_breakdown_note"] = ("2026-10-06 保單B App 截圖（QL18488224 戊型，價值總額 2,642,621／−1.95%）："
  "六檔逐檔合計＝價值總額 ✓。唯一正報酬＝元大台灣高股息優質龍頭 +1.83%；拖累＝黃金A10 −10.34%、"
  "健康科學A10 −4.65%、安聯收益成長 −4.70%；PIMCO −0.03%／M&G −1.00% 撐住。")
for k in ("allianz_policy_b","allianz_b","allianz_b_funds","allianz_b_current_value","allianz_policy_b_value","policy_b_total"):
    if k in snap: snap[k] = 2642621

# ================= 5. 現金 / 信用卡（Moneybook 10/06 帳戶 CSV）=================
CD = {"文心綜活儲存款-薪轉":118582,"敦南Richart子帳戶":311182,"營業部DAWHO活期儲蓄存款":206464,
      "敦南Richart數位一般帳戶":75915,"數位活儲":44116,"臺幣綜存":40044,"市政分行活期儲蓄存款":1008,
      "活期儲蓄存款":700000,"民權活儲存款-證券":290742,"Digital Savings Account":739,"iLEO帳戶":716,
      "北台中活儲存款-優質薪轉儲蓄存款":100,"敦南數位二類異業帳戶":13,"數位存款帳戶２類":2}
assert sum(CD.values()) == 1789623, f"現金 {sum(CD.values()):,} != 1,789,623"
snap["cash_detail"] = CD
snap["cash_total"] = sum(CD.values())
snap["cash_source"] = {"date": "2026-10-06", "note": "Moneybook 帳戶 CSV 匯入（cash_detail）"}
snap["credit_card"] = {"玉山Unicard": 5127, "台北富邦": -23464, "永豐": -237,
                       "台新Richart": -6100, "國泰CUBE": -6478}
snap["credit_card_pending"] = 23464 + 237 + 6100 + 6478

# ================= 6. 派生重算 =================
from asset_sync import sync_snapshot_keys, rebuild_liabilities
snap = sync_snapshot_keys(snap) or snap
snap["fund_market"] = snap["fund_market_value"] = snap["funds_total"] = \
    snap["fund_total_market_value"] = snap["funds"] = 11616448 + sum(GEN.values()) + sum(FREE.values())
snap["allianz_combined"] = snap["allianz_ab"] = snap["allianz_ab_current_value"] = \
    (snap.get("allianz_policy_a_value") or 0) + 2642621
snap["insurance_total"] = snap["allianz_combined"] + (snap.get("firstjin_fl65_current_value") or 0)
snap = sync_snapshot_keys(snap) or snap
snap["total_assets"] = snap["insurance_total"] + snap["securities_total_market_value"] + \
    snap["fund_market_value"] + snap["cash_total"]
# 2026-10-08（PEND-20261006-02 修復）：真值日流程必須**顯式**落 DB liabilities（land_db=True）——
# 這支是後續真值日腳本的複製範本；沿用預設＝只更新 snapshot，DB 不會前進（10/08 斷點的成因）。
snap = rebuild_liabilities(snap, land_db=True) or snap
snap["last_updated"] = "2026-10-06"
P.write_text(json.dumps(snap, ensure_ascii=False, indent=1).replace("\n", "\r\n"),
             encoding="utf-8", newline="")

print("=== 2026-10-06 真值日 ===")
for lab, k in [("現金","cash_total"),("證券","securities_total_market_value"),("基金","fund_market_value"),
               ("保險","insurance_total"),("總資產","total_assets"),("國泰直購","funds_cathay"),
               ("安聯B","allianz_b_funds"),("安聯合計","allianz_combined"),
               ("總負債","total_liabilities"),("淨值","net_worth")]:
    o = old.get(k, 0) or 0; n = snap.get(k, 0) or 0
    print(f"  {lab:<8} {o:>13,} → {n:>13,}  ({n-o:+,})")
print(f"  鉅亨合計 {sum(old.get('fund_general',{}).values())+sum(old.get('fund_freepay',{}).values()):>13,}"
      f" → {sum(GEN.values())+sum(FREE.values()):>13,}  "
      f"({sum(GEN.values())+sum(FREE.values())-sum(old.get('fund_general',{}).values())-sum(old.get('fund_freepay',{}).values()):+,})")
