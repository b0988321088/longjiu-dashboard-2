#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-09-29 真值日補完：保單 A/B 逐檔、第一金、國泰基金擔保池、鉅亨逐檔、總資產重算。"""
import json
from pathlib import Path
import sys

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
sys.path.insert(0, str(BASE))
P = BASE / "snapshot.json"
snap = json.loads(P.read_text(encoding="utf-8"))

A = {"USDEQ3490 安聯收益成長基金-AM穩定月收類股(美元)": 619256,
     "USDEQ5440 摩根投資基金 - 多重收益基金 - JPM多重收益(美元對沖) - A股(穩定月配)": 1715772,
     "USDEQ5680 貝萊德世界健康科學基金 A10美元(總報酬穩定配息)": 293508,
     "USDEQ5700 M&G入息基金A(美元避險月配)F": 752279,
     "USDEQ6550 PIMCO收益增長基金-M級類別(月收息強化股份)": 1364224,
     "USDEQ6730 貝萊德世界黃金基金 A10美元(總報酬穩定配息)": 189370}
B = {"USDEQ3490 安聯收益成長基金-AM穩定月收類股(美元)": 486704,
     "USDEQ5680 貝萊德世界健康科學基金 A10美元(總報酬穩定配息)": 244414,
     "USDEQ5700 M&G入息基金A(美元避險月配)F": 1548321,
     "USDEQ6550 PIMCO收益增長基金-M級類別(月收息強化股份)": 196962,
     "USDEQ6730 貝萊德世界黃金基金 A10美元(總報酬穩定配息)": 157531}
assert sum(A.values()) == 4934409, sum(A.values())
assert sum(B.values()) == 2633932, sum(B.values())

# ① 保單 A/B（安聯；2026-09-29 13:30 永旭/安聯 App 截圖，保單號 QL18610694 / QL1848824）
snap["allianz_policy_a"] = 4934409
snap["allianz_policy_b"] = 2633932
snap["allianz_a_value"] = 4934409
snap["allianz_b_value"] = 2633932
snap["allianz_a_performance"] = -2.95
snap["allianz_b_performance"] = -2.45
snap["allianz_combined"] = 7568341
snap["allianz_a_breakdown_note"] = (
    "2026-09-29 13:30 保單 QL18610694 截圖逐檔：安聯收益成長 619,256／摩根JPM多重收益 1,715,772／"
    "貝萊德世界健康A10 293,508／M&G入息 752,279／PIMCO收益增長 1,364,224／貝萊德世界黃金A10 189,370；"
    "合計 4,934,409（-2.95%）｜本月累積配息/撥回 7 筆 52,169（A+B 合計）")
snap["allianz_b_breakdown_note"] = (
    "2026-09-29 13:30 保單 QL1848824 截圖逐檔：安聯收益成長 486,704／貝萊德世界健康A10 244,414／"
    "M&G入息 1,548,321／PIMCO收益增長 196,962／貝萊德世界黃金A10 157,531；合計 2,633,932（-2.45%）"
    "（B 無摩根 JPM 部位）")

# ② 第一金（2026-09-29 官網保單資訊頁）
snap["firstjin_fl65_current_value"] = 1885484
snap["firstjin_cum_dividend"] = 133805
snap["firstjin_note_20260929"] = (
    "2026-09-29 第一金人壽保單資訊頁：保單帳戶價值 1,885,484｜累計總繳保費 2,000,000｜累計提領 0｜"
    "累計已給付配息/撥回 133,805｜投資標的 100% ID01-M&G入息基金A(美元避險月配)F｜"
    "總繳保險費報酬率（含息）0.96%／（不含息）-5.73%")

# ③ 保險總值 / 明細
snap["insurance_total"] = 7568341 + 1885484            # 9,453,825（synonym 群組會同步）
snap["insurance_breakdown"] = {
    "policy_a_total": 4934409, "policy_b_total": 2633932, "allianz_ab_total": 7568341,
    "policy_a_funds": A, "policy_b_funds": B, "firstjin_total": 1885484,
    "note": ("2026-09-29 13:30 安聯「我的投資」截圖（QL18610694／QL1848824）＋第一金官網保單頁；"
             "insurance_total = 安聯 7,568,341 + 第一金 1,885,484 = 9,453,825")}

# ④ 國泰基金：擔保池（9/28 報價）＋逐檔（update_data 已寫 funds_cathay_breakdown/國泰直購）
POOL = {"富達全球動能多元B股C月配息美元": 5863138,
        "聯博全球多元收益AD美元月配": 968889,
        "貝萊德智慧數據收益成長B11-美元-強化穩定月配息": 4947299}
assert sum(POOL.values()) == 11779326, sum(POOL.values())
cp = snap.setdefault("cathay_pledge_0911", {})
cp["擔保池"] = {**POOL, "合計": 11779326,
                "資料日": "2026-09-28（國泰基金平台庫存損益截圖，9/29 取得）"}
