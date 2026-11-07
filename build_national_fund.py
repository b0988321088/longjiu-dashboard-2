#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_national_fund.py — 國安基金護盤：機制＋買超清單＋「我的持股 × 護盤關聯 × 策略」

資料源（全部現讀，模板不寫死數字）：
  data/national_fund.json            機制、歷次清單、敘事型策略規則（人工維護）
  data/etf_holdings_YYYYMMDD.json    ETF 成分權重（MoneyDJ 持股明細）
  snapshot.json                      證券持股、保單結構、五桶、總資產

輸出：national_fund_YYYY-MM-DD.html（純 inline CSS、手機優先）
"""
from __future__ import annotations

import glob
import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent.resolve()
SRC = BASE / "data" / "national_fund.json"
SNAP = BASE / "snapshot.json"
TODAY = date.today().isoformat()

SEVEN = {
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2308": "台達電",
    "3711": "日月光投控", "2382": "廣達", "2881": "富邦金",
}
LIFE_FLOOR = 700_000
TW_CAP_PCT = 13.0  # 台股市值型帶狀上限


def money(v, unit="億"):
    if v is None:
        return "—"
    if unit == "億":
        return f"{v / 1e8:,.2f} 億"
    return f"{v:,.0f}"


def wan(v):
    return "—" if v is None else f"{v / 1e4:,.1f} 萬"


def load_etf():
    files = sorted(glob.glob(str(BASE / "data" / "etf_holdings_*.json")))
    if not files:
        return {}, None
    d = json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    dt = next((v.get("date") for v in d.values() if isinstance(v, dict) and v.get("date")), None)
    return d, dt


def weights(etf, ticker):
    e = (etf or {}).get(f"{ticker}.TW")
    if not e:
        return None
    return {c: float(w) for _, c, w in e.get("rows") or []}


def build() -> Path:
    d = json.loads(SRC.read_text(encoding="utf-8"))
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    etf, etf_date = load_etf()

    cur = d.get("current") or {}
    mech = d.get("mechanism") or []
    r9 = (d.get("history") or {}).get("round9") or {}
    r8 = (d.get("history") or {}).get("round8") or {}
    holds9 = r9.get("holdings") or []
    risks = d.get("risks") or []
    strat = d.get("strategy") or {}
    pol = d.get("policy") or {}
    link = d.get("linkage") or {}

    total_cost = float(r9.get("invested") or 0) or sum(float(h.get("cost") or 0) for h in holds9)

    # ── 我的持股 × 護盤關聯 ────────────────────────────────
    rows = []
    for h in (snap.get("securities") or {}).get("holdings") or []:
        t = str(h.get("ticker"))
        w = weights(etf, t)
        seven_pct = tsmc_pct = 0.0
        hit = {}
        if w:
            hit = {SEVEN[c]: v for c, v in w.items() if c in SEVEN}
            seven_pct = sum(hit.values())
            tsmc_pct = w.get("2330", 0.0)
        elif t in SEVEN:  # 直接持有個股
            seven_pct = tsmc_pct = 100.0
            hit = {SEVEN[t]: 100.0}
        mv = float(h.get("market_value") or 0)
        rows.append({
            "ticker": t, "name": h.get("name", ""), "mv": mv,
            "pnl_pct": h.get("pnl_pct"), "seven_pct": seven_pct, "tsmc_pct": tsmc_pct,
            "seven_twd": mv * seven_pct / 100, "tsmc_twd": mv * tsmc_pct / 100, "hit": hit,
        })
    rows.sort(key=lambda r: -r["seven_twd"])

    sec_seven = sum(r["seven_twd"] for r in rows)
    sec_tsmc = sum(r["tsmc_twd"] for r in rows)

    # 保單：元大台灣卓越50 追蹤台灣50 → 比照 0050 權重
    p50_w = weights(etf, "0050") or {}
    p50_tsmc = p50_w.get("2330", 0.0)
    p50_seven = sum(v for c, v in p50_w.items() if c in SEVEN)
    ib = snap.get("insurance_breakdown") or {}
    pol_funds = []
    for key, name in (("policy_a_funds", "安聯A"), ("policy_b_funds", "安聯B")):
        for fname, val in (ib.get(key) or {}).items():
            link_pct = 0.0
            if "卓越50" in fname:
                link_pct = p50_seven
            _abbr, _sep, _disp = fname.partition(" ")
            pol_funds.append({"policy": name, "fund": _disp or fname, "abbr": _abbr if _sep else "",
                              "full": fname, "val": float(val), "link_pct": link_pct,
                              "tsmc_pct": (p50_tsmc if "卓越50" in fname else 0.0),
                              "link_twd": float(val) * link_pct / 100,
                              "tsmc_twd": float(val) * (p50_tsmc if "卓越50" in fname else 0.0) / 100})
    for fname, val in ((ib.get("firstjin_total") and {"M&G入息A（第一金 100%）": ib["firstjin_total"]}) or {}).items():
        pol_funds.append({"policy": "第一金", "fund": fname, "abbr": "", "full": fname, "val": float(val),
                          "link_pct": 0.0, "tsmc_pct": 0.0, "link_twd": 0.0, "tsmc_twd": 0.0})
    pol_funds.sort(key=lambda x: -x["link_twd"])
    pol_total = sum(p["val"] for p in pol_funds)
    pol_seven = sum(p["link_twd"] for p in pol_funds)
    pol_tsmc = sum(p["tsmc_twd"] for p in pol_funds)

    ta = float(snap.get("total_assets") or 0)
    pen = snap.get("penetration") or {}
    tw_twd = float((pen.get("actual_twd") or {}).get("台股市值型成長") or 0)
    cash = float((pen.get("actual_twd") or {}).get("現金/安全網") or 0)
    ob = snap.get("opportunity_bullet_20261107") or {}
    order = ob.get("執行紀錄_20261109") or {}
    ordered = float((ob.get("資金現況_20261107") or {}).get("已承諾_未成交") or 0)
    ammo_left = max(0.0, cash - ordered - LIFE_FLOOR)
    tw_room = max(0.0, ta * TW_CAP_PCT / 100 - tw_twd - ordered)
    tsmc_all = sec_tsmc + pol_tsmc

    # ── 建議文字（規則化，避免模板罐頭）────────────────────
    def advice(r):
        p = r["pnl_pct"]
        if r["seven_pct"] >= 40:
            if p is not None and p > 0:
                return "高關聯｜續抱不加（曝險已足，再加只提高集中度）"
            return "高關聯但虧損｜不攤平，等回本再說"
        if r["seven_pct"] >= 20:
            if p is not None and p <= -10:
                return "中關聯但虧損｜不加（攤平禁令）"
            return "中關聯｜可列第二批加碼人選（不推高科技）"
        if r["seven_pct"] > 0:
            return "低關聯｜維持，不作護盤工具"
        return "無關聯｜維持（非護盤題材）"

    hold_rows = []
    for r in rows:
        pnl = "—" if r["pnl_pct"] is None else f"{r['pnl_pct']:+.1f}%"
        hold_rows.append(
            "<tr>"
            f"<td><b>{r['ticker']}</b><div class='sub'>{r['name']}</div></td>"
            f"<td class='n'>{wan(r['mv'])}</td>"
            f"<td class='n'>{pnl}</td>"
            f"<td class='n'>{r['seven_pct']:.1f}%</td>"
            f"<td class='n'>{wan(r['seven_twd'])}</td>"
            f"<td class='n'>{r['tsmc_pct']:.1f}%</td>"
            f"<td>{advice(r)}</td>"
            "</tr>"
        )

    pol_rows = []
    for p in pol_funds:
        note = ("七雄 %.1f%%（台積電 %.1f%%）" % (p["link_pct"], p["tsmc_pct"])) if p["link_pct"] >= 10 else "無直接關聯"
        pol_rows.append(
            "<tr>"
            f"<td><b>{p['policy']}</b></td>"
            f"<td>{p['fund']}<div class='sub'>{p['abbr']}</div></td>"
            f"<td class='n'>{wan(p['val'])}</td>"
            f"<td>{note}</td>"
            f"<td class='n'>{wan(p['link_twd']) if p['link_twd'] else '—'}</td>"
            "</tr>"
        )

    hold_rows9 = []
    for h in holds9:
        share = (float(h.get("cost") or 0) / total_cost * 100) if total_cost else 0
        hold_rows9.append(
            "<tr>"
            f"<td><b>{h.get('ticker', '')}</b><div class='sub'>{h.get('name', '')}</div></td>"
            f"<td class='n'>{money(h.get('cost'))}</td>"
            f"<td class='n'>{share:.1f}%</td>"
            f"<td class='n'>{money(h.get('profit'))}</td>"
            f"<td>{h.get('note', '')}</td>"
            "</tr>"
        )

    tok = {
        "{SEC_TSMC}": wan(sec_tsmc), "{POL_TSMC}": wan(pol_tsmc),
        "{TSMC_TOTAL}": wan(tsmc_all), "{AMMO}": wan(ammo_left),
        "{TSMC_PCT_TA}": f"{tsmc_all / ta * 100:.1f}%",
    }

    def fill(s):
        for k, v in tok.items():
            s = s.replace(k, v)
        return s

    plan = ob.get("分批計畫_v2_20261107") or {}
    plan_rows = []
    for b in plan.get("批次") or []:
        plan_rows.append(
            "<tr>"
            f"<td><b>{b.get('批次','')}</b></td>"
            f"<td><b>{b.get('ticker','')}</b> {b.get('名稱','')}<div class='sub'>{b.get('股數',0):,} 股 @ {b.get('參考價',0):.2f}</div></td>"
            f"<td class='n'>{b.get('估計合計',0):,.0f}</td>"
            f"<td>{b.get('觸發','')}<div class='sub'>{b.get('理由','')}</div></td>"
            "</tr>"
        )
    plan_ban = "".join(f"<li>{x}</li>" for x in plan.get("不進場條件") or [])
    _post = float((plan.get("前提") or {}).get("已下單後台股桶") or 0) + sum(
        float(b.get("估計金額") or 0) for b in plan.get("批次") or [])
    tier_rows = "".join(
        f"<tr><td><b>{t.get('tier', '')}</b></td><td>{fill(t.get('your', ''))}</td><td>{fill(t.get('conclusion', ''))}</td></tr>"
        for t in strat.get("tiers") or []
    )
    mech_li = "".join(f"<li>{m}</li>" for m in mech)
    risk_li = "".join(f"<li>{r}</li>" for r in risks)
    deploy_li = "".join(f"<li>{x}</li>" for x in strat.get("deploy_rules") or [])
    ban_li = "".join(f"<li>{x}</li>" for x in strat.get("ban") or [])
    watch_li = "".join(f"<li>{x}</li>" for x in strat.get("watch") or [])
    future_li = "".join(f"<li>{x}</li>" for x in pol.get("future_order") or [])
    src_li = "".join(
        f"<li>{s.get('label', '')}<div class='sub'>{s.get('note', '')}</div></li>"
        for s in (d.get("sources") or [])
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>國安基金護盤 × 我的持股策略 {TODAY}</title>
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;padding:14px;background:#0b1220;color:#e2e8f0;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang TC","Microsoft JhengHei",sans-serif;
 font-size:14px;line-height:1.65;-webkit-text-size-adjust:100%}}
h1{{font-size:18px;margin:2px 0 4px}}
h2{{font-size:15px;margin:22px 0 8px;padding-left:9px;border-left:4px solid #38bdf8}}
.card{{background:#131c2e;border:1px solid #1f2b42;border-radius:12px;padding:12px 13px;margin:10px 0}}
.hero{{background:linear-gradient(135deg,#0f2d4a,#132a3f);border:1px solid #1d4e73}}
.tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;
 background:#1e3a5f;color:#93c5fd;border:1px solid #2b4c74;margin-right:6px}}
.sub{{font-size:11.5px;color:#93a3bb}}
ul{{margin:6px 0 0;padding-left:18px}}
li{{margin:4px 0}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}}
th,td{{padding:7px 5px;border-bottom:1px solid #1f2b42;vertical-align:top;text-align:left}}
th{{color:#93a3bb;font-weight:600;font-size:11px;background:#0f1a2b}}
.n{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}
.kv{{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px dashed #1f2b42}}
.kv:last-child{{border-bottom:0}}
.kv b{{color:#fff;font-weight:700}}
.warn{{background:#2a1710;border:1px solid #7c2d12;color:#fed7aa}}
.ok{{background:#0f2418;border:1px solid #14532d;color:#bbf7d0}}
.big{{font-size:22px;font-weight:800;color:#fff;font-variant-numeric:tabular-nums}}
.foot{{margin:18px 0 6px;font-size:11px;color:#64748b}}
</style>
</head>
<body>
<h1>🏦 國安基金 × 我的持股策略</h1>
<div class="sub">更新 {d.get('updated_at', TODAY)}｜成分權重 {etf_date or '—'}（MoneyDJ）｜持股 snapshot 現讀</div>

<div class="card hero">
  <div class="sub" style="margin-bottom:6px">{cur.get('round','')}｜{cur.get('decision_date','')}｜{cur.get('budget','')}</div>
  <div style="font-size:13.5px;color:#e2e8f0">{fill(strat.get('headline',''))}</div>
  <div class="kv" style="margin-top:8px"><span>我的台積電曝險（證券＋保單）</span><b>{wan(tsmc_all)}</b></div>
  <div class="kv"><span>護盤七雄曝險（證券）</span><b>{wan(sec_seven)}</b></div>
  <div class="kv"><span>總彈藥（現金 {wan(cash)} − 生活底線 {wan(LIFE_FLOOR)}）</span><b>{wan(cash - LIFE_FLOOR)}</b></div>
  <div class="kv"><span>已承諾（已下單未成交）</span><b>{wan(ordered)}</b></div>
  <div class="kv"><span>未承諾彈藥（可再規劃）</span><b>{wan(ammo_left)}</b></div>
  <div class="kv"><span>台股桶還有空間（至 {TW_CAP_PCT:.0f}%）</span><b>{wan(tw_room)}</b></div>
</div>

<h2>一、機制重點（為什麼是那些股票）</h2>
<div class="card"><ul>{mech_li}</ul></div>

<h2>二、我的持股 × 護盤關聯</h2>
<div class="card">
  <div class="sub">護盤關聯＝該檔前十大成分中護盤七雄（台積電／鴻海／聯發科／台達電／日月光／廣達／富邦金）權重合計；未進前十大不計＝偏低估計</div>
  <table>
    <tr><th>標的</th><th class="n">市值</th><th class="n">損益</th><th class="n">七雄%</th><th class="n">七雄曝險</th><th class="n">台積%</th><th>判讀</th></tr>
    {''.join(hold_rows)}
  </table>
  <div class="kv" style="margin-top:8px"><span>證券部位七雄曝險合計</span><b>{wan(sec_seven)}（占證券 {sec_seven / (sum(r['mv'] for r in rows) or 1) * 100:.1f}%）</b></div>
  <div class="kv"><span>其中台積電曝險</span><b>{wan(sec_tsmc)}</b></div>
  <div class="sub" style="margin-top:6px">{link.get('caveat','')}</div>
</div>

<h2>三、保單部位：{pol.get('stance','')}</h2>
<div class="card ok">
  <div class="kv"><span>保單部位合計</span><b>{wan(pol_total)}</b></div>
  <div class="kv"><span>其中護盤七雄曝險</span><b>{wan(pol_seven)}</b></div>
  <div class="kv"><span>其中台積電曝險</span><b>{wan(pol_tsmc)}</b></div>
  <div class="sub" style="margin-top:6px">{pol.get('why','')}</div>
  <table>
    <tr><th>保單</th><th>基金</th><th class="n">市值</th><th>護盤關聯</th><th class="n">曝險</th></tr>
    {''.join(pol_rows)}
  </table>
  <div class="sub" style="margin-top:8px"><b>未來若啟動調整（現在不動）：</b></div>
  <ul>{future_li}</ul>
</div>

<h2>四、策略結論</h2>
<div class="card">
  <table>
    <tr><th>層級</th><th>我的曝險</th><th>結論</th></tr>
    {tier_rows}
  </table>
</div>
<div class="card">
  <div class="sub"><b>未承諾彈藥 {wan(ammo_left)} 的使用順序</b></div>
  <ul>{deploy_li}</ul>
</div>
<div class="card warn">
  <div class="sub"><b>不要做的事</b></div>
  <ul>{ban_li}</ul>
</div>
<div class="card">
  <div class="sub"><b>觀察指標（決定第二批何時動）</b></div>
  <ul>{watch_li}</ul>
</div>

<h2>五、乾粉進場計畫（{plan.get('版本','')}）</h2>
<div class="card">
  <div class="kv"><span>未承諾彈藥（總彈藥 {wan(cash - LIFE_FLOOR)} − 已承諾 {wan(ordered)}）</span><b>{wan(ammo_left)}</b></div>
  <div class="kv"><span>本計畫合計</span><b>{wan(plan.get('計畫合計') or 0)}</b></div>
  <div class="kv"><span>執行後現金</span><b>{wan(plan.get('執行後現金') or 0)}（距底線剩 {wan(plan.get('執行後緩衝') or 0)}）</b></div>
  <div class="kv"><span>全數執行後台股桶</span><b>{_post / ta * 100:.2f}%（上限 {TW_CAP_PCT:.0f}%）</b></div>
  <table>
    <tr><th>批次</th><th>標的</th><th class="n">估金額</th><th>觸發條件／理由</th></tr>
    {''.join(plan_rows)}
  </table>
  <div class="sub" style="margin-top:8px"><b>不進場條件</b></div>
  <ul>{plan_ban}</ul>
  <div class="sub" style="margin-top:6px">{plan.get('停止條件','')}</div>
</div>
<div class="card ok">
  <div class="sub"><b>資金約束（為什麼不能一次打光）</b></div>
  <ul>
    <li><b>硬約束</b>：{plan.get('約束',{}).get('硬','')}</li>
    <li><b>軟約束</b>：{plan.get('約束',{}).get('軟','')}</li>
    <li><b>季節性</b>：{plan.get('約束',{}).get('季節','')}</li>
  </ul>
</div>

<h2>六、第 9 次實際買進（護盤慣性依據）</h2>
<div class="card">
  <div class="sub">{r9.get('label','')}｜{r9.get('period','')}</div>
  <div class="kv"><span>投入金額</span><b>{money(r9.get('invested'))}</b></div>
  <div class="kv"><span>處分淨利＋股利</span><b>{money(r9.get('net_profit'))}</b></div>
  <div class="kv"><span>報酬率</span><b>{pct(r9.get('return_pct'))}</b></div>
  <table>
    <tr><th>標的</th><th class="n">投入成本</th><th class="n">占比</th><th class="n">處分獲利</th><th>定位</th></tr>
    {''.join(hold_rows9)}
  </table>
  <div class="sub" style="margin-top:8px">中小型股、櫃買（OTC）買超為 0；8 檔全數獲利出場。第 8 次為 {r8.get('count','—')} 檔：{r8.get('note','')}</div>
</div>

<h2>七、風險與誤區</h2>
<div class="card warn"><ul>{risk_li}</ul></div>

<h2>八、來源</h2>
<div class="card"><ul>{src_li}</ul></div>

<div class="foot">產生時間 {TODAY}｜build_national_fund.py｜持股與保單現讀 snapshot.json、成分權重現讀 data/etf_holdings_*.json<br>
本頁為資訊整理與紀律提醒，非投資建議；本次（第 10 次）買進標的須待退場後才由官方揭露。</div>
</body>
</html>
"""
    out = BASE / f"national_fund_{TODAY}.html"
    out.write_text(html, encoding="utf-8", newline="\n")
    print(f"✅ {out.name}（{len(html):,} chars）｜台積電總曝險 {wan(tsmc_all)}｜未承諾彈藥 {wan(ammo_left)}")
    return out


def pct(v):
    return "—" if v is None else f"{v:.0f}%"


if __name__ == "__main__":
    build()
