#!/usr/bin/env python3
"""report_components.py — 龍九報表共享渲染組件（2026-08-27 建立）

目的：消除「同一分析多處各自渲染 → 數字/格式不一致」。
原則：所有報表（日報/儀表板/週報/再平衡/穿透/緊急應變）呼叫同一組件 → 改格式只改 1 處。

組件（全部只讀 snapshot.json / schedule_events.json，無副作用，可被任意報表 import）：
- render_penetration_card(snap)  → 穿透五桶卡（HTML 片段）
- render_coverage(snap, mode)    → 覆蓋率文字（mode: passive=被動保守 100,000 / full=含薪水）
- render_status_line(repo)       → 今日狀態列（今日 + 近3天 + 下一個，讀 schedule_events）
- render_health_score(snap)      → 健康度分數 0-100（六維度加權）+ 燈號

用法：from report_components import render_penetration_card, ...
"""
import json
from datetime import date, timedelta
from pathlib import Path
from sot_targets import (sot_monthly_expense, sot_monthly_income,  # INC-270 月支出／月收入單一入口
                         cash_floor as _cf_fn)  # 2026-10-04 P0延伸：現金底線單一入口


# ═══════════════ 穿透五桶卡 ═══════════════
def render_penetration_card(snap: dict, title: str = "📊 資產穿透") -> str:
    """穿透五桶卡（HTML 片段）。7 個報表共用 — 改格式只改這裡。"""
    pen = snap.get("penetration", {})
    at = pen.get("actual_pct", {}) or {}
    tw = at.get("台股市值型成長", 0)
    us = at.get("美股市值型成長", 0)
    df = at.get("防守型配息", 0)
    bd = at.get("債券", 0)
    ca = at.get("現金/安全網", 0)
    total = snap.get("total_assets", 0)
    rows = [
        ("台股", tw, "#2563eb"),
        ("美股", us, "#7c3aed"),
        ("防守", df, "#059669"),
        ("債券", bd, "#b45309"),
        ("現金", ca, "#64748b"),
    ]
    bars = "".join(
        f'<div style="margin:3px 0"><span style="font-size:11px;color:#6e6e73;width:34px;display:inline-block">{n}</span>'
        f'<span style="display:inline-block;width:{max(p*4, 2):.1f}%;min-width:2px;max-width:100%;height:10px;'
        f'background:{c};border-radius:3px;vertical-align:middle"></span>'
        f'<span style="font-size:11px;color:#1f2937;margin-left:6px"><b>{p:.1f}%</b></span></div>'
        for n, p, c in rows
    )
    return (
        f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px;margin:8px 0">'
        f'<div style="font-weight:800;color:#111827;margin-bottom:6px">{title}（總資產 {total:,.0f}）</div>{bars}</div>'
    )


# ═══════════════ 覆蓋率 ═══════════════
def render_coverage(snap: dict, mode: str = "passive") -> str:
    """覆蓋率文字。mode=passive：被動保守（配息 100,000+房租）；mode=full：含薪水常態。
    2026-08-25 定案：日報主顯示用 passive（保守口徑）。"""
    expense = sot_monthly_expense(snap)
    # 2026-10-04 P0（PEND-20261004-02）：原 `rent_monthly_total, 80100` 與 `dividend_month_expected or 100000`
    # 為同型假真值（且兩常數恰好等於現行真值 → 毫無症狀）。缺真值一律不予判斷，禁以常數救場。
    _rent_v = snap.get("rent_monthly_total")
    _dme_v = snap.get("dividend_month_expected")
    if mode == "full":
        income = sot_monthly_income(snap)  # 2026-10-04 P0：原 fallback 214,685 為舊口徑假真值
        label = "含薪水常態"
    else:
        _miss = [k for k, v in (("rent_monthly_total", _rent_v),
                                ("dividend_month_expected", _dme_v)) if v in (None, "")]
        if _miss:
            return (f"⚠️ 現金流覆蓋（被動保守）：缺真值（{'、'.join(_miss)}）"
                    "→ 不予判斷（禁以 100,000／80,100 救場）")
        income = float(_dme_v) + float(_rent_v)
        label = "被動保守"
    cov = income / expense * 100 if expense else 0
    light = "🟢" if cov >= 100 else ("🟡" if cov >= 80 else "🔴")
    return f"{light} 現金流覆蓋（{label}）{income:,.0f}/{expense:,.0f} = {cov:.0f}%"


