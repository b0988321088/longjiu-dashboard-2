#!/usr/bin/env python3
"""龍九決策自動記錄器 — 每次重要裁決自動寫入 Notion"""
import os, requests, datetime, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENV = BASE / ".env"

def _load(key, default=""):
    v = os.environ.get(key, "")
    if v:
        return v
    try:
        with open(ENV) as f:
            for line in f:
                if key in line and "=" in line and "YOUR" not in line:
                    return line.split("=", 1)[1].strip().strip('"')
    except:
        pass
    return default

TOKEN = _load("NOTION_TOKEN")
DB_ID = _load("NOTION_ANALYSIS_DB_ID")
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

STATUS_PREFIX = "狀態："


def _with_status(summary, status, today):
    """把狀態併進摘要文字（分析庫沒有「狀態」屬性，見 decision-governance 技能）。
    冪等：同一狀態行已存在就不重複附加。
    ⚠️ 狀態行一定保留：先讓出空間再截斷，避免摘要接近 2000 字時把剛附加的狀態行切掉
    （CIO 審查 2026-09-14 建議 #2）。"""
    summary = summary or ""
    if not status:
        return summary[:2000]
    line = f"{STATUS_PREFIX}{status}（{today}）"
    if line in summary:
        return summary[:2000]
    head = summary.rstrip()
    if not head:
        return line[:2000]
    room = max(0, 2000 - len(line) - 1)      # 留 1 字元給換行
    return (head[:room] + "\n" + line)[:2000]


def log_decision(title, summary, detail="", tags="", status="⚡ 執行中"):
    """寫入一筆決策記錄到 Notion（狀態併入摘要）"""
    if not TOKEN or not DB_ID:
        print("⚠️ Notion 未設定，略過")
        return ""
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    body = {
        "parent": {"database_id": DB_ID},
        "properties": {
            "名稱": {"title": [{"text": {"content": f"{today} {title}"}}]},
            "日期": {"date": {"start": today}},
            "類型": {"select": {"name": "決策記錄"}},
            "摘要": {"rich_text": [{"text": {"content": _with_status(summary, status, today)}}]},
            "原始報告": {"rich_text": [{"text": {"content": (detail or "")[:2000]}}]},
            "相關資產": {"rich_text": [{"text": {"content": (tags or "")[:2000]}}]},
        },
    }
    try:
        r = requests.post(
            "https://api.notion.com/v1/pages",
            headers=HEADERS, json=body, timeout=10
        )
        if r.status_code == 200:
            pid = r.json().get("id", "")
            print(f"✅ 決策已記錄 → Notion (status={status})")
            return pid
        else:
            print(f"⚠️ Notion 寫入失敗: {r.status_code} {r.text[:100]}")
            return ""
    except Exception as e:
        print(f"⚠️ Notion 異常: {e}")
        return ""


def complete(decision_id):
    """將決策標記為已完成 — 分析庫沒有「狀態」屬性，故把完成狀態併進摘要（冪等）。"""
    if not decision_id:
        return
    try:
        r = requests.get(f"https://api.notion.com/v1/pages/{decision_id}",
                         headers=HEADERS, timeout=10)
        if r.status_code != 200:
            print(f"⚠️ 讀取頁面失敗: {r.status_code}")
            return
        cur = "".join(t.get("plain_text", "") for t in
                      r.json().get("properties", {}).get("摘要", {}).get("rich_text", []))
        today = datetime.date.today().isoformat()
        new = _with_status(cur, "✅ 已完成", today)
        if new == cur:
            print("ℹ️ 摘要已含完成狀態，略過")
            return
        p = requests.patch(
            f"https://api.notion.com/v1/pages/{decision_id}",
            headers=HEADERS,
            json={"properties": {"摘要": {"rich_text": [{"text": {"content": new}}]}}},
            timeout=10,
        )
        print("✅ 決策狀態 → 摘要追加「✅ 已完成」" if p.status_code == 200
              else f"⚠️ 狀態更新失敗: {p.status_code} {p.text[:80]}")
    except Exception as e:
        print(f"⚠️ 狀態更新異常: {e}")

if __name__ == "__main__":
    # CLI mode: python notion_decision_logger.py "title" "summary" "detail" "tags" "status"
    if len(sys.argv) >= 3:
        log_decision(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "",
                     sys.argv[4] if len(sys.argv) > 4 else "",
                     sys.argv[5] if len(sys.argv) > 5 else "⚡ 執行中")
    else:
        print("用法: python notion_decision_logger.py <標題> <摘要> [詳細] [標籤] [狀態]")
