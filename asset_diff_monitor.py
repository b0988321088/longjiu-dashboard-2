"""
asset_diff_monitor.py — 資產每日變化監控 + 趨勢 + 巴菲特建議
資料來源：snapshot.json（唯一真值） + asset_diff_history.json（歷史）
產出：asset_diff_YYYY-MM-DD.html + Telegram 摘要
"""
from __future__ import annotations

import json, sys
import os
import urllib.request
import urllib.error
from pathlib import Path
from datetime import date
from typing import Any

import requests
from dotenv import load_dotenv

# ---------- env ----------
project_env = Path(__file__).resolve().parent / ".env"
hermes_env = Path.home() / "AppData" / "Local" / "hermes" / ".env"
default_env = os.environ.get("DOTENV", str(project_env))
if not Path(default_env).exists() and hermes_env.exists():
    default_env = str(hermes_env)
load_dotenv(default_env)
if hermes_env.exists():
    try:
        load_dotenv(str(hermes_env), override=True)
    except Exception:
        pass
if hermes_env.exists():
    try:
        load_dotenv(str(hermes_env), override=True)
    except Exception:
        pass

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "") or os.getenv("TELEGRAM_ALLOWED_USERS", "")

BASE = "https://api.notion.com/v1"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
MASTER_DB = "39dfc735-d433-8153-9712-c8a0ee0ec846"

HISTORY_FILE = Path("asset_diff_history.json")
SNAP_FILE = Path("snapshot.json")
OUT_HTML = Path(f"asset_diff_{date.today().isoformat()}.html")

ALERT_DROP_TWD = 100_000
ALERT_DROP_PCT = 2.0
ALERT_SEC_DROP_TWD = 50_000
WATCH_SEC_PCT = 3.0


# ---------- helpers ----------
def notion_post(path: str, payload: dict) -> dict:
    r = requests.post(f"{BASE}{path}", headers=NOTION_HEADERS, json=payload, timeout=60)
    if r.status_code >= 400:
        print(f"HTTP {r.status_code}: {r.text[:500]}")
    r.raise_for_status()
    return r.json()


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(p: Path, data: dict) -> None:
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _color(x: float, inverse: bool = False) -> str:
    good = x >= 0
    if inverse:
        good = not good
    return "#16a34a" if good else "#dc2626"


def _fmt(v):
    try:
        return f"{float(v):,.0f}"
    except Exception:
        return str(v)


def _pct(v, base):
    try:
        v = float(v)
        base = float(base)
    except Exception:
        return "N/A"
    return f"{v / base * 100:.1f}%" if base else "N/A"


# ---------- snapshot parsing ----------
def extract_snapshot(snap: dict) -> dict:
    total_assets = snap.get("total_assets", 0)
    total_liab = snap.get("total_liabilities", 22_000_000)
    net_worth = snap.get("net_worth", total_assets - total_liab)

    securities = snap.get("securities_total_market_value", snap.get("securities_total", 0))
    insurance = snap.get("insurance_current_value", snap.get("insurance_total", 0))
    insurance_total = snap.get("insurance_total", insurance)
    funds = snap.get("fund_market_value", snap.get("funds_total", 0))

    cash = snap.get("real_liquid_assets", 0) or (snap.get("high_yield_savings_total", 0) + snap.get("moneybook_total", 0))
    real_estate = snap.get("real_estate_value", 0)
    if not real_estate:
        real_estate = max(0, total_assets - securities - insurance - funds - cash)

    other = max(0, total_assets - securities - insurance - funds - real_estate - cash)

    insurance_detail = {
        "安聯保單A+B 現值": snap.get("allianz_ab_current_value", 0),
        "安聯保單A 帳面": snap.get("allianz_policy_a_value", 0),
        "安聯保單B 帳面": snap.get("allianz_policy_b_value", 0),
        "第一金保單 FL65 現值": snap.get("firstjin_fl65_current_value", 0),
        "保單總現値": insurance,
        "保單總帳面": insurance_total,
    }

    # Build display breakdown with JPY funds converted to TWD
    jpy_rate = snap.get('fx_rates', {}).get('jpy_to_twd', 0.2)
    display_funds = {}
    for name, val in snap.get('funds_breakdown', {}).items():
        if '日元' in name or '日圓' in name or 'JPY' in name.upper():
            jpy_val = val
            # Handle already converted values: if val > 1_000_000 assume still JPY
            twd = round(jpy_val * jpy_rate)
            display_name = name + '（換算台幣）'
            display_funds[display_name] = twd
        else:
            display_funds[name] = val
    # Add gap fund if present
    for name, val in snap.get('funds_gap_fill', {}).items():
        display_funds[name] = val

    return {
        "date": str(snap.get("generated_at", snap.get("date", date.today().isoformat())))[:10],
        "total_assets": float(total_assets),
        "total_liabilities": float(total_liab),
        "net_worth": float(net_worth),
        "securities_market": float(securities),
        "insurance_current": float(insurance),
        "insurance_total": float(insurance_total),
        "fund_market": float(funds),
        "fund_breakdown_display": display_funds,
        "real_estate": float(real_estate or 0),
        "other": float(other),
        "cash": float(cash),
        "insurance_detail": insurance_detail,
        "fund_dividend_monthly": float(snap.get("fund_dividend_monthly", 0)),
        "fund_dividend_conservative": float(snap.get("passive_income", {}).get("fund_dividend_conservative", snap.get("fund_dividend_monthly", 0))),
        "monthly_income": float(snap.get("monthly_income", 218102)),
        "monthly_expense": float(snap.get("monthly_expense", snap.get("monthly_expense_mb", 141958))),
        "rent_monthly": float(snap.get("rent_monthly_actual", 80100)),
        "cathay_refinance": float(snap.get("cathay_refinance_amount") or 0),
        "runway_months": float(snap.get("runway_months") or (snap.get("real_liquid_assets", 0) / (snap.get("monthly_expense", 1) or 1))),
    }


