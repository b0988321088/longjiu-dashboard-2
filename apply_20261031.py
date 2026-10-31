# -*- coding: utf-8 -*-
"""套用 2026-10-31 截圖＋Moneybook（月末真值）
來源：
  A) 證券 App 持股明細 10/30 收盤（14 檔，總市值 2,742,580）
  B) 鉅亨 10/30：一般申購 359,252（20 檔）＋自由PAY 427,024（3 檔）＝786,276
  C) 國泰直購 10/29：11,960,088（3 檔）
  D) 安聯 App 10/31 19:05：A 4,972,907（3 檔）／B 2,568,361（5 檔，等比）＝7,541,268
  E) 第一金 10/31：1,862,327（100% ID05），本月配息 9,901
  F) Moneybook 10/31：台幣活存 2,020,447（排除國泰重複列 20,776）、信用卡 53,279
只改本檔列出的 key，其餘不動；穿透/負債/DB 由 update_data.py 重算。
"""
import json, shutil, datetime, os

BASE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(BASE, 'snapshot.json')
s = json.load(open(SNAP, encoding='utf-8'))
shutil.copy(SNAP, os.path.join(BASE, 'snapshot.backup_pre_20261031.json'))

# ---------- A 證券 10/30 收盤 ----------
SEC = {
 '0050':  (104.95, 209900, 84.9,   169800),
 '006208':(240.75, 481500, 196.9,  393800),
 '009816':(15.67,  250720, 12.49,  199840),
 '00646': (78.60,   78600, 71.6,    71600),
 '00713': (65.70,  131400, 54.8,   109600),
 '00878': (34.81,  522150, 27.17,  407550),
 '0056':  (55.85,   55850, 37.15,   37150),
 '00981A':(26.66,  213280, 26.32,  210560),
 '00984A':(14.80,  148000, 14.56,  145600),
 '00919': (32.59,  195540, 29.55,  177300),
 '00918': (34.41,   34410, 28.55,   28550),
 '00888': (31.07,  155350, 31.73,  158650),
 '00983D':(9.91,   198200, 10.10,  202000),
 '00927': (33.84,   67680, 37.90,   75800),
}
sec = s['securities']
tot = 0
for h in sec['holdings']:
    t = h['ticker']
    if t not in SEC:
        raise SystemExit(f'未知持股 {t}：腳本未定義，停止')
    price, mv, avg, cost = SEC[t]
    h['price'] = price
    h['market_value'] = mv
    h['value'] = mv
    h['cost'] = cost
    h['cost_avg'] = avg
    h['pnl'] = mv - cost
    h['pnl_pct'] = round((mv - cost) / cost * 100, 2) if cost else 0
    tot += mv
cost_tot = sum(v[3] for v in SEC.values())
sec['total_market_value'] = tot
sec['as_of'] = '2026-10-30'
sec['price_date'] = '2026-10-30'
sec['source'] = '證券 App 持股明細截圖 2026-10-30（收盤）'
sec['unrealized_pnl'] = tot - cost_tot
sec['unrealized_pnl_pct'] = round((tot - cost_tot) / cost_tot * 100, 2)
sec['note'] = (f'2026-10-31 19:11 截圖：14 檔全數逐檔合計＝頁首 {tot:,}（當日 -50,390 / -1.80%）'
               f'｜未實現 +{tot-cost_tot:,}（+{sec["unrealized_pnl_pct"]}%）｜已實現 +23,460（+27.34%）')
s['securities_total_market_value'] = tot
s['securities_total'] = tot
print(f'A 證券 {tot:,}｜成本 {cost_tot:,}｜未實現 {tot-cost_tot:,}')

