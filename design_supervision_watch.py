#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""design_supervision_watch.py — 中部「設計監造」小額案每日監控

2026-11-02 使用者定調：謝技師（土木＋結構技師、有工程顧問公司牌、有繪圖人員）
可承接 8672 工程服務類；8671 建築服務需建築師 → 直接排除。

篩選條件：
  ①標題含「設計監造／規劃設計監造／委託設計」
  ②履約地點在中部（台中／彰化／南投／苗栗）
  ③預算 ≤ 800 萬（使用者要「規模比較小」；2026-11-03 由 600 萬上調）
  ④分類非 8671 建築服務

資料源：acebidx（列表頁有 tender id → 詳情頁有預算/截止/履約地點/分類）
有新品才輸出（no_agent cron：stdout 為空＝不推播）。
去重：data/design_supervision_seen.json（保留 120 天）
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html as htmlmod
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE = BASE / "data" / "design_supervision_seen.json"
TZ = dt.timezone(dt.timedelta(hours=8))

KEYWORD = "設計監造"
MAX_BUDGET = 10_000_000  # 2026-11-03 使用者定案：中部設計監造一律 1,000 萬上限
LIST_URL = ("https://acebidx.com/zh-TW/docs/tender/T/by-keyword/"
            "%E8%A8%AD%E8%A8%88%E7%9B%A3%E9%80%A0")
CENTRAL = ("台中", "彰化", "南投", "苗栗", "后里", "豐原", "大里", "太平", "南屯",
           "北屯", "西屯", "中區", "員林", "溪湖", "田中", "北斗", "埔里", "草屯",
           "竹山", "大甲", "清水", "沙鹿", "烏日", "霧峰", "通霄", "苑裡", "竹南",
           "頭份", "和美", "福興", "花壇", "溪州", "潭子", "大雅", "神岡", "龍井")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

ROW_RE = re.compile(
    r'href="(/zh-TW/docs/tender/id/[^"]+)"[^>]*>(.{0,700}?)</a>', re.S)
BUDGET_RE = re.compile(r"預算金額\s*([0-9][0-9,]*)")
BUDGET_WAN_RE = re.compile(r"預算金額[：:]\s*([0-9.]+)\s*萬")


def _get(url: str, timeout: int = 45) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def fetch_candidates(max_pages: int = 12) -> list[tuple[str, str]]:
    """回傳 [(tender_id, 標題文字)]，已初篩中部地名。

    2026-11-03 修：acebidx 每頁固定 50 筆、分頁走路徑 /2 /3 …，
    先前只抓第 1 頁 → 400 筆中只看到 50 筆，610 萬「北區」、631 萬「集集攔河堰」
    等案全被漏掉。改為逐頁翻到「該頁無新 id」為止（上限 max_pages）。
    """
    out: list[tuple[str, str]] = []
    seen = set()
    for pg in range(1, max_pages + 1):
        url = LIST_URL if pg == 1 else f"{LIST_URL}/{pg}"
        try:
            raw = _get(url)
        except Exception:
            if pg == 1:
                raise
            break
        new = 0
        for m in ROW_RE.finditer(raw):
            tid = m.group(1).rstrip("/").split("/")[-1]
            if tid in seen:
                continue
            seen.add(tid)
            new += 1
            body = re.sub(r"<[^>]+>", " ", m.group(2))
            body = re.sub(r"\s+", " ", htmlmod.unescape(body)).strip()
            if body and any(k in body for k in CENTRAL):
                out.append((tid, body))
        if new == 0:
            break
    return out


def parse_deadline(s: str) -> dt.datetime | None:
    """'115/11/09 17:00' → datetime（民國年自動換算）。"""
    m = re.match(r"(\d{2,4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})", str(s or ""))
    if not m:
        return None
    y, mo, dd, hh, mi = (int(x) for x in m.groups())
    if y < 200:
        y += 1911
    try:
        return dt.datetime(y, mo, dd, hh, mi, tzinfo=TZ)
    except ValueError:
        return None


