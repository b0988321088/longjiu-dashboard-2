# -*- coding: utf-8 -*-
"""
龍九控股 日報情報補給
- 優先使用 Yahoo Finance API 抓取即時市場數據
- 產出 daily_analysis.json（結構化分析）
- 產出 daily_intel_report_YYYYMMDD.json（統一情報來源）
- 供日報讀取
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path

try:
    import feedparser
    _FEEDPARSER_OK = True
except Exception:
    feedparser = None
    _FEEDPARSER_OK = False

from logging_config import get_logger
logger = get_logger(__name__)

import market_price  # 2026-09-22 INC-239：Yahoo 取價單一入口（前收用日線 timestamp 對齊）

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

def _today_str() -> str:
    return date.today().isoformat().replace("-", "")

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
    """台股/美股即時價 + 漲跌%（2026-09-22 INC-239：改走 market_price 單一入口）。

    舊版兩個坑（保留紀錄，勿再回頭用）：
    - INC-171（9/13）：拿 meta.chartPreviousClose 當昨收 —— range=5d/1mo 時它是「區間起點前」的收盤，
      漲跌% 會變成「一週漲跌」（TWII -2.41% 應 -1.61%、SOX +4.16% 應 +1.81%）。
    - INC-239（9/22）：改讀 meta.previousClose 後仍然錯 —— ^TWII 的 previousClose 落後一整個交易日
      （回 47,180.80＝9/18，真正前收 47,718.84）→ 台股 +0.17% 被算成 +1.31%；
      且收盤後 Yahoo 當日日線未 roll 時會退回 closes[-1]＝前一日，把 9/21 的 47,718.80 標成「今日」。
    market_price 改以「日線 timestamp 對齊」推前收（天然跳過休市日與 null 缺口），
    台股收盤後（台北 13:40+）日線未 roll 則改抓 interval=1m 補當日最後成交。
    """
    try:
        s = market_price.fetch_snapshot(symbol, timeout=timeout)
    except Exception as e:
        logger.error(f"Error fetching Yahoo Finance chart for {symbol}: {e}")
        return {}
    if not s or s.get("price") is None or s.get("change_pct") is None:
        return {}
    return {
        "price": s["price"],
        "prev": s["prev"],
        "change_pct": s["change_pct"],
        "as_of": s.get("as_of"),
        "used_intraday": s.get("used_intraday"),
        "stale": s.get("stale"),
    }

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
        p = d.get("price")
        c = d.get("change_pct")
        if p is None or c is None:
            return "—"
        return f"{p:,.2f} ({c:+.2f}%)"

    us_parts = []
    if dji: us_parts.append(f"道瓊 {fmt(dji)}")
    if ixic: us_parts.append(f"納指 {fmt(ixic)}")
    if gspc: us_parts.append(f"S&P {fmt(gspc)}")
    us = " / ".join(us_parts) if us_parts else "—"

    return {
        "twii": fmt(twii),
        "tsm": fmt(tsm),
        "sox": fmt(sox),
        "us": us,
        "cpi": "美國 7 月 CPI YoY 3.5% (FRED 8/13)；Core 2.8% (FRED 8/13)",
    }

def _fetch_news(queries: list[str], limit: int = 3) -> list[dict]:
    RSS_FEEDS = {
        "cnyes": "https://tw.stock.yahoo.com/rss",
        "yahoo_stock": "https://tw.stock.yahoo.com/rss",
    }
    results = []
    if not _FEEDPARSER_OK:
        return results
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
                if not title: continue
                if any(k in title.lower() for k in _kw):
                    results.append({"title": title[:120], "url": link[:200], "snippet": summary[:200]})
                    if len(results) >= limit: break
            if len(results) >= limit: break
        except Exception as e:
            logger.error(f"RSS error {source_name}: {e}")
            continue
    return results

def classify_from_yf(market: dict) -> dict:
    sell, buy = [], []
    for key, val in market.items():
        if not isinstance(val, str) or val == "—" or "%" not in val:
            continue
        try:
            pct = float(re.search(r"\(([+-]?\d+\.\d+)%\)", val).group(1))
        except Exception:
            continue
        if key == "twii" and pct <= -1.5: sell.append(f"台股加權大跌 {pct:.2f}%")
        if key == "sox" and pct <= -2.0: sell.append(f"費半跌 {pct:.2f}%")
        if key == "tsm" and pct <= -2.0: sell.append(f"台積電大跌 {pct:.2f}%")
        if key == "twii" and pct >= 1.0: buy.append(f"台股大漲 {pct:.2f}%")
        if key == "sox" and pct >= 3.0: buy.append(f"費半大漲 {pct:.2f}%")
    return {"sell_signals": sell[:5], "buy_signals": buy[:5]}

def classify(text: str) -> dict:
    sell, buy = [], []
    _today_md = date.today().strftime("%m/%d")
    for line in text.splitlines():
        if _today_md not in line: continue
        if any(k in line for k in ["賣超", "大跌", "跌 2%", "跌2%", "跌破", "賣壓", "外資賣超"]):
            sell.append(line.strip())
        if any(k in line for k in ["買超", "大漲", "漲 3%", "漲3%", "買盤", "外資買超"]):
            buy.append(line.strip())
    return {"sell_signals": sell[:5], "buy_signals": buy[:5]}

def build_analysis(intel_text: str, signals: dict, market_override: dict | None = None) -> dict:
    today = _today_str()
    market = market_override if market_override else fetch_yf_market()
    
    sell_desc = "; ".join(signals.get("sell_signals", [])[:2]) or "無賣出訊號"
    buy_desc = "; ".join(signals.get("buy_signals", [])[:2]) or "無買進訊號"
    
    scenario_summary = "市場震盪，維持防禦"
    buffett = {"bull": buy_desc, "bear": sell_desc, "actions": ["維持現有配置", "保留高利活存"], "scenario_summary": scenario_summary}
    cto = {"tech_stack": "市場震盪", "risk": sell_desc, "action": "觀望為主"}

    news = _fetch_news(["台股", "美股", "台積電", "外資"])
    briefing_lines = [
        "【台股/大盤】", f"加權指數：{market.get('twii', '—')}", f"台積電：{market.get('tsm', '—')}", "",
        "【美股/外資】", f"美股：{market.get('us', '—')}", f"費半：{market.get('sox', '—')}", "",
        "【CPI/利率】", f"美國CPI：{market.get('cpi', '—')}", ""
    ]
    if signals.get("sell_signals"):
        briefing_lines.append("【賣出訊號】")
        for s in signals["sell_signals"][:3]: briefing_lines.append(f"• {s}")
    else:
        briefing_lines.append("【賣出訊號】")
        briefing_lines.append("無")

    briefing_lines.append("")
    if signals.get("buy_signals"):
        briefing_lines.append("【買進訊號】")
        for s in signals["buy_signals"][:3]: briefing_lines.append(f"• {s}")
    else:
        briefing_lines.append("【買進訊號】")
        briefing_lines.append("無")

    if news:
        briefing_lines.append("\n【最新市場消息】")
        for n in news[:3]: briefing_lines.append(f"• {n.get('title', '')} (來源：{n.get('url', '').split('/')[2]})")

    # 持倉關聯分析與濃縮情報
    briefing_lines.append("\n【持倉關聯分析】")
    try:
        snap = json.loads((BASE / "snapshot.json").read_text(encoding='utf-8'))
        pen = snap.get('penetration', {}).get('actual_twd', {})
        tw_equity = pen.get('台股市值型成長', 0)
        us_equity = pen.get('美股市值型成長', 0)
        long_short = ""
        if tw_equity > 0 and (market.get('twii') and "%" in market['twii']):
            twii_pct = float(re.search(r"\(([+-]?\d+\.\d+)%\)", market['twii']).group(1))
            if twii_pct <= -1.0:
                long_short += f"台股持倉市值型成長 {tw_equity:,.0f} TWD，今日大盤下跌 {twii_pct:.2f}%，短線承壓。"
            elif twii_pct >= 1.0:
                long_short += f"台股持倉市值型成長 {tw_equity:,.0f} TWD，今日大盤上漲 {twii_pct:.2f}%，動能轉強。"

        if not long_short:
            long_short = "目前持倉與市場連動正常，無特殊事件。"
        briefing_lines.append(long_short)
    except Exception as e:
        briefing_lines.append(f"持倉關聯分析錯誤: {e}")

    condensed_intel_text = _load_condensed_intel()
    if condensed_intel_text:
        briefing_lines.append("\n【情報重點（含持倉關聯）】")
        briefing_lines.append(condensed_intel_text)

    briefing = "\n".join(briefing_lines)
    return {"date": today, "generated_at": datetime.now().isoformat(), "market": market, "buffett": buffett, "cto": cto, "signals": signals, "news": news, "scenario_summary": scenario_summary, "briefing": briefing}

def ensure_today_intel(force_refresh: bool = False) -> dict:
    today = _today_str()

    market = fetch_yf_market()
    signals = classify_from_yf(market)
    
    news = _fetch_news(["台股", "美股", "台積電", "外資"], limit=10)
    if news:
        news_text = "\n".join(item.get("title","") + " " + item.get("snippet","") for item in news)
        news_signals = classify(news_text)
        for k in ["sell_signals", "buy_signals"]:
            if news_signals.get(k):
                signals.setdefault(k, []).extend(news_signals[k])

    analysis = build_analysis("", signals, market_override=market)
    BASE.joinpath("daily_analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    
    unified = {"date": today, "generated_at": datetime.now().isoformat(), "market": market, "briefing": analysis["briefing"], "signals": signals, "buffett": analysis["buffett"], "cto": analysis["cto"], "news": news}
    BASE.joinpath(f"daily_intel_report_{today}.json").write_text(json.dumps(unified, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"briefing_text": analysis["briefing"]}

def load_latest_hunter() -> str:
    return ""

def load_daily_analysis() -> dict:
    path = BASE / "daily_analysis.json"
    if not path.exists(): return {}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except: return {}

def _load_condensed_intel() -> str:
    cf = BASE / f"daily_condensed_intel_{date.today()}.json"
    if not cf.exists(): return ""
    try:
        data = json.loads(cf.read_text(encoding='utf-8'))
        return "\n".join(f"{(i.get('signal_level','') or '').split()[0]} {i.get('description','')}（影響: {', '.join(i.get('holdings_impact',[]))}）" for i in data)
    except: return ""

if __name__ == "__main__":
    ensure_today_intel(force_refresh=True)
    print("daily_intel.py re-written & executed successfully.")
