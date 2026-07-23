#!/usr/bin/env python3
"""morning_briefing.py — 龍九晨間簡報
每日 08:30 動態推送：行事曆比對 + Gmail入帳 + 資產變化 + 市場情報 + FIRE
"""

import json, csv, subprocess, re, sqlite3
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
TODAY = date.today()
GAPI = Path.home() / "AppData/Local/hermes/skills/productivity/google-workspace/scripts/google_api.py"

def load_json(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def run_gapi(*args):
    try:
        r = subprocess.run(["python", str(GAPI)] + list(args), capture_output=True, text=True, timeout=15)
        out = r.stdout
        idx = out.find("[{")
        return json.loads(out[idx:]) if idx >= 0 else []
    except:
        return []

def get_asset_changes(hist):
    dates = sorted([d for d in hist if d <= TODAY.isoformat()])
    if len(dates) < 2: return []
    first, last = hist[dates[-2]], hist[dates[-1]]
    diffs = []
    for key, label in [("securities_market","證券"),("insurance_current","保單"),("fund_market","基金"),("cash","現金")]:
        yv, tv = (first.get(key,0) or 0), (last.get(key,0) or 0)
        d = tv - yv
        if abs(d) >= 1000:
            diffs.append(f"{label} {'▲' if d>0 else '▼'} {abs(d):,.0f}")
    liq = sum(last.get(k,0) or 0 for k in ["securities_market","insurance_current","fund_market","cash"])
    y_liq = sum(first.get(k,0) or 0 for k in ["securities_market","insurance_current","fund_market","cash"])
    ld = liq - y_liq
    if abs(ld) >= 10000:
        diffs.append(f"流動合計 {'▲' if ld>0 else '▼'} {abs(ld):,.0f}")
    return diffs

def get_calendar_events(run_gapi, days=0):
    ts = TODAY.isoformat()
    end_day = TODAY + timedelta(days=days)
    end_s = end_day.isoformat()
    ev = run_gapi("calendar","list","--start",f"{ts}T00:00:00+08:00","--end",f"{end_s}T23:59:59+08:00")
    return ev if isinstance(ev, list) else []

def format_events(events, with_time=True):
    out = []
    for e in events:
        if with_time:
            t = e.get("start",{}).get("dateTime","")[11:16] if e.get("start",{}).get("dateTime","") else "全天"
            out.append(f"  ⏰ {t} {e['summary']}")
        else:
            s = e.get("start",{}).get("date","") or e.get("start",{}).get("dateTime","")[:10]
            out.append(f"  📅 {s[-5:]} {e['summary']}")
    return out

def get_market_intel():
    try:
        h = load_json(BASE / "hunter_cache" / f"market_intel_{TODAY.isoformat()}.json")
        if not h:
            files = sorted((BASE / "hunter_cache").glob("market_intel_*.json"), reverse=True)
            if files: h = load_json(files[0])
        if not h: return []
        parts = []
        md = h.get("market_data", {})
        if md.get("台股加權"):
            parts.append(f"台股 {md['台股加權']}")
        if md.get("S&P500"):
            parts.append(f"美股 {md['S&P500']}")
        if md.get("費半"):
            parts.append(f"費半 {md['費半']}")
        return parts
    except:
        return []

def get_fire(snap):
    mdb = snap.get("monthly_dividend_breakdown", {})
    ins = mdb.get("allianz",0)+mdb.get("firstjin",0)
    etf = mdb.get("etf",0)
    fund = mdb.get("fund",0)
    rent = snap.get("rent_monthly_actual", 80100)
    total = ins+etf+fund+rent
    ideal = 300000
    basic = 141958
    lines = [f"  被動收入 {total:,} / 理想 {ideal:,}（{total/ideal*100:.1f}%{'🎉' if total>=ideal else '🔄'}）"]
    if total < ideal:
        lines.append(f"  缺口 {ideal-total:,}/月 | 基本已超越 {total/basic*100:.1f}% ✅")
    return lines

def main():
    snap = load_json(BASE / "snapshot.json")
    hist = load_json(BASE / "asset_diff_history.json")
    lines = []

    # 1. 昨日資產變化
    changes = get_asset_changes(hist)
    if changes:
        lines.append("📊 **昨日資產變化**")
        lines.append("  " + " | ".join(changes))

    # 2. 今日待辦（Google Calendar）
    today_ev = get_calendar_events(run_gapi)
    if today_ev:
        lines.append("")
        lines.append("📅 **今日待辦**")
        lines.extend(format_events(today_ev)[:5])

    # 3. Gmail 銀行入帳
    banks = ["sinopac","dbs","taishinbank","cathay","yuantabank","fubon","esun","nccc"]
    msgs = run_gapi("gmail","search",f"({' OR '.join(['from:'+b for b in banks])}) newer_than:1d","--max","5")
    deposits = []
    if msgs and isinstance(msgs, list):
        for m in msgs[:5]:
            deposits.append(f"  💰 {m.get('from','')[:25]} — {m.get('subject','')[:50]}")
    if deposits:
        lines.append("")
        lines.append("📧 **銀行入帳通知**")
        lines.extend(deposits[:3])

    # 4. 行事曆比對（relay vs Calendar）
    try:
        rc = (BASE / "relay_calendar.md").read_text(encoding="utf-8")
        week_ev = get_calendar_events(run_gapi, days=7)
        gc_names = [e["summary"] for e in week_ev]
        missing = []
        for m in re.finditer(r'\|\s*([^|]+?)\s*\|\s*(\d+/\d+)\(', rc):
            name, ds = m.group(1).strip(), m.group(2)
            if name in ("基金","基金名稱"): continue
            mth, dy = ds.split("/")
            d = date(TODAY.year, int(mth), int(dy))
            if 0 <= (d-TODAY).days <= 7:
                if not any(kw in g for g in gc_names for kw in [name[:4], name.replace(" ","")]):
                    missing.append(f"  ❌ {ds} {name}")
        if missing:
            lines.append("")
            lines.append("🔍 **行事曆比對**")
            lines.extend(missing[:3])
    except: pass

    # 5. 市場情報
    market = get_market_intel()
    if market:
        lines.append("")
        lines.append("📡 **市場情報**")
        lines.append("  " + " | ".join(market))

    # 6. 近3日提醒
    upcoming = []
    try:
        rc = (BASE / "relay_calendar.md").read_text(encoding="utf-8")
        for m in re.finditer(r'\|\s*([^|]+?)\s*\|\s*(\d+/\d+)\(', rc):
            name, ds = m.group(1).strip(), m.group(2)
            if name in ("基金","基金名稱"): continue
            mth, dy = ds.split("/")
            d = date(TODAY.year, int(mth), int(dy))
            if 1 <= (d-TODAY).days <= 3:
                upcoming.append(f"  📅 {ds} {name}")
    except: pass
    future_3d = get_calendar_events(run_gapi, days=3)
    for e in future_3d:
        s = e.get("start",{}).get("date","") or e.get("start",{}).get("dateTime","")[:10]
        if s != TODAY.isoformat():
            upcoming.append(f"  📅 {s[-5:]} {e['summary']}")
    if upcoming:
        lines.append("")
        lines.append("🔜 **近3日提醒**")
        for u in sorted(set(upcoming))[:5]:
            lines.append(u)

    # 7. FIRE 進度
    lines.append("")
    lines.append("🎯 **FIRE 進度**")
    lines.extend(get_fire(snap))

    # 輸出
    print(f"☀️ **龍九晨間簡報 — {TODAY}**" + "\n" + "\n".join(lines))

if __name__ == "__main__":
    main()
