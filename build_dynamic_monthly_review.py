#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_dynamic_monthly_review.py — 動態自我檢討月報產生器（逐月可重跑）

為什麼有這支
------------
2026-07／08／09 的 dynamic_monthly_review_*.html 是手寫/一次性產出，
10 月缺檔且無法重跑。本檔把它腳本化：所有數字從 asset_diff_history.json
與 snapshot.json 動態計算，情境參數從 data/scenario_b_<month>.json 讀，
不寫死任何金額（no-hardcode）。

用法
----
  python build_dynamic_monthly_review.py --month 2026-10
  python build_dynamic_monthly_review.py --month 2026-10 --print   # 只印摘要

輸出
----
  dynamic_monthly_review_<month>.html
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
HIST = BASE / "asset_diff_history.json"
SNAP = BASE / "snapshot.json"


def n(v, d=0.0):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return d


def money(v, dash="—"):
    return f"{v:,.0f}" if v is not None else dash


def signed(v):
    if v is None:
        return "—"
    return f"{v:+,.0f}"


def pct(v, d=1):
    return f"{v:,.{d}f}%" if v is not None else "—"


def load_month(month):
    h = json.loads(HIST.read_text(encoding="utf-8"))
    days = sorted(d for d in h if re.match(r"\d{4}-\d{2}-\d{2}", d) and d.startswith(month))
    if not days:
        raise SystemExit(f"❌ asset_diff_history 沒有 {month} 的資料")
    return h[days[0]], h[days[-1]], days[0], days[-1]


def cashflow(snap, month):
    div = (snap.get("dividend_records") or {}).get(month) or {}
    div_total = sum(v for v in div.values() if isinstance(v, (int, float)))
    rent = sum(sum(x.values()) for d, x in (snap.get("rent_received_records") or {}).items()
               if str(d).startswith(month) and isinstance(x, dict))
    sal = n(((snap.get("salary_records") or {}).get(month) or {}).get("amount"))
    exp = n((snap.get("monthly_fixed_expense") or {}).get("合計")) or n(snap.get("monthly_expense"))
    return {"dividend": div_total, "dividend_items": div, "rent": rent, "salary": sal,
            "expense": exp, "income": div_total + rent + sal,
            "passive": div_total + rent, "net_cash": div_total + rent + sal - exp,
            "cover_pct": (div_total + rent) / exp * 100 if exp else None}


