"""
🟡 決策核准處理腳本 — decision_handler.py
職責：
1. 從 dashboard_decisions.json 讀取 pending 項目
2. 匹配使用者輸入的「✅ 核准 [ID]」或「✅ 核准」
3. 更新 JSON 狀態為 approved + 時間戳
4. 同步寫入 Notion ops_logs
5. Telegram 回覆確認閉環

使用方式（由 Hermes 執行長呼叫）：
  python decision_handler.py "✅ 核准 TEST_DEPLOY_20260720"
  python decision_handler.py "✅ 核准"  # 自動匹配最新 pending
"""
import json, os, sys, requests
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent.resolve()
DECISIONS_FILE = BASE / "dashboard_decisions.json"
NOTION_DB_IDS_FILE = BASE / "notion_db_ids.json"
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")


def _load_decisions() -> dict:
    if not DECISIONS_FILE.exists():
        return {"pending_decisions": [], "decisions": []}
    try:
        return json.loads(DECISIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"pending_decisions": [], "decisions": []}


def _save_decisions(data: dict):
    DECISIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _tg_reply(text: str) -> bool:
    """回覆 Telegram 確認訊息"""
    if not TG_TOKEN or not TG_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def _notion_write(event: dict) -> bool:
    """寫入 Notion ops_logs database"""
    if not NOTION_DB_IDS_FILE.exists():
        return False
    try:
        db_ids = json.loads(NOTION_DB_IDS_FILE.read_text(encoding="utf-8"))
        db_id = db_ids.get("ops_logs", "")
    except Exception:
        return False
    if not db_id:
        return False

    notion_token = ""
    env_path = BASE / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("NOTION_TOKEN="):
                notion_token = line.split("=", 1)[1].strip()
                break

    if not notion_token:
        return False

    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    props = {
        "事件名稱": {"title": [{"text": {"content": event.get("name", "未命名")}}]},
        "來源系統": {"select": {"name": event.get("source", "Hermes Decision Handler")}},
        "執行狀態": {"select": {"name": event.get("status", "已核准")}},
        "事件分類": {"select": {"name": event.get("category", "決策")}},
        "CIO摘要": {"rich_text": [{"text": {"content": event.get("summary", "")}}]},
    }
    payload = {"parent": {"database_id": db_id}, "properties": props}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def handle(input_text: str) -> str:
    """主處理函數：解析輸入，匹配 pending，更新狀態，同步 Notion，回覆 TG"""
    data = _load_decisions()
    pending = data.get("pending_decisions", [])
    if not pending:
        return "⚠️ 目前無 pending 決策項目"

    # 解析輸入：支援「✅ 核准 ID」或「✅ 核准」
    cleaned = input_text.replace("✅", "").replace(" ", "").strip()
    target_id = None
    if cleaned.startswith("核准"):
        rest = cleaned[2:].strip()
        if rest:
            target_id = rest

    # 匹配 pending 項目
    matched = None
    if target_id:
        for p in pending:
            if p["id"] == target_id:
                matched = p
                break
        if not matched:
            ids = [p["id"] for p in pending]
            return f"⚠️ 找不到 ID: {target_id}。可用 ID：{', '.join(ids)}"
    else:
        # 無指定 ID，取最新 pending
        matched = pending[0]

    # 更新狀態
    now = datetime.now(timezone.utc).isoformat()
    matched["action"] = "approved"
    matched["approved_at"] = now

    # 冪等性檢查：如 decisions 已有相同 ID，不重複寫入
    data.setdefault("decisions", [])
    existing_ids = {d["id"] for d in data["decisions"] if "id" in d}
    if matched["id"] in existing_ids:
        return f"ℹ️ {matched['id']} 已核准過，跳過重複記錄"

    # 移出 pending，加入 decisions
    data["pending_decisions"] = [p for p in pending if p["id"] != matched["id"]]
    data["decisions"].append(matched)
    _save_decisions(data)

    # 建構事件物件（含即時資產摘要）
    snap_now = {}
    try:
        snap_now = json.loads((BASE / "snapshot.json").read_text("utf-8"))
    except: pass
    event = {
        "name": matched.get("text", matched["id"]),
        "source": "Hermes Decision Handler",
        "status": "已核准",
        "category": matched.get("category", "決策"),
        "summary": f"[{matched['id']}] {matched.get('text', '')} — 執行長核准 ✅",
        "context": f"資產 {snap_now.get('total_assets',0):,} / 保險 {snap_now.get('insurance_current_value',0):,} / 現金 {snap_now.get('real_liquid_assets',0):,}",
    }

    # 同步 Notion
    notion_ok = _notion_write(event)
    
    # 同步到戰略手稿頁面
    try:
        _summary = matched.get("text", matched["id"])
        import requests as _rq
        _env = open(os.path.expanduser("~/AppData/Local/hermes/.env"))
        _nt = ""
        for _l in _env:
            if "NOTION_TOKEN" in _l and "=" in _l:
                _nt = _l.split("=",1)[1].strip()
        if _nt:
            _hdrs = {"Authorization": f"Bearer {_nt}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
            _block = {"children": [{"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": f"✅ {_summary[:80]}"}}]}}]}
            _rq.patch("https://api.notion.com/v1/blocks/3a4fc735d43381d18a4bfe63e1bd6b2a/children", json=_block, headers=_hdrs, timeout=10)
    except: pass
    
    if notion_ok:
        reply = f"✅ 已記錄：{matched['id']} 並同步至 Notion ✅"
    else:
        reply = f"✅ 已記錄：{matched['id']}（Notion 同步失敗）"

    # Telegram 回覆
    _tg_reply(reply)

    return reply


if __name__ == "__main__":
    if len(sys.argv) > 1:
        result = handle(" ".join(sys.argv[1:]))
        print(result)
    else:
        print("使用方式：python decision_handler.py \"✅ 核准 [ID]\"")
