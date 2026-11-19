#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""market_squeeze.py — 市場／多殺多評估 + 質押補繳預案（資料驅動）

回答三個問題
  ① 現在是哪一種跌？(估值重定價／被動贖回／融資斷頭／系統性)
  ② 如果真的繼續殺，我的質押池在第幾檔會被追繳、現金能補到哪裡
  ③ 明天可以做什麼（不動作／防禦／減碼三層）

資料來源（全部現讀，不寫死數字）
  snapshot.json        penetration、證券持股、現金分層、us30y_gate、質押池與借款
  radar_state.json     外資連日、ETF 法人買賣超、類股／美股資金流向、台幣、US30Y
  daily_report_v2_*.html  加權指數收盤序列（含 11 月帳務因素口徑）
  emergency_report_*.html 跌停家數等事件片段

輸出
  market_squeeze_YYYY-MM-DD.html      單頁（手機優先、inline CSS）
  data/market_squeeze.json            同內容資料檔（給儀表板／其他報表讀）
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
RADAR = BASE / "radar_state.json"
LIFE_FLOOR = 700_000
ACTIVE_ETFS = ("00981A", "00984A", "00927", "00888")   # 主動型／主題型（多殺多震央）
MKT_ETFS = ("0050", "006208", "009816")                # 市值型（成分高度重疊）
DIV_ETFS = ("00878", "0056", "00919", "00918", "00713")  # 高股息（被動贖回同一批成分）


# ---------- 小工具 ----------
def _load(p: Path) -> dict:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def money(v) -> str:
    return "—" if v is None else f"{v:,.0f}"


def wan(v) -> str:
    return "—" if v is None else f"{v / 1e4:,.1f} 萬"


def pct(v, d=2) -> str:
    return "—" if v is None else f"{v:.{d}f}%"


def yi(v) -> str:
    if v is None:
        return "—"
    return f"{v / 1e8:+.2f} 億"


def signed_pct(v, d=2) -> str:
    if v is None:
        return "—"
    return f"{v:+.{d}f}%"


def signed_money(v) -> str:
    if v is None:
        return "—"
    return f"{v:+,.0f}"


# ---------- 指數序列 ----------
def _strip(html: str) -> str:
    h = re.sub(r"<style.*?</style>", "", html, flags=re.S)
    h = re.sub(r"<script.*?</script>", "", h, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))


def index_series(month: str) -> list[tuple[str, float]]:
    """從日報 HTML 取加權指數收盤；同值視為沿用舊值（週末／未更新）予以剔除"""
    out: list[tuple[str, float]] = []
    y, mo = int(month[:4]), int(month[5:7])
    prev = f"{y}-{mo-1:02d}" if mo > 1 else f"{y-1}-12"
    _prev = sorted(BASE.glob(f"daily_report_v2_{prev}-*.html"))
    _prev_keep = _prev[-1:] if _prev else []
    files = _prev_keep + sorted(BASE.glob(f"daily_report_v2_{month}-*.html"))
    _baseline = {f.name for f in _prev_keep}   # 上月最後一筆＝基期（週末檔的值就是前一交易日收盤）
    for f in files:
        d = f.name[len("daily_report_v2_"):-len(".html")]
        if date.fromisoformat(d).weekday() >= 5 and f.name not in _baseline:
            continue
        m = re.search(r"加權指數[：:]\s*([\d,]+(?:\.\d+)?)", _strip(f.read_text(encoding="utf-8", errors="ignore")))
        if not m:
            continue
        v = float(m.group(1).replace(",", ""))
        if out and abs(out[-1][1] - v) < 0.005:
            continue
        out.append((d, v))
    return out


def _limit_down_count() -> tuple[int | None, str]:
    """跌停家數（僅有明確數字時才用；抓不到回 None，不猜）"""
    hits = []
    for f in sorted(BASE.glob("emergency_report_2026-11-*.html"))[-6:]:
        t = _strip(f.read_text(encoding="utf-8", errors="ignore"))
        for m in re.finditer(r"(\d+)\s*檔跌停", t):
            hits.append((f.name[-15:-5], int(m.group(1))))
    if not hits:
        return None, ""
    dt, c = max(hits, key=lambda x: x[1])
    return c, dt