# ═══════════════ 今日狀態列 ═══════════════
def render_status_line(repo: Path, sep: str = "<br>") -> str:
    """今日狀態列：今日 + 近3天 + 下一個（讀 schedule_events）。
    sep='<br>' 給儀表板（多行）；sep=' | ' 給日報（單行）。"""
    try:
        _evs = json.loads((Path(repo) / "schedule_events.json").read_text(encoding="utf-8"))
        if isinstance(_evs, dict):
            _evs = _evs.get("events", _evs.get("items", []))
        _td = date.today().isoformat()
        _ACT = ("🔴", "📞", "📋", "📡", "🏦", "🔍", "📅")
        _today_act = [e for e in _evs if str(e.get("date", "")) == _td and str(e.get("item", "")).startswith(_ACT)]
        _soon3 = sorted([e for e in _evs if _td < str(e.get("date", "")) <= (date.today() + timedelta(days=3)).isoformat() and str(e.get("item", "")).startswith(_ACT)],
                        key=lambda x: str(x.get("date", "")))
        _next = sorted([e for e in _evs if _td < str(e.get("date", "")) <= (date.today() + timedelta(days=7)).isoformat() and str(e.get("item", "")).startswith(_ACT)],
                       key=lambda x: str(x.get("date", "")))
        parts = []
        if _today_act:
            for e in _today_act[:2]:
                parts.append(f"🔴 今日要做：{str(e.get('item', ''))[:48]}")
        else:
            parts.append("🟢 今日無需操作")
        if _soon3:
            _d3 = " ｜ ".join(f"{str(e.get('date', ''))[5:]} {str(e.get('item', ''))[:26]}" for e in _soon3[:3])
            parts.append(f"📌 近 3 天：{_d3}")
        if _next:
            _n = next((e for e in _next if str(e.get("date", "")) > (date.today() + timedelta(days=3)).isoformat()), None) or _next[0]
            parts.append(f"⏭ 下一個：{str(_n.get('date', ''))[5:]} {str(_n.get('item', ''))[:44]}")
        return sep.join(parts)
    except Exception:
        return "🟢 今日無需操作"


# ═══════════════ 健康度分數 ═══════════════
def _num(v, default=0):
    """相容取值：dict/list → 第一個數值；str → float；其他 → default"""
    if isinstance(v, dict):
        v = next((x for x in v.values() if isinstance(x, (int, float))), default)
    elif isinstance(v, list):
        v = next((x for x in v if isinstance(x, (int, float))), default)
    try:
        return float(v)
    except Exception:
        return default


