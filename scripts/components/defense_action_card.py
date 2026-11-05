#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""defense_action_card.py — 日報「每日資產防禦檢查」卡（2026-11-05 使用者定版規格）

使用者規格（第二次收斂）：每天只回答四個問題，不再堆疊指標。
  ① 今日帳面   我的資產今天實際增加還是減少？
  ② 跑贏原因   是配置防守成功，還是剛好其他市場上漲？
  ③ 真正風險   哪個資產是目前最大拖累／最大曝險？
  ④ 後續動作   維持、注意，還是需要調整？

三項強制判斷（不得省略）：
  * 高股息（00878／0056 等）＝股票收益型，**不列為防禦資產**；壓力測試一律併入股票類。
  * 美股超配持續監控（目標與上限一律讀 thresholds_2026_0915），科技 15% 為上限。
  * 債券與現金的防禦效果必須用「實際跌幅 ＋ 壓力測試」驗證，不能只看配置比例。

界線：不得自行解除 G1/G2/G3 HOLD；情境為假設、不是預測；缺值一律「—」並降級為無法判定。
資料一律讀既有單一真值（snapshot／asset_diff_history／daily_analysis），本檔不新增口徑。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]

VERDICT_HOLD, VERDICT_WATCH, VERDICT_ACT, VERDICT_UNKNOWN = "維持", "注意", "調整", "無法判定"