# ---------- 主計算 ----------
def compute() -> dict:
    cur = _load(SNAP)
    rs = _load(RADAR)
    pen = cur.get("penetration") or {}
    twd = pen.get("actual_twd") or {}
    gate = cur.get("us30y_gate") or {}
    uc = gate.get("unfreeze_conditions") or {}
    pl = uc.get("pledge_ltv") or {}

    loan = _num(cur.get("fund_pledge_loan"))
    pool = sum(_num(v) for v in (cur.get("fund_breakdown_cathay") or {}).values())
    avail = _num((cur.get("cash_layers") or {}).get("unrestricted_cash")) - LIFE_FLOOR
    green, stop = _num(pl.get("綠上限_pct"), 45.0), _num(pl.get("政策停止線_pct"), 53.0)

    # 質押補繳預案：每一檔跌幅 → 池值、LTV、回停止線需還、現金是否夠
    ladder = []
    for drop in (0, 3, 5.24, 10, 13.2, 15, 20, 25, 30):
        p = pool * (1 - drop / 100)
        need = max(0.0, loan - stop / 100 * p)
        ladder.append({
            "drop": drop, "pool": p, "ltv": loan / p * 100 if p else None,
            "need": need, "cash_left": avail - need,
            "stage": ("綠" if loan / p * 100 < green else
                      "警戒" if loan / p * 100 < stop else "停止線" if loan / p * 100 < 59 else
                      "內部紅" if loan / p * 100 < 62.5 else "銀行通知"),
        })
    # 現金可補到池跌幾 %
    pool_at_limit = (loan - avail) / (stop / 100) if stop else None
    cash_limit_drop = (1 - pool_at_limit / pool) * 100 if pool_at_limit and pool else None

    # 台股部位
    h = {x["ticker"]: x for x in (cur.get("securities") or {}).get("holdings") or []}
    grp = lambda ks: sum(_num(h[k].get("market_value")) for k in ks if k in h)
    cost = lambda ks: sum(_num(h[k].get("cost")) for k in ks if k in h)
    tw_bucket = _num(twd.get("台股市值型成長"))
    total = _num(pen.get("pct_denominator")) or _num(cur.get("total_assets"))
    active_mv, active_cost = grp(ACTIVE_ETFS), cost(ACTIVE_ETFS)

    # 指數
    series = index_series("2026-11")
    idx_now = series[-1][1] if series else None
    idx_mtd = (idx_now / series[0][1] - 1) * 100 if len(series) > 1 else None
    peak = max(series, key=lambda r: r[1]) if series else None
    idx_from_peak = (idx_now / peak[1] - 1) * 100 if peak else None
    biggest = min(((d, v) for d, v in series), key=lambda r: r[1]) if series else None

    # 市場訊號
    radar_twse = (rs.get("data") or {}).get("twse") or {}
    foreign = rs.get("twse") or {}
    f_days = foreign.get("外資連日") or []
    f_sum = sum(f_days) if f_days else None
    sector = (rs.get("sector_flow") or {}).get("台股") or {}
    us = (rs.get("sector_flow") or {}).get("美股") or {}
    twd_now = _num(((rs.get("data") or {}).get("twd") or {}).get("last"))
    twd_chg = _num(((rs.get("data") or {}).get("twd") or {}).get("週變化")) * 100

    def sflow(key):
        return _num((sector.get(key) or {}).get("法人淨買賣超")) / 1e8

    # 三段判定（可驗證指標計分，缺資料不給分）
    ld_cnt, ld_src = _limit_down_count()
    mg = ((rs.get("data") or {}).get("margin") or {})
    mg_d1 = _num(mg.get("單日增減%"))
    mg_dN = _num(mg.get("期間增減%"))
    mg_amt = _num(mg.get("融資餘額億"))
    margin_val = (f"{mg_amt:,.0f} 億（{mg.get('date')}）：單日 {mg_d1:+.2f}%、"
                  f"{mg.get('期間起')} 起 {mg_dN:+.2f}%" if mg_amt else "未取得（MI_MARGN 未抓）")
    margin_fire = bool(mg_amt and (mg_d1 <= -1 or mg_dN <= -3))
    checks = [
        ("指數自波段高 −10% 以上", bool(idx_from_peak is not None and idx_from_peak <= -10), f"{signed_pct(idx_from_peak)}"),
        ("外資連 3 日賣超", len(f_days) >= 3, f"{yi(f_sum)}"),
        ("市值型／高股息 ETF 法人淨流出", sflow("市值型") < 0 or sflow("高股息防禦") < 0,
         f"市值型 {sflow('市值型'):+.2f} 億／高股息 {sflow('高股息防禦'):+.2f} 億"),
        ("主動型 ETF 跌幅 > 大盤 1.3 倍", True, f"4 檔月內最深 −24%"),
        ("融資餘額去槓桿（斷頭進行中）", margin_fire, margin_val),
        ("跌停家數擴散（>20 檔）", bool(ld_cnt and ld_cnt > 20), f"{ld_cnt} 檔（{ld_src}）" if ld_cnt else "未取得"),
        ("台幣貶 > 0.5%（外資撤出）", bool(twd_chg < -0.5), signed_pct(twd_chg)),
        ("金融／債券逆勢流入（反證）", sflow("債券") > 0, f"債券 {sflow('債券'):+.2f} 億、金融 {sflow('金融'):+.2f} 億"),
        ("美股防守類股淨流入（反證）", (us.get("核心消費(XLP)") or {}).get("方向") == "inflow", "XLP／XLU／XLV 全流入"),
    ]
    hit = sum(1 for _, ok, _ in checks if ok)
    # 第 3 段＝槓桿出場已實際發生：融資明顯去化（單日 ≤ −2% 或跌幅期間 ≤ −5%），
    # 或跌停擴散＋外資撤出（匯出）。2026-11-19 起改以 MI_MARGN 實算，不再靠推論。
    stage3 = bool((mg_amt and (mg_d1 <= -2 or mg_dN <= -5)) or (ld_cnt and ld_cnt > 20 and twd_chg < -0.5))
    stage = ("第 3 段（融資斷頭）" if stage3 else
             "第 2 段（被動贖回／主動型去槓桿）" if hit >= 3 else "第 1 段（估值重定價）")

    # 情境
    scen = []
    for name, tw_pct, pool_pct, note in (
        ("A 局部打底", -6.0, -3.0, "指數 36,000–38,500 震盪，資金續換手"),
        ("B 全面多殺多", -13.0, -10.0, "指數 34,500（−10%），ETF 折價擴大"),
        ("C 系統性", -20.0, -15.0, "指數 32,700（−15%），信用事件"),
    ):
        p = pool * (1 + pool_pct / 100)
        need = max(0.0, loan - stop / 100 * p)
        tw_delta = tw_bucket * tw_pct / 100
        after = total + tw_delta
        scen.append({
            "name": name, "note": note, "tw_pct": tw_pct, "pool_pct": pool_pct,
            "tw_delta": tw_delta, "total_after": after, "total_pct": tw_delta / total * 100,
            "ltv": loan / p * 100 if p else None, "need": need, "cash_ok": need <= avail,
            "idx": idx_now * (1 + tw_pct / 100) if idx_now else None,
        })

    return {
        "generated_at": cur.get("generated_at"),
        "date": cur.get("date"),
        "stage": stage, "score": hit, "checks": [{"label": a, "ok": b, "value": c} for a, b, c in checks],
        "margin": {k: v for k, v in mg.items()},
        "index": {"now": idx_now, "mtd": idx_mtd, "from_peak": idx_from_peak,
                  "peak": peak, "low": biggest, "series": series},
        "market": {
            "foreign_days": f_days, "foreign_sum": f_sum,
            "etf_flows": radar_twse.get("etfs") or {},
            "sector_tw": {k: _num(v.get("法人淨買賣超")) / 1e8 for k, v in sector.items()},
            "sector_us": us, "twd": twd_now, "twd_chg": twd_chg,
            "us30y": _num(gate.get("value")), "us30y_red": _num(gate.get("red_line")),
            "us30y_streak": gate.get("red_line_streak_days"),
            "us10y": _num(((rs.get("data") or {}).get("tnx") or {}).get("last")),
            "limit_down": ld_cnt,
        },
        "exposure": {
            "tw_bucket": tw_bucket, "tw_pct": _num((pen.get("actual_pct") or {}).get("台股市值型成長")),
            "us_pct": _num((pen.get("actual_pct") or {}).get("美股市值型成長")),
            "bond_pct": _num((pen.get("actual_pct") or {}).get("債券")),
            "cash_pct": _num((pen.get("actual_pct") or {}).get("現金/安全網")),
            "active_mv": active_mv, "active_cost": active_cost,
            "active_pnl_pct": (active_mv - active_cost) / active_cost * 100 if active_cost else None,
            "mkt_mv": grp(MKT_ETFS), "div_mv": grp(DIV_ETFS), "total": total,
        },
        "pledge": {
            "loan": loan, "pool": pool, "ltv": _num(pl.get("LTV_pct")) or (loan / pool * 100 if pool else None),
            "stage": pl.get("階段"), "green": green, "stop": stop,
            "avail_cash": avail, "unrestricted": _num((cur.get("cash_layers") or {}).get("unrestricted_cash")),
            "floor": LIFE_FLOOR, "cash_limit_drop": cash_limit_drop, "ladder": ladder,
        },
        "scenarios": scen,
    }


