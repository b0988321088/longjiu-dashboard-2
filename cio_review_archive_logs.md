
## 審查請求：日誌歸檔腳本 `archive_logs.py`

**審查員：** CIO-Gemini
**提交者：** Hermes Agent
**日期：** 2026-09-16 00:22:29

**檔案路徑：** `C:\Users\bot/Desktop/longjiu_system\archive_logs.py`

**目的：**
此腳本旨在優化上下文大小和 API 成本，透過自動歸檔 `work_log.json` 和 `error_register.md` 中的舊條目來實現。這將有助於保持這些常用檔案的精簡，減少它們被載入 LLM 上下文時所需的 token 數量。

**主要修改點：**

1.  **`work_log.json` 歸檔：**
    *   保留過去 30 天內的條目。
    *   將所有超過 30 天的條目歸檔至 `.archive/work_log_archive_YYYYMMDD.json`。
    *   更新 `work_log.json` 只包含最新條目。
    *   確保 JSON 格式正確，縮排 `1` 個空格，並使用 `LF` 換行符。

2.  **`error_register.md` 歸檔：**
    *   保留所有尚未解決的 INC 報告。
    *   將所有已解決且解決日期超過 60 天的 INC 報告歸檔至 `.archive/error_register_archive_YYYYMMDD.md`。
    *   更新 `error_register.md` 只包含未解決或最近解決的 INC 報告。
    *   確保 Markdown 格式正確，並使用 `LF` 換行符。

**潛在影響：**

*   **正面：** 減少 `work_log.json` 和 `error_register.md` 的檔案大小，從而降低這些檔案在 LLM 上下文中佔用的 token 數量，潛在地減少 API 成本和觸發 `context overflow` 的風險。提高系統運行效率。
*   **中性：** 歸檔的舊條目仍然保留在 `.archive` 目錄中，可以隨時查閱。
*   **風險：**
    *   **數據丟失風險（已考慮）**：腳本在寫入前會讀取所有數據，並在寫入新檔案後更新舊檔案，降低了數據丟失的風險。同時，歸檔檔案會以日期為名獨立保存。
    *   **格式破壞風險（已考慮）**：腳本在保存 JSON 和 Markdown 檔案時，會強制使用標準的縮排和換行符，以防止格式錯誤。
    *   **邏輯錯誤風險**：日期解析和 INC 狀態判斷的邏輯是否完全無誤。

**審查建議：**

請 CIO 審查此腳本的邏輯，特別是日期判斷、INC 狀態提取和檔案更新機制，以確保其穩健性和數據完整性。核准後，將考慮將此腳本納入每日自動化維護任務。

--- 腳本內容 START ---
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
archive_logs.py — 歸檔 work_log.json 和 error_register.md 的舊條目