def render_health_score(snap: dict) -> dict:
    """健康度分數 0-100（四維度加權）→ (分數, 燈號, 明細)。
    2026-08-27 定版：覆蓋30/防禦25/曝險20/現金15/LTV10（US30Y 為市場環境，非個人健康指標 → 移除計分）。
    2026-10-07 裁決①：美元曝險已裁定「僅顯示、不觸發資產調整」→ 移出計分（原 20% 權重併入防禦）。
    現行權重：覆蓋30/防禦45/現金15/LTV10；曝險僅在明細顯示供參考。"""
    expense = sot_monthly_expense(snap)
    # 2026-10-04 P0（PEND-20261004-02）：同 render_coverage——缺真值不得靠預設值計分。
    _rent_h = snap.get("rent_monthly_total")
    _dme_h = snap.get("dividend_month_expected")
    _rent_h = float(_rent_h) if _rent_h not in (None, "") else None
    _dme_h = float(_dme_h) if _dme_h not in (None, "") else None
    income = (_dme_h + _rent_h) if (_dme_h is not None and _rent_h is not None) else None
    income_act = (float(snap.get("monthly_dividend_total", 0) or 0) + _rent_h
                  if _rent_h is not None else None)
    cov = (income / expense * 100) if (income is not None and expense) else None
    cov_act = (income_act / expense * 100) if (income_act is not None and expense) else None

    # 現金流覆蓋（2026-09-13 修正：>=100% 即為 100 分，100%~150% 為超額加分區間）
    # 2026-10-04 P0：缺真值 → 該維度 0 分（fail-closed：不得靠預設值拿分）
    if cov is None:
        _cov_std = 0
    elif cov >= 100.0:
        _cov_std = min(100, int(90 + (cov - 100.0) / 50.0 * 10))  # 100%給90分，150%以上給100分
    else:
        _cov_std = max(0, int(cov / 100.0 * 90))

    # 防禦維度（雙維度框架 8/21：情境門檻）— 讀「佔比」，含 ±3% 公差與分階段計分
    ddm = snap.get("dual_dimension_metric", {})
    _dd_def = ddm.get("防禦維度", ddm.get("防禦", {})) if isinstance(ddm, dict) else {}
    try:
        defense = float(_dd_def.get("佔比", _dd_def.get("合計", 53.9)))
    except Exception:
        defense = 53.9
    # 分階段計分：目標 50%，公差 ±3% (47%~53% 滿分 100)；偏離每 1% 扣 10 分，最低 0 分
    if 47.0 <= defense <= 53.0:
        def_score = 100
    elif defense < 47.0:
        def_score = max(0, int(100 - (47.0 - defense) * 10))
    else:
        def_score = max(0, int(100 - (defense - 53.0) * 10))

    # 美元曝險：2026-10-07 使用者裁決① —— 本項已裁定「僅顯示、不觸發資產調整」，
    # 故不再作為健康度扣分項（原權重 20%／原以 60% 當基準線性扣分＝政策與評分系統矛盾）。
    # 這不是美化分數，而是移除已被政策取消的觸發語意；真值仍讀出供明細參考（不計分）。
    _usd_m = snap.get("usd_exposure_monitor", {}).get("current", {})
    if isinstance(_usd_m, dict):
        usd = _num(_usd_m.get("合計", _usd_m.get("美股桶", 54)), 54)
    else:
        usd = _num(_usd_m, 54)
    usd_score = None   # 不計分（2026-10-07 裁決①；原 20% 權重併入防禦維度）

    # 現金底線（70萬）
    # 2026-09-29 CIO major：健康度現金維度一律看可動用（扣質押撥款指定清償款），否則評分端 fail-open
    from sot_targets import restricted_cash as _rst_fn
    cash = max(0.0, _num(snap.get("cash_total", 0), 0) - _rst_fn(snap))
    floor = _cf_fn(snap)  # 2026-10-04 P0延伸：現金底線單一入口（原雙重 700,000 fallback）
    cash_score = 100 if cash >= floor else 0

    # LTV（2026-09-05 定版口徑1：質押借款/擔保品現值 — 讀 snapshot 真值，移除寫死 20.4）
    # 2026-09-29 擴充：加入國泰基金質押 fund_pledge_loan（590萬@2.65%，9/29 10:57 撥款）。
    # 借分子與擔保品分母（質押基金池市值）必須同時計入，否則整體槓桿會被低估。
    # 質押借款 = 保單質押 policy_pledge_loan(400萬@4%) + 券商質押 pledge_loan(100萬@3.92%)
    #            + 國泰基金質押 fund_pledge_loan(590萬@2.65%)
    # 擔保品現值 = 保單現值 insurance_current_value + 證券市值 securities.total_market_value
    #              + 質押基金池市值（cathay_pledge_0911.擔保池.合計）
    # 2026-10-04 P0（CIO 五審 M2）：質押借款三鍵原為 `or 0`——缺真值時分子少算 590 萬，
    # LTV 由 24.4%→0.0%、銀行 LTV 由 50.1%→0.0%（**看起來更健康**），且健康度仍 93 🟢、無任何缺真值標記。
    # 缺鍵 → 值為「未知」→ LTV 系列一律 None（不與 0 混淆），該維度 0 分。
    def _num1(v):
        return float(v) if v not in (None, "") else None
    _fund_pledge = _num1(snap.get("fund_pledge_loan"))
    _fund_pool = _num1(((snap.get("cathay_pledge_0911") or {}).get("擔保池") or {}).get("合計"))
    _pol_pl = _num1(snap.get("policy_pledge_loan"))
    _sec_pl = _num1(snap.get("pledge_loan"))
    _pl_missing = [n for n, v in (("policy_pledge_loan", _pol_pl), ("pledge_loan", _sec_pl),
                                  ("fund_pledge_loan", _fund_pledge)) if v is None]
    _pl_loan = sum(v for v in (_pol_pl, _sec_pl, _fund_pledge) if v is not None)
    _pl_col = (float(snap.get("insurance_current_value") or 0)
               + float((snap.get("securities") or {}).get("total_market_value") or 0)
               + (_fund_pool or 0))
    ltv = None if _pl_missing else ((_pl_loan / _pl_col * 100) if _pl_col > 0 else 0.0)
    # 銀行口徑（國泰監看這條）：基金質押借款 ÷ 質押基金池市值
    _bank_ltv = (None if _fund_pledge is None
                 else ((_fund_pledge / _fund_pool * 100) if _fund_pool else 0.0))
    _pl_total_asset = float(snap.get("total_assets") or 0)
    _pl_ratio_total = None if _pl_missing else (
        (_pl_loan / _pl_total_asset * 100) if _pl_total_asset > 0 else 0.0)
    # 健康線 ≤50（2026-09-05 修正：35% 屬「總質押率(借款÷總資產)」制，勿誤貼到擔保品 LTV；LTV 目標依銀行鏈 50起/55黃/60紅/70追繳 與穿透情境 ≤52 一致）
    # 2026-10-04 P0（CIO 五審 M2）：ltv 可為 None（缺真值）→ 該維度 0 分，不得靠少算的分子拿分
    ltv_score = 0 if ltv is None else (100 if ltv <= 50 else (50 if ltv <= 60 else 0))

    # 2026-10-04 P0（CIO 四審 R2）：本顆已把 cov 改為可為 None（缺真值），但漏改此行 →
    # 缺鍵時 TypeError（sync_all 的組件自測會崩）。缺真值時該維度以 0 計分（fail-closed：不靠預設值拿分）。
    score = round((min(cov / 150 * 100, 100) if cov is not None else 0) * 0.30 + def_score * 0.45 + cash_score * 0.15 + ltv_score * 0.10)
    # 2026-10-07 裁決①：權重＝覆蓋30／防禦45（原25＋美元曝險20併入）／現金15／LTV10
    light = "🟢" if score >= 80 else ("🟡" if score >= 60 else "🔴")
    # 2026-09-29 CIO minor：現金跌破底線屬紅線（不可只 −15 分仍顯示 77 🟡）→ 強制 🔴 且總分上限 55
    if cash_score == 0:
        score = min(score, 55)
        light = "🔴"
    # 標準分 = 各維度 0-100 制原始得分；權重分 = 標準分 × 權重（加總 = 總分）
    _cov_std = round(min(cov / 150 * 100, 100)) if cov is not None else 0
    detail = {
        "分數": score, "燈號": light,
        "覆蓋": round(cov) if cov is not None else None,
        "覆蓋實收": round(cov_act) if cov_act is not None else None,
        "覆蓋標準": _cov_std, "覆蓋分": round(_cov_std * 0.30),
        "覆蓋缺真值": cov is None,
        "防禦": defense, "防禦標準": def_score, "防禦分": round(def_score * 0.45),
        "曝險": usd, "曝險標準": None, "曝險分": None, "曝險計分": False,
        "現金": cash, "現金標準": cash_score, "現金分": cash_score * 0.15,
        "支出": expense, "收入": income,
        "LTV": ltv, "LTV標準": ltv_score, "LTV分": ltv_score * 0.10,
        "LTV缺真值": bool(_pl_missing),
        "銀行LTV": _bank_ltv,
        "總質押率": _pl_ratio_total,
    }
    return detail

