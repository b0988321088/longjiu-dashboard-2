"""龍九週報 — 每週五 19:00"""
import sqlite3, json, os
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
TG_TOKEN = ""
env_path = BASE / ".env"
if env_path.exists():
    for line in env_path.read_text("utf-8").splitlines():
        if line.startswith("TG_TOKEN="): TG_TOKEN = line.split("=",1)[1].strip()
        if line.startswith("TG_CHAT_ID="): TG_CHAT_ID = line.split("=",1)[1].strip()
    else:
        TG_CHAT_ID = ""

TODAY = date.today()
MON = TODAY - timedelta(days=TODAY.weekday())
WEEK = f"{MON} ~ {min(MON+timedelta(6), TODAY)}"

db = sqlite3.connect(str(BASE / "dragon_assets.db"))
db.row_factory = sqlite3.Row
rows = db.execute("SELECT * FROM assets ORDER BY date").fetchall()
liab = db.execute("SELECT * FROM liabilities ORDER BY date DESC LIMIT 1").fetchone()
db.close()

rows = [r for r in rows if r["date"]]
this_week = [r for r in rows if r["date"] >= str(MON)]
if len(this_week) < 2:
    this_week = rows[-7:] if len(rows) >= 7 else rows
first, last = this_week[0], this_week[-1]
prev_v = this_week[0]["total_assets"]  # use first day of week as baseline

liabilities = liab["total_liabilities"] if liab else 17199287
nw = last["total_assets"] - liabilities
nw_prev = this_week[0]["total_assets"] - liabilities

CATS = [
    ("securities", "證券", "📈"),
    ("insurance", "保單", "📋"),
    ("funds", "基金", "💰"),
    ("cash_total", "現金", "💵"),
    ("bonds", "債券", "🏦"),
    ("total_assets", "總資產", "📊"),
]
changes = []
for k, lab, ic in CATS:
    ov = first[k] or 0; nv = last[k] or 0
    d = nv - ov; p = (d/ov*100) if ov else 0
    changes.append((ic, lab, ov, nv, d, p))

# 決策
decs = []
f = BASE / "dashboard_decisions.json"
if f.exists():
    d = json.loads(f.read_text("utf-8"))
    for x in d.get("decisions",[]):
        if x.get("approved_at","")[:10] >= str(MON):
            decs.append((x.get("text","") or x.get("name","") or "")[:60])

# 趨勢
tv = [r["total_assets"] or 0 for r in this_week]
td = [r["date"][-5:] for r in this_week]
mx, mn = max(tv) if tv else 1, min(tv) if tv else 0
rg = mx - mn if mx != mn else 1

def fm(v): return f"{v:,.0f}" if isinstance(v,(int,float)) else str(v or "-")
def fp(v): return f"{v:+.1f}%" if isinstance(v,(int,float)) else "-"
anomalies = [f"{ic} {lab} 週變動 {fp(p)}（{fm(ov)}→{fm(nv)}）" for ic,lab,ov,nv,d,p in changes if abs(p)>10]

html = f'''<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>龍九週報 {TODAY}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,'Segoe UI','Noto Sans TC',sans-serif;background:#0a0e1a;color:#e2e8f0;padding:16px}}
.h{{text-align:center;padding:20px 0 12px}}
.h h1{{font-size:20px;font-weight:700;color:#fff}}
.h .s{{font-size:12px;color:#6b7280;margin-top:4px}}
.c{{background:#111827;border-radius:12px;padding:16px;margin-bottom:10px;border:1px solid #1f2937}}
.ct{{font-size:13px;font-weight:600;color:#9ca3af;margin-bottom:10px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{text-align:left;padding:6px 4px;color:#6b7280;border-bottom:1px solid #1f2937;font-weight:500}}
td{{padding:7px 4px;border-bottom:1px solid #1a1f2e}}
td.n,th.n{{text-align:right;font-family:'SF Mono',monospace}}
.g{{color:#10b981}} .r{{color:#ef4444}}
.sg{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.si{{background:#1a1f2e;border-radius:8px;padding:10px;text-align:center}}
.si .v{{font-size:18px;font-weight:700;font-family:'SF Mono';margin:4px 0}}
.si .l{{font-size:10px;color:#6b7280}}
.tr{{display:flex;align-items:flex-end;gap:3px;height:70px;padding:8px 0}}
.ba{{flex:1;background:linear-gradient(to top,#1e40af,#3b82f6);border-radius:3px 3px 0 0;min-width:10px;position:relative}}
.ba .lb{{position:absolute;bottom:-14px;left:50%;transform:translateX(-50%);font-size:7px;color:#6b7280;white-space:nowrap}}
.ar{{background:#7f1d1d;border:1px solid #ef4444;color:#fca5a5;padding:10px;border-radius:8px;font-size:12px;margin-bottom:8px}}
.ag{{background:#064e3b;border:1px solid #059669;color:#6ee7b7;padding:10px;border-radius:8px;font-size:12px;margin-bottom:8px}}
.ci{{font-size:11px;color:#9ca3af;padding:4px 0;border-bottom:1px solid #1a1f2e}}
.b{{font-size:12px;line-height:1.6;color:#d1d5db}}
.b h3{{color:#f59e0b;font-size:13px;margin-bottom:6px;margin-top:10px}}
.b h3:first-child{{margin-top:0}}
.b li{{margin-bottom:4px;margin-left:16px}}
</style></head>
<body>
<div class="h"><h1>📊 龍九週報</h1><div class="s">{WEEK}</div></div>

<div class="sg">
<div class="si"><div class="l">總資產</div><div class="v" style="color:#60a5fa">{fm(last["total_assets"])}</div><div class="l" style="color:{"#10b981" if last["total_assets"]>=prev_v else "#ef4444"}">較上週 {fp((last["total_assets"]-prev_v)/max(prev_v,1)*100)}</div></div>
<div class="si"><div class="l">淨值</div><div class="v" style="color:#10b981">{fm(nw)}</div><div class="l" style="color:{"#10b981" if nw>=nw_prev else "#ef4444"}">負債比 {fm(liabilities/max(last["total_assets"],1)*100)}%</div></div>
</div>

<div class="c"><div class="ct">📈 本週資產趨勢</div><div class="tr">'''
for i in range(len(tv)):
    pct = int((tv[i]-mn)/rg*75+5) if rg else 50
    html += f'<div class="ba" style="height:{pct}%"><div class="lb">{td[i]}</div></div>'
