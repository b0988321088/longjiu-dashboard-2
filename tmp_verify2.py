import requests, os
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": "2022-06-28"}
BASE = "https://api.notion.com/v1"
db_id = "39dfc735-d433-8153-9712-c8a0ee0ec846"
payload = {"page_size": 5}
r = requests.post(f"{BASE}/databases/{db_id}/query", headers=HEADERS, json=payload, timeout=30)
print(r.status_code, r.text[:500])
