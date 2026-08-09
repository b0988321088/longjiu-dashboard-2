#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""notion_weekly_trend_wrapper.py — 每週日 10:00 資產趨勢報告
優先讀取本機 dragon_assets.db assets 表（數字與日報一致）；
若 DB 無資料，fallback 查詢 Notion master_ledger。
輸出：淨資產趨勢、主要變動來源、異常提醒（±5%）、一句話結論。
"""
import json, os, sys, sqlite3, urllib.request
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

def report_from_db(rows):
    """從 DB rows 產出趨勢報告（數字與日報一致）"""
    rows = sorted(rows, key=lambda r: r["date"])
    print("=" * 60)
    print(f"📊 龍九控股資產趨勢（dragon_assets.db 真值，最近 {len(rows)} 天）")
    print(f"📅 查詢日: {date.today()}")
    print("=" * 60)
    print(f"{'日期':<12} {'總資產':>14} {'現金':>12} {'證券':>12} {'變動':>12} {'%':>7}")
    prev = None
    anomalies = []
    for r in rows:
        t = float(r["total_assets"] or 0)
        cash = float(r["cash_total"] or 0)
        sec = float(r["securities"] or 0)
        d = r["date"][:10]
        if prev is not None:
            diff = t - prev
            pct = diff / prev * 100
            flag = "🔴" if abs(pct) >= 5 else ""
            if abs(pct) >= 5:
                anomalies.append((d, pct))
            print(f"{d:<12} {t:>14,.0f} {cash:>12,.0f} {sec:>12,.0f} {diff:>+12,.0f} {pct:>+6.1f}% {flag}")
        else:
            print(f"{d:<12} {t:>14,.0f} {cash:>12,.0f} {sec:>12,.0f} {'(基準)':>12}")
        prev = t

    latest, earliest = rows[-1], rows[0]
    net_change = float(latest["total_assets"]) - float(earliest["total_assets"])
    net_pct = net_change / float(earliest["total_assets"]) * 100
    print(f"\n▶ 期間淨變動: {net_change:+,.0f}（{net_pct:+.1f}%）")

    print("\n▶ 主要類別變動（最新 vs 最舊）：")
    for label, key in [("現金", "cash_total"), ("證券", "securities"),
                       ("保險", "insurance"), ("基金", "funds"), ("負債", "total_liabilities")]:
        v1 = float(latest.get(key) or 0)
        v0 = float(earliest.get(key) or 0)
        dd = v1 - v0
        if abs(dd) > 100:
            print(f"   {label}: {v0:,.0f} → {v1:,.0f}（{dd:+,.0f}）")

    if anomalies:
        print("\n🚨 異常提醒（單日變動 ≥±5%）：")
        for d, p in anomalies:
            print(f"   {d}: {p:+.1f}%")
    else:
        print("\n✅ 無異常（單日變動皆 <±5%）")

    trend = "上升" if net_change > 0 else ("下降" if net_change < 0 else "持平")
    print(f"\n📌 結論：最近 {len(rows)} 天資產{trend}（{net_change:+,.0f}，{net_pct:+.1f}%）。")
    print("=" * 60)

if __name__ == "__main__":
    main()
