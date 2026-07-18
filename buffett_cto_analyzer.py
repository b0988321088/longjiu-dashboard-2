#!/usr/bin/env python3
"""Difference-driven Buffett / CTO analyzer for 龍九 daily report.
Reads changelog_<today>.md and snapshot.json, then injects
scenario-driven Buffett + CTO sections into daily_report_v2_<today>.html.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path.home() / "AppData" / "Local" / "hermes" / ".env")

import requests

BASE = Path(__file__).parent.resolve()
TODAY = date.today().isoformat()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


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
    coverage = p1.get("coverage_ratio", 0)
    passive_income = p1.get("passive_income", 0)

    return (
        "你是龍九控股的 Buffett 代理人與 CTO 技術分析師。\n"
        "請根據「今日差異」和「真值」輸出兩段分析。\n\n"
        "【真值錠定】\n"
        f"  淨資產：{net:,} TWD\n"
        f"  月收入：{monthly_income:,} / 月支出：{monthly_expense:,}\n"
        f"  被動收入：{passive_income:,} / 覆蓋率：{coverage}\n\n"
        f"【今日差異】\n{changelog}\n\n"
        "規則：\n"
        "1. Buffett 段落：場景判定（bull/bear）+ 淨資產數字 + 建議部位（TWD 金額）\n"
        "2. CTO 段落：tech_stack + 今日最大風險（具體數字）+ 建議動作\n"
        "3. 禁止靜態通用文案；必須引用上述具體數字\n"
        "4. 中文繁式輸出\n"
        "5. 格式：見以下 HTML 模板\n\n"
        "<h3>巴菲特視角建議</h3>\n"
        "<strong>場景判定</strong>：...<br>\n"
        "• Bull：...\n"
        "• Bear：...<br>\n"
        "<strong>🤝 Buffett 派操作建議</strong><br>\n"
        "• 淨資產：...,XXX TWD<br>\n"
        "• 建議部位：...<br>\n"
        "• 今日動作：...\n\n"
        "<h3>CTO 技術視角</h3>\n"
        "<strong>tech_stack</strong>：...<br>\n"
        "<strong>今日最大風險</strong>：...<br>\n"
        "<strong>建議動作</strong>：..."
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


def _extract_sections(text: str) -> dict:
    """Extract Buffett + CTO HTML fragments from Gemini output."""
    result = {"buffett": "", "cto": ""}
    if not text:
        return result

    # Try to split by section headers
    bm = re.search(r"(<h3>巴菲特視角建議.*?)(?=<h3>|$)", text, re.S)
    cm = re.search(r"(<h3>CTO技術視角.*?)(?=<h3>|$)", text, re.S)
    if bm:
        result["buffett"] = bm.group(1).strip()
    if cm:
        result["cto"] = cm.group(1).strip()

    # Fallback: split by marker names
    if not result["buffett"] and not result["cto"]:
        parts = re.split(r"巴菲特視角建議|CTO技術視角", text)
        if len(parts) >= 2:
            result["buffett"] = "<h3>巴菲特視角建議</h3>" + parts[1].strip()
        if len(parts) >= 3:
            result["cto"] = "<h3>CTO技術視角</h3>" + parts[2].strip()

    return result


def _inject(html_path: Path, sections: dict) -> bool:
    if not sections.get("buffett") and not sections.get("cto"):
        print("[SKIP] No Buffett/CTO content to inject")
        return False

    html = html_path.read_text(encoding="utf-8")

    # Find Buffett block
    b_start = html.find("<h3>巴菲特視角建議</h3>")
    if b_start == -1:
        b_start = html.find("巴菲特視角")
    c_start = html.find("<h3>CTO技術視角</h3>")
    if c_start == -1:
        c_start = html.find("CTO技術視角")

    if b_start != -1 and c_start != -1:
        # Replace between markers
        new_html = html[:b_start]
        if sections.get("buffett"):
            new_html += sections["buffett"] + "<br>\n        "
        new_html += sections.get("cto", html[b_start:c_start].split("</h3>")[0] + "</h3>")
        new_html = new_html.rstrip() + html[c_start + len("<h3>CTO技術視角</h3>"):]
    elif b_start != -1:
        end = html.find("</div>", b_start)
        end = html.find("</div>", end + 1) if end != -1 else -1
        if end != -1:
            new_html = html[:b_start]
            if sections.get("buffett"):
                new_html += sections["buffett"] + "<br>\n        "
            if sections.get("cto"):
                new_html += sections["cto"] + "<br>\n        "
            new_html += html[end:]
        else:
            new_html = html
    else:
        # Insert before closing </body>
        insert = ""
        if sections.get("buffett"):
            insert += '        <div class="luxury-card p-6 space-y-4">\n            '
            insert += sections["buffett"] + "\n        </div>\n"
        if sections.get("cto"):
            insert += '        <div class="luxury-card p-6 space-y-4">\n            '
            insert += sections["cto"] + "\n        </div>\n"
        new_html = html.replace("</body>", insert + "</body>")

    html_path.write_text(new_html, encoding="utf-8")
    return True


def run() -> bool:
    changelog = _read_changelog()
    snapshot = _read_snapshot()

    if not changelog:
        print("[SKIP] No changelog found for today")
        return False

    prompt = _build_prompt(changelog, snapshot)
    raw = _call_gemini(prompt)
    if not raw:
        print("[SKIP] Gemini returned empty")
        return False

    sections = _extract_sections(raw)
    if not any(sections.values()):
        print(f"[WARN] Could not extract Buffett/CTO sections from:\n{raw[:200]}")
        return False

    html_path = BASE / f"daily_report_v2_{TODAY}.html"
    if not html_path.exists():
        print(f"[SKIP] {html_path} not found")
        return False

    ok = _inject(html_path, sections)
    if ok:
        print(f"[OK] Buffett/CTO sections injected into {html_path.name}")
    return ok


if __name__ == "__main__":
    ok = run()
    raise SystemExit(0 if ok else 1)
