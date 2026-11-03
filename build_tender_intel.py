#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_tender_intel.py — 標案情報頁產生器（2026-11-03 建立）

資料源：data/tender_intel.json（唯一真值）
產物：tender_intel_{YYYY-MM-DD}.html

儀表板接線三處（見 links_config.py 說明）：
  1. index_template.html  <a href="__TENDER_INTEL__">
  2. links_config.PREFIX_RULES       "tender_intel_": (".html", None)
  3. links_config.PLACEHOLDER_PREFIX "__TENDER_INTEL__": "tender_intel_"

設計原則：
  - 純 inline CSS（不依賴 CDN／Tailwind），手機優先
  - 所有數字從 JSON 讀，不在模板寫死金額
  - 缺資料顯示「—」，不以估算補值
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data" / "tender_intel.json"


def wan(v) -> str:
    """元 → 萬元字串；0/None 顯示 —"""
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        return "—"
    if v <= 0:
        return "—"
    return f"{v / 10000:,.0f} 萬"


def pct(award, budget) -> str:
    try:
        b = float(budget or 0)
        a = float(award or 0)
        if b <= 0 or a <= 0:
            return "—"
        return f"{a / b * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def ratio_color(p: str) -> str:
    """折數越低＝對手越殺，用顏色標示"""
    try:
        v = float(p.rstrip("%"))
    except (ValueError, AttributeError):
        return "#64748b"
    if v >= 96:
        return "#f87171"   # 貼預算：我方有空間
    if v >= 88:
        return "#fbbf24"   # 中間
    return "#34d399"       # 已在殺價


