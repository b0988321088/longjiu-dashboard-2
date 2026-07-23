"""Notion 雙向橋接 v0.1 — 祕書處管線
功能：讀取 Notion「戰略手稿」頁面 → 寫入本地決策 db
"""
import json, os, re, requests
from datetime import date, datetime
from pathlib import Path

# ── 設定 ──
_HERMES_ENV = Path(os.path.expanduser("~/AppData/Local/hermes/.env"))
LJ = Path(os.path.expanduser("~/Desktop/longjiu_system"))
NOTION_TOKEN = ""
# 動態讀取（從 Hermes 主 .env）
def _load_env():
    global NOTION_TOKEN, NOTION_DAILY_SNAPSHOT_DB_ID
    NOTION_DAILY_SNAPSHOT_DB_ID = ""
    if _HERMES_ENV.exists():
        for line in _HERMES_ENV.read_text().splitlines():
            if 'NOTION_TOKEN' in line and '=' in line and not line.strip().startswith('#'):
                NOTION_TOKEN = line.split('=',1)[1].strip().strip('"\'')
            if 'NOTION_DAILY_SNAPSHOT_DB_ID' in line and '=' in line and not line.strip().startswith('#'):
                NOTION_DAILY_SNAPSHOT_DB_ID = line.split('=',1)[1].strip().strip('"\'')
    if NOTION_TOKEN:
        HEADERS["Authorization"] = f"Bearer {NOTION_TOKEN}"

def _get_snapshot_db_id() -> str:
    import os
    if 'NOTION_DAILY_SNAPSHOT_DB_ID' in os.environ:
        return os.environ['NOTION_DAILY_SNAPSHOT_DB_ID']
    _load_env()
    return NOTION_DAILY_SNAPSHOT_DB_ID or ""
