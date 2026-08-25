# -*- coding: utf-8 -*-
"""美股緊急應變 8/25 21:30 — 從 data/emergency_llm_analysis.json 渲染兩版 HTML
產出：emergency_report_2026-08-25.html (Railway 版) + emergency_taiex_report_2026-08-25.html (GitHub 版)
⚠️ INC-134：HTML 必須含穿透卡（資產穿透真值），否則 check_penetration_consistency 會擋推送
資料：Yahoo Finance chart API 即時（21:30 開盤）＋ snapshot.json 穿透真值
"""
import json, re
from pathlib import Path

BASE = Path(__file__).resolve().parent
TODAY = "2026-08-26"
NOW = "2026-08-25 21:33"

CSS = """
:root{--bg:#0b0f17;--card:#131a26;--line:#1f2937;--txt:#e5e7eb;--mut:#9ca3af;--up:#34d399;--down:#f87171;--acc:#60a5fa;--gold:#fbbf24;--warn:#fb923c;}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--txt);font-family:"Segoe UI","PingFang TC","Microsoft JhengHei",sans-serif;padding:24px;line-height:1.75;}
.wrap{max-width:1020px;margin:0 auto;}
.hd{border:1px solid var(--line);border-radius:14px;padding:22px 26px;background:linear-gradient(135deg,#101828,#0b0f17);margin-bottom:18px;}
.hd h1{font-size:24px;letter-spacing:1px;color:#fff;}
.hd .sub{color:var(--mut);font-size:13px;margin-top:6px;}
.badge{display:inline-block;background:#7c3aed33;border:1px solid #7c3aed;color:#c4b5fd;border-radius:20px;padding:2px 12px;font-size:12px;margin-left:8px;vertical-align:middle;}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0;}
.kpi{flex:1;min-width:148px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;text-align:center;}
.kpi .v{font-size:19px;font-weight:700;margin-top:2px;}
.kpi .l{color:var(--mut);font-size:12px;}
.up{color:var(--up);} .down{color:var(--down);} .flat{color:var(--mut);} .warn{color:var(--warn);}
.sec{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 24px;margin-bottom:16px;}
.sec h2{font-size:18px;color:var(--acc);border-left:4px solid var(--acc);padding-left:10px;margin-bottom:12px;}
.sec p{margin:6px 0;}
.alert{background:#f8717133;border:1px solid #f87171;color:#fca5a5;border-radius:10px;padding:10px 14px;margin:10px 0;font-weight:600;}
.foot{color:var(--mut);font-size:12px;text-align:center;margin-top:24px;}
"""

def load_report():
    d = json.loads((BASE / "data" / "emergency_llm_analysis.json").read_text(encoding="utf-8"))
    return d.get("generated_at", NOW), d.get("full_report", "")

def split_sections(text):
    parts = re.split(r"(【[一二三四五六]、[^】]+】)", text)
    secs = []
    cur_title, cur_body = None, []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if re.fullmatch(r"【[一二三四五六]、[^】]+】", p):
            if cur_title:
                secs.append((cur_title, cur_body))
            cur_title, cur_body = p, []
        else:
            cur_body.append(p)
    if cur_title:
        secs.append((cur_title, cur_body))
    return secs

def render(kpis_html, sec_html, title, sub):
    return f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{CSS}</style></head><body><div class="wrap">
