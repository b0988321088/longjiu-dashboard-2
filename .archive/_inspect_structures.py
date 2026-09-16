# -*- coding: utf-8 -*-
"""一次性結構檢視：刪除作業前先看清楚 schedule_events / pending_decisions / dashboard_decisions 結構。"""
import json, pathlib

R = pathlib.Path('.')
for f in ('schedule_events.json', 'pending_decisions.json', 'dashboard_decisions.json'):
    p = R / f
    if not p.exists():
        print(f'{f}: 不存在'); continue
    d = json.loads(p.read_text(encoding='utf-8'))
    print(f'=== {f} ===')
    if isinstance(d, dict):
        print('  top keys:', list(d.keys())[:10])
        for k, v in d.items():
            if isinstance(v, list) and v:
                print(f'  {k}: {len(v)} 筆 欄位={sorted(v[0].keys())}')
                print('   樣本:', json.dumps(v[0], ensure_ascii=False)[:200])
            elif not isinstance(v, (list, dict)):
                print(f'  {k} = {str(v)[:80]}')
    elif isinstance(d, list):
        print('  list len =', len(d))
        print('  樣本:', json.dumps(d[0], ensure_ascii=False)[:200])
        ks = set()
        for e in d:
            if isinstance(e, dict):
                ks |= set(e.keys())
        print('  欄位:', sorted(ks))

# schedule_events 內含多少過期
p = R / 'schedule_events.json'
d = json.loads(p.read_text(encoding='utf-8'))
ev = d['events'] if isinstance(d, dict) and 'events' in d else (d if isinstance(d, list) else [])
if ev:
    old = [e for e in ev if str(e.get('date', ''))[:10] < '2026-08-01']
    print('schedule_events: 總', len(ev), '｜2026-08-01 前 =', len(old))
    for e in old[:25]:
        print('   ', e.get('date'), '|', str(e.get('item', ''))[:60])
