# -*- coding: utf-8 -*-
"""對齊 allianz_a_breakdown / allianz_b_breakdown 至 10/31 真值（保單不變式）"""
import json, os
BASE = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(BASE, 'snapshot.json')
s = json.load(open(p, encoding='utf-8'))
ib = s['insurance_breakdown']
s['allianz_a_breakdown'] = dict(ib['policy_a_funds'])
s['allianz_b_breakdown'] = dict(ib['policy_b_funds'])
ba = sum(s['allianz_a_breakdown'].values())
bb = sum(s['allianz_b_breakdown'].values())
pa = s['allianz_policy_a_value']
pb = s['allianz_policy_b_value']
print(f'A 子基金 {ba:,} vs policy {pa:,} → {"OK" if ba == pa else "FAIL"}')
print(f'B 子基金 {bb:,} vs policy {pb:,} → {"OK" if bb == pb else "FAIL"}')
assert ba == pa and bb == pb
json.dump(s, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('✅ 已寫入')
