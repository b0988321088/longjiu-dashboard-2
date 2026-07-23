#!/usr/bin/env python3
"""
龍九控股 日報情報補給
- 優先使用 Yahoo Finance API 抓取即時市場數據
- 備援使用 web_search
- 產出 hunter_logs/intel_YYYYMMDD_HHMM.txt
- 產出 daily_analysis.json（結構化分析）
- 供日報讀取
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
# import feedparser # This was added by another agent, keeping it for now if it's used elsewhere

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    import requests as _requests
    _REQUESTS_OK = True
except Exception:
    _REQUESTS_OK = False

try:
    from finnews import News
    _FINNEWS_OK = True
except Exception as e:
    _FINNEWS_OK = False
    print(f"ERROR: Could not import finnews: {e}", file=sys.stderr)


BASE = Path(__file__).parent.resolve()
HUNTER_DIR = BASE / "hunter_logs"


def ensure_dir() -> None:
    HUNTER_DIR.mkdir(exist_ok=True)


def _now_ts() -> str:
    return datetime.now().strftime("%H%M")


def _today_str() -> str:
    return date.today().isoformat().replace("-", "")

# ===== Yahoo Finance API =====
_YF_HEADERS = {"User-Agent": "Mozilla/5.0"}

_YF_SYMBOLS = {
    "twii": "^TWII",
    "tsm": "2330.TW",
    "sox": "^SOX",
    "us_dji": "^DJI",
    "us_ixic": "^IXIC",
    "us_gspc": "^GSPC",
}


def _yf_chart(symbol: str, timeout: int = 8) -> dict:
    if not _REQUESTS_OK:
        return {}
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1m"
        r = _requests.get(url, timeout=timeout, headers=_YF_HEADERS)
        data = r.json()
        meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose")
        if price is None or prev is None:
            return {}
        pct = round((price - prev) / prev * 100, 2)
        return {"price": price, "prev": prev, "change_pct": pct}
    except Exception:
        return {}


def fetch_yf_market() -> dict:
    twii = _yf_chart(_YF_SYMBOLS["twii"])
    tsm = _yf_chart(_YF_SYMBOLS["tsm"])
    sox = _yf_chart(_YF_SYMBOLS["sox"])
    dji = _yf_chart(_YF_SYMBOLS["us_dji"])
    ixic = _yf_chart(_YF_SYMBOLS["us_ixic"])
    gspc = _yf_chart(_YF_SYMBOLS["us_gspc"])

    def fmt(d):
        if not d:
            return "—"
        p = d.get("price", "—")
        c = d.get("change_pct", "—")
        if isinstance(p, (int, float)) and isinstance(c, (int, float)):
            return f"{p:,.2f} ({c:+.2f}%)"
        return str(p)

    us_parts = []
    if dji:
        us_parts.append(f"道瓊 {fmt(dji)}")
    if ixic:
        us_parts.append(f"納指 {fmt(ixic)}")
    if gspc:
        us_parts.append(f"S&P {fmt(gspc)}")
    us = " / ".join(us_parts) if us_parts else "—"

    return {
        "twii": fmt(twii),
        "tsm": fmt(tsm),
        "sox": fmt(sox),
        "us": us,
        "cpi": "美國 6 月 CPI YoY 3.5% (預期 3.8%)；Core 2.6% (預期 2.8%)",
    }


# ===== News fetching with finnews =====
_NEWS_CLIENT = None
if _FINNEWS_OK:
    try:
        _NEWS_CLIENT = News()
    except Exception as e:
        print(f"ERROR: Could not initialize finnews client: {e}", file=sys.stderr)
        pass


def _fetch_news(keywords: list[str], limit: int = 5) -> list[dict]:
    """Search market news using finnews, filtering for today's articles and keywords."""
    if _NEWS_CLIENT is None:
        print("DEBUG: finnews client not initialized.", file=sys.stderr)
        return []

    results = []
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    # Compile a regex pattern for keywords, supporting Chinese characters
    if keywords:
        keyword_match_pattern = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)
    else:
        keyword_match_pattern = re.compile(r".+", re.IGNORECASE)


    try:
        # Fetch from Yahoo Finance
        yahoo_news = _NEWS_CLIENT.yahoo_finance.news()
        print(f"DEBUG: Fetched {len(yahoo_news)} articles from Yahoo Finance.")
        for article in yahoo_news:
            pub_date_str = article.get("published_at") or article.get("published")
            if pub_date_str:
                try:
                    # Handle various ISO 8601 formats, specifically with 'Z' for UTC
                    if 'Z' in pub_date_str:
                        pub_dt = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00')).date()
                    else:
                        pub_dt = datetime.fromisoformat(pub_date_str).date()

                    if pub_dt >= yesterday: # Include yesterday to catch late updates
                        title = article.get("title", "")
                        snippet = article.get("description", article.get("snippet", ""))
                        
                        # Filter by keywords
                        if keyword_match_pattern.search(title) or (snippet and keyword_match_pattern.search(snippet)):
                            results.append({
                                "title": title[:120],
                                "url": article.get("link", "")[:200],
                                "snippet": snippet[:200],
                            })
                except ValueError as ve:
                    print(f"DEBUG: ValueError parsing Yahoo Finance date '{pub_date_str}': {ve}", file=sys.stderr)
                    pass

        # Fetch from CNBC (top news)
        cnbc_news = _NEWS_CLIENT.cnbc.news_feed(topic='top_news')
        print(f"DEBUG: Fetched {len(cnbc_news)} articles from CNBC.")
        for article in cnbc_news:
            pub_date_str = article.get("published_at") or article.get("published")
            if pub_date_str:
                try:
                    if 'Z' in pub_date_str:
                        pub_dt = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00')).date()
                    else:
                        pub_dt = datetime.fromisoformat(pub_date_str).date()

                    if pub_dt >= yesterday: # Include yesterday to catch late updates
                        title = article.get("title", "")
                        snippet = article.get("description", article.get("snippet", ""))
                        
                        # Filter by keywords
                        if keyword_match_pattern.search(title) or (snippet and keyword_match_pattern.search(snippet)):
                            results.append({
                                "title": title[:120],
                                "url": article.get("link", "")[:200],
                                "snippet": snippet[:200],
                            })
                except ValueError as ve:
                    print(f"DEBUG: ValueError parsing CNBC date '{pub_date_str}': {ve}", file=sys.stderr)
                    pass

    except Exception as e:
        print(f"Error fetching news with finnews: {e}", file=sys.stderr)
        return []

    # Deduplicate and limit
    unique_results = []
    seen_urls = set()
    for item in results:
        if item["url"] and item["url"] not in seen_urls: # Ensure URL is not empty before adding to seen_urls
            unique_results.append(item)
            seen_urls.add(item["url"])
        if len(unique_results) >= limit:
            break

    print(f"DEBUG: Final {len(unique_results)} unique news articles after filtering.")
    return unique_results