# ---------- B/C 基金 ----------
HENG_GEN = {
 '台新美日台半導體基金A-日圓': 120340,   # 585,496 日圓原幣 × 0.2055 反推（頁首差額校準）
 '台中銀台灣優息基金-B配息台幣': 46666,
 '路博邁台灣5G股票基金T月配級別(台幣)': 83414,
 '元大台灣卓越50ETF(0050)連結基金-台幣B配息': 47488,
 '國泰台灣高股息基金B': 7573,
 '貝萊德世界能源A10美元總報酬穩定配息': 5927,
 '貝萊德世界健康科學A10美元總報酬穩定配息': 5234,
 '安聯收益成長AMg7月收總收益美元': 3374,
 '安聯台灣科技基金': 2953,
 '聯博-全球多元收益基金AD月配美元': 2920,
 '聯博-美國成長基金AP總報酬月配美元': 2948,
 '摩根基金-JPM多重收益美元對沖A穩定月配': 2964,
 '貝萊德世界黃金A2美元': 2870,
 '貝萊德全球股票收益A6美元穩定配息': 3133,
 '貝萊德世界科技A10美元總報酬穩定配息': 3880,
 '貝萊德世界黃金A10美元總報酬穩定配息': 2300,
 '貝萊德全球智慧數據股票入息A11美元強化穩定配息': 3047,
 '富達全球動能多元基金A股C月配美元': 2925,
 'M&G入息基金A(美元避險月配)F': 2962,
 '安聯AI收益成長多重資產基金-B(月配)美元': 6334,   # 194.89 USD × 32.5
}
HENG_FREE = {
 '路博邁台灣5G股票基金T累積級別(台幣)': 229742,
 '元大台灣卓越50ETF(0050)連結基金-台幣A不配息': 110002,
 '統一奔騰基金': 87280,
}
CATHAY = {
 '富達全球動能多元B股C月配息美元': 5894411,
 '貝萊德智慧數據收益成長B11-美元-強化穩定月配息': 5079377,
 '聯博全球多元收益AD美元月配': 986300,
}
g_sum, f_sum, c_sum = sum(HENG_GEN.values()), sum(HENG_FREE.values()), sum(CATHAY.values())
assert g_sum == 359252, f'一般申購合計 {g_sum} ≠ 359,252'
assert f_sum == 427024, f'自由PAY合計 {f_sum} ≠ 427,024'
assert c_sum == 11960088, f'國泰合計 {c_sum} ≠ 11,960,088'
fb = s['funds_breakdown']
fb['一般申購'] = HENG_GEN
fb['自由Pay'] = HENG_FREE
fb['國泰直購'] = CATHAY
fb['一般申購_平台小計'] = g_sum
fb['平台小計'] = g_sum + f_sum
fb['note'] = (f'2026-10-31：鉅亨帳戶總覽截圖（淨值日 10/30）台幣市值 {g_sum+f_sum:,}'
              f'（一般申購 {g_sum:,}／自由PAY {f_sum:,}）｜國泰直購 {c_sum:,}（淨值日 10/29）。'
              f'一般申購 A47219 為日圓級別（585,496 円），台幣值由頁首差額反推 120,340。')
funds_total = g_sum + f_sum + c_sum
s['funds_total'] = funds_total
s['fund_market'] = funds_total
s['fund_market_value'] = funds_total
s['funds_cathay'] = c_sum
s['fund_freepay_as_of'] = f'2026-10-30（平台自由PAY專區：市值 {f_sum:,}／成本 310,000／已Pay 5,096／含Pay +39.39%）'
s['hend_heng_note_20261031'] = f'2026-10-30 鉅亨帳戶總覽：台幣市值 {g_sum+f_sum:,}、成本 570,603、損益 215,673、已配息 20,678、含息 41.42%'
s['fund_source_note'] = f'國泰直購＝2026-10-29 淨值 {c_sum:,}（富達 5,894,411／貝萊B11 5,079,377／聯博AD 986,300）；本金 12,000,000、不含息 -39,912'
print(f'B/C 基金 {funds_total:,}（一般 {g_sum:,}／自由PAY {f_sum:,}／國泰 {c_sum:,}）')

# ---------- D 安聯 ----------
A_FUNDS = {
 'USDEQ3490 安聯收益成長基金-AM穩定月收類股(美元)': 2669591,
 'USDEQ5440 摩根投資基金-多重收益基金-JPM多重收益(美元對沖)-A股(穩定月配)': 691591,
 'USDEQ6550 PIMCO收益增長基金-M級類別(月收息強化股份)': 1611725,
}
assert sum(A_FUNDS.values()) == 4972907, sum(A_FUNDS.values())
ib = s['insurance_breakdown']
old_b = ib['policy_b_funds']
b_tot_new = 2568361
b_old_sum = sum(old_b.values())
b_new = {k: round(v * b_tot_new / b_old_sum) for k, v in old_b.items()}
_diff = b_tot_new - sum(b_new.values())
if _diff:
    _k = max(b_new, key=lambda x: b_new[x])
    b_new[_k] += _diff