def fetch_detail(tid: str) -> dict:
    """抓詳情頁，取預算／截止／履約地點／分類。失敗回空 dict。"""
    url = f"https://acebidx.com/zh-TW/docs/tender/id/{tid}"
    raw = _get(url, timeout=40)
    meta = re.search(r"預算金額：([0-9.]+)萬", raw)
    budget = int(float(meta.group(1)) * 10000) if meta else None
    if budget is None:
        m2 = BUDGET_RE.search(raw)
        if m2:
            budget = int(m2.group(1).replace(",", ""))
    text = re.sub(r"<script.*?</script>", "", raw, flags=re.S)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "\n", text)
    lines = [x.strip() for x in htmlmod.unescape(text).split("\n") if x.strip()]
    joined = "\n".join(lines)

    def grab(key: str, n: int = 60) -> str:
        i = joined.find(key)
        if i < 0:
            return ""
        return re.sub(r"\s+", " ", joined[i:i + n].replace("\n", " "))

    cat = ""
    cm = re.search(r"勞務類\s*—\s*(86\d\d)\s*—\s*([^\n]{0,12})", joined)
    if cm:
        cat = f"{cm.group(1)} {cm.group(2)}".strip()
    deadline = re.sub(r"\s+", " ", grab("截止投標", 30).replace("截止投標", "")).strip()[:16]
    place = grab("履約地點", 30).replace("履約地點", "").strip()
    place = re.sub(r"\(.*", "", place).replace("履約", "").strip()[:6]
    return {"budget": budget, "cat": cat, "deadline": deadline, "place": place}


def load_seen() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_seen(seen: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    cutoff = (dt.datetime.now(TZ) - dt.timedelta(days=120)).strftime("%Y-%m-%d")
    trimmed = {k: v for k, v in seen.items() if v >= cutoff}
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(trimmed, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    now = dt.datetime.now(TZ)
    stamp = now.date().isoformat()
    seen = load_seen()
    rows: list[tuple] = []
    errors = 0

    try:
        cands = fetch_candidates()
    except Exception as e:
        print(f"⚠️ 列表抓取失敗：{type(e).__name__}", file=sys.stderr)
        return 1

    titles: set[str] = set()
    for tid, title in cands:
        key = hashlib.md5(tid.encode()).hexdigest()[:16]
        try:
            d = fetch_detail(tid)
        except Exception:
            errors += 1
            continue
        time.sleep(0.6)
        b = d.get("budget")
        if b is not None and b > MAX_BUDGET:
            continue
        if d.get("cat", "").startswith("8671"):
            continue                      # 建築服務需建築師，排除
        if d.get("place") and not any(k in d["place"] for k in CENTRAL):
            continue                      # 以詳情履約地點複核
        dl = parse_deadline(d.get("deadline"))
        if dl and dl < now:
            continue                      # 等標期已過 → 不列（2026-11-03 使用者要求：只給等標期內）
        t = re.sub(r"^\d+\s+", "", title)
        t = re.sub(r"\s*\d+月\d+日\s*公告\s*$", "", t).strip()
        sig = re.sub(r"\s+", "", t)
        if sig in titles:
            continue                      # 同案多次公告（不同 id）只留一筆
        titles.add(sig)
        is_new = key not in seen
        if is_new:
            seen[key] = stamp
        rows.append((dl, b, d.get("place", ""), t, d.get("cat") or "類別未載", is_new))

    save_seen(seen)
    if errors:
        print(f"⚠️ 詳情抓取失敗 {errors} 筆", file=sys.stderr)
    if not rows:
        return 0

    rows.sort(key=lambda r: (r[0] or now, r[3]))
    new_n = sum(1 for r in rows if r[5])
    lines = [
        f"🏛️ 中部設計監造（≤1,000 萬）等標期內 {stamp}"
        f"（共 {len(rows)} 筆：🆕 新案 {new_n}・📌 曾報 {len(rows) - new_n}）"
    ]
    for dl, b, place, t, cat, is_new in rows:
        mark = "🆕" if is_new else "📌"
        wan = f"{b/10000:.0f} 萬" if b else "未公開"
        dls = dl.strftime("%m/%d %H:%M") if dl else "未載"
        lines.append(f"{mark} {wan}｜{place}｜{t[:52]}｜{dls}截止｜{cat}")
    lines.append("→ 🆕 新案・📌 曾報（仍在等標期）；技師可投 8672 工程服務，8671 建築服務已排除")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
