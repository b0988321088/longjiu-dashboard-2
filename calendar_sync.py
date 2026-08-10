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

SCOPES = ["https://www.googleapis.com/auth/calendar"]  # calendar 是 calendar.events 的超集（2026-08-10 修正：原同時列 calendar.events 導致備份 token refresh 時 invalid_scope）

def load_creds():
    if not TOKEN_PATH.exists():
        logger.error("❌ 無 Google token")
        return None
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        # 不寫回 token 檔：避免狹窄 scope 覆寫其他權限（2026-08-02 修正）
    return creds

def parse_events(text: str):
    """從 Company_Ledger.md 解析固定行程"""
    events = []
    today = date.today()
    
    # 固定行程（人工定義）— 2026-08-06：移除過期/已被 schedule_events.json 動態涵蓋的寫死項
    # （國泰8/4、T+4 截止等已由 schedule_events.json 統一同步，避免再次過期）
    fixed = [
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
        # 1號：龍七動態月報自動產出
        events.append({"summary": "📊 龍七動態月報自動產出（09:00）", "start": date(y, m, 1).isoformat(), "end": date(y, m, 1).isoformat()})
        # 5號：女友還款 6,000
        events.append({"summary": "🔄 女友還款（每月6,000）", "start": date(y, m, 5).isoformat(), "end": date(y, m, 5).isoformat()})
        # 6號：台電薪資
        events.append({"summary": "💰 台電薪資入帳 $39,727", "start": date(y, m, 6).isoformat(), "end": date(y, m, 6).isoformat()})
        # 20號：洲際W房租
        events.append({"summary": "🏠 洲際W房租入帳 $33,000", "start": date(y, m, 20).isoformat(), "end": date(y, m, 20).isoformat()})
        # 25號：大義街二三樓房租＋管理費
        events.append({"summary": "🏠 大義街二三樓房租 $21,000+$2,100 入帳", "start": date(y, m, 25).isoformat(), "end": date(y, m, 25).isoformat()})

    # 每週六再平衡評估 + 每週日動態週報（未來8週）
    _sat = today
    while _sat.weekday() != 5:
        _sat += timedelta(days=1)
    for _i in range(8):
        _d = _sat + timedelta(days=7 * _i)
        events.append({"summary": "📊 每週六再平衡評估（09:00）", "start": _d.isoformat(), "end": _d.isoformat()})
        _sun = _d + timedelta(days=1)
        events.append({"summary": "🧠 動態自我檢討週報產出（19:00）", "start": _sun.isoformat(), "end": _sun.isoformat()})
    
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

def sync():
    creds = load_creds()
    if not creds:
        return
    service = build("calendar", "v3", credentials=creds)
    events = parse_events(LEDGER.read_text("utf-8") if LEDGER.exists() else "")

    # 2026-08-06：追加 schedule_events.json 動態事件（今日~+30天），
    # 忠德驗收 / 8/15 撥款 / T+4 截止 / 房租等自動同步 GCal，不再手動維護 fixed 清單
    # ⚠️ 2026-08-10 修正：一律讀 longjiu_system 真值（scripts 副本會過期，曾導致 8/15 撥款事件漏同步）
    try:
        _sev_path = Path(os.path.expanduser("~/Desktop/longjiu_system/schedule_events.json"))
        if not _sev_path.exists():
            _sev_path = Path(__file__).resolve().parent / "schedule_events.json"  # 兜底
        _sev = json.loads(_sev_path.read_text(encoding="utf-8"))
        _today_s = date.today().isoformat()
        _end30 = (date.today() + timedelta(days=30)).isoformat()
        def _norm(s):
            return re.sub(r'[\W_]+', '', s)
        # 2026-08-10 修正：改「日期+類別」去重 — 精確標題比對抓不到同義重複
        # （例：fixed 的「🏠 大義街二三樓房租 $21,000+$2,100 入帳」vs schedule 的「大義街二三樓房租+管理費入帳」）
        _CAT_RULES = [
            ("大義街二三樓", "rent_23f"), ("二三樓房租", "rent_23f"), ("大義街店面", "rent_shop"),
            ("洲際W", "rent_w"), ("台電薪資", "salary"), ("女友還款", "gf_repay"),
            ("動態月報", "monthly_report"), ("再平衡評估", "rebalance"), ("動態自我檢討週報", "weekly_review"),
            ("繳款截止", "cc_pay"), ("每月租金總對帳", "rent_audit"), ("T+4 轉換", "t4_conv"),
            ("國泰核貸", "cathay"), ("忠德驗收", "zhongde"), ("地政拿件", "land_office"),
        ]
        def _cat(s):
            for kw, c in _CAT_RULES:
                if kw in s:
                    return c
            return None
        _seen = {(_cat(e["summary"]), e["start"]) for e in events if _cat(e["summary"])}
        for _e in _sev:
            _d = _e.get("date", "")
            if _d == "待處理" or not (_today_s <= _d <= _end30):
                continue
            _item = _e.get("item", "")
            _amt = _e.get("amount", "")
            _status = _e.get("status", "")
            # 2026-08-10 修正：跳過「📋 節日」狀態（Google 內建假日行事曆已有，自建=重複顯示）
            if "節日" in _status:
                continue
            _title = f"{_item} {_amt}".strip() if _amt else _item
            _c = _cat(_title)
            if _c and (_c, _d) in _seen:
                continue  # 同日期同類別已有事件（fixed 優先），跳過避免重複
            events.append({
                "summary": _title,
                "start": _d,
                "end": (datetime.strptime(_d, "%Y-%m-%d") + timedelta(days=1)).date().isoformat(),
            })
            if _c:
                _seen.add((_c, _d))
    except Exception as _se:
        logger.warning(f'  schedule_events 動態事件讀取失敗: {_se}')

    # 清空所有舊系統事件（依標記 + 關鍵字雙重清掃）
    import logging
    logger = logging.getLogger('calendar_sync')
    _CLEAN_KEYWORDS = ['房租', '大義街', '洲際W', '台電薪資', '管理費', '繳款截止', '[calendar_sync]', '動態月報', '再平衡評估', '動態自我檢討週報', '女友還款', '國泰核貸', 'T+4 轉換截止', '忠德驗收', '地政拿件', '大雪山', '每月租金總對帳']
    try:
        page_token = None
        deleted = 0
        while True:
            _evs = service.events().list(calendarId='primary', pageToken=page_token, maxResults=250).execute()
            for item in _evs.get('items', []):
                desc = item.get('description','')
                summary = item.get('summary','')
                if '[calendar_sync]' in desc or any(kw in summary for kw in _CLEAN_KEYWORDS):
                    service.events().delete(calendarId='primary', eventId=item['id']).execute()
                    deleted += 1
            page_token = _evs.get('nextPageToken')
            if not page_token:
                break
        if deleted:
            logger.info(f'  刪除 {deleted} 個舊系統事件')
    except Exception as e:
        logger.warning(f'  刪除系統事件失敗: {e}')

    created = 0
    for ev in events:
        body = {
            "summary": ev["summary"],
            "description": "[calendar_sync]",
            "start": {"date": ev["start"]},
            "end": {"date": ev["end"]},
        }
        service.events().insert(calendarId="primary", body=body).execute()
        created += 1

    logger.info(f"✅ Calendar 同步完成：新增 {created} 個行程")

    # 反向：從 GCal 讀取用戶手動事件，合併回 schedule_events.json（longjiu_system 真值）
    try:
        _pulled = pull_calendar_events(service)
        if _pulled:
            _schedule_path = Path(os.path.expanduser("~/Desktop/longjiu_system/schedule_events.json"))
            if not _schedule_path.exists():
                _schedule_path = Path(__file__).resolve().parent / "schedule_events.json"
            _existing = json.loads(_schedule_path.read_text(encoding="utf-8")) if _schedule_path.exists() else []
            _existing_items = {(e.get("date"), e.get("item")) for e in _existing}
            _added = 0
            for _ev in _pulled:
                if (_ev["date"], _ev["item"]) not in _existing_items:
                    _existing.append(_ev)
                    _existing_items.add((_ev["date"], _ev["item"]))
                    _added += 1
            if _added:
                _schedule_path.write_text(json.dumps(_existing, ensure_ascii=False, indent=2), encoding="utf-8")
                logger.info(f"  合併行事曆手動事件 {_added} 筆 → schedule_events.json")
    except Exception as e:
        logger.warning(f'  合併行事曆事件失敗: {e}')


def pull_calendar_events(service) -> list:
    """從 Google Calendar 讀取用戶手動建立的事件（非 [calendar_sync] 標記）

    回傳 [{date, item, amount, status}]，供 schedule_events.json 合併
    """
    import logging
    logger = logging.getLogger('calendar_sync')
    events_out = []
    try:
        page_token = None
        while True:
            _evs = service.events().list(calendarId='primary', pageToken=page_token, maxResults=250).execute()
            for item in _evs.get('items', []):
                desc = item.get('description', '')
                summary = item.get('summary', '')
                # 跳過系統同步事件與重複關鍵字
                if '[calendar_sync]' in desc:
                    continue
                start = item.get('start', {}).get('date') or item.get('start', {}).get('dateTime', '')
                if not start:
                    continue
                date_only = str(start)[:10]
                if date_only < '2026-07-01':
                    continue
                events_out.append({
                    "date": date_only,
                    "item": summary.strip(),
                    "amount": "",
                    "status": "📋 行程",
                })
            page_token = _evs.get('nextPageToken')
            if not page_token:
                break
    except Exception as e:
        logger.warning(f'  讀取行事曆失敗: {e}')
    return events_out

if __name__ == "__main__":
    sync()