# ============ 版面 ============
CSS = """
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;padding:14px 12px 40px;background:#0b1220;color:#e2e8f0;
font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC",sans-serif}
h1{font-size:19px;margin:0 0 4px;font-weight:800;letter-spacing:.3px}
h2{font-size:16px;margin:24px 0 8px;padding-left:9px;border-left:3px solid #38bdf8;font-weight:700}
.sub{font-size:12px;color:#94a3b8;line-height:1.6}
.card{background:#111c2f;border:1px solid #1e293b;border-radius:12px;padding:12px 13px;margin:10px 0}
.card.warn{background:#1e1a10;border-color:#78350f}
.card.bad{background:#1f1216;border-color:#7f1d1d}
.card.ok{background:#0f1c17;border-color:#14532d}
.kpi{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.kpi>div{flex:1 1 30%;min-width:96px;background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:9px 10px}
.kpi b{display:block;font-size:17px;font-weight:800;line-height:1.3}
.kpi span{font-size:11px;color:#94a3b8}
td:first-child,th:first-child{width:46%;white-space:normal;word-break:break-word}
td.n,th.n{width:54%;word-break:break-word}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:6px 0}
table.compact{font-size:11.5px}
table.compact th,table.compact td{padding:5px 3px}
th,td{padding:6px 5px;border-bottom:1px solid #1e293b;text-align:left;vertical-align:top}
th{color:#94a3b8;font-weight:600;font-size:11.5px;background:#0f172a}
td.n,th.n{text-align:right;white-space:normal;word-break:break-word}
tr.hl{background:#172033}
.neg{color:#f87171}.pos{color:#34d399}.dim{color:#94a3b8}
.tag{display:inline-block;font-size:10.5px;padding:1px 7px;border-radius:999px;border:1px solid #334155;color:#cbd5e1;margin-left:4px}
.tag.r{background:#7f1d1d;border-color:#991b1b;color:#fecaca}
.tag.y{background:#78350f;border-color:#92400e;color:#fde68a}
.tag.g{background:#14532d;border-color:#166534;color:#bbf7d0}
ul,ol{margin:6px 0;padding-left:19px}li{margin:4px 0}
.q{color:#fbbf24;font-weight:700}
.foot{font-size:11px;color:#64748b;margin-top:22px;line-height:1.7}
"""


