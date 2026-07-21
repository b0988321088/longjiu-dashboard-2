"""Notion 雙向橋接 v0.1 — 祕書處管線
功能：讀取 Notion「戰略手稿」頁面 → 寫入本地決策 db
"""
import json, os, re, requests
from datetime import date, datetime
from pathlib import Path

# ── 設定 ──
ENV = Path(os.path.expanduser("~/AppData/Local/hermes/.env"))
LJ = Path(os.path.expanduser("~/Desktop/龍九系統"))
NOTION_TOKEN = ""
if ENV.exists():
    for line in ENV.read_text().splitlines():
        if "NOTION_TOKEN" in line and "=" in line and not line.strip().startswith("#"):
            NOTION_TOKEN = line.split("=", 1)[1].strip()

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
BASE = "https://api.notion.com/v1"

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
