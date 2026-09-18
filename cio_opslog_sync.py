#!/usr/bin/env python3
"""CIO 18:30 戰略審計復盤 → 寫入 Notion ops_logs（週五復盤底稿）"""
import json, os, sys, requests
import argparse as _ap_mod
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_IDS = json.loads((BASE / "notion_db_ids.json").read_text(encoding="utf-8"))
DB_ID = DB_IDS.get("ops_logs", "")

token = ""
for src in [Path(os.environ.get("NOTION_TOKEN", "")), Path.home() / "AppData/Local/hermes/.env", BASE / ".env"]:
    pass

def _find_token():
    # 1) env
    t = os.environ.get("NOTION_TOKEN", "")
    if t:
        return t
    # 2) hermes .env
    for p in [Path.home() / "AppData/Local/hermes/.env", BASE / ".env"]:
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("NOTION_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

token = _find_token()
if not token or not DB_ID:
    print("NO_TOKEN_OR_DBID")
    sys.exit(2)

_ap = _ap_mod.ArgumentParser(description="寫入 Notion ops_logs（CIO 復盤底稿／審計事件共用）")
_ap.add_argument("summary", nargs="?", default="")
_ap.add_argument("name", nargs="?", default="CIO 18:30 戰略審計與決策復盤 2026-09-02")
_ap.add_argument("--source", default="CIO Adversarial Review", help="來源系統（select）；審計事件填 Hermes")
_ap.add_argument("--category", default="戰略審計", help="事件分類（select）；審計事件填 審計")
_ap.add_argument("--status", default="完成")
_ap.add_argument("--link", default="", help="關聯頁面 URL（選填，空值不寫入）")
_args = _ap.parse_args()
summary = _args.summary
name = _args.name

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}
# 分段寫入（Notion rich_text 單段上限 2000 字元）
chunks = [summary[i:i + 1900] for i in range(0, len(summary), 1900)] or [""]
props = {
    "事件名稱": {"title": [{"text": {"content": name}}]},
    "來源系統": {"select": {"name": _args.source}},
    "執行狀態": {"select": {"name": _args.status}},
    "事件分類": {"select": {"name": _args.category}},
    "CIO摘要": {"rich_text": [{"text": {"content": c}} for c in chunks]},
}
if _args.link:
    props["關聯頁面"] = {"url": _args.link}
url = "https://api.notion.com/v1/pages"
r = requests.post(url, headers=headers, json={"parent": {"database_id": DB_ID}, "properties": props}, timeout=15)
print(f"HTTP {r.status_code}")
if r.status_code != 200:
    print(r.text[:500])
    sys.exit(1)
sys.exit(0)