# ---------- history ----------
def load_history() -> dict:
    return load_json(HISTORY_FILE)


def append_today(snap: dict) -> dict:
    history = load_history()
    ex = extract_snapshot(snap)
    today = ex["date"]

    history[today] = {
        "date": today,
        "total_assets": ex["total_assets"],
        "total_liabilities": ex["total_liabilities"],
        "net_worth": ex["net_worth"],
        "securities_market": ex["securities_market"],
        "insurance_current": ex["insurance_current"],
        "insurance_total": ex["insurance_total"],
        "fund_market": ex["fund_market"],
        "real_estate": ex["real_estate"],
        "cash": ex["cash"],
        "other": ex["other"],
        "insurance_detail": ex["insurance_detail"],
        "fund_dividend_monthly": ex["fund_dividend_monthly"],
        "monthly_income": ex["monthly_income"],
        "monthly_expense": ex["monthly_expense"],
        "rent_monthly": ex["rent_monthly"],
        "cathay_refinance": ex["cathay_refinance"],
    }
    save_json(HISTORY_FILE, history)
    return history


def compute_changes(history: dict) -> list[dict]:
    sorted_dates = sorted(history.keys())
    rows: list[dict] = []
    prev = None
    for d in sorted_dates:
        cur = history[d]
        if prev is None:
            prev = cur
            continue
        row: dict[str, Any] = {"date": d, "changes": {}}
        for key in [
            "total_assets",
            "total_liabilities",
            "net_worth",
            "securities_market",
            "insurance_current",
            "insurance_total",
            "fund_market",
            "real_estate",
            "cash",
            "other",
            "fund_dividend_monthly",
            "monthly_income",
            "monthly_expense",
            "rent_monthly",
        ]:
            pv = prev.get(key, 0) or 0
            cv = cur.get(key, 0) or 0
            row[key] = cv
            row[f"d_{key}"] = cv - pv
            row[f"d_{key}_pct"] = ((cv - pv) / pv * 100) if pv else 0.0
        prev = cur
        rows.append(row)
    return rows


# ---------- charts ----------
def _svg_line(values, width=600, height=120, color="#2563eb", label=""):
    if not values or len(values) < 2:
        return ""
    values = [float(v) for v in values]
    min_v = min(values)
    max_v = max(values)
    span = max_v - min_v if max_v != min_v else 1
    pad = 8
    w = width - pad * 2
    h = height - pad * 2
    step = w / (len(values) - 1)
    pts = []
    for i, v in enumerate(values):
        x = pad + i * step
        y = pad + h - ((v - min_v) / span) * h
        pts.append(f"{x:.1f},{y:.1f}")
    points_str = " ".join(f"L {p}" for p in pts)
    first = pts[0]
    return (
        f'<svg width="{width}" height="{height}" style="max-width:100%;height:auto;" viewBox="0 0 {width} {height}">'
        f'<polyline points="{first} {points_str.replace("L ", "L")}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{first.split(",")[0]}" cy="{first.split(",")[1]}" r="3" fill="{color}"/>'
        f'<circle cx="{pts[-1].split(",")[0]}" cy="{pts[-1].split(",")[1]}" r="3" fill="{color}"/>'
        f'<text x="{first.split(",")[0]}" y="{height - 1}" font-size="9" fill="#6b7280" text-anchor="middle">{label}</text>'
        f'</svg>'
    )


