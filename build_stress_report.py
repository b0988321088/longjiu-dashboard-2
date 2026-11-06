#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_stress_report.py — 股災壓力測試報告（stress_test_{date}.html）

用途：把「這次股災對資產造成什麼影響」變成可重複產出的頁面，掛在儀表板按鈕。
原則：
  · 全部數字現讀 snapshot／dragon_assets.db／Yahoo 收盤，**不得寫死**（no-hardcode）。
  · 假設一律具名（例：情境衝擊對各桶採 β 假設），不得偽裝成實測。
  · 資料日與價格日各自標示，不把前一交易日收盤說成當日。
"""
from __future__ import annotations

import json
import sqlite3
import urllib.request
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).parent.resolve()
TODAY = date.today().isoformat()


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


def yclose(sym):
    """回傳 (date, close, prev_close) 或 None。"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1mo"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        j = json.load(urllib.request.urlopen(req, timeout=15))["chart"]["result"][0]
        ts, cl = j["timestamp"], j["indicators"]["quote"][0]["close"]
        pts = [(datetime.utcfromtimestamp(t + 8 * 3600).strftime("%Y-%m-%d"), c)
               for t, c in zip(ts, cl) if c]
        if len(pts) >= 2:
            return pts[-1][0], pts[-1][1], pts[-2][1]
    except Exception:
        return None
    return None


def fmt(v, unit="元"):
    return f"{v:,.0f}" if unit == "元" else f"{v:,.2f}"


