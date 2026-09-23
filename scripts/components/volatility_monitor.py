"""投資波動損失檢視卡（2026-09-16 建立）

用途：把「近 2/6/15/30 交易日的總資產與投資部位變動」換算成「約幾個月配息」，
      再補一段最壞情境模擬（市場再跌 5%），讓波動從「帳面數字」變成可感知的生活量尺。

兩處消費端，樣式不同（2026-09-16 INC-209 修）：
  - 儀表板（build_dashboard.py）：theme="dark"（Tailwind 深色指揮中心）
  - 日報（run_daily.render_daily_report）：theme="light"（日報自己的 .card/.callout 設計系統）
    ⚠️ 日報沒有載入 Tailwind，直接塞深色版會變沒樣式的裸文字。

BASE 一律由 __file__ 推算：舊版用 Path(".").resolve()，只要 cron 的 CWD 不是 repo 根目錄，
就會靜默降級成「⚠️ 無歷史資產差異資料」（不報錯、卡片變空）。
"""
import io
import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]      # longjiu_system 根目錄（不吃 CWD）
SNAPSHOT = BASE / "snapshot.json"
HISTORY = BASE / "asset_diff_history.json"


def get_asset_diff_history():
    try:
        content = io.open(HISTORY, encoding="utf-8").read()
        return json.loads(content)
    except Exception:
        return {}


def inv(r):
    return ((r.get("securities_market", 0) or 0)
            + (r.get("fund_market", 0) or 0)
            + (r.get("insurance_current", 0) or 0))


def _periods(R, today):
    """回傳 [(label, 起始日 dict)]，不含資料不足的期間。"""
    all_dates = sorted([k for k in R.keys() if k <= today])
    out = []
    for label, off in (("近2交易日", 2), ("近6交易日", 6), ("近15交易日", 15), ("近30交易日", 30)):
        idx = len(all_dates) - 1 - off
        if idx < 0:
            continue
        prev = R.get(all_dates[idx])
        if prev:
            out.append((label, prev))
    return out


def make_volatility_report(theme: str = "dark") -> str:
    d = get_asset_diff_history()
    _missing = ("<p style='color:#64748b;font-size:14px'>⚠️ 無歷史資產差異資料</p>"
                if theme == "light" else
                "<p class='text-xs text-slate-400'>⚠️ 無歷史資產差異資料</p>")
    if not d:
        return _missing

    R = {r["date"]: r for r in d.values()}
    today = date.today().isoformat()
    cur = R.get(today)
    if not cur:
        # fallback: 用最近一筆資料的日期
        all_dates = sorted([k for k in R.keys() if k <= today])
        if all_dates:
            today = all_dates[-1]
            cur = R.get(today)
        if not cur:
            return ("<p style='color:#64748b;font-size:14px'>⚠️ 無歷史資產差異資料</p>"
                    if theme == "light" else
                    "<p class='text-xs text-slate-400'>⚠️ 無歷史資產差異資料</p>")

    periods = _periods(R, today)
    try:
        _md = json.load(io.open(SNAPSHOT, encoding="utf-8")).get("monthly_dividend")
    except Exception:
        _md = None
    monthly_dividend = float(_md) if _md else 0

    if theme == "dark":
        return _render_dark(today, cur, periods, monthly_dividend)
    return _render_light(today, cur, periods, monthly_dividend)


def _render_dark(today, cur, periods, monthly_dividend) -> str:
    parts = [f'<h4 class="text-md font-bold text-white">📊 投資波動損失檢視（{today}）</h4>',
             "<div class='grid grid-cols-1 md:grid-cols-2 gap-4'>"]
    for label, prev in periods:
        dt = cur["total_assets"] - prev["total_assets"]
        di = inv(cur) - inv(prev)
        pt = (dt / prev["total_assets"] * 100) if prev["total_assets"] else 0
        pi = (di / inv(prev) * 100) if inv(prev) else 0
        parts.append("<div class='bg-slate-900/40 p-4 rounded-xl border border-slate-800 space-y-2'>")
        parts.append(f"<span class='text-xs font-bold text-red-400'>{label}</span>")
        parts.append("<ul class='text-xs text-slate-300 space-y-1.5 list-disc pl-4'>")
        parts.append(f"<li>總資產 {dt:+,.0f} TWD ({pt:+.2f}%)</li>")
        parts.append(f"<li>投資部位 {di:+,.0f} TWD ({pi:+.2f}%)</li>")
        parts.append(f"<li>約 {abs(di) / monthly_dividend:.1f} 個月配息</li>" if monthly_dividend > 0
                     else "<li>月配息數據缺失或為零，無法計算相對波動</li>")
        parts.append("</ul></div>")
    parts.append("</div>")
    parts.append("<div class='luxury-card p-6 space-y-4'>")
    parts.append('<h4 class="text-md font-bold text-white">🚨 最壞情境模擬：市場再跌 5%</h4>')
    parts.append("<ul class='text-xs text-slate-300 space-y-1.5 list-disc pl-4'>")
    parts.append(f"<li>總投資部位預估損失：{inv(cur) * 0.05:,.0f} TWD</li>")
    parts.append(f"<li>其中保單資產預估損失：{cur.get('insurance_current', 0) * 0.05:,.0f} TWD</li>")
    parts.append("</ul></div>")
    return "\n".join(parts)


def _render_light(today, cur, periods, monthly_dividend) -> str:
    """日報版：沿用日報自己的設計系統（.card / .callout-bear），不用 Tailwind。"""
    parts = [f"<h2>📊 投資波動損失檢視（{today}）</h2>", '<div class="card">',
             '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px">']
    for label, prev in periods:
        dt = cur["total_assets"] - prev["total_assets"]
        di = inv(cur) - inv(prev)
        pt = (dt / prev["total_assets"] * 100) if prev["total_assets"] else 0
        pi = (di / inv(prev) * 100) if inv(prev) else 0
        _md_txt = (f"約 {abs(di) / monthly_dividend:.1f} 個月配息" if monthly_dividend > 0
                   else "月配息數據缺失，無法換算")
        parts.append('<div style="border:1px solid #e5e7eb;border-radius:10px;padding:10px 12px">')
        parts.append(f'<div style="font-weight:700;color:#ef4444;font-size:15px;margin-bottom:4px">{label}</div>')
        parts.append('<div style="font-size:15px;line-height:1.9">')
        parts.append(f'<div>總資產 <b style="float:right">{dt:+,.0f}</b>（{pt:+.2f}%）</div>')
        parts.append(f'<div>投資部位 <b style="float:right">{di:+,.0f}</b>（{pi:+.2f}%）</div>')
        parts.append(f'<div style="color:#6b7280">{_md_txt}</div>')
        parts.append("</div></div>")
    parts.append("</div></div>")
    parts.append('<div class="callout callout-bear">')
    parts.append("<strong>🚨 最壞情境模擬：市場再跌 5%</strong>")
    parts.append(f"<div>總投資部位預估損失：<b>{inv(cur) * 0.05:,.0f} TWD</b></div>")
    parts.append(f"<div>其中保單資產預估損失：<b>{cur.get('insurance_current', 0) * 0.05:,.0f} TWD</b></div>")
    parts.append("</div>")
    return "\n".join(parts)
