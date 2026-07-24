"""Google Calendar 每日同步 — 純腳本版（0 Token）
讀取 Company_Ledger.md 固定排程，寫入 Google Calendar"""

import json, os, re
from datetime import date, datetime, timedelta
from pathlib import Path
from logging_config import get_logger
logger = get_logger("calendar_sync")
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

BASE = Path(__file__).resolve().parent
TOKEN_PATH = Path(os.path.expanduser("~/AppData/Local/hermes/google_token.json"))
LEDGER = BASE / "Company_Ledger.md"

SCOPES = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/calendar.events"]

def delete_existing_event(service, summary: str, event_date: str):
    """刪除相同標題+日期的舊事件，避免重複"""
    try:
        events = service.events().list(
            calendarId='primary',
            timeMin=f"{event_date}T00:00:00Z",
            timeMax=f"{event_date}T23:59:59Z",
            q=summary
        ).execute()
        for item in events.get('items', []):
            if item['summary'] == summary:
                service.events().delete(calendarId='primary', eventId=item['id']).execute()
                logger.info(f"  刪除舊事件: {summary} ({event_date})")
    except Exception as e:
        logger.warning(f"  刪除事件失敗: {e}")

def load_creds():
    if not TOKEN_PATH.exists():
        logger.error("❌ 無 Google token")
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
    
    # 每月固定收支（當月及未來3個月）
    for offset in range(0, 4):
        m = today.month + offset
        y = today.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        # 1號：大義街店面 24,000
        events.append({"summary": "🏠 大義街店面房租入帳 $24,000", "start": date(y, m, 1).isoformat(), "end": date(y, m, 1).isoformat()})
        # 6號：台電薪資
        events.append({"summary": "💰 台電薪資入帳 $43,144", "start": date(y, m, 6).isoformat(), "end": date(y, m, 6).isoformat()})
        # 20號：洲際W房租
        events.append({"summary": "🏠 洲際W房租入帳 $33,000", "start": date(y, m, 20).isoformat(), "end": date(y, m, 20).isoformat()})
        # 25號：大義街二三樓房租＋管理費
        events.append({"summary": "🏠 大義街二三樓房租 $21,000+$2,100 入帳", "start": date(y, m, 25).isoformat(), "end": date(y, m, 25).isoformat()})
    
    for summary, dates in fixed:
        if any(d >= today for d in dates):
            events.append({"summary": summary, "start": dates[0].isoformat(), "end": dates[-1].isoformat()})
    
    # 信用卡繳款（從 MB 最新帳單 CSV 讀取）
    cc = []
    try:
        _mb_dir = Path(__file__).resolve().parent / "moneybook"
        _mb_bill = sorted(_mb_dir.glob("*帳單*.csv"), reverse=True)
        if _mb_bill:
            import csv
            _cc_map = {"玉山銀行": ("玉山", 22), "台新銀行": ("台新", 27), "永豐銀行": ("永豐", 29), "台北富邦": ("富邦", 3)}
            _latest = {}
            with open(_mb_bill[0], "r", encoding="utf-8-sig") as _f:
                for _r in csv.DictReader(_f):
                    _bank = _r.get("金融機構","")
                    if _bank in _cc_map:
                        _due = _r.get("繳費截止日","")
                        _amt = float(_r.get("帳單金額",0))
                        if _bank not in _latest or _due > _latest[_bank][0]:
                            _latest[_bank] = (_due, int(_amt))
            for _bank, (_, _amt) in _latest.items():
                if _amt > 0:
                    _name, _day = _cc_map[_bank]
                    cc.append((f"{_name} {_amt:,}", _day))
    except: pass
    if not cc:
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
    # 先刪舊的（精確比對標題+日期），再新增
    delete_existing_event(service, ev["summary"], ev["start"])
    body = {
        "summary": ev["summary"],
        "start": {"date": ev["start"]},
        "end": {"date": ev["end"]},
    }
    service.events().insert(calendarId="primary", body=body).execute()
    created += 1

logger.info(f"✅ Calendar 同步完成：新增 {created} 個行程")
