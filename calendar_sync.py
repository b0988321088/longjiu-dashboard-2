"""Google Calendar 每日同步 — 純腳本版（0 Token）
讀取 Company_Ledger.md 固定排程，寫入 Google Calendar"""

import json, os, re
from datetime import date, datetime, timedelta
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

BASE = Path(__file__).resolve().parent
TOKEN_PATH = Path(os.path.expanduser("~/AppData/Local/hermes/google_token.json"))
LEDGER = BASE / "Company_Ledger.md"

SCOPES = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/calendar.events"]

def load_creds():
    if not TOKEN_PATH.exists():
        print("❌ 無 Google token")
        return None
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds

def parse_events(text: str):
    """從 Company_Ledger.md 解析固定行程"""
    events = []
    today = date.today()
    
    # 固定行程（人工定義）
    fixed = [
        ("峨眉初驗", (date(2026, 7, 29), date(2026, 7, 30))),
        ("Notion 訂閱扣款 US$12", (date(2026, 8, 14), date(2026, 8, 14))),
    ]
    plus_30 = [
        ("大義街23樓房租 + 管理費", (today.replace(day=min(today.day + 30, 28)),)),
    ]
    
    for summary, dates in fixed:
        if any(d >= today for d in dates):
            events.append({"summary": summary, "start": dates[0].isoformat(), "end": dates[-1].isoformat()})
    
    # 信用卡繳款（每月固定日）
    cc = [("玉山 3,176", 22), ("台新 1,000", 27)]
    for name, day in cc:
        d = today.replace(day=min(day, 28))
        if d >= today:
            events.append({"summary": f"💳 {name} 繳款截止", "start": d.isoformat(), "end": d.isoformat()})
    
    return events

creds = load_creds()
if not creds:
    exit(1)

service = build("calendar", "v3", credentials=creds)
events = parse_events(LEDGER.read_text("utf-8") if LEDGER.exists() else "")

created = 0
for ev in events:
    exists = service.events().list(calendarId="primary", q=ev["summary"], timeMin=f"{ev['start']}T00:00:00Z",
                                    timeMax=f"{ev['end']}T23:59:59Z", maxResults=5).execute()
    if not exists.get("items"):
        body = {
            "summary": ev["summary"],
            "start": {"date": ev["start"]},
            "end": {"date": ev["end"]},
        }
        service.events().insert(calendarId="primary", body=body).execute()
        created += 1

print(f"✅ Calendar 同步完成：新增 {created} 個行程")
