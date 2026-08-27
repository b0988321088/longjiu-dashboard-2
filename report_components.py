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
    expense = snap.get("monthly_expense", 162781)
    rent = snap.get("rent_monthly_total", 80100) or 0
    if mode == "full":
        income = (snap.get("monthly_income", 214685) or 0)
        label = "含薪水常態"
    else:
        income = (snap.get("dividend_month_expected") or 100000) + rent
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
    """健康度分數 0-100（六維度加權）→ (分數, 燈號, 明細)。
    2026-08-27 設計：覆蓋25/防禦20/曝險15/現金15/利率15/LTV10。"""
    expense = snap.get("monthly_expense", 162781)
    rent = snap.get("rent_monthly_total", 80100) or 0
    income = (snap.get("dividend_month_expected") or 100000) + rent
    cov = income / expense * 100 if expense else 0

    # 防禦維度（雙維度框架 8/21：情境門檻）
    ddm = snap.get("dual_dimension_metric", {})
    defense = _num(ddm.get("防禦維度", ddm.get("防禦", 50)), 50)
    def_score = 100 if defense >= 50 else (60 if defense >= 40 else 0)

    # 美元曝險（口徑：美股桶+美元定存+美元債券梯+保單美元債 ≈54%）
    _usd_m = snap.get("usd_exposure_monitor", {}).get("current", {})
    if isinstance(_usd_m, dict):
        # ⚠️ 2026-08-27 實踩：current 是 dict，_num 會取第一個值(美股桶42.1)漏掉「合計54.4」→ 滿分誤判
        usd = _num(_usd_m.get("合計", _usd_m.get("美股桶", 54)), 54)
    else:
        usd = _num(_usd_m, 54)
    usd_score = 100 if usd <= 50 else (50 if usd <= 60 else 0)

    # 現金底線（70萬）
    cash = _num(snap.get("cash_total", 0), 0)
    floor = _num(snap.get("cash_floor_rule", {}).get("cash_floor", 700000), 700000)
    cash_score = 100 if cash >= floor else 0

    # US30Y（凍結 5.30）— 優先讀 us30y_state.json（最新真值），fallback snapshot
    try:
        _us = json.loads((Path(__file__).resolve().parent / "us30y_state.json").read_text(encoding="utf-8"))
        _us30y = _us.get("last_rate", _us.get("rate", None))
    except Exception:
        _us30y = None
    us30y = _num(_us30y if _us30y is not None else snap.get("rhythm08", {}).get("indicators", {}).get("us30y", 5.19), 5.19)
    rate_score = 100 if us30y < 5.20 else (50 if us30y < 5.30 else 0)

    # LTV（質押後 ~20.4%，上限 35）
    ltv = _num(snap.get("policy_pledge", {}).get("ltv", 20.4), 20.4)
    ltv_score = 100 if ltv <= 35 else (50 if ltv <= 50 else 0)

    score = round(min(cov / 150 * 100, 100) * 0.25 + def_score * 0.20 + usd_score * 0.15 + cash_score * 0.15 + rate_score * 0.15 + ltv_score * 0.10)
    light = "🟢" if score >= 80 else ("🟡" if score >= 60 else "🔴")
    # 標準分 = 各維度 0-100 制原始得分；權重分 = 標準分 × 權重（加總 = 總分）
    _cov_std = round(min(cov / 150 * 100, 100))
    detail = {
        "分數": score, "燈號": light,
        "覆蓋": round(cov), "覆蓋標準": _cov_std, "覆蓋分": round(_cov_std * 0.25),
        "防禦": defense, "防禦標準": def_score, "防禦分": round(def_score * 0.20),
        "曝險": usd, "曝險標準": usd_score, "曝險分": round(usd_score * 0.15),
        "現金": cash, "現金標準": cash_score, "現金分": cash_score * 0.15,
        "利率": us30y, "利率標準": rate_score, "利率分": rate_score * 0.15,
        "LTV": ltv, "LTV標準": ltv_score, "LTV分": ltv_score * 0.10,
    }
    return detail


def render_health_card(snap: dict) -> str:
    """健康度卡（HTML 片段）— 儀表板/日報共用。"""
    d = render_health_score(snap)
    # 防禦維度：可能是金額（>100）→ 顯示「充足」避免怪數字
    _def_txt = f"{d['防禦']:.0f}%" if d["防禦"] <= 100 else "✅ 充足"
    # (名稱, 現況, 目標, 權重分/權重) — 現況 vs 目標 → 得分
    rows = [
        ("現金流覆蓋", f"{d['覆蓋']}%", "≥100%", d["覆蓋分"], 25),
        ("防禦維度", _def_txt, "≥50%", d["防禦分"], 20),
        ("美元曝險", f"{d['曝險']:.1f}%", "≤50%", d["曝險分"], 15),
        ("現金底線", f"{d['現金']:,.0f}", "≥700,000", d["現金分"], 15),
        ("US30Y", f"{d['利率']:.2f}%", "<5.20%", d["利率分"], 15),
        ("LTV", f"{d['LTV']:.1f}%", "≤35%", d["LTV分"], 10),
    ]
    bar = "".join(
        f'<div style="display:flex;justify-content:space-between;font-size:11px;margin:2px 0">'
        f'<span style="color:#6e6e73">{n}</span><span style="color:#1f2937">{v}（目標 {t}）<b>{p}/{w}</b></span></div>'
        for n, v, t, p, w in rows
    )
    return (
        f'<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:10px;padding:12px;margin:8px 0">'
        f'<div style="font-weight:800;color:#14532d;margin-bottom:4px">🩺 龍九健康度：<span style="font-size:16px">{d["分數"]}/100</span> {d["燈號"]}</div>'
        f'{bar}'
        f'<div style="font-size:10.5px;color:#166534;margin-top:4px">{"唯一弱項：美元曝險（下一階段降）" if d["曝險分"] < 15 else "六維度全數達標"}</div></div>'
    )


if __name__ == "__main__":
    # 自測
    snap = json.loads((Path(__file__).resolve().parent / "snapshot.json").read_text(encoding="utf-8"))
    print(render_penetration_card(snap)[:200])
    print(render_coverage(snap, "passive"))
    print(render_coverage(snap, "full"))
    print(render_status_line(Path(__file__).resolve().parent, sep=" | "))
    print(render_health_score(snap))
