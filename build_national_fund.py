#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_national_fund.py — 國安基金護盤：機制與買超清單（national_fund_{date}.html）

資料源：data/national_fund.json（唯一真值，人工維護：官方新聞稿＋結算報告）
原則：純 inline CSS、不依賴 CDN，手機優先；金額全部從 JSON 讀，不寫死在模板。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent.resolve()
SRC = BASE / "data" / "national_fund.json"
TODAY = date.today().isoformat()


def money(v, unit="億"):
    if v is None:
        return "—"
    if unit == "億":
        return f"{v / 1e8:,.2f} 億"
    return f"{v:,.0f}"


def pct(v):
    return "—" if v is None else f"{v:.0f}%"


def build() -> Path:
    d = json.loads(SRC.read_text(encoding="utf-8"))
    cur = d.get("current") or {}
    mech = d.get("mechanism") or []
    r9 = (d.get("history") or {}).get("round9") or {}
    r8 = (d.get("history") or {}).get("round8") or {}
    holds = r9.get("holdings") or []
    imp = d.get("portfolio_impact") or []
    risks = d.get("risks") or []

    total_cost = sum(float(h.get("cost") or 0) for h in holds)

    hold_rows = []
    for h in holds:
        share = (float(h.get("cost") or 0) / total_cost * 100) if total_cost else 0
        hold_rows.append(
            "<tr>"
            f"<td><b>{h.get('ticker', '')}</b><div class='sub'>{h.get('name', '')}</div></td>"
            f"<td class='n'>{money(h.get('cost'))}</td>"
            f"<td class='n'>{share:.1f}%</td>"
            f"<td class='n'>{money(h.get('profit'))}</td>"
            f"<td>{h.get('note', '')}</td>"
            "</tr>"
        )

    imp_rows = "".join(
        f"<tr><td><b>{i.get('holding', '')}</b></td><td>{i.get('link', '')}</td><td>{i.get('note', '')}</td></tr>"
        for i in imp
    )
    mech_li = "".join(f"<li>{m}</li>" for m in mech)
    risk_li = "".join(f"<li>{r}</li>" for r in risks)
    src_li = "".join(
        f"<li>{s.get('label', '')}<div class='sub'>{s.get('note', '')}</div></li>"
        for s in (d.get("sources") or [])
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>國安基金護盤：機制與買超清單 {TODAY}</title>
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;padding:14px;background:#0b1220;color:#e2e8f0;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang TC","Microsoft JhengHei",sans-serif;
 font-size:14px;line-height:1.65;-webkit-text-size-adjust:100%}}
h1{{font-size:18px;margin:2px 0 4px}}
h2{{font-size:15px;margin:22px 0 8px;padding-left:9px;border-left:4px solid #38bdf8}}
.card{{background:#131c2e;border:1px solid #1f2b42;border-radius:12px;padding:12px 13px;margin:10px 0}}
.tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;
 background:#1e3a5f;color:#93c5fd;border:1px solid #2b4c74;margin-right:6px}}
.sub{{font-size:11.5px;color:#93a3bb}}
ul{{margin:6px 0 0;padding-left:18px}}
li{{margin:4px 0}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}}
th,td{{padding:7px 6px;border-bottom:1px solid #1f2b42;vertical-align:top;text-align:left}}
th{{color:#93a3bb;font-weight:600;font-size:11.5px;background:#0f1a2b}}
.n{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}
.kv{{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px dashed #1f2b42}}
.kv:last-child{{border-bottom:0}}
.kv b{{color:#fff;font-weight:700}}
.warn{{background:#2a1710;border:1px solid #7c2d12;color:#fed7aa}}
.ok{{background:#0f2418;border:1px solid #14532d;color:#bbf7d0}}
.foot{{margin:18px 0 6px;font-size:11px;color:#64748b}}
</style>
</head>
<body>
<h1>🏦 國安基金護盤：機制與買超清單</h1>
<div class="sub">更新 {d.get('updated_at', TODAY)}｜資料源：data/national_fund.json（官方新聞稿＋退場結算報告）</div>

<div class="card">
  <div><span class="tag">{cur.get('round', '')}</span><span class="tag">{cur.get('decision_date', '')}</span></div>
  <div class="kv"><span>額度</span><b>{cur.get('budget', '—')}</b></div>
  <div class="kv"><span>決策會議</span><b>{cur.get('decision_body', '—')}</b></div>
  <div class="kv"><span>揭露狀態</span><b>本次清單未公布</b></div>
  <div style="margin-top:8px" class="sub">{cur.get('market_context', '')}</div>
  <div style="margin-top:8px" class="sub">{cur.get('status', '')}</div>
</div>

<h2>一、機制重點（為什麼是那些股票）</h2>
<div class="card"><ul>{mech_li}</ul></div>

<h2>二、第 9 次實際買進（最近一次完整結算）</h2>
<div class="card">
  <div class="sub">{r9.get('label', '')}｜{r9.get('period', '')}</div>
  <div class="kv"><span>投入金額</span><b>{money(r9.get('invested'))}</b></div>
  <div class="kv"><span>處分淨利＋股利</span><b>{money(r9.get('net_profit'))}</b></div>
  <div class="kv"><span>報酬率</span><b>{pct(r9.get('return_pct'))}</b></div>
  <table>
    <tr><th>標的</th><th class="n">投入成本</th><th class="n">占比</th><th class="n">處分獲利</th><th>定位</th></tr>
    {''.join(hold_rows)}
  </table>
  <div class="sub" style="margin-top:8px">中小型股、櫃買（OTC）買超為 0；8 檔全數獲利出場。</div>
</div>

<h2>三、第 8 次（對照）</h2>
<div class="card">
  <div class="kv"><span>檔數</span><b>{r8.get('count', '—')} 檔</b></div>
  <div class="sub" style="margin-top:6px">{r8.get('note', '')}</div>
</div>

<h2>四、對我們持倉的意涵</h2>
<div class="card">
  <table>
    <tr><th>持倉</th><th>關聯</th><th>說明</th></tr>
    {imp_rows}
  </table>
</div>

<h2>五、風險與誤區</h2>
<div class="card warn"><ul>{risk_li}</ul></div>

<h2>六、來源</h2>
<div class="card"><ul>{src_li}</ul></div>

<div class="foot">產生時間 {TODAY}｜build_national_fund.py｜數字現讀 data/national_fund.json，未在模板寫死<br>
本頁為資訊整理，非投資建議；本次（第 10 次）買進標的須待退場後才由官方揭露。</div>
</body>
</html>
"""
    out = BASE / f"national_fund_{TODAY}.html"
    out.write_text(html, encoding="utf-8", newline="\n")
    print(f"✅ {out.name}（{len(html):,} chars）")
    return out


if __name__ == "__main__":
    build()
