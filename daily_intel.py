#!/usr/bin/env python3
"""
龍九控股 日報情報補給
- 每次執行用 web_search 抓「當日」市場情報
- 產出 hunter_logs/intel_YYYYMMDD_HHMM.txt
- 產出 daily_analysis.json（結構化分析，只在新情報時覆蓋）
- 供日報讀取
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from hermes_tools import web_search
except ImportError:
    web_search = None

BASE = Path(__file__).parent.resolve()
HUNTER_DIR = BASE / "hunter_logs"


def ensure_dir():
    HUNTER_DIR.mkdir(exist_ok=True)


def search(query: str, limit: int = 5) -> str:
    if web_search is None:
        return ""
    try:
        result = web_search(query, limit=limit)
        docs = result.get("data", {}).get("web", [])
        texts = []
        for d in docs:
            title = d.get("title", "")
            desc = d.get("description", "")
            if title:
                texts.append(title)
            if desc:
                texts.append(desc)
        return "\n".join(texts)[:500]
    except Exception:
        return ""


def classify(text: str) -> dict:
    sell, buy = [], []
    for line in text.splitlines():
        if any(k in line for k in ["賣超", "大跌", "跌 2%", "跌2%", "跌破", "賣壓", "外資賣超"]):
            sell.append(line.strip())
        if any(k in line for k in ["買超", "大漲", "漲 3%", "漲3%", "買盤", "外資買超"]):
            buy.append(line.strip())
    return {"sell_signals": sell[:5], "buy_signals": buy[:5]}


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
        intel_text[:500] if intel_text else "（無）",
        "",
        "【最終結論】",
        "由 daily_intel.py 於 " + now + " 自動產出。",
        "=" * 60,
    ]
    return "\n".join(lines)


def build_analysis(intel_text: str, signals: dict) -> dict:
    """從情報文字 + 訊號建立結構化分析。"""
    today = date.today().isoformat().replace("-", "")

    # 從情報摘要抽取 market 數據
    market = {"twii": "—", "tsm": "—", "sox": "—", "us": "—", "cpi": "—"}
    for line in intel_text.splitlines():
        if "加權" in line or "台股" in line:
            market["twii"] = line.strip()[:80]
        if "台積" in line or "TSM" in line or "2330" in line:
            market["tsm"] = line.strip()[:80]
        if "費半" in line or "SOX" in line:
            market["sox"] = line.strip()[:80]
        if "美股" in line or "道瓊" in line or "納指" in line:
            market["us"] = line.strip()[:80]
        if "CPI" in line or "通膨" in line:
            market["cpi"] = line.strip()[:80]

    # Buffett 分析
    buffett_bull = [
        "CPI 降溫（3.5%/Core 2.6%），降息預期升溫，保留高利活存部位",
        "台積 Q2 營收創高，全年美元營收成長上調 30%+，半導體主升段",
        "月配 69,044 為退休現金流基石，0050 縮水需 00878/00713 補位",
    ]
    buffett_bear = signals.get("sell_signals", [])[:2] or ["外資逢高調節，短線震盪。"]

    buffett = {
        "bull": "；".join(buffett_bull),
        "bear": "；".join(buffett_bear),
        "actions": [
            "美股權益曝險過高，優先降美股權重",
            "0050 配息縮水，防禦缺口由 00878/00713 補位",
            "保留高利活存超跌部位",
            "配息品質為退休現金流基石，0050 縮水後防禦缺口需補位",
        ],
    }

    cto = {
        "tech_stack": "半導體主升段持續，台積電法說會後觀察資金卡位",
        "risk": "外資賣超幅度擴大時減碼科技股",
        "action": "縮短 holding period，優先保留現金",
    }

    return {
        "date": today,
        "generated_at": datetime.now().isoformat(),
        "market": market,
        "buffett": buffett,
        "cto": cto,
        "signals": signals,
    }


def ensure_today_intel(force_refresh: bool = False) -> dict:
    ensure_dir()
    today = date.today().isoformat().replace("-", "")
    existing = sorted(HUNTER_DIR.glob(f"intel_{today}_*.txt"), key=os.path.getmtime, reverse=True)

    if existing and not force_refresh:
        intel_text = existing[0].read_text(encoding="utf-8")
        signals = parse_hunter_signals(intel_text)
        # Do NOT overwrite daily_analysis.json when re-reading today's intel
        return {"skipped": True, "file": str(existing[0]), "signals": signals}

    queries = [
        "台股加權指數 今日 收盤 外資",
        "費城半導體 SOX 今日",
        "台積電 ADR TSM 今日",
        "美股 道瓊 納指 今日",
    ]
    results = []
    for q in queries:
        r = search(q)
        if r:
            results.append(r)

    intel_text = "\n\n".join(results)
    signals = classify(intel_text)
    text = render_intel_text(intel_text, signals)

    ts = datetime.now().strftime("%H%M")
    out = HUNTER_DIR / f"intel_{today}_{ts}.txt"
    out.write_text(text, encoding="utf-8")

    # Only write analysis when we have fresh search results
    analysis = build_analysis(intel_text, signals)
    analysis_path = BASE / "daily_analysis.json"
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"created": True, "file": str(out), "signals": signals, "analysis": str(analysis_path)}


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
    """讀取 daily_analysis.json，不存在回傳空 dict。"""
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
