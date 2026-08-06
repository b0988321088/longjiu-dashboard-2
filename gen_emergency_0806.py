# -*- coding: utf-8 -*-
"""Generate emergency_report_YYYY-MM-DD.html (Railway) + emergency_taiex_report_YYYY-MM-DD.html (GitHub)
from data/emergency_llm_analysis.json — full six-chapter styled report."""
import json, html, datetime

BASE = "."
today = datetime.date.today().isoformat()
d = json.load(open("data/emergency_llm_analysis.json", encoding="utf-8"))
report = d["full_report"]
alloc = d.get("allocation", {})
holdings = d.get("holdings", {})
us30y = d.get("us30y", {})

def pct(num, up_is_good=True, invert=False):
    v = float(num)
    cls = "pos" if v > 0 else ("neg" if v < 0 else "")
    return f'<span class="{cls}">{v:+.1f}pp</span>'

# --- asset allocation table ---
alloc_rows = ""
for name, v in alloc.items():
    twd, p, tgt = v["twd"], v["pct"], v["target"]
    gap = p - tgt
    if gap < -5:
        status, act = "嚴重低配", "增持(回檔小單)"
    elif gap < -1:
        status, act = "低配", "分批增持"
    elif gap > 5:
        status, act = "超配", "凍結/暫緩"
    elif gap > 1:
        status, act = "超配", "暫緩加碼"
    else:
        status, act = "合規", "持有"
    cls = "neg" if gap < 0 else ("pos" if gap > 0 else "")
    alloc_rows += (f'<tr><td>{name}</td><td class="num">{twd:,}</td><td class="num">{p}%</td>'
                   f'<td class="num">{tgt}%</td><td class="num {cls}">{gap:+.1f}pp</td>'
                   f'<td>{status}</td><td>{act}</td></tr>')

# --- holdings table ---
hold_rows = ""
hnames = {"0050": "元大台灣50", "006208": "富邦台50", "00878": "國泰永續高股息",
          "00919": "群益台灣精選高息", "00983D": "富邦複合收益(主動債ETF)"}
for tk, v in holdings.items():
    hold_rows += (f'<tr><td>{tk}</td><td>{hnames.get(tk, "")}</td>'
                  f'<td class="num">{v["shares"]:,}</td><td class="num">{v["price"]}</td>'
                  f'<td class="num">{v["value"]:,}</td></tr>')

report_html = html.escape(report).replace("\n", "<br>")

page = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>台股緊急應變報告 {today}</title>
<style>
:root {{ --bg:#0b0f17; --card:#131a26; --line:#1f2937; --txt:#e5e7eb; --mut:#9ca3af;
  --up:#34d399; --down:#f87171; --acc:#60a5fa; --gold:#fbbf24; --warn:#fb923c; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--txt); font-family:"Segoe UI","PingFang TC","Microsoft JhengHei",sans-serif; padding:24px; line-height:1.7; }}
.wrap {{ max-width:1000px; margin:0 auto; }}
header {{ border:1px solid var(--line); border-radius:14px; padding:22px 26px; background:linear-gradient(135deg,#16203a,#131a26); margin-bottom:20px; }}
h1 {{ font-size:26px; color:#fff; letter-spacing:.5px; }}
.sub {{ color:var(--mut); margin-top:6px; font-size:14px; }}
.badge {{ display:inline-block; margin-top:10px; padding:4px 14px; border-radius:999px; font-size:13px; font-weight:700; background:rgba(251,146,60,.15); color:var(--warn); border:1px solid rgba(251,146,60,.4); }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:20px 24px; margin-bottom:18px; }}
h2 {{ font-size:19px; color:var(--acc); margin-bottom:12px; border-left:4px solid var(--acc); padding-left:10px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th,td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; }}
th {{ color:var(--mut); font-weight:600; background:rgba(255,255,255,.03); }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.pos {{ color:var(--up); font-weight:700; }}
.neg {{ color:var(--down); font-weight:700; }}
.analysis {{ font-size:14.5px; }}
.analysis b {{ color:var(--gold); }}
.hl {{ background:rgba(96,165,250,.12); border:1px solid rgba(96,165,250,.35); border-radius:10px; padding:12px 16px; margin-top:14px; font-size:14px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin-top:12px; }}
.kpi {{ background:rgba(255,255,255,.03); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }}
.kpi .k {{ font-size:12px; color:var(--mut); }}
.kpi .v {{ font-size:18px; font-weight:700; margin-top:4px; }}
footer {{ text-align:center; color:var(--mut); font-size:12px; padding:18px 0 8px; }}
</style>
</head>
<body><div class="wrap">
<header>
  <h1>🚨 台股緊急應變報告（13:00 午盤）</h1>
  <div class="sub">📅 {today} 13:00（台股午盤・收盤前最後確認）・龍九控股 Chief Reporter / 台股危機應變官</div>
  <span class="badge">⚠ 開低震盪・韓股 AI 修正擴散・台股相對抗跌・非系統性風險</span>
</header>

<div class="card">
  <h2>📊 市場速覽（Yahoo Finance 即時 / 13:00）</h2>
  <div class="grid">
    <div class="kpi"><div class="k">加權指數</div><div class="v">44,409.35</div><div class="neg">-0.45%（早盤最低 44,024）</div></div>
    <div class="kpi"><div class="k">台積電</div><div class="v">2,375 元</div><div class="neg">-1.25%</div></div>
    <div class="kpi"><div class="k">費城半導體 SOX</div><div class="v">12,008.88</div><div class="neg">-1.40%</div></div>
    <div class="kpi"><div class="k">道瓊 / 納指 / S&amp;P</div><div class="v" style="font-size:14px">54,349 / 26,363 / 7,723</div><div>+0.49% / -0.83% / -0.17%</div></div>
    <div class="kpi"><div class="k">US30Y 美債30年</div><div class="v">5.202%</div><div class="warn" style="color:var(--warn)">貼近 5.20% 防禦門檻・未觸 5.30% 凍結紅線</div></div>
    <div class="kpi"><div class="k">美國 6 月 CPI</div><div class="v" style="font-size:15px">YoY 3.5% / Core 2.6%</div><div class="pos">低於預期（3.8% / 2.8%）</div></div>
  </div>
</div>

<div class="card">
  <h2>⚖️ 資產配置透視（snapshot penetration，臨時階段目標）</h2>
  <table><tr><th>類別</th><th class="num">金額(TWD)</th><th class="num">實際</th><th class="num">目標</th><th class="num">偏離</th><th>狀態</th><th>動作</th></tr>{alloc_rows}</table>
  <div class="hl">💡 成長合計 45.3%（台 11.3 + 美 34.0）／債券+現金安全網 36.2%／總股票曝險未逾 55% 紅線／現金 302 萬 &gt; 底線 85 萬 ✅。US30Y 5.202% 貼近 5.20% 防禦門檻（需連 3 日 &lt;5.20% 才解除防禦），5.30% 債券凍結紅線未觸發。</div>
</div>

<div class="card">
  <h2>📈 重點持股（snapshot 2026-08-06）</h2>
  <table><tr><th>代碼</th><th>名稱</th><th class="num">股數</th><th class="num">現價</th><th class="num">市值(TWD)</th></tr>{hold_rows}</table>
</div>

<div class="card">
  <h2>🧠 LLM 六大章節深度分析</h2>
  <div class="analysis">{report_html}</div>
</div>

<footer>龍九控股・Chief Reporter 台股緊急應變｜{today} 13:00｜資料來源：Yahoo Finance API + snapshot.json + daily_intel（Firecrawl 額度暫缺，以既有情報彙整）｜本報告為自動化例行應變，非投資建議</footer>
</div></body></html>
"""

with open(f"emergency_report_{today}.html", "w", encoding="utf-8") as f:
    f.write(page)
with open(f"emergency_taiex_report_{today}.html", "w", encoding="utf-8") as f:
    f.write(page)

print("written:", len(page), "chars -> emergency_report_%s.html + emergency_taiex_report_%s.html" % (today, today))
