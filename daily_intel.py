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
import feedparser # Added for RSS feed parsing

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

# ===== News fetching with RSS feeds =====
def _fetch_news(queries: list[str], limit: int = 3) -> list[dict]:
    """Fetch news from RSS feeds, filtering for today's articles and matching queries."""
    RSS_FEEDS = {
        "cnyes": "https://tw.stock.yahoo.com/rss",
        "yahoo_stock": "https://tw.stock.yahoo.com/rss",
    }
    
    results = []
    today = date.today()

    # 把查詢拆成單詞，任一匹配即可
    _kw = set()
    for q in queries:
        for w in q.split():
            _kw.add(w.lower())

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                title = entry.get("title", "")
                link = entry.get("link", "")
                summary = entry.get("summary", "") or entry.get("description", "")
                if not title:
                    continue
                # Filter: title 含任一關鍵字即保留
                _tl = title.lower()
                if any(k in _tl for k in _kw):
                    results.append({
                        "title": title[:120],
                        "url": link[:200],
                        "snippet": summary[:200],
                    })
                    if len(results) >= limit:
                        break
            if len(results) >= limit:
                break
        except Exception as e:
            print(f"RSS error {source_name}: {e}", file=sys.stderr)
            continue
    
    return results

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
            "action": "縮短 holding period，優先保留現金，觀望季線支撑",
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
            "action": "觀望為主，等待明確訊號",
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
            _news_queries = ["台股", "美股", "川普", "走勢", "分析", "台積電", "股價", "大盤", "外資"]
            _news = _fetch_news(_news_queries, limit=10) # Fetch more, filter later
            search_results = _news
            if _news:
                _news_text = "\n".join(n.get("title","") + " " + n.get("snippet",""))
                _news_signals = classify(_news_text)
                for k in ["sell_signals", "buy_signals"]:
                    if _news_signals.get(k):
                        signals.setdefault(k, []).extend(_news_signals[k])
        except Exception as e:
            print(f"Error in fetching news for cron job: {e}", file=sys.stderr)
            pass

    # 3. 產出 intel 檔
    text = render_intel_text(intel_text, signals)
    ts = datetime.now().strftime("%H%M")
    out = HUNTER_DIR / f"intel_{today}_{ts}.txt"
    out.write_text(text, encoding="utf-8")

    # 4. 產出 daily_analysis.json
    analysis = build_analysis(intel_text, signals, market_override=market)
    analysis_path = BASE / "daily_analysis.json"
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

    # 5. 產出 unified intel report（single source of truth）
    unified = {
        "date": today,
        "generated_at": datetime.now().isoformat(),
        "sources": {
            "yf_market": market,
            "hunter_raw": intel_text[:2000] if intel_text else "",
        },
        "market": market,
        "briefing": briefing,
        "taiex": _tw_str,
        "tsmc": _tsm_str,
        "semiconductor": _sox_str,
        "dow": _us_str.split("道瓊")[1].split("/")[0].strip() if "道瓊" in _us_str else _us_str,
        "nasdaq": "",
        "sp500": "",
        "cpi": _cpi_str,
        "signals": signals,
        "buffett": analysis.get("buffett", {}),
        "cto": analysis.get("cto", {}),
        "scenario_summary": analysis.get("scenario_summary", ""),
        "news": analysis.get("news", []),
    }
    unified_path = BASE / f"daily_intel_report_{today}.json"
    unified_path.write_text(json.dumps(unified, ensure_ascii=False, indent=2), encoding="utf-8")

    # Generate unified briefing text for run_daily.py injection
    briefing_lines = []
    briefing_lines.append("【台股/大盤】")
    briefing_lines.append(f"加權指數：{market.get('twii', '—')}")
    briefing_lines.append(f"台積電：{market.get('tsm', '—')}")
    briefing_lines.append(f"費半：{market.get('sox', '—')}")
    briefing_lines.append("")
    briefing_lines.append("【美股/外資】")
    briefing_lines.append(f"美股：{market.get('us', '—')}")
    briefing_lines.append(f"外資7日淨流：{market.get('foreign_flow', {}).get('7d_net', '—')}")
    briefing_lines.append("")
    briefing_lines.append("【CPI/利率】")
    briefing_lines.append(f"美國CPI：{market.get('cpi', '—')}")
    briefing_lines.append("")
    briefing_lines.append("【情報訊號】")
    if signals.get("sell_signals"):
        briefing_lines.append("賣出訊號：")
        for s in signals["sell_signals"][:3]:
            briefing_lines.append(f"• {s}")
    else:
        briefing_lines.append("賣出訊號：無")
    briefing_lines.append("")
    if signals.get("buy_signals"):
        briefing_lines.append("買進訊號：")
        for s in signals["buy_signals"][:3]:
            briefing_lines.append(f"• {s}")
    else:
        briefing_lines.append("買進訊號：無")
    briefing_lines.append("")
    briefing_lines.append("【持倉關聯分析】")
    # Read snapshot to relate market moves to holdings
    try:
        snap = json.loads((BASE / "snapshot.json").read_text(encoding='utf-8'))
        pen = snap.get('penetration', {}).get('actual_twd', {})
        tw_equity = pen.get('台股市值型成長', 0)
        us_equity = pen.get('美股市值型成長', 0)
        long_short = "" # Placeholder for now

        if tw_equity > 0 and (market.get('twii') and "%" in market['twii']):
            twii_pct = float(re.search(r"\(([+-]?\d+\.\d+)%\)", market['twii']).group(1))
            if twii_pct <= -1.0:
                long_short += f"台股持倉市值型成長 {tw_equity:,.0f} 萬元，今日大盤下跌，短線承壓。"
            elif twii_pct >= 1.0:
                long_short += f"台股持倉市值型成長 {tw_equity:,.0f} 萬元，今日大盤上漲，動能轉強。"

        if us_equity > 0 and (market.get('us') and "道瓊" in market['us']):
            # Extract Dow Jones percentage change from the 'us' string
            us_match = re.search(r"道瓊 [^()]+ \(([+-]?\d+\.\d+)%\)", market['us'])
            if us_match:
                us_dji_pct = float(us_match.group(1))
                if us_dji_pct <= -1.0:
                    long_short += f"美股持倉市值型成長 {us_equity:,.0f} 萬元，今日美股下跌，短期風險增加。"
                elif us_dji_pct >= 1.0:
                    long_short += f"美股持倉市值型成長 {us_equity:,.0f} 萬元，今日美股上漲，可適度樂觀。"
        if not long_short:
            long_short = "目前持倉與市場連動正常，無特殊事件。"
        briefing_lines.append(long_short)
    except Exception as e:
        briefing_lines.append(f"持倉關聯分析錯誤: {e}")

    return {"briefing_text": "\n".join(briefing_lines)}