def build():
    snap = load_snap()
    rows = load_rows(2)
    cur, prev = rows[0], rows[1] if len(rows) > 1 else rows[0]

    tot_now, tot_prev = _num(cur["total_assets"]), _num(prev["total_assets"])
    d_tot = tot_now - tot_prev
    parts = [
        ("現金", _num(cur["cash_total"]), _num(prev["cash_total"])),
        ("證券（台股）", _num(cur["securities"]), _num(prev["securities"])),
        ("基金", _num(cur["funds"]), _num(prev["funds"])),
        ("保險（含保單基金）", _num(cur["insurance"]), _num(prev["insurance"])),
    ]
    pen = snap.get("penetration") or {}
    act_twd = pen.get("actual_twd") or {}
    act_pct = pen.get("actual_pct") or {}
    tw = _num(act_twd.get("台股市值型成長"))
    us = _num(act_twd.get("美股市值型成長"))
    df = _num(act_twd.get("防守型配息"))
    bd = _num(act_twd.get("債券"))
    cash = _num(act_twd.get("現金/安全網"))

    pledge = _num(snap.get("fund_pledge_loan") or 0)
    pool = _num(snap.get("funds_cathay") or 0)
    ratio = pool / pledge * 100 if pledge else 0

    twii = yclose("%5ETWII")
    sox = yclose("%5ESOX")

    # 情境：對投資桶套用假設衝擊（假設具名，非預測）
    scen = []
    for label, s_tw, s_us, s_df, s_bd in [
        ("台股再跌 10%", -0.10, 0, 0, 0),
        ("美股再跌 10%", 0, -0.10, 0, 0),
        ("股債雙殺（台美 -10%、防守 -5%、債 -2%）", -0.10, -0.10, -0.05, -0.02),
        ("極端（台美 -20%、防守 -10%、債 -4%）", -0.20, -0.20, -0.10, -0.04),
    ]:
        d = tw * s_tw + us * s_us + df * s_df + bd * s_bd
        new_tot = tot_now + d
        new_pool = pool * (1 + s_us * 0.8)  # 池以美股部位為主，β 假設 0.8
        scen.append((label, d, new_tot, new_pool / pledge * 100 if pledge else 0))

    def cls(v):
        return "up" if v >= 0 else "down"

    rows_html = "".join(
        f"<tr><td>{n}</td><td class='n'>{fmt(a)}</td><td class='n'>{fmt(b)}</td>"
        f"<td class='n {cls(a-b)}'>{a-b:+,.0f}</td>"
        f"<td class='n {cls(a-b)}'>{(a-b)/b*100:+.2f}%</td></tr>"
        for n, a, b in parts if b)

    scen_html = "".join(
        f"<tr><td>{l}</td><td class='n down'>{d:+,.0f}</td><td class='n'>{t:,.0f}</td>"
        f"<td class='n {'down' if r < 160 else ''}'>{r:.1f}%</td></tr>"
        for l, d, t, r in scen)

    idx_html = ""
    if twii:
        d0, c0, p0 = twii
        idx_html += (f"<li>台股加權 {c0:,.2f}（{d0} 收盤），前一日 {p0:,.2f}，"
                     f"<b class='{'up' if c0>=p0 else 'down'}'>{c0-p0:+,.2f}（{(c0-p0)/p0*100:+.2f}%）</b></li>")
    if sox:
        d1, c1, p1 = sox
        idx_html += (f"<li>費城半導體 {c1:,.2f}（{d1} 收盤），前一日 {p1:,.2f}，"
                     f"<b class='{'up' if c1>=p1 else 'down'}'>{c1-p1:+,.2f}（{(c1-p1)/p1*100:+.2f}%）</b></li>")

    pct_tot = d_tot / tot_prev * 100 if tot_prev else 0
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
.card{{background:#111c2e;border:1px solid #1f2c44;border-radius:14px;padding:16px 18px;margin:12px 0}}
.big{{font-size:32px;font-weight:900}}
.down{{color:#f87171}} .up{{color:#34d399}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin-top:8px}}
th,td{{padding:8px 6px;border-bottom:1px solid #1f2c44;text-align:left}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}}
ul{{margin:8px 0 0;padding-left:20px}} li{{margin:4px 0}}
.tag{{display:inline-block;font-size:12px;background:#1e293b;border:1px solid #334155;border-radius:999px;padding:2px 10px;color:#cbd5e1;margin-right:6px}}
a{{color:#34d399}}
</style></head><body><div class="wrap">
<h1>股災壓力測試・{TODAY}</h1>
<div class="sub">資料基準：{cur['date']}｜比較基準：{prev['date']}｜全部數字現讀 snapshot／DB，未經人工填寫</div>

<div class="card">
  <div class="sub" style="margin:0">總資產（{cur['date']} vs {prev['date']}）</div>
  <div class="big {'down' if d_tot<0 else 'up'}">{tot_now:,.0f} <span style="font-size:16px">({d_tot:+,.0f}／{pct_tot:+.2f}%)</span></div>
</div>

<h2>一、衝擊歸因（逐部位）</h2>
<div class="card">
<table>
<tr><th>部位</th><th class="n">本次</th><th class="n">前次</th><th class="n">差異</th><th class="n">幅度</th></tr>
{rows_html}
</table>
<div class="sub" style="margin:8px 0 0">註：基金與保單的變動含「估值日推進」（淨值日由前次推進至最新），不完全是單日跌幅。</div>
</div>

<h2>二、市場對照</h2>
<div class="card"><ul>{idx_html or '<li>行情取得失敗（不補值）</li>'}</ul></div>

<h2>三、質押壓力</h2>
<div class="card">
<ul>
<li>借款 <b>{pledge:,.0f}</b>｜擔保池（國泰三檔）<b>{pool:,.0f}</b>｜維持率 <b class="{'down' if ratio<160 else 'up'}">{ratio:.1f}%</b></li>
<li>距銀行通知線 160%：池需再跌 <b>{(1-pledge*1.6/pool)*100:.1f}%</b></li>
<li>距追繳線 140%：池需再跌 <b>{(1-pledge*1.4/pool)*100:.1f}%</b></li>
</ul>
</div>

<h2>四、情境壓力（假設，非預測）</h2>
<div class="card">
<table>
<tr><th>情境</th><th class="n">總資產影響</th><th class="n">情境後總資產</th><th class="n">維持率</th></tr>
{scen_html}
</table>
<div class="sub" style="margin:8px 0 0">假設：台股／美股桶 β=1.0、防守 0.5、債券 0.2；擔保池以美股 β=0.8 估算。僅供壓力測試，不代表預測。</div>
</div>

<h2>五、現金流是否受影響</h2>
<div class="card">
<ul>
<li>配息為「單位數 × 每單位配息」，價格下跌不影響單位數 → 月配現金流不變。</li>
<li>質押只繳息（月付約 {pledge*_num(snap.get('fund_pledge_rate'))/12:,.0f}，利率 {_num(snap.get('fund_pledge_rate'))*100:.2f}%），與市值無關。</li>
<li>房租、薪資與市場無關。</li>
</ul>
</div>

<h2>六、結論</h2>
<div class="card">
<ul>
<li>本次回檔對總資產的影響為 <b class="{'down' if d_tot<0 else 'up'}">{pct_tot:+.2f}%</b>，主因台股部位僅 {_num(act_pct.get('台股市值型成長')):.1f}%，不是重傷。</li>
<li>真正的風險不是今天，是<b>美股桶 {_num(act_pct.get('美股市值型成長')):.1f}%（目標 30%）超標</b>與台幣升值同時發生。</li>
<li>紀律不變：11 月凍結、不接刀、不停損、不攤平；減碼窗口是反彈。</li>
</ul>
</div>
<div class="sub">產生時間 {datetime.now().strftime('%Y-%m-%d %H:%M')}｜來源：snapshot.json／dragon_assets.db／Yahoo Finance</div>
</div></body></html>"""
    out = BASE / f"stress_test_{TODAY}.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ {out.name}（{len(html):,} chars）")
    return out


if __name__ == "__main__":
    build()
