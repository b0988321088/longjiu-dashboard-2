#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""forestry_supervision_watch.py — 林業署「治山防災／林道／擋土牆」設計監造監控

2026-11-02 使用者定調：謝技師特別擅長林務局案子（擋土牆、年度開口），
鎖定農業部林業及自然保育署各分署的「委託規劃設計及監造技術服務」。

篩選：機關含「林業及自然保育署／林業試驗所」
      且案名含（委託規劃設計／委託設計／監造）
      且案名含（治山／防災／林道／擋土／邊坡／治理／崩塌／復育／保安林／溪）
      排除純施工標（無「委託／監造／技術服務」字樣者自然被濾掉）

資料源：acebidx by-org（各分署）＋ by-keyword（治山防災）
去重：data/forestry_supervision_seen.json（保留 180 天）
有新品才輸出（no_agent cron：stdout 為空＝不推播）。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html as htmlmod
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE = BASE / "data" / "forestry_supervision_seen.json"
MAX_BUDGET = 10_000_000  # 2026-11-03 使用者定案：林業署設計監造一律 1,000 萬上限
TZ = dt.timezone(dt.timedelta(hours=8))

ORGS = ("臺中分署", "台中分署", "南投分署", "新竹分署", "嘉義分署",
        "屏東分署", "臺東分署", "台東分署", "花蓮分署", "宜蘭分署")
ORG_URL = "https://acebidx.com/zh-TW/docs/tender/T/by-org/"
KW_URL = "https://acebidx.com/zh-TW/docs/tender/T/by-keyword/"
KEYWORDS = ("治山防災", "委託規劃設計及監造")
INC_SCOPE = ("委託規劃設計", "委託設計", "監造")
INC_THEME = ("治山", "防災", "林道", "擋土", "邊坡", "治理", "崩塌", "復育",
             "保安林", "溪", "護坡", "災後")
CENTRAL = ("台中", "臺中", "彰化", "南投", "苗栗", "和平", "東勢", "埔里",
           "竹山", "水里", "集集", "仁愛", "信義", "鹿谷", "國姓")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
ROW_RE = re.compile(r'href="(/zh-TW/docs/tender/id/[^"]+)"[^>]*>(.{0,600}?)</a>', re.S)
BUDGET_WAN = re.compile(r"預算金額：([0-9.]+)萬")


def _get(url: str, timeout: int = 40) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def fetch_rows() -> list[tuple[str, str, str]]:
    """[(tender_id, 案名文字, 來源)]，來源＝by-org/分署 或 by-keyword。"""
    out: list[tuple[str, str, str]] = []
    seen = set()
    urls: list[tuple[str, str]] = []
    for o in ORGS:
        urls.append((ORG_URL + urllib.parse.quote("農業部林業及自然保育署" + o), o))
    for k in KEYWORDS:
        urls.append((KW_URL + urllib.parse.quote(k), f"kw:{k}"))
    for url, tag in urls:
        # 2026-11-03 修：acebidx 每頁 50 筆、分頁走路徑 /2 /3 …，先前只讀第 1 頁會漏案
        for pg in range(1, 7):
            u = url if pg == 1 else f"{url}/{pg}"
            try:
                raw = _get(u)
            except Exception:
                break
            new = 0
            for m in ROW_RE.finditer(raw):
                full = m.group(1)
                tid = full.rstrip("/").split("/")[-1]
                body = re.sub(r"<[^>]+>", " ", m.group(2))
                body = re.sub(r"\s+", " ", htmlmod.unescape(body)).strip()
                body = re.sub(r"^\d+\s+", "", body)
                if not body or tid in seen:
                    continue
                seen.add(tid)
                new += 1
                if not any(g in body for g in ("林業及自然保育署", "林業試驗所", "林務局")):
                    continue
                out.append((tid, body, tag))
            if new == 0:
                break
    return out


def in_scope(text: str) -> bool:
    return (any(k in text for k in INC_SCOPE) and any(k in text for k in INC_THEME))


