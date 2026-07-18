"""
Telegram Decision Webhook（Railway / Render 部署）
接收 balancer 建議的 InlineKeyboard callback，
簽核/延後 後寫入本地 ops_logs + Notion + Telegram 回覆。
"""
from __future__ import annotations

import json
import os
import sys
import hmac
import hashlib
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify

# ===== config =====
app = Flask(__name__)
BASE = Path(__file__).parent.resolve()
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")

DECISIONS_FILE = BASE / "dashboard_decisions.json"
OPS_LOGS_FILE = BASE / "ops_logs_2026-07-18.md"
NOTION_DB_ID = os.getenv("NOTION_OPS_LOGS_DB_ID", "")

# ===== helpers =====

def _verify_signature(body: bytes, sig: str) -> bool:
    if not WEBHOOK_SECRET:
        return True
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()[:64]
    return hmac.compare_digest(expected, sig or "")


def _tg_call(method: str, payload: dict) -> tuple[bool, dict]:
    if not TG_TOKEN:
        return False, {}
    url = f"https://api.telegram.org/bot{TG_TOKEN}/{method}"
    try:
        import requests
        r = requests.post(url, json=payload, timeout=10)
        ok = r.status_code == 200
        return ok, r.json() if ok else {"_status": r.status_code}
    except Exception as e:
        return False, {"_error": str(e)}


def _notion_write(event: dict) -> bool:
    if not NOTION_TOKEN or not NOTION_DB_ID:
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
    payload = {"parent": {"database_id": NOTION_DB_ID}, "properties": props}
    try:
        import requests
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def _record_decision(event: dict) -> None:
    # dashboard_decisions.json
    decs = {}
    if DECISIONS_FILE.exists():
        try:
            decs = json.loads(DECISIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            decs = {}
    decs.setdefault("decisions", []).append(event)
    DECISIONS_FILE.write_text(json.dumps(decs, ensure_ascii=False, indent=2), encoding="utf-8")

    # ops_logs.md
    if OPS_LOGS_FILE.exists():
        ts = datetime.now().strftime("%H:%M")
        entry = (
            f"\n## {ts} Telegram 決策\n"
            f"- **事件**：{event.get('name','')}\n"
            f"- **動作**：{event.get('action','')}\n"
            f"- **操作人**：執行長（Telegram Inline Button）\n"
            f"- **結果**：{event.get('status','')}\n"
            f"- **摘要**：{event.get('summary','')}\n"
        )
        OPS_LOGS_FILE.write_text(
            OPS_LOGS_FILE.read_text(encoding="utf-8") + entry, encoding="utf-8"
        )


# ===== routes =====

@app.route("/webhook/telegram", methods=["POST"])
def telegram_webhook():
    body = request.get_data()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not _verify_signature(body, sig):
        return jsonify({"ok": False, "error": "bad signature"}), 403

    update = json.loads(body.decode("utf-8"))
    callback = update.get("callback_query")
    if not callback:
        return jsonify({"ok": True})

    cqid = callback.get("id")
    data = callback.get("data", "")
    user = callback.get("from", {}).get("username", "unknown")
    chat_id = callback.get("message", {}).get("chat", {}).get("id", TG_CHAT_ID)

    # Expect format: action|key|idempotency_key
    parts = data.split("|", 2)
    if len(parts) < 3:
        answer = "格式錯誤"
        _tg_call("answerCallbackQuery", {"callback_query_id": cqid, "text": answer})
        return jsonify({"ok": False})

    action, key, idem_key = parts[0], parts[1], parts[2]

    # Idempotency: skip if already processed
    if DECISIONS_FILE.exists():
        try:
            existing = json.loads(DECISIONS_FILE.read_text(encoding="utf-8")).get("decisions", [])
            if any(d.get("idem_key") == idem_key for d in existing):
                _tg_call("answerCallbackQuery", {"callback_query_id": cqid, "text": "已處理"})
                return jsonify({"ok": True, "skip": "duplicate"})
        except Exception:
            pass

    # Map action
    action_zh = {"approve": "核准", "defer": "延後", "detail": "詳細"}.get(action, action)
    status_map = {"approve": "已核准", "defer": "已延後", "detail": "查看"}
    status = status_map.get(action, "未處理")

    # Parse item from key (format: action|target|idem)
    target = key.replace("_", " ")

    event = {
        "timestamp": datetime.now().isoformat(),
        "action": action_zh,
        "name": f"Decision: {target}",
        "source": "Telegram Inline Button",
        "status": status,
        "category": "決策",
        "user": user,
        "idem_key": idem_key,
        "summary": f"{user} 在 Telegram 按下 [{action_zh}] {target}",
    }

    _record_decision(event)
    _notion_write(event)

    # Telegram reply
    reply_text = f"✅ 已記錄：{action_zh}「{target}」\n操作人：@{user}\n時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    _tg_call("sendMessage", {"chat_id": chat_id, "text": reply_text})
    _tg_call("answerCallbackQuery", {"callback_query_id": cqid, "text": action_zh})

    return jsonify({"ok": True})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