# 2026-10-02 裁示：健康度綜合分數（0-100）不再顯示；保留供歷史查看。

def _render_health_card_legacy(snap: dict) -> str:
    """健康度卡（HTML 片段）— 儀表板/日報共用。"""
    d = render_health_score(snap)
    # 防禦維度：可能是金額（>100）→ 顯示「充足」避免怪數字
    _def_txt = f"{d['防禦']:.0f}%" if d["防禦"] <= 100 else "✅ 充足"
    # (名稱, 現況, 目標, 權重分/權重) — 現況 vs 目標 → 得分
    # 2026-10-07 裁決②：政策門檻唯一來源（usd_advisory.policy ← thresholds.美元曝險_pct）
    from usd_advisory import tier_limit_text as _usd_tl
    rows = [
        ("現金流覆蓋",
         (f"{d['覆蓋']}%／實收 {d['覆蓋實收']}%" if d.get("覆蓋") is not None
          else "⚠️ 缺真值（該維度不計分）"),
         "≥100%", d["覆蓋分"], 30),
        ("防禦維度", _def_txt, "≥50%", d["防禦分"], 45),
        ("美元曝險", f"{d['曝險']:.1f}%", f"{_usd_tl(snap)}（僅顯示、不計分）", "—", 0),
        ("現金底線", f"{d['現金']:,.0f}", "≥700,000", d["現金分"], 15),
        ("LTV",
         (f"{d['LTV']:.1f}%／銀行 {d['銀行LTV']:.1f}%" if d.get("LTV") is not None
          else "⚠️ 缺真值（該維度不計分）"),
         "≤50%（質押/擔保品）", d["LTV分"], 10),
    ]
    bar = "".join(
        (f'<div style="display:flex;justify-content:space-between;font-size:11px;margin:2px 0">'
         f'<span style="color:#6e6e73">{n}</span><span style="color:#1f2937">{v}（目標 {t}）<b>{p}/{w}</b></span></div>'
         if w else
         f'<div style="display:flex;justify-content:space-between;font-size:11px;margin:2px 0">'
         f'<span style="color:#6e6e73">{n}</span><span style="color:#6e6e73">{v}（{t}）</span></div>')
        for n, v, t, p, w in rows
    )
    _weak = []
    if d["現金標準"] == 0:
        _weak.append("現金跌破底線")
    if d.get("LTV分", 10) < 10:
        _weak.append("質押LTV")
    _weak_txt = (("唯一弱項：" + "、".join(_weak)) if _weak
                 else "各計分維度全數達標（美元曝險僅顯示、不計分）")
    # 2026-09-30 CIO minor：月支出補「現金扣帳／帳上計息」拆解與過渡期口徑標註（利息動態化後）
    _li_txt = ""
    try:
        from sot_targets import liability_interest as _li_fn2
        _li2 = _li_fn2(snap)
        _cashout = float(snap.get("monthly_expense_cash") or 0)
        _accr = float(snap.get("monthly_expense_accrual") or 0)
        _pol2, _sec2, _fd2 = (_li2["保單借貸利息"], _li2["券商質押利息"], _li2["基金質押利息"])
        if None in (_pol2, _sec2, _fd2):
            # 2026-10-04 P0（PEND-20261004-02）：缺利率 → 明示缺真值；
            # 禁以預設利率（4.0／3.92／2.65%）算出的數字混充（原為 silent except → _li_txt=""）
            _li_txt = (f'（現金扣帳 {_cashout:,.0f} ＋ 帳上計息 {_accr:,.0f}）'
                       f'｜⚠️ 負債利率缺真值（{"、".join(_li2.get("_缺真值") or [])}）'
                       f'→ 三項利息不顯示、不以預設利率頂替')
        else:
            _li_txt = (f'（現金扣帳 {_cashout:,.0f} ＋ 帳上計息 {_accr:,.0f}＝保單 {_pol2:,}'
                       f'＋券商 {_sec2:,}＋基金質押 {_fd2:,}）')
            if _pol2 > 0:
                _li_txt += (f'｜過渡期口徑：含待清償保單息 {_pol2:,}，清完後月支出 '
                            f'{float(d["支出"]) - float(_pol2):,.0f}')
    except (TypeError, ValueError, ImportError):
        _li_txt = ""
    # 2026-10-04 P0：口徑說明原寫死「配息100,000+房租80,100=180,100」——同型硬編碼真值，改由 snapshot 派生
    _n_dme = snap.get("dividend_month_expected")
    _n_rent = snap.get("rent_monthly_total")
    _n_dme_txt = f"{int(_n_dme):,}" if _n_dme not in (None, "") else "⚠️ 缺真值"
    _n_rent_txt = f"{int(_n_rent):,}" if _n_rent not in (None, "") else "⚠️ 缺真值"
    _n_inc_txt = (f"{int(_n_dme) + int(_n_rent):,}"
                  if (_n_dme not in (None, "") and _n_rent not in (None, "")) else "⚠️ 缺真值")
    # 2026-10-04 P0（CIO 五審 M2）：LTV 系列可為 None（缺真值）→ 口徑說明須明示，不得印 None 或崩潰
    _n_ltv = (f"{d['LTV']:.1f}%" if d.get("LTV") is not None else "⚠️ 缺真值")
    _n_bltv = (f"{d['銀行LTV']:.1f}%" if d.get("銀行LTV") is not None else "⚠️ 缺真值")
    _n_prt = (f"{d['總質押率']:.1f}%" if d.get("總質押率") is not None else "⚠️ 缺真值")
    _note = (f'<div style="font-size:9.5px;color:#14532d;margin-top:2px;line-height:1.6">'
             f'口徑：覆蓋=保守常態（配息{_n_dme_txt}+房租{_n_rent_txt}={_n_inc_txt}）÷每月固定支出 {d["支出"]:,.0f}{_li_txt}（snapshot.dividend_month_expected+rent_monthly_total÷monthly_expense，缺鍵即示缺真值不代數）｜'
             f'防禦=dual_dimension_metric.防禦維度.佔比（{d["防禦"]:.1f}%）｜曝險=usd_exposure_monitor.current.合計（{d["曝險"]:.1f}%，2026-10-07 裁決：僅顯示、不計分）｜'
             f"現金=可動用（cash_total−指定用途款）{d['現金']:,.0f}≥cash_floor 700,000｜LTV=(policy_pledge_loan+pledge_loan+fund_pledge_loan)÷(insurance_current_value+securities+質押基金池)（{_n_ltv}；目標≤50；銀行監看50起/55黃/60紅/70追繳）｜銀行口徑 LTV＝國泰質押借款÷質押基金池＝{_n_bltv}｜總質押率 {_n_prt}（借款÷總資產，≤35%制）</div>")
    return (
        f'<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:10px;padding:12px;margin:8px 0">'
        f'<div style="font-weight:800;color:#14532d;margin-bottom:4px">🩺 龍九健康度：<span style="font-size:16px">{d["分數"]}/100</span> {d["燈號"]}</div>'
        f'{bar}'
        f'<div style="font-size:10.5px;color:#166534;margin-top:4px">{_weak_txt}</div>{_note}</div>'
    )


