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
from datetime import date, datetime
from pathlib import Path

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


# ===== Web search fallback =====
_WEB_SEARCH = None
try:
    from hermes_tools import web_search as _hermes_web_search
    _WEB_SEARCH = _hermes_web_search
except Exception:
    pass


def search(query: str, limit: int = 5) -> str:
    if _WEB_SEARCH is None:
        return ""
    try:
        result = _WEB_SEARCH(query, limit=limit)
        docs = result.get("data", {}).get("web", [])
        texts = []
        for d in docs:
            title = d.get("title", "")
            desc = d.get("description", "")
            if title:
                texts.append(title)
            if desc:
                texts.append(desc)
        return "\n".join(texts)[:1000]
    except Exception:
        return ""


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
        if key == "twii" and pct >= 1.0 and "外資" in (market.get("twii", "") or ""):
            buy.append(f"台股大漲 {pct}%，外資買超")
        if key == "sox" and pct >= 3.0:
            buy.append(f"費半大漲 {pct}%")
    return {"sell_signals": sell[:5], "buy_signals": buy[:5]}


def classify(text: str) -> dict:
    sell, buy = [], []
    for line in text.splitlines():
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

def _fetch_news(queries: list[str], limit: int = 3) -> list[dict]:
    """Search market news. Fallback: returns empty list silently."""
    try:
        import urllib.request, json as _json
        results = []
        for q in queries[:2]:
            try:
                url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q)
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    html = r.read().decode("utf-8", errors="ignore")[:5000]
                # crude extract titles/links from DDG results
                import re
                for m in re.finditer(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html):
                    href = m.group(1)
                    title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
                    if title and len(title) > 10 and 'duckduckgo' not in href:
                        results.append({"title": title[:120], "url": href[:200], "desc": ""})
            except Exception:
                continue
        return results[:6]
    except Exception:
        return []


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
            "tech_stack": "半導體反弹，觀察資金回補是否持續",
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
            "risk": sell_desc or "震盪期間容易誤判趋势",
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

    # 1. 优先使用 Yahoo Finance API
    market = fetch_yf_market()
    signals = classify_from_yf(market)

    # 2. 備援 web_search
    intel_text = ""
    queries = [
        "台股加權指數 今日 收盤 外資",
        "費城半導體 SOX 今日",
        "台積電 ADR TSM 今日",
        "美股 道瓊 納指 今日",
        "美債收益率 10年 跳動 2026",
        "央行 理監事會議 利率決策 2026",
        "國泰世華 轉貸 利率 政策 2026",
        "0050 配息 除息日 2026",
        "凱基證券 鉅亨基金 機構調倉 2026",
    ]
    search_results = []
    for q in queries:
        r = search(q)
        if r:
            search_results.append(r)

    if search_results:
        intel_text = "\n\n".join(search_results)
        # Merge search-based signals with YF signals
        search_signals = classify(intel_text)
        signals["sell_signals"] = list(dict.fromkeys(signals["sell_signals"] + search_signals["sell_signals"]))[:5]
        signals["buy_signals"] = list(dict.fromkeys(signals["buy_signals"] + search_signals["buy_signals"]))[:5]

    # 3. 產出 intel 檔
    text = render_intel_text(intel_text, signals)
    ts = datetime.now().strftime("%H%M")
    out = HUNTER_DIR / f"intel_{today}_{ts}.txt"
    out.write_text(text, encoding="utf-8")

    # 4. 產出 daily_analysis.json
    analysis = build_analysis(intel_text, signals, market_override=market)
    analysis_path = BASE / "daily_analysis.json"
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "created": True,
        "file": str(out),
        "signals": signals,
        "analysis": str(analysis_path),
        "market": market,
    }


# ===== compat shims for run_daily.py =====
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


def load_daily_analysis() -> dict:
    path = BASE / "daily_analysis.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


if __name__ == "__main__":
    res = ensure_today_intel()
    print(json.dumps(res, ensure_ascii=False, default=str))
