# -*- coding: utf-8 -*-
"""build_ceo_dashboard.py — CEO 深度分析儀表板（2026-08-21 建立）
讀 data/ceo_analysis_{today}.json（CEO cron 產出）+ snapshot.json → 渲染儀表板 HTML
若 JSON 不存在 → 從 snapshot 產生基本版（KPI+穿透），策略段落留待 cron 補
"""
import json, datetime, os, sqlite3, re

REPO = os.path.dirname(os.path.abspath(__file__))
# 2026-09-13：支援指定日期補產（python build_ceo_dashboard.py 2026-09-11）
import sys as _sys
today = _sys.argv[1] if len(_sys.argv) > 1 else datetime.date.today().strftime("%Y-%m-%d")
s = json.load(open(os.path.join(REPO, "snapshot.json"), encoding="utf-8"))
TA = s["total_assets"]; TL = s["total_liabilities"]; RE = s.get("real_estate_value", 34017063)
CASH = s["cash_total"]
pen = s["penetration"]["actual_pct"]; twd = s["penetration"]["actual_twd"]
pen_key = {"台股市值型成長": "台股", "美股市值型成長": "美股", "防守型配息": "防守", "債券": "債券", "現金/安全網": "現金"}

# ── 週對照期間動態化（2026-09-04 修正：原寫死「8/14 → 8/21」每週沿用舊對照）──
# dragon_assets.db assets 表每日歷史 → 本週 = 最新交易日，上週 = 距今 7 天內最近交易日
def _load_week_pair():
    db = sqlite3.connect(os.path.join(REPO, "dragon_assets.db"))
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT date, total_assets, total_liabilities, cash_total, securities, insurance, funds, bonds "
        "FROM assets WHERE date <= ? ORDER BY date DESC LIMIT 14", (today,)
    ).fetchall()
    db.close()
    if not rows:
        return None
    d1 = rows[0]  # 本週基準（最新交易日）
    target = datetime.date.fromisoformat(d1["date"]) - datetime.timedelta(days=7)
    d0 = None
    for r in rows[1:]:
        rd = datetime.date.fromisoformat(r["date"])
        if rd <= target:
            d0 = r
            break
    if d0 is None:  # 歷史不足 7 天 → 退用最早的
        d0 = rows[-1]
    return d0, d1

_wp = _load_week_pair()
if _wp:
    _d0, _d1 = _wp
    _d0d, _d1d = _d0["date"], _d1["date"]
    TA0, TA1 = _d0["total_assets"], _d1["total_assets"]
    TL0, TL1 = _d0["total_liabilities"], _d1["total_liabilities"]
    # 顯示格式 M/D（如 8/28→9/4）
    _f0 = f"{int(_d0d[5:7])}/{int(_d0d[8:10])}"
    _f1 = f"{int(_d1d[5:7])}/{int(_d1d[8:10])}"
    _span = f"{_f0} → {_f1}"
    # KPI 副標動態值
    NW0, NW1 = TA0 + RE - TL0, TA1 + RE - TL1
    _nw_delta = (NW1 - NW0) / 10000  # 萬
    _nw_pct = (NW1 / NW0 - 1) * 100 if NW0 else 0
    _ta_delta = (TA1 - TA0) / 10000
    _tl_delta = (TL1 - TL0) / 10000
    _dr0 = TL0 / (TA0 + RE) * 100
    _dr1 = TL1 / (TA1 + RE) * 100
    kpi1_sub = f"{_f0}→{_f1} 變化 {_nw_delta:+.1f}萬 ({_nw_pct:+.1f}%)"
    kpi2_sub = f"{_f0}→{_f1} 變化 {_ta_delta:+.1f}萬"
    kpi3_sub = f"{_f0}→{_f1} 變化 {_tl_delta:+.1f}萬" if abs(_tl_delta) >= 0.05 else f"{_f0}→{_f1} 持平"
    kpi4_sub = f"{_f0} {_dr0:.1f}% → {_f1} {_dr1:.1f}%"
    chg_title = f"一、本週資產變化摘要（{_span}）"
else:
    kpi1_sub = kpi2_sub = kpi3_sub = kpi4_sub = ""
    chg_title = "一、本週資產變化摘要"

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
pen_rows += f"<tr><td style='padding:6px 10px;border-bottom:1px solid #e5e7eb'>科技曝險</td><td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;text-align:right'>{twd.get('美股市值型成長_科技',0):,}</td><td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:700'>{pen.get('美股市值型成長_科技',0):.1f}% (≤20%)</td></tr>"

def card(title, emoji, body):
    return f"""<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:14px">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">{emoji} {title}</h3>{body}</div>"""

# 決策表
dec_rows = ""
for d in A.get("決策", []):
    dec_rows += f"<tr><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb'>{d.get('類型','')}</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb'>{d.get('標的','')}</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb;text-align:right'>{d.get('裁決','')}</td></tr>"

