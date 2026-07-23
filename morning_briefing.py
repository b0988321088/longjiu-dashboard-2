#!/usr/bin/env python3
"""morning_briefing.py — 每日晨間簡報
產出「今天跟昨天哪裡不一樣」的通知，不是固定數字"""

import json, csv, re
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)

def load_json(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def main():
    snap = load_json(BASE / "snapshot.json")
    hist = load_json(BASE / "asset_diff_history.json")
    lines = []
    
    # 1. 昨日資產變化
    yd = YESTERDAY.isoformat()
    td = TODAY.isoformat()
    today_key = td if td in hist else yd
    yesterday_key = yd if yd in hist else None
    
    if yesterday_key and today_key in hist:
        y = hist[yesterday_key]
        t = hist[today_key]
        changes = []
        for key, label in [("securities_market","證券"), ("insurance_current","保單"), ("fund_market","基金"), ("cash","現金"), ("total_assets","總資產"), ("total_liabilities","總負債")]:
            yv = y.get(key, 0) or 0
            tv = t.get(key, 0) or 0
            diff = tv - yv
            if abs(diff) > 1000:
                arrow = "▲" if diff > 0 else "▼"
                changes.append(f"{label} {arrow} {abs(diff):,.0f}")
        if changes:
            lines.append(f"📊 **昨日資產變化**（{yesterday_key} → {today_key}）")
            for c in changes[:5]:
                lines.append(f"  {c}")
    
    # 2. 今日待辦（從 relay_calendar）
    try:
        rc = (BASE / "relay_calendar.md").read_text(encoding="utf-8")
        today_str = f"{TODAY.month}/{TODAY.day}"
        todos = []
        # 信用卡
        cc = snap.get("credit_card", {})
        for bank, amt in cc.items():
            lines.append(f"  💳 {bank} 待繳 {amt:,}")
        # relay 截止
        for m in re.finditer(r'\|(.+?)\|(\d+/\d+)\(', rc):
            name = m.group(1).strip()
            date_str = m.group(2)
            if date_str == today_str and name not in ("基金", "基金名稱"):
                lines.append(f"  ⏰ {name} T+4截止日")
        # MB 信用卡
        try:
            src = [p for p in sorted((BASE / "moneybook").glob("Moneybook_帳單_*_1.csv"))][-1]
            for row in csv.DictReader(src.read_text(encoding="utf-8-sig").split('\n')):
                due = row.get("繳費截止日","").strip()
                bank = row.get("銀行","") or row.get("金融機構","")
                amt = float(row.get("金額",0) or 0)
                if due == today_str and amt > 0:
                    lines.append(f"  💳 {bank} 繳款截止 {amt:,.0f}")
        except: pass
    except: pass
    
    # 3. 異常（穿透偏差 >10%）
    pen = snap.get("penetration", {})
    apct = pen.get("actual_pct", {})
    for key, label, tgt in [("台股市值型成長","台股",30),("美股市值型成長","美股",30),("防守型配息","防守",25),("債券及安全現金","債+現",10)]:
        act = apct.get(key, 0)
        if tgt > 0 and abs(act - tgt) > 10:
            direction = "超標 ▲" if act > tgt else "偏低 ▼"
            lines.append(f"  ⚠️ 配置偏差：{label} {act:.0f}%（目標 {tgt}%）{direction}")
    
    # 4. 近3日事件
    try:
        rc3 = (BASE / "relay_calendar.md").read_text(encoding="utf-8")
        upcoming = []
        for m in re.finditer(r'\|\s*([^|]+?)\s*\|\s*(\d+/\d+)\(', rc3):
            name = m.group(1).strip()
            ds = m.group(2)
            if name not in ("基金", "基金名稱"):
                month, day = ds.split("/")
                d = date(TODAY.year, int(month), int(day))
                delta = (d - TODAY).days
                if 0 <= delta <= 3:
                    upcoming.append(f"  📅 {ds} {name}")
        if upcoming:
            lines.append(f"📅 **近3日事件**")
            lines.extend(upcoming[:5])
    except: pass
    
    # 5. FIRE 進度
    mdb = snap.get("monthly_dividend_breakdown", {})
    ins = mdb.get("allianz",0)+mdb.get("firstjin",0)
    etf = mdb.get("etf",0)
    fund = mdb.get("fund",0)
    rent = snap.get("rent_monthly_actual", 80100)
    total_income = ins + etf + fund + rent
    basic = 141958
    lines.append(f"")
    lines.append(f"🎯 FIRE 進度：{total_income/basic*100:.1f}%（基本已達標{'🎉' if total_income>=basic else '🔄'}）")
    
    # 組裝
    title = f"☀️ **龍九晨間簡報 — {TODAY}**"
    if len(lines) > 1:
        msg = title + "\n\n" + "\n".join(lines)
    else:
        msg = title + "\n\n✅ 今日無異常，所有項目正常。"
    
    print(msg)

if __name__ == "__main__":
    main()
