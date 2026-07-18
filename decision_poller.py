"""
決策长轮询器（Decision Poller）
- 每 60 秒向 Telegram getUpdates 查询
- 检测"核准/延后/批准/拒绝"关键词
- 写到 ops_logs + Notion ops_logs DB + Telegram 回覆
- 需要 .env: TG_TOKEN, TG_CHAT_ID, NOTION_TOKEN
"""
from __future__ import annotations

import json
import os
import sys
import time
import hmac
import hashlib
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE = Path(__file__).parent.resolve()
load_dotenv(BASE / ".env")

OPS_LOGS_FILE = BASE / "ops_logs_2026-07-18.md"
DECISIONS_FILE = BASE / "dashboard_decisions.json"
NOTION_DB_ID_FILE = BASE / "notion_db_ids.json"

TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
POLL_INTERVAL = 60

KEYWORDS_APPROVE = ["核准", "批准", "approve", "yes", "✅", "好"]
KEYWORDS_DEFER = ["延后", "拒絕", "reject", "no", "⏸️", "不要"]


def tg_call(method: str, payload: dict) -> tuple[bool, dict]:
    if not TG_TOKEN:
        return False, {}
    url = f"https://api.telegram.org/bot{TG_TOKEN}/{method}"
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200, r.json() if r.status_code == 200 else {"_status": r.status_code}
    except Exception as e:
        return False, {"_error": str(e)}


def notion_write(event: dict) -> bool:
    if not NOTION_TOKEN or not NOTION_DB_ID_FILE.exists():
        return False
    try:
        db_id = json.loads(NOTION_DB_ID_FILE.read_text(encoding="utf-8")).get("ops_logs", "")
    except Exception:
        return False
    if not db_id:
        return False
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    props = {
        "事件名稱": {"title": [{"text": {"content": event.get("name", "未命名")}}]},
        "來源系統": {"select": {"name": event.get("source", "Telegram Decision")}},
        "執行狀態": {"select": {"name": event.get("status", "已完成")}},
        "事件分類": {"select": {"name": event.get("category", "決策")}},
        "CIO摘要": {"rich_text": [{"text": {"content": event.get("summary", "")}}]},
    }
    payload = {"parent": {"database_id": db_id}, "properties": props}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def record_decision(event: dict) -> None:
    decs = {"decisions": []}
    if DECISIONS_FILE.exists():
        try:
            decs = json.loads(DECISIONS_FILE.read_text(encoding="utf-8"))
            if not isinstance(decs, dict):
                decs = {"decisions": []}
        except Exception:
            decs = {"decisions": []}
    decs["decisions"].append(event)
    DECISIONS_FILE.write_text(json.dumps(decs, ensure_ascii=False, indent=2), encoding="utf-8")

    if OPS_LOGS_FILE.exists():
        ts = datetime.now().strftime("%H:%M")
        entry = (
            f"\n## {ts} Telegram 決策\n"
            f"- **事件**：{event.get('name', '')}\n"
            f"- **動作**：{event.get('action', '')}\n"
            f"- **操作人**：{event.get('user', '')}\n"
            f"- **結果**：{event.get('status', '')}\n"
            f"- **摘要**：{event.get('summary', '')}\n"
        )
        OPS_LOGS_FILE.write_text(
            OPS_LOGS_FILE.read_text(encoding="utf-8") + entry, encoding="utf-8"
        )


def process(text: str, chat_id: str, user: str, update_id: int) -> None:
    lower = text.lower()
    if any(k.lower() in lower for k in KEYWORDS_APPROVE):
        action = "核准"
    elif any(k.lower() in lower for k in KEYWORDS_DEFER):
        action = "延後"
    else:
        return

    event = {
        "timestamp": datetime.now().isoformat(),
        "update_id": update_id,
        "action": action,
        "name": f"Decision: {text[:40]}",
        "source": "Telegram Poller",
        "status": f"已{action}",
        "category": "決策",
        "user": user,
        "idem_key": f"poll-{update_id}",
        "summary": f"{user} 在 Telegram 輸入 [{action}] {text[:40]}",
    }
    record_decision(event)
    notion_write(event)

    reply = f"✅ 已記錄：{action}「{text[:30]}」\n操作人：@{user}\n時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    tg_call("sendMessage", {"chat_id": chat_id, "text": reply})
    print(f"[DECISION] {action} by {user}: {text[:40]}")


def main() -> None:
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[FAIL] TG_TOKEN / TG_CHAT_ID 未設定，請在 .env 填入")
        sys.exit(1)

    print(f"[POLLER] 啟動，每 {POLL_INTERVAL}s 輪詢 Telegram...")
    offset = 0
    while True:
        try:
            ok, resp = tg_call("getUpdates", {"offset": offset, "timeout": 5})
            if ok and resp.get("ok"):
                for upd in resp.get("result", []):
                    offset = max(offset, upd.get("update_id", 0) + 1)
                    msg = upd.get("message") or upd.get("channel_post")
                    if not msg:
                        continue
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if chat_id != str(TG_CHAT_ID):
                        continue
                    text = msg.get("text", "")
                    user = msg.get("from", {}).get("username") or msg.get("from", {}).get("first_name", "unknown")
                    process(text, chat_id, user, upd.get("update_id", 0))
        except KeyboardInterrupt:
            print("\n[POLLER] 停止")
            sys.exit(0)
        except Exception as e:
            print(f"[POLLER] error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