def build_trend_charts(history: dict) -> str:
    dates = sorted(history.keys())
    rows = [history[d] for d in dates[-14:]]
    charts = [
        ("證券市值", "securities_market", "#2563eb"),
        ("保單現値", "insurance_current", "#16a34a"),
        ("基金市值", "fund_market", "#7c3aed"),
        ("現金部位", "cash", "#f59e0b"),
        ("總資產", "total_assets", "#0ea5e9"),
        ("總負債", "total_liabilities", "#dc2626"),
    ]
    svgs = []
    for label, key, color in charts:
        vals = [float(r.get(key, 0) or 0) for r in rows]
        label_short = dates[0][5:] if len(dates) > 1 else ""
        svg = _svg_line(vals, color=color, label=label_short)
        block = f'<div style="flex:1;min-width:260px;"><div class="text-sm">{label}</div>'
        svgs.append(block + (svg if svg else '<div class="text-sm">累計中</div>') + '</div>')

    # asset structure (latest)
    last = rows[-1]
    stack = [
        ("證券市值", last.get("securities_market", 0), "#2563eb"),
        ("保單現値", last.get("insurance_current", 0), "#16a34a"),
        ("基金市值", last.get("fund_market", 0), "#7c3aed"),
        ("不動產", last.get("real_estate", 0), "#10b981"),
        ("現金", last.get("cash", 0), "#f59e0b"),
        ("其他", last.get("other", 0), "#9ca3af"),
    ]
    bars = []
    for label, v, c in stack:
        v = max(0, float(v or 0))
        if v == 0:
            continue
        bars.append(
            f'<div style="display:flex;align-items:center;margin:4px 0;">'
            f'<div style="width:14px;height:14px;background:{c};border-radius:3px;margin-right:8px;"></div>'
            f'<div style="flex:1;font-size:13px;color:#374151;">{label}</div>'
            f'<div style="font-size:13px;font-weight:700;color:#111;margin-left:8px;width:70px;text-align:right;">{v/10000:.0f}萬</div>'
            f'</div>'
        )
    stack_chart = '<div class="card"><h2>📊 資產結構（最新）</h2>' + "".join(bars) + '</div>'

    trend = (
        '<div class="card"><h2>📈 資產趨勢（近 14 日）</h2>'
        '<div style="display:flex;flex-wrap:wrap;gap:12px;">'
        + "".join(svgs) +
        '</div></div>'
    )
    return trend + stack_chart