<div class="hd"><h1>{title}<span class="badge">緊急應變</span></h1>
<div class="sub">{sub}</div></div>
{kpis_html}
{sec_html}
<div class="foot">龍九控股內部報告｜僅供決策參考，非投資建議｜資料時間 {NOW} 台北（美股開盤）｜Yahoo Finance chart API 即時 + Yahoo Finance news + us30y_state/^TYX + snapshot.json 穿透數據</div>
</div></body></html>"""

def penetration_card():
    """INC-134 穿透注入：資產穿透真值卡（check_penetration_consistency 依賴此區塊）"""
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    pp = snap.get("penetration", {}).get("actual_pct", {})
    pt = snap.get("penetration", {}).get("actual_twd", {})
    tt = snap.get("total_assets", 0)
    usd = snap.get("usd_exposure_pct", "-")
    rows = [
        ("台股市值型成長", pp.get("台股市值型成長", 0), pt.get("台股市值型成長", 0)),
        ("美股市值型成長", pp.get("美股市值型成長", 0), pt.get("美股市值型成長", 0)),
        ("防守型配息", pp.get("防守型配息", 0), pt.get("防守型配息", 0)),
        ("債券", pp.get("債券", 0), pt.get("債券", 0)),
        ("現金/安全網", pp.get("現金/安全網", 0), pt.get("現金/安全網", 0)),
    ]
    lis = "".join(
        f"<li>{name} {pct:.1f}%（{twd:,.0f} 元）</li>" for name, pct, twd in rows
    )
    us_stock = pp.get("美股市值型成長", 0)
    tw_stock = pp.get("台股市值型成長", 0)
    alert_txt = (
        f"⚠️ 美股成長 {us_stock:.1f}% 超標 +{us_stock - 30:.1f}pp｜台股 {tw_stock:.1f}% 不足 -{23.5 - tw_stock:.1f}pp"
        f"｜今晚費半 -2.83% 主曝險來源（美元曝險 {usd}% 超紅線 50%）"
    )
    return f"""<div class="sec"><h2>📊 資產穿透真值（{TODAY} snapshot）</h2>
<p>總資產 <b>{tt:,.0f}</b> 元｜美元曝險 <b class="warn">{usd}%</b>（紅線 50%）｜目標：美股30/台股23.5/防守19/債券13/現金14.5</p>
<ul>{lis}</ul>
<div class="alert">{alert_txt}</div></div>"""

def build():
    gen, report = load_report()
    secs = split_sections(report)
    n = len(report)
    print(f"[JSON] full_report len = {n} chars (generated_at={gen})")
    assert n > 1500, f"full_report too short: {n}"

    kpis = [
        ("道瓊 (DIA)", "53,529.39", "+0.21%", "up"), ("S&P 500 (SPY)", "7,682.92", "-0.11%", "down"),
        ("納斯達克 (QQQ)", "26,163.48", "-0.48%", "down"), ("費城半導體 (SOXX)", "11,653.44", "-2.83%", "down"),
        ("台積電 ADR", "416.68", "+0.79%", "up"), ("NVDA", "210.81", "-4.06%", "down"),
        ("AAPL", "313.25", "+1.04%", "up"), ("META", "565.75", "+4.06%", "up"),
        ("US30Y", "5.19%", "警戒5.20/凍結5.30", "warn"), ("台股加權", "45,169.46", "+0.91%", "up"),
    ]

    kpis_html = '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="l">{l}</div><div class="v {c}">{v}</div><div class="l">{s}</div></div>'
        for l, v, s, c in kpis) + "</div>"

    sec_html = ""
    for title, paras in secs:
        body = "".join(f"<p>{p}</p>" for p in paras if p)
        sec_html += f'<div class="sec"><h2>{title}</h2>{body}</div>'

    sec_html += penetration_card()

    rail = BASE / f"emergency_report_{TODAY}.html"
    gh = BASE / f"emergency_taiex_report_{TODAY}.html"
    rail.write_text(render(kpis_html, sec_html, f"美股緊急應變報告 {TODAY} 21:30｜龍九控股",
                           f"資料時間 {gen} 台北｜美股開盤即時分析（六大章節＋穿透真值）"), encoding="utf-8")
    gh.write_text(render(kpis_html, sec_html, f"台股/美股緊急應變報告 {TODAY} 21:30｜龍九控股",
                         f"資料時間 {gen} 台北｜美股開盤即時分析（六大章節＋穿透真值）"), encoding="utf-8")
    print(f"[HTML] {rail.name} ({rail.stat().st_size:,} bytes)")
    print(f"[HTML] {gh.name} ({gh.stat().st_size:,} bytes)")
    print("[DONE]", NOW)

if __name__ == "__main__":
    build()