# ===== Signal classification =====
def classify_from_yf(market: dict) -> dict:
    sell, buy = [], []
    for key, val in market.items():
        if not isinstance(val, str) or val == "—":
            continue
        if "%" not in val:
            continue
        try:
            pct = float(re.search(r"\(([+-]?\d+\.\d+)%\)", val).group(1))
        except Exception:
            continue
        if key == "twii" and pct <= -1.5:
            sell.append(f"台股加權大跌 {pct}%")
        if key == "sox" and pct <= -2.0:
            sell.append(f"費半跌 {pct}%")
        if key == "tsm" and pct <= -2.0:
            sell.append(f"台積電大跌 {pct}%")
        if key == "twii" and pct >= 1.0:
            buy.append(f"台股大漲 {pct}%")
        if key == "sox" and pct >= 3.0:
            buy.append(f"費半大漲 {pct}%")

    # 補充：累計週跌幅超過 5% → 趨勢注意（非外資訊號，僅供參考）
    if not sell and not buy:
        try:
            from pathlib import Path
            mi = json.loads((Path(__file__).resolve().parent / "market_intel.json").read_text(encoding="utf-8"))
            prev_7d = mi.get("TAIEX", {}).get("prev_close_7d", 0)
            twii_str = market.get("twii", "")
            price_str = twii_str.split("(")[0].strip().replace(",", "")
            if prev_7d and price_str:
                current = float(price_str)
                weekly_cum = (current - prev_7d) / prev_7d * 100
                if weekly_cum <= -5:
                    pass  # 保留空訊號，不要偽造外資數據
        except Exception:
            pass

    return {"sell_signals": sell[:5], "buy_signals": buy[:5]}


