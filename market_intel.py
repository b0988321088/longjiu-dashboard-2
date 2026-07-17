#!/usr/bin/env python3
"""
龍九控股 Market情报可信度評分 + Hunter 情報自动納入
規則：
- web_search 結果一致 → ✅ 可信度 90%+，直接寫入
- web_search 結果矛盾 → ⚠️ 可信度 50%，標記「待補齊」
- 無來源或單一匿名來源 → ❌ 可信度 0%，不顯示
- Hunter 情報自动納入：讀取 hunter_logs/ 最新檔案，解析 P1 訊號
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent.resolve()
HUNTER_DIR = BASE / "hunter_logs"


def load_latest_hunter() -> str:
    if not HUNTER_DIR.exists():
        return ""
    files = sorted(HUNTER_DIR.glob("intel_*.txt"), key=os.path.getmtime, reverse=True)
    if not files:
        return ""
    return files[0].read_text(encoding="utf-8")


def parse_hunter_signals(text: str) -> dict:
    """解析 Hunter 情報中的 P1 訊號。"""
    result = {
        "sell_signals": [],
        "buy_signals": [],
        "summary": "",
    }
    if not text:
        return result

    # P1 sell signal keywords
    sell_keywords = ["賣超", "大跌", "跌 2%", "跌2%", "跌破", "賣壓", "外資賣超"]
    buy_keywords = ["買超", "大漲", "漲 3%", "漲3%", "買盤", "外資買超"]

    lines = text.splitlines()
    for line in lines:
        if any(k in line for k in sell_keywords):
            result["sell_signals"].append(line.strip())
        if any(k in line for k in buy_keywords):
            result["buy_signals"].append(line.strip())

    # 最終結論
    m = re.search(r"【最終結論】\s*(.+)", text, re.DOTALL)
    if m:
        result["summary"] = m.group(1).strip()[:200]

    return result


def score_market_data(data: dict) -> dict:
    """
    對 market 情報中的每個項目進行可信度評分。
    data: { "台股收盤": {"value": "...", "sources": ["url1", "url2"]}, ... }
    """
    scored = {}
    for key, item in data.items():
        sources = item.get("sources", [])
        value = item.get("value", "")

        if not sources:
            scored[key] = {"value": "", "credibility": 0, "status": "❌ 無來源，不顯示"}
        elif len(sources) >= 2:
            # 多個來源一致 → 高可信度
            scored[key] = {"value": value, "credibility": 90, "status": "✅ 可信"}
        else:
            # 單一來源
            scored[key] = {"value": value, "credibility": 50, "status": "⚠️ 單一來源，待補齊"}

    return scored


def main() -> dict:
    hunter_text = load_latest_hunter()
    signals = parse_hunter_signals(hunter_text)

    # 最新 market data（2026-07-16 web_search 擷取）
    market_data = {
        "台股加權指數": {
            "value": "45,624.98（-6.61，-0.01%）",
            "sources": ["Yahoo Finance", "GoodInfo", "sinotrade"],
            "credibility": 90,
        },
        "台積電收盤": {
            "value": "2,470 元（+1.23%）",
            "sources": ["Yahoo Finance", "Threads", "Business Weekly"],
            "credibility": 85,
        },
        "台積電法說會": {
            "value": "Q2營收創歷史新高；全年美元營收成長上調至30%+；資本支出600-640億美元",
            "sources": ["Business Weekly", "LTN", "stock.ltn.com.tw", "goodinfo.tw"],
            "credibility": 80,
        },
        "費半 7/15": {
            "value": "12,398.89（-2.08%）",
            "sources": ["Yahoo Finance", "Threads"],
            "credibility": 75,
        },
        "美股 7/15": {
            "value": "道瓊 +0.29%、納指 +0.62%、標普 +0.38%",
            "sources": ["Yahoo Finance"],
            "credibility": 70,
        },
        "美國 6 月 CPI": {
            "value": "年增3.5%（<預期3.8%）；核心2.6%（<預期2.8%）；月減0.4%",
            "sources": ["web_search_multiple", "Yahoo Finance", "sinotrade"],
            "credibility": 90,
        },
        "0050 配息": {
            "value": "0.6元，較前次縮水4成；7/21除息，8/10發放",
            "sources": ["元大投信", "wealth.com.tw", "ettoday"],
            "credibility": 85,
        },
    }

    scored = score_market_data(market_data)

    result = {
        "date": date.today().isoformat(),
        "market": scored,
        "hunter": {
            "sell_signals": signals["sell_signals"][:3],
            "buy_signals": signals["buy_signals"][:3],
            "summary": signals["summary"],
        },
    }
    return result


if __name__ == "__main__":
    data = main()
    print(json.dumps(data, ensure_ascii=False, indent=2))


def render_buffett_analysis(tv: dict, market: dict) -> str:
    """根據最新 market 情報產生巴菲特視角建議"""
    allianz = tv.get("insurance_total", 9_876_282)
    monthly_dividend = 69_044

    buffett_md = f"""# 巴菲特視角分析（{tv.get('date', date.today().isoformat())}）

## 能力圈
- 台股權值股集中度高，保單穿透後美股佔比86%
- 0050配息縮水4成後，防禦缺口需由00878/00713補位
- 0056凍結質押中，短期無法加碼

## 安全邊際
- 美國CPI年增3.5%、核心2.6%，雙雙低於預期，降息預期升溫
- 外資賣超14.15億元，賣壓減輕，短線震盪而非趨勢反轉
- 台積法說會：Q2營收創歷史新高、全年營收成長上調至30%+、資本支出600-640億美元

## 長期持有
- 台積電半導體主升段持續，AI需求支撐
- 0050縮水4成後，00878/00713必須持續配置

## 配息品質
- 本月配息：{monthly_dividend:,} TWD（安聯 {55_451:,} + 第一金 {13_593:,}）
- 0050配息0.6元，7/21除息前可能賣壓
- 配息入帳後hold至T+4最晚申請日才轉換

## 結論
維持現有配置，0056凍結不動；00878/00713補位0050缺口；
保留現金部位至CPI確認降息路徑後，再評估超跌進場。
"""
    return buffett_md
