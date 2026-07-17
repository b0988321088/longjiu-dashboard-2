"""
dividend_tracker.py
龍九控股 — 保單/ETF 配息與除息自動追蹤器
2026 下半年「千萬江山」核心標的配息基準日總表（Dragon 5 錨定）
"""

import json
import os
import re
from datetime import datetime, date
from typing import List, Dict

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
EVENT_FILE = os.path.join(DATA_DIR, "dividend_events.json")

# ========== 2026 下半年度配息基準日總表（截圖錨定） ==========
# 月初：摩根JPM | 月中：安聯收益成長/M&G入息 | 月底：安聯AI收益/貝萊德A10
# T+4 規則：舊有保單轉換申請須於基準日「前4個工作日」送出，才能參與當月配息
# 第一金新保單：閃電窗口，基準日前 2-3 天仍可發動
# 現金入帳：基準日後約 12 天
ANCHOR_DIVIDENDS = [
    # 6月（已過，保留供歷史參照）
    {"code": "JPM", "name": "摩根多重收益基金（FJ33）", "ex_date": "2026-06-08", "type": "insurance", "status": "done", "note": "6月月初站點"},
    {"code": "ALLIANZ", "name": "安聯收益成長基金（QL18610694/QL18488224）", "ex_date": "2026-06-12", "type": "insurance", "status": "done", "note": "6月月中站點1"},
    {"code": "M&G", "name": "M&G入息基金", "ex_date": "2026-06-19", "type": "insurance", "status": "done", "note": "6月月中站點2"},
    {"code": "A10", "name": "貝萊德世界科技A10", "ex_date": "2026-06-29", "type": "insurance", "status": "done", "note": "6月月底站點2"},
    # 7月（進行中）
    {"code": "JPM", "name": "摩根多重收益基金（FJ33）", "ex_date": "2026-07-07", "type": "insurance", "status": "waiting", "note": "7月月初站點；配息尚未入帳，預計 7/19 前後到帳（+12天）"},
    {"code": "ALLIANZ", "name": "安聯收益成長基金（QL18610694/QL18488224）", "ex_date": "2026-07-14", "type": "insurance", "status": "pending", "note": "7月月中站點1；T+4=7/08 最後申請日（已過）"},
    {"code": "M&G", "name": "M&G入息基金", "ex_date": "2026-07-17", "type": "insurance", "status": "pending", "note": "7月月中站點2；T+4=7/11 最後申請日"},
    {"code": "00984A", "name": "安聯台灣高息成長主動式ETF", "ex_date": "2026-07-14", "type": "etf", "status": "pending", "note": "7月ETF 除息；持有 10,000 股"},
    {"code": "A10", "name": "貝萊德世界科技A10", "ex_date": "2026-07-30", "type": "insurance", "status": "pending", "note": "7月月底站點2；T+4=7/24 最後申請日"},
    # 8月
    {"code": "JPM", "name": "摩根多重收益基金（FJ33）", "ex_date": "2026-08-07", "type": "insurance", "status": "future", "note": "8月月初站點"},
    {"code": "ALLIANZ", "name": "安聯收益成長基金", "ex_date": "2026-08-14", "type": "insurance", "status": "future", "note": "8月月中站點1；T+4=8/07"},
    {"code": "M&G", "name": "M&G入息基金", "ex_date": "2026-08-21", "type": "insurance", "status": "future", "note": "8月月中站點2；T+4=8/14"},
    {"code": "A10", "name": "貝萊德世界科技A10", "ex_date": "2026-08-28", "type": "insurance", "status": "future", "note": "8月月底站點2；T+4=8/21"},
    # 9月
    {"code": "JPM", "name": "摩根多重收益基金（FJ33）", "ex_date": "2026-09-07", "type": "insurance", "status": "future", "note": "9月月初站點"},
    {"code": "ALLIANZ", "name": "安聯收益成長基金", "ex_date": "2026-09-14", "type": "insurance", "status": "future", "note": "9月月中站點1"},
    {"code": "M&G", "name": "M&G入息基金", "ex_date": "2026-09-18", "type": "insurance", "status": "future", "note": "9月月中站點2"},
    {"code": "A10", "name": "貝萊德世界科技A10", "ex_date": "2026-09-29", "type": "insurance", "status": "future", "note": "9月月底站點2"},
    # 10月
    {"code": "JPM", "name": "摩根多重收益基金（FJ33）", "ex_date": "2026-10-07", "type": "insurance", "status": "future", "note": "10月月初站點"},
    {"code": "ALLIANZ", "name": "安聯收益成長基金", "ex_date": "2026-10-14", "type": "insurance", "status": "future", "note": "10月月中站點1"},
    {"code": "M&G", "name": "M&G入息基金", "ex_date": "2026-10-16", "type": "insurance", "status": "future", "note": "10月月中站點2"},
    {"code": "A10", "name": "貝萊德世界科技A10", "ex_date": "2026-10-29", "type": "insurance", "status": "future", "note": "10月月底站點2"},
    # 11月
    {"code": "JPM", "name": "摩根多重收益基金（FJ33）", "ex_date": "2026-11-09", "type": "insurance", "status": "future", "note": "11月月初站點"},
    {"code": "ALLIANZ", "name": "安聯收益成長基金", "ex_date": "2026-11-13", "type": "insurance", "status": "future", "note": "11月月中站點1"},
    {"code": "M&G", "name": "M&G入息基金", "ex_date": "2026-11-20", "type": "insurance", "status": "future", "note": "11月月中站點2"},
    {"code": "A10", "name": "貝萊德世界科技A10", "ex_date": "2026-11-27", "type": "insurance", "status": "future", "note": "11月月底站點2"},
    # 12月
    {"code": "JPM", "name": "摩根多重收益基金（FJ33）", "ex_date": "2026-12-07", "type": "insurance", "status": "future", "note": "12月月初站點"},
    {"code": "ALLIANZ", "name": "安聯收益成長基金", "ex_date": "2026-12-14", "type": "insurance", "status": "future", "note": "12月月中站點1"},
    {"code": "M&G", "name": "M&G入息基金", "ex_date": "2026-12-18", "type": "insurance", "status": "future", "note": "12月月中站點2"},
    {"code": "A10", "name": "貝萊德世界科技A10", "ex_date": "2026-12-30", "type": "insurance", "status": "future", "note": "12月月底站點2"},
]


