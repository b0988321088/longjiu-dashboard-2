#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_mtd_report.py — 本月績效頁（mtd_performance.html）＋ 即時資料（mtd_data.json）

口徑**完全重用**月報（build_investment_performance.py）：本檔 import 它，直接呼叫
load_adjust / db_asset_on / load_loans / classify_dividend，不另寫第二套算法。

四段式拆解（每類資產同一套）：
    帳面市值變化（dragon_assets.db：上月底最後一筆 → 最新一筆）
  − 新增投入（只算實際交割）
  − 估值更新（investment_performance_adjust.json[月份].估值更新，明列日期/as-of/原因）
  ＋ 配息實收（snapshot.dividend_records[月份]，與月報同一個 auto 分類）
  ＝ 市場面損益（含匯率）

⚠️ 保單那條序列是「一次一次截圖之間的差額」，同時含真實市場漲跌與前次估值誤差，
   現有資料無法完全分離 —— 所以本頁把「估值更新」明列成時間軸，不假裝能拆乾淨。

輸出：mtd_performance.html（固定檔名）＋ mtd_data.json
用法：python build_mtd_report.py [--quiet]
"""
import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import build_investment_performance as bip  # noqa: E402

CLASS_KEYS = ["股票", "基金", "保單"]
OUT_HTML = BASE / "mtd_performance.html"
OUT_JSON = BASE / "mtd_data.json"
# 資金成本燈號門檻（與 build_investment_performance.funding_cost_report 同值；改一處要同步）
SPREAD_GREEN = 0.012


def _num(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def _freshness(snap: dict, mk: str, end_date: str) -> list[dict]:
    """各源 as-of（給讀者判斷數字新鮮度；保單抓 snapshot 註記裡的日期）。"""
    out = [{"src": "資產序列（dragon_assets.db）", "date": end_date}]
    if snap.get("date"):
        out.append({"src": "snapshot 真值日", "date": str(snap.get("date"))})
    note = str(snap.get("note") or "")
    ins = snap.get("insurance_breakdown") or {}
    note = (str(ins.get("note") or "") + " " + note).strip()   # 保單 as-of 記在 insurance_breakdown.note
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", note)
    if dates:
        out.append({"src": "保單（安聯 App 截圖）", "date": max(dates)})
    m = re.findall(r"(\d{1,2})/(\d{1,2})\s*App", note)
    if m:
        mm, dd = m[-1]
        out.append({"src": "保單（第一金 App 截圖）", "date": f"{mk[:4]}-{int(mm):02d}-{int(dd):02d}"})
    return out


def payload() -> dict:
    today = dt.date.today()
    mk = f"{today.year:04d}-{today.month:02d}"
    month_start = dt.date(today.year, today.month, 1)
    prev_end = month_start - dt.timedelta(days=1)

    adj_all = bip.load_adjust()
    a = adj_all.get(mk, {}) or {}
    adj_invest = a.get("新增投入", {}) or {}
    adj_src = a.get("資金來源", {}) or {}
    adj_mv = a.get("市值變化", {}) or {}
    adj_div = a.get("配息", {}) or {}
    adj_fee = a.get("手續費", {}) or {}
    adj_interest = a.get("利息", {}) or {}
    rate_overrides = a.get("資金成本", {}) or {}
    updates_all = a.get("估值更新", []) or []
    mv_reliable = a.get("市值可靠", True)

    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    db = sqlite3.connect(str(BASE / "dragon_assets.db"))
    end_row = bip.db_asset_on(db, today.isoformat())
    start_row = bip.db_asset_on(db, prev_end.isoformat())
    # 總資產另查（db_asset_on 只回 4 欄：date/securities/funds/insurance）
    def _db_total(d):
        r = db.execute("SELECT date, total_assets FROM assets WHERE date <= ? "
                       "ORDER BY date DESC LIMIT 1", (d,)).fetchone()
        return (_num(r[1]), r[0]) if r else (None, None)
    total_end, total_end_date = _db_total(today.isoformat())
    total_start, total_start_date = _db_total(prev_end.isoformat())
    db.close()
    if not end_row:
        raise RuntimeError("dragon_assets.db 沒有可用資產列")

    mv0 = {"股票": start_row[1], "基金": start_row[2], "保單": start_row[3]} if start_row else None
    mv1 = {"股票": end_row[1], "基金": end_row[2], "保單": end_row[3]}

    # 配息：與月報同一條 auto 分類（校正檔有指定則優先）
    dr = (snap.get("dividend_records") or {}).get(mk, {}) or {}
    auto_div = {c: 0.0 for c in CLASS_KEYS}
    for k, v in dr.items():
        if isinstance(v, (int, float)):
            auto_div[bip.classify_dividend(k)] += float(v)

    updates = [{"date": u.get("date"), "c": u.get("類") or u.get("類別"),
                "amount": _num(u.get("金額")), "as_of": u.get("as_of", ""),
                "kind": u.get("態樣", "估值更新"), "reason": u.get("原因", "")}
               for u in updates_all if isinstance(u, dict)]

    classes = []
    for c in CLASS_KEYS:
        inv = _num(adj_invest.get(c, 0))
        upd_sum = sum(u["amount"] for u in updates if u["c"] == c)
        div = _num(adj_div.get(c, auto_div.get(c, 0)))
        fee = _num(adj_fee.get(c, 0))
        gross = (mv1[c] - mv0[c]) if mv0 else 0
        if c in adj_mv:
            mkt = _num(adj_mv[c])
            basis = "校正檔指定"
        elif mv_reliable and mv0:
            mkt = gross - inv - upd_sum
            basis = "推導"
        else:
            mkt = 0
            basis = "無月初基準，不計"
        classes.append({"c": c, "mv0": (mv0[c] if mv0 else None), "mv1": mv1[c],
                        "gross": gross, "invest": inv, "src": adj_src.get(c, ""),
                        "upd_sum": upd_sum, "mkt": mkt, "div": div, "fee": fee,
                        "pnl": mkt + div - fee, "basis": basis})

    grand_mkt = sum(x["mkt"] for x in classes)
    grand_div = sum(x["div"] for x in classes)
    grand_fee = sum(x["fee"] for x in classes)
    sub_total = grand_mkt + grand_div - grand_fee

    # ── 本月報酬率／佔比／配息率（2026-09-22 使用者核准：本月頁只談本月，累計移到頁尾折疊）──
    total_mv0 = sum((x["mv0"] or 0) for x in classes) or 0
    for x in classes:
        b0 = x["mv0"] or 0
        x["rate"] = (x["pnl"] / b0) if b0 else None
        x["rate_ann"] = (x["rate"] * 12) if x["rate"] is not None else None
        x["share"] = (b0 / total_mv0) if total_mv0 else None
        x["div_yield_m"] = (x["div"] / b0) if (b0 and x["div"]) else None
        x["div_yield_y"] = (x["div_yield_m"] * 12) if x["div_yield_m"] is not None else None
    # 保單借貸月息 → 配息覆蓋倍數（本月頁該看的槓桿指標）
    policy_int = sum(l["monthly"] for l in bip.load_loans(snap, rate_overrides) if "保單借貸" in l["name"])
    for x in classes:
        x["int_cover"] = ((x["div"] / policy_int) if (x["c"] == "保單" and policy_int and x["div"]) else None)
        x["policy_int"] = (policy_int if x["c"] == "保單" else None)
    interest_total = sum(_num(v) for v in adj_interest.values())

    # 資金成本（結構化；公式與 funding_cost_report 相同）
    loans = bip.load_loans(snap, rate_overrides)
    total_bal = sum(l["balance"] for l in loans)
    total_m = sum(l["monthly"] for l in loans)
    total_pay = sum(l["payment"] for l in loans)
    wacc = (total_m * 12 / total_bal) if total_bal else 0
    inv_mv = (_num(snap.get("securities_total_market_value") or snap.get("securities_total"))
              + _num(snap.get("fund_market_value") or snap.get("funds_total"))
              + _num(snap.get("insurance_total")))
    div_month_actual = sum(_num(self_div) for self_div in (adj_div.values() or [])) or None
    div_base = div_month_actual if div_month_actual else _num(snap.get("dividend_month_expected") or 100000)
    div_yield = (div_base * 12 / inv_mv) if inv_mv else 0
    spread = div_yield - wacc
    if spread >= SPREAD_GREEN:
        light, light_txt = "ok", f"🟢 利差充足（≥{SPREAD_GREEN*100:.1f}%）→ 現金流安全、套利空間存在"
    elif spread >= 0:
        light, light_txt = "warn", "🟡 利差偏薄（0~1.2%）→ 付息可、擴槓桿謹慎"
    else:
        light, light_txt = "bad", "🔴 利差為負 → 配息不足以 cover 利息，停止加槓桿"

    policies = []
    for nm, cost_key, cur_key, div_key in (("安聯 A+B", "allianz_cost", "allianz_ab_current_value", "allianz_cum_dividend"),
                                           ("第一金 FJ33", "firstjin_cost", "firstjin_current_value", "firstjin_cum_dividend")):
        cost = _num(snap.get(cost_key))
        cur = _num(snap.get(cur_key))
        cd = _num(snap.get(div_key))
        policies.append({"name": nm, "cost": cost, "current": cur, "principal": cur - cost,
                         "cum_div": cd, "real": cd + cur - cost})

    return {
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "month": mk,
        "period": {"start": month_start.isoformat(), "end": end_row[0],
                   "prev_end": prev_end.isoformat(), "start_db": (start_row[0] if start_row else ""),
                   "start_ref": total_start_date or (start_row[0] if start_row else "")},
        "total_assets": {"start": total_start, "end": total_end,
                         "chg": (total_end - total_start) if (total_start is not None and total_end is not None) else None},
        "mv_reliable": bool(mv_reliable),
        # 保單專屬：配息 vs 借貸月息覆蓋（本月頁該看的指標，不是累計本金）
        "policy_int": policy_int,
        "classes": classes,
        "grand": {"mkt": grand_mkt, "div": grand_div, "fee": grand_fee, "sub": sub_total},
        "total_mv0": total_mv0,
        "rate": ((sub_total / total_mv0) if total_mv0 else None),
        "rate_ann": ((sub_total / total_mv0 * 12) if total_mv0 else None),
        "interest": {"total": interest_total, "by": adj_interest},
        "perf": {"gross": sub_total, "net": sub_total - interest_total},
        "updates": updates,
        "loans": [{"name": l["name"], "balance": l["balance"], "rate": l["rate"],
                   "monthly": l["monthly"], "payment": l["payment"]} for l in loans],
        "funding": {"total_balance": total_bal, "total_monthly_interest": total_m,
                    "total_payment": total_pay, "wacc": wacc, "inv_mv": inv_mv,
                    "div_base": div_base, "div_yield": div_yield, "spread": spread,
                    "light": light, "light_txt": light_txt,
                    "div_source": ("當月實收" if div_month_actual else "保守常態")},
        "policies": policies,
        "freshness": _freshness(snap, mk, end_row[0]),
        "dividend_raw": {k: v for k, v in dr.items() if isinstance(v, (int, float))},
    }


# ── 靜態摘要（無 JS 也看得到關鍵數字） ─────────────────────────────
def static_fallback(p: dict) -> str:
    def nt(v):
        try:
            return f"{int(round(float(v))):+,}"
        except Exception:
            return "—"

    rows = [
        (f'{p["month"]} 本月投資損益', nt(p["perf"]["net"]) + "（未扣利息）" if not p["interest"]["total"] else nt(p["perf"]["net"])),
        ("　帳面市值變化", nt(p["total_assets"].get("chg")) + "（總資產）"),
        ("　配息實收", nt(p["grand"]["div"])),
        ("　本月報酬率", "｜".join(f'{x["c"]} {x["rate"]*100:+.2f}%（佔 {(x["share"] or 0)*100:.1f}%）'
                                  for x in p["classes"] if x.get("rate") is not None)),
        ("　估值更新", nt(-sum(u["amount"] for u in p["updates"]))),
        ("市場面損益（推定）", nt(p["grand"]["mkt"])),
    ]
    for c in p["classes"]:
        rows.append((f'　{c["c"]}', f'市值 {nt(c["gross"])}｜配息 {nt(c["div"])}｜損益 {nt(c["pnl"])}'))
    rows.append(("淨利差", f'{p["funding"]["spread"]*100:+.2f}pp｜{p["funding"]["light_txt"]}'))
    tr = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
    return ('<section class="card"><h2>◆ 摘要<em>（靜態版；JS 可用時自動升級為完整圖表）</em></h2>'
            f'<table class="fb"><tbody>{tr}</tbody></table></section>')


CSS = """
*{box-sizing:border-box}
body{margin:0;background:#0b1120;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC",sans-serif;line-height:1.5}
.wrap{max-width:1080px;margin:0 auto;padding:14px}
a{color:#93c5fd;text-decoration:none}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:12px}
h1{font-size:19px;font-weight:900;margin:0}
h1 small{display:block;font-size:11.5px;font-weight:500;color:#94a3b8;margin-top:3px}
.back{flex:0 0 auto;font-size:11.5px;border:1px solid #334155;border-radius:9px;padding:6px 9px;background:rgba(30,41,59,.7)}
.card{background:rgba(30,41,59,.55);border:1px solid rgba(148,163,184,.14);border-radius:14px;padding:13px 14px;margin-bottom:11px}
.card h2{font-size:13.5px;font-weight:800;margin:0 0 10px;display:flex;flex-wrap:wrap;gap:8px;align-items:baseline}
.card h2 em{font-style:normal;font-size:10.5px;font-weight:500;color:#94a3b8}
.grid{display:grid;gap:9px}
.grid>*{min-width:0}
.tscroll{max-width:100%}
.k4{grid-template-columns:repeat(2,1fr)}
.k2{grid-template-columns:1fr}
@media(min-width:720px){.k4{grid-template-columns:repeat(4,1fr)}.k2{grid-template-columns:1fr 1fr}}
.kpi{background:rgba(15,23,42,.75);border:1px solid rgba(148,163,184,.16);border-radius:12px;padding:10px 11px}
.kpi .lbl{font-size:10.5px;color:#94a3b8;letter-spacing:.02em}
.kpi .val{font-size:20px;font-weight:900;margin-top:2px;font-variant-numeric:tabular-nums}
.kpi .sub{font-size:10.5px;color:#94a3b8;margin-top:2px}
.up{color:#34d399}.down{color:#fb7185}.neutral{color:#e2e8f0}
.chip{display:inline-block;font-size:10.5px;font-weight:700;border-radius:999px;padding:2px 8px;border:1px solid}
.chip.ok{color:#6ee7b7;border-color:rgba(52,211,153,.4);background:rgba(52,211,153,.08)}
.chip.warn{color:#fcd34d;border-color:rgba(251,191,36,.4);background:rgba(251,191,36,.08)}
.chip.bad{color:#fda4af;border-color:rgba(251,113,133,.4);background:rgba(251,113,133,.08)}
.chip.info{color:#a5b4fc;border-color:rgba(129,140,248,.4);background:rgba(129,140,248,.08)}
.wf{margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid rgba(148,163,184,.12)}
.wf:last-child{border-bottom:none;margin-bottom:0;padding-bottom:0}
.wf .head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px}
.wf .name{font-size:13px;font-weight:800}
.wf .amt{font-size:15px;font-weight:900;font-variant-numeric:tabular-nums}
.step{display:flex;justify-content:space-between;gap:10px;font-size:11.5px;color:#cbd5e1;padding:1.5px 0}
.step .v{font-variant-numeric:tabular-nums}
.step.total{border-top:1px solid rgba(148,163,184,.2);margin-top:4px;padding-top:5px;font-weight:800;color:#f1f5f9}
.note{font-size:11px;color:#94a3b8;border-top:1px solid rgba(148,163,184,.12);margin-top:8px;padding-top:8px}
table.fb,table.t{width:100%;border-collapse:collapse;font-size:12px}
table.fb th{text-align:left;font-weight:500;color:#94a3b8;padding:6px 8px;border-bottom:1px solid rgba(148,163,184,.14);white-space:nowrap;width:42%}
table.fb td{padding:6px 8px;border-bottom:1px solid rgba(148,163,184,.14);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
table.t th{text-align:right;font-weight:600;color:#94a3b8;font-size:11px;padding:5px 7px;border-bottom:1px solid rgba(148,163,184,.18)}
table.t th:first-child{text-align:left}
table.t td{text-align:right;padding:5px 7px;border-bottom:1px solid rgba(148,163,184,.1);font-variant-numeric:tabular-nums}
table.t td:first-child{text-align:left;color:#e2e8f0}
.tscroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.tscroll table{min-width:0}
@media(min-width:720px){.tscroll table{min-width:520px}}
@media(max-width:430px){table.t{font-size:11px}table.t th,table.t td{padding:4px 5px}}
.step .v,.wf .amt{white-space:nowrap}
.tl{position:relative;padding-left:15px}
.tl:before{content:"";position:absolute;left:4px;top:4px;bottom:4px;width:1px;background:rgba(148,163,184,.25)}
.tl .ev{position:relative;padding:6px 0;font-size:12.5px}
.tl .ev .src{display:block;font-size:11px;color:#94a3b8;margin-top:1px}
.tl .ev:before{content:"";position:absolute;left:-14px;top:12px;width:7px;height:7px;border-radius:50%;background:#fbbf24;box-shadow:0 0 0 3px rgba(251,191,36,.14)}
.muted{color:#94a3b8}
.chip2{display:inline-block;font-size:10.5px;padding:1px 7px;border-radius:999px;background:rgba(148,163,184,.16);color:#cbd5e1;margin-left:6px;white-space:nowrap}
.chip2.up{background:rgba(16,185,129,.18);color:#6ee7b7}
.chip2.down{background:rgba(244,63,94,.18);color:#fda4af}
.wf .head{flex-wrap:wrap}
.wf .head .rt{display:flex;gap:4px;flex-wrap:wrap;margin-left:auto;margin-right:6px}
.step.sub2 span{font-size:11px;color:#94a3b8}
details.bg{margin-top:14px;background:rgba(15,23,42,.55);border:1px solid rgba(148,163,184,.16);border-radius:12px;padding:10px 13px}
details.bg summary{cursor:pointer;font-size:12.5px;font-weight:700;color:#94a3b8}
details.bg[open] summary{color:#e2e8f0;margin-bottom:8px}
.period-tag{font-size:10.5px;color:#94a3b8;font-weight:500}
""".strip()

JS = """
function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function money(n){ if(n===null||n===undefined||isNaN(n)){ return '—'; } var v=Math.round(n); return v.toLocaleString('en-US'); }
function sgn(n){ if(n===null||n===undefined||isNaN(n)){ return '—'; } return (n>=0?'+':'') + money(n); }
function cls(n){ return n>0?'up':(n<0?'down':'neutral'); }
function pct(n){ return (n>=0?'+':'') + (n*100).toFixed(2) + '%'; }
var PERIOD_END = '';

function kpi(lbl, val, sub, klass){
  return '<div class="kpi"><div class="lbl">'+esc(lbl)+'</div><div class="val '+(klass||'')+'">'+val+
         '</div><div class="sub">'+(sub||'')+'</div></div>';
}

function wfRow(c){
  var h = '<div class="wf"><div class="head"><div class="name">'+esc(c.c)+
          (c.share!=null?'<span class="chip2">佔 '+(c.share*100).toFixed(1)+'%</span>':'')+'</div>'+
          '<div class="rt">'+(c.rate!=null?'<span class="chip2 '+cls(c.rate)+'">本月 '+pct(c.rate)+'</span>':'')+
          (c.rate_ann!=null?'<span class="chip2">年化 '+pct(c.rate_ann)+'</span>':'')+'</div>'+
          '<div class="amt '+cls(c.pnl)+'">'+sgn(c.pnl)+'</div></div>';
  if(c.mv0!=null){ h += '<div class="step sub2"><span>月初市值 → '+esc(PERIOD_END)+'</span><span class="v">'+money(c.mv0)+' → '+money(c.mv1)+'</span></div>'; }
  h += '<div class="step"><span>帳面市值變化</span><span class="v '+cls(c.gross)+'">'+sgn(c.gross)+'</span></div>';
  if(c.invest){ h += '<div class="step"><span>− 新增投入'+(c.src?'（'+esc(c.src)+'）':'')+'</span><span class="v">'+money(-c.invest)+'</span></div>'; }
  if(c.upd_sum){ h += '<div class="step"><span>− 估值更新</span><span class="v">'+money(-c.upd_sum)+'</span></div>'; }
  h += '<div class="step total"><span>＝ 市場面損益'+(c.basis==='推導'?'（推定）':'')+'</span><span class="v '+cls(c.mkt)+'">'+sgn(c.mkt)+'</span></div>';
  h += '<div class="step"><span>＋ 配息實收</span><span class="v up">'+sgn(c.div)+'</span></div>';
  if(c.div_yield_m){ h += '<div class="step sub2"><span>配息率（本月配息 ÷ 月初市值）</span><span class="v">'+(c.div_yield_m*100).toFixed(2)+'%/月 ≈ '+(c.div_yield_y*100).toFixed(1)+'%/年</span></div>'; }
  if(c.int_cover!=null){ h += '<div class="step sub2"><span>配息 vs 借貸月息</span><span class="v">'+money(c.div)+' ÷ '+money(c.policy_int)+' → 覆蓋 '+c.int_cover.toFixed(1)+' 倍</span></div>'; }
  if(c.fee){ h += '<div class="step"><span>− 手續費</span><span class="v">'+money(-c.fee)+'</span></div>'; }
  h += '<div class="step total"><span>＝ '+esc(c.c)+'損益（含市值）</span><span class="v '+cls(c.pnl)+'">'+sgn(c.pnl)+'</span></div>';
  if(c.basis!=='推導'){ h += '<div class="note">基準：'+esc(c.basis)+'</div>'; }
  return h+'</div>';
}

function render(d){
  var h = [], g = d.grand||{}, f = d.funding||{}, p = d.period||{}, t = d.total_assets||{};
  PERIOD_END = p.end || '';
  h.push('<header class="top"><div><h1>📈 本月績效<small>'+esc(d.month)+'　'+esc(p.start)+' ~ '+esc(p.end)+
         '（月初基準 '+esc(p.start_db||p.prev_end)+'）｜產生於 '+esc(d.generated_at)+'</small></h1></div>'+
         '<a class="back" href="index.html">← 回主儀表板</a></header>');

  var sub = (d.interest && d.interest.total) ? '已扣投資利息 '+money(d.interest.total) : '未扣利息（見資金成本卡）';
  h.push('<section class="grid k4">');
  h.push(kpi('本月投資損益', '<span class="'+cls(d.perf.net)+'">'+sgn(d.perf.net)+'</span>', esc(sub)));
  h.push(kpi('總資產變化', '<span class="'+cls(t.chg)+'">'+sgn(t.chg)+'</span>', '帳面（含未實現、含配息）'));
  h.push(kpi('配息實收（三類）', '<span class="up">'+sgn(g.div)+'</span>', '股票＋基金＋保單'));
  h.push(kpi('本月報酬率', '<span class="'+(d.rate>=0?'up':'down')+'">'+pct(d.rate)+'</span>',
             '以月初市值 '+money(d.total_mv0)+' 計（年化＝單月推估 '+pct(d.rate_ann)+'）'));
  h.push(kpi('淨利差（配息−資金成本）', '<span class="'+(f.light==='ok'?'up':(f.light==='bad'?'down':''))+'">'+(f.spread*100).toFixed(2)+'pp</span>',
             '加權資金成本 '+(f.wacc*100).toFixed(2)+'%'));
  h.push('</section>');

  h.push('<section class="card"><h2>◆ 四段式拆解<em>帳面 → 投入/校正 → 市場 → 配息（每類同一套）</em></h2>');
  (d.classes||[]).forEach(function(c){ h.push(wfRow(c)); });
  h.push('<div class="note">市場面＝帳面市值變化 − 新增投入 − 估值更新（推定值，含匯率）。'+
         '配息實收為本月入帳金額；月配息基金的除息本身會壓低淨值，已由「配息實收」加回，不重複計算。</div>');
  h.push('</section>');

  if((d.updates||[]).length){
    h.push('<section class="card"><h2>◆ 估值更新<em>帳務校正事件（不是市場虧損）</em></h2><div class="tl">');
    d.updates.forEach(function(u){
      h.push('<div class="ev"><b>'+esc(u.date)+'</b>　'+esc(u.c)+'　'+
             '<span class="'+cls(u.amount)+'">'+sgn(u.amount)+'</span>'+
             '<span class="src">'+esc(u.kind)+(u.as_of?('｜真值 as-of '+esc(u.as_of)):'')+(u.reason?('｜'+esc(u.reason)):'')+'</span></div>');
    });
    h.push('</div><div class="note">估值更新＝兩次截圖/真值同步之間的差額被歸為「帳務校正」的部分。'+
           '保單序列本身是截圖之間的差額，內含市場漲跌與前次估值誤差，無法完全分離 —— 本清單只列已確認的事件。</div></section>');
  }

  h.push('<section class="card"><h2>◆ 資金成本<em>借款利息 vs 投資現金流</em></h2><div class="grid k2"><div>');
  h.push('<div class="tscroll"><table class="t"><thead><tr><th>借款</th><th>餘額</th><th>利率</th><th>實際月付</th><th>其中利息</th></tr></thead><tbody>');
  (d.loans||[]).forEach(function(l){
    h.push('<tr><td>'+esc(l.name)+'</td><td>'+money(l.balance)+'</td><td>'+(l.rate*100).toFixed(2)+'%</td>'+
           '<td>'+money(l.payment)+'</td><td>'+money(l.monthly)+'</td></tr>');
  });
  h.push('<tr><td><b>合計</b></td><td><b>'+money(f.total_balance)+'</b></td><td>—</td><td><b>'+money(f.total_payment)+
         '</b></td><td><b>'+money(f.total_monthly_interest)+'</b></td></tr></tbody></table></div>');
  h.push('</div><div>');
  h.push('<div class="tscroll"><table class="t"><tbody>'+
    '<tr><td>加權平均資金成本</td><td>'+(f.wacc*100).toFixed(2)+'%/年</td></tr>'+
    '<tr><td>投資市值（股票＋基金＋保單）</td><td>'+money(f.inv_mv)+'</td></tr>'+
    '<tr><td>配息（'+esc(f.div_source)+'）</td><td>'+money(f.div_base)+'</td></tr>'+
    '<tr><td>配息殖利率</td><td>'+(f.div_yield*100).toFixed(2)+'%/年</td></tr>'+
    '<tr><td><b>淨利差</b></td><td><b>'+(f.spread*100).toFixed(2)+'pp</b></td></tr>'+
    '</tbody></table></div>');
  h.push('<div style="margin-top:8px"><span class="chip '+esc(f.light)+'">'+esc(f.light_txt)+'</span></div>');
  h.push('</div></div><div class="note">純配息 '+money(f.div_base)+' vs 純月息 '+money(f.total_monthly_interest)+
         '；實際月付含本金攤還 '+money(f.total_payment)+'（永豐房貸為本利攤還）。</div></section>');

  var _pc = (d.policies||[]).reduce(function(a,x){return a+(x.cost||0);},0),
      _pr = (d.policies||[]).reduce(function(a,x){return a+(x.real||0);},0);
  h.push('<details class="bg"><summary>📦 背景資訊（非本月）｜保單自買入累計 — 投入 '+money(_pc)+'｜真實累計 '+sgn(_pr)+'（點開看明細）</summary>'+
         '<div class="period-tag">⚠️ 不同時間尺度：下面是「自買入至今」的累計口徑，上面全部是本月。月配息基金的現值會被配息搬走，所以「現值 &lt; 成本」是常態，不是虧損 —— 累計要看「累計配息 ＋ (現值 − 成本)」。</div>');
  h.push('<div class="tscroll"><table class="t"><thead><tr><th>保單</th><th>投入</th><th>現值</th><th>本金</th><th>累計配息</th><th>真實績效</th></tr></thead><tbody>');
  var rsum = 0;
  (d.policies||[]).forEach(function(x){
    rsum += x.real;
    h.push('<tr><td>'+esc(x.name)+'</td><td>'+money(x.cost)+'</td><td>'+money(x.current)+'</td>'+
           '<td class="'+cls(x.principal)+'">'+sgn(x.principal)+'</td><td>'+money(x.cum_div)+'</td>'+
           '<td class="'+cls(x.real)+'"><b>'+sgn(x.real)+'</b></td></tr>');
  });
  h.push('<tr><td><b>合計</b></td><td>—</td><td>—</td><td>—</td><td>—</td><td class="'+cls(rsum)+'"><b>'+sgn(rsum)+'</b></td></tr>');
  h.push('</tbody></table></div><div class="note">只讀「現值 − 成本」會看到本金 −4.5%，但月配息基金的配息已入袋；把累計配息加回才是真實績效。</div></details>');

  h.push('<section class="card"><h2>◆ 資料基準<em>各源 as-of（越舊的數字越可能再變）</em></h2><table class="t"><tbody>');
  (d.freshness||[]).forEach(function(x){ h.push('<tr><td>'+esc(x.src)+'</td><td>'+esc(x.date)+'</td></tr>'); });
  h.push('</tbody></table><div class="note">本月為「未收月」：月底前市值與配息都會再動，最終版以每月 1 日的月報為準。'+
         (d.mv_reliable?'':'⚠️ 本月市值基準不足，市場面未計。')+'</div></section>');

  return h.join('');
}

var seed = {};
try { seed = JSON.parse(document.getElementById('seed').textContent); } catch(e){ seed = {}; }
var app = document.getElementById('app');
try { app.innerHTML = render(seed); } catch(e){ /* 保留靜態摘要 */ }
if(window.fetch){
  fetch('mtd_data.json', {cache:'no-store'}).then(function(r){ return r.json(); }).then(function(fresh){
    try { app.innerHTML = render(fresh); } catch(e){}
  }).catch(function(){});
}
""".strip()

HTML_TPL = """<!DOCTYPE html>
<html lang="zh-Hant-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📈 龍九本月績效</title>
<style>__CSS__</style>
</head>
<body>
<div class="wrap" id="app">__FALLBACK__</div>
<script type="application/json" id="seed">__SEED__</script>
<script>__JS__</script>
</body>
</html>
""".strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="產出本月績效頁（mtd_performance.html + mtd_data.json）")
    ap.add_argument("--quiet", action="store_true", help="只產檔、不印摘要（cron 用）")
    a = ap.parse_args()

    d = payload()
    seed = json.dumps(d, ensure_ascii=False).replace("</", "<\\/")
    html = (HTML_TPL.replace("__CSS__", CSS).replace("__JS__", JS)
            .replace("__SEED__", seed).replace("__FALLBACK__", static_fallback(d)))
    OUT_HTML.write_text(html, encoding="utf-8", newline="\n")
    OUT_JSON.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")

    if not a.quiet:
        g = d["grand"]
        print(f"✅ {OUT_HTML.name}（{OUT_HTML.stat().st_size:,} bytes）＋ {OUT_JSON.name}"
              f"（{OUT_JSON.stat().st_size:,} bytes）")
        print(f"   {d['month']}（{d['period']['start']}~{d['period']['end']}）"
              f"｜市場面 {g['mkt']:+,.0f}｜配息 {g['div']:+,.0f}｜損益 {g['sub']:+,.0f}"
              f"｜估值更新 {sum(u['amount'] for u in d['updates']):+,.0f} 共 {len(d['updates'])} 筆")
        for c in d["classes"]:
            print(f"     {c['c']}：帳面 {c['gross']:+,.0f}｜市場 {c['mkt']:+,.0f}｜配息 {c['div']:+,.0f}｜損益 {c['pnl']:+,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
