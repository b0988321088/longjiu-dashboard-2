#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""taipower_tender_watch.py — 台電「督導類 / 中部勞務類」標案每日監控

2026-11-02 使用者定調：
  ①只要督導相關（工地安衛督導、巡查、查證）→ 全台電都通知，標註履約地區
  ②或勞務類（勞務／派遣／承攬／人力）→ 只通知中部地區
  ③不做環境調查／環評／環境監測／檢測類

有新品才輸出（no_agent cron：stdout 為空＝不推播）。
去重：data/taipower_tender_seen.json（key=機關+案名 md5，保留 180 天）
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
STATE = BASE / "data" / "taipower_tender_seen.json"
TZ = dt.timezone(dt.timedelta(hours=8))

SUPERVISE_KW = ("督導", "巡查", "查證")
SUPERVISE_REQ = ("安衛", "安全衛生", "工安", "勞安", "職安", "環保", "污染")
LABOR_KW = ("勞務", "派遣", "承攬", "人力")
# 低階／特許類勞務不做（保全需許可、清潔屬低價紅海）
NOT_FIT = ("保全", "警衛", "清潔", "綠美化", "除草", "清運", "病媒", "洗車", "水塔")

# 中部地區（含台電中部各廠處所在鄉鎮）
CENTRAL = ("台中", "彰化", "南投", "苗栗", "通霄", "大甲", "龍井", "梧棲", "清水",
           "沙鹿", "豐原", "烏日", "霧峰", "大里", "太平", "潭子", "后里", "東勢",
           "新社", "石岡", "外埔", "大肚", "竹南", "頭份", "苑裡", "後龍", "三義",
           "銅鑼", "公館", "大湖", "卓蘭", "員林", "溪湖", "田中", "北斗", "二林",
           "草屯", "埔里", "竹山", "水里", "集集", "日月潭", "萬大", "大觀", "明潭",
           "大甲溪", "國姓", "名間", "鹿谷", "中寮", "中部", "中區", "彰濱", "中港")
OTHER = ("台北", "新北", "桃園", "基隆", "宜蘭", "花蓮", "台東", "新竹", "嘉義",
         "台南", "高雄", "屏東", "澎湖", "金門", "連江", "林口", "大潭", "興達",
         "大林", "核一", "核二", "核三", "龍門", "協和", "深澳")

ROW_RE = re.compile(
    r"<td>\s*\d+\.\s*</td>\s*<td>\s*<a[^>]*?RecNo=(\d+)[^>]*>(.*?)</a>", re.S)
BODY_RE = re.compile(r"^(.+?):(.+?)\s*\((\d{4}/\d{1,2}/\d{1,2})\)$")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"


def roc_url(d: dt.date) -> str:
    return ("https://www.taiwanbuying.com.tw/Query_Dateaction.ASP"
            f"?yy={d.year - 1911}&mm={d.month}&dd={d.day}")