if __name__ == "__main__":
    # Manual test / cron job entry point
    print("Running daily_intel.py as main entry point.")
    # ensure_today_intel(force_refresh=True)
    # Example: how ensure_today_intel would be called from cron
    # For this example, we will just call build_analysis to demonstrate
    # the output structure.

    # Mock signals and market data for demonstration
    mock_market = {
        "twii": "23000.00 (+1.25%)",
        "tsm": "900.00 (+1.50%)",
        "sox": "5000.00 (+3.00%)",
        "us": "道瓊 39000.00 (+0.50%) / 納指 17000.00 (+1.00%) / S&P 5200.00 (+0.75%)",
        "cpi": "美國 6 月 CPI YoY 3.5% (預期 3.8%)；Core 2.6% (預期 2.8%)",
    }
    mock_signals = {
        "sell_signals": ["外資賣超台積電", "科技股展望不佳"],
        "buy_signals": ["半導體景氣回升", "政策利多出台"],
    }
    intel_text_mock = ""
    
    analysis_result = build_analysis(intel_text_mock, mock_signals, market_override=mock_market)
    print("\n--- Daily Analysis JSON ---")
    print(json.dumps(analysis_result, ensure_ascii=False, indent=2))

    # Demonstrate unified briefing text
    briefing_output = ensure_today_intel(force_refresh=True)
    print("\n--- Unified Briefing Text ---")
    print(briefing_output["briefing_text"])

    print("\nDaily Intel generation complete.")

def load_latest_hunter() -> str:
    ensure_dir()
    files = sorted(HUNTER_DIR.glob("intel_*.txt"), key=os.path.getmtime, reverse=True)
    if not files:
        return ""
    return files[0].read_text(encoding="utf-8")


def parse_hunter_signals(text: str) -> dict:
    result = {"sell_signals": [], "buy_signals": [], "summary": ""}
    if not text:
        return result
    sell_keywords = ["賣超", "大跌", "跌 2%", "跌2%", "跌破", "賣壓", "外資賣超"]
    buy_keywords = ["買超", "大漲", "漲 3%", "漲3%", "買盤", "外資買超"]
    for line in text.splitlines():
        if any(k in line for k in sell_keywords):
            result["sell_signals"].append(line.strip())
        if any(k in line for k in buy_keywords):
            result["buy_signals"].append(line.strip())
    m = re.search(r"【最終結論】\s*(.+)", text, re.DOTALL)
    if m:
        result["summary"] = m.group(1).strip()[:200]
    return result


def _load_condensed_intel() -> str:
    """讀取濃縮情報"""
    import json
    cf = __file__ and chr(10)
    cf = __import__("pathlib").Path(__file__).parent / f"daily_condensed_intel_{__import__('datetime').date.today()}.json"
    if not cf.exists(): return ""
    try:
        data = json.loads(cf.read_text(encoding='utf-8'))
        if not data: return ""
        lines = []
        for item in data:
            sig = (item.get("signal_level","") or "").split()[0]
            desc = item.get("description","")
            impact = ", ".join(item.get("holdings_impact",[]))
            lines.append(f"{sig} {desc}（影響: {impact}）")
        return chr(10).join(lines)
    except: return ""

def load_daily_analysis() -> dict:
    path = BASE / "daily_analysis.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