def trades_in_month(snap, month):
    """掃 snapshot 內 securities_trade_note_YYYYMMDD，取當月交易（人為操作）。"""
    out = []
    for k, v in (snap or {}).items():
        m = re.match(r".*trade_note[_-](\d{8})$", str(k))
        if not m:
            continue
        d = m.group(1)
        if f"{d[:4]}-{d[4:6]}" != month:
            continue
        txt = str(v)
        amt = re.search(r"成交\s*([\d,]+)", txt) or re.search(r"([\d,]{5,})\s*元", txt)
        out.append({"date": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                    "text": txt,
                    "amount": n(amt.group(1)) if amt else None})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--print", action="store_true")
    a = ap.parse_args(argv)

    month = a.month
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    f, l, d0, d1 = load_month(month)
    cf = cashflow(snap, month)

    scen_path = BASE / "data" / f"scenario_b_{month}.json"
    scen = json.loads(scen_path.read_text(encoding="utf-8")) if scen_path.exists() else None

    keys = [("cash", "現金"), ("securities_market", "證券市值"), ("insurance_total", "保單現值"),
            ("fund_market", "基金市值"), ("total_assets", "流動資產合計"), ("total_liabilities", "總負債")]
    rows = []
    for k, label in keys:
        a0, a1 = n(f.get(k)), n(l.get(k))
        rows.append((label, a0, a1, a1 - a0))
    net0 = n(f.get("total_assets")) - n(f.get("total_liabilities"))
    net1 = n(l.get("total_assets")) - n(l.get("total_liabilities"))
    rows.append(("淨資產（流動−負債）", net0, net1, net1 - net0))

    pen = (snap.get("penetration") or {}).get("actual_pct") or {}
    targets = (snap.get("penetration") or {}).get("targets") or {}
    gate = snap.get("us30y_gate") or {}
    layers = snap.get("cash_layers") or {}

    trades = trades_in_month(snap, month)
    buy_amt = sum(t["amount"] or 0 for t in trades)
    sec_chg = n(l.get("securities_market")) - n(f.get("securities_market"))
    sec_wave = sec_chg - buy_amt
    cash_chg = n(l.get("cash")) - n(f.get("cash"))
    cf_gap = cash_chg - cf["net_cash"]

    summary = (f"{month[5:]} 月金融資產 {money(n(l.get('total_assets')))}（月變 {signed(n(l.get('total_assets')) - n(f.get('total_assets')))}）、"
               f"淨資產 {money(net1)}（月變 {signed(net1 - net0)}）；被動收入 {money(cf['passive'])}、"
               f"覆蓋 {pct(cf['cover_pct'])}；現金 {money(layers.get('cash_total'))}"
               f"（可動用 {money(layers.get('unrestricted_cash'))}＋指定款 {money((layers.get('restricted_cash') or {}).get('total'))}）。"
               + f" 證券 {'回檔' if sec_wave < 0 else '上漲'} {money(abs(sec_wave))}"
               + (f"（另含買進 {money(buy_amt)}，人為）" if buy_amt else "（本月無買賣）")
               + f"；現金流淨 {signed(cf['net_cash'])}，現金實際變動 {signed(cash_chg)}"
               + (f"（差 {signed(cf_gap)} 屬時序/未對帳項）" if abs(cf_gap) > 1000 else "")
               + "。本月賺的是現金流" + ("，價差是負的。" if sec_wave < 0 else "，價差也是正的。"))

    if a.print:
        print(summary)
        for r in rows:
            print(f"  {r[0]:<12}{r[1]:>14,.0f}{r[2]:>14,.0f}{r[3]:>+14,.0f}")
        print("  現金流:", {k: (round(v) if isinstance(v, float) else v) for k, v in cf.items() if k != "dividend_items"})
        print("  情境 B:", "已載入" if scen else "缺檔")
        return 0

    # ── 渲染 ────────────────────────────────────────────────
    def rule_block():
        if not scen:
            return '<div class="warn">⚠️ 未載入情境參數（data/scenario_b_%s.json），本段留空。</div>' % month
        r = scen["rules"]
        items = []
        for k, label in (("cash_hold", "現金處理"), ("defense_no_topup", "防守配置"),
                         ("caliber_freeze", "口徑"), ("monthly_channel", "每月導流"),
                         ("cash_target", "現金目標"), ("bond_ladder_gate", "債券 ladder 啟動條件")):
            v = r.get(k) or {}
            items.append(f'<li><b>{label}</b>：{v.get("statement","—")}</li>')
        return ('<ul class="rules">' + "".join(items) + "</ul>"
                f'<div class="src">情境 {scen.get("scenario")}｜定調：{scen.get("asserted_by")}（{scen.get("asserted_at")}）'
                f'｜參數檔 data/scenario_b_{month}.json</div>')

    row_html = "".join(
        f'<tr><td>{r[0]}</td><td class="num">{money(r[1])}</td><td class="num">{money(r[2])}</td>'
        f'<td class="num {"up" if r[3] > 0 else ("down" if r[3] < 0 else "")}">{signed(r[3])}</td></tr>'
        for r in rows
    )

    div_items = sorted(((k, v) for k, v in cf["dividend_items"].items() if isinstance(v, (int, float))),
                       key=lambda x: -x[1])[:6]
    div_html = "".join(f"<li>{k}：<b>{money(v)}</b></li>" for k, v in div_items)

    pen_items = [(k, v) for k, v in pen.items() if not k.endswith(("_科技", "_非科技"))]
    pen_html = "".join(
        f'<div class="pill"><span>{k}</span><b>{pct(v)}</b>'
        f'{f"<i>目標 {targets.get(k)}%</i>" if targets.get(k) is not None else ""}</div>'
        for k, v in pen_items
    )

    html = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>龍九控股 動態自我檢討月報 {month}</title><style>