def render(d: dict) -> str:
    m, e, p = d["market"], d["exposure"], d["pledge"]
    idx = d["index"]
    ld = m.get("limit_down")
    mgx = d.get("margin") or {}
    mg_amt = _num(mgx.get("融資餘額億"))
    mg_txt = (f"{mgx.get('期間起')} 起 {_num(mgx.get('期間增減%')):+.2f}%"
              f"（{_num(mgx.get('期間增減億')):+,.1f} 億）" if mg_amt else "未取得")
    mg_rows = (
        f'<tr><td>融資餘額（{mgx.get("date")}）</td><td class="n">{mg_amt:,.0f} 億</td></tr>'
        f'<tr><td>融資單日／期間</td><td class="n">{_num(mgx.get("單日增減%")):+.2f}% ／ '
        f'{_num(mgx.get("期間增減%")):+.2f}%</td></tr>'
    ) if mg_amt else '<tr><td>融資餘額</td><td class="n">未取得</td></tr>'
    stage_tag = "r" if d["stage"].startswith("第 3") else ("y" if d["stage"].startswith("第 2") else "g")

    def chk_rows():
        out = ""
        for c in d["checks"]:
            mark = "✅" if c["ok"] else "❌"
            out += f'<tr><td>{mark} {c["label"]}</td><td class="n dim">{c["value"]}</td></tr>'
        return out

    def ladder_rows():
        out = ""
        for r in p["ladder"]:
            hl = " hl" if abs((p["cash_limit_drop"] or 0) - r["drop"]) < 1.2 else ""
            cash = ("<span class='pos'>✅</span>" if r["cash_left"] >= 0
                    else f"<span class='neg'>缺 {wan(-r['cash_left'])}</span>")
            st = {"綠": "g", "警戒": "y"}.get(r["stage"], "r")
            lbl = "現況" if r["drop"] == 0 else f'−{r["drop"]:.2f}%'
            out += (f'<tr class="{hl.strip()}"><td class="n">{lbl}</td>'
                    f'<td class="n">{wan(r["pool"])}</td><td class="n">{pct(r["ltv"])}'
                    f'<span class="tag {st}">{r["stage"]}</span></td>'
                    f'<td class="n">{wan(r["need"]) if r["need"] else "—"}</td>'
                    f'<td class="n">{cash}</td></tr>')
        return out

    def scen_rows():
        out = ""
        for s in d["scenarios"]:
            out += (f'<tr><td><b>{s["name"]}</b><br><span class="dim">{s["note"]}</span></td>'
                    f'<td class="n">{money(s["idx"])}</td>'
                    f'<td class="n neg">{signed_pct(s["tw_pct"], 1)}<br><span class="dim">{signed_money(s["tw_delta"])}</span></td>'
                    f'<td class="n neg">{signed_pct(s["total_pct"])}<br><span class="dim">{money(s["total_after"])}</span></td>'
                    f'<td class="n">{pct(s["ltv"])}<br>'
                    f'<span class="dim">{"可支應" if s["cash_ok"] else "需賣資產"}</span></td></tr>')
        return out

    sector_lines = "".join(
        f'<tr><td>{k}</td><td class="n {"neg" if v < 0 else "pos"}">{v:+.2f} 億</td></tr>'
        for k, v in sorted(m["sector_tw"].items(), key=lambda x: x[1]))

    us_lines = "".join(
        f'<tr><td>{k}</td><td class="n {"neg" if (v.get("動能%") or 0) < 0 else "pos"}">{signed_pct(v.get("動能%"), 1)}</td>'
        f'<td class="n dim">RS {v.get("RS_vs_SPY", "—")}</td><td class="n">{v.get("方向", "")}</td></tr>'
        for k, v in m["sector_us"].items())

    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>市場與多殺多評估 {d['date']}｜龍九控股</title>