此腳本會執行以下操作：
1. 讀取 work_log.json。
2. 針對 work_log.json，保留過去 30 天的記錄，將更舊的記錄移至 .archive/work_log_archive_YYYYMMDD.json。
3. 讀取 error_register.md。
4. 針對 error_register.md，保留未解決的 INC 報告，並將已解決且超過 60 天的報告移至 .archive/error_register_archive_YYYYMMDD.md。
5. 確保歸檔後的檔案保持正確的 JSON 縮排和 Markdown 格式。
6. 在腳本執行後，會顯示變更的摘要。
"""
import json
import os
import re
from datetime import datetime, timedelta

ROOT = os.path.expanduser('~/Desktop/longjiu_system')
WORK_LOG_PATH = os.path.join(ROOT, 'work_log.json')
ERROR_REGISTER_PATH = os.path.join(ROOT, 'error_register.md')
ARCHIVE_DIR = os.path.join(ROOT, '.archive')

# 確保歸檔目錄存在
os.makedirs(ARCHIVE_DIR, exist_ok=True)

def load_json(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"WARN: {filepath} not found.")
        return []
    except json.JSONDecodeError:
        print(f"ERROR: Failed to decode JSON from {filepath}. Skipping.")
        return []

def save_json(filepath, data, indent=1):
    with open(filepath, 'w', encoding='utf-8', newline='\\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)

def load_text(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"WARN: {filepath} not found.")
        return ""

def save_text(filepath, content):
    with open(filepath, 'w', encoding='utf-8', newline='\\n') as f:
        f.write(content)

def archive_work_log():
    print(f"處理 {WORK_LOG_PATH}...")
    current_logs = load_json(WORK_LOG_PATH)
    
    if not current_logs:
        print("work_log.json 為空或無法讀取，跳過歸檔。")
        return 0, 0

    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    recent_logs = []
    old_logs = []

    for log_entry in current_logs:
        log_date_str = log_entry.get('date')
        if log_date_str:
            try:
                log_date = datetime.strptime(log_date_str, '%Y-%m-%d')
                if log_date < thirty_days_ago:
                    old_logs.append(log_entry)
                else:
                    recent_logs.append(log_entry)
            except ValueError:
                print(f"WARN: 無效的日期格式 '{log_date_str}'，保留此條目。")
                recent_logs.append(log_entry)
        else:
            print(f"WARN: 缺少 'date' 鍵，保留此條目。")
            recent_logs.append(log_entry)

    if old_logs:
        archive_filename = datetime.now().strftime('work_log_archive_%Y%m%d.json')
        archive_filepath = os.path.join(ARCHIVE_DIR, archive_filename)
        save_json(archive_filepath, old_logs)
        save_json(WORK_LOG_PATH, recent_logs)
        print(f"已歸檔 {len(old_logs)} 條 work_log 舊條目至 {archive_filepath}")
        print(f"work_log.json 已更新，保留 {len(recent_logs)} 條最新條目。")
        return len(old_logs), len(recent_logs)
    else:
        print("沒有 work_log 舊條目需要歸檔。")
        return 0, len(current_logs)

def archive_error_register():
    print(f"處理 {ERROR_REGISTER_PATH}...")
    content = load_text(ERROR_REGISTER_PATH)

    if not content:
        print("error_register.md 為空或無法讀取，跳過歸檔。")
        return 0, 0

    sections = re.split(r'(^## INC-\d+.*?$)', content, flags=re.MULTILINE | re.DOTALL)
    
    resolved_old_sections = []
    remaining_content_parts = []
    
    for i in range(1, len(sections), 2):
        header = sections[i]
        body = sections[i+1] if i+1 < len(sections) else ""
        full_section = header + body

        # 檢查是否為「已解決」且超過 60 天
        resolved_match = re.search(r'- \*\*日期\*\*：(\d{4}-\d{2}-\d{2}).*?\b已解決\b', full_section, re.DOTALL)
        
        if resolved_match:
            resolved_date_str = resolved_match.group(1)
            try:
                resolved_date = datetime.strptime(resolved_date_str, '%Y-%m-%d')
                sixty_days_ago = datetime.now() - timedelta(days=60)
                if resolved_date < sixty_days_ago:
                    resolved_old_sections.append(full_section)
                    continue # 不保留此部分
            except ValueError:
                print(f"WARN: error_register 中無效的解決日期格式 '{resolved_date_str}'，保留此 INC。")
        
        remaining_content_parts.append(full_section)
    
    # 處理開頭的非 INC-xxx 內容 (sections[0])
    if sections and sections[0].strip() and not sections[0].strip().startswith('## INC-'):
        remaining_content_parts.insert(0, sections[0])
    elif sections and sections[0].strip().startswith('## INC-'):
        # 如果sections[0]是INC-xxx開頭，表示第一個INC被split了，不應該再加一次
        pass
    else:
        # sections[0]可能是空字串或只有換行，或無效內容
        pass

    if resolved_old_sections:
        archive_filename = datetime.now().strftime('error_register_archive_%Y%m%d.md')
        archive_filepath = os.path.join(ARCHIVE_DIR, archive_filename)
        save_text(archive_filepath, "\\n".join(resolved_old_sections).strip())
        save_text(ERROR_REGISTER_PATH, "\\n".join(remaining_content_parts).strip())
        print(f"已歸檔 {len(resolved_old_sections)} 條 error_register 舊條目至 {archive_filepath}")
        print(f"error_register.md 已更新，保留 {len(remaining_content_parts) - 1 if remaining_content_parts and len(sections) > 1 and not sections[0].strip().startswith('## INC-') else len(remaining_content_parts)} 條最新條目。") # 估計INC數量
        return len(resolved_old_sections), len(remaining_content_parts)
    else:
        print("沒有 error_register 舊條目需要歸檔。")
        return 0, len(remaining_content_parts) # 估計INC數量


def main():
    print("--- 開始執行日誌歸檔 ---")
    
    # Work Log 歸檔
    old_work_logs, current_work_logs = archive_work_log()
    
    print("-" * 30)
    
    # Error Register 歸檔
    old_error_inc, current_error_inc = archive_error_register() # 這裡 current_error_inc 其實是 sections 數量
    
    print("\\n--- 日誌歸檔完成 ---")
    print(f"work_log.json: 歸檔 {old_work_logs} 條，保留 {current_work_logs} 條。")
    print(f"error_register.md: 歸檔 {old_error_inc} 條，保留 {current_error_inc} 區塊。") # 這裡的區塊數量是 split 後的數量，非準確 INC 數量

if __name__ == '__main__':
    main()

```
--- 腳本內容 END ---