def esc(s) -> str:
    return (str(s or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def winner_class(w: str) -> str:
    if "我方" in w or "上境" in w:
        return "win-us"
    if "益洲" in w:
        return "win-yi"
    if "承晏" in w:
        return "win-cheng"
    return "win-lx"


def row(c: dict) -> str:
    p = pct(c.get("award"), c.get("budget"))
    return f"""      <tr>
        <td class="c-year">{esc(c.get('year'))}</td>
        <td class="c-org">{esc(c.get('org'))}</td>
        <td class="c-num">{wan(c.get('budget'))}</td>
        <td class="c-num strong">{wan(c.get('award'))}</td>
        <td class="c-num" style="color:{ratio_color(p)};font-weight:700">{p}</td>
        <td class="c-win {winner_class(str(c.get('winner')))}">{esc(c.get('winner'))}</td>
        <td class="c-date">{esc(c.get('date'))}</td>
      </tr>"""


def kind_block(kind: str, cases: list[dict], subtitle: str) -> str:
    rows = [c for c in cases if c.get("kind") == kind]
    if not rows:
        return ""
    rows.sort(key=lambda c: str(c.get("date", "")))
    body = "\n".join(row(c) for c in rows)
    return f"""
  <section class="card">
    <h2>{esc(kind)} <span class="sub">{esc(subtitle)}</span></h2>
    <div class="tw">
      <table>
        <thead>
          <tr><th>年度</th><th>機關</th><th>預算</th><th>決標</th><th>折數</th><th>得標</th><th>決標月</th></tr>
        </thead>
        <tbody>
{body}
        </tbody>
      </table>
    </div>
  </section>"""


def rival_card(r: dict) -> str:
    lines = []
    if r.get("tax_id"):
        lines.append(f'<div class="kv"><span>統編</span><b>{esc(r.get("tax_id"))}</b></div>')
    if r.get("rep"):
        lines.append(f'<div class="kv"><span>負責人</span><b>{esc(r.get("rep"))}</b></div>')
    if r.get("capital"):
        lines.append(f'<div class="kv"><span>資本額</span><b>{esc(r.get("capital"))}</b></div>')
    if r.get("base"):
        lines.append(f'<div class="kv"><span>所在地</span><b>{esc(r.get("base"))}</b></div>')
    if r.get("bids"):
        lines.append(f'<div class="kv"><span>投標／得標</span><b>{r["bids"]}／{r["wins"]}（{r.get("win_rate")}%）</b></div>')
    if r.get("award_total"):
        lines.append(f'<div class="kv"><span>得標總額</span><b>{wan(r.get("award_total"))}</b></div>')
    if r.get("main_org"):
        lines.append(f'<div class="kv"><span>主場</span><b>{esc(r.get("main_org"))}</b></div>')
    if r.get("style"):
        lines.append(f'<div class="kv"><span>手法</span><b>{esc(r.get("style"))}</b></div>')
    if r.get("record"):
        lines.append(f'<div class="kv"><span>實績</span><b>{esc(r.get("record"))}</b></div>')
    extra = r.get("weakness") or r.get("threat") or ""
    extra_html = f'<p class="note">{esc(extra)}</p>' if extra else ""
    return f"""
    <div class="rival">
      <div class="rival-h">{esc(r.get('name'))}</div>
      {''.join(lines)}
      {extra_html}
    </div>"""


def window_card(w: dict) -> str:
    return f"""
    <div class="win">
      <div class="win-when">{esc(w.get('when'))}</div>
      <div class="win-name">{esc(w.get('name'))}</div>
      <div class="kv"><span>機關</span><b>{esc(w.get('org'))}</b></div>
      <div class="kv"><span>預算</span><b>{wan(w.get('budget'))}</b></div>
      <div class="kv"><span>押標金</span><b>{esc(w.get('deposit') and wan(w.get('deposit')) or '—')}</b></div>
      <div class="kv"><span>履約期</span><b>{esc(w.get('term'))}</b></div>
      <div class="kv"><span>現況</span><b>{esc(w.get('status'))}</b></div>
      <p class="note">{esc(w.get('note'))}</p>
    </div>"""


def build() -> Path:
    d = json.loads(DATA.read_text(encoding="utf-8"))
    today = date.today()
    cases = d.get("cases", [])
    us = d.get("entities", {}).get("us", {})
    rivals = d.get("entities", {}).get("rivals", [])
    windows = d.get("windows", [])
    pricing = d.get("pricing", {})

    lx = next((r for r in rivals if "亮軒" in r.get("name", "")), {})
    our_cases = [c for c in cases if "我方" in str(c.get("winner"))]

    summary = f"""
  <section class="grid">
    <div class="kpi">
      <div class="kpi-t">我方在手</div>
      <div class="kpi-v">{len(our_cases)} 件</div>
      <div class="kpi-s">{esc(us.get('name'))}</div>
    </div>
    <div class="kpi">
      <div class="kpi-t">主要對手</div>
      <div class="kpi-v">{esc(lx.get('name') or '—')}</div>
      <div class="kpi-s">投 {lx.get('bids', '—')} 中 {lx.get('wins', '—')}｜得標率 {lx.get('win_rate', '—')}%</div>
    </div>
    <div class="kpi">
      <div class="kpi-t">對手習慣</div>
      <div class="kpi-v">{lx.get('bid_to_budget', '—')}%</div>
      <div class="kpi-s">決標價占預算（貼預算、不殺價）</div>
    </div>
    <div class="kpi">
      <div class="kpi-t">下一個窗口</div>
      <div class="kpi-v">{esc(windows[0].get('when', '—') if windows else '—')}</div>
      <div class="kpi-s">{esc(windows[0].get('name', '') if windows else '')}</div>
    </div>
  </section>"""

    pricing_html = "".join(f'<li>{esc(a)}</li>' for a in pricing.get("advice", []))

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>標案情報｜台電工地督導查證</title>
<style>
  :root {{
    --bg:#0b1220; --card:#111c2e; --line:#1e293b; --txt:#e2e8f0; --dim:#94a3b8;
    --us:#38bdf8; --lx:#f87171; --yi:#fbbf24; --cheng:#a78bfa;
  }}
  * {{ box-sizing:border-box; -webkit-text-size-adjust:100%; }}
  body {{ margin:0; padding:16px 14px 40px; background:var(--bg); color:var(--txt);
         font-family:-apple-system,BlinkMacSystemFont,"PingFang TC","Microsoft JhengHei",sans-serif;
         line-height:1.6; }}
  h1 {{ font-size:19px; margin:0 0 4px; }}
  .meta {{ color:var(--dim); font-size:11px; margin-bottom:14px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:14px;
           padding:14px; margin:14px 0; }}
  .card h2 {{ font-size:15px; margin:0 0 10px; color:var(--us); }}
  .card h2 .sub {{ font-size:11px; color:var(--dim); font-weight:400; display:block; margin-top:2px; }}
  .grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:10px; margin:12px 0; }}
  @media (min-width:640px) {{ .grid {{ grid-template-columns:repeat(4,1fr); }} }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:10px 12px; }}
  .kpi-t {{ font-size:11px; color:var(--dim); }}
  .kpi-v {{ font-size:16px; font-weight:700; margin:2px 0; word-break:break-all; }}
  .kpi-s {{ font-size:10px; color:var(--dim); line-height:1.4; }}
  .tw {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; min-width:560px; }}
  th, td {{ padding:7px 6px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }}
  th {{ color:var(--dim); font-weight:600; font-size:11px; position:sticky; top:0; background:var(--card); }}
  .c-num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .c-num.strong {{ font-weight:700; }}
  .c-win {{ font-weight:700; }}
  .win-us {{ color:var(--us); }}
  .win-lx {{ color:var(--lx); }}
  .win-yi {{ color:var(--yi); }}
  .win-cheng {{ color:var(--cheng); }}
  .c-date, .c-year, .c-org {{ color:var(--dim); font-size:11px; }}
  .rival {{ border:1px solid var(--line); border-radius:12px; padding:12px; margin-bottom:10px; }}
  .rival-h {{ font-weight:700; font-size:14px; margin-bottom:8px; color:var(--txt); }}
  .kv {{ display:flex; justify-content:space-between; gap:10px; font-size:12px; padding:3px 0;
         border-bottom:1px dashed rgba(148,163,184,.15); }}
  .kv span {{ color:var(--dim); flex:0 0 auto; }}
  .kv b {{ text-align:right; font-weight:600; }}
  .note {{ font-size:11px; color:var(--dim); margin:8px 0 0; }}
  .win {{ border:1px solid var(--line); border-left:3px solid var(--us); border-radius:10px;
          padding:12px; margin-bottom:10px; }}
  .win-when {{ font-size:11px; color:var(--us); font-weight:700; }}
  .win-name {{ font-size:13px; font-weight:700; margin:2px 0 8px; }}
  ul {{ margin:8px 0 0; padding-left:18px; font-size:12px; }}
  li {{ margin-bottom:6px; }}
  .banner {{ background:linear-gradient(135deg,rgba(56,189,248,.12),rgba(168,85,247,.10));
             border:1px solid rgba(56,189,248,.3); border-radius:12px; padding:12px; font-size:12px; }}
  .banner b {{ color:var(--us); }}
  footer {{ color:var(--dim); font-size:10px; margin-top:18px; line-height:1.6; }}
  .tag {{ display:inline-block; font-size:10px; padding:1px 7px; border-radius:999px;
          background:rgba(56,189,248,.15); color:var(--us); margin-left:6px; vertical-align:middle; }}