# ---------- buffett ----------
def buffett_advice(history: dict, snap: dict) -> str:
    rows = compute_changes(history)
    ex = extract_snapshot(snap)
    ta = ex["total_assets"] or 1
    debt_ratio = ex["total_liabilities"] / ta * 100
    monthly_div = ex["fund_dividend_monthly"]
    monthly_div_conservative = ex.get("fund_dividend_conservative", monthly_div)
    monthly_rent = ex["rent_monthly"]
    monthly_exp = ex["monthly_expense"]
    passive_total = monthly_div_conservative + monthly_rent
    passive_coverage = passive_total / monthly_exp * 100 if monthly_exp else 0

    # allocations
    alloc = (
        f"證券 {ex['securities_market']/ta*100:.1f}% / "
        f"保單 {ex['insurance_current']/ta*100:.1f}% / "
        f"基金 {ex['fund_market']/ta*100:.1f}% / "
        f"現金 {ex['cash']/ta*100:.1f}% / "
        f"不動產 {ex['real_estate']/ta*100:.1f}%"
    )

    lines = [
        "🧠 在家巴菲特",
        "",
        f"資產結構：{alloc}",
        f"負債比率：{debt_ratio:.1f}%",
        f"保守配息：{_fmt(monthly_div_conservative)}（覆蓋率 {passive_coverage:.1f}%）",
    ]

    if rows:
        r = rows[-1]
        d_total = r.get("d_total_assets", 0)
        d_sec = r.get("d_securities_market", 0)
        d_fund = r.get("d_fund_market", 0)
        d_ins = r.get("d_insurance_current", 0)
        d_total_pct = r.get("d_total_assets_pct", 0)
        lines += [
            "",
            f"近一日變化：總資產 {d_total:+,.0f}（{d_total_pct:+.2f}%）",
            f"證券 {d_sec:+,.0f} / 保單 {d_ins:+,.0f} / 基金 {d_fund:+,.0f}",
        ]

    warnings = []
    if ex["securities_market"] / ta * 100 > 50:
        warnings.append("證券部位佔比偏高，注意集中度")
    if debt_ratio > 55:
        warnings.append(f"負債比率 {debt_ratio:.1f}% 偏高，8/2 轉貸完成後將下降")
    if ex["cathay_refinance"] > 0:
        warnings.append(f"國泰轉貸 {ex['cathay_refinance']/10000:.0f} 萬執行中")
    if ex.get("allianz_ab_current_value") and ex.get("allianz_policy_a_value"):
        cost_a = ex.get("allianz_policy_a_value", 0)
        cost_b = ex.get("allianz_policy_b_value", 0)
        total_cost = cost_a + cost_b
        current_value = ex.get("allianz_ab_current_value", 0)
        if total_cost and current_value:
            unrealized = current_value - total_cost
            warnings.append(f"安聯 A+B 未實現損益：{unrealized:+,.0f}（帳面 {_fmt(total_cost)} / 現值 {_fmt(current_value)}）")

    if warnings:
        lines += ["", "⚠️ 觀察點："]
        lines += [f"• {w}" for w in warnings]

    suggestions = []
    if ex["cathay_refinance"] > 0:
        suggestions.append("等待 8/2 國泰轉貸完成，減少利息支出")
    suggestions.append("0050 權重集中台積電 ~57%，可考慮補碼分散")
    suggestions.append("保單 A+B 管理費 1.5% 偏高，定期複檢配息收益率")
    if passive_coverage < 100:
        suggestions.append(f"保守配息 70K+房租 80K 可覆蓋月支出 {_fmt(monthly_exp)}")
    lines += ["", "💡 建議："]
    lines += [f"• {s}" for s in suggestions]

    return "\n".join(lines)


