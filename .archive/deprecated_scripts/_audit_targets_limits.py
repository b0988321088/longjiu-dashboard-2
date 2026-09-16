# -*- coding: utf-8 -*-
"""盤點：穿透『目標值』與『限制/紅線』的單一真值來源 + 所有讀取者。"""
import json, pathlib, re

R = pathlib.Path('.')
snap = json.loads((R / 'snapshot.json').read_text(encoding='utf-8'))

print('=== snapshot 內與目標/限制相關的 key ===')
def walk(o, path=''):
    if isinstance(o, dict):
        for k, v in o.items():
            p = f'{path}.{k}' if path else k
            kl = str(k)
            if any(s in kl for s in ('target', '目標', '紅線', '限制', '門檻', 'threshold', 'floor', '底線',
                                     '上限', 'ceiling', 'cap', '凍結', 'frozen', 'risk')):
                if isinstance(v, (dict, list)):
                    print(f'  {p} = {json.dumps(v, ensure_ascii=False)[:220]}')
                else:
                    print(f'  {p} = {v}')
            walk(v, p)
    elif isinstance(o, list):
        for i, v in enumerate(o[:40]):
            walk(v, f'{path}[{i}]')
walk(snap)

print()
print('=== 全 repo 寫死的目標/限制字串（.py，排除 .archive）===')
pats = [
    r'台\s*10[%/]', r'台股\s*10', r'美\s*30[%/]', r'美股\s*30', r'美\s*40[%/]', r'美股\s*40',
    r'防\s*(30|20)[%/]', r'防守\s*(30|20)', r'債\s*25[%/]', r'現金\s*5[%/]', r'現\s*5[%/]',
    r'科技\s*(15|20)[%/]', r'5\.30', r'70\s*萬', r'53[%/]', r'2\.77', r'7%', r'衛星',
]
hits = {}
for f in sorted(R.glob('*.py')):
    if f.name.startswith('_') or f.name in ('_audit_closeout.py',):
        continue
    txt = f.read_text(encoding='utf-8', errors='ignore').splitlines()
    for i, line in enumerate(txt, 1):
        for p in pats:
            if re.search(p, line):
                hits.setdefault(f.name, []).append((i, line.strip()[:120]))
                break
for fn, rows in hits.items():
    print(f'-- {fn}（{len(rows)} 行）')
    for i, l in rows[:6]:
        print(f'   {i}: {l}')