if __name__ == "__main__":
    # 自測
    snap = json.loads((Path(__file__).resolve().parent / "snapshot.json").read_text(encoding="utf-8"))
    print(render_penetration_card(snap)[:200])
    print(render_coverage(snap, "passive"))
    print(render_coverage(snap, "full"))
    print(render_status_line(Path(__file__).resolve().parent, sep=" | "))
    print(render_health_score(snap))


# ════════════════════════════════════════════════════════════════════════════
# 決策核心顯示（使用者 2026-10-02 裁示 第 1 批）
#   目標：每天只看「GO/WAIT ＋ 今天有沒有事」；其餘數字退到第二層。
# ════════════════════════════════════════════════════════════════════════════

def render_decision_banner(snap: dict) -> str:
    """首頁決定卡：自由現金三層 ＋ 留停 Gate 三燈 ＋ 今日動作（觸發器單一入口）。"""
    from sot_targets import cash_mode as _cm, sabbatical_gate as _gt, triggers as _tr
    from sot_targets import cash_need_90d as _cn
    cm, gt, tr = _cm(snap), _gt(snap), _tr(snap)
    from pending_engine import pending_line as _pl
    try:
        _pend = _pl()
    except Exception as _pend_e:
        _pend = "📌 Pending：無法判定（" + str(_pend_e) + "）"
    try:
        _nd = _cn(snap)
    except Exception as _nd_e:
        _nd = {"覆蓋率_pct": None, "可動用": cm["可動用"], "門檻_pct": 100,
               "A_已確認": {"合計": 0}, "錯誤": str(_nd_e)}
    _nd_pct = ("{:.1f}%".format(_nd["覆蓋率_pct"]) if _nd.get("覆蓋率_pct") is not None else "—")
    _nd_ok = isinstance(_nd.get("覆蓋率_pct"), (int, float)) and _nd["覆蓋率_pct"] >= (_nd.get("門檻_pct") or 100)
    _nd_color = "text-emerald-300" if _nd_ok else "text-amber-300"
    _mc = {"green": "text-emerald-300", "amber": "text-amber-300", "red": "text-rose-300"}[cm["燈號"]]
    # 現金口徑自我說明（2026-10-02 使用者「維持」裁示）：總現金含指定款，與可動用分開揭露
    _cl = (snap or {}).get("cash_layers") or {}
    _cash_total = float(_cl.get("cash_total") or 0)
    _cash_restricted = float((_cl.get("restricted_cash") or {}).get("total") or 0)
    _rows = "".join(
        '<div class="flex items-center justify-between gap-2 py-0.5">'
        '<span class="text-slate-300">{} {}</span>'
        '<span class="font-bold {}">{}</span></div>'.format(
            "🟢" if g["通過"] else "🔴", g["名稱"],
            "text-emerald-300" if g["通過"] else "text-rose-300", g["顯示"])
        for g in gt["gate"])
    _fired = [x for x in tr["列表"] if x["觸發"] is True]
    if _fired:
        _act = "".join('<div class="py-0.5">・<b>{}</b> {} → {}</div>'.format(
            x["項目"], x["現值"], x["動作"]) for x in _fired[:5])
    else:
        _act = '<div class="py-0.5 text-emerald-300 font-bold">今日無需動作</div>'
    _unknown = ("".join('<span class="text-slate-400">{}（待補真值）</span>'.format(u)
                        for u in tr["未建真值"]) if tr["未建真值"] else "")
    _go = gt["判定"] == "GO"
    return (
        '<div class="mb-4 p-4 rounded-xl bg-slate-900/80 border border-emerald-700/60">'
        '<div class="flex items-center justify-between flex-wrap gap-2 mb-3">'
        '<div class="text-base font-black text-white">🧭 龍九｜CEO 決定卡</div>'
        '<div class="text-xs px-2 py-1 rounded border {}">留停 Gate：{}</div></div>'
        '<div class="grid grid-cols-1 md:grid-cols-3 gap-3">'
        '<div class="rounded-lg bg-slate-800/50 p-3">'
        '<div class="text-[11px] text-slate-400 mb-1">現金三層（可動用＝唯一真值）</div>'
        '<div class="text-xl font-black {}">{:,.0f}</div>'
        '<div class="text-[11px] text-slate-400 leading-relaxed">底線 {:,.0f}｜餘裕 {:,.0f}<br>'
        '模式：<b class="{}">{}</b>（距自由現金門檻 {:,.0f}）<br>'
        '<span class="text-slate-500">總現金 {:,.0f} ＝ 可動用 {:,.0f} ＋ 指定款 {:,.0f}'
        '（國泰保留／洲際W 預繳，依 10/02 裁示不釋放）</span></div></div>'
        '<div class="rounded-lg bg-slate-800/50 p-3">'
        '<div class="text-[11px] text-slate-400 mb-1">留停 Gate（三條硬門檻）</div>'
        '<div class="text-xs">{}</div>'
        '<div class="text-[11px] text-slate-400 mt-1 leading-relaxed">'
        '參考指標（不參與判定）：保守覆蓋 {}%｜3 個月趨勢：{}</div></div>'
        '<div class="rounded-lg bg-slate-800/50 p-3">'
        '<div class="text-[11px] text-slate-400 mb-1">今日動作（{} 項觸發）</div>'
        '<div class="text-xs leading-relaxed">{}</div>'
        '<div class="text-[10px] text-slate-500 mt-1">{}{}</div>'
        '<div class="text-[11px] text-slate-200 mt-1">{}</div></div>'
        '<div class="rounded-lg bg-slate-800/50 p-3">'
        '<div class="text-[11px] text-slate-400 mb-1">未來 90 天現金需求（A｜已確認）</div>'
        '<div class="text-xl font-black {}">{}</div>'
        '<div class="text-[11px] text-slate-400 leading-relaxed">'
        '可動用 {:,.0f} ÷ 已確認 {:,.0f}（門檻 {:,.0f}%）<br>'
        '被動收入僅作參考，不參與此 Gate。</div></div></div>'
        '<div class="text-[10px] text-slate-500 mt-2">'
        '可動用＝cash_layers.unrestricted_cash；穿透桶「現金/安全網」（＋589 在途／未對帳差異）'
        '不參與 Gate／覆蓋率／投資決策。</div></div>'
    ).format(
        ("border-emerald-500/40 bg-emerald-500/10 text-emerald-300" if _go
         else "border-amber-500/40 bg-amber-500/10 text-amber-300"),
        gt["燈號"], _mc, cm["可動用"], cm["底線"], cm["餘裕"], _mc, cm["模式"], cm["距門檻"],
        _cash_total, cm["可動用"], _cash_restricted,
        _rows, gt["參考指標"]["保守覆蓋_pct"], gt["參考指標"]["3個月趨勢"],
        tr["觸發數"], _act, tr["授權邊界"], ("｜" + _unknown) if _unknown else "", _pend,
        _nd_color, _nd_pct, _nd["可動用"], (_nd.get("A_已確認") or {}).get("合計") or 0,
        _nd.get("門檻_pct") or 100)


