#!/usr/bin/env python3
"""龍九決策自動記錄器 — 每次重要裁決自動寫入 Notion"""
import os, json, requests, datetime, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENV = BASE / ".env"

def _load(key, default=""):
    v = os.environ.get(key, "")
    if v:
        return v
    try:
        with open(ENV) as f:
            for line in f:
                if key in line and "=" in line and "YOUR" not in line:
                    return line.split("=", 1)[1].strip().strip('"')
    except:
        pass
    return default

TOKEN = _load("NOTION_TOKEN")
DB_ID = _load("NOTION_ANALYSIS_DB_ID")
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def log_decision(title, summary, detail="", tags="", status="⚡ 執行中"):
    """寫入一筆決策記錄到 Notion"""
    if not TOKEN or not DB_ID:
        print("⚠️ Notion 未設定，略過")
        return ""
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    body = {
        "parent": {"database_id": DB_ID},
        "properties": {
            "名稱": {"title": [{"text": {"content": f"{today} {title}"}}]},
            "日期": {"date": {"start": today}},
            "類型": {"select": {"name": "決策記錄"}},
            "摘要": {"rich_text": [{"text": {"content": (summary or "")[:2000]}}]},
            "原始報告": {"rich_text": [{"text": {"content": (detail or "")[:2000]}}]},
            "相關資產": {"rich_text": [{"text": {"content": (tags or "")[:2000]}}]},
        },
    }
    try:
        r = requests.post(
            "https://api.notion.com/v1/pages",
            headers=HEADERS, json=body, timeout=10
        )
        if r.status_code == 200:
            pid = r.json().get("id", "")
            print(f"✅ 決策已記錄 → Notion (status={status})")
            return pid
        else:
            print(f"⚠️ Notion 寫入失敗: {r.status_code} {r.text[:100]}")
            return ""
    except Exception as e:
        print(f"⚠️ Notion 異常: {e}")
        return ""

def complete(decision_id):
    """將決策標記為已完成"""
    if not decision_id:
        return
    try:
        requests.patch(
            f"https://api.notion.com/v1/pages/{decision_id}",
            headers=HEADERS,
            json={"properties": {"狀態": {"select": {"name": "✅ 已完成"}}}},
            timeout=10,
        )
        print(f"✅ 決策狀態 → ✅ 已完成")
    except:
        pass

if __name__ == "__main__":
    # CLI mode: python notion_decision_logger.py "title" "summary" "detail" "tags" "status"
    if len(sys.argv) >= 3:
        log_decision(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "",
                     sys.argv[4] if len(sys.argv) > 4 else "",
                     sys.argv[5] if len(sys.argv) > 5 else "⚡ 執行中")
    else:
        print("用法: python notion_decision_logger.py <標題> <摘要> [詳細] [標籤] [狀態]")
