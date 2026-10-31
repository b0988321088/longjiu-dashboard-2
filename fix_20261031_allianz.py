# -*- coding: utf-8 -*-
"""修正 2026-10-31 安聯/第一金：寫對 canonical master key
根因：SYNONYM_GROUPS 的群組名 allianz_policy_a / allianz_policy_b / firstjin_total
     本身就是 snapshot 頂層既有 key，sync_snapshot_keys 會拿它當 master，
     只改 allianz_a / firstjin_fl65_current_value 會被舊值覆蓋回來。
"""
import json, shutil, os, datetime
BASE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(BASE, 'snapshot.json')
s = json.load(open(SNAP, encoding='utf-8'))
shutil.copy(SNAP, os.path.join(BASE, 'snapshot.backup_pre_20261031_az.json'))

A, B, FJ = 4972907, 2568361, 1862327
A_FUNDS = {
 'USDEQ3490 安聯收益成長基金-AM穩定月收類股(美元)': 2669591,
 'USDEQ5440 摩根投資基金-多重收益基金-JPM多重收益(美元對沖)-A股(穩定月配)': 691591,
 'USDEQ6550 PIMCO收益增長基金-M級類別(月收息強化股份)': 1611725,
}
assert sum(A_FUNDS.values()) == A, sum(A_FUNDS.values())

# canonical master keys
s['allianz_policy_a'] = A
s['allianz_policy_b'] = B
s['firstjin_total'] = FJ

# 逐檔（A 精確、B 維持 apply 的等比結果但確認合計）
ib = s['insurance_breakdown']
ib['policy_a_total'] = A
ib['policy_a_funds'] = A_FUNDS
b_funds = ib['policy_b_funds']
assert sum(b_funds.values()) == B, (sum(b_funds.values()), B)
ib['policy_b_total'] = B
ib['allianz_ab_total'] = A + B
ib['firstjin_total'] = FJ
ib['note'] = ('安聯 A/B＝2026-10-31 19:05 App 截圖：A 4,972,907（3 檔逐檔 ✓）、'
              'B 2,568,361（App 只給總額，逐檔按 10/27 比例等比）；'
              '第一金＝2026-10-31 19:10 帳戶價值 1,862,327（100% ID05 M&G入息A）。')

s['allianz_a_breakdown_note'] = ('2026-10-31 19:05 安聯 App 標的列表（A QL18610694）：3 檔逐檔合計 4,972,907＝價值總額 ✓'
                                 '（3490 2,669,591 +1.39%／5440 691,591 -1.82%／6550 1,611,725 +0.71%）')
s['allianz_b_breakdown_note'] = ('2026-10-31 19:05 安聯 App（B QL18488224）：價值總額 2,568,361（-4.50%）；'
                                 '逐檔未截圖，按 10/27 比例等比縮放（5 檔）。')
s['allianz_note_20261031'] = ('2026-10-31 19:05 安聯 App「我的投資」：帳戶總價值 7,541,268 = A 4,972,907（-0.78%）'
                              '+ B 2,568,361（-4.50%）；本月累積配息/撥回 10 筆共 49,533（vs 10/27 之 9 筆 44,136，'
                              '新增 10/29 入帳 5,397）；風險屬性 積極型（效期至 116/01/21）。')
s['firstjin_note_20261031'] = ('2026-10-31 19:10 第一金人壽『我的帳戶表現』：保單帳戶價值 1,862,327'
                               '（vs 10/24 之 1,870,639，-8,312）；累計總繳保費 2,000,000、累計提領 0、'
                               '累計已給付配息/撥回 169,024（vs 10/22 之 159,123，+9,901）；'
                               '投資總成本報酬率 -6.80%、總繳保險費報酬率 含息 1.57%／不含息 -6.88%；'
                               '配置 100% ID05-M&G入息基金A(美元避險月配)。')
s['insurance_note'] = '2026-10-31 安聯 A 4,972,907＋B 2,568,361＋第一金 1,862,327（10/31）＝9,403,595'
s['insurance_stale_notice'] = '無（安聯 A/B、第一金皆 2026-10-31）'
s['firstjin_cum_dividend'] = 169024
s['insurance_total'] = A + B + FJ
s['insurance_current_value'] = s['insurance_total']
s['total_assets'] = (s['insurance_total'] + s['securities_total_market_value']
                     + s['fund_market'] + s['cash_total'])
json.dump(s, open(SNAP, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'安聯 A {A:,} + B {B:,} = {A+B:,}｜第一金 {FJ:,}｜保險 {s["insurance_total"]:,}')
print(f'總資產 {s["total_assets"]:,}')
