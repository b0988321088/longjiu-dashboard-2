#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每週資產防禦審計 → Notion ops_logs 寫入（一次性腳本，審計員專用）"""
import os, json, sys
from pathlib import Path

REPO = Path(r"C:\Users\bot\Desktop\longjiu_system")
os.chdir(REPO)

hermes_env = Path.home() / "AppData" / "Local" / "hermes" / ".env"
proj_env = REPO / ".env"
for p in [proj_env, hermes_env]:
    if p.exists():
        os.environ["DOTENV"] = str(p)
        break
from dotenv import load_dotenv
load_dotenv(os.environ.get("DOTENV", ""))

NOTION_API_KEY = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY") or ""
if not NOTION_API_KEY:
    print("FATAL: NOTION_TOKEN not found in env")
    sys.exit(2)

import requests
BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

db_ids = json.loads((REPO / "notion_db_ids.json").read_text(encoding="utf-8"))
OPS_DB = db_ids["ops_logs"]

today = "2026-08-21"
name = f"每週資產防禦審計 {today}"
summary_path = REPO / "_weekly_audit_summary_20260821.txt"
summary = summary_path.read_text(encoding="utf-8")[:2000]

# 依任務指定：關聯頁面 = daily_report_v2_{today}.md（以 file:// 形式填入 Notion URL 欄位）
link = f"file:///C:/Users/bot/Desktop/longjiu_system/daily_report_v2_{today}.md"

# 1) 查詢是否已存在同名事件（避免重複）
q = requests.post(
    f"{BASE}/databases/{OPS_DB}/query",
    headers=HEADERS,
    json={"filter": {"property": "事件名稱", "title": {"equals": name}}},
    timeout=60,
)
q.raise_for_status()
existing = q.json().get("results", [])
print(f"existing ops_logs entries with same title: {len(existing)}")

props = {
    "事件名稱": {"title": [{"text": {"content": name}}]},
    "來源系統": {"select": {"name": "Hermes"}},
    "執行狀態": {"select": {"name": "完成"}},
    "事件分類": {"select": {"name": "審計"}},
    "CIO摘要": {"rich_text": [{"text": {"content": summary}}]},
}
# URL 欄位：先試 file://，失敗則退回 hermes 網域連結
try:
    props["關聯頁面"] = {"url": link}
    if existing:
        pid = existing[0]["id"]
        r = requests.patch(f"{BASE}/pages/{pid}", headers=HEADERS, json={"properties": props}, timeout=60)
    else:
        r = requests.post(f"{BASE}/pages", headers=HEADERS, json={"parent": {"database_id": OPS_DB}, "properties": props}, timeout=60)
    if r.status_code >= 400:
        print(f"file:// rejected: HTTP {r.status_code} {r.text[:300]}")
        raise RuntimeError("file url rejected")
except Exception as e:
    print(f"fallback: {e}")
    props["關聯頁面"] = {"url": "https://hermes-agent.nousresearch.com/daily_report_v2_2026-08-21.md"}
    if existing:
        pid = existing[0]["id"]
        r = requests.patch(f"{BASE}/pages/{pid}", headers=HEADERS, json={"properties": props}, timeout=60)
    else:
        r = requests.post(f"{BASE}/pages", headers=HEADERS, json={"parent": {"database_id": OPS_DB}, "properties": props}, timeout=60)
    r.raise_for_status()

print(f"ops_logs write OK: {r.status_code} -> {r.json().get('id', '')}")
