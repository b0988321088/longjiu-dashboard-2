"""
Hermes Telegram 決策按鈕輔助工具
- 發送底部鍵盤（ReplyKeyboardMarkup）給使用者
- 收到鍵盤訊息後，解析決策並記錄
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE = Path(__file__).parent.resolve()
load_dotenv(BASE / ".env")

TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
DECISIONS_FILE = BASE / "dashboard_decisions.json"
OPS_LOGS_FILE = BASE / "ops_logs_2026-07-18.md"
NOTION_DB_ID_FILE = BASE / "notion_db_ids.json"


def tg_send_keyboard(text: str) -> bool:
    """發送訊息 + 底部鍵盤"""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "reply_markup": {
            "keyboard": [
                [{"text": "✅ 核准"}, {"text": "⏸️ 延後"}],
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        },
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def tg_remove_keyboard() -> bool:
    """移除底部鍵盤"""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": "---",
        "reply_markup": {"remove_keyboard": True},
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def tg_send(text: str) -> bool:
    """發送純文字"""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def record_decision(action: str, summary: str) -> dict:
    from decision_utils import defer_until

    now = datetime.now()
    remind_at = defer_until(action) if action == "延後" else ""
    event = {
        "timestamp": now.isoformat(),
        "action": action,
        "name": summary[:60],
        "source": "Hermes Telegram Gate",
        "status": f"已{action}",
        "category": "決策",
        "user": "Laing",
        "idem_key": f"hermes-{int(now.timestamp())}",
        "summary": summary,
        "remind_at": remind_at,
    }

    # 1) dashboard_decisions.json
    decs = {"decisions": []}
    if DECISIONS_FILE.exists():
        try:
            d = json.loads(DECISIONS_FILE.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                decs = d
        except Exception:
            pass
    decs.setdefault("decisions", [])
    # 冪等性檢查：同名+同動作+同分鐘，視為重複
    is_dup = any(
        d.get("name") == event["name"]
        and d.get("action") == event["action"]
        and d.get("timestamp", "")[:16] == now.isoformat()[:16]
        for d in decs["decisions"]
    )
    if not is_dup:
        decs["decisions"].append(event)
    DECISIONS_FILE.write_text(json.dumps(decs, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2) ops_logs.md
    ts = now.strftime("%H:%M")
    entry = (
        f"\n## {ts} Telegram 決策\n"
        f"- **事件**：{event['name']}\n"
        f"- **動作**：{event['action']}\n"
        f"- **操作人**：{event['user']}\n"
        f"- **結果**：{event['status']}\n"
    )
    if remind_at:
        entry += f"- **提醒**：{remind_at}\n"
    entry += f"- **摘要**：{event['summary']}\n"
    OPS_LOGS_FILE.write_text(
        OPS_LOGS_FILE.read_text(encoding="utf-8") + entry, encoding="utf-8"
    )

    # 3) Notion
    _notion_write(event)

    return event


def _notion_write(event: dict) -> bool:
    if not NOTION_DB_ID_FILE.exists():
        return False
    try:
        db_id = json.loads(NOTION_DB_ID_FILE.read_text(encoding="utf-8")).get("ops_logs", "")
    except Exception:
        return False
    if not db_id:
        return False
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {os.getenv('NOTION_TOKEN', '')}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    props = {
        "事件名稱": {"title": [{"text": {"content": event.get("name", "未命名")}}]},
        "來源系統": {"select": {"name": event.get("source", "Hermes Telegram Gate")}},
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


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "send_keyboard":
            text = sys.argv[2] if len(sys.argv) > 2 else "請確認："
            tg_send_keyboard(text)
        elif cmd == "remove_keyboard":
            tg_remove_keyboard()
        elif cmd == "send":
            text = sys.argv[2] if len(sys.argv) > 2 else ""
            tg_send(text)
    else:
        print("Usage: python decision_buttons.py send_keyboard|remove_keyboard|send <text>")
