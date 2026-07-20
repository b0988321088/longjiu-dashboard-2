"""龍九週報 — 每週五 19:00，往前比較 7 天"""
import sqlite3, json, sys, os
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
TG_TOKEN = TG_CHAT_ID = ""
env = BASE / ".env"
if env.exists():
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("TG_TOKEN="): TG_TOKEN = line.split("=",1)[1].strip()
        if line.startswith("TG_CHAT_ID="): TG_CHAT_ID = line.split("=",1)[1].strip()

TODAY = date.today()
AGO7 = TODAY - timedelta(days=7)
WEEK_TAG = f"{AGO7} ~ {TODAY}"

db = sqlite3.connect(str(BASE / "dragon_assets.db"))
db.row_factory = sqlite3.Row
all_rows = db.execute("SELECT * FROM assets ORDER BY date").fetchall()
liab_row = db.execute("SELECT total_liabilities FROM liabilities ORDER BY date DESC LIMIT 1").fetchone()
db.close()
liabilities = liab_row[0] if liab_row else 17_199_287

rows = [r for r in all_rows if r["date"] and AGO7 <= date.fromisoformat(r["date"]) <= TODAY]
if len(rows) < 2:
    print("資料不足"); exit(1)

base = None
for r in all_rows:
    if r["date"] and AGO7.isoformat() >= r["date"]: base = r
    elif r["date"] and r["date"] > AGO7.isoformat(): break
if not base: base = all_rows[0] if all_rows else rows[0]

latest = rows[-1]
nw = latest["total_assets"] - liabilities

CATS = [("securities","證券","📈"),("insurance","保單","📋"),("funds","基金","💰"),("cash_total","現金","💵"),("bonds","債券","🏦"),("total_assets","總資產","📊")]
changes = [(ic, lab, base[k] or 0, latest[k] or 0, (latest[k] or 0)-(base[k] or 0), ((latest[k] or 0)-(base[k] or 0))/max(base[k] or 1,1)*100) for k,lab,ic in CATS]

snap = {}
if (BASE / "snapshot.json").exists(): snap = json.loads((BASE / "snapshot.json").read_text("utf-8"))
div_total = snap.get("monthly_dividend", 89_400)
div_fj33 = snap.get("actual_fj33_dividend", 9_356)

ANOMALY_NOTES = {"bonds":"⚠️ 穿透校準調整（非真實損益）","funds":"ℹ️ 鉅亨平台完整匯入","insurance":"ℹ️ 以截圖校正為準"}
anomalies = []
for k,lab,ic in CATS[:5]:
    ic2 = next(x[0] for x in changes if x[0]==ic) if any(x[0]==ic for x in changes) else ""
    ov = base[k] or 0; nv = latest[k] or 0; d = nv-ov; p = (d/ov*100) if ov else 0
    note = ANOMALY_NOTES.get(k,"")
    if abs(p)>10: anomalies.append((ic, lab, ov, nv, d, p, note))

tv = [r["total_assets"] or 0 for r in rows]
td = [r["date"][-5:] for r in rows]
inv_v = [(r["securities"] or 0)+(r["insurance"] or 0)+(r["funds"] or 0)+(r["bonds"] or 0)+(r["cash_total"] or 0) for r in rows]

def fm(v): return f"{v:,.0f}" if isinstance(v,(int,float)) else "-"
def fp(v): return f"{v:+.1f}%" if isinstance(v,(int,float)) else "-"

CAT_KEYS = ["securities","insurance","funds","cash_total","bonds"]
CAT_COLORS = {"securities":"#3b82f6","insurance":"#f59e0b","funds":"#14b8a6","cash_total":"#10b981","bonds":"#8b5cf6"}
CAT_LABELS = {"securities":"證券","insurance":"保單","funds":"基金","cash_total":"現金","bonds":"債券"}

max_inv = max(inv_v) if inv_v else 1

# Build 7-day stacked bars
stacked_bars = ""
for i, r in enumerate(rows):
    day_total = inv_v[i]
    bar_h = int(day_total / max_inv * 140)
    d = td[i]
    is_today = (i == len(rows)-1)
    border = 'border:1px solid #60a5fa;border-bottom:none' if is_today else ''
    opacity = '0.95' if is_today else '0.7'
    
    segs = ""
    for ck in reversed(CAT_KEYS):
        val = r[ck] or 0
        h = int(val / max(day_total, 1) * bar_h)
        if h > 0:
            segs += f'<div style="height:{h}px;background:{CAT_COLORS[ck]};opacity:{opacity};width:100%;border-radius:1px"></div>'
    
    stacked_bars += f'<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;min-width:16px;{border};position:relative">{segs}<div style="font-size:7px;color:#6b7280;text-align:center;position:absolute;bottom:-14px;width:100%;white-space:nowrap">{d}</div></div>'