# 預先組各區塊（避免 f-string 內嵌 f-string，3.11 相容）
def table(header, rows_html, num_cols=3):
    th = "".join(f"<th style='text-align:left;padding:6px 10px'>{h}</th>" for h in header)
    return f"<table style='width:100%;font-size:12.5px;border-collapse:collapse'><tr style='color:#6e6e73'>{th}</tr>{rows_html}</table>"

# ── 數字區塊治本（2026-09-13）：全部現算，不依賴 LLM JSON ──────────────────
# 血淚：9/11 週五三合一 cron 被 gateway 中斷 → ceo_analysis JSON 只寫了散文欄位，
# 缺 資產變化/資金流動/里程碑/雙維度 → 儀表板表格只剩表頭（使用者：「CEO 的報告很多都沒有數字」）。
# 對策：數字一律由 DB / snapshot / schedule_events 現算；LLM JSON 只補「歸因／去向」文字。
def _n(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0

def _fm(v):
    return f"{_n(v):,}"

_td_cell = "padding:5px 10px;border-bottom:1px solid #e5e7eb"
_tr_cell = _td_cell + ";text-align:right"

# A. 資產變化：dragon_assets.db 本週/上週 pair（分項欄位全在 assets 表）
chg_rows = ""
if _wp:
    _attr = {str(c.get("項目", "")).strip(): str(c.get("歸因", "")) for c in (A.get("資產變化") or [])}
    _mon_inc = s.get("monthly_income", 0)
    for _lab, _v0, _v1 in [
        ("總資產", TA0, TA1),
        ("證券（凱基）", _d0["securities"], _d1["securities"]),
        ("基金", _d0["funds"], _d1["funds"]),
        ("保單現值", _d0["insurance"], _d1["insurance"]),
        ("純現金", _d0["cash_total"], _d1["cash_total"]),
        ("總負債", TL0, TL1),
        ("淨資產（含不動產）", TA0 + RE - TL0, TA1 + RE - TL1),
        ("月收入", _mon_inc, _mon_inc),
    ]:
        _dd_ = _n(_v1) - _n(_v0)
        _col = "#22c55e" if _dd_ > 0 else ("#ef4444" if _dd_ < 0 else "#6e6e73")
        chg_rows += (f"<tr><td style='{_td_cell}'>{_lab}</td>"
                     f"<td style='{_tr_cell}'>{_fm(_v0)}</td>"
                     f"<td style='{_tr_cell};font-weight:700'>{_fm(_v1)}</td>"
                     f"<td style='{_tr_cell};font-weight:700;color:{_col}'>{_dd_:+,}</td>"
                     f"<td style='{_td_cell};font-size:11.5px;color:#6e6e73'>{_attr.get(_lab, '')}</td></tr>")
if not chg_rows:  # 後備：DB 歷史不足 → 回退 LLM 原列
    for c in (A.get("資產變化") or []):
        chg_rows += (f"<tr><td style='{_td_cell}'>{c.get('項目','')}</td>"
                     f"<td style='{_tr_cell}'>{c.get('上週','')}</td>"
                     f"<td style='{_tr_cell};font-weight:700'>{c.get('本週','')}</td>"
                     f"<td style='{_tr_cell};color:{'#ef4444' if '-' in str(c.get('變化','')) else '#22c55e'}'>{c.get('變化','')}</td>"
                     f"<td style='{_td_cell};font-size:11.5px;color:#6e6e73'>{c.get('歸因','')}</td></tr>")
chg_card = card(chg_title, "📊", table(["項目", "上週", "本週", "變化", "歸因"], chg_rows, 5))

# B. 資金流動：snapshot weekly_ops_closure_{date}（最新一期）執行清單，金額非空即入列
_wk_keys = sorted([k for k in s if str(k).startswith("weekly_ops_closure_")])
_wk_period, _flow_src = "", []
_infra_kw = ("日報", "同步", "修復", "整併", "清除", "上線", "缺陷", "審計", "檢查", "測試", "收斂", "登記", "建檔", "污染")
if _wk_keys:
    _wk = s[_wk_keys[-1]]
    _wk_period = str(_wk.get("期間", ""))
    for _it in (_wk.get("執行清單") or []):
        _amt = str(_it.get("金額", "")).strip()
        _nm = str(_it.get("項目", ""))
        if not _amt or _amt in ("—", "-", "0"):
            continue
        # 排除「管線/系統維護」類項目（金額欄常填總資產或無意義值，非資金流動）
        if any(_kw in _nm for _kw in _infra_kw):
            continue
        _num_txt = re.sub(r"[,\s元]", "", _amt)
        if re.fullmatch(r"\d+(\.\d+)?", _num_txt) and float(_num_txt) > 20_000_000:  # 純數字且 >2,000萬 = 誤填（如總資產）
            continue
        _flow_src.append((_nm, _amt, str(_it.get("狀態", ""))))
_flow_ov = {str(c.get("項目", "")).strip(): str(c.get("去向", "")) for c in (A.get("資金流動") or [])}
flow_rows = ""
for _p, _a, _g in _flow_src:
    flow_rows += (f"<tr><td style='{_td_cell}'>{_p[:46]}</td>"
                  f"<td style='{_tr_cell};font-weight:700'>{_a}</td>"
                  f"<td style='{_td_cell};font-size:11.5px;color:#6e6e73'>{_flow_ov.get(_p, _g)[:110]}</td></tr>")
if not flow_rows:
    for c in (A.get("資金流動") or []):
        flow_rows += (f"<tr><td style='{_td_cell}'>{c.get('項目','')}</td>"
                      f"<td style='{_tr_cell};font-weight:700'>{c.get('金額','')}</td>"
                      f"<td style='{_td_cell};font-size:11.5px;color:#6e6e73'>{c.get('去向','')}</td></tr>")
flow_card = card(f"二、本週資金流動{('（' + _wk_period + '）') if _wk_period else ''}", "💸",
                 table(["項目", "金額", "去向"], flow_rows, 3))

# 隱憂 / 市場 / 建議 / 里程碑
worry_html = "".join(f"<p style='margin:6px 0;font-size:13px'><b>{u.get('標題','')}</b><br><span style='color:#4b5563;font-size:12.5px'>{u.get('內容','')}</span></p>" for u in A.get("隱憂", [])) or "<p style='margin:6px 0;font-size:12.5px;color:#6e6e73'>本次分析未產出（數字區塊仍為 DB/snapshot 真值）</p>"
market_html = "".join(f"<p style='margin:6px 0;font-size:12.5px'><b>{m.get('事件','')}</b><br><span style='color:#4b5563'>{m.get('影響','')}</span></p>" for m in A.get("市場", [])) or "<p style='margin:6px 0;font-size:12.5px;color:#6e6e73'>本次分析未產出</p>"
advice_html = "<ol style='margin:0;padding-left:20px;font-size:13px;line-height:1.95'>" + "".join(f"<li>{x}</li>" for x in A.get("建議", [])) + "</ol>"
if not A.get("建議"):
    advice_html = "<p style='margin:0;font-size:12.5px;color:#6e6e73'>本次分析未產出建議</p>"
# C. 里程碑：schedule_events.json 未來 14 天（現算，不依賴 LLM）
ms_rows = ""
try:
    _evs = json.load(open(os.path.join(REPO, "schedule_events.json"), encoding="utf-8"))
    _t0 = datetime.date.fromisoformat(today)
    _due = []
    for _e in _evs:
        try:
            _ed = datetime.date.fromisoformat(str(_e.get("date", ""))[:10])
        except ValueError:
            continue
        if _t0 <= _ed <= _t0 + datetime.timedelta(days=14):
            _due.append((_ed, str(_e.get("item", ""))))
    _due.sort(key=lambda x: (x[0], 0 if any(_e2 in x[1] for _e2 in ("💰", "📌", "🏛️", "🔴", "⚖️", "🚨")) else 1))
    for _ed, _it in _due[:12]:
        ms_rows += (f"<tr><td style='{_td_cell};white-space:nowrap;font-weight:700'>{_ed.month}/{_ed.day}（{'一二三四五六日'[_ed.weekday()]}）</td>"
                    f"<td style='{_td_cell}'>{_it[:78]}</td></tr>")
except Exception:
    pass
if not ms_rows:  # 後備：LLM 原列
    ms_rows = "".join(f"<tr><td style='{_td_cell};white-space:nowrap;font-weight:700'>{m.get('日期','')}</td><td style='{_td_cell}'>{m.get('事項','')}</td></tr>" for m in (A.get("里程碑") or []))
ms_card = card("📅 未來 14 天里程碑", "🗓️", table(["日期", "事項"], ms_rows, 2))

# D. 雙維度：snapshot.dual_dimension_metric 現算；情境優先用 macro_regime 最高分情境
_dd_snap = s.get("dual_dimension_metric", {}) or {}
_dd_llm = A.get("雙維度", {}) or {}
_def_pct = (_dd_snap.get("防禦維度") or {}).get("佔比")
_inc_pct = (_dd_snap.get("收入維度") or {}).get("佔比")
_def_txt = f"{_def_pct:.1f}%" if isinstance(_def_pct, (int, float)) else str(_dd_llm.get("防禦", "—"))
_inc_txt = f"{_inc_pct:.1f}%" if isinstance(_inc_pct, (int, float)) else str(_dd_llm.get("收入", "—"))
_scene = str(_dd_llm.get("情境", "") or "")
if not _scene:
    try:
        import glob as _g
        _mf = sorted(_g.glob(os.path.join(REPO, "macro_regime_*.json")))
        if _mf:
            _mr = json.load(open(_mf[-1], encoding="utf-8"))
            _sc = _mr.get("情境評分", {}) or {}
            if _sc:
                _top = max(_sc.items(), key=lambda kv: (kv[1] or {}).get("score", 0))
                _scene = f"{_mr.get('燈號','')}{_top[0]}（{(_top[1] or {}).get('score',0):.0f} 分）"
    except Exception:
        pass
if not _scene:
    _scene = "區間震盪"
dd_card = card("🧭 雙維度 + 情境", "⚖️",
    f"<p style='margin:4px 0;font-size:13px'>🛡️ 防禦維度 <b>{_def_txt}</b> ｜ 💵 收入引擎 <b>{_inc_txt}</b> ｜ 🎯 情境：<b>{_scene}</b></p>"
    "<p style='margin:4px 0;font-size:12px;color:#6e6e73'>配息≠防守；多頭可進攻、空頭只能防守；加減碼/LTV/現金水位隨情境自動切換</p>")
summary_txt = A.get("總結", "等待 cron 產出")

# KPI 預先組（避免 f-string 內嵌 f-string）
net_worth = TA + RE - TL
kpi1 = kpi("淨資產（含不動產）", f"{net_worth:,}", kpi1_sub, "#1d1d1f")
kpi2 = kpi("總資產（不含不動產）", f"{TA:,}", kpi2_sub, "#3b82f6")
kpi3 = kpi("總負債", f"{TL:,}", kpi3_sub, "#ef4444")
kpi4 = kpi("負債率（含不動產）", f"{TL/(TA+RE)*100:.1f}%", kpi4_sub, "#d97706")
kpi5 = kpi("現金", f"{CASH:,}", f"底線 70萬 {'✅' if CASH>=700000 else '⚠️'}（餘裕 {(CASH-700000)/10000:.0f}萬）", "#22c55e")

pen_card = card("一、穿透分布（目標 台10/美40/防20/債25/現5）", "🎯",
    f"""<table style="width:100%;font-size:13px;border-collapse:collapse"><tr style="color:#6e6e73"><th style="text-align:left;padding:6px 10px">桶</th><th style="text-align:right;padding:6px 10px">金額</th><th style="text-align:right;padding:6px 10px">現況</th></tr>{pen_rows}</table>""")
dec_card = card("五、今日決策", "⚖️",
    f"""<table style="width:100%;font-size:13px;border-collapse:collapse"><tr style="color:#6e6e73"><th style="text-align:left;padding:5px 10px">類型</th><th style="text-align:left;padding:5px 10px">標的</th><th style="text-align:right;padding:5px 10px">裁決</th></tr>{dec_rows}</table>""")

# footer「下次」動態化：下一個週五 20:00
_next = datetime.date.today()
while _next.weekday() != 4:  # 4 = 週五
    _next += datetime.timedelta(days=1)
if _next <= datetime.date.today():
    _next += datetime.timedelta(days=7)
_next_txt = f"{_next.year}-{_next.month:02d}-{_next.day:02d}（五）20:00"
html = f"""<div style="background:#f5f5f7;font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;padding:20px;max-width:1000px;margin:0 auto">
<h1 style="font-size:22px;font-weight:900;margin:0 0 2px">🏛️ 龍九控股 CEO 深度分析儀表板</h1>
<div style="font-size:13px;color:#6e6e73;margin-bottom:16px">{today}（{'一二三四五六日'[datetime.date.today().weekday()]}）｜ 真值來源：snapshot.json + CEO 分析</div>

<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">
{kpi1}
{kpi2}
{kpi3}
{kpi4}
{kpi5}
</div>

{chg_card}

{flow_card}

{pen_card}

{dd_card}

{card("三大隱憂現狀", "⚠️", worry_html)}

{card("市場事件對持倉影響", "📉", market_html)}

{card("戰略建議（3 條）", "🧭", advice_html)}

{dec_card}

{ms_card}

<div style="font-size:12px;color:#6e6e73;background:#fff;border-radius:12px;padding:12px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)"><b>一句話總結</b>：{summary_txt}</div>
<div style="font-size:11px;color:#94a3b8;margin-top:12px;text-align:center">龍九控股 CEO 深度分析儀表板 ｜ build_ceo_dashboard.py 動態產生 ｜ 下次：{_next_txt}</div>
</div>"""

out = os.path.join(REPO, f"ceo_dashboard_{today}.html")
open(out, "w", encoding="utf-8").write(html)
print(f"✅ {out}（{os.path.getsize(out):,} bytes）")