# ---------- HTML ----------
def build_html(rows: list[dict], history: dict, snap: dict) -> str:
    today = rows[-1]["date"] if rows else date.today().isoformat()
    ex = extract_snapshot(snap)

    # table rows
    changes_rows = []
    for r in rows[-7:]:
        d_total = r.get("d_total_assets", 0)
        d_sec = r.get("d_securities_market", 0)
        d_ins = r.get("d_insurance_current", 0)
        d_fund = r.get("d_fund_market", 0)
        d_cash = r.get("d_cash", 0)
        d_total_pct = r.get("d_total_assets_pct", 0)
        badge = ""
        if d_total < -ALERT_DROP_TWD or d_total_pct < -ALERT_DROP_PCT:
            badge = ' <span style="color:#dc2626;font-size:12px;">🚨 警示</span>'
        changes_rows.append(
            "<tr>"
            f"<td>{r['date']}</td>"
            f"<td class='num'>{_fmt(r['total_assets'])}</td>"
            f"<td class='num' style='color:{_color(d_total)}'>{d_total:+,.0f}</td>"
            f"<td class='num' style='color:{_color(d_total_pct)}'>{d_total_pct:+.2f}%</td>"
            f"<td class='num'>{_fmt(r['insurance_current'])}</td>"
            f"<td class='num' style='color:{_color(d_ins)}'>{d_ins:+,.0f}</td>"
            f"<td class='num'>{_fmt(r['fund_market'])}</td>"
            f"<td class='num' style='color:{_color(d_fund)}'>{d_fund:+,.0f}</td>"
            f"<td class='num'>{_fmt(r['securities_market'])}</td>"
            f"<td class='num' style='color:{_color(d_sec)}'>{d_sec:+,.0f}</td>"
            f"<td class='num'>{_fmt(r['cash'])}</td>"
            f"<td class='num' style='color:{_color(d_cash)}'>{d_cash:+,.0f}</td>"
            f"</tr>{badge}"
        )

    table_header = (
        "<tr>"
        "<th>日期</th>"
        "<th class='num'>總資產</th><th class='num'>增減</th><th class='num'>%</th>"
        "<th class='num'>保單現値</th><th class='num'>增減</th>"
        "<th class='num'>基金市值</th><th class='num'>增減</th>"
        "<th class='num'>證券市值</th><th class='num'>增減</th>"
        "<th class='num'>現金</th><th class='num'>增減</th>"
        "</tr>"
    )

    # insurance detail block
    if ex.get("insurance_detail"):
        d = ex["insurance_detail"]
        detail_rows = "".join(f"<tr><td>{k}</td><td class='num'>{_fmt(v)}</td></tr>" for k, v in d.items())
        detail_table = (
            '<div class="card"><h2>🛡️ 保單明細（最新）</h2>'
            '<div class="table-wrap"><table><thead><tr><th>項目</th><th class=\'num\'>金額 TWD</th></tr></thead><tbody>'
            + detail_rows + "</tbody></table></div></div>"
        )
    else:
        detail_table = ""

    # alerts
    alerts = []
    if rows:
        r = rows[-1]
        d_sec = r.get("d_securities_market", 0)
        d_total = r.get("d_total_assets", 0)
        d_total_pct = r.get("d_total_assets_pct", 0)
        if d_total < -ALERT_DROP_TWD or d_total_pct < -ALERT_DROP_PCT:
            alerts.append(f"<b>總資產</b>：{d_total:+,.0f}（{d_total_pct:+.2f}%）")
        if d_sec < -ALERT_SEC_DROP_TWD or abs(r.get("d_securities_market_pct", 0)) >= WATCH_SEC_PCT:
            alerts.append(f"<b>證券市值</b>：{d_sec:+,.0f}（{r.get('d_securities_market_pct',0):+.2f}%）")
    alerts_html = "".join(f"<li style='font-size:15px;line-height:1.8;'>{a}</li>" for a in alerts) if alerts else '<li style="font-size:15px;line-height:1.8;">✅ 今日無異常</li>'
    alert_header = f"單日資產下跌 ≥ {ALERT_DROP_TWD:,.0f} / {ALERT_DROP_PCT:.1f}%；證券下跌 ≥ {ALERT_SEC_DROP_TWD:,.0f} / ±{WATCH_SEC_PCT:.1f}%"

    buffett_md = buffett_advice(history, snap)
    charts_html = build_trend_charts(history)

    # Fund detail card from screenshot
    fund_detail_rows = "".join(
        f"<tr><td>{k}</td><td class='num'>{v:,.0f}</td><td>{'JPY換算' if '日元' in k else 'TWD'}</td></tr>"
        for k, v in ex.get('fund_breakdown_display', {}).items()
    )
    fund_card = (
        '<div class="card"><h2>📊 基金部位</h2>'
        '<div class="table-wrap"><table><thead><tr><th>基金名稱</th><th class=\'num\'>市值</th><th>幣別</th></tr></thead><tbody>'
        + fund_detail_rows
        + "</tbody></table></div></div>"
    )

    # Cash detail card
    cash_card = (
        '<div class="card"><h2>💵 現金部位</h2>'
        '<div class="table-wrap"><table><thead><tr><th>項目</th><th class=\'num\'>金額</th></tr></thead><tbody>'
        f"<tr><td>real_liquid_assets（總流動資產）</td><td class='num'>{_fmt(ex['cash'])}</td></tr>"
        "</tbody></table></div>"
        '<div class="text-sm" style="margin-top:8px;color:#6e6e73">包含：高利活存 2,200,410 + Moneybook 活期 3,071,343｜合併後唯一真值</div>'
        "</div>"
    )

    # Asset allocation card with all components incl real estate
    # Allocation: exclude real estate so other components sum to ~100%
    alloc_den = max(1, ex['total_assets'] - ex.get('real_estate', 0))
    alloc_items = [
        ('證券市值', ex['securities_market'], '#3b82f6'),
        ('保單現値', ex['insurance_current'], '#10b981'),
        ('基金市值', ex['fund_market'], '#f59e0b'),
        ('現金部位', ex['cash'], '#8b5cf6'),
    ]
    alloc_bars = "".join(
        f"<div style='margin:6px 0'><div style='display:flex;justify-content:space-between;font-size:14px'>"
        f"<span>{label}</span><span class='num'>{v/10000:.0f}萬 ({v/alloc_den*100:.1f}%)</span></div>"
        f"<div style='background:#f2f2f7;border-radius:4px;height:8px;margin-top:4px'><div style='background:{c};width:{v/alloc_den*100:.1f}%;height:8px;border-radius:4px'></div></div>"
        "</div>"
        for label, v, c in alloc_items
    )
    alloc_card = f'<div class="card"><h2>📈 資產結構（最新）</h2>{alloc_bars}</div>'

    body = "\n".join([
        f'<div class="card"><h1>📈 資產變化對照 {today}</h1><div class="text-sm">資產監控 / 趨勢 / 巴菲特分析</div></div>',
        f'<div class="card"><h2>📋 資產變化明細（近 7 日）</h2><div class="table-wrap"><table><thead>{table_header}</thead><tbody>',
        "".join(changes_rows),
        "</tbody></table></div></div>",
        charts_html,
        detail_table,
        fund_card,
        cash_card,
        alloc_card,
        f'<div class="card"><h2>🚨 監控警示</h2><div class="text-sm">{alert_header}</div><ul style="list-style:none;padding:0;">{alerts_html}</ul></div>',
        f'<div class="card"><h2>🧠 在家巴菲特</h2><pre style="font-size:15px;line-height:1.8;white-space:pre-wrap;">{buffett_md}</pre></div>',
        '</div></body></html>',
    ])

    style = (
        "body{font-family:-apple-system,\"Helvetica Neue\",\"PingFang TC\",sans-serif;background:#f5f5f7;color:#1d1d1f;margin:0;padding:14px}"
        ".page{max-width:1000px;margin:0 auto}"
        ".card{background:#fff;border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}"
        "h1{font-size:20px;font-weight:900;margin:0 0 6px}"
        "h2{font-size:17px;font-weight:800;margin:12px 0 8px;color:#111}"
        ".table-wrap{overflow-x:auto}"
        "th{background:#f2f2f7;font-weight:700;text-align:left;padding:8px 10px;border-bottom:2px solid #e5e5ea;white-space:nowrap}"
        "td{padding:8px 10px;border-bottom:1px solid #f2f2f7}"
        "td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}"
        ".text-sm{font-size:13px;color:#6e6e73}"
    )
    return (
        "<!DOCTYPE html><html lang=\"zh-TW\"><head><meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        f"<title>asset_diff_{today}</title>"
        f"<style>{style}</style></head><body><div class=\"page\">"
        + body
    )