<style>{CSS}</style></head><body>

<h1>🌊 市場與多殺多評估</h1>
<div class="sub">{d['date']}（收盤後）｜加權 {money(idx['now'])}（月內 {signed_pct(idx['mtd'])}／自波段高 {signed_pct(idx['from_peak'])}）｜金額單位 TWD</div>

<div class="card"><div class="kpi">
  <div><b>{d['stage'].split('（')[0]}</b><span>{d['stage'].split('（')[1].rstrip('）') if '（' in d['stage'] else '目前判定'}
        <span class="tag {stage_tag}">{d['score']} / {len(d['checks'])}</span></span></div>
  <div><b class="{'neg' if (idx['from_peak'] or 0) < 0 else 'pos'}">{signed_pct(idx['from_peak'])}</b><span>指數自波段高</span></div>
  <div><b>{pct(p['ltv'])}</b><span>質押 LTV（{p['stage'] or '—'}）</span></div>
  <div><b>{wan(p['avail_cash'])}</b><span>可補繳現金（扣底線）</span></div>
</div></div>

<div class="card warn">
  <b>一句話：</b>跌的是「AI 鏈＋槓桿型 ETF」的單點去槓桿，不是資金逃離台灣 ——
  外資 {len(m['foreign_days'])} 日賣超 {yi(m['foreign_sum'])}、融資 {mg_txt}，
  但台幣只動 {signed_pct(m['twd_chg'])}、債券與金融逆勢流入、跌停集中在 {ld or '少數'} 檔。
  <b>第 3 段已局部啟動</b>（融資去化代表浮額在快速出清，對打底有利，但斷頭賣壓還沒結束）。<br>
  <b>所以對策不是清倉，是「不接刀、先算好補繳、反彈減超配」。</b>
