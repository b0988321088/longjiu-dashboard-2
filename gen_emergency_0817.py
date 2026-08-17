# -*- coding: utf-8 -*-
"""台股緊急應變 2026-08-17 — 從 data/emergency_llm_analysis.json 渲染完整 HTML（Railway + GitHub 版）

資料源：LLM 完整分析（六大章節）→ JSON → 本腳本產出 emergency_report_2026-08-17.html
+ emergency_taiex_report_2026-08-17.html（同內容，命名供 Railway / GitHub Pages 使用）
"""
import json, re
from pathlib import Path

BASE = Path(__file__).resolve().parent
TODAY = "2026-08-17"

d = json.loads((BASE / "data" / "emergency_llm_analysis.json").read_text(encoding="utf-8"))
GEN_AT = d.get("generated_at", "")
FULL_REPORT = d.get("full_report", "")
print(f"✅ 讀取 JSON: generated_at={GEN_AT} | full_report={len(FULL_REPORT)} chars")

# 今日即時 KPI（Yahoo Finance 13:06 抓取 / FRED DGS30 8/13）
KPIS = [
    ("台股加權", "46,027.70", "+0.47%", "var(--grn)"),
    ("台積電 2330", "2,410.00", "+0.63%", "var(--grn)"),
    ("0050", "106.75", "+0.33%", "var(--grn)"),
    ("00878", "33.70", "-0.50%", "var(--red)"),
    ("費半 SOX", "12,417.05", "-0.31%", "var(--red)"),
    ("US30Y", "5.21%", "防禦5.20/紅線5.30", "var(--yel)"),
]
kpi_html = "".join(
    f"<div class='box'><div class='lbl'>{l}</div><div class='val' style='color:{c}'>{v}</div><div class='lbl'>{s}</div></div>"
    for l, v, s, c in KPIS
)

# 依【X、】章節切分
sections = re.split(r"(?=【[一二三四五六]、)", FULL_REPORT.strip())
cards = []
for sec in sections:
    if not sec.strip():
        continue
    head, _, body = sec.partition("\n")
    body_html = body.strip().replace("\n", "<br>")
    cards.append(f'<div class="card"><h2>{head}</h2><p>{body_html}</p></div>')

CSS = """:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--tx:#e6edf3;--mut:#8b949e;
--red:#f85149;--grn:#3fb950;--yel:#d29922;--blu:#58a6ff}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:'Segoe UI','Noto Sans TC','Microsoft JhengHei',sans-serif;line-height:1.7;padding:24px}
.wrap{max-width:960px;margin:0 auto}
header{border:1px solid var(--line);border-radius:12px;padding:22px 26px;background:linear-gradient(135deg,#1a2332,#161b22);margin-bottom:20px}
header h1{font-size:25px;letter-spacing:1px}
header .sub{color:var(--mut);margin-top:6px;font-size:14px}
.alert-bar{margin:14px 0 4px;padding:10px 16px;border-radius:8px;background:rgba(63,185,80,.12);border:1px solid rgba(63,185,80,.4);font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 24px;margin-bottom:16px}
.card h2{font-size:18px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--line);color:var(--blu)}
.card p{margin:6px 0;font-size:14.5px}
.kpi{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px}
.kpi .box{flex:1;min-width:150px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.kpi .box .lbl{font-size:12px;color:var(--mut)} .kpi .box .val{font-size:19px;font-weight:700;margin-top:2px}
footer{color:var(--mut);font-size:12px;text-align:center;margin-top:22px}"""

def page(title, sub_note):
    return f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🐉 龍九控股 — {title} {TODAY}</title>
<style>{CSS}</style></head><body><div class="wrap">
<header>
<h1>🐉 龍九控股 — 台股緊急應變報告</h1>
<div class="sub">📅 {GEN_AT}｜Chief Reporter + 台股危機應變官｜六大章節完整版｜資料：Yahoo Finance / FRED / briefing（tw.stock.yahoo.com）</div>
<div class="alert-bar">📈 台股 46,027.70（+0.47%）上漲日｜台積電 2,410（+0.63%）｜ETF 下車潮籌碼洗牌｜US30Y 5.21% 防禦模式（紅線 5.30%）｜無系統性風險</div>
</header>
<div class="kpi">{kpi_html}</div>
{''.join(cards)}
<footer>🐉 龍九控股 emergency response ｜ generated {GEN_AT} ｜ 數據來源：Yahoo Finance 即時（13:06）、FRED DGS30（8/13）、daily_analysis.json briefing、snapshot.json penetration.actual_twd</footer>
</div></body></html>"""

railway = page("台股緊急應變報告", GEN_AT)
github = page("台股緊急應變報告（GitHub 版）", GEN_AT)

# INC-134 補強（2026-08-17）：動態注入穿透五桶 + 總資產（緊急應變必須含穿透真值）
try:
    _snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    _pen_twd = _snap.get("penetration", {}).get("actual_twd", {})
    _pen_pct = _snap.get("penetration", {}).get("actual_pct", {})
    _total = _snap.get("total_assets", 0)
    _pen_card = f"""<div class="card"><h2>📊 資產穿透（{TODAY}）</h2>
    <p>總資產：<b>{_total:,.0f}</b> TWD（不含不動產）</p>
    <p>台股 {_pen_pct.get('台股市值型成長',0):.1f}%｜美股 {_pen_pct.get('美股市值型成長',0):.1f}%｜防守 {_pen_pct.get('防守型配息',0):.1f}%｜債券 {_pen_pct.get('債券',0):.1f}%｜現金 {_pen_pct.get('現金/安全網',0):.1f}%</p>
    <p style="color:var(--mut);font-size:13px">金額：台股 {_pen_twd.get('台股市值型成長',0):,.0f}｜美股 {_pen_twd.get('美股市值型成長',0):,.0f}｜防守 {_pen_twd.get('防守型配息',0):,.0f}｜債券 {_pen_twd.get('債券',0):,.0f}｜現金 {_pen_twd.get('現金/安全網',0):,.0f}</p></div>"""
    railway = railway.replace("</div></body></html>", _pen_card + "</div></body></html>")
    github = github.replace("</div></body></html>", _pen_card + "</div></body></html>")
    print(f"✅ 穿透已注入（總資產 {_total:,.0f}）")
except Exception as e:
    print(f"⚠️ 穿透注入失敗: {e}")

p1 = BASE / f"emergency_report_{TODAY}.html"
p2 = BASE / f"emergency_taiex_report_{TODAY}.html"
p1.write_text(railway, encoding="utf-8")
p2.write_text(github, encoding="utf-8")
print(f"✅ {p1.name} ({p1.stat().st_size:,} bytes)")
print(f"✅ {p2.name} ({p2.stat().st_size:,} bytes)")