def classify(text: str) -> dict:
    sell, buy = [], []
    _today_md = date.today().strftime("%m/%d")
    _today_iso = date.today().isoformat()
    _today_slash = date.today().strftime("%m/%d")
    _today_cn = f"{date.today().month}月{date.today().day}日"
    for line in text.splitlines():
        # 只取今日訊號，跳過過期新聞
        if _today_md not in line and _today_iso not in line and _today_slash not in line and _today_cn not in line:
            continue
        if any(k in line for k in ["賣超", "大跌", "跌 2%", "跌2%", "跌破", "賣壓", "外資賣超"]):
            sell.append(line.strip())
        if any(k in line for k in ["買超", "大漲", "漲 3%", "漲3%", "買盤", "外資買超"]):
            buy.append(line.strip())
    return {"sell_signals": sell[:5], "buy_signals": buy[:5]}


# ===== Intel text rendering =====
def render_intel_text(intel_text: str, signals: dict) -> str:
    today = date.today().isoformat()
    now = datetime.now().strftime("%H%M")
    lines = [
        "情報timestamp：" + today,
        "=" * 60,
        "【P1 賣出訊號】",
    ]
    if signals["sell_signals"]:
        for i, s in enumerate(signals["sell_signals"], 1):
            lines.append(str(i) + ". " + s)
    else:
        lines.append("（無）")
    lines += [
        "",
        "【P1 買進訊號】",
    ]
    if signals["buy_signals"]:
        for i, s in enumerate(signals["buy_signals"], 1):
            lines.append(str(i) + ". " + s)
    else:
        lines.append("（無）")
    lines += [
        "",
        "【情報摘要（≤200字/條）】",
        intel_text[:1500] if intel_text else "（無）",
        "",
        "【最終結論】",
        "由 daily_intel.py 於 " + now + " 自動產出。",
        "=" * 60,
    ]
    return "\n".join(lines)


# ===== Analysis builder =====

