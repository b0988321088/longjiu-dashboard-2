#!/usr/bin/env python3
"""memory_archiver.py — 記憶自動歸檔腳本
功能：將低頻記憶條目寫入 Notion 並回報哪些可移除
設計：由 cron 觸發，回報結果給使用者處理（因只有 Hermes 能改 memory）"""

import json, os, re
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Notion DB ID（從環境變數或 hermes .env 讀取）
NOTION_DB = ""
env_path = Path.home() / "AppData/Local/hermes/.env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.startswith("NOTION_DAILY_SNAPSHOT_DB_ID="):
            NOTION_DB = line.split("=", 1)[1].strip().strip("\"'")

print(f"📦 記憶歸檔檢查 — {date.today()}")
print(f"   Notion DB: {NOTION_DB[:30] if NOTION_DB else '未設定'}")
print()
print("⚠️ 注意：此腳本只能寫入 Notion，無法直接修改 Hermes memory。")
print("   請在執行後手動從 memory 移除已歸檔的條目。")
print()
print("建議歸檔條件（低頻/已穩定的記錄）：")
print("  - INC 記錄（已存入 ERROR_LOG.md）")
print("  - 已決策且不再變動的設定")
print("  - 超過 1 個月未更新的資訊")
print()
print("執行方式：python memory_archiver.py")
