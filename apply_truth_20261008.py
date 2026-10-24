#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# ⚠️ 一次性留痕，不作模板（2026-10-08 使用者裁決 A；#48 liabilities 自然回歸）
#   · 本檔為 2026-10-08 真值日之一次性套用腳本，**刻意不納入版控**。
#   · 本檔未帶 `land_db=True`（第 257 行 `rebuild_liabilities(snap)`）→ 當日 DB
#     liabilities **未落列**，需人工補救；因此**不得**被複製為下一次真值日的模板。
#   · 真值日落 DB liabilities 一律走單一入口：
#         python asset_sync.py --rebuild-liabilities
#     或套用腳本內顯式 `rebuild_liabilities(snap, land_db=True)`（見 monthly-truth-day 步驟 ③a）。
#   · 守門：check_thresholds.py 的「負債落列 freshness」斷言會在值未落列時 fail-closed。
# ============================================================================
"""2026-10-08 真值套用：安聯保單 A/B 逐檔（App 截圖）+ 第一金保單現值
來源：永旭保險經紀人 App「我的投資」（資料查詢時間 115/10/08 08:55:12）
      第一金人壽「我的帳戶表現」頁（2026-10-08）
規則：截圖 = authoritative；逐檔合計必須等於價值總額（assert 硬擋）
"""
import json, shutil, sys
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
sys.path.insert(0, str(BASE))
P = BASE / "snapshot.json"
shutil.copy(P, BASE / "snapshot.backup_20261008.json")  # 日期備份（不覆蓋 rolling snapshot.backup.json）
snap = json.loads(P.read_text(encoding="utf-8"))
old = dict(snap)

# ============ 1. 安聯保單 A（QL18610694）價值總額 4,956,894／−1.74% ============
A = {
    "USDEQ3490 安聯收益成長基金-AM穩定月收類股(美元)": 616560,
    "USDEQ5440 摩根投資基金 - 多重收益基金 - JPM多重收益(美元對沖) - A股(穩定月配)": 686447,
    "USDEQ5680 貝萊德世界健康科學基金 A10美元(總報酬穩定配息)": 286862,
    "USDEQ6550 PIMCO收益增長基金-M級類別(月收息強化股份)": 3187889,
    "USDEQ6730 貝萊德世界黃金基金 A10美元(總報酬穩定配息)": 179136,
}
A_TOTAL = 4956894
assert sum(A.values()) == A_TOTAL, f"安聯A 逐檔合計 {sum(A.values()):,} != {A_TOTAL:,}"

# ============ 2. 安聯保單 B（QL18488224）價值總額 2,648,097／−1.75% ============
B = {
    "NTDEQ2640 元大台灣高股息優質龍頭基金-新台幣(B)配息": 376671,
    "USDEQ3490 安聯收益成長基金-AM穩定月收類股(美元)": 491298,
    "USDEQ5680 貝萊德世界健康科學基金 A10美元(總報酬穩定配息)": 238879,
    "USDEQ5700 M&G入息基金A(美元避險月配)F": 624122,
    "USDEQ6550 PIMCO收益增長基金-M級類別(月收息強化股份)": 768110,
    "USDEQ6730 貝萊德世界黃金基金 A10美元(總報酬穩定配息)": 149017,
}
B_TOTAL = 2648097
assert sum(B.values()) == B_TOTAL, f"安聯B 逐檔合計 {sum(B.values()):,} != {B_TOTAL:,}"

# ============ 3. 第一金人壽（FJ33 摩根JPM 100%）1,868,043 ============
FJ_TOTAL = 1868043
FJ_CUM_DIV = 149721

snap["allianz_a_breakdown"] = dict(A)
snap["allianz_b_breakdown"] = dict(B)
snap["allianz_a_performance"] = -1.74
snap["allianz_b_performance"] = -1.75
snap["allianz_a_breakdown_note"] = (
    "2026-10-08 保單A App 截圖（QL18610694 戊型，價值總額 4,956,894／−1.74%）：五檔逐檔合計＝價值總額 ✓。"
    "報酬：PIMCO +0.09%（唯一正報酬）；拖累＝黃金A10 −10.09%、安聯收益成長 −4.27%、健康科學A10 −3.92%、摩根JPM −0.63%。")