# ---------- telegram ----------
def build_telegram_text(rows: list[dict], snap: dict) -> str:
    if not rows:
        return "📈 資產變化對照：尚無歷史紀錄"
    last = rows[-1]
    today_r = last["date"]
    d_total = last.get("d_total_assets", 0)
    d_total_pct = last.get("d_total_assets_pct", 0)
    d_sec = last.get("d_securities_market", 0)
    d_sec_pct = last.get("d_securities_market_pct", 0)
    flag = "\n🚨 異常警示已觸發，請查看詳細 HTML。" if d_total < -ALERT_DROP_TWD or d_total_pct < -ALERT_DROP_PCT else ""

    ex = extract_snapshot(snap)
    alloc = (
        f"資產佔比：證券 {_pct(ex['securities_market'], ex['total_assets'])} / "
        f"保單 {_pct(ex['insurance_current'], ex['total_assets'])} / "
        f"基金 {_pct(ex['fund_market'], ex['total_assets'])} / "
        f"現金 {_pct(ex['cash'], ex['total_assets'])}"
    )

    return (
        f"📈 資產變化對照 {today_r}\n"
        f"總資產：{_fmt(last['total_assets'])}（{d_total:+,.0f} / {d_total_pct:+.2f}%）\n"
        f"證券市值：{_fmt(last['securities_market'])}（{d_sec:+,.0f} / {d_sec_pct:+.2f}%）\n"
        f"保單現値：{_fmt(last['insurance_current'])}（{last.get('d_insurance_current',0):+,.0f}）\n"
        f"基金市值：{_fmt(last['fund_market'])}（{last.get('d_fund_market',0):+,.0f}）\n"
        f"{alloc}\n"
        f"負債比率：{ex['total_liabilities']/ex['total_assets']*100:.1f}%\n"
        f"{flag}"
    )


