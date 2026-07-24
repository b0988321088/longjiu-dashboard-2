"""
Notion AI 自動摘要腳本 — 取代 Hermes 輕量查詢 cron
從 Notion API 讀取 ops_logs + master_ledger，產出摘要推送到 Telegram

使用方式：
  python notion_ai_summary.py daily    # 日報摘要
  python notion_ai_summary.py weekly   # 週報摘要
  python notion_ai_summary.py decisions  # 決策清單
"""
import json, os, requests, sys
from datetime import datetime, date, timedelta
from pathlib import Path

BASE = Path(__file__).parent.resolve()

# ── 環境變數 ──
NOTION_TOKEN = ""
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

env_path = BASE / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("NOTION_TOKEN="):
            NOTION_TOKEN = line.split("=", 1)[1].strip()
        elif line.startswith("TG_TOKEN="):
            TG_TOKEN = line.split("=", 1)[1].strip()

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# ── Notion DB IDs ──
DB_IDS = {}
ids_file = BASE / "notion_db_ids.json"
if ids_file.exists():
    DB_IDS = json.loads(ids_file.read_text(encoding="utf-8"))


def _query_db(db_key: str, filter_dict: dict = None) -> list:
    """Query Notion database by key, return list of pages."""
    db_id = DB_IDS.get(db_key, "")
    if not db_id:
        return []
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    payload = {}
    if filter_dict:
        payload["filter"] = filter_dict
    try:
        r = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=15)
        return r.json().get("results", [])
    except Exception:
        return []


def _extract_title(page: dict) -> str:
    """Extract title from a Notion page."""
    props = page.get("properties", {})
    for key, val in props.items():
        if val.get("type") == "title":
            texts = val.get("title", [])
            return "".join(t.get("plain_text", "") for t in texts)
    return ""


def _extract_text(page: dict, field: str) -> str:
    """Extract rich_text or select value from a page property."""
    props = page.get("properties", {})
    prop = props.get(field, {})
    if prop.get("type") == "rich_text":
        texts = prop.get("rich_text", [])
        return "".join(t.get("plain_text", "") for t in texts)
    if prop.get("type") == "select":
        sel = prop.get("select")
        return sel.get("name", "") if sel else ""
    if prop.get("type") == "date":
        d = prop.get("date")
        return d.get("start", "") if d else ""
    return ""


def _tg_push(text: str):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
    except Exception:
        pass


# ══════════════════════════════════════
#  摘要功能
# ══════════════════════════════════════

def daily_summary():
    """今日決策與資產摘要"""
    today = date.today().isoformat()
    
    # ops_logs: 今日決策
    ops = _query_db("ops_logs", {
        "and": [
            {"property": "事件名稱", "title": {"is_not_empty": True}},
        ]
    })
    
    lines = [f"📋 Notion 日報摘要 {today}", ""]
    
    # 決策
    dec_lines = []
    for p in ops:
        name = _extract_title(p)
        status = _extract_text(p, "執行狀態")
        ts = _extract_text(p, "時間戳記")[:10] if _extract_text(p, "時間戳記") else ""
        if today in ts or not ts:
            dec_lines.append(f"  {status} {name}")
    
    if dec_lines:
        lines.append("📌 今日決策：")
        lines.extend(dec_lines)
    else:
        lines.append("📌 今日無新決策")
    
    # master_ledger: 本週資產
    lines.append(f"\n📊 資產狀態：請至 Notion master_ledger 查看")
    lines.append(f"\n💡 使用 Notion AI：直接在搜尋框問「本週資產變化」")
    
    return "\n".join(lines)


def weekly_review():
    """週報：從共享知識層讀取本週資產快照 + 分析記錄"""
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    try:
        from notion_knowledge import query_latest, _db_id
        # 讀取本週資產快照
        snaps = query_latest("NOTION_DAILY_SNAPSHOT_DB_ID", limit=7)
        # 讀取本週分析記錄
        analyses = query_latest("NOTION_ANALYSIS_DB_ID", limit=10)
    except:
        snaps, analyses = [], []
    
    lines = ["📋 Notion 週報", f"期間：{week_ago} ~ {date.today().isoformat()}", ""]
    
    # 資產趨勢
    if snaps:
        latest = snaps[0]
        lines.append(f"📊 最新資產：{latest.get('總資產',0):,} TWD")
        lines.append(f"  證券 {latest.get('證券',0):,} / 保單 {latest.get('保單',0):,} / 基金 {latest.get('基金',0):,} / 現金 {latest.get('現金',0):,}")
        if len(snaps) >= 2:
            diff = (snaps[0].get('總資產',0) or 0) - (snaps[-1].get('總資產',0) or 0)
            lines.append(f"  本週變動：{diff:+,} TWD")
    else:
        lines.append("📊 資產資料：尚無記錄")
    
    # 分析記錄摘要
    lines.append("")
    if analyses:
        lines.append(f"📝 分析記錄 ({len(analyses)} 筆)：")
        for a in analyses[:5]:
            t = a.get('類型','')
            s = a.get('摘要','')[:60]
            if t or s:
                lines.append(f"  [{t}] {s}")
    else:
        lines.append("📝 分析記錄：尚無記錄")
    
    lines.append(f"\n💡 所有代理共享：notion_knowledge.py 自動寫入")
    return "\n".join(lines)


def decision_list():
    """目前 pending 決策清單"""
    ops = _query_db("ops_logs")
    pending = []
    for p in ops:
        name = _extract_title(p)
        status = _extract_text(p, "執行狀態")
        if "延後" in status or "pending" in status.lower():
            pending.append(f"  ⏸️ {name}")
    
    lines = ["📋 延後/Pending 決策清單", ""]
    lines.extend(pending or ["  （無 pending 項目）"])
    lines.append("\n💡 使用 Notion AI：直接在 Notion 問「有哪些延後的決策」")
    
    return "\n".join(lines)


# ══════════════════════════════════════
#  Main
# ══════════════════════════════════════

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    
    if mode == "daily":
        text = daily_summary()
    elif mode == "weekly":
        text = weekly_review()
    elif mode == "decisions":
        text = decision_list()
    else:
        text = "❌ 用法：python notion_ai_summary.py [daily|weekly|decisions]"
    
    print(text)
    _tg_push(text)