snap["allianz_b_breakdown_note"] = (
    "2026-10-08 保單B App 截圖（QL18488224 戊型，價值總額 2,648,097／−1.75%）：六檔逐檔合計＝價值總額 ✓。"
    "唯一正報酬＝元大台灣高股息優質龍頭 +1.20%；拖累＝黃金A10 −10.09%、健康科學A10 −3.92%、安聯收益成長 −4.27%；"
    "PIMCO +0.09%／M&G −0.63% 撐住。")
snap["allianz_note_20261008"] = (
    "2026-10-08 安聯保單 App『我的投資』（資料查詢時間 115/10/08 08:55:12）：帳戶總價值 7,604,991 "
    "= A 4,956,894（−1.74%）+ B 2,648,097（−1.75%）；本月累積配息/撥回 2 筆共 9,446；"
    "投資風險屬性 積極型（效期至 116/01/21）。逐檔明細見 allianz_a_breakdown／allianz_b_breakdown。")

for k in ("allianz_a", "allianz_a_current_value", "allianz_a_funds", "allianz_a_value",
          "allianz_policy_a", "allianz_policy_a_value", "policy_a_total"):
    snap[k] = A_TOTAL
for k in ("allianz_b", "allianz_b_current_value", "allianz_b_funds", "allianz_b_value",
          "allianz_policy_b", "allianz_policy_b_value", "policy_b_total"):
    snap[k] = B_TOTAL
for k in ("allianz_ab", "allianz_ab_current_value", "allianz_combined", "allianz_current_value", "allianz_total"):
    snap[k] = A_TOTAL + B_TOTAL

# 第一金
for k in ("firstjin", "firstjin_current_value", "firstjin_fl65_current_value"):
    snap[k] = FJ_TOTAL
snap["firstjin_cum_dividend"] = FJ_CUM_DIV
snap["firstjin_fund_name"] = ("FJ33-摩根投資基金-多重收益基金-JPM多重收益(美元對沖)-A股(每月派息) 100%"
                              "（2026-10-08 App 截圖；同日申請轉換至 M&G入息基金A(美元避險月配)F，生效日待 App 確認）")
snap["firstjin_short_label"] = "摩根JPM多重收益（10/08 轉 M&G 申請中）"
snap["firstjin_note_20261008"] = (
    "2026-10-08 第一金人壽『我的帳戶表現』：保單帳戶價值 1,868,043｜累計總繳保費 2,000,000｜累計提領 0｜"
    "累計已給付配息/撥回 149,721｜投資總成本報酬率 −6.53%｜總繳保險費報酬率 含息 +0.89%／不含息 −6.6%｜"
    "資產配置 100% FJ33 摩根JPM多重收益（每月派息）。使用者同日確認：目前持倉為 FJ33 摩根JPM，"
    "並於 2026-10-08 轉換至 M&G入息A（IDXX），生效日以前例 T+4 推估、未確認前不視為已完成。"
    "⚠️ 與本檔 9/16 舊記錄（FJXX→M&G 生效完成、9/18 與 10/01 兩次截圖皆顯示 100% IDXX）不一致 — "
    "待使用者確認中間是否曾轉回摩根系或該筆轉換紀錄有誤。")

# ============ 4. insurance_breakdown / insurance_total 重算 ============
ib = dict(snap.get("insurance_breakdown") or {})
ib["policy_a_total"] = A_TOTAL
ib["policy_b_total"] = B_TOTAL
ib["allianz_ab_total"] = A_TOTAL + B_TOTAL
ib["policy_a_funds"] = dict(A)
ib["policy_b_funds"] = dict(B)
ib["firstjin_total"] = FJ_TOTAL
ib["note"] = "安聯 A+B 逐檔＝2026-10-08 08:55 App 截圖；第一金＝2026-10-08『我的帳戶表現』截圖"
snap["insurance_breakdown"] = ib

INSURANCE = A_TOTAL + B_TOTAL + FJ_TOTAL
for k in ("insurance", "insurance_current_value", "insurance_total"):
    snap[k] = INSURANCE
snap["insurance_total_note"] = "含配息（安聯A+B 2026-10-08 截圖 + 第一金 2026-10-08 截圖）"
snap["insurance_label_b"] = "第一金 FJXX 摩根JPM多重收益（2026-10-08 申請轉 M&G入息A，生效待確認）"

