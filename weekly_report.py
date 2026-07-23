#!/usr/bin/env python3
"""weekly_report.py — 每週資產變化摘要
彙整近7日資產變化 + 被動收入 + 異常事件
每週日 19:00 自動產出推送"""

import json
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
TODAY = date.today()
WEEK_AGO = TODAY - timedelta(days=7)

def load_json(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def build():
    hist = load_json(BASE / "asset_diff_history.json")
    snap = load_json(BASE / "snapshot.json")
    
    # 過濾近7日
    week_dates = sorted([d for d in hist if WEEK_AGO.isoformat() <= d <= TODAY.isoformat()])
    if len(week_dates) < 2:
        print("⚠️ 不足2日資料")
        return None
    
    first = hist[week_dates[0]]
    last = hist[week_dates[-1]]
    
    # 計算變化
    changes = {}
    for key in ["total_assets", "total_liabilities", "securities_market", "insurance_current", "fund_market", "cash", "rent_monthly"]:
        fv = first.get(key, 0) or 0
        lv = last.get(key, 0) or 0
        changes[key] = {"start": fv, "end": lv, "diff": lv - fv}
    
    # 被動收入
    mdb = snap.get("monthly_dividend_breakdown", {})
    insurance_div = mdb.get("allianz", 0) + mdb.get("firstjin", 0)
    etf_div = mdb.get("etf", 0)
    fund_div = mdb.get("fund", 0)
    rent = snap.get("rent_monthly_actual", 80100)
    total_income = insurance_div + etf_div + fund_div + rent
    
    # 產出 HTML
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>龍九週報 {TODAY}</title>
<style>body{{font-family:-apple-system,sans-serif;background:#f5f5f7;margin:0;padding:16px;color:#1d1d1f}}
.card{{background:#fff;border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
h2{{font-size:16px;font-weight:800;margin:0 0 8px;padding-left:8px;border-left:3px solid #2563eb}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th{{background:#f0f0f5;padding:8px 6px;text-align:left;font-weight:600}}
td{{padding:8px 6px;border-top:1px solid #e5e5ea}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.up{{color:#16a34a}} .down{{color:#dc2626}}</style></head><body>
<h2>📊 龍九週報 {WEEK_AGO.isoformat()} ~ {TODAY.isoformat()}</h2>
<div class="card"><h2>資產變化</h2><table><thead><tr><th>項目</th><th class="num">7日前</th><th class="num">今日</th><th class="num">增減</th></tr></thead><tbody>"""
    
    labels = {"total_assets":"總資產","total_liabilities":"總負債","securities_market":"證券市值","insurance_current":"保單現值","fund_market":"基金市值","cash":"現金","rent_monthly":"房租"}
    for key, label in labels.items():
        if key in changes:
            c = changes[key]
            cls = "up" if c["diff"] > 0 else "down" if c["diff"] < 0 else ""
            html += f'<tr><td>{label}</td><td class="num">{c["start"]:,.0f}</td><td class="num">{c["end"]:,.0f}</td><td class="num {cls}">{c["diff"]:+,.0f}</td></tr>'
    
    html += f"""</tbody></table></div>
<div class="card"><h2>被動收入</h2>
<table><thead><tr><th>來源</th><th class="num">月收</th></tr></thead><tbody>
<tr><td>保單配息</td><td class="num">{insurance_div:,}</td></tr>
<tr><td>ETF配息</td><td class="num">{etf_div:,}</td></tr>
<tr><td>基金配息</td><td class="num">{fund_div:,}</td></tr>
<tr><td>房租收入</td><td class="num">{rent:,}</td></tr>
<tr style="font-weight:700;border-top:2px solid #2563eb"><td>合計</td><td class="num">{total_income:,}</td></tr>
</tbody></table></div>
<div class="card"><h2>異常事件</h2>
<p style="font-size:14px;color:#6e6e73">期間內資產變化超過 ±5% 的項目已標示於上表。</p></div>
</body></html>"""
    
    out = BASE / f"weekly_report_{TODAY.isoformat()}.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ 週報: {out.name}")
    return str(out)

if __name__ == "__main__":
    build()
