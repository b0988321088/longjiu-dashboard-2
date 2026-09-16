# -*- coding: utf-8 -*-
"""一次性：清掉「已決定」待辦卡與殘留垃圾事件（--apply 才寫入）。"""
import json, pathlib, sys

R = pathlib.Path('.')
ARCH = R / '.archive'
APPLY = '--apply' in sys.argv
ARCH.mkdir(exist_ok=True)
log = []

# --- 1) schedule_events：垃圾/測試殘留 ---
p = R / 'schedule_events.json'
ev = json.loads(p.read_text(encoding='utf-8'))
junk = [e for e in ev if str(e.get('date', '')) in ('待處理',) or str(e.get('date', ''))[:4] == '4050']
keep = [e for e in ev if e not in junk]
for e in junk:
    log.append(f'  事件垃圾 - {e.get("date")} | {e.get("status")} | {str(e.get("item"))[:44]}')
if APPLY and junk:
    (ARCH / 'removed_schedule_events_junk.json').write_text(
        json.dumps(junk, ensure_ascii=False, indent=1), encoding='utf-8')
    p.write_text(json.dumps(keep, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
log.append(f'1) schedule_events {len(ev)} → {len(keep)}（刪垃圾/測試殘留 {len(junk)}）')

# --- 2) 已決定的待辦卡（status 以 ✅/☑/❌ 開頭 = 已定案/已執行）---
DECIDED = ('✅', '☑', '❌')
for f, key in (('pending_decisions.json', None), ('dashboard_decisions.json', 'pending_decisions')):
    fp = R / f
    d = json.loads(fp.read_text(encoding='utf-8'))
    arr = d if key is None else d[key]
    gone = [it for it in arr if str(it.get('status', '')).strip().startswith(DECIDED)]
    kept = [it for it in arr if it not in gone]
    for it in gone:
        log.append(f'  待辦卡 - {str(it.get("date"))[:10]} | {str(it.get("status"))[:34]} | {str(it.get("title") or it.get("action"))[:40]}')
    log.append(f'2) {f}{"[" + key + "]" if key else ""} {len(arr)} → {len(kept)}（刪已決定 {len(gone)}）')
    if APPLY and gone:
        (ARCH / (f.replace('.json', '') + ('_' + key if key else '') + '_decided.json')).write_text(
            json.dumps(gone, ensure_ascii=False, indent=1), encoding='utf-8')
        if key is None:
            fp.write_text(json.dumps(kept, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        else:
            d[key] = kept
            fp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

print('=== APPLY ===' if APPLY else '=== DRY-RUN ===')
print('\n'.join(log))
# 驗證
for f in ('schedule_events.json', 'pending_decisions.json', 'dashboard_decisions.json'):
    d = json.loads((R / f).read_text(encoding='utf-8'))
    n = len(d) if isinstance(d, list) else f"{len(d['pending_decisions'])} 待辦 + {len(d['decisions'])} 日誌"
    print(f'  ✅ {f} 可解析：{n}')