:root{{--bg:#0b0d1a;--card:#151a2e;--line:#27304d;--txt:#e8ebf2;--dim:#8a8fa0;--gold:#f7a01c;--green:#34d399;--red:#ff5c5c}}
*{{box-sizing:border-box}}
body{{margin:0;padding:18px;background:var(--bg);color:var(--txt);font-family:-apple-system,"Segoe UI","Noto Sans TC",sans-serif;line-height:1.6}}
h1{{font-size:21px;margin:0 0 6px}}
h2{{font-size:16px;margin:0 0 10px;padding-left:8px;border-left:3px solid var(--gold)}}
.sub{{color:var(--dim);font-size:12px;margin-bottom:14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:14px}}
.lead{{background:linear-gradient(135deg,#1b2340,#141a2e);border:1px solid #33406b}}
.lead p{{margin:6px 0 0;font-size:14px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:7px 6px;border-bottom:1px solid var(--line);text-align:left}}
th{{color:var(--dim);font-weight:600;font-size:12px}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.up{{color:var(--green)}} .down{{color:var(--red)}}
ul{{margin:8px 0 0;padding-left:20px}} li{{margin:4px 0;font-size:13px}}
.rules li{{margin:6px 0}}
.pill{{display:inline-flex;gap:8px;align-items:baseline;background:#0f1424;border:1px solid var(--line);border-radius:999px;padding:5px 12px;margin:0 6px 6px 0;font-size:12px}}
.pill i{{color:var(--dim);font-style:normal;font-size:11px}}
.src,.dim{{color:var(--dim);font-size:11px}}
.warn{{background:#2a1f12;border:1px solid #6b5a1f;color:#f5c26b;padding:10px;border-radius:8px;font-size:12px}}
.kpi{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:8px}}
.kpi div{{background:#0f1424;border-radius:8px;padding:8px}}
.kpi span{{display:block;color:var(--dim);font-size:11px}}
.kpi b{{font-size:15px}}
</style></head><body>

<h1>🧠 龍九控股 — 動態自我檢討月報 {month}</h1>
<div class="sub">{d0} ~ {d1}｜月度復盤 ＋ 全域判斷 ＋ 策略迭代｜產出 source: build_dynamic_monthly_review.py</div>

<div class="card lead">
  <h2>📌 一句話總結</h2>
  <p>{summary}</p>
</div>

<div class="card">
  <h2>1. 數據動態回顧（{d0} → {d1}）</h2>
  <table>
    <tr><th>項目</th><th class="num">月初</th><th class="num">月末</th><th class="num">增減</th></tr>
    {row_html}
  </table>
  <div class="src">資料源 asset_diff_history.json（逐日快照）。增減為帳面變動，含人為操作與市值波動，兩者已於下方現金流段分別處理。</div>
</div>

<div class="card">
  <h2>2. 現金流（當月實收）</h2>
  <div class="kpi">
    <div><span>配息實收</span><b>{money(cf["dividend"])}</b></div>
    <div><span>租金實收</span><b>{money(cf["rent"])}</b></div>
    <div><span>薪資</span><b>{money(cf["salary"])}</b></div>
    <div><span>常態支出</span><b>{money(cf["expense"])}</b></div>
    <div><span>被動收入</span><b>{money(cf["passive"])}</b></div>
    <div><span>被動覆蓋</span><b>{pct(cf["cover_pct"])}</b></div>
  </div>
  <p style="font-size:13px;margin:10px 0 0">淨現金流（收入−常態支出）：<b class="up">{signed(cf["net_cash"])}</b></p>
  <ul>{div_html}</ul>
  <div class="src">配息取 snapshot.dividend_records.{month} 逐筆加總；租金取 rent_received_records 當月逐筆；支出用常態月支出（非實際刷卡金額）。</div>
</div>

<div class="card">
  <h2>3. 歸因（人為 vs 波動）</h2>
  <table>
    <tr><th>項目</th><th class="num">金額</th><th>性質</th></tr>
    <tr><td>現金：收入−常態支出</td><td class="num">{signed(cf["net_cash"])}</td><td>現金流（可持續）</td></tr>
    <tr><td>現金：其他增減</td><td class="num">{signed(cf_gap)}</td><td>{("時序／未對帳" if abs(cf_gap) > 1000 else "無")}</td></tr>
    <tr><td>證券：市值波動</td><td class="num">{signed(sec_wave)}</td><td>市場</td></tr>
    <tr><td>證券：買進</td><td class="num">{signed(buy_amt) if buy_amt else "—"}</td><td>人為（{len(trades)} 筆）</td></tr>
    <tr><td>保單現值</td><td class="num">{signed(n(l.get("insurance_total")) - n(f.get("insurance_total")))}</td><td>配息撥回抵市值變動</td></tr>
    <tr><td>基金市值</td><td class="num">{signed(n(l.get("fund_market")) - n(f.get("fund_market")))}</td><td>配息再投入＋淨值</td></tr>
    <tr><td>總負債</td><td class="num">{signed(n(l.get("total_liabilities")) - n(f.get("total_liabilities")))}</td><td>正常攤還</td></tr>
  </table>
  <div class="src">{("本月交易：" + "；".join(f'{t["date"]} {t["text"][:60]}' for t in trades)) if trades else "本月無交易紀錄（securities_trade_note_*）。"}</div>
</div>

<div class="card">
  <h2>4. 穿透與燈號（現行）</h2>
  <div>{pen_html}</div>
  <div class="src">US30Y {gate.get("value","—")}（連續 {gate.get("streak_days","—")} 日）｜美元曝險 {snap.get("usd_exposure_pct","—")}%｜
  現金 {money(layers.get("cash_total"))}＝可動用 {money(layers.get("unrestricted_cash"))}＋指定款 {money((layers.get("restricted_cash") or {}).get("total"))}｜
  乾粉 {money(n(layers.get("dry_powder")))}</div>
</div>

<div class="card">
  <h2>5. 情境 B（凍結期結構調整）</h2>
  {rule_block()}
  <p class="dim" style="margin-top:10px">本段只陳述已定調參數，不推導新的投資授權；任何進場仍需另行授權。</p>
</div>

<div class="card">
  <h2>6. 下月觀察（條件式，不看日曆）</h2>
  <ul>
    <li>現金導流：每月 <b>{money(n(((scen or {}).get("rules",{}).get("monthly_channel") or {}).get("value_twd")))}</b>，補至現金 5% 目標（差額約 {money(n(((scen or {}).get("rules",{}).get("cash_target") or {}).get("gap_twd_approx")))}）。</li>
    <li>債券 ladder：US30Y 連 2 日 &lt; {((scen or {}).get("rules",{}).get("bond_ladder_gate") or {}).get("us30y_below","—")}% 且美元 &lt; {((scen or {}).get("rules",{}).get("bond_ladder_gate") or {}).get("usd_exposure_below_pct","—")}%，首批上限 {money(n(((scen or {}).get("rules",{}).get("bond_ladder_gate") or {}).get("first_batch_cap_twd")))}。</li>
    <li>防守配置：本情境不補；缺口仍在，留待下一輪裁決。</li>
    <li>口徑：凍結期間不重定義分母，跨報告一致性以現行 snapshot 為準。</li>
  </ul>
</div>

<div class="sub" style="margin-top:18px">唯一寫入者 build_dynamic_monthly_review.py｜數字源 snapshot.json ＋ asset_diff_history.json ＋ data/scenario_b_{month}.json</div>
</body></html>"""

    out = BASE / f"dynamic_monthly_review_{month}.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ {out.name}（{len(html.encode('utf-8')):,} bytes）")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