def fetch_detail(tid: str) -> dict:
    raw = _get(f"https://acebidx.com/zh-TW/docs/tender/id/{tid}")
    m = BUDGET_WAN.search(raw)
    budget = int(float(m.group(1)) * 10000) if m else None
    text = re.sub(r"<script.*?</script>", "", raw, flags=re.S)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "\n", text)
    joined = "\n".join(x.strip() for x in htmlmod.unescape(text).split("\n") if x.strip())

    def grab(key: str, n: int = 60) -> str:
        i = joined.find(key)
        return re.sub(r"\s+", " ", joined[i:i + n].replace("\n", " ")) if i >= 0 else ""

    deadline = grab("截止投標", 30).replace("截止投標", "").strip()[:16]
    place = re.sub(r"\(.*", "", grab("履約地點", 30).replace("履約地點", "")).strip()[:8]
    closed = "已決標" in joined
    return {"budget": budget, "deadline": deadline, "place": place, "closed": closed}


def parse_deadline(dl: str) -> dt.date | None:
    """'115/10/13 09:00' → date(2026,10,13)；民國年 +1911。"""
    m = re.match(r"(\d{2,3})/(\d{1,2})/(\d{1,2})", dl or "")
    if not m:
        return None
    return dt.date(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3)))


def load_seen() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_seen(seen: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    cutoff = (dt.datetime.now(TZ) - dt.timedelta(days=180)).strftime("%Y-%m-%d")
    trimmed = {k: v for k, v in seen.items() if v >= cutoff}
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(trimmed, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    today = dt.datetime.now(TZ).date()
    stamp = today.isoformat()
    seen = load_seen()
    fresh: list[str] = []
    errors = 0
    expired = 0
    over = 0

    try:
        rows = fetch_rows()
    except Exception as e:
        print(f"⚠️ 列表抓取失敗：{type(e).__name__}", file=sys.stderr)
        return 1

    for tid, text, tag in rows:
        if not in_scope(text):
            continue
        key = hashlib.md5(tid.encode()).hexdigest()[:16]
        is_new = key not in seen
        try:
            d = fetch_detail(tid)
        except Exception:
            errors += 1
            continue
        b = d.get("budget")
        if b and b > MAX_BUDGET:
            seen[key] = stamp
            over += 1
            continue                       # 超過 1,000 萬 → 不通知
        dl = parse_deadline(d.get("deadline", ""))
        if d.get("closed") or (dl and dl < today):
            seen[key] = stamp
            expired += 1
            continue                       # 已決標或已過截止 → 不通知
        seen[key] = stamp
        wan = f"{b/10000:.0f} 萬" if d.get("budget") else "未公開"
        reg = "中部" if any(k in (text + d.get("place", "")) for k in CENTRAL) else d.get("place") or "其他"
        mark = "🆕" if is_new else "📌"
        fresh.append(f"{mark} {wan}｜{reg}｜{text[:60]}｜{d.get('deadline','')} 截止")

    save_seen(seen)
    if expired:
        print(f"ℹ️ 已過截止／已決標略過 {expired} 筆", file=sys.stderr)
    if over:
        print(f"ℹ️ 超過 {MAX_BUDGET//10000} 萬略過 {over} 筆", file=sys.stderr)
    if errors:
        print(f"⚠️ 詳情抓取失敗 {errors} 筆", file=sys.stderr)

    if not fresh:
        print(f"🌲 林業署設計監造（治山／林道／擋土，≤1,000 萬）{stamp}："
              f"今日無符合條件案件（掃 {len(rows)} 筆）")
        return 0

    lines = [f"🌲 林業署設計監造（治山／林道／擋土，≤1,000 萬）{stamp}（{len(fresh)} 筆）"]
    lines += fresh[:12]
    lines.append("→ 🆕 新案・📌 曾報（仍在等標期）；8672 工程服務，技師可投；已決標者自動略過")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