def send_telegram_document(path: str, caption: str = "") -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "") or os.environ.get("TELEGRAM_ALLOWED_USERS", "")
    if not token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN / CHAT_ID 未設定")
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        with open(path, "rb") as f:
            files = {"document": f}
            data = {"chat_id": chat_id, "caption": caption}
            req = urllib.request.Request(url, data=__import__("urllib.parse").parse.urlencode(data).encode(), method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = json.loads(resp.read())
                return raw.get("ok", False)
    except Exception as e:
        print(f"❌ Telegram document {e}")
        return False

def send_telegram(text: str) -> None:
    token = TELEGRAM_BOT_TOKEN
    chat_id = TELEGRAM_CHAT_ID
    if not token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN / CHAT_ID 未設定")
        return
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"📨 Telegram {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"❌ Telegram {e.code}: {e.read().decode('utf-8', errors='ignore')[:240]}")



def check_url(url: str, timeout: int = 15) -> dict:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"url": url, "status": resp.status, "ok": True}
    except urllib.error.HTTPError as e:
        return {"url": url, "status": e.code, "ok": False}
    except Exception as e:
        return {"url": url, "status": str(e), "ok": False}

# ---------- notion ----------
def push_to_notion(snap: dict) -> None:
    if not NOTION_TOKEN:
        print("[notion] token missing, skip")
        return
    ex = extract_snapshot(snap)
    note = (
        f"總資產 {ex['total_assets']:,.0f}（{ex['total_assets']/10000:.0f}萬）"
        f"｜淨資產 {ex['net_worth']:,.0f}"
        f"｜證券 {ex['securities_market']:,.0f}"
        f"｜保單現値 {ex['insurance_current']:,.0f} 總帳面 {ex['insurance_total']:,.0f}"
        f"｜基金 {ex['fund_market']:,.0f}"
        f"｜現金 {ex['cash']:,.0f}"
        f"｜負債 {ex['total_liabilities']:,.0f}"
        f"｜配息/月 {ex['fund_dividend_monthly']:,.0f}"
        f"｜負債比率 {ex['total_liabilities']/ex['total_assets']*100:.1f}%"
    )
    payload = {
        "parent": {"database_id": MASTER_DB},
        "properties": {
            "資產名稱": {"title": [{"text": {"content": f"快照 {ex['date']}"}}]},
            "分類": {"select": {"name": "快照"}},
            "更新日期": {"date": {"start": ex["date"]}},
            "即時餘額": {"number": ex["total_assets"]},
            "成本基準": {"number": ex["insurance_total"]},
            "幣別": {"select": {"name": "TWD"}},
            "備註": {"rich_text": [{"text": {"content": note}}]},
        },
    }
    try:
        notion_post("/pages", payload)
        print("✅ Notion snapshot pushed")
    except Exception as e:
        print(f"⚠️ Notion push failed: {e}")


# ---------- main ----------
def main() -> int:
    snap = load_json(SNAP_FILE)
    if not snap:
        print("⚠️ snapshot.json 不存在或為空")
        return 1

    history = append_today(snap)
    rows = compute_changes(history)
    if not rows:
        print("⚠️ 歷史資料不足，明日起開始累積")
        return 0

    html = build_html(rows, history, snap)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"✅ HTML 已產出：{OUT_HTML} ({len(html)} bytes)")

    today_r = rows[-1]["date"]
    tg = build_telegram_text(rows, snap)
    send_telegram(tg)

    try:
        import subprocess
        if OUT_HTML.exists():
            subprocess.run([
                sys.executable,
                str(Path(__file__).resolve().parent / "scripts" / "telegram_send_document.py"),
                str(OUT_HTML.resolve()),
                f"📈 資產變化對照 {today_r} 網頁版",
                TELEGRAM_BOT_TOKEN,
                TELEGRAM_CHAT_ID,
            ], check=False)
        docx_path = OUT_HTML.with_suffix('.docx')
        if docx_path.exists():
            subprocess.run([
                sys.executable,
                str(Path(__file__).resolve().parent / "scripts" / "telegram_send_document.py"),
                str(docx_path.resolve()),
                f"📈 資產變化對照 {today_r} Word 版",
                TELEGRAM_BOT_TOKEN,
                TELEGRAM_CHAT_ID,
            ], check=False)
    except Exception as e:
        print(f"⚠️ 附件傳送失敗：{e}")

    push_to_notion(snap)

    try:
        import webbrowser
        webbrowser.open(OUT_HTML.resolve().as_uri())
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
