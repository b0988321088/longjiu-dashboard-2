import requests
import os
import json

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": "2022-06-28"}
BASE = "https://api.notion.com/v1"

db_ids = {
    "master_ledger": "39dfc735-d433-8153-9712-c8a0ee0ec846",
    "debt_cashflow": "22bc6fdb-6b06-4f63-8bb9-eaf9482f828d",
    "fund_station": "39dfc735-d433-81df-acfe-f179b6666c1d",
    "ops_logs": "39dfc735-d433-818e-9b5c-d206d0c791af",
}

for name, db_id in db_ids.items():
    r = requests.get(f"{BASE}/databases/{db_id}", headers=HEADERS, timeout=30)
    print(f"=== {name} ===")
    if r.status_code != 200:
        print(f"Error: {r.status_code} {r.text[:200]}")
        continue
    data = r.json()
    props = data.get("properties", {})
    for k, v in props.items():
        print(f"  {k}: {v.get('type')}")
    print()