html += f'''</div><div style="font-size:10px;color:#6b7280;text-align:center;margin-top:10px">{fm(mn)} ~ {fm(mx)}</div></div>

<div class="c"><div class="ct">📋 資產變化</div><table><tr><th>類別</th><th class="n">上週</th><th class="n">本週</th><th class="n">增減</th><th class="n">增幅</th></tr>'''
for ic,lab,ov,nv,d,p in changes:
    c = "g" if d>0 else ("r" if d<0 else "")
    a = "▲" if d>0 else ("▼" if d<0 else "—")
    html += f'<tr><td>{ic} {lab}</td><td class="n">{fm(ov)}</td><td class="n">{fm(nv)}</td><td class="n {c}">{a} {fm(abs(d))}</td><td class="n {c}">{fp(p)}</td></tr>'
html += '</table></div>'

html += f'<div class="c"><div class="ct">🚨 異常</div>'
if anomalies: [html := html + f'<div class="ar">{a}</div>' for a in anomalies]
else: html += '<div class="ag">✅ 本週無異常</div>'
html += '</div>'

html += f'<div class="c"><div class="ct">⚙️ 決策變動</div>'
if decs: [html := html + f'<div class="ci">{c}</div>' for c in decs]
else: html += '<div class="ci" style="color:#6b7280">無</div>'
html += '</div>'

cash_m = int(last["cash_total"]/141958) if last["cash_total"] else 0
html += f'''<div class="c"><div class="ct">🧓 巴菲特週審</div><div class="b">
<h3>📊 資產概況</h3><ul>
<li>總資產 {fm(last["total_assets"])} → {"上漲" if last["total_assets"]>=prev_v else "下跌"} {fm(abs(last["total_assets"]-prev_v))}</li>
<li>淨值 {fm(nw)}（負債 {fm(liabilities)}）</li>
</ul>
<h3>💡 安全邊際</h3><ul>
<li>現金 {fm(last["cash_total"])} → 可支應 {cash_m} 個月</li>
<li>保單 {fm(last["insurance"])} / 證券 {fm(last["securities"])}</li>
</ul>
<h3>🎯 策略</h3><ul>
<li>{"🔴 資產下跌，關注風險" if last["total_assets"]<prev_v else "🟢 資產穩定"}</li>
<li>{"🟢 現金充裕 >" + fm(141958*6) if last["cash_total"]>141958*6 else "🟡 現金需關注"}</li>
<li>📌 機會子彈：現金 {cash_m} 個月</li>
</ul></div></div>

<div style="text-align:center;font-size:10px;color:#374151;padding:12px 0">龍九週報 · {TODAY} · SSoT: dragon_assets.db</div>
</body></html>'''

out = BASE / f"weekly_report_{TODAY}.html"
out.write_text(html, encoding="utf-8")
print(f"✅ {out} ({out.stat().st_size:,} bytes)")

# Push
import subprocess
for cmd in [["git","add",str(out.name)], ["git","commit","-m",f"weekly {TODAY}"], ["git","push","origin","clean-main"]]:
    r = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True, timeout=30)
    if r.returncode != 0: break
print(f"📤 Git: {'ok' if r.returncode==0 else r.stderr[:80] if r.stderr else 'ok'}")

# Telegram
if TG_TOKEN:
    import requests
    msg = f"""📊 龍九週報 {WEEK}

🏦 總資產 {fm(last['total_assets'])} ({fp((last['total_assets']-prev_v)/max(prev_v,1)*100)})
🎯 淨值 {fm(nw)}
💵 現金 {fm(last['cash_total'])}（{cash_m}個月）

{'🚨 '+anomalies[0][:50] if anomalies else '✅ 正常'}
🔗 https://b0988321088.github.io/longjiu-dashboard-2/weekly_report_{TODAY}.html"""
    try: requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": msg}, timeout=10)
    except: pass

print(f"🔗 https://b0988321088.github.io/longjiu-dashboard-2/weekly_report_{TODAY}.html")
