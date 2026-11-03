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

SUPERVISE_KW = ("督導", "巡查", "查證", "稽核", "稽查")
SUPERVISE_REQ = ("安衛", "安全衛生", "工安", "勞安", "職安", "環保", "污染")
LABOR_KW = ("勞務", "派遣", "承攬", "人力", "勤務")
# 低階／特許類勞務不做（保全需許可、清潔屬低價紅海）
NOT_FIT = ("保全", "警衛", "清潔", "綠美化", "除草", "清運", "病媒", "洗車", "水塔")
# 2026-11-03 使用者裁決「不放寬」：環境監測／檢測／環評／採樣類一律排除（僅計數揭露）
ENV_EXCLUDE = ("環境監測", "環境調查", "環評", "環評", "檢測", "採樣", "水質",
               "空氣品質", "噪音", "土壤", "廢棄物", "篩檢")

# 中部地區（含台電中部各廠處所在鄉鎮）
CENTRAL = ("台中", "彰化", "南投", "苗栗", "通霄", "大甲", "龍井", "梧棲", "清水",
           "沙鹿", "豐原", "烏日", "霧峰", "大里", "太平", "潭子", "后里", "東勢",
           "新社", "石岡", "外埔", "大肚", "竹南", "頭份", "苑裡", "後龍", "三義",
           "銅鑼", "公館", "大湖", "卓蘭", "員林", "溪湖", "田中", "北斗", "二林",
           "草屯", "埔里", "竹山", "水里", "集集", "日月潭", "萬大", "大觀", "明潭",
           "大甲溪", "國姓", "名間", "鹿谷", "中寮", "彰濱", "中港")
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


CENTRAL_ORG = ("台中", "臺中", "彰化", "南投", "苗栗")
OTHER_ORG = ("台北", "臺北", "新北", "基隆", "桃園", "新竹", "嘉義", "台南", "臺南",
             "高雄", "屏東", "宜蘭", "花蓮", "台東", "臺東", "澎湖", "金門", "連江")


def region_of(org: str, name: str) -> str:
    """履約地區粗判。2026-11-03 修：改以機關所在縣市優先，避免『高中部』『公館場』等字串誤配中部。"""
    if any(k in org for k in CENTRAL_ORG):
        return "中部"
    if any(k in org for k in OTHER_ORG):
        return "其他"
    s = name.replace("高中部", "高中").replace("國中部", "國中").replace("公館場", "公館場區")
    if any(k in s for k in CENTRAL):
        return "中部"
    if any(k in s for k in OTHER):
        return "其他"
    return "未註明"


def classify(org: str, name: str) -> str | None:
    """回傳分類。2026-11-03 使用者指示：①工安環保查證 ②勞務／勤務 分開查、分開回報。

    範圍：中部（region_of 於 main 過濾），不限台電（台電另以 ⚡ 標示）。
    排除：環境監測／檢測／環評／採樣（使用者已裁示「不放寬」）、低階特許勞務。
    """
    s = name.replace("施工安裝", "")          # 子字串陷阱：施工安裝≠工安
    if any(k in s for k in ENV_EXCLUDE):
        return None                            # 不放寬：監測/檢測/環評類不做
    if any(k in s for k in NOT_FIT):
        return None
    if any(k in s for k in SUPERVISE_KW) and any(k in s for k in SUPERVISE_REQ):
        return "🛡️ 工安環保查證"
    if any(k in s for k in LABOR_KW):
        return "👷 勞務／勤務"
    return None


MAX_BUDGET = 10_000_000  # 2026-11-03 使用者定案：督導／勞務／工安／環保一律 1,000 萬上限
WINDOW_DAYS = 7           # 2026-11-03：改列「近 7 日內」符合條件的案，不再只報當日新案
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
    env_n = 0

    for d in [today - dt.timedelta(days=i) for i in range(WINDOW_DAYS)]:
        try:
            rows = fetch_day(d)
        except Exception as e:
            errors.append(f"{d.isoformat()} {type(e).__name__}")
            continue
        scanned += len(rows)
        for org, name, day, recno in rows:
            if any(k in name for k in ENV_EXCLUDE):
                env_n += 1                     # 不放寬：僅計數揭露
                continue
            cat = classify(org, name)
            if not cat:
                continue
            reg = region_of(org, name)
            if cat == "👷 勞務／勤務" and reg != "中部":
                continue                       # 勞務／勤務只收中部
            if cat == "🛡️ 工安環保查證" and reg != "中部" and "台灣電力" not in org:
                continue                       # 工安環保查證：台電可跨全台，其他機關只收中部
            key = hashlib.md5(f"{org}|{name}".encode("utf-8")).hexdigest()[:16]
            is_new = key not in seen
            budget = None
            if len(lookups) < BUDGET_LOOKUP_CAP:
                lookups.append(name)
                budget = lookup_budget(name)
                if budget is not None and budget > MAX_BUDGET:
                    seen[key] = stamp      # 超過上限：記錄但不通知
                    continue
            if is_new:
                seen[key] = stamp
            fresh.append((cat, reg, org, name, day, budget, is_new))

    save_seen(seen)

    if scanned == 0:
        print("⚠️ 解析 0 筆（網站格式可能改版）", file=sys.stderr)
    if errors:
        print("⚠️ 抓取異常：" + "；".join(errors), file=sys.stderr)

    def _line(org: str, name: str, day: str, budget: int | None, is_new: bool) -> str:
        short = (org.replace("台灣電力股份有限公司", "⚡ 台電")
                    .replace("核能火力發電工程處", "核火工程處")
                    .replace("輸變電工程處", "輸變電處")
                    .replace("發電廠", "電廠"))
        amt = f"{budget / 10000:.0f} 萬" if budget else "金額待查"
        mark = "🆕" if is_new else "📌"
        return f"{mark} {amt}｜{short}｜{name[:56]}｜{day}"

    out = [f"🏗️ 中部標案日報 {stamp}（近 {WINDOW_DAYS} 日、≤1,000 萬；"
           f"掃 {scanned} 筆，環保監測類排除 {env_n} 筆）"]
    for cat in ("🛡️ 工安環保查證", "👷 勞務／勤務"):
        hits = [f for f in fresh if f[0] == cat]
        # 新案優先、金額已知者優先、日期新者優先
        hits.sort(key=lambda f: (f[6], f[5] is not None, str(f[4])), reverse=True)
        if not hits:
            out.append(f"{cat}：今日無符合條件案件")
            continue
        out.append(f"{cat}：{len(hits)} 筆")
        for c_, reg, org, name, day, budget, is_new in hits[:12]:
            out.append("・" + _line(org, name, day, budget, is_new))
        if len(hits) > 12:
            out.append(f"（另有 {len(hits) - 12} 筆，請至採購網查）")
    out.append("→ 🆕 今日新案・📌 先前已報（近 "
               f"{WINDOW_DAYS} 日內）｜金額明細：https://www.taiwanbuying.com.tw/"
               f"Query_Dateaction.ASP?yy={today.year - 1911}&mm={today.month}&dd={today.day}")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
