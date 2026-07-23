#!/usr/bin/env python3
"""notion_context_loader.py — 從 Notion 載入昨日快照供 Agent 參考
由 morning_wrapper.py 在每日 06:00 自動執行，產出快取檔案供 agent 讀取"""

import json
from pathlib import Path
from datetime import date, timedelta

BASE = Path(__file__).resolve().parent
CACHE = BASE / "notion_context_cache.json"
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()

def load_from_notion():
    """查詢 Notion 最新分析記錄"""
    try:
        from notion_knowledge import query_latest
        data = query_latest(limit=1)
        if data:
            return {"source": "notion", "date": YESTERDAY, "data": data}
    except Exception as e:
        return {"source": "error", "error": str(e)}
    return {"source": "not_found"}

def load_from_local():
    """Fallback: 讀取本地 daily_analysis.json"""
    path = BASE / "daily_analysis.json"
    if path.exists():
        return {"source": "local", "date": YESTERDAY, "data": json.loads(path.read_text(encoding="utf-8"))}
    return {"source": "not_found"}

result = load_from_notion()
if result["source"] == "not_found":
    result = load_from_local()

CACHE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[CONTEXT] Notion 脈絡載入完成 → {result['source']}")
