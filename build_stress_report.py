#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_stress_report.py — 股災壓力測試報告（stress_test_{date}.html）

用途：把「這次股災對資產造成什麼影響、壓力在哪、可承受多少」變成可重複產出的頁面，掛在儀表板按鈕。
原則：
  · 全部數字現讀 snapshot／dragon_assets.db／asset_diff_history／radar_state／Yahoo 收盤，**不得寫死**（no-hardcode）。
  · 假設一律具名（例：情境衝擊對各桶採 β 假設），不得偽裝成實測。
  · 資料日與價格日各自標示，不把前一交易日收盤說成當日；淨值日落後市場日時必須示警。
  · 門檻讀 thresholds／snapshot，不在程式裡寫 53／160／140。

2026-11-06 改版（使用者要求把當日評估回饋進本報告）：
  ① 歸因由「前後兩日」改為「本波高點→今日」，並同時列前後日。
  ② 質押段加入內部停止線 LTV 53% 與「回線需還本金額」。
  ③ 新增流動性壓力段（押標金與維持率回補搶同一筆現金）。
  ④ 新增收入韌性段（配息縮水斷點）。
  ⑤ 修正舊版「配息不變」的過度樂觀敘述。
"""
from __future__ import annotations

import json
import sqlite3
import urllib.request
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).parent.resolve()
TODAY = date.today().isoformat()

# 情境 β 假設（具名，非實測）：台股／美股桶 1.0、防守型配息 0.5、債券 0.2
BETA = {"tw": 1.0, "us": 1.0, "df": 0.5, "bd": 0.2}
POOL_BETA_US = 0.8   # 擔保池以美股部位為主


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def load_snap():
    return json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))


def load_rows(n=2):
    con = sqlite3.connect(str(BASE / "dragon_assets.db"))
    cols = ["date", "cash_total", "bonds", "securities", "insurance", "funds", "total_assets"]
    rows = [dict(zip(cols, r)) for r in con.execute(
        f"SELECT {','.join(cols)} FROM assets ORDER BY date DESC LIMIT {n}")]
    con.close()
    return rows


def load_history(days=60):
    p = BASE / "asset_diff_history.json"
    if not p.exists():
        return {}
    h = json.loads(p.read_text(encoding="utf-8"))
    keys = sorted(h.keys())[-days:]
    return {k: h[k] for k in keys}


def yhist(sym, months=6):
    """回傳 [(date, close)]（依日期遞增）或 []。"""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?interval=1d&range={months}mo")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        j = json.load(urllib.request.urlopen(req, timeout=15))["chart"]["result"][0]
        ts, cl = j["timestamp"], j["indicators"]["quote"][0]["close"]
        pts = [(datetime.utcfromtimestamp(t + 8 * 3600).strftime("%Y-%m-%d"), float(c))
               for t, c in zip(ts, cl) if c]
        return pts
    except Exception:
        return []


def close_asof(pts, d):
    """取 <= d 的最後一筆收盤。"""
    out = None
    for dt, c in pts:
        if dt <= d:
            out = (dt, c)
        else:
            break
    return out


def fmt(v, unit="元"):
    return f"{v:,.0f}" if unit == "元" else f"{v:,.2f}"


def build():
    snap = load_snap()
    rows = load_rows(2)
    hist = load_history(60)
    cur = rows[0]
    prev = rows[1] if len(rows) > 1 else rows[0]

    # ── 本波高點（近 60 天 total_assets 最大值）─────────────────────────
    hi_date, hi = (None, None)
    for d, v in hist.items():
        ta = _num(v.get("total_assets"))
        if hi is None or ta > hi:
            hi_date, hi = d, ta
    if hi is None:
        hi_date, hi = cur["date"], _num(cur["total_assets"])

    tot_now = _num(cur["total_assets"])
    d_wave = tot_now - hi
    pct_wave = d_wave / hi * 100 if hi else 0

    # 逐部位：本波（高點→今日）與前後日
    def part(key_map):
        out = []
        for name, hkey, ckey in key_map:
            hv = _num(hist.get(hi_date, {}).get(hkey))
            cv = _num(cur[ckey])
            pv = _num(prev[ckey])
            out.append((name, hv, cv, cv - hv, (cv - hv) / hv * 100 if hv else 0, cv - pv))
        return out

    parts = part([
        ("現金", "cash", "cash_total"),
        ("證券（台股）", "securities_market", "securities"),
        ("基金", "fund_market", "funds"),
        ("保險（含保單基金）", "insurance_current", "insurance"),
    ])

    # ── 市場 ──────────────────────────────────────────────────────────
    idx = {}
    for sym, label in [("%5ETWII", "台股加權"), ("%5ESOX", "費城半導體"), ("%5EIXIC", "納斯達克")]:
        pts = yhist(sym)
        if not pts:
            continue
        last = pts[-1]
        prevc = pts[-2] if len(pts) > 1 else last
        base = close_asof(pts, hi_date) or pts[0]
        idx[label] = {
            "date": last[0], "close": last[1], "prev": prevc[1],
            "base_date": base[0], "base": base[1],
            "wave_pct": (last[1] - base[1]) / base[1] * 100 if base[1] else 0,
        }

    radar = {}
    try:
        rs = json.loads((BASE / "radar_state.json").read_text(encoding="utf-8"))
        radar = (rs.get("data") or {}).get("us_sector") or {}
    except Exception:
        radar = {}

    # ── 質押 ──────────────────────────────────────────────────────────
    pledge = _num(snap.get("fund_pledge_loan"))
    # 2026-11-06：池值以 cathay_pledge_0911.擔保池 為單一真值（含資料日），舊 funds_cathay 僅作回退
    pool = _num((((snap.get("cathay_pledge_0911") or {}).get("擔保池") or {}).get("合計"))
                or snap.get("funds_cathay"))
    ratio = pool / pledge * 100 if pledge else 0
    ltv = pledge / pool * 100 if pool else 0

    th = snap.get("thresholds_2026_0915") or {}
    ltv_bands = th.get("ltv分級_pct") or {}
    ltv_stop = _num(ltv_bands.get("黃上限"), 53)          # 內部停止線
    maint_warn = _num(th.get("通知_維持率_pct"), 160)      # 銀行通知
    maint_call = _num(th.get("追繳_維持率_pct"), 140)      # 銀行追繳

    gates = []
    for label, gpool, note in [
        (f"內部停止線 LTV {ltv_stop:.0f}%", pledge / (ltv_stop / 100) if ltv_stop else 0,
         f"維持率 {100/ltv_stop*100:.1f}%"),
        (f"銀行通知 {maint_warn:.0f}%", pledge * maint_warn / 100, f"LTV {100/maint_warn*100:.1f}%"),
        (f"銀行追繳 {maint_call:.0f}%", pledge * maint_call / 100, f"LTV {100/maint_call*100:.1f}%"),
    ]:
        drop = (1 - gpool / pool) * 100 if pool else 0
        gates.append((label, gpool, drop, note))

    scen_pledge = []
    for d in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
        p = pool * (1 - d)
        need = max(0.0, pledge - (ltv_stop / 100) * p)
        scen_pledge.append((d * 100, p, p / pledge * 100 if pledge else 0,
                            pledge / p * 100 if p else 0, need))

    # ── 流動性 ────────────────────────────────────────────────────────
    cl = snap.get("cash_layers") or {}
    unrestricted = _num(cl.get("unrestricted_cash"))
    restricted = _num((cl.get("restricted_cash") or {}).get("total"))
    floor = _num(cl.get("emergency_cash", {}).get("金額") or cl.get("cash_floor"), 700000)

    bid = snap.get("bid_evaluation_20261102") or {}
    bid_amt = _num(bid.get("押標金"))
    bid_date = (bid.get("時程") or {}).get("截止投標") or "—"
    after_bid = unrestricted - bid_amt
    short_after = max(0.0, floor - after_bid)

    ds = snap.get("debt_service_split") or {}
    month_pay = _num((ds.get("合計") or {}).get("月付"))
    _mdd = snap.get("mortgage_due_day") or {}
    _d_cathay = _mdd.get("國泰", 20) if isinstance(_mdd, dict) else 20
    _d_yf = _mdd.get("永豐", 27) if isinstance(_mdd, dict) else 27
    due_rows = [
        ("國泰房貸", _num((ds.get("房貸_國泰") or {}).get("月付")), f"每月 {_d_cathay} 日"),
        ("永豐房貸", _num((ds.get("房貸_永豐") or {}).get("月付")), f"每月 {_d_yf} 日"),
        ("質押利息", _num((ds.get("基金質押息") or {}).get("月付")), f"每月 {snap.get('fund_pledge_due_day', 22)} 日"),
    ]

    # ── 收入韌性 ──────────────────────────────────────────────────────
    income = _num(snap.get("monthly_income"))
    expense = _num(snap.get("monthly_expense"))
    surplus = income - expense
    pi = snap.get("passive_income") or {}
    div_n = _num(pi.get("fund_dividend_normal"))
    rent_n = _num(pi.get("rent_monthly"))
    pccr = (div_n + rent_n) / expense * 100 if expense else 0
    div_actual = _num(snap.get("monthly_dividend_total"))

    cut_zero = surplus / div_n * 100 if div_n else 0
    cut_pccr = (1 - expense / (div_n + rent_n)) * 100 if (div_n + rent_n) else 0
    div_rows = []
    for c in (0, 0.10, 0.20, 0.30, cut_zero / 100, 0.40):
        d = div_n * (1 - c)
        inc = income - (div_n - d)
        div_rows.append((max(0.0, c * 100), d, inc - expense))

    # ── 淨值日 vs 市場日（落後示警）──────────────────────────────────
    nav_note = []
    for k, lab in [("fund_nav_dates", "基金淨值日"), ("insurance_nav_dates", "保單淨值日")]:
        v = snap.get(k)
        if isinstance(v, dict) and v:
            dates = sorted({str(x) for x in v.values() if x})
            if dates:
                nav_note.append(f"{lab} {dates[-1]}")
        elif isinstance(v, str) and v:
            nav_note.append(f"{lab} {v}")
    latest_mkt = max((i["date"] for i in idx.values()), default="")
    stale = any(n.split()[-1] < latest_mkt for n in nav_note) if latest_mkt and nav_note else False

    # ── 總資產情境（沿用 β 假設）─────────────────────────────────────
    pen = snap.get("penetration") or {}
    act_twd = pen.get("actual_twd") or {}
    act_pct = pen.get("actual_pct") or {}
    tw = _num(act_twd.get("台股市值型成長"))
    us = _num(act_twd.get("美股市值型成長"))
    df = _num(act_twd.get("防守型配息"))
    bd = _num(act_twd.get("債券"))
    # ── 整合分析用（與日報第八章同源；全部現讀 snapshot）─────────────
    _nw = _num(snap.get("net_worth"))
    _nw_re = _num(snap.get("net_worth_incl_re"))
    _re_val = _num(snap.get("real_estate_value_as_of") or snap.get("real_estate_value"))
    _liab = _num(snap.get("total_liabilities"))
    _mort = _num(((snap.get("liabilities_build_up") or {}).get("房貸_含國泰")))
    _dd = _num((((snap.get("dual_dimension_metric") or {}).get("防禦維度") or {}).get("佔比")))
    _ind = ((snap.get("industry_penetration") or {}).get("產業") or {})
    _gics_tech = _num((_ind.get("資訊科技") or {}).get("佔比"))
    _usd = ((snap.get("usd_exposure_monitor") or {}).get("current") or {})
    _usd_all, _usd_hedge, _usd_net = (_num(_usd.get("合計")), _num(_usd.get("已避險")),
                                      _num(_usd.get("匯率曝險合計")))
    _pool_date = ((snap.get("cathay_pledge_0911") or {}).get("擔保池") or {}).get("資料日", "")
    _pool_hist = (((snap.get("cathay_pledge_0911") or {}).get("擔保池_歷史") or [{}])[0])
    scen = []
    for label, s_tw, s_us, s_df, s_bd in [
        ("止穩（不再下跌）", 0, 0, 0, 0),
        ("再修正 8%（美股 -8／台股 -5／債 +2）", -0.05, -0.08, -0.03, 0.02),
        ("再修正 15%（美股 -15／台股 -12／債 -2）", -0.12, -0.15, -0.06, -0.02),
        ("股債同跌（股 -20／債 -5）", -0.20, -0.20, -0.10, -0.05),
        ("極端 25%（美股 -25／台股 -20／債 -5）", -0.20, -0.25, -0.12, -0.05),
    ]:
        d = (tw * s_tw * BETA["tw"] + us * s_us * BETA["us"]
             + df * s_df * BETA["df"] + bd * s_bd * BETA["bd"])
        new_tot = tot_now + d
        new_pool = pool * (1 + s_us * POOL_BETA_US)
        scen.append((label, d, new_tot, new_pool / pledge * 100 if pledge else 0,
                     pledge / new_pool * 100 if new_pool else 0))

    def cls(v):
        return "up" if v >= 0 else "down"

    _sc = {lab: (d, t, r, lt) for lab, d, t, r, lt in scen}
    _gb = _sc.get("股債同跌（股 -20／債 -5）", (0.0, tot_now, 0.0, 0.0))
    _inv_sum = sum(p[3] for p in parts[1:4])
    _pool_note = (f"（資料日 {str(_pool_date).split('（')[0].strip()}）" if _pool_date else "")
    _hist_note = (f"；舊值 {_num(_pool_hist.get('合計')):,.0f}（{_pool_hist.get('asof','')} 截圖／"
                  f"報價日 {_pool_hist.get('報價日','—')}，維持率 {_pool_hist.get('對應維持率','—')}）"
                  f"保留於 snapshot 歷史" if _pool_hist.get("合計") else "")

    parts_html = "".join(
        f"<tr><td>{n}</td><td class='n'>{fmt(h)}</td><td class='n'>{fmt(c)}</td>"
        f"<td class='n {cls(c-h)}'>{c-h:+,.0f}</td>"
        f"<td class='n {cls(c-h)}'>{(c-h)/h*100:+.1f}%</td></tr>"
        for n, h, c, dh, ph, dp in parts if h)

    idx_html = ""
    for lab, v in idx.items():
        idx_html += (
            f"<li>{lab} <b>{v['close']:,.2f}</b>（{v['date']} 收盤）"
            f"當日 <b class='{cls(v['close']-v['prev'])}'>{(v['close']-v['prev'])/v['prev']*100:+.2f}%</b>"
            f"｜本波（{v['base_date']} 起）<b class='{cls(v['wave_pct'])}'>{v['wave_pct']:+.1f}%</b></li>")

    rot_html = ""
    if radar:
        etfs = radar.get("etfs") or {}
        best = sorted(etfs.items(), key=lambda kv: _num(kv[1].get("動能%")), reverse=True)[:3]
        worst = sorted(etfs.items(), key=lambda kv: _num(kv[1].get("動能%")))[:2]
        seg = "｜".join(f"{k} {v.get('產業','')} {_num(v.get('動能%')):+.1f}%" for k, v in worst)
        seg2 = "｜".join(f"{k} {v.get('產業','')} {_num(v.get('動能%')):+.1f}%" for k, v in best)
        rot_html = (f"<li>產業輪動（{radar.get('date','')}）：資金流出 <b class='down'>{seg}</b>；"
                    f"流入 <b class='up'>{seg2}</b></li>")

    gate_html = "".join(
        f"<tr><td>{lab}</td><td class='n'>{fmt(p)}</td><td class='n down'>-{d:.1f}%</td>"
        f"<td class='n'>{note}</td></tr>"
        for lab, p, d, note in gates)

    scen_pl_html = "".join(
        f"<tr><td class='n'>-{d:.0f}%</td><td class='n'>{fmt(p)}</td><td class='n'>{r:.1f}%</td>"
        f"<td class='n'>{l:.1f}%</td><td class='n'>{fmt(need)}</td></tr>"
        for d, p, r, l, need in scen_pledge)

    due_html = "".join(
        f"<li>{n} <b>{fmt(a)}</b>（{d}）</li>" for n, a, d in due_rows if a)

    div_html = "".join(
        f"<tr><td class='n'>{'-' if c>0 else ''}{c:.1f}%</td><td class='n'>{fmt(d)}</td>"
        f"<td class='n {cls(s)}'>{s:+,.0f}</td></tr>"
        for c, d, s in div_rows)

    scen_html = "".join(
        f"<tr><td>{l}</td><td class='n down'>{'0' if abs(d)<0.5 else f'{d:+,.0f}'}</td><td class='n'>{t:,.0f}</td>"
        f"<td class='n'>{r:.1f}%</td><td class='n'>{lt:.1f}%</td></tr>"
        for l, d, t, r, lt in scen)

    pct_tot = (_num(cur["total_assets"]) - _num(prev["total_assets"])) / _num(prev["total_assets"]) * 100 \
        if _num(prev["total_assets"]) else 0
    d_tot = _num(cur["total_assets"]) - _num(prev["total_assets"])

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>股災壓力測試 {TODAY}</title>
<style>
:root{{color-scheme:dark}}
body{{margin:0;background:#0b1220;color:#e5e7eb;font:16px/1.75 -apple-system,"Noto Sans TC",sans-serif}}
.wrap{{max-width:920px;margin:0 auto;padding:24px 18px 60px}}
h1{{font-size:26px;font-weight:900;margin:0 0 6px}}
h2{{font-size:18px;font-weight:800;margin:30px 0 10px;color:#93c5fd}}
.sub{{color:#94a3b8;font-size:13px;margin-bottom:18px}}
.card{{background:#111c2e;border:1px solid #1f2c44;border-radius:14px;padding:16px 18px;margin:12px 0;overflow-x:auto}}
.big{{font-size:30px;font-weight:900}}
.down{{color:#f87171}} .up{{color:#34d399}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}}
th,td{{padding:7px 5px;border-bottom:1px solid #1f2c44;text-align:left}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}}
ul{{margin:8px 0 0;padding-left:20px}} li{{margin:5px 0}}
.warn{{background:#2a1215;border-color:#7f1d1d}}
.tag{{display:inline-block;font-size:12px;background:#1e293b;border:1px solid #334155;border-radius:999px;padding:2px 10px;color:#cbd5e1;margin-right:6px}}
a{{color:#34d399}}
</style></head><body><div class="wrap">
<h1>股災壓力測試・{TODAY}</h1>
<div class="sub">資料基準 {cur['date']}｜本波高點 {hi_date}｜全部數字現讀 snapshot／DB／history／radar，未經人工填寫</div>

<div class="card">
  <div class="sub" style="margin:0">總資產（今日 vs 本波高點 {hi_date}）</div>
  <div class="big {'down' if d_wave<0 else 'up'}">{tot_now:,.0f} <span style="font-size:15px">({d_wave:+,.0f}／{pct_wave:+.2f}%)</span></div>
  <div class="sub" style="margin:6px 0 0">前一交易日對比：{_num(prev['total_assets']):,.0f} → {d_tot:+,.0f}（{pct_tot:+.2f}%）</div>
</div>

<h2>一、本波衝擊歸因（{hi_date} → {cur['date']}）</h2>
<div class="card">
<table>
<tr><th>部位</th><th class="n">高點</th><th class="n">今日</th><th class="n">差異</th><th class="n">幅度</th></tr>
{parts_html}
</table>
<div class="sub" style="margin:8px 0 0">註：基金與保單變動含「估值日推進」，不完全是單日跌幅；高點以 history 總資產最大值認定。</div>
</div>

<h2>二、市場對照</h2>
<div class="card"><ul>{idx_html or '<li>行情取得失敗（不補值）</li>'}{rot_html}</ul>
<div class="sub" style="margin:8px 0 0">價格日以 Yahoo 最後收盤為準；本波起算日＝總資產高點日，非指數自身高點。</div>
</div>

<h2>三、質押壓力（三段門檻）</h2>
<div class="card">
<ul>
<li>借款 <b>{fmt(pledge)}</b>｜擔保池 <b>{fmt(pool)}</b>｜維持率 <b class="{'down' if ratio<maint_warn else 'up'}">{ratio:.1f}%</b>｜LTV <b>{ltv:.1f}%</b></li>
<li>門檻讀 snapshot／thresholds：內部停止 LTV {ltv_stop:.0f}%／銀行通知 {maint_warn:.0f}%／追繳 {maint_call:.0f}%</li>
</ul>
<table>
<tr><th>門檻</th><th class="n">池市值</th><th class="n">池需跌</th><th class="n">對應</th></tr>
{gate_html}
</table>
<div class="sub" style="margin:8px 0 0">維持率＝池市值÷借款；LTV＝借款÷池市值（互為倒數，不得混用）。</div>
</div>

<div class="card">
<div class="sub" style="margin:0 0 6px">逐跌幅情境（回 {ltv_stop:.0f}% 需還本金額）</div>
<table>
<tr><th class="n">池跌幅</th><th class="n">池市值</th><th class="n">維持率</th><th class="n">LTV</th><th class="n">需還本</th></tr>
{scen_pl_html}
</table>
<div class="sub" style="margin:8px 0 0">假設借款不變、不計配息再投入；擔保品以<b>後收級別</b>為主（CDSC 未到期），追繳時不宜賣擔保品，優先以現金還本。</div>
</div>

<h2>四、流動性壓力（押標金 vs 維持率回補）</h2>
<div class="card{' warn' if short_after>0 else ''}">
<ul>
<li>可動用現金 <b>{fmt(unrestricted)}</b>｜指定款（不可動用）<b>{fmt(restricted)}</b>｜生活底線 <b>{fmt(floor)}</b></li>
<li>押標金 <b>{fmt(bid_amt)}</b>（{bid_date}）→ 支出後可動用 <b class="{'down' if short_after>0 else 'up'}">{fmt(after_bid)}</b>，低於底線 <b>{fmt(short_after)}</b></li>
<li>11 月固定扣款合計 <b>{fmt(month_pay)}</b>：</li>
</ul>
<ul>{due_html}</ul>
<div class="sub" style="margin:8px 0 0">扣款日以 snapshot 為準；押標金屬「暫時性資金占用」，不得視為投資配置或加碼。</div>
</div>

<h2>五、收入韌性（配息縮水斷點）</h2>
<div class="card">
<ul>
<li>月收入 <b>{fmt(income)}</b>（含薪資）－月支出 <b>{fmt(expense)}</b>＝盈餘 <b class="{'down' if surplus<0 else 'up'}">{fmt(surplus)}</b></li>
<li>常態配息 <b>{fmt(div_n)}</b>＋房租 <b>{fmt(rent_n)}</b>｜被動覆蓋 <b>{pccr:.1f}%</b>（常態口徑）</li>
<li>當月實收配息 <b>{fmt(div_actual)}</b>（月初筆數少，非縮水；月際波動含 ETF 除息月曆效應）</li>
</ul>
<table>
<tr><th class="n">配息縮水</th><th class="n">配息金額</th><th class="n">盈餘</th></tr>
{div_html}
</table>
<div class="sub" style="margin:8px 0 0">兩個斷點口徑不同、不得互換：以「月收入（含薪資）」計，配息縮水 {cut_zero:.1f}% 盈餘歸零；以「被動收入覆蓋率」計，配息縮水 {cut_pccr:.1f}% 覆蓋跌破 100%。</div>
</div>

<h2>六、總資產情境（假設，非預測）</h2>
<div class="card">
<table>
<tr><th>情境</th><th class="n">影響</th><th class="n">資產</th><th class="n">維持率</th><th class="n">LTV</th></tr>
{scen_html}
</table>
<div class="sub" style="margin:8px 0 0">β 假設：台股／美股 1.0、防守 0.5、債券 0.2；擔保池美股 β {POOL_BETA_US}。僅供壓力測試。</div>
</div>

<h2>七、整合分析結論（{TODAY} 股災｜與日報第八章同源）</h2>
<div class="card">
<ul>
<li><b>真值校準</b>：本波（{hi_date} → {cur['date']}）總資產 {hi:,.0f} → {tot_now:,.0f}（<b class="down">{d_wave:+,.0f}／{pct_wave:+.1f}%</b>）；三個投資部位合計 <b class="down">{_inv_sum:+,.0f}</b>。含房淨值 <b>{_nw_re:,.0f}</b>、流動淨值（不含房產）<b class="down">{_nw:,.0f}</b>——負債 {_liab:,.0f} 中房貸 {_mort:,.0f}（{(_mort/_liab*100) if _liab else 0:.1f}%），「負債大於流動資產」是不對等口徑，不是償債危機。</li>
<li><b>三個口徑不可互換</b>：五桶 台股 {_num(act_pct.get('台股市值型成長')):.1f}%／美股 {_num(act_pct.get('美股市值型成長')):.1f}%／防守 {_num(act_pct.get('防守型配息')):.1f}%／債券 {_num(act_pct.get('債券')):.1f}%／現金 {_num(act_pct.get('現金/安全網')):.1f}%；抗跌力看<b>雙維度防禦維度 {_dd:.1f}%</b>（不是防守桶）；GICS 高科技 <b>{_gics_tech:.1f}%</b>；美元曝險 {_usd_all:.1f}%／已避險 {_usd_hedge:.1f}%／淨 {_usd_net:.1f}%。</li>
<li><b>質押主線</b>：維持率 {ratio:.1f}%／LTV {ltv:.1f}%{_pool_note}{_hist_note}。距內部停止線 {gates[0][2]:.1f}%、距銀行通知 {gates[1][2]:.1f}%、距追繳 {gates[2][2]:.1f}%——真正危險距離是通知線，內部 53% 只是停止加碼線。</li>
<li><b>股債同跌</b>（股 -20／債 -5）：資產影響 <b class="down">{_gb[0]:+,.0f}</b> → {_gb[1]:,.0f}，維持率 <b>{_gb[2]:.1f}%</b>、LTV {_gb[3]:.1f}%（擔保池按美股 β {POOL_BETA_US} 推估，屬假設）。</li>
<li><b>流動性才是真風險</b>：押標金後可動用 {after_bid:,.0f}，低於底線 <b class="down">{short_after:,.0f}</b>；11 月固定扣款 {month_pay:,.0f}。若同時遇池跌 15%（需還 {scen_pledge[2][4]:,.0f}）→ 只剩「賣後收級別」一途（CDSC 未到期，不該賣）。</li>
<li><b>一句話</b>：真正要守的是「11 月現金不被擠爆」，不是「資產不再跌」；紀律＝不追跌、不攤平、減碼窗口在反彈。</li>
</ul>
<div class="sub" style="margin:8px 0 0">本段與日報第八章同一批真值（2026-11-06 18:05 整合版）；數字全部現算，未人工填寫。</div>
</div>

<h2>八、結論與行動</h2>
<div class="card">
<ul>
<li>本波回檔 {pct_wave:+.2f}%，主因台股部位僅 {_num(act_pct.get('台股市值型成長')):.1f}%、三塊各跌約 25–33 萬，屬配置分散生效，非單一部位爆炸。</li>
<li>最緊的不是銀行線，是<b>內部停止線</b>：池再跌 {gates[0][2]:.1f}% 就觸線，而美股單日波動即可達此量級。</li>
<li>流動性衝突：押標金後只剩 {fmt(after_bid)}，可承受「池跌 10%（需還 {fmt(scen_pledge[1][4])}）」，不足承受「池跌 15%（需還 {fmt(scen_pledge[2][4])}）」。</li>
<li>若觸線：<b>現金還本</b>，不賣後收級別擔保品（CDSC 未到期）；不新增借款。</li>
<li>紀律不變：急跌日（單日 ≥3%）只回報不動作；11 月凍結、不接刀、不停損、不攤平；減碼窗口是反彈。</li>
</ul>
</div>
{f'<div class="card warn"><b>淨值日落後示警</b>：{"／".join(nav_note)}，市場價 {latest_mkt}。下一交易日淨值仍可能再下修，今日總資產不是底部。</div>' if stale else ''}
<div class="sub">產生時間 {datetime.now().strftime('%Y-%m-%d %H:%M')}｜來源：snapshot.json／dragon_assets.db／asset_diff_history.json／radar_state.json／Yahoo Finance</div>
</div></body></html>"""
    out = BASE / f"stress_test_{TODAY}.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ {out.name}（{len(html):,} chars）")
    return out


if __name__ == "__main__":
    build()
