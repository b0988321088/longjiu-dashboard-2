# -*- coding: utf-8 -*-
"""一次性：登錄 calendar_sync 過期事件灌回根因修正（work_log + error_register INC-191）。"""
import json, pathlib, datetime

R = pathlib.Path('.')

# --- work_log ---
p = R / 'work_log.json'
d = json.loads(p.read_text(encoding='utf-8'))
before = len(d)
d.append(dict(
    date='2026-09-15', category='修正',
    item='根因修正：calendar_sync 每輪把手動過期事件灌回 schedule_events（清理無效的真因）',
    detail='現象：7 月過期事件清掉後，一跑 calendar_sync 就整批回魂（本次實測 20 筆 7-8 月手動事件重新寫回 schedule_events.json，82→69→73 反覆）。根因：calendar_sync.py 末段「反向合併 GCal 手動事件」只做去重、不過濾日期，於是「每週清理刪掉 → 下次同步灌回」形成永久迴圈（使用者：「已經過期的事件一直放著沒有意思」）。修正：合併前加日期閘門 —— `str(_ev["date"])[:10] < date.today().isoformat()` 者直接 skip 並計數，log 印「略過已過期手動事件 N 筆」；Google 日曆原始事件不動（只停止灌回系統真值）。驗收：重跑 calendar_sync → 刪 73/新增 73、略過過期 20 筆，schedule_events 維持 54 筆、過期僅剩 3 筆追蹤中事件。'))
if len(d) != before + 1:
    raise SystemExit('work_log append 異常')
p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
print(f'work_log: {before} → {len(d)}')

# --- error_register ---
er = R / 'error_register.md'
txt = er.read_text(encoding='utf-8')
if 'INC-191' not in txt:
    block = """
## INC-191 — schedule_events 過期事件被 calendar_sync 灌回（每週清理形同無效）

- **日期**：2026-09-15（使用者：「裡面有很多已經過期的事件或是已經決定的事件可以把它刪掉」）
- **現象**：清掉 7 月過期事件後，重跑 `calendar_sync.py` 立刻回魂 20 筆（7/11 台南住宿、7/12 孫子演唱會、7/17 段部上課、7/19 跟媽媽打牌…），事件數 69→73 反覆。
- **根因**：`calendar_sync.py` 末段「反向合併 GCal 手動事件」僅以 item 名稱去重（INC-136 的修正），**沒有日期過濾** → 只要 Google 日曆上還留著舊的手動事件，每次同步就會寫回 `schedule_events.json`；與 `schedule_events_weekly_clean.py`（週日 08:00 自動刪過期）形成永久迴圈。
- **修正**：合併迴圈前加日期閘門（`date < today` → skip 並計數），log 新增「略過已過期手動事件 N 筆」；Google 日曆原始事件保留不動。
- **驗收**：`calendar_sync.py` → 刪 73／新增 73／略過過期 20；`schedule_events.json` = 54 筆，過期僅 3 筆（仍在追蹤語意）。
- **教訓**：清理腳本只能治標，**「誰把資料寫回來」才是根因**；任何『刪了又出現』的資料，先找反寫入路徑（sync/merge/import）。
"""
    er.write_text(txt.rstrip() + '\n' + block, encoding='utf-8')
    print('error_register: 新增 INC-191')
else:
    print('error_register: INC-191 已存在')

# 驗證
json.loads(p.read_text(encoding='utf-8'))
print('✅ work_log.json 可解析')