def render_health_card(snap: dict) -> str:
    """決策核心卡（取代 93 分健康度）：Gate 三條 ＋ 參考指標，不再顯示綜合分數。"""
    from sot_targets import cash_mode as _cm, sabbatical_gate as _gt
    gt, cm = _gt(snap), _cm(snap)
    _rows = "".join(
        '<tr><td>{} {}</td><td class="num">{}</td><td>{}</td></tr>'.format(
            "🟢" if g["通過"] else "🔴", g["名稱"], g["顯示"],
            "通過" if g["通過"] else "未達") for g in gt["gate"])
    return (
        '<div class="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 mb-4">'
        '<div class="font-black text-white mb-2">🎯 留停 Gate（三條硬門檻｜{}）</div>'
        '<table class="w-full text-xs"><tr><th>門檻</th><th>現況</th><th>判定</th></tr>{}</table>'
        '<div class="text-[11px] text-slate-400 mt-2 leading-relaxed">'
        '參考指標（不參與 GO/WAIT）：保守覆蓋 {}%｜當月實收覆蓋 {}%｜3 個月趨勢：{}<br>'
        '現金模式：<b>{}</b>｜可動用 {:,.0f}（底線 {:,.0f}、餘裕 {:,.0f}）<br>'
        '<span class="text-slate-500">2026-10-02 裁示：取消 B 級與健康度分數敘事，'
        '保留原始指標供歷史查看。</span></div></div>'
    ).format(gt["燈號"], _rows, gt["參考指標"]["保守覆蓋_pct"],
             gt["參考指標"]["當月實收覆蓋_pct"], gt["參考指標"]["3個月趨勢"],
             cm["模式"], cm["可動用"], cm["底線"], cm["餘裕"])


