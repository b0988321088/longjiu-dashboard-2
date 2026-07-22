#!/usr/bin/env python3
"""CIO-Gemini代理人審查龍九日報。"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from html.parser import HTMLParser

try:
    from dotenv import load_dotenv
    load_dotenv(Path.home() / "AppData" / "Local" / "hermes" / ".env")
except Exception:
    pass

import requests


BASE = Path(__file__).parent.resolve()
TODAY = date.today().isoformat()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _to_text(html_path: Path) -> str:
    class TE(HTMLParser):
        def __init__(self):
            super().__init__()
            self.items = []
            self.skip = False
            self.depth = 0
        def handle_starttag(self, tag, attrs):
            if tag in {"style", "script", "head"}:
                self.skip = True
                self.depth += 1
        def handle_endtag(self, tag):
            if tag in {"style", "script", "head"}:
                self.depth -= 1
                if self.depth <= 0:
                    self.skip = False
                    self.depth = 0
        def handle_data(self, data):
            if not self.skip:
                self.items.append(data)

    raw = html_path.read_text(encoding="utf-8")
    parser = TE()
    parser.feed(raw)
    txt = " ".join(parser.items)
    return re.sub(r"\s+", " ", txt).strip()[:4000]


def _load_daily_report() -> str:
    path = BASE / f"daily_report_v2_{TODAY}.html"
    if not path.exists():
        return ""
    return _to_text(path)


def _load_diff() -> str:
    path = BASE / f"diff_{TODAY}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:2000]



def _extract(t):
    import re
    c = t.replace(chr(92)+chr(34), chr(34)).replace(chr(92)+chr(110), " ")
    s = 0; sm = ""; ii = []
    m = re.search('"score"\s*:\s*(\d+)', c)
    if m: s = int(m.group(1))
    m = re.search('"summary"\s*:\s*"(.+?)"', c)
    if m: sm = m.group(1)[:120]
    pts = re.findall('"point"\s*:\s*"(.+?)"', c)
    ds = re.findall('"description"\s*:\s*"(.+?)"', c)
    for p,d in zip(pts, ds): ii.append({"point": p, "description": d[:80]})
    return {"status":"ok","raw":t[:500],"score":s,"summary":sm,"issues":ii}


def _load_hunter_intel():
    import re, json
    from pathlib import Path
    BASE2 = Path(__file__).resolve().parent
    parts = []
    da_path = BASE2 / "daily_analysis.json"
    if da_path.exists():
        try:
            da = json.loads(da_path.read_text("utf-8"))
            m = da.get("market", {})
            parts.append("加權：" + str(m.get("twii","?")))
            sig = da.get("signals", {})
            for s in sig.get("sell_signals", [])[:2]:
                if re.search(r"7月(1[0-9]|20)日|2026-07-(1[0-9]|20)", s): continue
                parts.append("賣出：" + s[:60])
            for s in sig.get("buy_signals", [])[:2]:
                parts.append("買進：" + s[:60])
        except: pass
    try:
        import sqlite3
        db = sqlite3.connect(str(BASE2 / "dragon_assets.db"))
        r = db.execute("SELECT summary FROM market_intel WHERE date=? ORDER BY id DESC LIMIT 1", (TODAY,)).fetchone()
        db.close()
        if r: parts.append("Hunter統計：" + str(r[0] or ""))
    except: pass
    return chr(10).join(parts) if parts else "（無）"

def review() -> dict:
    if not GEMINI_API_KEY:
        return {"status": "skipped", "reason": "GEMINI_API_KEY not set"}

    report = _load_daily_report()
    diff = _load_diff()
    hunter = _load_hunter_intel()

    prompt = (
        "你是CIO-Gemini代理人。審查龍九日報。\n"
        "檢查：五大章節完整、配息SOP(wording)、Relay三站制、"
        "無Railway/dashboard.py/旗艦版連結、保單現值snapshot一致、情報可信度、"
        "Buffett/CTO分析data-driven、diff正確。\n"
        "巴菲特視角建議/CTO視角區塊必須具體存在不可省略；兩者都必須包含「可操作建議(action items)」，不能只是描述現象。\n\n"
        f"日報：\n{report}\n\n"
        f"差異：\n{diff}\n\n"
        'JSON：{"status":"approved"/"rejected","issues":[{"point":"","description":""}],"score":1-10,"summary":""}'
    )

    url = f"{GEMINI_BASE_URL}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }

    try:
        r = requests.post(url, json=payload, timeout=30, headers={"Content-Type": "application/json"})
        if r.status_code != 200:
            return {"status": "error", "reason": f"HTTP {r.status_code}", "detail": r.text[:200]}

        # Unwrap candidates -> parts -> text
        candidate_texts = []
        for cand in r.json().get("candidates", []):
            content = cand.get("content", {})
            for part in content.get("parts", []):
                if "text" in part:
                    candidate_texts.append(part["text"])

        model_text = "\n".join(candidate_texts)

        # Direct parse: responseMimeType="application/json" guarantees JSON
        try:
            result = json.loads(model_text)
            result["_raw"] = model_text[:500]
            return result
        except Exception:
            pass

        # Fallback: strip fences, brace-count
        clean = re.sub(r"```(?:json)?\s*", "", model_text).strip()
        start = clean.find("{")
        if start >= 0:
            depth = 0
            end = -1
            for i, ch in enumerate(clean[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end >= 0:
                try:
                    result = json.loads(clean[start:end+1])
                    result["_raw"] = model_text[:500]
                    return result
                except Exception:
                    pass

        return _extract(model_text)
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}


if __name__ == "__main__":
    print(json.dumps(review(), ensure_ascii=False, indent=2))
