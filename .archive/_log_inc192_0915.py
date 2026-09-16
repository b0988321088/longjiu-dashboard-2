# -*- coding: utf-8 -*-
"""一次性：登錄 INC-192（work_log 縮排寫錯造成 925 行假 diff，CIO V6 攔下）。"""
import json, pathlib

R = pathlib.Path('.')
p = R / 'work_log.json'
d = json.loads(p.read_text(encoding='utf-8'))
before = len(d)
d.append(dict(
    date='2026-09-15',
    category='修正',
    item='INC-192：自寫日誌腳本把 work_log.json 縮排寫成 2（canonical 1）→ 925/919 行假 diff（CIO V6 攔下）',
    detail='現象：以 _log_calsync_fix_0915.py 追加 work_log 後，commit 顯示 work_log.json 925 行新增／919 行刪除（整檔 churn），且行尾被 Windows 寫成 CRLF。根因：一次性腳本用 indent 2 寫 work_log.json，而 work_log 的 canonical 縮排是 1（json.dumps(indent=1) 才有 1 空格縮排）→ 全檔重排；git autocrlf 再把 LF 正規化，形成「看起來動了整檔」的假 diff，真改動其實只有新增 1 筆（6 行）。CIO-Gemini 複審 V6（閉環稽核第 10 類）判 REJECT 攔下。修正：①work_log.json 還原 canonical 縮排並改明示 newline="\\n"（避免 CRLF）②腳本改 indent=1 + newline="\\n" ③以 --amend 併回原 data commit（未推送），使歷史不留 925 行 churn。驗收：相對前一顆 commit 的 work_log diff = 6 行新增／0 刪除；閉環稽核全部通過。教訓：寫任何管線 JSON 前先查該檔 canonical 縮排（schedule_events／pending_decisions／dashboard_decisions＝2、snapshot／work_log／radar_state＝1），並一律明示 newline="\\n"；另閉環稽核第 10 類會把散文裡的「indent 加等號加數字」字樣誤判為寫入者，敘述時改用文字描述。'))
if len(d) != before + 1:
    raise SystemExit('work_log append 異常')
p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
print(f'work_log: {before} → {len(d)}')

er = R / 'error_register.md'
txt = er.read_text(encoding='utf-8')
if 'INC-192' not in txt:
    txt = txt.rstrip() + """

## INC-192 — 自寫日誌腳本寫錯 JSON 縮排 → 925 行假 diff（CIO 複審攔下）

- **日期**：2026-09-15
- **現象**：`_log_calsync_fix_0915.py` 追加 work_log 後，commit 顯示 `work_log.json` 925 行新增／919 行刪除（整檔 churn），行尾同時被寫成 CRLF。
- **根因**：work_log.json 的 canonical 縮排是 1（`json.dumps(indent=1)`），腳本卻用 2 寫入 → 全檔重排；git autocrlf 再正規化行尾 → 假 diff 掩蓋真改動（真的只有新增 1 筆＝6 行）。
- **攔截**：CIO-Gemini 複審 V6（閉環稽核第 10 類）判 REJECT。
- **修正**：work_log.json 還原 canonical 縮排＋明示 `newline="\\n"`；腳本同步改正；以 `--amend` 併回未推送的 data commit。
- **教訓**：①寫任何管線 JSON 前先查該檔 canonical 縮排（schedule_events／pending_decisions／dashboard_decisions＝2；snapshot／work_log／radar_state＝1）②一律明示 `newline="\\n"` ③閉環稽核第 10 類會把散文中的「indent 加等號加數字」誤判為違規寫入者，敘述請用文字（已在稽核腳本層留待收緊）。
"""
    er.write_text(txt, encoding='utf-8')
    print('error_register: 新增 INC-192')
else:
    print('error_register: INC-192 已存在')

raw = p.read_bytes()
print('驗證：', 'LF ✅' if b'\r\n' not in raw else 'CRLF ❌', '｜可解析',
      '✅' if json.loads(raw.decode('utf-8')) else '❌')
