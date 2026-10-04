#!/usr/bin/env python3
"""pi_card.py — PI 專業投資人「雙軌狀態卡」唯一計算與渲染層（2026-10-04 裁決）

設計原則（PI_DATA_LIFECYCLE_SPEC.md）：
  ① 計算一律經 sot_targets 的 PI accessor（本模組**不新增任何真值來源、不寫死任何數字**）。
  ② 財力軌（proxy vs 法規門檻）與資格軌（application／approval）**分離**。
  ③ 缺真值 → payload.error，由渲染端 fail-closed 顯示（禁數值頂替）。
  ④ 日報（HTML）與週報（Markdown）由**同一份 payload**渲染，數字必然一致。
"""
from __future__ import annotations

import html as _html


def pi_payload(snap: dict) -> dict:
    """PI 雙軌 payload（唯一計算點）。缺真值 → {"error": ...}（不 raise、由渲染端顯示）。"""
    try:
        import sot_targets as _sot
        rec = _sot.pi_record(snap)
        thr = float(_sot.pi_regulatory_threshold())
        proxy = float(_sot.pi_financial_asset_proxy(snap))
        return {
            "record": rec,
            "threshold_twd": thr,
            "proxy_twd": proxy,
            "gap_twd": max(0.0, thr - proxy),
            "meets_financial_threshold": proxy >= thr,
            "approved": _sot.pi_is_approved(snap),
            "error": None,
        }
    except Exception as e:  # fail-closed：不在這裡補任何預設值
        return {"record": {}, "error": f"{type(e).__name__}: {e}"}


def _head(payload: dict) -> str:
    return "**🎫 專業投資人（PI）｜雙軌狀態卡**"


def pi_markdown_lines(payload: dict) -> list:
    """Markdown 行（週報／tactical_table 用）。"""
    if payload.get("error"):
        return ["", _head(payload),
                f"- ⛔ PI 資料缺真值（{payload['error']}）→ 拒絕顯示任何數字（fail-closed）"]
    rec = payload.get("record") or {}
    out = ["", _head(payload) + "（零槓桿預設）",
           (f"- 資格軌：申請 {rec.get('application_status', '—')}｜核准 {rec.get('approval_status', '—')}"
            f"｜Lombard 硬鎖 {'🔓 已解除' if payload['approved'] else '🔒 鎖定'}"),
           (f"- 財力軌（系統內部 readiness proxy，非機構最終認定）：{payload['proxy_twd']:,.0f}"
            f" ／ 門檻 {payload['threshold_twd']:,.0f}｜缺口 {payload['gap_twd']:,.0f}"
            f"｜{'✅ 達標' if payload['meets_financial_threshold'] else '🔴 未達'}"),
           "- ⚠️ 財力達標 ≠ 已核准：門檻僅為送件條件之一（另涉書面申請、專業知識與交易經驗、機構合理調查）"]
    return out


def pi_html(payload: dict) -> str:
    """日報用 HTML（callout 卡）。"""
    if payload.get("error"):
        return ("<div class='callout callout-danger' style='margin-top:12px'>"
                "<h3>🎫 專業投資人（PI）｜雙軌狀態卡</h3>"
                "<div style='font-size:12.5px;line-height:1.8'>⛔ PI 資料缺真值（"
                + _html.escape(str(payload["error"]))
                + "）→ 拒絕顯示任何數字（fail-closed）</div></div>")
    rec = payload.get("record") or {}
    _cls = "callout-warning" if not payload["approved"] else "callout"
    _lock = "🔓 已解除" if payload["approved"] else "🔒 鎖定"
    _meet = "✅ 達標" if payload["meets_financial_threshold"] else "🔴 未達"
    _fo = rec.get("force_order", [])
    _fo_txt = " > ".join(_fo[:2]) if isinstance(_fo, list) and _fo else str(_fo or "")
    _mt = rec.get("macro_triggers", {}) or {}
    _fb = rec.get("forbidden", [])
    _fb_txt = "；".join(_fb[:2]) if isinstance(_fb, list) and _fb else ""
    return (
        f"<div class='callout {_cls}' style='margin-top:12px'>"
        "<h3>🎫 專業投資人（PI）｜雙軌狀態卡（零槓桿預設）</h3>"
        "<div style='font-size:12.5px;line-height:1.8'>"
        f"<strong>資格軌｜申請：</strong>{rec.get('application_status', '—')}"
        f"｜<strong>核准：</strong>{rec.get('approval_status', '—')}"
        f"｜<strong>Lombard 硬鎖：</strong>{_lock}<br/>"
        f"<strong>財力軌（系統內部 readiness proxy，非機構最終認定）：</strong>"
        f"{payload['proxy_twd']:,.0f} ／ 門檻 {payload['threshold_twd']:,.0f}"
        f"｜<strong>缺口：{payload['gap_twd']:,.0f}</strong>｜{_meet}<br/>"
        "<strong>⚠️ 財力達標 ≠ 已核准：</strong>門檻僅為送件條件之一（另涉書面申請、專業知識與交易經驗、機構合理調查）<br/>"
        f"{'<strong>強制順序：</strong>' + _fo_txt + '<br/>' if _fo_txt else ''}"
        f"<strong>🔴 宏觀紅線：</strong>30Y美債 &gt;5.20% → {_mt.get('警戒線_5.20', '停止新增長債/平衡基金')}<br/>"
        "<strong>🟢 友善線：</strong>&lt;4.80% 才可評估小槓桿（高息全清+現金≥300萬+擔保≤4成）<br/>"
        f"{'<strong>⛔ 禁止：</strong>' + _fb_txt if _fb_txt else ''}"
        f"<br/><strong>⚠️ 風險：</strong>{rec.get('risk_warning', '專業投資人不受金融消保法保障')}"
        "</div></div>"
    )
