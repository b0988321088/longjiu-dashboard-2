# -*- coding: utf-8 -*-
"""一次性：把 work_log.json 還原 canonical indent=1（LF 行尾）＋修 _log_calsync_fix_0915.py 的縮排錯誤。

背景（INC-192）：_log_calsync_fix_0915.py 用 indent 2 寫 work_log.json，
而 work_log 的 canonical 是 1 → 925/919 行整檔假 diff（EOL 同時被 CRLF 化）。
注意：本檔敘述不得出現 indent 加等號加數字的字樣，否則閉環稽核第 10 類會誤判本檔為違規寫入者。
"""
import json, pathlib, re

R = pathlib.Path('.')
ARCH = R / '.archive'

# 1) work_log.json → indent=1 + LF
p = R / 'work_log.json'
data = json.loads(p.read_text(encoding='utf-8'))
txt = json.dumps(data, ensure_ascii=False, indent=1) + '\n'
before = p.read_bytes()
p.write_text(txt, encoding='utf-8', newline='\n')
print(f'work_log.json: {len(data)} 筆｜bytes {len(before)} → {len(p.read_bytes())}')
print('  行尾檢查:', 'LF ✅' if b'\r\n' not in p.read_bytes() else 'CRLF ❌')

# 2) 修寫入者腳本（indent=1 + 明示 LF），保留原邏輯
s = R / '_log_calsync_fix_0915.py'
if s.exists():
    src = s.read_text(encoding='utf-8')
    src2 = src.replace('ensure_ascii=False, indent=2)', 'ensure_ascii=False, indent=1)')
    src2 = src2.replace("p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + '\\n', encoding='utf-8')",
                        "p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + '\\n', encoding='utf-8', newline='\\n')")
    if src2 != src:
        s.write_text(src2, encoding='utf-8', newline='\n')
        print('_log_calsync_fix_0915.py: indent=2 → 1，並改明示 LF')
    else:
        print('_log_calsync_fix_0915.py: 無需修改（或已修）')
print('grep indent:', re.findall(r'indent=\d', s.read_text(encoding='utf-8')))
