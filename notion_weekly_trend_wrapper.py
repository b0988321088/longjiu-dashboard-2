#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""notion_weekly_trend_wrapper.py — 每週日 10:00 資產趨勢報告
優先讀取本機 dragon_assets.db assets 表（數字與日報一致）；
若 DB 無資料，fallback 查詢 Notion master_ledger。
輸出：淨資產趨勢、主要變動來源、異常提醒（±5%）、一句話結論。
"""
import json, sys, sqlite3, urllib.request
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_PATH = Path("C:/Users/bot/Desktop/longjiu_system/dragon_assets.db")
ENV = Path.home() / "AppData/Local/hermes/.env"

DB_ID = "39dfc735-d433-8153-9712-c8a0ee0ec846"  # master_ledger

def get_token():
    if not ENV.exists():
        return ""
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("NOTION_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"\'')
    return ""

def notion_query(db_id, token, days=7):
    """查詢 Notion database 最近 days 天資產記錄（明細級 master_ledger）"""
    since = (date.today() - timedelta(days=days)).isoformat()
    payload = {
        "filter": {"property": "更新日期", "date": {"on_or_after": since}},
        "sorts": [{"property": "更新日期", "direction": "descending"}],
        "page_size": 100,
    }
    req = urllib.request.Request(
        f"https://api.notion.com/v1/databases/{db_id}/query",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def extract_asset(row):
    """從 Notion page 提取資產（明細級 master_ledger：資產名稱/分類/即時餘額/更新日期）"""
    props = row.get("properties", {})
    out = {"date": "", "total": None, "name": "", "category": "", "balance": None}
    for k, v in props.items():
        t = v.get("type")
        if t == "title":
            out["name"] = "".join(r.get("plain_text", "") for r in v.get("title", []))
        elif k == "更新日期" and t == "date":
            out["date"] = (v.get("date") or {}).get("start", "")
        elif k == "分類" and t == "select":
            out["category"] = (v.get("select") or {}).get("name", "")
        elif k == "即時餘額" and t == "number":
            out["balance"] = v.get("number")
    return out

def load_from_db(days=14):
    """從本機 dragon_assets.db 讀取最近 N 天資產記錄（與日報同源）"""
    if not DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT date, total_assets, cash_total, securities, insurance, funds, "
            "total_liabilities FROM assets ORDER BY date DESC LIMIT ?",
            (days,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return None

def main():
    # === 優先本機 DB（數字與日報一致）===
    db_rows = load_from_db()
    if db_rows and len(db_rows) >= 2:
        report_from_db(db_rows)
        return

    # === Fallback：Notion master_ledger ===
    print("ℹ️ 本機 DB 無資料，改用 Notion master_ledger...")
    token = get_token()
    if not token:
        print("❌ 找不到 NOTION_TOKEN（.env 不存在或未設定）")
        sys.exit(1)
    try:
        data = notion_query(DB_ID, token)
    except Exception as e:
        print(f"❌ Notion API 呼叫失敗: {e}")
        sys.exit(1)

    results = data.get("results", [])
    if not results:
        print("ℹ️ 最近 7 天無 master_ledger 記錄（可能尚未同步）")
        sys.exit(0)

    rows = []
    for r in results:
        a = extract_asset(r)
        if a["balance"] is not None:
            rows.append(a)

    if not rows:
        print("ℹ️ master_ledger 有記錄但無法解析即時餘額")
        sys.exit(0)

    # 依日期+分類彙總
    from collections import defaultdict
    by_date = defaultdict(lambda: defaultdict(float))
    for a in rows:
        d = (a["date"] or "未知")[:10]
        by_date[d][a["category"]] += a["balance"]

    dates = sorted(by_date.keys(), reverse=True)
    print("=" * 60)
    print(f"📊 龍九控股 Notion master_ledger 資產趨勢（最近 {len(dates)} 天）")
    print(f"📅 查詢日: {date.today()}")
    print("=" * 60)

    # 每日總資產 = 資產類別加總（排除負債）
    daily_total = {}
    for d in dates:
        cats = by_date[d]
        total = sum(v for k, v in cats.items() if "負債" not in k and "貸款" not in k)
        daily_total[d] = total

    print(f"{'日期':<12} {'資產總值':>14} {'變動':>12} {'%':>7} {'類別數':>4}")
    prev = None
    anomalies = []
    for d in dates:
        t = daily_total[d]
        ncat = len(by_date[d])
        if prev is not None:
            diff = t - prev
            pct = diff / prev * 100
            flag = "🔴" if abs(pct) >= 5 else ""
            if abs(pct) >= 5:
                anomalies.append((d, pct))
            print(f"{d:<12} {t:>14,.0f} {diff:>+12,.0f} {pct:>+6.1f}% {flag} {ncat:>4}")
        else:
            print(f"{d:<12} {t:>14,.0f} {'(基準)':>12} {ncat:>4}")
        prev = t

    if len(dates) >= 2:
        latest, earliest = dates[0], dates[-1]
        net_change = daily_total[latest] - daily_total[earliest]
        net_pct = net_change / daily_total[earliest] * 100
        print(f"\n▶ 期間淨變動: {net_change:+,.0f}（{net_pct:+.1f}%）")

        print("\n▶ 主要類別變動（最新 vs 最舊）：")
        all_cats = set(by_date[latest]) | set(by_date[earliest])
        for c in sorted(all_cats):
            v1 = by_date[latest].get(c, 0)
            v0 = by_date[earliest].get(c, 0)
            d = v1 - v0
            if abs(d) > 100:
                print(f"   {c}: {v0:,.0f} → {v1:,.0f}（{d:+,.0f}）")

    if anomalies:
        print("\n🚨 異常提醒（單日變動 ≥±5%）：")
        for d, p in anomalies:
            print(f"   {d}: {p:+.1f}%")
    else:
        print("\n✅ 無異常（單日變動皆 <±5%）")

    print("\n📌 結論：")
    if len(dates) >= 2:
        trend = "上升" if net_change > 0 else ("下降" if net_change < 0 else "持平")
        print(f"   最近 {len(dates)} 天資產{trend}（{net_change:+,.0f}，{net_pct:+.1f}%）；"
              f"共 {len(rows)} 筆明細更新。")
    print("=" * 60)

# ===== 2026-10-09 新增：事件鏈判定（同口徑口徑修正）=====
# 背景（唯讀稽核 2026-10-09）：質押撥款、保單借貸清償等結構事件，其「資產腿」（現金轉出）
# 與「負債腿」（借款沖銷）入帳日不同（保單公司 3 個工作日入帳），常落在相鄰兩天。
# 兩天的單日跳變可能都未達 ≥10% 門檻 → 舊版「同口徑」只排除跳變日，漏掉中間那一天，
# 造成 2026-09-30 單日 −1,959,263 被誤計為損失（實為假性下降，兩日合計 +18,800）。
# 規則（三條件須同時成立，避免誤排除真實市場損失）：
#   1) 相鄰兩日淨值方向相反、金額對沖比 ≥ 80%（且 ≤ 125%）
#   2) 兩日「主導腿」不同：一日為資產腿主導、另一日為負債腿主導
#      → 市場漲跌造成的反向變動兩腿皆為資產腿，不會被排除
#   3) 兩日淨值變動絕對值皆 ≥ EVENT_CHAIN_MIN_AMOUNT（材料性門檻）
EVENT_CHAIN_OFFSET_RATIO = 0.80
EVENT_CHAIN_MIN_AMOUNT = 100_000.0
EVENT_CHAIN_LEG_SHARE = 0.60   # 主導腿須佔該日淨值變動 60% 以上
# 已知限制（2026-10-09 CIO 對抗性審查 required_fixes #3，非阻擋級）：本判定為啟發式。
# 當「真實負債惡化」與「隔日真實市場反彈」金額恰好落在對沖比 [0.80, 1.25] 且兩日皆
# ≥ EVENT_CHAIN_MIN_AMOUNT 時，該兩日會被整鏈排除（偽陽性）。比率趨近 1 時淨殘差近 0，
# 且大幅變動會先被 ≥10% 基準變動日規則攔截。若日後出現此型態，改為「只排除對沖量、
# 保留淨殘差」之實作，並補對應回歸測試。

def _dominant_leg(d_nw, d_ta, d_liab):
    """該日淨值變動主要由哪一腿驅動：'資產' / '負債' / None（無明顯主導腿）"""
    if not d_nw:
        return None
    if abs(d_ta or 0) >= abs(d_liab or 0) and abs(d_ta or 0) >= EVENT_CHAIN_LEG_SHARE * abs(d_nw):
        return "資產"
    if abs(d_liab or 0) > abs(d_ta or 0) and abs(d_liab or 0) >= EVENT_CHAIN_LEG_SHARE * abs(d_nw):
        return "負債"
    return None

def compute_daily_metrics(rows):
    """逐日指標 —— 結構日／資產腿／負債腿的唯一計算法源（勿在他處重算，避免口徑分歧）。
    負債缺資料的列＝不計淨值（沿用舊口徑），且不前進比較基準。
    回傳 {date: {date, ta, liab, nw, cash, d_nw, d_ta, d_liab, ta_jump, liab_jump, structural, leg}}
    """
    metrics = {}
    prev = None
    for r in sorted(rows, key=lambda x: (x.get("date") or "")[:10]):   # 防呆：一律依日期遞增（呼叫端可能傳 DESC）
        liab_raw = r.get("total_liabilities")
        ta = float(r["total_assets"] or 0)
        d = (r.get("date") or "")[:10]
        base = {"date": d, "ta": ta, "liab": None, "nw": None,
                "cash": float(r.get("cash_total") or 0),
                "d_nw": None, "d_ta": None, "d_liab": None,
                "ta_jump": 0.0, "liab_jump": 0.0, "structural": False, "leg": None}
        if liab_raw in (None, "", 0):
            metrics[d] = base
            continue
        liab = float(liab_raw)
        nw = ta - liab
        m = dict(base, liab=liab, nw=nw)
        if prev is not None:
            m["d_nw"] = nw - prev["nw"]
            m["d_ta"] = ta - prev["ta"]
            m["d_liab"] = liab - prev["liab"]
            m["ta_jump"] = abs(m["d_ta"]) / prev["ta"] * 100 if prev["ta"] else 0.0
            m["liab_jump"] = abs(m["d_liab"]) / prev["liab"] * 100 if prev["liab"] else 0.0
            # 資產或負債單日跳變 ≥10% = 基準變動（借款/撥款入帳、帳務重述），非市場損益
            m["structural"] = m["ta_jump"] >= 10 or m["liab_jump"] >= 10
            m["leg"] = _dominant_leg(m["d_nw"], m["d_ta"], m["d_liab"])
        metrics[d] = m
        prev = m
    return metrics

def detect_event_chains(metrics, structural_days=None):
    """偵測「事件鏈」：相鄰兩日反向對沖 ≥80% 且主導腿不同 → 同一結構事件分兩日入帳。
    回傳 [{"dates": [...], "first", "reverse", "ratio", "amount", "first_leg", "reverse_leg"}]
    並把緊鄰的基準變動日併入同一條鏈（僅供顯示與同口徑排除，判準不變）。
    """
    days = [m for m in metrics.values() if m["d_nw"] is not None]
    days.sort(key=lambda m: m["date"])
    chains = []
    for a, b in zip(days, days[1:]):
        d1, d2 = a["d_nw"], b["d_nw"]
        if not d1 or not d2 or (d1 > 0) == (d2 > 0):
            continue
        ratio = abs(d2) / abs(d1)
        if not (EVENT_CHAIN_OFFSET_RATIO <= ratio <= 1 / EVENT_CHAIN_OFFSET_RATIO):
            continue
        if abs(d1) < EVENT_CHAIN_MIN_AMOUNT or abs(d2) < EVENT_CHAIN_MIN_AMOUNT:
            continue
        if not a["leg"] or not b["leg"] or a["leg"] == b["leg"]:
            continue
        chains.append({"dates": [a["date"], b["date"]], "first": a["date"], "reverse": b["date"],
                       "ratio": ratio, "amount": abs(d1),
                       "first_leg": a["leg"], "reverse_leg": b["leg"]})
    merged = []
    for c in chains:
        if merged and c["dates"][0] in merged[-1]["dates"]:
            merged[-1]["dates"] = sorted(set(merged[-1]["dates"]) | set(c["dates"]))
            merged[-1]["reverse"] = c["reverse"]
            merged[-1]["reverse_leg"] = c["reverse_leg"]   # 同步更新，避免與 reverse 不一致
        else:
            merged.append(c)
    sd = set(structural_days or [])
    order = {m["date"]: i for i, m in enumerate(days)}
    for c in merged:
        dates = set(c["dates"])
        i, j = order.get(c["dates"][0]), order.get(c["dates"][-1])
        if i is not None and i - 1 >= 0 and days[i - 1]["date"] in sd:
            dates.add(days[i - 1]["date"])
        if j is not None and j + 1 < len(days) and days[j + 1]["date"] in sd:
            dates.add(days[j + 1]["date"])
        c["dates"] = sorted(dates)
    return merged

ASOF_KEYS = (("現金", r"^cash_source$"),
             ("證券", r"^securities_note_(\d{8})$"),
             ("基金", r"^(?:funds_cathay_note|heng_note|funds_note)_(\d{8})?$"),
             ("保單", r"^(?:allianz_note|firstjin_note)_(\d{8})$"))

def extract_asof(snapshot):
    """從 snapshot 註記鍵取各類別資料截至日（含註記內第一個 HH:MM），回傳 [(類別, YYYY-MM-DD, HH:MM, key)]"""
    import re
    out = []
    for label, pat in ASOF_KEYS:
        best = None
        for k, v in (snapshot or {}).items():
            m = re.match(pat, k)
            if not m:
                continue
            ds = m.group(1) if m.groups() else None
            if not ds and isinstance(v, dict):
                ds = str(v.get("date") or "").replace("-", "")
            ds = (ds or "").strip()
            if len(ds) == 4 and ds.isdigit():            # MMDD（如 funds_cathay_note_1008）→ 補當年
                ds = f"{date.today().year}{ds}"
            if not (len(ds) == 8 and ds.isdigit()):
                ds = ""
            txt = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
            if best is None or ds > best[0]:
                best = (ds, k, txt)
        if best and best[0]:
            ds, k, txt = best
            tm = re.search(r"(\d{2}:\d{2})", txt or "")
            out.append((label, f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}", tm.group(1) if tm else "", k))
    return out

def data_asof_line():
    """📅 各類別資料截至時間（唯讀讀 snapshot.json；缺檔回空字串）"""
    try:
        snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    except Exception:
        return ""
    parts = [f"{lb} {ymd}" + (f" {tm}" if tm else "") for lb, ymd, tm, _k in extract_asof(snap)]
    return "｜".join(parts)

def report_from_db(rows):
    """從 DB rows 產出趨勢報告（數字與日報一致）
    2026-08-23 改淨值口徑：借款入帳（如國泰 1,200萬 8/20）資產負債同步增，總資產會誤報 +81%；
    以淨值（總資產−總負債）計算變動/異常/結論。
    2026-09-06 增基準變動日處理：資產或負債單日跳變 ≥10%（借款入帳/帳務重述，如 8/20
    大義街1,200萬、8/11 負債重述）→ 該日標記 ⚠️基準變動、不列入 ±5% 異常；期間另印同口徑
    淨值變動（剔除跳進基準變動日的單日變動）；保險/基金類別附註非純市值損益。
    2026-10-09 增事件鏈處理（唯讀稽核後修正）：質押撥款、保單借貸清償等結構事件的「資產腿」
    與「負債腿」入帳日不同（保單公司 3 個工作日入帳），常落在相鄰兩日；兩日單日跳變可能都
    未達 ≥10%，舊版同口徑會把中間那天（2026-09-30 單日 −1,959,263）誤計成損失。
    → 改以 detect_event_chains() 偵測「相鄰反向對沖 ≥80% 且主導腿不同」的事件鏈，整鏈排除；
      真實市場漲跌（兩日皆資產腿主導）與對沖不足者不排除。另輸出各類別資料截至時間。
    判準常數：EVENT_CHAIN_*；回歸測試：tests/test_weekly_trend_event_chain.py。"""
    rows = sorted(rows, key=lambda r: r["date"])
    metrics = compute_daily_metrics(rows)   # 結構日/資產腿/負債腿：唯一計算法源（2026-10-09）
    # 基準變動日與事件鏈先算（逐日標記、異常排除、同口徑共用同一份結果，避免兩處重算）
    structural_all = [d for d, m in sorted(metrics.items()) if m["structural"]]
    chains = detect_event_chains(metrics, structural_all)
    chain_days = sorted({dt for c in chains for dt in c["dates"]})
    excluded = sorted(set(structural_all) | set(chain_days))
    print("=" * 60)
    print(f"📊 龍九控股資產趨勢（dragon_assets.db 真值，最近 {len(rows)} 天）")
    print(f"📅 查詢日: {date.today()}")
    print("=" * 60)
    print(f"{'日期':<12} {'總資產':>14} {'負債':>12} {'淨值':>12} {'現金':>12} {'淨值變動':>12} {'%':>7}")
    prev = None          # 前一有效列淨值
    prev_ta = None       # 前一有效列總資產
    prev_liab = None     # 前一有效列總負債
    anomalies = []
    structural_days = []  # 基準變動日：資產/負債結構性入帳或帳務重述（如 8/20 大義街1,200萬入帳）
    for r in rows:
        t = float(r["total_assets"] or 0)
        liab_raw = r.get("total_liabilities")
        if liab_raw in (None, "", 0):  # 缺資料（龍九恆有房貸/借款，0 = 未記錄）→ 淨值不計算
            nw = None
        else:
            nw = t - float(liab_raw)
        cash = float(r["cash_total"] or 0)
        d = r["date"][:10]
        if nw is None:
            print(f"{d:<12} {t:>14,.0f} {'缺資料':>12} {'?':>12} {cash:>12,.0f} {'(負債缺)':>12}")
            continue
        # 結構日／事件鏈判定一律取自 compute_daily_metrics（單一計算法源，勿在此重算）
        structural = bool((metrics.get(d) or {}).get("structural"))
        in_chain = d in chain_days
        if structural:
            structural_days.append(d)
        if prev is not None:
            diff = nw - prev
            pct = diff / abs(prev) * 100 if prev else 0
            is_anom = abs(pct) >= 5 and d not in excluded
            flag = "🔴" if is_anom else ("⚠️基準變動" if structural else ("🔗事件鏈" if in_chain else ""))
            if is_anom:
                anomalies.append((d, pct))
            print(f"{d:<12} {t:>14,.0f} {float(liab_raw):>12,.0f} {nw:>12,.0f} {cash:>12,.0f} {diff:>+12,.0f} {pct:>+6.1f}% {flag}")
        else:
            print(f"{d:<12} {t:>14,.0f} {float(liab_raw):>12,.0f} {nw:>12,.0f} {cash:>12,.0f} {'(基準)':>12}")
        prev, prev_ta, prev_liab = nw, t, float(liab_raw)

    latest, earliest = rows[-1], rows[0]
    def _nw(r): return float(r["total_assets"] or 0) - float(r.get("total_liabilities") or 0)
    net_change = _nw(latest) - _nw(earliest)
    net_pct = net_change / abs(_nw(earliest)) * 100 if _nw(earliest) else 0
    # 同口徑：剔除「基準變動日」與「事件鏈各日」的單日變動，避免結構入帳/帳務重述被當成績效
    # （chains／chain_days／excluded 已於逐日輸出前算出，此處不重算）
    excl_change = 0.0
    for i in range(len(rows) - 1):
        if rows[i + 1]["date"][:10] in excluded:
            continue
        excl_change += _nw(rows[i + 1]) - _nw(rows[i])
    has_ex = len(excluded) > 0 and excl_change != net_change
    if has_ex:
        excl_pct = excl_change / abs(_nw(earliest)) * 100 if _nw(earliest) else 0
        _overlap = len(set(structural_days) & set(chain_days))
        print(f"\n▶ 期間淨值變動: {net_change:+,.0f}（{net_pct:+.1f}%，已剔除聯集 {len(excluded)} 日"
              f"：基準變動 {len(structural_days)}／事件鏈 {len(chain_days)}／重疊 {_overlap}）")
        print(f"  ↳ 同口徑（不含基準變動日與事件鏈）: {excl_change:+,.0f}（{excl_pct:+.1f}%）")
    else:
        print(f"\n▶ 期間淨值變動: {net_change:+,.0f}（{net_pct:+.1f}%）")

    print("\n▶ 主要類別變動（最新 vs 最舊）：")
    cat_notes = []
    for label, key in [("現金", "cash_total"), ("證券", "securities"),
                       ("保險", "insurance"), ("基金", "funds"), ("負債", "total_liabilities")]:
        v1 = float(latest.get(key) or 0)
        v0 = float(earliest.get(key) or 0)
        dd = v1 - v0
        if abs(dd) > 100:
            print(f"   {label}: {v0:,.0f} → {v1:,.0f}（{dd:+,.0f}）")
            if key in ("insurance", "funds"):
                cat_notes.append(label)
    if cat_notes:
        print("  ※ " + "、".join(cat_notes) + " 類別含配息撥回/保單轉換/T+4重估與帳務校準，非純市值損益；")
        print("    負債增減含借款入帳與償還（基準變動日），非費用。")

    if anomalies:
        print("\n🚨 異常提醒（單日淨值變動 ≥±5%，基準變動日與事件鏈已排除）：")
        for d, p in anomalies:
            print(f"   {d}: {p:+.1f}%")
    else:
        print("\n✅ 無異常（單日淨值變動皆 <±5%，基準變動日與事件鏈已排除）")
    if structural_days:
        print("  🧱 基準變動日（資產/負債結構性入帳或帳務重述，非市場損益）："
              + "、".join(structural_days))
    if chains:
        print("  🔗 事件鏈（相鄰日反向對沖 ≥80%、資產腿／負債腿分屬不同日 → 同一結構事件分日入帳，非損益）：")
        for c in chains:
            m1 = metrics.get(c["first"]) or {}
            m2 = metrics.get(c["reverse"]) or {}
            resid = float(m1.get("d_nw") or 0) + float(m2.get("d_nw") or 0)
            print(f"     {c['dates'][0]} ~ {c['dates'][-1]}：首日 {c['first']}（{c['first_leg']}腿主導）"
                  f"Δ資產 {float(m1.get('d_ta') or 0):+,.0f}／Δ負債 {float(m1.get('d_liab') or 0):+,.0f}；"
                  f"反轉日 {c['reverse']}（{c['reverse_leg']}腿主導）"
                  f"Δ資產 {float(m2.get('d_ta') or 0):+,.0f}／Δ負債 {float(m2.get('d_liab') or 0):+,.0f}；"
                  f"對沖比 {c['ratio'] * 100:.0f}%（兩腿互抵後淨差額 {resid:+,.0f}）")
        print("     ※ 事件鏈各日已整鏈排除；兩腿互抵後之淨差額亦不留在同口徑內（未對沖者才計入）。")
    print("  📅 各類別資料截至：" + (data_asof_line() or "（snapshot 註記不可讀）"))

    trend = "上升" if net_change > 0 else ("下降" if net_change < 0 else "持平")
    if has_ex:
        t2 = "上升" if excl_change > 0 else ("下降" if excl_change < 0 else "持平")
        print(f"\n📌 結論：最近 {len(rows)} 天含基準變動淨值{trend} {net_change:+,.0f}（{net_pct:+.1f}%）；"
              f"同口徑{t2} {excl_change:+,.0f}（{excl_pct:+.1f}%）"
              f"（已剔除 {len(excluded)} 日：{'、'.join(excluded)}）— 以同口徑為準。")
    else:
        print(f"\n📌 結論：最近 {len(rows)} 天淨值{trend}（{net_change:+,.0f}，{net_pct:+.1f}%）。")
    print("=" * 60)

if __name__ == "__main__":
    main()