def _load(p):
    try:
        return json.loads((BASE / p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _m(v, sign=False):
    if v is None:
        return "—"
    return f"{v:+,.0f}" if sign else f"{v:,.0f}"


def _pc(v, nd=1):
    return "—" if v is None else f"{v:.{nd}f}%"


def _pp(v):
    return "—" if v is None else f"{v:+.1f}pp"


def _pct_signed(v):
    return "—" if v is None else f"{v:+.2f}%"


def _pct_from_text(s):
    if not s:
        return None
    m = re.search(r"\(([+-]?\d+(?:\.\d+)?)%\)", str(s))
    return float(m.group(1)) if m else None


# ────────────────────────── 資料層 ──────────────────────────
def assess(snap: dict) -> dict:
    pen = snap.get("penetration") or {}
    twd = pen.get("actual_twd") or {}
    pct = pen.get("actual_pct") or {}
    sat = pen.get("satellite_twd") or {}

    total = _f(snap.get("total_assets"))
    cash = _f(snap.get("cash_total"))
    layers = snap.get("cash_layers") or {}
    avail = _f(layers.get("unrestricted_cash"))
    th = snap.get("thresholds_2026_0915") or {}
    floor = _f(snap.get("cash_floor")) or _f((th.get("現金_twd") or {}).get("生活底線"))
    thick = snap.get("cash_thickness") or {}

    tw, us = _f(twd.get("台股市值型成長")), _f(twd.get("美股市值型成長"))
    defi, bond = _f(twd.get("防守型配息")), _f(twd.get("債券"))
    gold = _f(sat.get("黃金"))
    equity = sum(x for x in (tw, us, defi) if x is not None) or None

    pl = snap.get("cathay_pledge_0911") or {}
    pool = _f((pl.get("擔保池") or {}).get("合計"))
    loan = _f(snap.get("fund_pledge_loan"))
    maint = (pool / loan * 100) if (pool and loan) else None
    line_notice, line_call, line_stop = 160.0, 140.0, 188.7
    for row in ((pl.get("維持率級距_單一真值_20261103") or {}).get("級距") or []):
        name = str(row.get("性質", ""))
        try:
            v = float(str(row.get("維持率", "")).replace("%", ""))
        except ValueError:
            continue
        if "通知" in name:
            line_notice = v
        elif "追繳" in name:
            line_call = v
        elif "停止" in name:
            line_stop = v

    def _drop_to(line):
        if not (pool and loan and line):
            return None
        return (1 - (loan * line / 100.0) / pool) * 100

    tgt, cap = th.get("桶目標_pct") or {}, th.get("單桶硬上限_pct") or {}
    step = ((th.get("動作階梯_pp") or {}).get("觀察")) or 3.0

    return {
        "total": total, "cash": cash, "avail": avail, "floor": floor,
        "target_cash": _f(thick.get("target")), "net_incl_re": _f(snap.get("net_worth_incl_re")),
        "tw": tw, "us": us, "defi": defi, "bond": bond, "gold": gold, "equity": equity,
        "tw_pct": _f(pct.get("台股市值型成長")), "us_pct": _f(pct.get("美股市值型成長")),
        "tech_pct": _f(pct.get("美股市值型成長_科技")), "defi_pct": _f(pct.get("防守型配息")),
        "bond_pct": _f(pct.get("債券")), "cash_pct": _f(pct.get("現金/安全網")),
        "def_comb": _f((snap.get("defensive_combined_metric") or {}).get("佔比")),
        "tgt": tgt, "cap": cap, "step": step,
        "pool": pool, "loan": loan, "maint": maint,
        "line_notice": line_notice, "line_call": line_call, "line_stop": line_stop,
        "drop_stop": _drop_to(line_stop), "drop_notice": _drop_to(line_notice),
    }


def today_parts() -> dict:
    """今日帳面與分項貢獻（asset_diff 真值；含估值日）。"""
    hist = _load("asset_diff_history.json")
    dates = sorted(hist)
    if len(dates) < 2:
        return {}
    t, p = dates[-1], dates[-2]
    keys = {"total_assets": "總資產", "securities_market": "台股／證券",
            "fund_market": "基金", "insurance_current": "保單", "cash": "現金"}
    chg = {v: (_f(hist[t].get(k)) - _f(hist[p].get(k)))
           for k, v in keys.items()
           if _f(hist[t].get(k)) is not None and _f(hist[p].get(k)) is not None}
    base = _f(hist[p].get("total_assets"))
    tot = _f(hist[t].get("total_assets"))
    return {"date": t, "prev": p, "total": tot,
            "chg": chg.get("總資產"),
            "pct": ((chg["總資產"] / base * 100) if (chg.get("總資產") is not None and base) else None),
            "parts": chg}


def scenarios(a: dict, shocks=(-10.0, -20.0, -30.0)) -> list:
    """壓力測試：股票類（含高股息，不當防禦）全額受衝擊；債券／現金／黃金不動。"""
    out = []
    eq, pool, loan, total, net = a["equity"], a["pool"], a["loan"], a["total"], a["net_incl_re"]
    for s in shocks:
        loss = eq * (s / 100.0) if eq else None
        pool_after = pool * (1 + s / 100.0) if pool else None
        out.append({"label": f"股市 {int(s)}%", "loss": loss,
                    "total_after": (total + loss) if (total is not None and loss is not None) else None,
                    "net_after": (net + loss) if (net is not None and loss is not None) else None,
                    "maint_after": (pool_after / loan * 100) if (pool_after and loan) else None,
                    "cash_after": a["cash"]})
    if eq and a["bond"]:
        loss2 = eq * -0.20 + a["bond"] * -0.05
        out.append({"label": "股債同跌（股 20%／債 5%）", "loss": loss2,
                    "total_after": (total + loss2) if total is not None else None,
                    "net_after": (net + loss2) if net is not None else None,
                    "maint_after": None, "cash_after": a["cash"]})
    # 流動性壓力：股市 −20% 同時質押池同幅下跌 → 維持率惡化、回內部停止線需還本金
    if eq:
        loss3 = eq * -0.20
        pool_after = pool * 0.8 if pool else None
        maint3 = (pool_after / loan * 100) if (pool_after and loan) else None
        repay = max(0.0, loan - 0.53 * pool_after) if (pool_after and loan) else None
        out.append({"label": "流動性壓力（股 20%＋維持率惡化）", "loss": loss3,
                    "total_after": (total + loss3) if total is not None else None,
                    "net_after": (net + loss3) if net is not None else None,
                    "maint_after": maint3, "cash_after": a["cash"], "repay": repay})
    return out


def asset_class_rows(a: dict) -> list:
    """依使用者規格重新分類實際持倉（高股息＝股票收益型，不列防禦；未穿透不得假設低風險）。"""
    def row(name, examples, bucket, amt, pct, judge):
        return {"分類": name, "代表標的": examples, "口徑": bucket,
                "金額": _m(amt), "占比": _pc(pct), "防禦判定": judge}
    return [
        row("台股成長型", "0050／006208／主動台股", "台股市值型成長", a["tw"], a["tw_pct"], "成長型，非防禦"),
        row("股票收益型", "00878／0056／00919 等高股息", "防守型配息", a["defi"], a["defi_pct"],
            "不列防禦（與台股同向）"),
        row("海外股票型", "美股 ETF／美股基金", "美股市值型成長", a["us"], a["us_pct"], "成長型，非防禦"),
        row("固定收益型", "債券基金／債券 ETF", "債券", a["bond"], a["bond_pct"], "需以股債同跌情境驗證"),
        row("流動性防禦型", "現金／存款", "現金/安全網", a["cash"], a["cash_pct"], "可防禦（對比 70 萬底線）"),
        row("分散風險型", "黃金", "衛星", a["gold"],
            ((a["gold"] / a["total"] * 100) if (a["gold"] and a["total"]) else None), "衛星，避險強度以 0 計"),
    ]


def verdict(a: dict) -> dict:
    reasons, watch = [], []
    cash, floor = a["cash"], a["floor"]
    maint, line_notice, line_stop = a["maint"], a["line_notice"], a["line_stop"]
    if cash is None or maint is None:
        return {"code": VERDICT_UNKNOWN, "icon": "⚪", "text": "資料不足，無法判定（不得視為安全）",
                "reasons": ["現金或質押維持率缺值"], "watch": []}
    if floor and cash < floor:
        reasons.append(f"現金 {_m(cash)} 低於底線 {_m(floor)}")
    if maint <= line_notice:
        reasons.append(f"質押維持率 {maint:.1f}% 已到銀行通知線 {line_notice:.0f}%")
    for name, now, cap_v in (("美股", a["us_pct"], a["cap"].get("美股市值型")),
                             ("科技", a["tech_pct"], a["cap"].get("科技")),
                             ("台股", a["tw_pct"], a["cap"].get("台股市值型"))):
        if now is not None and cap_v is not None and now > float(cap_v):
            reasons.append(f"{name} {now:.1f}% 已超硬上限 {float(cap_v):.0f}%")
    if a["def_comb"] is not None and a["def_comb"] < 60:
        reasons.append(f"防守合併口徑 {a['def_comb']:.1f}% < 60%")
    if reasons:
        return {"code": VERDICT_ACT, "icon": "🔴", "text": "已觸發調整條件（需人工裁決，非自動交易）",
                "reasons": reasons, "watch": []}
    if maint <= line_stop:
        watch.append(f"維持率 {maint:.1f}% 到內部停止線 {line_stop:.0f}%（停止新增、備還本）")
    us_t = a["tgt"].get("美股市值型")
    if a["us_pct"] is not None and us_t is not None and a["us_pct"] - float(us_t) >= a["step"]:
        watch.append(f"美股 {a['us_pct']:.1f}% 超目標 {float(us_t):.0f}% 達 {a['us_pct'] - float(us_t):+.1f}pp（≥觀察 {a['step']:.0f}pp）")
    tech_t = a["tgt"].get("科技")
    if a["tech_pct"] is not None and tech_t is not None and float(tech_t) - a["tech_pct"] <= 1.0:
        watch.append(f"科技 {a['tech_pct']:.1f}% 距上限 {float(tech_t):.0f}% 僅 {float(tech_t) - a['tech_pct']:.1f}pp")
    if a["def_comb"] is not None and a["def_comb"] < 65:
        watch.append(f"防守合併 {a['def_comb']:.1f}% 低於目標水位")
    if watch:
        return {"code": VERDICT_WATCH, "icon": "🟡", "text": "HOLD：不需操作，但風險需持續監控",
                "reasons": [], "watch": watch}
    return {"code": VERDICT_HOLD, "icon": "🟢", "text": "目前配置安全，不必操作",
            "reasons": [], "watch": []}


# ────────────────────────── 渲染層 ──────────────────────────
def render(snap: dict | None = None, theme: str = "light") -> str:
    if snap is None:
        snap = _load("snapshot.json")
    a = assess(snap)
    v = verdict(a)
    tp = today_parts()
    rows = scenarios(a)
    note = 'style="color:#6e6e73;font-size:12px"'

    tone = {"維持": "#059669", "注意": "#d97706", "調整": "#dc2626"}.get(v["code"], "#6b7280")
    bg = {"維持": "#ecfdf5", "注意": "#fffbeb", "調整": "#fef2f2"}.get(v["code"], "#f9fafb")

    # ② 跑贏原因：分項歸因 + 判定（規則化，不看圖說故事）
    parts = tp.get("parts") or {}
    order = ["台股／證券", "基金", "保單", "現金"]
    parts_txt = "｜".join(f"{k} {_m(parts.get(k), True)}" for k in order if k in parts) or "—"
    equity_up = (parts.get("基金") or 0) + (parts.get("保單") or 0)
    local_dn = parts.get("台股／證券") or 0
    if local_dn < 0 and equity_up > 0:
        why = ("<b>不是防守奏效，是市場輪動。</b>今天殺的是台股（加權 "
               f"{_pct_signed(_pct_from_text((_load('daily_analysis.json').get('market') or {}).get('twii')))}），"
               "而基金與保單反映的是<b>前一交易日美股上漲</b>的淨值；你的台股比重低（"
               f"{_pc(a['tw_pct'])}）讓傷害有限，這是配置的副作用，不是避險設計。")
    elif local_dn < 0 and equity_up <= 0:
        why = "<b>防守沒有生效。</b>台股與海外部位同向下跌，代表目前配置在這次回檔中沒有提供緩衝。"
    else:
        why = "<b>全面上漲。</b>今天沒有可歸因的防守效果，漲幅來自市場本身。"

    # ③ 真正風險：最大拖累 + 三大監控
    worst = min(((k, val) for k, val in parts.items() if k != "總資產" and val is not None),
                key=lambda x: x[1], default=(None, None))
    etf = {}
    try:
        from scripts.components import book_vs_market_metrics as bvm
        etf = bvm.etf_check(["00878.TW", "0056.TW"]) or {}
        sec = bvm.secondary(snap)
    except Exception:
        sec = {}
    etf_txt = "｜".join(f"{k.replace('.TW', '')} {val}" for k, val in etf.items()) or "—"

    # 穿透引擎（獨立模組；失敗一律留缺口，不影響本卡其餘數字）
    hp_dual, hp_cov = {}, {}
    try:
        import holdings_penetration as _hp
        _hr = _hp.run(snap)
        hp_dual = _hr.get("dual") or {}
        hp_cov = _hr.get("coverage") or {}
        _c30 = (_hr.get("correlation") or {}).get("30日") or {}
        _pairs = _c30.get("相關係數") or {}
        _hd = _hr.get("hedge") or {}
        _pairs = {k: v for k, v in _pairs.items() if "現金" not in k}   # 現金為資金調度，非市場連動
        _best = sorted(_pairs.items(), key=lambda x: x[1])[:2]
        hp_corr_txt = "｜".join(f"{k} {v:+.2f}" for k, v in _best) or "資料不足"
        hp_corr_txt += f"（30 日，n={_c30.get('樣本數', '—')}）"
        if not _hd.get("資料不足"):
            _rows = _hd.get("樣本", [])
            _n = len(_rows) or 1
            hp_corr_txt += f"｜過去 {len(_rows)} 個台股下跌日中，各桶平均變動：" + \
                "、".join(f"{t} {sum((r.get(t + '_pct') or 0) for r in _rows) / _n:+.2f}%"
                          for t in ("台股／證券", "基金", "保單"))
    except Exception:
        hp_corr_txt = "資料不足"

    # ④ 壓力測試表
    cls_html = "".join(
        f"<tr><td>{c['分類']}</td><td>{c['代表標的']}</td><td>{c['金額']}</td>"
        f"<td>{c['占比']}</td><td>{c['防禦判定']}</td></tr>" for c in asset_class_rows(a))

    rows_html = ""
    for r in rows:
        mt = _pc(r["maint_after"]) if r["maint_after"] is not None else "—（池內股債比重未取得）"
        if r.get("repay"):
            mt += f"（回內部停止線需還 {_m(r['repay'])}）"
        warn = ""
        if r["maint_after"] is not None:
            gap = r["maint_after"] - a["line_call"]
            if r["maint_after"] <= a["line_call"]:
                warn = " ⚠️ 已觸及追繳線"
            elif gap <= 5:
                warn = f" ⚠️ 距追繳線僅 {gap:.1f}pp"
            elif r["maint_after"] <= a["line_notice"]:
                warn = " ⚠️ 已觸及通知線"
        cash_ok = (" ✅ ≥底線" if (r["cash_after"] and a["floor"] and r["cash_after"] >= a["floor"])
                   else (" ⚠️ 低於底線" if r["cash_after"] else ""))
        rows_html += (f"<tr><td>{r['label']}</td><td>{_m(r['loss'], True)}</td>"
                      f"<td>{_m(r['total_after'])}</td><td>{_m(r['net_after'])}</td>"
                      f"<td>{mt}{warn}</td><td>{_m(r['cash_after'])}{cash_ok}</td></tr>")

    trig = [
        f"現金 < 底線 {_m(a['floor'])}",
        f"質押維持率 ≤ 通知線 {a['line_notice']:.0f}%（目前 {_pc(a['maint'])}，池需跌 {_pc(a['drop_notice'], 2)}）",
        f"美股超硬上限 {a['cap'].get('美股市值型', '—')}% 或科技超 {a['tgt'].get('科技', '—')}%",
        "台股解凍雙閘門：US30Y < 5.30 連 2 日 ＋ 高息負債清償",
    ]
    trig_html = "".join(f"<li>{t}</li>" for t in trig)
    watch_html = ("".join(f"<li>{w}</li>" for w in v["watch"])) or "<li>無</li>"
    reason_html = ("<br>".join(f"・{r}" for r in v["reasons"]) + "<br>") if v["reasons"] else ""

    act = {
        VERDICT_HOLD: "維持 HOLD：不因單日上漲而加碼，也不因短期下跌而恐慌減碼。",
        VERDICT_WATCH: "維持 HOLD：不因單日上漲而加碼，也不因短期下跌而恐慌減碼；上列風險持續監控。",
        VERDICT_ACT: "需人工裁決（非自動交易）：下列門檻已突破，請裁示處理順序與金額。",
        VERDICT_UNKNOWN: "先補資料再判斷，不得推論為安全。",
    }.get(v["code"], "")

    twii_txt = (_load("daily_analysis.json").get("market") or {}).get("twii") or "—"
    sox_txt = (_load("daily_analysis.json").get("market") or {}).get("sox") or "—"
    sec_txt = "｜".join(x for x in [f"今日 {sec.get('today')}" if sec.get("today") else None,
                                   f"本週 {sec.get('week')}" if sec.get("week") else None,
                                   f"匯兌 {sec.get('fx')}" if sec.get("fx") else None] if x) or "—"

    return f'''<div class="card" style="border-left:6px solid {tone};background:{bg}">
<h2>🛡️ 每日資產防禦檢查（{tp.get("date") or snap.get("date") or "—"}）</h2>
<p style="font-size:15px;font-weight:800;color:{tone};margin:2px 0 2px">
{v["icon"]} {v["code"]}｜{v["text"]}</p>
<p {note}>只看四件事：今天賺賠、為什麼、風險在哪、要不要動。</p>

<h3 style="font-size:14px;margin:12px 0 4px">① 今日帳面：資產今天增加還是減少？</h3>
<table>
<tr><th style="width:26%">帳面變動</th><td><b style="color:{tone};font-size:16px">{_m(tp.get("chg"), True)}</b>
　（{_pct_signed(tp.get("pct"))}）｜總資產 {_m(tp.get("total"))}</td></tr>
<tr><th>分項貢獻</th><td>{parts_txt}</td></tr>
<tr><th>估值日</th><td>台股 {tp.get("date") or "—"} 收盤｜美股／費半 <b>前一交易日 {tp.get("prev") or "—"}</b>（T+1 反映於基金與保單淨值）</td></tr>
</table>
<p {note}>基金淨值有 T+1 時差：今日顯示的美股部位漲跌，實際是前一交易日的價格。不同交易日的數字不得當成同一天的避險效果。</p>

<h3 style="font-size:14px;margin:14px 0 4px">② 跑贏原因：防守成功，還是其他市場剛好漲？</h3>
<p style="margin:2px 0">{why}</p>
<p {note}>對照：台股加權 {twii_txt}｜費半 {sox_txt}（前一交易日）</p>

<h3 style="font-size:14px;margin:14px 0 4px">③ 真正風險：哪個資產是最大拖累？</h3>
<table>
<tr><th style="width:26%">今日最大拖累</th><td>{worst[0] or "—"}　{_m(worst[1], True) if worst[1] is not None else "—"}</td></tr>
<tr><th>美股超配</th><td><b style="color:{tone}">{_pc(a["us_pct"])}</b>（目標 {a["tgt"].get("美股市值型", "—")}%／硬上限 {a["cap"].get("美股市值型", "—")}%）＝目前最大單一風險</td></tr>
<tr><th>科技（雙口徑）</th><td><b>{_pc(a["tech_pct"])}</b>（桶口徑：美股科技桶，上限 {a["tgt"].get("科技", "—")}%）　／　<b>{_pc(hp_dual.get("GICS_pct"))}</b>（GICS 產業穿透：含台股半導體與基金間接持股）<br><span style="color:#6e6e73;font-size:12px">兩者衡量不同維度且重疊，<b>不可相加</b>；GICS 完整度 {_pc(hp_dual.get("GICS_完整度_pct"))}、資料日 {hp_dual.get("GICS_資料日") or "—"}</span></td></tr>
<tr><th>連動與歷史實測</th><td>{hp_corr_txt}<br><span style="color:#6e6e73;font-size:12px">相關性只描述同向、非因果；歷史不保證未來</span></td></tr>
<tr><th>持股穿透完整度</th><td>已穿透 {_pc(hp_cov.get("分級佔比", {}).get("已穿透"))}／部分穿透 {_pc(hp_cov.get("分級佔比", {}).get("部分穿透"))}／未穿透 {_pc(hp_cov.get("分級佔比", {}).get("未穿透"))}　<span style="color:#6e6e73;font-size:12px">未穿透不等於低風險；重複持股僅就已知商品合併</span></td></tr>
<tr><th>高股息不是防禦</th><td>防守型配息 {_pc(a["defi_pct"])} 為台股高股息 ETF，實測週跌幅：{etf_txt}（與台股同向，不列為防禦資產）</td></tr>
<tr><th>債券與現金</th><td>債券 {_pc(a["bond_pct"])}／現金 {_pc(a["cash_pct"])}；防禦效果以壓力測試驗證（下表），不看比例本身</td></tr>
<tr><th>槓桿</th><td>質押維持率 <b>{_pc(a["maint"])}</b>（借款 {_m(a["loan"])}／池 {_m(a["pool"])}）｜距內部停止線 {a["line_stop"]:.0f}% 需跌 {_pc(a["drop_stop"], 2)}｜距銀行通知 {a["line_notice"]:.0f}% 需跌 {_pc(a["drop_notice"], 2)}</td></tr>
</table>
<table>
<tr><th>資產分類（重新歸類）</th><th>代表標的</th><th>金額</th><th>占比</th><th>防禦判定</th></tr>
{cls_html}
</table>
<p {note}>配息率不等於報酬；債券可能因利率上升而下跌；未完成穿透的基金不得假設為低風險。</p>
<table>
<tr><th>下跌壓力測試</th><th>資產損失</th><th>總資產</th><th>淨值（含房產）</th><th>質押維持率</th><th>現金</th></tr>
{rows_html}
</table>
<p {note}>假設情境，不是預測。股票類 {_m(a['equity'])}（台股＋美股＋高股息，高股息不當防禦）、債券 {_m(a['bond'])}、現金 {_m(a['cash'])}；
股票全額受衝擊、債券與現金不動、借款不變、不計配息再投入；質押池以「與股市同幅」為最保守假設。</p>

<h3 style="font-size:14px;margin:14px 0 4px">④ 後續動作：維持、注意，還是需要調整？</h3>
<table>
<tr><th style="width:26%">今日行動</th><td><b style="color:{tone}">{v["code"]}</b>｜{act}{reason_html}</td></tr>
<tr><th>需要注意</th><td><ul style="margin:2px 0 2px 16px;padding:0">{watch_html}</ul></td></tr>
<tr><th>調整觸發條件</th><td><ul style="margin:2px 0 2px 16px;padding:0">{trig_html}</ul></td></tr>
</table>
<p {note}>G1／G2／G3 HOLD 未解除；本卡不產生交易授權、不自動加減碼、不解除凍結。壓力測試只供理解風險。</p>
<p {note}>次要（績效，不作判斷用）：{sec_txt}</p>
</div>'''


def render_dashboard(snap: dict | None = None, theme: str = "dark") -> str:
    """儀表板首頁版（暗色 Tailwind）：首頁摘要 ＋ 詳細分析，與日報共用同一計算。

    2026-11-05 使用者定版：不建新頁、不建平行系統；數字一律走本模組 compute。
    """
    if snap is None:
        snap = _load("snapshot.json")
    a = assess(snap)
    v = verdict(a)
    tp = today_parts()
    rows = scenarios(a)
    try:
        from scripts.components import book_vs_market_metrics as bvm
        etf = bvm.etf_check(["00878.TW", "0056.TW"]) or {}
    except Exception:
        etf = {}
    etf_txt = "｜".join(f"{k.replace('.TW', '')} {val}" for k, val in etf.items()) or "—"
    hp_dual, hp_cov = {}, {}
    try:
        import holdings_penetration as _hp
        _hr = _hp.run(snap)
        hp_dual = _hr.get("dual") or {}
        hp_cov = _hr.get("coverage") or {}
    except Exception:
        pass

    tone = {"維持": "emerald", "注意": "amber", "調整": "rose"}.get(v["code"], "slate")
    icon = v["icon"]

    def tile(label, main, sub, color="text-white"):
        return (f'<div class="bg-slate-800/50 rounded-lg p-3">'
                f'<p class="text-[11px] text-slate-400 mb-1">{label}</p>'
                f'<p class="text-lg font-black font-mono {color}">{main}</p>'
                f'<p class="text-[11px] text-slate-500">{sub}</p></div>')

    tiles = "".join([
        tile("台股", _pc(a["tw_pct"]), f'目標 {a["tgt"].get("台股市值型", "—")}%'),
        tile("美股曝險", _pc(a["us_pct"]), f'目標 {a["tgt"].get("美股市值型", "—")}%／上限 {a["cap"].get("美股市值型", "—")}%',
             "text-rose-300" if (a["us_pct"] or 0) > float(a["tgt"].get("美股市值型") or 0) else "text-white"),
        tile("科技股（雙口徑）", f'{_pc(a["tech_pct"])} ／ {_pc(hp_dual.get("GICS_pct"))}',
             f'桶口徑 ／ GICS 產業（不可相加）；上限 {a["tgt"].get("科技", "—")}%', "text-amber-300"),
        tile("股票收益型", _pc(a["defi_pct"]), "高股息：不列防禦"),
        tile("債券", _pc(a["bond_pct"]), f'{_m(a["bond"])}（防禦力看壓力測試）'),
        tile("現金＋黃金", f'{_pc(a["cash_pct"])}／{_pc((a["gold"] / a["total"] * 100) if (a["gold"] and a["total"]) else None, 2)}',
             f'底線 {_m(a["floor"])}｜{"✅ 高於底線" if (a["cash"] and a["floor"] and a["cash"] >= a["floor"]) else "⚠️ 低於底線"}'),
    ])

    rows_html = ""
    for r in rows:
        mt = _pc(r["maint_after"]) if r["maint_after"] is not None else "—"
        flag = ""
        if r["maint_after"] is not None and r["maint_after"] <= a["line_call"] + 5:
            flag = " ⚠️"
        if r.get("repay"):
            flag += f'<br><span class="text-[10px] text-amber-300">需還 {_m(r["repay"])}</span>'
        rows_html += (f'<tr><td class="py-1 text-slate-300">{r["label"]}</td>'
                      f'<td class="py-1 text-right font-mono text-rose-300">{_m(r["loss"], True)}</td>'
                      f'<td class="py-1 text-right font-mono text-slate-300">{_m(r["total_after"])}</td>'
                      f'<td class="py-1 text-right font-mono text-slate-300">{mt}{flag}</td></tr>')

    cls_dash = "".join(
        f'<tr><td class="py-0.5 text-slate-300">{c["分類"]}</td>'
        f'<td class="py-0.5 text-right font-mono">{c["占比"]}</td>'
        f'<td class="py-0.5 pl-2">{c["防禦判定"]}</td></tr>' for c in asset_class_rows(a))
    watch_html = "".join(f'<li>{w}</li>' for w in v["watch"]) or "<li>無</li>"
    act = {
        VERDICT_HOLD: "維持 HOLD：不因單日上漲加碼、不因短期下跌恐慌減碼。",
        VERDICT_WATCH: "維持 HOLD：風險需監控，未達觸發條件前不動。",
        VERDICT_ACT: "需人工裁決（非自動交易）：門檻已突破。",
        VERDICT_UNKNOWN: "先補資料再判斷。",
    }.get(v["code"], "")

    return f'''<div class="luxury-card p-6" id="defense-center" style="border:1px solid #334155">
  <div class="flex justify-between items-start flex-wrap gap-2 mb-3">
    <div>
      <h3 class="text-md font-bold text-white flex items-center gap-2">🛡️ 資產防護中心
        <span class="text-xs font-normal text-slate-400">與日報共用同一計算模組</span></h3>
      <p class="text-xs text-slate-400">首頁摘要｜最大風險｜現金底線｜壓力測試｜今日行動（只顯示，不觸發交易）</p>
    </div>
    <span class="text-xs px-3 py-1 rounded-full font-mono font-bold border border-{tone}-500/40 bg-{tone}-500/10 text-{tone}-300">{icon} {v["code"]}</span>
  </div>

  <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-3">{tiles}</div>

  <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
    <div class="bg-slate-800/40 rounded-lg p-3">
      <p class="text-[11px] text-slate-400 mb-1">真正的防禦能力（不看比例，看實測）</p>
      <p class="text-xs text-slate-300 leading-relaxed">
        ・高股息 <b>{_pc(a["defi_pct"])}</b>＝股票收益型，<b>不列入防禦</b>（週跌幅 {etf_txt}）<br>
        ・債券 <b>{_pc(a["bond_pct"])}</b>：只看股債同跌情境下的實際損失（右下表）<br>
        ・現金 <b>{_m(a["cash"])}</b>：對比底線 {_m(a["floor"])}，{"✅ 充足" if (a["cash"] and a["floor"] and a["cash"] >= a["floor"]) else "⚠️ 不足"}<br>
        ・黃金 <b>{_pc((a["gold"] / a["total"] * 100) if (a["gold"] and a["total"]) else None, 2)}</b>（衛星，計入避險強度時以 0 計）
      </p>
      <p class="text-[11px] text-slate-500 mt-2">最大風險來源：美股 {_pc(a["us_pct"])}（超目標 {_pp((a["us_pct"] or 0) - float(a["tgt"].get("美股市值型") or 0))}）</p>
      <table class="w-full text-[11px] mt-2 text-slate-400"><tbody>{cls_dash}</tbody></table>
    </div>
    <div class="bg-slate-800/40 rounded-lg p-3">
      <p class="text-[11px] text-slate-400 mb-1">下跌壓力測試（假設，非預測）</p>
      <table class="w-full text-xs"><tbody>{rows_html}</tbody></table>
      <p class="text-[11px] text-slate-500 mt-1">股票類含高股息；質押池假設與股市同幅。借款 {_m(a["loan"])}／池 {_m(a["pool"])}（維持率 {_pc(a["maint"])}）。</p>
    </div>
  </div>

  <div class="mt-3 bg-slate-800/40 rounded-lg p-3">
    <p class="text-[11px] text-slate-400 mb-1">下一步</p>
    <p class="text-sm font-bold text-white">{icon} {v["code"]}｜{act}</p>
    <ul class="text-xs text-slate-300 mt-1 ml-4 list-disc">{watch_html}</ul>
    <p class="text-[11px] text-slate-500 mt-2">估值日：台股 {tp.get("date") or "—"}｜美股／費半前一交易日 {tp.get("prev") or "—"}（T+1 時差）。
    不同曝險維度（美股 {_pc(a["us_pct"])} 與科技 {_pc(a["tech_pct"])}）會重疊，不可相加。G1／G2／G3 HOLD 未解除，風險監控不等於交易授權。</p>
  </div>
</div>'''


def _main() -> int:
    print(render())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
