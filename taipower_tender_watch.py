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
LABOR_KW = ("勤務",)          # 2026-11-03：只收「勤務類勞務性工作」型（如 116年度勤務類勞務性工作）
LABOR_REQ = ("勞務",)
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
    if any(k in s for k in LABOR_KW) and any(k in s for k in LABOR_REQ):
        return "👷 勞務／勤務"
    return None


MAX_BUDGET = 10_000_000  # 2026-11-03 使用者定案：督導／勞務／工安／環保一律 1,000 萬上限
WINDOW_DAYS = 7           # 2026-11-03：改列「近 7 日內」符合條件的案，不再只報當日新案
BUDGET_LOOKUP_CAP = 20    # 2026-11-03 使用者同意：每輪最多查 20 筆金額（原 8 筆）


def _http(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")


def lookup_budget(name: str, org: str = "") -> int | None:
    """用 acebidx 關鍵字搜尋對應標案並抓預算金額。

    2026-11-03 修：acebidx 同一案名會有多個機關版本（各電廠「勤務類勞務性工作」），
    只比對前 10 字會抓到別機關的金額 → 誤判超上限而漏報。
    改為同時要求「案名關鍵字」與「機關識別字」都命中；比對不到回 None（寧可標金額待查）。
    """
    kw = name[:10]
    org_key = org.replace("台灣電力股份有限公司", "").replace("臺灣電力股份有限公司", "")[:6]
    try:
        s = _http("https://acebidx.com/zh-TW/docs/tender/T/by-keyword/" + urllib.parse.quote(kw))
        tid = None
        for href, body in re.findall(r'href="(/zh-TW/docs/tender/id/[^"]+)"[^>]*>(.{0,900}?)</a>', s, re.S):
            txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", htmlmod.unescape(body)))
            if kw not in txt:
                continue
            if org_key and org_key not in txt:
                continue
            tid = href
            break
        if not tid and org_key:
            # 退一步：不要求機關字，但案名頭尾都要命中（避免抓到別案）
            for href, body in re.findall(r'href="(/zh-TW/docs/tender/id/[^"]+)"[^>]*>(.{0,900}?)</a>', s, re.S):
                txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", htmlmod.unescape(body)))
                if name[:12] in txt and name[-8:] in txt:
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


ACE_BASE = "https://acebidx.com/zh-TW/docs/tender/T/by-keyword/"
ACE_ROW_RE = re.compile(r'href="(/zh-TW/docs/tender/id/[^"]+)"[^>]*>(.{0,900}?)</a>', re.S)
# 2026-11-03：勞務／勤務改掃 acebidx，才拿得到「等標期＋預算」；關鍵字涵蓋台電各廠勤務類寫法
ACE_LABOR_KW = ("勤務類勞務性工作", "勤務類", "事務類勞務性工作", "勤務類及清潔維護類")


def ace_rows(kw: str, max_pages: int = 6) -> dict[str, str]:
    """acebidx by-keyword 逐頁抓取（每頁 50 筆，分頁走路徑 /2 /3 …）。"""
    out: dict[str, str] = {}
    for pg in range(1, max_pages + 1):
        u = ACE_BASE + urllib.parse.quote(kw) + ("" if pg == 1 else f"/{pg}")
        try:
            raw = _http(u)
        except Exception:
            break
        new = 0
        for href, body in ACE_ROW_RE.findall(raw):
            tid = href.rstrip("/").split("/")[-1]
            if tid in out:
                continue
            out[tid] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", htmlmod.unescape(body)))
            new += 1
        if new == 0:
            break
    return out


def _ace_detail(tid: str) -> dict:
    """acebidx 詳情（預算／截止／履約地點）— 沿用 design_supervision_watch 的解析。"""
    try:
        import design_supervision_watch as _dd
        return _dd.fetch_detail(tid)
    except Exception:
        return {}


def _t2(s: str) -> str:
    """臺→台 正規化（taiwanbuying 用『臺中』、acebidx 用『台中』，不比對就會查無）。"""
    return s.replace("臺", "台").replace("　", " ")


def ace_lookup(name: str, org: str = "") -> tuple[int | None, str]:
    """用 acebidx 找同案（案名＋機關雙比對），回 (預算, 截止日字串)。

    2026-11-03：工安環保查證原本只靠 taiwanbuying 猜金額，查不到就列入，
    結果把 3,950 萬、1,142 萬這種超上限案也列進來。改為直接讀 acebidx 詳情。
    """
    n_name = _t2(name)
    org_key = _t2(org.replace("台灣電力股份有限公司", "")
                     .replace("臺灣電力股份有限公司", ""))[:6]
    tid = None
    for kw in (n_name[:12], n_name[:10], n_name[6:16]):
        if len(kw) < 6:
            continue
        try:
            rows = ace_rows(kw, max_pages=2)
        except Exception:
            rows = {}
        for t, txt in rows.items():
            ntxt = _t2(txt)
            if n_name[:8] not in ntxt:
                continue
            if org_key and org_key not in ntxt and "台灣電力" not in n_name:
                continue
            tid = t
            break
        if tid:
            break
    if not tid:
        return (None, "")
    d = _ace_detail(tid)
    return (d.get("budget"), str(d.get("deadline") or ""))


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
    over_general: list[tuple[int | None, str, str, str]] = []

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
            if cat != "🛡️ 工安環保查證":
                continue                       # 勞務／勤務改由 acebidx 掃（含等標期與預算）
            reg = region_of(org, name)
            if reg != "中部" and "台灣電力" not in org:
                continue                       # 工安環保查證：台電可跨全台，其他機關只收中部
            key = hashlib.md5(f"{org}|{name}".encode("utf-8")).hexdigest()[:16]
            is_new = key not in seen
            b_ace, dl_s = ace_lookup(name, org)
            try:
                import design_supervision_watch as _dd2
                dl = _dd2.parse_deadline(dl_s)
            except Exception:
                dl = None
            if dl and dl < dt.datetime.now(TZ):
                continue                       # 等標期已過 → 不列
            if b_ace and b_ace > MAX_BUDGET:
                if (b_ace, name, org, dl_s) not in over_general:
                    over_general.append((b_ace, name, org, dl_s))
                continue                       # 超過上限 → 僅揭露
            if is_new:
                seen[key] = stamp
            day_show = dl.strftime("%m/%d %H:%M") if dl else day
            fresh.append((cat, reg, org, name, day_show, b_ace, is_new))

    # ② 勞務／勤務：改掃 acebidx（有等標期與預算），能撈到 taiwanbuying 7 日視窗外的案
    ace_scanned = 0
    over_labor: list[tuple[int | None, str, str]] = []
    try:
        import design_supervision_watch as _dd
    except Exception:
        _dd = None
    if _dd is not None:
        now_dt = dt.datetime.now(TZ)
        for kw in ACE_LABOR_KW:
            for tid, txt in ace_rows(kw).items():
                if not ("勤務" in txt and "勞務" in txt):
                    continue
                if any(k in txt for k in ENV_EXCLUDE) or any(k in txt for k in NOT_FIT):
                    continue
                reg = region_of(txt, txt)
                if reg != "中部" and "台灣電力" not in txt:
                    continue
                ace_scanned += 1
                d2 = _ace_detail(tid)
                b = d2.get("budget")
                dl = _dd.parse_deadline(d2.get("deadline", ""))
                if dl and dl < now_dt:
                    continue                   # 已過等標期 → 不列
                name2 = re.sub(r"^\s*\d+\s+", "", txt)
                name2 = re.sub(r"\s*\d+月\d+日\s*公告\s*$", "", name2).strip()
                dls = dl.strftime("%m/%d %H:%M") if dl else "截止日未載"
                if b and b > MAX_BUDGET:
                    if (b, name2, dls) not in over_labor:
                        over_labor.append((b, name2, dls))
                    continue                   # 超過 1,000 萬 → 不列入，但下方揭露
                key = hashlib.md5(name2.encode("utf-8")).hexdigest()[:16]
                is_new = key not in seen
                if is_new:
                    seen[key] = stamp
                fresh.append(("👷 勞務／勤務", reg, "", name2, dls, b, is_new))

    save_seen(seen)

    if scanned == 0:
        print("⚠️ 解析 0 筆（網站格式可能改版）", file=sys.stderr)
    if errors:
        print("⚠️ 抓取異常：" + "；".join(errors), file=sys.stderr)

    def _line(org: str, name: str, day: str, budget: int | None, is_new: bool) -> str:
        short = (org.replace("台灣電力股份有限公司", "⚡ 台電")
                    .replace("核能火力發電工程處", "核火工程處")
                    .replace("輸變電工程處", "輸變電處")
                    .replace("發電廠", "電廠")) if org else ""
        amt = f"{budget / 10000:.0f} 萬" if budget else "金額未載"
        mark = "🆕" if is_new else "📌"
        mid = f"{short}｜" if short else ""
        return f"{mark} {amt}｜{mid}{name[:64]}｜{day}"

    out = [f"🏗️ 中部標案日報 {stamp}（≤1,000 萬；"
           f"taiwanbuying 掃 {scanned} 筆〔近 {WINDOW_DAYS} 日〕、"
           f"acebidx 勞務候選 {ace_scanned} 筆；環保監測類排除 {env_n} 筆）"]
    for cat in ("🛡️ 工安環保查證", "👷 勞務／勤務"):
        hits = [f for f in fresh if f[0] == cat]
        # 新案優先、金額已知者優先、日期新者優先
        hits.sort(key=lambda f: (f[6], f[5] is not None, str(f[4])), reverse=True)
        if not hits:
            out.append(f"{cat}：今日無符合條件案件")
            continue
        out.append(f"{cat}：{len(hits)} 筆")
        for c_, reg, org, name, day, budget, is_new in hits[:15]:
            out.append("・" + _line(org, name, day, budget, is_new))
        if len(hits) > 15:
            out.append(f"（另有 {len(hits) - 15} 筆，請至採購網查）")
    if over_labor:
        # 2026-11-03 使用者裁決：勞務／勤務一律 1,000 萬上限、保全／警衛勤務不納入
        #   （無保全業商業登記）→ 超過上限者僅列筆數與前 3 高，供確認「不是漏抓」
        over_labor.sort(key=lambda x: -(x[0] or 0))
        out.append(f"⛔ 勞務／勤務另有 {len(over_labor)} 筆超過 1,000 萬上限（依裁決不列入，僅供確認）")
        for b_, n_, d_ in over_labor[:3]:
            out.append(f"　・{b_/10000:.0f} 萬｜{n_[:52]}｜{d_}")
    if over_general:
        over_general.sort(key=lambda x: -(x[0] or 0))
        out.append(f"⛔ 工安環保查證另有 {len(over_general)} 筆超過 1,000 萬上限（依裁決不列入）")
        for b_, n_, o_, d_ in over_general[:3]:
            out.append(f"　・{b_/10000:.0f} 萬｜{o_.replace('台灣電力股份有限公司', '⚡ 台電')[:14]}"
                       f"｜{n_[:44]}｜{d_}")
    out.append("→ 🆕 今日新案・📌 先前已報｜工安環保查證＝taiwanbuying 近 "
               f"{WINDOW_DAYS} 日；勞務／勤務＝acebidx 等標期內（含預算）"
               "｜金額明細：https://www.taiwanbuying.com.tw/Query_Dateaction.ASP"
               f"?yy={today.year - 1911}&mm={today.month}&dd={today.day}")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
