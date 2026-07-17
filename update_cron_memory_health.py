import subprocess
from pathlib import Path

prompt = """你是龍九控股的 Chief Reporter。現在是每天早上 08:50，請執行以下任務：

## 產出流程
1. 讀取 C:/Users/bot/Desktop/龍九系統/Company_Ledger.md 取得資產負債最新數據
2. 讀取 C:/Users/bot/Desktop/龍九系統/framework_snapshot_2026-07-16.json 取得系統快照
3. 讀取 C:/Users/bot/Desktop/龍九系統/moneybook_6m_analysis.py 錯誤
4. 寫入 daily_report_v2_YYYY-MM-DD.md 檔案

## 大腦成熟度指標（新增）
在日報末尾加入「MEMORY_HEALTH」區段：
- 執行 python C:/Users/bot/Desktop/龍九系統/holographic_daily_check.py
- 讀取 PRESSURE_TEST_LOG.md 趨勢
- 顯示：總事實數、高信號事實(>0.8)、實體數、LIKE查詢延遲
- 目標：7天內從 7 條 -> 20 條

## 內容規範
1. 五章 markdown：市場情報、資產負債表、被動income追蹤、異常與行動、Buffett/CTO洞察
2. 繁體中文
3. 寫入後 git add + git commit + git push origin main

## 交付
日報連結：https://github.com/b0988321088/longjiu-dashboard-2/blob/main/daily_report_v2_YYYY-MM-DD.md
儀表板連結：https://b0988321088.github.io/longjiu-dashboard-2/"""

result = subprocess.run([
    'hermes', 'cron', 'update',
    '--job-id', 'ebe15ce7517f',
    '--prompt', prompt,
    '--workdir', 'C:\\Users\\bot\\Desktop\\龍九系統'
], capture_output=True, text=True, timeout=60)

print('STDOUT:', result.stdout[:800])
print('STDERR:', result.stderr[:800])
print('RC:', result.returncode)