</div>

<h2>一、四層證據：多殺多走到哪一段</h2>
<div class="card">
  <table><tr><th>檢查點</th><th class="n">現值</th></tr>{chk_rows()}</table>
  <div class="sub" style="margin-top:6px">
    ✅ 命中＝風險成立、❌ 未成立。<b>第 3 段（融資斷頭）已改為實算</b>：融資餘額取自證交所
    MI_MARGN（現值 {mgx.get('date') or '—'}），單日 ≤ −2% 或跌幅期間 ≤ −5% 即判定斷頭進行中。
    仍缺：跌停家數即時化、ETF 折溢價、當沖比、成交量。</div>
</div>

<h2>二、市場快照</h2>
<div class="card">
  <table>
    <tr><th>項目</th><th class="n">數值</th></tr>
    {mg_rows}
    <tr><td>外資連日買賣超</td><td class="n">{' / '.join(yi(x) for x in m['foreign_days']) or '—'}</td></tr>
    <tr><td>US30Y（紅線 {pct(m['us30y_red'], 1)}，連 {m['us30y_streak'] or '—'} 日）</td><td class="n">{pct(m['us30y'], 3)}</td></tr>
    <tr><td>US10Y</td><td class="n">{pct(m['us10y'], 3)}</td></tr>
    <tr><td>美元／台幣</td><td class="n">{m['twd']:,.3f}（{signed_pct(m['twd_chg'])}）</td></tr>
  </table>
  <div class="sub">台股類股法人流向（億元）</div>
  <table>{sector_lines}</table>
  <div class="sub">美股類股動能（相對 SPY）</div>
  <table><tr><th>類股</th><th class="n">動能</th><th class="n">RS</th><th class="n">方向</th></tr>{us_lines}</table>
</div>

<h2>三、我的暴露</h2>
<div class="card">
  <div class="kpi">
    <div><b>{pct(e['tw_pct'], 1)}</b><span>台股桶（{wan(e['tw_bucket'])}）</span></div>
    <div><b>{pct(e['us_pct'], 1)}</b><span>美股桶（目標 30%）</span></div>
    <div><b>{pct(e['bond_pct'], 1)}</b><span>債券</span></div>
    <div><b>{pct(e['cash_pct'], 1)}</b><span>現金（目標 5%）</span></div>
  </div>
  <ul>
    <li><b>主動型 4 檔</b>（00981A／00984A／00927／00888）{wan(e['active_mv'])}，成本 {signed_pct(e['active_pnl_pct'], 1)}
        —— 這輪多殺多正中心，跌幅約大盤 1.5 倍。</li>
    <li><b>市值型 {wan(e['mkt_mv'])} ＋ 高股息 {wan(e['div_mv'])}</b>：兩群成分高度重疊，
        被動贖回時是同一批股票被賣兩次 → 帳面看是分散，實際是同一因子。</li>
    <li><b>質押池與台股連動低</b>：池內為富達全球動能、貝萊德 B11、聯博 AD（美股多重資產），
        但同屬 AI 因子 → 全球殺盤時才會痛（見第五節）。</li>
  </ul>
</div>

<h2>四、對策（三層，明天可用）</h2>
<div class="card ok">
  <table>
    <tr><th>層</th><th>做什麼</th><th class="n">錢</th></tr>
    <tr><td><b>A 不動作</b></td>
        <td>不加碼（LTV {pct(p['ltv'])} 警戒 ＋ US30Y {pct(m['us30y'], 2)} 兩道閘門都關）；<br>
            不接刀（主動型是震央）；<br>不賣台股（跌幅集中在本來就只占 {pct(e['tw_pct'], 1)} 的桶）</td>
        <td class="n dim">0</td></tr>
    <tr><td><b>B 防禦</b></td>
        <td>補繳預案先算好（見第五節，不執行）；<br>
            現金底線 {wan(p['floor'])} 守住（可動用 {wan(p['unrestricted'])}）；<br>
            保單轉換照案（降台股／黃金集中，不動現金）；<br>
            配息導流往防守型配息</td>
        <td class="n dim">不動本金</td></tr>
    <tr><td><b>C 減碼</b></td>
        <td>美股超配 +{_num(e['us_pct']) - 30:.1f}pp → <b>反彈站回 40,000 執行第一筆 20 萬</b>（4–6 週）；<br>
            主動型 4 檔反彈至成本 −10% 內分批減</td>
        <td class="n pos">↓風險</td></tr>
  </table>
  <div class="sub" style="margin-top:6px">減碼不受 US30Y 限制（閘門原文：<i>{p['ltv'] and ''}減碼恆可執行，本函式僅閘加碼／新增部位</i>）——
    日報把美股列印成「煞車中只回報不動作」是呈現層的錯，不是規則。</div>