legend = "".join(f'<span style="color:{CAT_COLORS[ck]};font-weight:600">■</span> {CAT_LABELS[ck]} ' for ck in CAT_KEYS)

html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>龍九週報 {TODAY}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,'Segoe UI','Noto Sans TC',sans-serif;background:#0a0e1a;color:#e2e8f0;padding:14px}}
.h{{text-align:center;padding:20px 0 10px}}
.h h1{{font-size:20px;font-weight:700;color:#fff}}
.h .s{{font-size:11px;color:#6b7280;margin-top:3px}}
.c{{background:#111827;border-radius:12px;padding:14px;margin-bottom:10px;border:1px solid #1f2937}}
.ct{{font-size:13px;font-weight:600;color:#9ca3af;margin-bottom:8px}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{text-align:left;padding:6px 3px;color:#6b7280;border-bottom:1px solid #1f2937;font-weight:500}}
td{{padding:6px 3px;border-bottom:1px solid #1a1f2e}}
.n{{text-align:right;font-family:'SF Mono',monospace}}
.g{{color:#10b981}}.r{{color:#ef4444}}.w{{color:#f59e0b}}
.sg{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:10px}}
.si{{background:#1a1f2e;border-radius:8px;padding:8px;text-align:center}}
.si .v{{font-size:16px;font-weight:700;font-family:'SF Mono';margin:3px 0}}
.si .l{{font-size:9px;color:#6b7280}}
.ar{{background:#7f1d1d;border:1px solid #ef4444;color:#fca5a5;padding:8px;border-radius:8px;font-size:11px;margin-bottom:6px}}
.ay{{background:#713f12;border:1px solid #d97706;color:#fde68a;padding:8px;border-radius:8px;font-size:11px;margin-bottom:6px}}
.ag{{background:#064e3b;border:1px solid #059669;color:#6ee7b7;padding:8px;border-radius:8px;font-size:11px;margin-bottom:6px}}
.note{{font-size:9px;color:#6b7280;margin-top:2px}}
.buffett{{font-size:11px;line-height:1.6;color:#d1d5db}}
.buffett h3{{color:#f59e0b;font-size:12px;margin-bottom:5px;margin-top:8px}}
.buffett li{{margin-bottom:3px;margin-left:14px}}
.section-desc{{font-size:10px;color:#6b7280;margin-bottom:8px}}
</style></head>
<body>
<div class="h"><h1>📊 龍九週報</h1><div class="s">{WEEK_TAG} · 七日變動</div></div>

<div class="sg">
<div class="si"><div class="l">總資產</div><div class="v" style="color:#60a5fa">{fm(latest["total_assets"])}</div><div class="l" style="color:{"#10b981" if latest["total_assets"]>=base["total_assets"] else "#ef4444"}">{fp((latest["total_assets"]-base["total_assets"])/max(base["total_assets"],1)*100)}</div></div>
<div class="si"><div class="l">投資部位</div><div class="v" style="color:#14b8a6">{fm(inv_v[-1])}</div><div class="l" style="color:{"#10b981" if inv_v[-1]>=inv_v[0] else "#ef4444"}">{fp((inv_v[-1]-inv_v[0])/max(inv_v[0],1)*100)}</div></div>
<div class="si"><div class="l">本月配息</div><div class="v" style="color:#f59e0b">{fm(div_total)}</div><div class="l">FJ33 {fm(div_fj33)}</div></div>
</div>

<div class="c"><div class="ct">📊 七日資產走勢（各色塊 = 類別佔比）</div>
<div class="section-desc">每柱為當日投資部位總值，色塊由下至上：證券(藍)、保單(黃)、基金(青)、現金(綠)、債券(紫)</div>
<div style="display:flex;align-items:flex-end;gap:3px;height:170px;padding:4px">
{stacked_bars}
</div>
<div style="text-align:center;font-size:9px;color:#6b7280;margin-top:10px">{legend}</div>
</div>

<div class="c"><div class="ct">📋 七日變化對照</div>
<table><tr><th>類別</th><th class="n">7天前</th><th class="n">今日</th><th class="n">增減</th><th class="n">變幅</th></tr>"""
for ic, lab, ov, nv, d, p in changes:
    c = "g" if d>0 else ("r" if d<0 else "")
    a = "▲" if d>0 else ("▼" if d<0 else "—")
    html += f'<tr><td>{ic} {lab}</td><td class="n">{fm(ov)}</td><td class="n">{fm(nv)}</td><td class="n {c}">{a} {fm(abs(d))}</td><td class="n {c}">{fp(p)}</td></tr>'
html += '</table></div>'

html += '<div class="c"><div class="ct">🚨 顯著變動</div>'
if anomalies:
    for ic, lab, ov, nv, d, p, note in anomalies:
        cls = "ar" if d<0 else "ay"
        html += f'<div class="{cls}">{ic} {lab} {fp(p)}（{fm(ov)}→{fm(nv)}）'
        if note: html += f'<div class="note">{note}</div>'
        html += '</div>'
else: html += '<div class="ag">✅ 七日內無顯著變動</div>'
html += '</div>'

html += f"""<div class="c"><div class="ct">📌 本週配息</div>
<table><tr><th>來源</th><th>金額</th><th>狀態</th></tr>
<tr><td>安聯 A+B 月配</td><td class="n g">55,451</td><td>✅ 7/09-10</td></tr>
<tr><td>第一金 FL65</td><td class="n g">13,593</td><td>✅ 7/08</td></tr>
<tr><td>摩根 FJ33</td><td class="n g">{fm(div_fj33)}</td><td>✅ 7/20</td></tr>
<tr><td>基金配息</td><td class="n g">~11,000</td><td>✅ 7/14-15</td></tr>
<tr><td colspan="1" style="font-weight:600">合計</td><td class="n" style="font-weight:600">{fm(div_total)}</td><td></td></tr>
</table></div>"""

total_ch = latest["total_assets"] - base["total_assets"]
invest_ch = inv_v[-1] - inv_v[0]
cash_m = int(latest["cash_total"] / 141958) if latest["cash_total"] else 0

html += f"""<div class="c"><div class="ct">🧓 巴菲特七日審查</div><div class="buffett">
<h3>📊 資產變動</h3><ul>
<li>總資產 {fm(latest["total_assets"])}（{fp(total_ch/max(base["total_assets"],1)*100)}）</li>
<li>投資部位 {fm(inv_v[-1])}（{fp(invest_ch/max(inv_v[0],1)*100)}），扣不動產</li>
<li>主要動因：{"穿透校正 + 鉅亨匯入" if abs(invest_ch)>200000 else "證券加碼 + 租金入帳"}</li></ul>
<h3>💡 安全邊際</h3><ul>
<li>現金 {fm(latest["cash_total"])} → {cash_m} 個月</li>
<li>保單 {fm(latest["insurance"])} / 證券 {fm(latest["securities"])} / 負債比 {fm(liabilities/max(latest["total_assets"],1)*100)}%</li></ul>
<h3>🎯 策略</h3><ul>
<li>{'🔴 微幅下跌（系統校正）' if invest_ch<0 else '🟢 投資部位略增'}</li>
<li>{'🟢 現金充裕' if latest["cash_total"]>141958*6 else '🟡 現金需關注'}</li>
<li>📌 機會子彈：{cash_m} 個月</li></ul></div></div>

<div style="text-align:center;font-size:10px;color:#374151;padding:12px 0">龍九週報 · {WEEK_TAG} · SSoT: dragon_assets.db</div>
</body></html>"""

out = BASE / f"weekly_report_{TODAY}.html"
out.write_text(html, encoding="utf-8")
print(f"✅ {out} ({out.stat().st_size:,} bytes)")

import subprocess as sp
sp.run(["git","add",str(out.name)], cwd=str(BASE), capture_output=True)
sp.run(["git","add","weekly_report.py"], cwd=str(BASE), capture_output=True)
sp.run(["git","commit","-m",f"weekly v3 {TODAY}","--allow-empty"], cwd=str(BASE), capture_output=True)
r = sp.run(["git","push","--force","origin","main:clean-main"], cwd=str(BASE), capture_output=True, text=True, timeout=30)
print(f"📤 {'ok' if 'force' in (r.stderr or r.stdout or '') else 'fail'}")

if TG_TOKEN and TG_CHAT_ID:
    import requests as req
    msg = f"📊 龍九週報 {WEEK_TAG}\n投資部位 {fm(inv_v[-1])}（{fp(invest_ch/max(inv_v[0],1)*100)}）\n現金 {fm(latest['cash_total'])} · 配息 {fm(div_total)}\n🔗 https://b0988321088.github.io/longjiu-dashboard-2/weekly_report_{TODAY}.html"
    try: req.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": msg}, timeout=10)
    except: pass
