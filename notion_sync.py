import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

BANK_DB = "290368b4-047b-4ee9-9fd1-739055689523"
ASSET_DB = "27ecdd83-8137-4943-ba87-2b0b8e9555c6"


def notion_get(path: str) -> dict:
    r = requests.get(f"{BASE}{path}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def notion_post(path: str, payload: dict) -> dict:
    r = requests.post(f"{BASE}{path}", headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def test_identity():
    data = notion_get("/users/me")
    print("[OK] identity:", data.get("name"), data.get("id"))


def test_db_properties(db_id: str, label: str):
    data = notion_get(f"/databases/{db_id}")
    props = list(data.get("properties", {}).keys())
    print(f"[OK] {label} properties:", props)


def create_page_in_db(db_id: str, props: dict, markdown: str = "") -> dict:
    payload = {
        "parent": {"database_id": db_id},
        "properties": props,
    }
    if markdown:
        payload["markdown"] = markdown
    return notion_post("/pages", payload)


def clean_slate():
    print("=== Notion Clean Slate Test ===")
    test_identity()
    test_db_properties(BANK_DB, "BANK")
    test_db_properties(ASSET_DB, "ASSET")

    # Minimal property write using title-only first
    bank_page = create_page_in_db(
        BANK_DB,
        {
            "名稱": {"title": [{"text": {"content": "【TEST】Clean Slate 連線測試"}}]},
        },
    )
    print("[OK] bank test page:", bank_page.get("id"))

    asset_page = create_page_in_db(
        ASSET_DB,
        {
            "名稱": {"title": [{"text": {"content": "【TEST】Clean Slate 資產庫"}}]},
        },
    )
    print("[OK] asset test page:", asset_page.get("id"))
    print("=== Clean Slate Done ===")


if __name__ == "__main__":
    clean_slate()