</style>
</head>
<body>
  <h1>🎯 標案情報｜台電工地督導查證</h1>
  <div class="meta">資料截止 {esc(d.get('as_of'))}｜{esc(d.get('scope'))}</div>

{summary}

  <div class="banner">
    <b>一句話：</b>{esc(pricing.get('headline'))}<br>
    {esc(pricing.get('trend'))}
  </div>

{kind_block('安衛', cases, '中部施工處｜每年 10–12 月招標｜亮軒連 6 年')}
{kind_block('環保', cases, '中部施工處｜每年 4–5 月招標｜台中／通霄兩工區分開標')}
{kind_block('勞務', cases, '金額最大的戰場｜每年 11–12 月招標')}

  <section class="card">
    <h2>🥊 對手畫像</h2>
{''.join(rival_card(r) for r in rivals)}
  </section>

  <section class="card">
    <h2>📅 出手窗口</h2>
{''.join(window_card(w) for w in windows)}
  </section>

  <section class="card">
    <h2>💰 報價基準<span class="tag">依歷史折數推算</span></h2>
    <ul>{pricing_html}</ul>
  </section>

  <footer>
    資料來源：政府電子採購網決標公告、開放政府標案、ToBid 廠商分析。<br>
    金額單位：新台幣元（表格以萬元顯示）。折數＝決標金額 ÷ 預算金額。<br>
    本頁由 build_tender_intel.py 依 data/tender_intel.json 產生，數字勿手改。
  </footer>
</body>
</html>"""

    out = BASE / f"tender_intel_{today.isoformat()}.html"
    out.write_text(html, encoding="utf-8")
    print(f"OK {out.name}  bytes={len(html)}  cases={len(cases)}  rivals={len(rivals)}  windows={len(windows)}")
    return out


if __name__ == "__main__":
    try:
        build()
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: {e}", file=sys.stderr)
        raise