# ========== 爬蟲：安聯投信公告 ==========
def fetch_allianz_announcements() -> List[Dict]:
    events: List[Dict] = []
    try:
        import urllib.request
        url = "https://tw.allianzgi.com/zh-tw/announcement/product-announcement"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        patterns = [
            r"配息.*?(\d{3,4}/\d{1,2}/\d{1,2})",
            r"除息.*?(\d{3,4}/\d{1,2}/\d{1,2})",
            r"(\d{3,4}/\d{1,2}/\d{1,2}).*?配息",
            r"(\d{3,4}/\d{1,2}/\d{1,2}).*?除息",
        ]
        found = set()
        for p in patterns:
            for m in re.finditer(p, html):
                raw = m.group(1)
                try:
                    dt = datetime.strptime(raw, "%Y/%m/%d").date()
                    found.add(dt)
                except ValueError:
                    pass
        for d in sorted(found):
            events.append({
                "code": "ALLIANZ_RAW", "name": "安聯投信公告（擷取）",
                "ex_date": d.isoformat(), "type": "insurance", "status": "pending",
                "note": f"安聯公告頁擷取日期 {d.isoformat()}",
            })
    except Exception:
        pass
    return events


# ========== 讀寫配息事件 ==========
def load_dividend_events() -> List[Dict]:
    if os.path.exists(EVENT_FILE):
        try:
            with open(EVENT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return list(ANCHOR_DIVIDENDS)


def save_dividend_events(events: List[Dict]):
    with open(EVENT_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


# ========== 主流程 ==========
def refresh_dividend_events(force_anchor: bool = False) -> List[Dict]:
    """
    合併靜態錨定 + 爬蟲結果。
    預設以 ANCHOR_DIVIDENDS 為主（已知基準日錨定），爬蟲結果作為補強。
    """
    merged = {e["ex_date"] + "|" + e["code"]: e for e in ANCHOR_DIVIDENDS}
    if not force_anchor:
        crawled = fetch_allianz_announcements()
        for e in crawled:
            merged[e["ex_date"] + "|" + e["code"]] = e
    events = list(merged.values())
    events.sort(key=lambda x: x.get("ex_date", ""))
    save_dividend_events(events)
    return events


def get_upcoming_dividends(days_ahead: int = 14) -> List[Dict]:
    """取得未來 N 天內的配息/除息事件"""
    events = load_dividend_events()
    today = date.today()
    upcoming = []
    for e in events:
        try:
            ex = datetime.strptime(e["ex_date"], "%Y-%m-%d").date()
            delta = (ex - today).days
            if 0 <= delta <= days_ahead:
                e["days_left"] = delta
                upcoming.append(e)
        except Exception:
            pass
    upcoming.sort(key=lambda x: x["days_left"])
    return upcoming


def get_dividend_alerts(days_ahead: int = 7) -> List[str]:
    """
    取得 T-x 除息提醒字串。
    供 full_monitor.py 直接使用。
    """
    upcoming = get_upcoming_dividends(days_ahead + 4)
    today = date.today()
    alerts: List[str] = []
    for e in upcoming[:8]:
        try:
            ex = datetime.strptime(e["ex_date"], "%Y-%m-%d").date()
            delta = (ex - today).days
            if delta < 0:
                continue
            label = "⚡" if delta <= 2 else "🔔"
            cash_date = ex.replace(day=min(ex.day + 12, 28))  # 粗略 +12 天
            alerts.append(
                f"{label} T-{delta} {e['code']} {e['name']} 基準日 {e['ex_date']} → 預估入帳 {cash_date} | {e.get('note','')}"
            )
        except Exception:
            pass
    return alerts if alerts else ["✅ 配息/除息：近期無需預警"]


def print_dividend_summary():
    """列印配息狀態摘要（CLI 用）"""
    events = load_dividend_events()
    today = date.today()
    print("=" * 70)
    print("龍九控股 — 配息/除息狀態追蹤")
    print(f"報告時間：{today.isoformat()}")
    print("=" * 70)
    for e in events:
        ex = datetime.strptime(e["ex_date"], "%Y-%m-%d").date()
        delta = (ex - today).days
        tag = ""
        if delta < 0:
            tag = "[已過期]"
        elif delta <= 2:
            tag = "[ imminent]"
        elif delta <= 14:
            tag = "[本週/月內]"
        print(f"{tag} {e['ex_date']} | {e['code']} {e['name']} | {e.get('status','')} | {e.get('note','')}")
    print("=" * 70)


if __name__ == "__main__":
    print("抓取最新配息事件...")
    events = refresh_dividend_events()
    print(f"已載入 {len(events)} 筆配息事件")
    print_dividend_summary()