# ════════════════════════════════════════════════════════════════════════════
# 顯示層靜默過濾（第 2 批｜使用者 2026-10-02 裁示②）
#   落在「可接受範圍」內的桶：不得出現「缺口 ±X.Xpp／還差／不足／低於目標／建議增加／
#   需再平衡／距離目標」等行動文字；範圍外原樣保留。**只改顯示文字，數字與決策邏輯不動。**
# ════════════════════════════════════════════════════════════════════════════
import re

_BAND_ALIAS = {
    "台股市值型成長": ("台股市值型", "台股"),
    "美股市值型成長": ("美股市值型", "美股"),
    "防守型配息": ("防守型配息", "防守", "防禦"),
    "債券": ("債券",),
    "科技": ("科技", "高科技"),
}
_BAND_BAD = ("缺口", "還差", "不足", "低於目標", "建議增加", "需再平衡", "距離目標")


def band_filter(text: str, snap: dict | None = None) -> str:
    """把「範圍內」桶的缺口／行動字樣自顯示文字移除；範圍外與所有數字原樣保留。

    snap 未給時自讀 snapshot.json（給呼叫端零負擔的注入方式）。
    """
    if snap is None:
        try:
            import json as _json

            snap = _json.loads((Path(__file__).resolve().parent / "snapshot.json").read_text(encoding="utf-8"))
        except Exception:
            return text
    try:
        from sot_targets import acceptable_band

        bands = acceptable_band(snap)
    except Exception:
        return text
    out = text
    for name, b in bands.items():
        if b.get("顯示行動"):
            continue                                  # 範圍外 → 原樣保留
        cur = b.get("現值")
        for w in _BAND_ALIAS.get(name, (name,)):
            _repl = (w + "（{:.1f}%，範圍內）".format(cur) if isinstance(cur, (int, float))
                     else w + "（範圍內）")
            pat = re.compile(re.escape(w) + r"[^（(]{0,10}[（(][^）)]{0,90}?(?:"
                             + "|".join(_BAND_BAD) + r")[^）)]{0,70}?[）)]")
            for _ in range(30):
                m = pat.search(out)
                if not m:
                    break
                out = out[:m.start()] + _repl + out[m.end():]
            for _ in range(30):
                m2 = re.search(re.escape(w) + r"((?:(?!" + re.escape(w) + r").){0,140}?)("
                               + "|".join(_BAND_BAD) + r")\s*[+-]?[\d.]+(?:\s*)pp", out, re.S)
                if not m2:
                    break
                out = out[:m2.start()] + w + m2.group(1).rstrip() + "（範圍內）" + out[m2.end():]
    return out
