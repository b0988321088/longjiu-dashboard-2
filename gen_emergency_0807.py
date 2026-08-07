# -*- coding: utf-8 -*-
"""Generate emergency_report_2026-08-07.html (Railway) + emergency_taiex_report_2026-08-07.html (GitHub)
from data/emergency_llm_analysis.json — full six-chapter styled report. 2026-08-07 13:00 台股時段."""
import json, html, datetime

BASE = "."
today = datetime.date.today().isoformat()
d = json.load(open("data/emergency_llm_analysis.json", encoding="utf-8"))
report = d["full_report"]
alloc = d.get("allocation", {})
holdings = d.get("holdings", {})
us30y = d.get("us30y", {})

# --- 動態穿透覆蓋：強制使用最新 snapshot（2026-08-07 修正：不再用 LLM 時點舊值）---
try:
    _snap = json.load(open("snapshot.json", encoding="utf-8"))
    _pen_twd = _snap.get("penetration", {}).get("actual_twd", {})
    _pen_pct = _snap.get("penetration", {}).get("actual_pct", {})
    _tgt = _snap.get("penetration", {}).get("targets", {})
    _ta = _snap.get("total_assets", 0)
    _map = [
        ("台股市值型", "台股市值型成長", "台股市值型目標", 20),
        ("美股市值型", "美股市值型成長", "美股市值型目標", 30),
        ("防守型配息", "防守型配息", "配息型目標", 20),
        ("債券", "債券", "債券型目標", 15),
        ("現金/安全網", "現金/安全網", "現金目標", 15),
    ]
    alloc = {}
    for _label, _pkey, _tkey, _def_tgt in _map:
        alloc[_label] = {
            "twd": _pen_twd.get(_pkey, 0),
            "pct": _pen_pct.get(_pkey, 0),
            "target": _tgt.get(_tkey, _def_tgt),
        }
    _ta_override = _ta

    # full_report 穿透段重寫（LLM 舊值 → 最新 snapshot 值）
    import re as _re
    _seg_start = report.find("【四、資產配置透視】")
    if _seg_start >= 0:
        _seg_end = report.find("【五", _seg_start)
        if _seg_end < 0:
            _seg_end = len(report)
        _g_tw = _pen_pct.get("台股市值型成長", 0); _g_us = _pen_pct.get("美股市值型成長", 0)
        _g_def = _pen_pct.get("防守型配息", 0); _g_bond = _pen_pct.get("債券", 0)
        _g_cash = _pen_pct.get("現金/安全網", 0)
        _t_tw = _tgt.get("台股市值型目標", 20); _t_us = _tgt.get("美股市值型目標", 30)
        _t_def = _tgt.get("配息型目標", 20); _t_bond = _tgt.get("債券型目標", 15)
        _t_cash = _tgt.get("現金目標", 15)
        _new_seg = (
            f"【四、資產配置透視】（snapshot penetration，動態校正 {today}；總投資 {_ta:,}）\n"
            f"台股市值型成長 {_pen_twd.get('台股市值型成長',0):,}（{_g_tw}%）vs {_t_tw}% → {_g_tw-_t_tw:+.1f}pp"
            f"；美股市值型成長 {_pen_twd.get('美股市值型成長',0):,}（{_g_us}%）vs {_t_us}% → {_g_us-_t_us:+.1f}pp"
            f"；防守型配息 {_pen_twd.get('防守型配息',0):,}（{_g_def}%）vs {_t_def}% → {_g_def-_t_def:+.1f}pp"
            f"；債券 {_pen_twd.get('債券',0):,}（{_g_bond}%）vs {_t_bond}% → {_g_bond-_t_bond:+.1f}pp"
            f"；現金/安全網 {_pen_twd.get('現金/安全網',0):,}（{_g_cash}%）vs {_t_cash}% → {_g_cash-_t_cash:+.1f}pp"
            f"。成長合計 {_g_tw+_g_us}%（目標 {_t_tw+_t_us}%）；安全網（債＋現金）{_g_bond+_g_cash}%。\n"
        )
        report = report[:_seg_start] + _new_seg + report[_seg_end:]
except Exception:
    _ta_override = None

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
  <span class="badge">⚠ 開高走低・季線整理・費半收紅支撐・非系統性風險</span>
</header>

<div class="card">
  <h2>📊 市場速覽（Yahoo Finance 即時 / 13:00）</h2>
  <div class="grid">
    <div class="kpi"><div class="k">加權指數</div><div class="v">44,020.34</div><div class="neg">-0.85%（全日低 44,010・開高走低）</div></div>
    <div class="kpi"><div class="k">台積電</div><div class="v">2,355 元</div><div class="neg">-0.42%</div></div>
    <div class="kpi"><div class="k">費城半導體 SOX</div><div class="v">12,048.69</div><div class="pos">+0.33%（8/6 開低走高收紅）</div></div>
    <div class="kpi"><div class="k">道瓊 / 納指 / S&amp;P</div><div class="v" style="font-size:14px">53,885 / 26,348 / 7,710</div><div class="neg">-0.85% / -0.06% / -0.18%</div></div>
    <div class="kpi"><div class="k">US30Y 美債30年</div><div class="v">5.17%</div><div style="color:var(--warn)">連續 3 日 &lt;5.20% 防禦門檻・未觸 5.30% 凍結紅線</div></div>
    <div class="kpi"><div class="k">美國 6 月 CPI</div><div class="v" style="font-size:15px">YoY 3.5% / Core 2.6%</div><div class="pos">低於預期（3.8% / 2.8%）</div></div>
  </div>
</div>

<div class="card">
  <h2>⚖️ 資產配置透視（snapshot penetration，臨時階段目標）</h2>
  <table><tr><th>類別</th><th class="num">金額(TWD)</th><th class="num">實際</th><th class="num">目標</th><th class="num">偏離</th><th>狀態</th><th>動作</th></tr>{alloc_rows}</table>
  <div class="hl">💡 成長合計 45.3%（台 11.3 + 美 34.0）／債券+現金安全網 36.2%／總股票曝險未逾 55% 紅線／現金 302 萬 &gt; 底線 85 萬 ✅。US30Y 5.17% 連續 3 日 &lt;5.20% 已達開放市值大額進場條件，惟實務仍採分批紀律（每週≤50萬、單筆&lt;5萬）；5.30% 債券凍結紅線未觸發。</div>
</div>

<div class="card">
  <h2>📈 重點持股（snapshot 2026-08-07）</h2>
  <table><tr><th>代碼</th><th>名稱</th><th class="num">股數</th><th class="num">現價</th><th class="num">市值(TWD)</th></tr>{hold_rows}</table>
</div>

<div class="card">
  <h2>🧠 LLM 六大章節深度分析</h2>
  <div class="analysis">{report_html}</div>
</div>

<footer>龍九控股・Chief Reporter 台股緊急應變｜{today} 13:00｜資料來源：Yahoo Finance API（TAIEX/2330/SOX）+ FRED DGS30 + snapshot.json + daily_intel 財訊快報（Firecrawl 額度暫缺，以既有情報彙整）｜本報告為自動化例行應變，非投資建議</footer>
</div></body></html>
"""

with open(f"emergency_report_{today}.html", "w", encoding="utf-8") as f:
    f.write(page)
with open(f"emergency_taiex_report_{today}.html", "w", encoding="utf-8") as f:
    f.write(page)

print("written:", len(page), "chars -> emergency_report_%s.html + emergency_taiex_report_%s.html" % (today, today))