HEADERS = {
    "Authorization": "Bearer invalid",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
BASE = "https://api.notion.com/v1"
_load_env()

def notion_get(path: str) -> dict:
    r = requests.get(f"{BASE}{path}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

def notion_post(path: str, payload: dict) -> dict:
    r = requests.post(f"{BASE}{path}", json=payload, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

def search_strategy_pages() -> list:
    """搜尋包含「戰略手稿」或「戰術指令」的頁面"""
    q = {"query": "戰略手稿", "sort": {"direction": "descending", "timestamp": "last_edited_time"}}
    r = notion_post("/search", q)
    results = r.get("results", [])
    if not results:
        q2 = {"query": "戰術指令", "sort": {"direction": "descending", "timestamp": "last_edited_time"}}
        r2 = notion_post("/search", q2)
        results = r2.get("results", [])
    return results

def read_page_blocks(page_id: str) -> list:
    """讀取 Notion 頁面所有 text blocks"""
    blocks = []
    cursor = None
    while True:
        url = f"/blocks/{page_id}/children"
        if cursor:
            url += f"?start_cursor={cursor}"
        r = notion_get(url)
        blocks.extend(r.get("results", []))
        if not r.get("has_more"):
            break
        cursor = r.get("next_cursor")
    return blocks

def parse_blocks_to_text(blocks: list) -> str:
    """將 Notion blocks 轉為純文字"""
    lines = []
    for b in blocks:
        btype = b.get("type", "")
        content = b.get(btype, {})
        rich_text = content.get("rich_text", []) if isinstance(content, dict) else []
        text = "".join(t.get("text", {}).get("content", "") for t in rich_text if isinstance(t, dict))
        if text.strip():
            if btype.startswith("heading"):
                prefix = "#" * int(btype[-1]) if btype[-1].isdigit() else ""
                lines.append(f"{prefix} {text}")
            elif btype == "bulleted_list_item":
                lines.append(f"- {text}")
            elif btype == "numbered_list_item":
                lines.append(f"1. {text}")
            elif btype == "to_do":
                checked = "✅" if content.get("checked") else "⬜"
                lines.append(f"{checked} {text}")
            else:
                lines.append(text)
    return "\n".join(lines)

def extract_decisions_from_text(text: str) -> list:
    """從文字中提取核准/延後決策"""
    decisions = []
    today = str(date.today())
    for line in text.split("\n"):
        line = line.strip()
        if "核准" in line or "✅" in line:
            decisions.append({
                "source": "notion",
                "action": "核准",
                "text": line.replace("✅", "").replace("核准", "").strip(":：- "),
                "approved_at": datetime.now().isoformat(),
            })
        elif "延後" in line or "⏸️" in line:
            decisions.append({
                "source": "notion",
                "action": "延後",
                "text": line.replace("⏸️", "").replace("延後", "").strip(":：- "),
                "approved_at": datetime.now().isoformat(),
            })
    return decisions

def sync_notion_to_local() -> dict:
    """主流程：Notion → 本地 db"""
    result = {"pages_found": 0, "decisions_imported": 0, "errors": []}
    
    pages = search_strategy_pages()
    result["pages_found"] = len(pages)
    
    all_decisions = []
    for page in pages[:3]:  # 最多讀3頁
        page_id = page["id"]
        page_title = ""
        for prop_name, prop_val in page.get("properties", {}).items():
            if prop_val.get("type") == "title":
                titles = prop_val.get("title", [])
                page_title = "".join(t.get("plain_text", "") for t in titles)
                break
        
        blocks = read_page_blocks(page_id)
        text = parse_blocks_to_text(blocks)
        
        decisions = extract_decisions_from_text(text)
        all_decisions.extend(decisions)
        
        # 寫入原始文字供日報使用
        raw_dir = LJ / "notion_bridge"
        raw_dir.mkdir(exist_ok=True)
        (raw_dir / f"{date.today()}_strategy_handbook.md").write_text(
            f"# 戰略手稿：{page_title}\n來源頁面：{page_id}\n讀取時間：{datetime.now().isoformat()}\n\n{text}",
            encoding="utf-8"
        )
    
    # 合併到 dashboard_decisions.json
    dec_file = LJ / "dashboard_decisions.json"
    if dec_file.exists():
        existing = json.loads(dec_file.read_text(encoding="utf-8"))
    else:
        existing = {"pending_decisions": [], "decisions": []}
    
    for d in all_decisions:
        # 去重：避免同一決策重複寫入
        dup = False
        for ed in existing.get("decisions", []):
            if ed.get("text") == d["text"] and ed.get("source") == "notion":
                dup = True
                break
        if not dup:
            existing.setdefault("decisions", []).append(d)
            result["decisions_imported"] += 1
    
    dec_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return result

def local_to_notion(decisions: list) -> dict:
    """本地決策 → Notion Ops Logs（已有 decision_handler.py 處理）"""
    return {"synced": False, "note": "由 decision_handler.py 接管"}

def push_daily_snapshot(tv: dict) -> str:
    """將每日資產快照寫入 Notion database"""
    db_id = _get_snapshot_db_id()
    if not db_id:
        print("Error: NOTION_DAILY_SNAPSHOT_DB_ID is not set in .env")
        return """

    data_to_send = {
        "parent": {"database_id": db_id},
        "properties": {
            "日期": {"date": {"start": tv.get("date", datetime.now().isoformat())}},
            "名稱": {"title": [{"text": {"content": f"{tv.get('date','today')} 資產快照"}}]},
            "總資產": {"number": tv.get("total_assets", 0)},
            "證券": {"number": tv.get("securities", 0)},
            "保單": {"number": tv.get("insurance", 0)},
            "基金": {"number": tv.get("funds", 0)},
            "現金": {"number": tv.get("cash", 0)},
            "備註": {"rich_text": [{"text": {"content": tv.get('note', '')}}]},
        },
    }
    
    try:
        response = notion_post("/pages", data_to_send)
        page_id = response.get("id")
        if page_id:
            print(f"Successfully pushed daily snapshot to Notion. Page ID: {page_id}")
        else:
            print(f"Failed to push daily snapshot to Notion. Response: {response}")
        return page_id
    except requests.exceptions.RequestException as e:
        print(f"Error pushing daily snapshot to Notion: {e}")
        return """

if __name__ == "__main__":
    r = sync_notion_to_local()
    print(f"📡 Notion 橋接報告")
    print(f"找到頁面：{r['pages_found']}")
    print(f"匯入決策：{r['decisions_imported']}")
    for e in r.get("errors", []):
        print(f"  ⚠️ {e}")
    
    if r["pages_found"] > 0:
        print(f"\n✅ 已寫入 notion_bridge/{date.today()}_strategy_handbook.md")
        print(f"✅ 決策已合併至 dashboard_decisions.json")