# ============ 4. 國泰直購基金（App 基金頁截圖 2026-10-08 09:18，淨值日 10/06）============
CAT = {
    "富達全球動能多元B股C月配息美元": 5903091,
    "貝萊德智慧數據收益成長B11-美元-強化穩定月配息": 4922710,
    "聯博全球多元收益AD美元月配": 968889,
}
CAT_TOTAL = 11794690
assert sum(CAT.values()) == CAT_TOTAL, f"國泰直購 逐檔合計 {sum(CAT.values()):,} != {CAT_TOTAL:,}"
snap["funds_cathay"] = CAT_TOTAL
snap["funds_cathay_breakdown"] = dict(CAT)
snap["fund_breakdown_cathay"] = dict(CAT)
snap.setdefault("funds_breakdown", {})["國泰直購"] = dict(CAT)
snap["funds_cathay_note_1008"] = (
    "2026-10-08 國泰基金頁截圖（09:18）：參考現值 11,794,690（−1.71%）、本金 12,000,000、不含息參考報酬 −205,310。"
    "富達 5,903,091（含息 −0.80%／不含息 −1.62%）｜B11 4,922,710（−1.55%／−1.55%）｜"
    "聯博 968,889（−1.76%／−3.11%）｜淨值日皆 2026/10/06。逐檔合計＝頁首現值 ✓")
snap.setdefault("fund_nav_dates", {})["國泰直購（富達/聯博/B11）"] = "2026-10-06"

# ============ 4b. 鉅亨（Fund口袋）：自由Pay 截圖 + 一般申購 CSV（2026-10-08 09:18，淨值日 10/06-10/07）============
# 台幣列直接為 TWD；美元列 A36135＝210.28 USD × 31.7825（CSV 自帶匯率）；日圓列 A47219＝695,806 JPY × 0.199301
# （0.199301 由平台「台幣市值 898,416」與「幣別明細 台幣 753,058」反解，交叉驗證成立：台幣桶 255,363＋497,695＝753,058 ✓）
GEN = {
    "元大台灣卓越50ETF(0050)連結基金-台幣B配息": 52697,
    "台中銀台灣優息基金-B配息台幣": 51122,
    "安聯台灣科技基金": 3532,
    "安聯AI收益成長多重資產基金-B(月配)美元": 6683,
    "國泰台灣高股息基金B": 8945,
    "台新美日台半導體基金A-日圓": 138675,
    "路博邁台灣5G股票基金T月配級別(台幣)": 97770,
    "聯博-全球多元收益基金AD月配美元": 2894,
    "聯博-美國成長基金AP總報酬月配美元": 3069,
    "摩根基金-JPM多重收益美元對沖A穩定月配": 2932,
    "貝萊德世界黃金A2美元": 3064,
    "貝萊德全球股票收益A6美元穩定配息": 3130,
    "貝萊德世界科技A10美元總報酬穩定配息": 4427,
    "貝萊德世界能源A10美元總報酬穩定配息": 5345,
    "貝萊德世界健康科學A10美元總報酬穩定配息": 4705,
    "貝萊德世界黃金A10美元總報酬穩定配息": 2478,
    "富達全球動能多元基金A股C月配美元": 2940,
    "安聯收益成長AMg7月收總收益美元": 3377,
    "M&G入息基金A(美元避險月配)F": 2936,
}
FREE = {
    "元大台灣卓越50ETF(0050)連結基金-台幣A不配息": 122078,
    "統一奔騰基金": 106305,
    "路博邁台灣5G股票基金T累積級別(台幣)": 269312,
}
GEN_TOTAL = 400721
FREE_TOTAL = 497695
HENG = 898416
assert sum(GEN.values()) == GEN_TOTAL, f"一般申購 {sum(GEN.values()):,} != {GEN_TOTAL:,}"
assert sum(FREE.values()) == FREE_TOTAL, f"自由Pay {sum(FREE.values()):,} != {FREE_TOTAL:,}"
assert GEN_TOTAL + FREE_TOTAL == HENG, f"鉅亨合計 {GEN_TOTAL + FREE_TOTAL:,} != {HENG:,}"
snap["fund_general"] = dict(GEN)
snap["fund_freepay"] = dict(FREE)
snap.setdefault("funds_breakdown", {})["一般申購"] = dict(GEN)
snap.setdefault("funds_breakdown", {})["自由Pay"] = dict(FREE)
snap["funds_note"] = (
    "2026-10-08 鉅亨（Fund口袋）：一般申購 400,721（CSV 19 檔，淨值日 10/06-10/07）＋ 自由Pay 497,695（截圖 3 檔）"
    "＝ 帳戶台幣市值 898,416（平台頁首）✓。換算基礎：美元列 210.28 USD×31.7825（CSV 自帶匯率）；"
    "日圓列 695,806 JPY×0.199301（由平台台幣桶 753,058 交叉驗證反解）。"
    "自由Pay：0050連結A不配息 122,078／統一奔騰 106,305／路博邁5G T累積 269,312。")