cp["LTV"] = "50.09%（借款 5,900,000 / 池市值 11,779,326，9/28 報價）"
cp["基金現值_20260929"] = {
    "總投資本金": 12000000, "參考現值": 11779326, "投資損益": -220674,
    "含息總報酬率": -1.37, "不含息總報酬率": -1.84, "現持有基金配息": 55881,
    "逐檔": {"富達全球動能多元B股-C月配息美元": {"單位數": 15744.5, "淨值USD": 11.74, "現值TWD": 5863138, "損益": -136862, "配息": 49120},
             "貝萊德智慧數據收益成長B11-美元-強化穩定月配息": {"單位數": 15503.76, "淨值USD": 10.06, "現值TWD": 4947299, "損益": -52701, "配息": 0},
             "聯博全球多元收益AD美元月配": {"單位數": 3386.37, "淨值USD": 9.02, "現值TWD": 968889, "損益": -31111, "配息": 6761}}}

# ⑤ 鉅亨：逐檔（一般申購 22 檔 CSV 直讀 + 自由PAY 3 檔卡片）；幣別：台幣列直讀、
#    美元列×31.8375、日圓列以「帳戶總額 874,818 − 自由Pay 484,716 − 台幣列 252,085 − 美元列 6,555」回推
GEN = {"元大台灣卓越50ETF(0050)連結基金-台幣B配息": 50961, "台中銀台灣優息基金-B配息台幣": 50796,
       "安聯台灣科技基金": 3327, "安聯AI收益成長多重資產基金-B(月配)美元": 6555,
       "國泰台灣高股息基金B": 8638, "台新美日台半導體基金A-日圓": 131462,
       "路博邁台灣5G股票基金T月配級別(台幣)": 96794, "聯博-全球多元收益基金AD月配美元": 2906,
       "聯博-美國成長基金AP總酬月配美元": 3033, "摩根基金-JPM多重收益美元對沖A穩定月配": 2933,
       "貝萊德世界黃金A2美元": 3200, "貝萊德全球股票收益A6美元穩定配息": 3145,
       "貝萊德世界科技A10美元總報酬穩定配息": 4319, "貝萊德世界能源A10美元總報酬穩定配息": 5354,
       "貝萊德世界健康科學A10美元總報酬穩定配息": 4819, "貝萊德世界黃金A10美元總報酬穩定配息": 2609,
       "富達全球動能多元基金A股C月配美元": 2948, "安聯收益成長AMg7月收總收益美元": 3376,
       "M&G入息基金A(美元避險月配)F": 2927}
PAY = {"元大台灣卓越50ETF(0050)連結基金-台幣A不配息": 118047,
       "統一奔騰基金": 102109, "路博邁台灣5G股票基金T累積級別(台幣)": 264560}
print("一般申購逐檔合計 =", f"{sum(GEN.values()):,}", "（應 390,102）")
print("自由PAY 逐檔合計 =", f"{sum(PAY.values()):,}", "（應 484,716，卡片值）")
assert sum(PAY.values()) == 484716
assert sum(GEN.values()) == 390102
fb = snap.setdefault("funds_breakdown", {})
fb["一般申購"] = {**GEN, "note": ("2026-09-29 鉅亨『一般申購』CSV 直讀（19 台幣列＋美元列＋日圓列；"
                                  "日圓列 657,638 JPY 以帳戶總額回推換算 131,462 TWD）。"
                                  "合計 390,102 = 鉅亨帳戶總額 874,818 − 自由Pay 484,716")}
fb["自由Pay"] = {**PAY, "note": ("2026-09-29 鉅亨『自由PAY』頁卡片：成本 310,000／市值 484,716／損益 +174,716／"
                                 "已PAY 5,096／含PAY 58%")}
fb["note"] = ("2026-09-29：鉅亨 874,818（一般申購 390,102 ＋ 自由Pay 484,716）"
              "＋ 國泰直購 11,779,326（9/28 報價）＝ 基金 12,654,144")

# ⑥ 總資產重算（禁差額法：ins+sec+funds+cash）＋負債/淨值
snap = __import__("asset_sync").sync_snapshot_keys(snap)
from asset_sync import rebuild_liabilities       # noqa: E402
snap["total_assets"] = (snap["insurance_total"] + snap["securities_total_market_value"]
                        + snap["fund_market_value"] + snap["cash_total"])
# 2026-10-08（PEND-20261006-02 修復）：真值日流程必須**顯式**落 DB liabilities（land_db=True）。
# 這裡若沿用預設（land_db=False）＝只更新 snapshot，DB liabilities 表不會前進，收工稽核隔日必兩條 ❌。
snap = rebuild_liabilities(snap, land_db=True)
snap["真值日_20260929"] = ("使用者 9/29 上傳：Moneybook ZIP（08/30–09/29）＋安聯保單 A/B 截圖＋"
                          "第一金保單頁＋國泰基金庫存＋鉅亨一般申購 CSV／自由PAY 截圖；"
                          "台股證券沿用 3,006,890（本批未提供）")
P.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")

print("--- 最終 ---")
for k in ("cash_total", "securities_total_market_value", "insurance_total", "fund_market_value",
          "total_assets", "total_liabilities", "net_worth"):
    print(f"  {k}: {snap.get(k):,}")
bu = snap["liabilities_build_up"]
print("  負債拆解:", {k: f"{v:,}" if isinstance(v, int) else v for k, v in bu.items() if k != "note"})
