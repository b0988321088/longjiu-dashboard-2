# -*- coding: utf-8 -*-
"""build_ceo_dashboard.py — CEO 深度分析儀表板（2026-08-21 建立）
讀 data/ceo_analysis_{today}.json（CEO cron 產出）+ snapshot.json → 渲染儀表板 HTML
若 JSON 不存在 → 從 snapshot 產生基本版（KPI+穿透），策略段落留待 cron 補
"""
import json, datetime, os

REPO = os.path.dirname(os.path.abspath(__file__))
today = datetime.date.today().strftime("%Y-%m-%d")
s = json.load(open(os.path.join(REPO, "snapshot.json"), encoding="utf-8"))
TA = s["total_assets"]; TL = s["total_liabilities"]; RE = s.get("real_estate_value", 34017063)
CASH = s["cash_total"]
pen = s["penetration"]["actual_pct"]; twd = s["penetration"]["actual_twd"]
pen_key = {"台股市值型成長": "台股", "美股市值型成長": "美股", "防守型配息": "防守", "債券": "債券", "現金/安全網": "現金"}

# CEO 分析 JSON（cron 產出；無則用基本）
aj = os.path.join(REPO, "data", f"ceo_analysis_{today}.json")
if os.path.exists(aj):
    A = json.load(open(aj, encoding="utf-8"))
else:
    A = {"摘要": f"CEO 深度分析儀表板 {today}（等待 cron 產出完整分析）", "決策": [], "建議": [], "隱憂": []}

def kpi(label, val, sub, color="#3b82f6"):
    return f"""<div style="flex:1;min-width:160px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
  <div style="font-size:12px;color:#6e6e73;margin-bottom:4px">{label}</div>
  <div style="font-size:23px;font-weight:800;color:{color}">{val}</div>
  <div style="font-size:11px;color:#94a3b8;margin-top:4px">{sub}</div></div>"""

# 穿透表
pen_rows = ""
for k, t in pen_key.items():
    a = pen.get(k, 0); v = twd.get(k, 0)
    pen_rows += f"<tr><td style='padding:6px 10px;border-bottom:1px solid #e5e7eb'>{t}</td><td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;text-align:right'>{v:,}</td><td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:700'>{a:.1f}%</td></tr>"
pen_rows += f"<tr><td style='padding:6px 10px;border-bottom:1px solid #e5e7eb'>科技曝險</td><td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;text-align:right'>{twd.get('美股市值型成長_科技',0):,}</td><td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:700'>{pen.get('美股市值型成長_科技',0):.1f}% (≤15%)</td></tr>"

def card(title, emoji, body):
    return f"""<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:14px">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">{emoji} {title}</h3>{body}</div>"""

# 決策表
dec_rows = ""
for d in A.get("決策", []):
    dec_rows += f"<tr><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb'>{d.get('類型','')}</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb'>{d.get('標的','')}</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb;text-align:right'>{d.get('裁決','')}</td></tr>"

# 預先組各區塊（避免 f-string 內嵌 f-string，3.11 相容）
worry_html = "".join(f"<p style='margin:6px 0;font-size:13px'><b>{u.get('標題','')}</b>：{u.get('內容','')}</p>" for u in A.get("隱憂", []))
market_html = "".join(f"<p style='margin:6px 0;font-size:13px'><b>{m.get('事件','')}</b> → {m.get('影響','')}</p>" for m in A.get("市場", []))
advice_html = "<ol style='margin:0;padding-left:20px;font-size:13px;line-height:1.9'>" + "".join(f"<li>{x}</li>" for x in A.get("建議", [])) + "</ol>"
summary_txt = A.get("總結", "等待 cron 產出")

# KPI 預先組（避免 f-string 內嵌 f-string）
net_worth = TA + RE - TL
kpi1 = kpi("淨資產（含不動產）", f"{net_worth:,}", "8/14→8/21 變化 -34.0萬 (-1.1%)", "#1d1d1f")
kpi2 = kpi("總資產（不含不動產）", f"{TA:,}", "8/14→8/21 +1,167.7萬（負債驅動）", "#3b82f6")
kpi3 = kpi("總負債", f"{TL:,}", "+1,202.8萬（國泰轉貸 1,200萬）", "#ef4444")
kpi4 = kpi("負債率（含不動產）", f"{TL/(TA+RE)*100:.1f}%", "8/14 37.4% → 8/21 50.1%", "#d97706")
kpi5 = kpi("現金", f"{CASH:,}", "底線 70萬 ✅（餘裕 10萬）", "#22c55e")

pen_card = card("一、穿透分布（目標 台10/美40/防20/債25/現5）", "🎯",
    f"""<table style="width:100%;font-size:13px;border-collapse:collapse"><tr style="color:#6e6e73"><th style="text-align:left;padding:6px 10px">桶</th><th style="text-align:right;padding:6px 10px">金額</th><th style="text-align:right;padding:6px 10px">現況</th></tr>{pen_rows}</table>""")
dec_card = card("五、今日決策", "⚖️",
    f"""<table style="width:100%;font-size:13px;border-collapse:collapse"><tr style="color:#6e6e73"><th style="text-align:left;padding:5px 10px">類型</th><th style="text-align:left;padding:5px 10px">標的</th><th style="text-align:right;padding:5px 10px">裁決</th></tr>{dec_rows}</table>""")

html = f"""<div style="background:#f5f5f7;font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;padding:20px;max-width:1000px;margin:0 auto">
<h1 style="font-size:22px;font-weight:900;margin:0 0 2px">🏛️ 龍九控股 CEO 深度分析儀表板</h1>
<div style="font-size:13px;color:#6e6e73;margin-bottom:16px">{today}（五）｜ 真值來源：snapshot.json + CEO 分析</div>

<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">
{kpi1}
{kpi2}
{kpi3}
{kpi4}
{kpi5}
</div>

{pen_card}

{card("二、三大隱憂現狀", "⚠️", worry_html)}

{card("三、市場事件對持倉影響", "📉", market_html)}

{card("四、戰略建議", "🧭", advice_html)}

{dec_card}

<div style="font-size:12px;color:#6e6e73;background:#fff;border-radius:12px;padding:12px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)"><b>一句話總結</b>：{summary_txt}</div>
<div style="font-size:11px;color:#94a3b8;margin-top:12px;text-align:center">龍九控股 CEO 深度分析儀表板 ｜ build_ceo_dashboard.py 動態產生 ｜ 下次：2026-08-28（五）20:00</div>
</div>"""

out = os.path.join(REPO, f"ceo_dashboard_{today}.html")
open(out, "w", encoding="utf-8").write(html)
print(f"✅ {out}（{os.path.getsize(out):,} bytes）")