snap["heng_note_20261008"] = (
    "2026-10-08 09:18 鉅亨帳戶總覽：台幣市值 898,416（當日 −237／−0.03%）、約當台幣成本 567,603、"
    "損益 +330,813（不含息 +58.28%）、已配息 20,149（含息 +61.83%）；幣別明細 台幣 753,058／"
    "美元 210.28／日圓 695,806。vs 10/05：905,554 → 898,416（−7,138／−0.79%）。")

# ============ 4c. 現金＋信用卡（Moneybook 帳戶 CSV 2026-10-08）============
CD = {
    "文心綜活儲存款-薪轉": 118582,
    "敦南Richart子帳戶": 311182,
    "營業部DAWHO活期儲蓄存款": 206464,
    "敦南Richart數位一般帳戶": 76082,
    "數位活儲": 44116,
    "臺幣綜存": 40044,
    "市政分行活期儲蓄存款": 1008,
    "活期儲蓄存款": 706765,
    "民權活儲存款-證券": 672,
    "Digital Savings Account": 739,
    "iLEO帳戶": 716,
    "北台中活儲存款-優質薪轉儲蓄存款": 100,
    "敦南數位二類異業帳戶": 13,
    "數位存款帳戶２類": 2,
}
CASH_TOTAL = 1506485
assert sum(CD.values()) == CASH_TOTAL, f"現金明細 {sum(CD.values()):,} != {CASH_TOTAL:,}"
snap["cash_detail"] = CD
snap["cash_total"] = CASH_TOTAL
snap["cash_source"] = {"date": "2026-10-08", "note": "Moneybook 帳戶 CSV 匯入（cash_detail）"}
snap["credit_card"] = {"玉山Unicard": 5343, "台北富邦": -23464, "永豐": -237,
                       "台新Richart": -6210, "國泰CUBE": -6558}
snap["credit_card_pending"] = 23464 + 237 + 6210 + 6558
snap["cash_detail_extra"] = {"國泰活期B(20,776)": 0}
snap["cash_note_20261008"] = (
    "2026-10-08 Moneybook 帳戶 CSV（09:18）：台幣現金 1,506,485。"
    "變動主因＝民權活儲存款-證券 290,742→672（10/07 新股抽籤預扣 290,070，未中籤約 10/14 退回；"
    "中籤則轉為持股市值）；國泰活期 700,000→706,765（+6,765）；敦南Richart數位一般帳戶 75,915→76,082。"
    "排除國泰活期重複列 20,776（沿用既有排除標記）。信用卡應繳 36,469（富邦 23,464／國泰 6,558／台新 6,210／永豐 237）。")

# ============ 4d. 證券（券商看盤頁 2026-10-08 09:19 即時報價）============
PX = {"0050": 115.10, "006208": 263.25, "009816": 16.90, "00646": 78.05, "00713": 63.20,
      "00878": 35.01, "0056": 58.20, "00981A": 31.89, "00984A": 16.18, "00919": 31.72,
      "00918": 33.96, "009824": 10.85, "009823": 10.62, "00888": 36.65, "00983D": 9.56}
_hold = []
for h in snap["securities"]["holdings"]:
    t = h["ticker"]; sh = h.get("shares", 0); cost = h.get("cost", 0)
    p = PX.get(t, h.get("price"))
    mv = round(p * sh, 2)
    pnl = round(mv - cost, 2)
    _hold.append({"ticker": t, "name": h["name"], "shares": sh, "price": p, "cost": cost,
                  "value": mv, "market_value": mv, "pnl": pnl,
                  "pnl_pct": round(pnl / cost * 100, 2) if cost else 0,
                  "currency": h.get("currency", "TWD")})
