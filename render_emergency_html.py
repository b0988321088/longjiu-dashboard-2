# -*- coding: utf-8 -*-
"""從 data/emergency_llm_analysis.json 渲染緊急應變 HTML（兩版：Railway / GitHub）"""
import json, re
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent
TODAY = date.today().isoformat()
d = json.loads((BASE / "data" / "emergency_llm_analysis.json").read_text(encoding="utf-8"))
gen = d.get("generated_at", "")
report = d.get("full_report", "")
gen_short = gen[:16]

# 切六大章節
parts = re.split(r"(?=【[一二三四五六]、)", report)
sections_html = ""
for p in parts:
    p = p.strip()
    if not p:
        continue
    m = re.match(r"(【[一二三四五六]、[^】]*】)(.*)", p, re.S)
    if m:
        title, body = m.group(1), m.group(2).strip()
        body_html = body.replace("\n", "<br>\n")
        sections_html += f'<div class="sec"><h2>{title}</h2><p>{body_html}</p></div>\n'
    else:
        sections_html += f'<div class="sec"><p>{p.replace(chr(10),"<br>")}</p></div>\n'

KPIS = [
    ("道瓊", "53,439.06", "+0.18%", "up"),
    ("S&P 500", "7,722.45", "+0.40%", "up"),
    ("納斯達克", "26,402.88", "+0.43%", "up"),
    ("費城半導體", "12,102.85", "+0.92%", "up"),
    ("台積電 ADR", "417.72", "+1.04%", "up"),
    ("NVDA", "221.97", "+1.01%", "up"),
    ("META", "539.43", "-0.78%", "down"),
    ("US30Y", "5.31%", "凍結線5.30", "warn"),
    ("US10Y", "4.64%", "前收4.71", "up"),
    ("VIX", "15.14", "-4.42% 回落", "up"),
]
kpi_html = "".join(
    f'<div class="kpi"><div class="l">{l}</div><div class="v {cls}">{v}</div><div class="l">{s}</div></div>'
    for l, v, s, cls in KPIS
)

def page(title, sub_note):
    return f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} {gen_short}｜龍九控股</title><style>
:root{{--bg:#0b0f17;--card:#131a26;--line:#1f2937;--txt:#e5e7eb;--mut:#9ca3af;--up:#34d399;--down:#f87171;--acc:#60a5fa;--gold:#fbbf24;--warn:#fb923c;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:var(--bg);color:var(--txt);font-family:"Segoe UI","PingFang TC","Microsoft JhengHei",sans-serif;padding:24px;line-height:1.75;}}
.wrap{{max-width:1020px;margin:0 auto;}}
.hd{{border:1px solid var(--line);border-radius:14px;padding:22px 26px;background:linear-gradient(135deg,#101828,#0b0f17);margin-bottom:18px;}}
.hd h1{{font-size:24px;letter-spacing:1px;color:#fff;}}
.hd .sub{{color:var(--mut);font-size:13px;margin-top:6px;}}
.badge{{display:inline-block;background:#7c3aed33;border:1px solid #7c3aed;color:#c4b5fd;border-radius:20px;padding:2px 12px;font-size:12px;margin-left:8px;vertical-align:middle;}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0;}}
.kpi{{flex:1;min-width:148px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;text-align:center;}}
.kpi .v{{font-size:19px;font-weight:700;margin-top:2px;}}
.kpi .l{{color:var(--mut);font-size:12px;}}
.up{{color:var(--up);}} .down{{color:var(--down);}} .flat{{color:var(--mut);}} .warn{{color:var(--warn);}}
.sec{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 24px;margin-bottom:16px;}}
.sec h2{{font-size:18px;color:var(--acc);border-left:4px solid var(--acc);padding-left:10px;margin-bottom:12px;}}
.sec p{{margin:6px 0;}}
.alert{{background:#f8717133;border:1px solid #f87171;color:#fca5a5;border-radius:10px;padding:10px 14px;margin:10px 0;font-weight:600;}}
.foot{{color:var(--mut);font-size:12px;text-align:center;margin-top:24px;}}
</style></head><body><div class="wrap">
<div class="hd"><h1>{title} {gen_short}｜龍九控股<span class="badge">緊急應變</span></h1>
<div class="sub">{sub_note}</div></div>
<div class="kpis">{kpi_html}</div>
{sections_html}
<div class="foot">龍九控股內部報告｜僅供決策參考，非投資建議｜資料時間 {gen_short} 台北（美股開盤）｜Yahoo Finance 即時 + FRED + snapshot.json 穿透數據</div>
</div></body></html>"""

railway = page("美股緊急應變報告", f"資料時間 {gen_short} 台北｜美股開盤即時分析（六大章節）")
github = page("美股緊急應變報告（GitHub 版）", f"資料時間 {gen_short} 台北｜美股開盤即時分析（六大章節）")

p1 = BASE / f"emergency_report_{TODAY}.html"
p2 = BASE / f"emergency_taiex_report_{TODAY}.html"
p1.write_text(railway, encoding="utf-8")
p2.write_text(github, encoding="utf-8")
print(f"✅ {p1.name} ({p1.stat().st_size:,} bytes)")
print(f"✅ {p2.name} ({p2.stat().st_size:,} bytes)")
