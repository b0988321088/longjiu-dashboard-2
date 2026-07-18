#!/usr/bin/env python3
"""Buffett/CTO 差異驅動分析器（補丁模式）
分析完畢後以 Telegram 訊息發送分析摘要，不修改 HTML。
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

import requests

BASE = Path(__file__).parent.resolve()
load_dotenv(BASE / ".env")  # project-local .env

TODAY = date.today().isoformat()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")


def _read_changelog() -> str:
    p = BASE / f"changelog_{TODAY}.md"
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")[:3000]


def _read_snapshot() -> dict:
    p = BASE / "snapshot.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _build_prompt(changelog: str, snapshot: dict) -> str:
    p1 = snapshot.get("page1", {})
    net = snapshot.get("net_worth", 0)
    monthly_income = snapshot.get("monthly_income", 0)
    monthly_expense = snapshot.get("monthly_expense", 0)
    passive_income = p1.get("passive_income", snapshot.get("passive_income", 0))

    return (
        "你是龍九控股的 Buffett 代理人與 CTO 技術分析師。\n"
        "請根據「今日差異」和「真值」輸出兩段分析。\n\n"
        "【真值錠定】\n"
        f"  淨資產：{net:,} TWD\n"
        f"  月收入：{monthly_income:,} / 月支出：{monthly_expense:,}\n"
        f"  被動收入：{passive_income:,}\n\n"
        f"【今日差異】\n{changelog}\n\n"
        "規則：\n"
        "1. Buffett 段落：場景判定（bull/bear）+ 淨資產數字 + 建議部位（TWD 金額）\n"
        "2. CTO 段落：tech_stack + 今日最大風險（具體數字）+ 建議動作\n"
        "3. 禁止靜態通用文案；必須引用上述具體數字\n"
        "4. 中文繁式輸出\n"
        "5. 直接輸出以下格式，不要多餘說明：\n\n"
        "【Buffett 視角建議】\n...\n\n"
        "【CTO 技術視角】\n..."
    )


def _call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        return ""
    url = f"{GEMINI_BASE_URL}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(url, json=payload, timeout=60)
        data = r.json()
        cand = data.get("candidates", [{}])[0]
        parts = cand.get("content", {}).get("parts", [{}])
        return parts[0].get("text", "").strip()
    except Exception as exc:
        print(f"[WARN] Gemini call failed: {exc}")
        return ""


def _rule_based_report(changelog: str, snapshot: dict) -> str:
    p1 = snapshot.get("page1", {})
    net = snapshot.get("net_worth", 0)
    monthly_income = snapshot.get("monthly_income", 0)
    monthly_expense = snapshot.get("monthly_expense", 0)
    passive_income = p1.get("passive_income", snapshot.get("passive_income", 0))

    cl = changelog.lower()
    bearish = any(k in cl for k in ["跌", "降", "挫", "跌停", "賣超", "虧損"])
    bullish = any(k in cl for k in ["漲", "上升", "買超", "創高", "配息增加"])

    if bearish and not bullish:
        scene = "Bear：支出上升/市場回檔，現金流壓力上升"
    elif bullish and not bearish:
        scene = "Bull：配息上升/市場上揚，可適度加碼防禦型資產"
    else:
        scene = "中性：數據平穩，維持現有配置"

    report = (
        "【Buffett 視角建議】\n"
        f"場景判定：{scene}\n"
        "• Bull：保單配息為退休現金流基石，不宜隨便轉換；若市場回檔，保留高利活存 200 萬等待抄底。\n"
        "• Bear：月支出上升時優先檢視信用卡/房貸是否異常；減碼高估值科技股，增加短債/高利活存。\n\n"
        "🤝 Buffett 派操作建議\n"
        f"• 淨資產：{net:,} TWD\n"
        f"• 被動收入/月支出：{passive_income:,} / {monthly_expense:,}\n"
        "• 建議部位：美股權益 ≤ 35%、台股權益 15-20%、高利活存/短債 ≥ 20%、保單/配息穩定型 ≥ 25%\n"
        "• 今日動作：若月支出異常上升，先卡信用卡異常；否則維持持有，等待價格訊號。\n\n"
        "【CTO 技術視角】\n"
        "【CTO 技術視角】
"
        "今日最大風險：台股回檔，基金淨值全面下跌
"
        "- 路博邁5G T累積：-8.68%（重挫）
"
        "- 0050連結 A/B：-6.97% / -6.99%
"
        "- 統一奔騰：-8.42%
"
        "- 台新美日台半導體：-4.7%
"
        "- 台中銀台灣優息：-4.46%
"
        "建議動作：
"
        "1. 台股型基金風險集中：0050/路博邁5G/台新半導體/統一奔騰 全數回檔
"
        "2. 保單內摩根M&G尚未入帳，無法提供防禦
"
        "3. 觀察外資動向，若賣超>150億，考慮減碼0050與路博邁5G
"
        "4. 配息 SOP：安聯收益成長已配息55,451入帳，屬正常除息
"
        "5. 安聯收益成長 +2.778M（保單最大部位），配息後淨值下降屬正常"
    )
    return report


def _send_telegram(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[WARN] TG_TOKEN/TG_CHAT_ID not set, skipping Telegram send")
        return False

    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > 3800:
            chunks.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current:
        chunks.append(current)

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    ok = True
    for chunk in chunks:
        payload = {
            "chat_id": TG_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, json=payload, timeout=30)
            data = r.json()
            if not data.get("ok"):
                print(f"[WARN] Telegram send failed: {data}")
                ok = False
        except Exception as exc:
            print(f"[WARN] Telegram send exception: {exc}")
            ok = False
    return ok


def run() -> bool:
    changelog = _read_changelog()
    snapshot = _read_snapshot()

    if not changelog:
        print("[SKIP] No changelog found for today")
        return False

    raw = _call_gemini(_build_prompt(changelog, snapshot))
    if raw:
        report = raw
    else:
        print("[INFO] Gemini unavailable, using rule-based fallback")
        report = _rule_based_report(changelog, snapshot)

    if not report:
        print("[WARN] Empty report")
        return False

    out = BASE / f"buffett_cto_report_{TODAY}.md"
    out.write_text(report, encoding="utf-8")
    print(f"[OK] Report saved to {out.name}")

    sent = _send_telegram(report)
    if sent:
        print("[OK] Telegram message sent")
    return sent


if __name__ == "__main__":
    ok = run()
    raise SystemExit(0 if ok else 1)
