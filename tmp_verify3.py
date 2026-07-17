import requests, os
from datetime import datetime

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": "2022-06-28"}
BASE = "https://api.notion.com/v1"

DB_MAP = {
    "master_ledger": "39dfc735-d433-8153-9712-c8a0ee0ec846",
    "debt_cashflow": "22bc6fdb-6b06-4f63-8bb9-eaf9482f828d",
    "fund_station": "39dfc735-d433-81df-acfe-f179b6666c1d",
    "ops_logs": "39dfc735-d433-818e-9b5c-d206d0c791af",
    "asset_investment": "27ecdd83-8137-4943-ba87-2b0b8e9555c6",
}

TODAY = "2026-07-17"

for name, db_id in DB_MAP.items():
    payload = {"page_size": 100}
    r = requests.post(f"{BASE}/databases/{db_id}/query", headers=HEADERS, json=payload, timeout=30)
    if r.status_code != 200:
        print(f"{name}: query failed {r.status_code}")
        continue
    data = r.json()
    results = data.get("results", [])
    today_results = [p for p in results if p.get("created_time", "").startswith(TODAY)]
    print(f"=== {name}: {len(today_results)} rows created today (total {len(results)}) ===")
    for page in today_results:
        props = page.get("properties", {})
        title = ""
        for k, v in props.items():
            if v.get("type") == "title":
                title = "".join(t.get("plain_text", "") for t in v.get("title", []))
                break
        print(f" - {title}")
    print()