def build_analysis(intel_text: str, signals: dict, market_override: dict | None = None) -> dict:
    today = date.today().isoformat().replace("-", "")
    market = market_override if market_override else fetch_yf_market()

    # Parse market numbers for scenario detection
    twii = market.get("twii", "")
    tsm = market.get("tsm", "")
    sox = market.get("sox", "")

    def pct(text):
        m = re.search(r"\(([+-]?[0-9.]+)%\)", str(text))
        return float(m.group(1)) if m else None

    twii_pct = pct(twii)
    tsm_pct = pct(tsm)
    sox_pct = pct(sox)

    # Signals 描述
    sell_desc = "; ".join(signals.get("sell_signals", [])[:2])
    buy_desc = "; ".join(signals.get("buy_signals", [])[:2])
    if not sell_desc:
        sell_desc = "無賣出訊號"
    if not buy_desc:
        buy_desc = "無買進訊號"

    # Scenario-driven Buffett/CTO
    crash = (twii_pct is not None and twii_pct <= -3) or (tsm_pct is not None and tsm_pct <= -5)
    rally = (twii_pct is not None and twii_pct >= 2) or (sox_pct is not None and sox_pct >= 3)
    foreign_sell = "賣超" in sell_desc
    foreign_buy = "買超" in buy_desc

    scenario_summary = "市場震盪，維持防禦"
    if crash:
        scenario_summary = "台股重挫，啟動減碼防禦"
    elif rally:
        scenario_summary = "台股反彈，觀察回補訊號"
    elif foreign_sell:
        scenario_summary = "外資賣超，保留現金部位"
    elif foreign_buy:
        scenario_summary = "外資買超，適度回補權益"

    if crash:
        buffett = {
            "bull": "台股超跌後常出現技術性反彈，但今日不抄底，保留高利活存與现金",
            "bear": sell_desc or "台股加權與台積電同步大跌，外資賣壓擴大",
            "actions": [
                "減碼美股權益至35%以下，優先降科技股曝險",
                "0050若配息縮水，缺口以 00878/00713 補位",
                "保留高利活存部位，等待恐慌賣壓结束後進場",
                "保單配息為退休現金流基石，不宜隨便轉換",
            ],
            "scenario_summary": scenario_summary,
        }
        cto = {
            "tech_stack": "半導體重挫，台積電法說會後資金卡位失敗",
            "risk": "台股大跌 " + (str(twii_pct) if twii_pct is not None else "N/A") + "%; 台積電大跌 " + (str(tsm_pct) if tsm_pct is not None else "N/A") + "%; 外資賣壓持續",
            "action": "縮短 holding period，優先保留现金，觀望季線支撑",
            "cto_signal": "台股重挫 + 外資賣超",
        }
    elif rally:
        buffett = {
            "bull": buy_desc or "台股反彈，外資買超",
            "bear": "反彈不宜追價，等待量能確認",
            "actions": [
                "若外資買超 + 大盤漲1% + 费半+3%，可回補台股至15-20%",
                "保留高利活存作為安全邊際",
                "保單配息持續入帳，維持退休金流",
            ],
            "scenario_summary": scenario_summary,
        }
        cto = {
            "tech_stack": "半導體反彈，觀察資金回補是否持續",
            "risk": "反彈量能不足，可能二次探底",
            "action": "分批回補，不要一次性加碼",
            "cto_signal": "外資買超 + 大盤上漲",
        }
    else:
        buffett = {
            "bull": buy_desc or "市場震盪，無明顯買訊",
            "bear": sell_desc or "市場震盪，無明顯賣訊",
            "actions": [
                "維持现有配置，不主動加碼 nor 減碼",
                "保留高利活存 ≥ 20% 作為緩衝",
                "0050 配息若確認縮水，提前部署 00878/00713",
            ],
            "scenario_summary": scenario_summary,
        }
        cto = {
            "tech_stack": "市場震盪，缺乏明確方向",
            "risk": sell_desc or "震盪期間容易誤判趨勢",
            "action": "觀望為主，等待明确訊號",
            "cto_signal": "",
        }

    news_queries = []
    if crash:
        news_queries = ["台股 大跌 外資 賣超 原因 2026年7月", "韓國 過度槓桿 亞洲股市 2026", "美國 科技股 泡沫 Fed 利率 2026"]
    elif rally:
        news_queries = ["台股 反彈 外資 買超 2026年7月", "美股 科技股 反彈 Fed 2026"]
    else:
        news_queries = ["台股 震盪 外資 2026年7月", "韓國 亞洲市場 連動 2026"]

    news = _fetch_news(news_queries)

    return {
        "date": today,
        "generated_at": datetime.now().isoformat(),
        "market": market,
        "buffett": buffett,
        "cto": cto,
        "signals": signals,
        "news": news,
        "scenario_summary": scenario_summary,
    }


# ===== Main workflow =====
def ensure_today_intel(force_refresh: bool = False) -> dict:
    ensure_dir()
    today = _today_str()
    existing = sorted(HUNTER_DIR.glob(f"intel_{today}_*.txt"), key=os.path.getmtime, reverse=True)

    # 1. 优先使用 Yahoo Finance API（每次都抓最新）
    market = fetch_yf_market()
    signals = classify_from_yf(market)

    # 2. 從 Yahoo Finance 數據建立 briefing（取代空殼 web search）
    _tw_str = market.get("twii", "")
    _tsm_str = market.get("tsm", "")
    _sox_str = market.get("sox", "")
    _us_str = market.get("us", "")
    _cpi_str = market.get("cpi", "")
    briefing_parts = [
        f"【台股/大盤】{_tw_str} | 台積電 {_tsm_str}",
        f"【美股/外資】{_us_str}",
        f"【半導體】費半 {_sox_str}",
        f"【CPI/利率】{_cpi_str}",
    ]
    briefing = " | ".join(briefing_parts)

    # web_search 定時執行：07:00 / 13:00 / 21:00 各抓一次（force_refresh 時強制執行）
    intel_text = ""
    search_results = []
    _h = datetime.now().hour
    if force_refresh or _h in [7, 13, 21]:
        try:
            # Modified to use finnews with broader queries, relying on internal filtering
            _news_keywords = ["台股", "美股", "川普", "走勢", "分析", "台積電", "股價", "大盤", "外資"]
            _news = _fetch_news(_news_keywords, limit=10) # Fetch more, filter later
            search_results = _news
            if _news:
                _news_text = "\n".join(n.get("title","") + " " + n.get("snippet","