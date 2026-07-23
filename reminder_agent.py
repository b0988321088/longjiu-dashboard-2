#!/usr/bin/env python3
"""reminder_agent.py — 主動提醒系統
每日兩次（08:00 / 20:00）檢查並推播：
- 保單轉換截止日（含 T+4 倒數）
- 信用卡繳款日（3天內到期）
- 待辦決策（未處理超過3天）
- 記憶容量（>80% 時提醒歸檔）"""

import json, csv, os, sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from logging_config import get_logger
logger = get_logger("reminder_agent")

BASE = Path(__file__).resolve().parent

# ── Telegram 推播 ──
def tg_send(text: str):
    env_path = Path.home() / "AppData/Local/hermes/.env"
    token, chat_id = "", ""
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="): token = line.split("=",1)[1].strip()
            if line.startswith("TELEGRAM_ALLOWED_USERS="): chat_id = line.split("=",1)[1].strip()
    if token and chat_id:
        import requests
        try:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
        except: pass

alerts = []
today = date.today()

# ── 1. 信用卡繳款提醒（3天內） ──
try:
    mb_dir = BASE / "moneybook"
    bills = sorted(mb_dir.glob("*帳單*.csv"), reverse=True)
    if bills:
        _cc_map = {"玉山銀行": "UNI", "台新銀行": "Richart", "永豐銀行": "SPORT", "台北富邦": "momo/J"}
        _latest = {}
        with open(bills[0], "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                bank = row.get("金融機構", "")
                amt = row.get("帳單金額", "0").replace(",", "").replace('"', "")
                due = row.get("繳費截止日", "").strip()
                if bank in _cc_map and due and amt:
                    try:
                        due_dt = datetime.strptime(due, "%Y/%m/%d").date()
                        if bank not in _latest or due_dt > _latest[bank][0]:
                            _latest[bank] = (due_dt, int(float(amt)))
                    except: pass
        for bank, (due_dt, amt) in _latest.items():
            days_left = (due_dt - today).days
            if 0 <= days_left <= 3:
                card = _cc_map[bank]
                level = "🔴" if days_left == 0 else "🟡"
                alerts.append(f"{level} {bank} {card} **{amt:,}元** {days_left}天後到期")
except Exception as e:
    alerts.append(f"⚠️ 信用卡讀取錯誤: {e}")

# ── 2. 保單轉換截止日（T+4） ──
try:
    relay = BASE / "relay_calendar.md"
    if relay.exists():
        text = relay.read_text(encoding="utf-8")
        import re
        for m in re.finditer(r"(\d{1,2})/(\d{1,2}).*?([\u4e00-\u9fff].*?)[：:]\s*(\d{4}-\d{2}-\d{2})", text):
            fund = m.group(3).strip()
            deadline_str = m.group(4)
            try:
                deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
                days_left = (deadline - today).days
                if 0 <= days_left <= 3:
                    level = "🔴" if days_left == 0 else "🟡"
                    alerts.append(f"{level} 保單轉換 **{fund}** {deadline}（{days_left}天後）")
            except: pass
except Exception as e:
    alerts.append(f"⚠️ 保單讀取錯誤: {e}")

# ── 3. 待辦決策（未處理 >3 天） ──
try:
    decisions = BASE / "dashboard_decisions.json"
    if decisions.exists():
        data = json.loads(decisions.read_text(encoding="utf-8"))
        for entry in data.get("entries", []):
            if entry.get("status") == "pending":
                created = entry.get("logged_at", "")[:10]
                if created:
                    try:
                        days = (today - datetime.strptime(created, "%Y-%m-%d").date()).days
                        if days >= 3:
                            alerts.append(f"📋 待辦決策已過 {days} 天：_{entry.get('content','')[:50]}..._")
                    except: pass
except: pass

# ── 4. 記憶容量（從 memory_archiver.py 狀態） ──
# 此項由 06:45 cron 處理，此處跳過

# ── 輸出 ──
if alerts:
    msg = f"📌 **龍九主動提醒 — {today}**\n\n" + "\n".join(alerts[:8])
else:
    msg = f"✅ **無待辦提醒 — {today}**\n所有項目正常。"

print(msg)
tg_send(msg)