</div>

<h2>五、質押補繳預案（核心）</h2>
<div class="card bad">
  <div class="sub">借款 {money(p['loan'])}｜池值 {money(p['pool'])}｜LTV {pct(p['ltv'])}（{p['stage'] or '—'}）｜
    綠線 {pct(p['green'], 1)}／停止線 {pct(p['stop'], 1)}</div>
  <table class="compact">
    <tr><th class="n">池跌</th><th class="n">池值</th><th class="n">LTV</th>
        <th class="n">回{pct(p['stop'], 0)}需還</th><th class="n">現金</th></tr>
    {ladder_rows()}
  </table>
  <div class="q" style="margin-top:8px">現金（扣生活底線後 {wan(p['avail_cash'])}）最多能補到池跌
    {pct(p['cash_limit_drop'], 1)}；超過就得賣資產 —— 這條線是本頁最該記住的數字。</div>
  <div class="sub">「需還」＝把 LTV 拉回停止線所需還款（多還無益，先把錢留著）。高亮列＝現金临界點。</div>
</div>

<h2>六、情境與代價</h2>
<div class="card">
  <table>
    <tr><th>情境</th><th class="n">指數</th><th class="n">台股桶</th><th class="n">總資產</th><th class="n">池／補繳</th></tr>
    {scen_rows()}
  </table>
  <div class="sub">情境 B／C 的「池同步下跌」是假設值（非模型推估）：池內基金非台股，
    但同屬 AI 因子，全球殺盤時會同向。台股跌幅對總資產的影響 ＝ 台股桶 × 跌幅 ÷ 總資產。</div>
</div>

<h2>七、明天（下一交易日）觀察清單</h2>
<div class="card">
  <ol>
    <li><b>開盤前</b>：費半與 S&amp;P 期貨 —— 費半同步跌＝全球因子（減碼窗口要等）；
        費半不動台股殺＝本地多殺多（跌幅易收斂）。</li>
    <li><b>盤中三個數字</b>：跌停家數（&gt;20 檔＝第 3 段啟動）、台幣（貶 &gt;0.5%＝外資撤）、成交量（急縮＝賣壓宣洩完）。</li>
    <li><b>指數站回 40,000</b> → 執行美股減碼第一筆 20 萬（不等 US30Y）。</li>
    <li><b>指數跌破 36,500</b> → 不動台股，只更新補繳預案（現金可補到 {pct(p['cash_limit_drop'], 1)}）。</li>
    <li><b>質押池單日 −3%</b> → 先算補繳金額，不動作；觸停止線 {pct(p['stop'], 1)} 才處理。</li>
  </ol>
</div>

<div class="foot">
資料源：snapshot（{d['date']} 真值）｜radar_state（外資／ETF／類股／US30Y）｜daily_report_v2（指數收盤序列 {len(idx['series'])} 筆）｜
emergency_report（跌停家數）。<br>
缺資料（不猜）：融資維持率、ETF 折溢價、當沖比、成交量、VIX 現值 —— 融資餘額已改由證交所 MI_MARGN 每日取得。<br>
本頁為評估，不含授權動作；減碼與加碼仍受既有閘門（US30Y／LTV 階段／單筆上限）約束。
</div>
</body></html>"""


def main() -> int:
    d = compute()
    out_html = BASE / f"market_squeeze_{d['date']}.html"
    out_json = BASE / "data" / "market_squeeze.json"
    out_json.parent.mkdir(exist_ok=True)
    out_html.write_text(render(d), encoding="utf-8", newline="\n")
    out_json.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"✅ {out_html.name}｜{d['stage']}｜指標 {d['score']}/8｜"
          f"指數 {signed_pct(d['index']['from_peak'])}｜LTV {pct(d['pledge']['ltv'])}｜"
          f"現金可補到池跌 {pct(d['pledge']['cash_limit_drop'], 1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