def fetch_day(d: dt.date) -> list[tuple[str, str, str, str]]:
    """回傳 [(機關, 案名, 公告日, RecNo)]；抓取失敗丟例外。"""
    req = urllib.request.Request(roc_url(d), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read().decode("utf-8", errors="ignore")
    out: list[tuple[str, str, str, str]] = []
    for m in ROW_RE.finditer(raw):
        recno, body = m.group(1), m.group(2)
        body = re.sub(r"<[^>]+>", "", body)
        body = htmlmod.unescape(body).strip()
        bm = BODY_RE.match(body)
        if not bm:
            continue
        out.append((bm.group(1).strip(), bm.group(2).strip(), bm.group(3), recno))
    return out


def region_of(org: str, name: str) -> str:
    """履約地區粗判（列表無履約地點欄，用機關名/案名地名推估）。"""
    blob = f"{org}{name}"
    if any(k in blob for k in CENTRAL):
        return "中部"
    if any(k in blob for k in OTHER):
        return "其他"
    return "未註明"


def classify(org: str, name: str) -> str | None:
    """回傳 '🎯 督導' / '👷 勞務' / None。勞務類僅中部（在 main 過濾）。"""
    if "台灣電力" not in org:
        return None
    s = name.replace("施工安裝", "")          # 子字串陷阱：施工安裝≠工安
    if any(k in s for k in SUPERVISE_KW) and any(k in s for k in SUPERVISE_REQ):
        return "🎯 督導"
    if any(k in s for k in LABOR_KW):
        if any(k in s for k in NOT_FIT):
            return None
        return "👷 勞務"
    return None


MAX_BUDGET = 10_000_000  # 2026-11-03 使用者定案：督導／勞務／工安／環保一律 1,000 萬上限
BUDGET_LOOKUP_CAP = 8     # 每輪最多查 8 筆金額，避免請求過量


def _http(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")


def lookup_budget(name: str) -> int | None:
    """用 acebidx 關鍵字搜尋對應標案並抓預算金額；抓不到回 None（寧可通知不漏）。"""
    kw = name[:10]
    try:
        s = _http("https://acebidx.com/zh-TW/docs/tender/T/by-keyword/" + urllib.parse.quote(kw))
        tid = None
        for href, body in re.findall(r'href="(/zh-TW/docs/tender/id/[^"]+)"[^>]*>(.{0,900}?)</a>', s, re.S):
            txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", htmlmod.unescape(body)))
            if kw in txt:
                tid = href
                break
        if not tid:
            return None
        d = _http("https://acebidx.com" + tid)
        d = re.sub(r"<script.*?</script>|<style.*?</style>", "", d, flags=re.S)
        o = re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", "\n", d)))
        mm = re.search(r"預算金額\s+([\d,]+)", o)
        return int(mm.group(1).replace(",", "")) if mm else None
    except Exception:
        return None


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
    seen = load_seen()
    stamp = today.isoformat()
    fresh: list[tuple[str, str, str, str, str, int | None]] = []
    errors: list[str] = []
    lookups: list[str] = []
    scanned = 0

    for d in (today - dt.timedelta(days=1), today):
        try:
            rows = fetch_day(d)
        except Exception as e:
            errors.append(f"{d.isoformat()} {type(e).__name__}")
            continue
        scanned += len(rows)
        for org, name, day, recno in rows:
            cat = classify(org, name)
            if not cat:
                continue
            reg = region_of(org, name)
            if cat == "👷 勞務" and reg != "中部":
                continue          # 勞務只收中部
            key = hashlib.md5(f"{org}|{name}".encode("utf-8")).hexdigest()[:16]
            if key in seen:
                continue
            budget = None
            if len(lookups) < BUDGET_LOOKUP_CAP:
                lookups.append(name)
                budget = lookup_budget(name)
                if budget is not None and budget > MAX_BUDGET:
                    seen[key] = stamp      # 超過 800 萬：記錄但不通知
                    continue
            seen[key] = stamp
            fresh.append((cat, reg, org, name, day, budget))

    save_seen(seen)

    if scanned == 0:
        print("⚠️ 解析 0 筆（網站格式可能改版）", file=sys.stderr)
    if errors:
        print("⚠️ 抓取異常：" + "；".join(errors), file=sys.stderr)
    if not fresh:
        return 0

    sup = sum(1 for f in fresh if f[0] == "🎯 督導")
    lab = len(fresh) - sup
    lines = [f"🏗️ 台電新標案 {stamp}（≤1,000 萬）｜督導 {sup} 筆・中部勞務 {lab} 筆"]
    for cat, reg, org, name, day, budget in fresh[:15]:
        short = (org.replace("台灣電力股份有限公司", "台電")
                    .replace("核能火力發電工程處", "核火工程處")
                    .replace("輸變電工程處", "輸變電處")
                    .replace("發電廠", "電廠"))
        amt = f"{budget / 10000:.0f} 萬" if budget else "金額待查"
        lines.append(f"{cat}｜{reg}｜{short}｜{name}｜{day}｜{amt}")
    if len(fresh) > 15:
        lines.append(f"（另有 {len(fresh) - 15} 筆，請至採購網查）")
    lines.append("→ 金額明細：https://www.taiwanbuying.com.tw/Query_Dateaction.ASP"
                 f"?yy={today.year - 1911}&mm={today.month}&dd={today.day}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