ib['policy_a_total'] = 4972907
ib['policy_a_funds'] = A_FUNDS
ib['policy_b_total'] = b_tot_new
ib['policy_b_funds'] = b_new
ib['allianz_ab_total'] = 4972907 + b_tot_new
ib['firstjin_total'] = 1862327
ib['note'] = ('安聯 A/B＝2026-10-31 19:05 App 截圖：A 4,972,907（3 檔逐檔 ✓）、B 2,568,361（總額，逐檔等比縮放）'
              '；第一金＝2026-10-31 19:10 帳戶價值 1,862,327（100% ID05 M&G入息A）。')
s['allianz_a'] = 4972907
s['allianz_b'] = b_tot_new
s['allianz_combined'] = 4972907 + b_tot_new
s['allianz_ab_value'] = s['allianz_combined']
s['firstjin_fl65_current_value'] = 1862327
s['firstjin_current_value'] = 1862327
s['insurance_total'] = s['allianz_combined'] + 1862327
fj = s.get('firstjin_detail', {})
fj['dividend_this_month'] = 9901
fj['last_update'] = '2026-10-31'
fj['account_value_20261031'] = 1862327
fj['cum_dividend_20261031'] = 169024
s['firstjin_detail'] = fj
print(f'D 保險 {s["insurance_total"]:,}（安聯 {s["allianz_combined"]:,}／第一金 1,862,327）')

# ---------- F 現金 ----------
CASH = {
 '北台中活儲存款-優質薪轉儲蓄存款': 100, '民權活儲存款-證券': 71396,
 '文心綜活儲存款-薪轉': 115298, '敦南Richart數位一般帳戶': 120798,
 '敦南數位二類異業帳戶': 13, '敦南Richart子帳戶': 709467,
 '臺幣綜存': 39044, '市政分行活期儲蓄存款': 1020,
 '營業部DAWHO活期儲蓄存款': 138348, '數位活儲': 44116,
 'Digital Savings Account': 739, 'iLEO帳戶': 716,
 '活期儲蓄存款': 779390, '數位存款帳戶２類': 2,
}
cash_sum = sum(CASH.values())
assert cash_sum == 2020447, cash_sum
s['cash_detail'] = CASH
s['cash_source'] = {'date': '2026-10-31', 'note': 'Moneybook 帳戶 CSV 匯入（cash_detail；國泰活期重複列 20,776 已排除）'}
CC = {'玉山Unicard': 4674, '台新Richart': -2990, '富邦': -32578, '永豐': -167, '國泰CUBE': -17544}
s['credit_card'] = CC
s['credit_card_pending'] = 53279
s['last_mb_sync'] = '2026-10-31 Moneybook ZIP（10/01–10/31）'
s['last_mb_sync_note'] = (
 '現金以 MB 帳戶 CSV 台幣活存為準（2,020,447；14 帳戶，已排除外幣/停用/信用卡/貸款，國泰活期重複列 20,776 不計）；'
 '信用卡 pending 53,279（富邦 32,578／國泰 17,544／台新 2,990／永豐 167；玉山 +4,674 為溢繳不計）；'
 '10/29 安聯 5,397、第一金 9,901 已入帳並補記 10 月配息。')
print(f'F 現金 {cash_sum:,}｜信用卡 53,279')

# ---------- 配息補記 ----------
dr = s['dividend_records']
oct_ = dr.setdefault('2026-10', {})
oct_['安聯保單撥回'] = 44136 + 5397
oct_['第一金人壽撥回(10/29)'] = 9901
s['dividend_records'] = dr

# ---------- 來源日期 ----------
s['source_import_dates'] = {
 '現金／銀行（Moneybook）': '2026-10-31', '證券部位': '2026-10-30',
 '保單 第一金': '2026-10-31', '保單 安聯 A/B（App）': '2026-10-31',
 '基金 國泰直購（富達/聯博/B11）': '2026-10-29', '基金 鉅亨（一般申購＋自由Pay）': '2026-10-30',
}
s['fund_nav_dates'] = {'國泰直購（富達/聯博/B11）': '2026-10-29', '鉅亨（一般申購＋自由Pay）': '2026-10-30', '安聯保單內基金（App）': '2026-10-31'}

s['total_assets'] = s['insurance_total'] + tot + funds_total + cash_sum
print(f'總資產 {s["total_assets"]:,}')
json.dump(s, open(SNAP, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('✅ snapshot 已寫入（穿透/負債/DB 待 update_data 重算）')
