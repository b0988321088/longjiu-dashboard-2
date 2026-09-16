# -*- coding: utf-8 -*-
"""檢視：schedule_events / pending_decisions / dashboard_decisions.pending_decisions 的過期與已結案分布。"""
import json, pathlib, collections, datetime

R = pathlib.Path('.')
TODAY = '2026-09-15'
WEEK_START = '2026-09-09'   # 本週起

ev = json.loads((R / 'schedule_events.json').read_text(encoding='utf-8'))
print(f'=== schedule_events.json（{len(ev)} 筆）===')
buckets = collections.Counter()
for e in ev:
    dt = str(e.get('date', ''))[:10]
    st = str(e.get('status', ''))
    closed = any(k in st for k in ('已結案', '已完成', '已取消', '已作廢', '維持不轉換', '已延後', '已暫緩', '不轉換', '已送出', '已生效'))
    if dt >= TODAY:
        buckets['未來'] += 1
    elif dt >= WEEK_START:
        buckets['本週(9/9-9/14)'] += 1
    elif closed:
        buckets['過期+已結案'] += 1
    else:
        buckets['過期+未結案'] += 1
for k, v in buckets.items():
    print(f'  {k}: {v}')
print('  --- 過期+已結案 全部 ---')
for e in ev:
    dt = str(e.get('date', ''))[:10]
    st = str(e.get('status', ''))
    closed = any(k in st for k in ('已結案', '已完成', '已取消', '已作廢', '維持不轉換', '已延後', '已暫緩', '不轉換', '已送出', '已生效'))
    if dt < TODAY and closed:
        print(f'   {dt} | {st[:16]} | {str(e.get("item",""))[:58]}')
print('  --- 過期+未結案（保留候選）---')
for e in ev:
    dt = str(e.get('date', ''))[:10]
    st = str(e.get('status', ''))
    closed = any(k in st for k in ('已結案', '已完成', '已取消', '已作廢', '維持不轉換', '已延後', '已暫緩', '不轉換', '已送出', '已生效'))
    if dt < TODAY and not closed:
        print(f'   {dt} | {st[:16]} | {str(e.get("item",""))[:58]}')
print('  --- 未來 ---')
for e in ev:
    dt = str(e.get('date', ''))[:10]
    if dt >= TODAY:
        print(f'   {dt} | {str(e.get("status",""))[:16]} | {str(e.get("item",""))[:58]}')

for f, key in (('pending_decisions.json', None), ('dashboard_decisions.json', 'pending_decisions')):
    d = json.loads((R / f).read_text(encoding='utf-8'))
    arr = d if key is None else d[key]
    print(f'=== {f}{"[" + key + "]" if key else ""}（{len(arr)} 筆）===')
    for it in arr:
        print(f'   {str(it.get("date"))[:10]} | {str(it.get("status",""))[:30]} | {str(it.get("title") or it.get("action",""))[:52]}')
