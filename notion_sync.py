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
        # 轉 markdown 為 Notion blocks
        blocks = []
        for line in markdown.strip().split("\n"):
            line = line.rstrip()
            if not line:
                continue
            if line.startswith("# "):
                blocks.append({"object": "block", "type": "heading_1", "heading_1": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
            elif line.startswith("## "):
                blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:]}}]}})
            elif line.startswith("### "):
                blocks.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:]}}]}})
            elif line.startswith("- "):
                blocks.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
            elif "：" in line or ":" in line:
                blocks.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line}}]}})
            else:
                blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}]}})
        payload["children"] = blocks[:100]  # Notion API 上限 100 blocks
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


def daily_dashboard_page():
    """在 Notion 建立今日資產儀表板頁面"""
    from datetime import date
    import json
    import os
    from pathlib import Path
    
    snap_path = Path(__file__).resolve().parent / "snapshot.json"
    if not snap_path.exists():
        print("[SKIP] snapshot.json 不存在")
        return
    
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    today = str(date.today())
    
    md = f"""# 📊 龍九資產儀表板 — {today}

## 💰 總覽
- 總資產：{snap.get('total_assets',0):,}
- 總負債：{snap.get('total_liabilities',0):,}
- 淨資產：{snap.get('net_worth',0):,}
- 負債比：{snap.get('debt_ratio','N/A')}%

## 🏦 資產明細
- 證券：{snap.get('securities_total',0):,}
- 保單現值：{snap.get('insurance_current_value',0):,}
- 基金：{snap.get('fund_market_value',0):,}
- 現金：{snap.get('real_liquid_assets',0):,}

## 💳 負債明細
- 房貸合計：13,159,422
- 保單質押：4,000,000
- 股票質押：1,000,000

## 📈 穿透5類
- 台股：缺口 -21pp（目標35%）
- 美股：溢價 +8pp（目標30%）
- 防守：缺口 -14pp（目標25%）
- 債券：溢價 +13pp（目標5%）
- 現金：溢價 +17pp（目標5%）

## 📋 本月配息合計：107,116
- 安聯A+B：73,167
- 第一金（FJ33+FR55）：22,949
- 基金：~11,000

## 💼 月收入
- 薪資：43,144
- 獎金（7/8）：39,121
- 差旅：12,000"""

    page = create_page_in_db(
        ASSET_DB,
        {
            "Name": {"title": [{"text": {"content": f"📊 資產儀表板 {today}"}}]},
        },
        markdown=md,
    )
    print(f"[OK] 儀表板頁面建立：{page.get('id', 'N/A')}")
    return page

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "dashboard":
        daily_dashboard_page()
    else:
        clean_slate()