S_TOTAL = round(sum(h["market_value"] for h in _hold), 2)
S_UNREAL = round(sum(h["pnl"] for h in _hold), 2)
assert S_TOTAL == 3045250, f"證券逐檔合計 {S_TOTAL:,} != 3,045,250（頁首）"
assert abs(S_UNREAL - 533700) <= 300, f"未實現 {S_UNREAL:,} 與畫面 533,700 差 >300"
S_UNREAL = 533700  # 以 App 真值為準
for k in ("securities_total_market_value", "securities_total", "securities_market",
          "securities_current_value", "securities_market_value", "total_stock_value"):
    snap[k] = S_TOTAL
snap["securities_unrealized_pnl"] = S_UNREAL
snap["securities_realized_pnl"] = 23460
snap["securities_realized_pnl_pct"] = 27.34
snap["securities"] = {"total_market_value": S_TOTAL, "unrealized_pnl": S_UNREAL,
                      "unrealized_pnl_pct": round(S_UNREAL / (S_TOTAL - S_UNREAL) * 100, 2),
                      "realized_pnl": 23460, "realized_pnl_pct": 27.34,
                      "holdings": _hold, "price_date": "2026-10-08",
                      "note": "2026-10-08 09:19 盤中即時報價（15 檔）；未實現 +533,700（+21.25%）｜已實現 +23,460（+27.34%）"}
snap["holdings"] = _hold
snap["securities_breakdown"] = {h["ticker"]: h["market_value"] for h in _hold}
snap["securities_note_20261008"] = (
    "2026-10-08 09:19 盤中即時報價：持有股票市值 3,045,250（15 檔，逐檔合計＝頁首 ✓）"
    "｜未實現 +533,700（+21.25%）｜已實現 +23,460（+27.34%）。vs 10/06 收盤 3,064,250（−19,000）。")

snap["cash_gap_temp_20261008"] = {
    "金額": 93515,
    "性質": "暫時性缺口（非實質現金流失）",
    "起因": "2026-10-07 新股抽籤預扣 290,070（台新民權活儲存款-證券）",
    "預計解除": "2026-10-14",
    "解除說明": "未中籤 → 預扣款退回現金；中籤 → 轉為持股市值（資產未消失，僅科目移動）",
    "期間效力": "2026-10-08 ~ 2026-10-15；可動用 606,485 < 底線 700,000，期間不做大額支出決策",
}

# ============ 5. 派生重算 ============
from asset_sync import sync_snapshot_keys, rebuild_liabilities
snap = sync_snapshot_keys(snap) or snap
_FUNDS = CAT_TOTAL + sum((snap.get("fund_general") or {}).values()) + sum((snap.get("fund_freepay") or {}).values())
for _k in ("fund_market_value", "funds_total", "fund_market", "funds", "fund_total_market_value"):
    snap[_k] = _FUNDS
snap["insurance"] = INSURANCE
snap["insurance_current_value"] = INSURANCE
snap["insurance_total"] = INSURANCE
snap["total_assets"] = INSURANCE + (snap.get("securities_total_market_value") or 0) + \
    _FUNDS + (snap.get("cash_total") or 0)
snap = rebuild_liabilities(snap) or snap
snap["last_updated"] = "2026-10-08"
P.write_text(json.dumps(snap, ensure_ascii=False, indent=1).replace("\n", "\r\n"),
             encoding="utf-8", newline="")

print("=== 2026-10-08 真值套用（安聯A/B + 第一金）===")
for lab, k in [("安聯A", "allianz_policy_a_value"), ("安聯B", "allianz_policy_b_value"),
               ("安聯合計", "allianz_combined"), ("第一金", "firstjin_current_value"),
               ("保險合計", "insurance_total"), ("國泰直購", "funds_cathay"),
               ("基金合計", "fund_market_value"), ("現金", "cash_total"), ("總資產", "total_assets"),
               ("總負債", "total_liabilities"), ("淨值", "net_worth")]:
    o = old.get(k, 0) or 0
    n = snap.get(k, 0) or 0
    print(f"  {lab:<6} {o:>13,} → {n:>13,}  ({n - o:+,})")
