import requests, os
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": "2022-06-28"}
db_id = "22bc6fdb-6b06-4f63-8bb9-eaf9482f828d"
r = requests.get(f"https://api.notion.com/v1/databases/{db_id}", headers=HEADERS, timeout=30)
print(r.status_code)
print(r.json().get("properties", {}).get("狀態"))
