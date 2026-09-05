# -*- coding: utf-8 -*-
"""build_investment_performance.py — 投資績效月報 v2（2026-09-04 定版）

核心：每月投資績效細分為 股票/基金/保單 三類，貸款資金單獨標示。

  每類損益 = 真實市值變化（帳面 − 當類新增投入）＋ 當類配息 − 當類費用
  總績效   = 三類損益合計 − 投資利息（房貸利息+保單借貸利息）− 申購手續費

口徑鐵則：
  · 借貸不創造淨值：轉貸撥款 = 負債同步增加。貸款投入的金額列「新增投入」，
    顯示於帳面但不計績效 → 貸款買的資產若漲跌，只有「漲跌部分」進績效
  · 配息自動分類：安聯/第一金 → 保單；ETF配息/台灣特品 → 股票；其餘基金名 → 基金
  · 校正檔帶入每月新增投入（分三類 + 資金來源），db 有月初基準後可全自動算市值
  · 新增投入只填「已交割的實際買賣」（需 Moneybook/交割紀錄佐證）；計畫額度（慢慢買每週1.5-2萬等）不得登入 — 9/5 修正實例：誤登股票投入 99,000 使 8 月真實市值變化被低估 9.9 萬（56,170→應為 155,170），已改基準

用法：
  python build_investment_performance.py            # 最近完整月
  python build_investment_performance.py 2026-08
"""
import json, sys, sqlite3, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
ADJ_FILE = BASE / "investment_performance_adjust.json"

CLASS_KEYS = ["股票", "基金", "保單"]


def classify_dividend(name):
    """配息 key → 類別：安聯/第一金→保單；ETF/台灣特品→股票；其他基金→基金"""
    if "安聯" in name or "第一金" in name:
        return "保單"
    if name.startswith("ETF") or "台灣特品" in name:
        return "股票"
    return "基金"


def load_adjust():
    if ADJ_FILE.exists():
        return json.loads(ADJ_FILE.read_text(encoding="utf-8"))
    return {}


def db_asset_on(db, date):
    r = db.execute(
        "SELECT date, securities, funds, insurance FROM assets "
        "WHERE date <= ? ORDER BY date DESC LIMIT 1", (date,)).fetchone()
    return r



# ── 資金成本儀表板（2026-09-04 使用者核准加入）──
# 利率對照（負債結構穩定；變動時改 investment_performance_adjust.json 的 "資金成本")
DEFAULT_LOANS = [
    # balance_keys: 多 key = 加總（永豐 3 筆分帳號，勿用 mortgage=含國泰 25,082,544）
    # monthly_payment: 實際月付；None = 純付息（月付=利息）。永豐本利攤還 65,735（含本金）
    {"name": "永豐房貸（洲際W 本利攤還 2.5%）", "balance_keys": ["mortgage_yy", "mortgage_yydu", "mortgage_xz"], "rate": 0.025, "monthly_payment": 65735},
    {"name": "國泰轉貸（大義街 2.6%）", "balance_keys": ["mortgage_cathay"], "rate": 0.026},
    {"name": "保單借貸（4%）", "balance_keys": ["policy_pledge_loan"], "rate": 0.040},
    {"name": "元大質押（3.92%）", "balance_keys": ["pledge_loan"], "rate": 0.0392},
]


def load_loans(snap, adj_costs=None):
    """讀 snapshot 負債餘額 + 利率 → [(name, balance, rate, monthly_interest, monthly_payment)]"""
    adj_costs = adj_costs or {}
    loans = []
    for dl in DEFAULT_LOANS:
        bal = sum(snap.get(k, 0) or 0 for k in dl["balance_keys"])
        if bal <= 0:
            continue
        rate = adj_costs.get(dl["name"], dl["rate"])
        monthly = bal * rate / 12
        pay = dl.get("monthly_payment") or monthly   # None→純付息
        loans.append({"name": dl["name"], "balance": bal, "rate": rate,
                      "monthly": monthly, "payment": pay})
    return loans


def funding_cost_report(snap, adj_costs=None, rate_overrides=None):
    """輸出資金成本儀表板文字：負債表 + 加權成本 + 配息殖利率 + 淨利差燈號"""
    loans = load_loans(snap, rate_overrides)
    total_bal = sum(l["balance"] for l in loans)
    total_m = sum(l["monthly"] for l in loans)
    total_pay = sum(l["payment"] for l in loans)
    wacc = total_m * 12 / total_bal if total_bal else 0

    # 投資市值（股票+基金+保單）
    inv = (snap.get("securities_total_market_value") or snap.get("securities_total") or 0) \
        + (snap.get("fund_market_value") or snap.get("funds_total") or 0) \
        + (snap.get("insurance_total") or 0)
    div_m = snap.get("dividend_month_expected") or 100000   # 保守常態月配息
    div_actual = adj_costs.get("配息實收") if adj_costs else None  # 當月實際實收（校正檔帶入）
    rent_m = adj_costs.get("房租實收") if adj_costs else (snap.get("passive_income", {}).get("rent_monthly") or 80100)
    if div_actual:
        div_yield = div_actual * 12 / inv if inv else 0
    else:
        div_yield = div_m * 12 / inv if inv else 0

    spread = div_yield - wacc
    if spread >= 0.012:
        light = "🟢 利差充足（≥1.2%）→ 現金流安全、套利空間存在"
    elif spread >= 0:
        light = "🟡 利差偏薄（0~1.2%）→ 付息可、擴槓桿謹慎"
    else:
        light = "🔴 利差為負 → 配息不足以 cover 利息，停止加槓桿"
    pay_ok = "✅ 配息可 cover 利息" if div_m >= total_m else "⚠️ 月配息 < 月利息"
    # 現金流兩層：實際月付 vs 配息(實際優先) vs 被動收入(含房租)
    div_base = div_actual if div_actual else div_m
    div_tag = "8月實收" if div_actual else "保守"
    passive = div_base + rent_m
    if passive >= total_pay:
        cash_ok = f"✅ 被動收入(配息{div_base:,.0f}+房租{rent_m:,.0f}) {passive:,.0f} > 實際月付 {total_pay:,.0f} → 償債後剩 {passive-total_pay:,.0f}/月"
    else:
        cash_ok = f"⚠️ 被動收入 {passive:,.0f} < 實際月付 {total_pay:,.0f}（含本利攤還）→ 需其他收入補 {total_pay-passive:,.0f}/月"
    div_cover_pay = f"⚠️ 純配息{div_tag} {div_base:,.0f} < 實際月付 {total_pay:,.0f}（永豐本利攤還所致）" if div_base < total_pay else f"✅ 純配息{div_tag} {div_base:,.0f} ≥ 實際月付 {total_pay:,.0f}"

    L = ["\n⚖️ 資金成本儀表板（借貸總成本 vs 投資現金流）", "-" * 58]
    L.append("  借款                     餘額    利率    實際月付(含本)  其中利息")
    for l in loans:
        flag = "（本利攤還）" if l["payment"] > l["monthly"] else ""
        L.append(f"  {l['name']:26s} {l['balance']/10000:>6.0f}萬 {l['rate']*100:>4.2f}% {l['payment']:>10,.0f} {flag:8s} {l['monthly']:>8,.0f}")
    L.append(f"  {'合計':26s} {total_bal/10000:>6.0f}萬        {total_pay:>10,.0f}    利息 {total_m:>8,.0f}")
    L.append(f"  加權平均資金成本 = {wacc*100:.2f}%/年｜⚠️ 永豐為本利攤還：實際月付 {total_pay:,.0f} > 純利息 {total_m:,.0f}")
    L.append(f"  投資市值（股票+基金+保單） {inv/10000:,.0f}萬")
    src_tag = f"當月實收 {div_actual:,.0f}" if div_actual else f"保守常態 {div_m:,.0f}"
    L.append(f"  配息 {src_tag} → 配息殖利率 {div_yield*100:.2f}%/年")
    L.append(f"  淨利差 = {div_yield*100:.2f}% − {wacc*100:.2f}% = {spread*100:+.2f}pp")
    L.append(f"  判斷：{light}")
    L.append(f"  利息層：{pay_ok}（月配息 {div_m:,.0f} vs 純月息 {total_m:,.0f}）")
    L.append(f"  現金流層：{div_cover_pay}")
    L.append(f"  現金流層：{cash_ok}")
    L.append(f"  註：房貸利息為居住成本；純投資槓桿 = 國泰+保單+元大（若看套利）")
    return "\n".join(L)


def _fmt(v, signed=False):
    return f"{v:+,.0f}" if signed else f"{v:,.0f}"


def write_dashboard_html(mk, class_rows, interest_total, grand, perf, project,
                         loans, pol_rows, real_sum, ins_div_m, pledge_m, cov,
                         ct_items, cur12, cost12, cathay_div, cathay_m, snap):
    """投資績效儀表板 HTML（2026-09-05：整併進 build 腳本，cron 每月自動重產不掉區塊）"""
    wacc = sum(l["monthly"] for l in loans) * 12 / sum(l["balance"] for l in loans) if loans else 0
    total_m = sum(l["monthly"] for l in loans)
    total_pay = sum(l["payment"] for l in loans)
    inv = (snap.get("securities_total_market_value") or snap.get("securities_total") or 0) \
        + (snap.get("fund_market_value") or snap.get("funds_total") or 0) \
        + (snap.get("insurance_total") or 0)
    div_actual = sum(r["div"] for r in class_rows)
    div_yield = div_actual * 12 / inv if inv else 0
    spread = div_yield - wacc
    if spread >= 0.012:
        light = "🟢 利差充足（≥1.2%）→ 現金流安全、套利空間存在"
    elif spread >= 0:
        light = "🟡 利差偏薄（0~1.2%）→ 付息可、擴槓桿謹慎"
    else:
        light = "🔴 利差為負 → 停止加槓桿"
    T = lambda s: s.replace("<", "&lt;")
    L = []
    L.append('<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">')
    L.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    L.append('<title>📊 龍九投資績效月報</title>')
    L.append("<style>body{font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;background:#f5f5f7;margin:0;padding:16px}</style></head><body><div style=\"max-width:720px;margin:0 auto\">")
    L.append('<div style="background:linear-gradient(135deg,#064e3b,#065f46);border-radius:14px;padding:16px 18px;color:#fff;margin-bottom:12px">')
    L.append(f'<h1 style="font-size:18px;font-weight:900;margin:0 0 4px">📊 龍九投資績效月報（{mk}）</h1>')
    L.append(f'<div style="font-size:11.5px;color:#a7f3d0">基準月 2026-08（Baseline）｜每月同尺比較：投資賺多少 ⇄ 借貸付多少</div>')
    L.append('<div style="font-size:11px;color:#86efac;margin-top:4px">📌 左欄＝投資收益（三類損益，貸款錢剔除不計績效）｜右欄＝借貸利息（月成本）｜下方＝勝負判定</div></div>')
    L.append('<div style="display:flex;gap:12px;flex-wrap:wrap;align-items:stretch">')
    # ── 左欄 投資收益 ──
    L.append('<div style="flex:1.15;min-width:300px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:14px">')
    perf_col = "#16a34a" if perf >= 0 else "#dc2626"
    L.append(f'<div style="display:flex;justify-content:space-between;align-items:baseline"><h3 style="font-size:15px;font-weight:800;margin:0;color:#1d1d1f">📈 投資收益</h3><div style="font-size:24px;font-weight:900;color:{perf_col}">{perf/10000:+.1f} 萬</div></div>')
    L.append(f'<div style="font-size:11px;color:#94a3b8;margin:2px 0 10px">{mk}｜市值變化+配息−利息−手續費｜轉貸 1,200 萬已剔除</div>')
    L.append('<table style="width:100%;font-size:12.5px;border-collapse:collapse"><tr style="color:#6b7280;border-bottom:2px solid #e5e7eb"><th style="text-align:left;padding:5px 8px">類別</th><th style="text-align:right;padding:5px 8px">市值變化</th><th style="text-align:right;padding:5px 8px">配息</th><th style="text-align:right;padding:5px 8px">費用</th><th style="text-align:right;padding:5px 8px">損益</th></tr>')
    icons = {"股票": "📈", "基金": "💰", "保單": "🛡️"}
    for r in class_rows:
        c = r["c"]
        col = "#16a34a" if r["sub"] >= 0 else "#dc2626"
        L.append(f'<tr><td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;font-weight:700">{icons.get(c, c)} {T(c)}</td>'
                 f'<td style="padding:6px 8px;text-align:right;border-bottom:1px solid #f3f4f6">{_fmt(r["real_mv"], True)}</td>'
                 f'<td style="padding:6px 8px;text-align:right;border-bottom:1px solid #f3f4f6">{_fmt(r["div"], True)}</td>'
                 f'<td style="padding:6px 8px;text-align:right;border-bottom:1px solid #f3f4f6;color:#6b7280">{_fmt(r["fee"], True)}</td>'
                 f'<td style="padding:6px 8px;text-align:right;border-bottom:1px solid #f3f4f6;font-weight:800;color:{col}">{_fmt(r["sub"], True)}</td></tr>')
    L.append(f'<tr style="background:#f9fafb"><td style="padding:6px 8px;font-weight:700">三類合計</td><td style="padding:6px 8px;text-align:right;font-weight:700">{_fmt(sum(r["real_mv"] for r in class_rows), True)}</td>'
             f'<td style="padding:6px 8px;text-align:right;font-weight:700">{_fmt(sum(r["div"] for r in class_rows), True)}</td>'
             f'<td style="padding:6px 8px;text-align:right;font-weight:700;color:#dc2626">{_fmt(-sum(r["fee"] for r in class_rows), True)}</td>'
             f'<td style="padding:6px 8px;text-align:right;font-weight:900">{_fmt(grand, True)}</td></tr>')
    L.append(f'<tr><td style="padding:6px 8px" colspan="4">投資利息（8月當月計入：永豐房貸 28,000 + 保單借貸 14,000）</td><td style="padding:6px 8px;text-align:right;color:#dc2626;font-weight:700">{_fmt(-interest_total, True)}</td></tr></table>')
    if project:
        L.append(f'<div style="font-size:10.5px;color:#94a3b8;margin-top:6px">📦 專案收入(非常態) {_fmt(project)}（另計不混入）</div>')
    L.append('</div>')
    # ── 右欄 借貸利息 ──
    L.append('<div style="flex:1;min-width:260px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:14px">')
    L.append(f'<div style="display:flex;justify-content:space-between;align-items:baseline"><h3 style="font-size:15px;font-weight:800;margin:0;color:#1d1d1f">🏦 借貸利息（月成本）</h3><div style="font-size:24px;font-weight:900;color:#dc2626">{_fmt(-total_m)}<span style="font-size:12px;color:#9ca3af">利息/月</span></div></div>')
    L.append(f'<div style="font-size:11px;color:#94a3b8;margin:2px 0 10px">若含還本：實際月付 {_fmt(total_pay)}（利息 {_fmt(total_m)} + 本金 {_fmt(total_pay - total_m)}，永豐本利攤還）</div>')
    L.append('<table style="width:100%;font-size:12px;border-collapse:collapse"><tr style="color:#6b7280"><th style="text-align:left;padding:4px 8px">借款</th><th style="text-align:right;padding:4px 8px">餘額</th><th style="text-align:right;padding:4px 8px">利率</th><th style="text-align:right;padding:4px 8px">月利息</th></tr>')
    for l in loans:
        flag = "（本利攤還）" if l["payment"] > l["monthly"] else ""
        L.append(f'<tr><td style="padding:4px 8px;border-bottom:1px solid #f3f4f6">{T(l["name"])}{flag}</td><td style="padding:4px 8px;text-align:right;border-bottom:1px solid #f3f4f6">{l["balance"]/10000:.0f}萬</td><td style="padding:4px 8px;text-align:right;border-bottom:1px solid #f3f4f6">{l["rate"]*100:.2f}%</td><td style="padding:4px 8px;text-align:right;border-bottom:1px solid #f3f4f6">{_fmt(l["monthly"])}</td></tr>')
    L.append(f'<tr style="background:#f9fafb;font-weight:800"><td style="padding:5px 8px">合計</td><td style="padding:5px 8px;text-align:right">{sum(l["balance"] for l in loans)/10000:.0f}萬</td><td style="padding:5px 8px;text-align:right">加權 {wacc*100:.2f}%</td><td style="padding:5px 8px;text-align:right">{_fmt(total_m)}</td></tr></table>')
    L.append('<div style="background:#fef2f2;border-radius:8px;padding:7px 9px;margin-top:8px;font-size:11px;color:#991b1b">⚠️ 永豐是<b>本利攤還</b>：月付含本金 → 別只拿利息比現金流</div></div>')
    L.append('</div>')
    # ── 勝負判定 ──
    L.append('<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:14px">')
    L.append('<h3 style="font-size:15px;font-weight:800;margin:0 0 2px;color:#1d1d1f">⚖️ 勝負判定：投資收益 vs 借貸利息</h3>')
    L.append('<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px">')
    L.append(f'<div style="flex:1;min-width:130px;background:#f0fdf4;border:1px solid #86efac;border-radius:10px;padding:10px 12px;text-align:center"><div style="font-size:11px;color:#166534">加權資金成本</div><div style="font-size:22px;font-weight:900;color:#166534">{wacc*100:.2f}%</div><div style="font-size:10px;color:#166534">月息 {_fmt(total_m)}</div></div>')
    L.append(f'<div style="flex:1;min-width:130px;background:#eff6ff;border:1px solid #93c5fd;border-radius:10px;padding:10px 12px;text-align:center"><div style="font-size:11px;color:#1e40af">配息殖利率(當月實收)</div><div style="font-size:22px;font-weight:900;color:#1e40af">{div_yield*100:.2f}%</div><div style="font-size:9.5px;color:#1e40af">實收 {_fmt(div_actual)}</div></div>')
    spread_col = "#16a34a" if spread >= 0 else "#dc2626"
    L.append(f'<div style="flex:1;min-width:130px;background:#f0fdf4;border:1px solid #86efac;border-radius:10px;padding:10px 12px;text-align:center"><div style="font-size:11px;color:#166534">淨利差</div><div style="font-size:22px;font-weight:900;color:{spread_col}">{spread*100:+.2f}pp</div><div style="font-size:9.5px;color:#166534">{light}</div></div>')
    L.append('</div>')
    L.append(f'<div style="font-size:11px;color:#374151;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:8px 10px">✅ 投資面：配息殖利率 {div_yield*100:.2f}% − 資金成本 {wacc*100:.2f}% = 淨利差 {spread*100:+.2f}pp（{light.split("→")[0]}）</div>')
    L.append('</div>')
    # ── 保單真實累計績效 ──
    L.append('<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:14px">')
    L.append('<h3 style="font-size:15px;font-weight:800;margin:0 0 2px;color:#1d1d1f">📋 保單真實累計績效<span style="font-size:10px;background:#064e3b;color:#fff;border-radius:6px;padding:2px 7px;vertical-align:middle;margin-left:6px">真實績效 = 累計配息 + (現值 − 原始成本)</span></h3>')
    L.append('<table style="width:100%;font-size:12.5px;border-collapse:collapse"><tr style="color:#6b7280;border-bottom:2px solid #e5e7eb"><th style="text-align:left;padding:5px 8px">保單</th><th style="text-align:right;padding:5px 8px">投入成本</th><th style="text-align:right;padding:5px 8px">目前現值</th><th style="text-align:right;padding:5px 8px">本金損益</th><th style="text-align:right;padding:5px 8px">累計配息</th><th style="text-align:right;padding:5px 8px">真實績效</th></tr>')
    for nm, cost, cur, cd, real, pl in pol_rows:
        col = "#16a34a" if real >= 0 else "#dc2626"
        L.append(f'<tr><td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;font-weight:700">{T(nm)}</td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #f3f4f6">{_fmt(cost)}</td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #f3f4f6">{_fmt(cur)}</td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #f3f4f6;color:#dc2626">{_fmt(pl, True)}</td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #f3f4f6;color:#16a34a">{_fmt(cd, True)}</td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #f3f4f6;font-weight:800;color:{col}">{_fmt(real, True)}</td></tr>')
    L.append(f'<tr style="background:#f9fafb"><td style="padding:6px 8px;font-weight:700">合計</td><td style="padding:6px 8px;text-align:right;font-weight:700">{_fmt(sum(r[1] for r in pol_rows))}</td><td style="padding:6px 8px;text-align:right;font-weight:700">{_fmt(sum(r[2] for r in pol_rows))}</td><td style="padding:6px 8px;text-align:right;font-weight:700;color:#dc2626">{_fmt(sum(r[5] for r in pol_rows), True)}</td><td style="padding:6px 8px;text-align:right;font-weight:700;color:#16a34a">{_fmt(sum(r[4] for r in pol_rows), True)}</td><td style="padding:6px 8px;text-align:right;font-weight:900;color:#16a34a">{_fmt(real_sum, True)}</td></tr></table>')
    L.append(f'<div style="font-size:11px;color:#065f46;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:8px 10px;margin-top:8px">✅ <b>判定（2026-09-05 核准標準）</b>：月配息估 {_fmt(ins_div_m)} ＞ 保單借貸月息 {_fmt(pledge_m)}，且累計本金+配息 {_fmt(real_sum)} 為正 → <b>{cov}</b></div></div>')
    # ── 國泰轉貸專區 ──
    L.append('<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:14px">')
    L.append('<h3 style="font-size:15px;font-weight:800;margin:0 0 2px;color:#1d1d1f">🏦 國泰轉貸 1,200萬 專區</h3>')
    L.append('<div style="font-size:11px;color:#94a3b8;margin-bottom:8px">借貸資金：投入列帳面、漲跌才計績效｜snapshot 最新真值</div>')
    L.append('<table style="width:100%;font-size:12.5px;border-collapse:collapse"><tr style="color:#6b7280;border-bottom:2px solid #e5e7eb"><th style="text-align:left;padding:5px 8px">標的</th><th style="text-align:right;padding:5px 8px">目前市值</th></tr>')
    for k, v in ct_items:
        L.append(f'<tr><td style="padding:6px 8px;border-bottom:1px solid #f3f4f6">{T(k)}</td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #f3f4f6">{_fmt(v)}</td></tr>')
    pl12 = cur12 - cost12
    L.append(f'<tr style="background:#f9fafb"><td style="padding:6px 8px;font-weight:700">合計 {_fmt(cur12)} vs 投入 12,000,000</td><td style="padding:6px 8px;text-align:right;font-weight:900;color:{"#dc2626" if pl12 < 0 else "#16a34a"}">{_fmt(pl12, True)}</td></tr></table>')
    ok12 = "✅ 配息可 cover 利息（本金+配息 > 借貸成本）" if cathay_div >= cathay_m else "⚠️ 配息不足 cover 利息"
    L.append(f'<div style="font-size:11px;color:#065f46;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:8px 10px;margin-top:8px">富達月配息估 {_fmt(cathay_div)} vs 國泰月息 {_fmt(cathay_m)}（12M×2.6%）→ {ok12}</div></div>')
    L.append('<div style="font-size:10.5px;color:#94a3b8;text-align:center;padding:8px 0 20px">投資績效月報 v3（2026-09-04 定版，9/5 加保單真實績效+國泰專區）｜build_investment_performance.py 自動產生</div>')
    L.append('</div></body></html>')
    Path(BASE / "investment_performance.html").write_text("\n".join(L), encoding="utf-8")
    print("📄 investment_performance.html 已自動產生")


def main():
    today = datetime.date.today()
    if len(sys.argv) > 1:
        ym = sys.argv[1]
        y, m = int(ym[:4]), int(ym[5:7])
    else:
        prev = today.replace(day=1) - datetime.timedelta(days=1)
        y, m = prev.year, prev.month

    month_start = datetime.date(y, m, 1)
    month_end = (datetime.date(y, m + 1, 1) - datetime.timedelta(days=1))
    prev_end = month_start - datetime.timedelta(days=1)
    mk = f"{y:04d}-{m:02d}"

    adj = load_adjust()
    a = adj.get(mk, {}) or {}
    adj_invest = a.get("新增投入", {}) or {}       # {類: 金額}
    adj_src = a.get("資金來源", {}) or {}          # {類: "國泰轉貸 1,200萬"}
    adj_mv = a.get("市值變化", {}) or {}           # {類: 真實市值變化(已剔投入)} 校正優先
    adj_div = a.get("配息", {}) or {}              # {類: 金額} 校正優先，否則自動分類
    adj_interest = a.get("利息", {}) or {}         # {"房貸":x,"保單借貸":y}
    adj_fees = a.get("手續費", {}) or {}           # {類: 金額}
    project = a.get("專案收入", 0)
    adj_costs = a  # 整個月份校正 dict：含 "資金成本"(利率覆蓋) + "配息實收" + "房租實收"
    rate_overrides = a.get("資金成本", {})

    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    db = sqlite3.connect(str(BASE / "dragon_assets.db"))
    end_row = db_asset_on(db, month_end.isoformat())
    start_row = db_asset_on(db, prev_end.isoformat())
    db.close()

    mv_reliable = a.get("市值可靠", True)   # false=月初基準不足/投入時點未知，只列現金型報酬

    # ── 各類帳面市值起訖（db 自動） ──
    mv0 = mv1 = None
    db_start_note = ""
    if end_row:
        mv1 = {"股票": end_row[1], "基金": end_row[2], "保單": end_row[3]}
        if start_row:
            mv0 = {"股票": start_row[1], "基金": start_row[2], "保單": start_row[3]}
            db_start_note = start_row[0]
        else:
            db_start_note = f"（db 自 {end_row[0]} 起，無月初基準）"

    # ── 配息自動分類（若校正未帶） ──
    auto_div = {"股票": 0, "基金": 0, "保單": 0}
    dr = (snap.get("dividend_records") or {}).get(mk, {}) or {}
    for k, v in dr.items():
        if isinstance(v, (int, float)):
            auto_div[classify_dividend(k)] += v

    # ── 利息（校正帶入，fallback 月報慣例） ──
    interest_total = sum(adj_interest.values()) if adj_interest else 0

    print(f"\n📊 投資績效月報 {y:04d}-{m:02d}（細分版：股票/基金/保單）")
    print(f"基準：{db_start_note or '校正檔'} → {end_row[0] if end_row else '校正檔'}")
    print("=" * 58)

    grand = 0
    class_rows = []
    for c in CLASS_KEYS:
        inv = adj_invest.get(c, 0)
        src = adj_src.get(c, "")
        div = adj_div.get(c, auto_div[c])
        fee = adj_fees.get(c, 0)
        print(f"\n■ {c}")
        if mv_reliable:
            # 真實市值變化：校正優先，其次 帳面−投入
            if c in adj_mv:
                real_mv = adj_mv[c]
                gross_mv = real_mv + inv
            elif mv0 and mv1:
                gross_mv = mv1[c] - mv0[c]
                real_mv = gross_mv - inv
            else:
                print(f"  ⚠️ 無基準 → 市值變化需校正檔，先以 0 計")
                real_mv = 0; gross_mv = 0
            print(f"  市值：帳面 {gross_mv:+,.0f}")
            if inv:
                print(f"     − 新增投入 {inv:,.0f}" + (f"（{src}）" if src else "（自有資金）"))
            print(f"     ＝ 真實市值變化 {real_mv:+,.0f}")
        else:
            real_mv = 0
            print(f"  市值：本月基準不足/投入時點未知 → 不計（見備註）")
        print(f"  ＋ 配息實收 {div:+,.0f}")
        if fee:
            print(f"  − 手續費 {-fee:,.0f}")
        sub = real_mv + div - fee
        grand += sub
        class_rows.append({"c": c, "real_mv": real_mv, "div": div, "fee": fee, "sub": sub})
        print(f"  ＝ {c}損益 {sub:+,.0f}" + ("（含市值）" if real_mv else "（現金型：不含市值）"))

    print("\n" + "-" * 58)
    print(f"三類損益合計        {grand:+,.0f}")
    if interest_total:
        print(f"− 投資利息(合計)    {-interest_total:,.0f}" + (f"（{json.dumps(adj_interest, ensure_ascii=False)}）" if adj_interest else ""))
    print("=" * 58)
    perf = grand - interest_total
    print(f"🎯 投資績效（月）= {perf:+,.0f} ＝ {(perf/10000):+.1f} 萬")
    print("=" * 58)
    if project:
        print(f"📦 專案收入(非常態) {project:+,.0f}（另計不混入）")
    print(funding_cost_report(snap, adj_costs, rate_overrides))

    # ── 保單真實累計績效（2026-09-05 核准：配息 vs 本金；本金錨 = 原始成本）──
    _pols = [
        ("安聯 A+B", snap.get("allianz_cost", 8000000), snap.get("allianz_ab_current_value", 0) or 0, snap.get("allianz_cum_dividend", 0) or 0),
        ("第一金 FJ33", snap.get("firstjin_cost", 2000000), snap.get("firstjin_current_value", 0) or 0, snap.get("firstjin_cum_dividend", 0) or 0),
    ]
    print("\n📋 保單真實累計績效（真實績效 = 累計配息 + (現值 − 原始成本)）")
    print("-" * 58)
    _real_sum = 0
    for _nm, _cost, _cur, _cd in _pols:
        _pl = _cur - _cost
        _real = _cd + _pl
        _real_sum += _real
        print(f"  {_nm:12s} 投入 {_cost:>9,.0f}｜現值 {_cur:>9,.0f}｜本金 {_pl:>+10,.0f}｜累計配息 {_cd:>9,.0f}｜真實績效 {_real:>+10,.0f}")
    print(f"  {'合計':12s} 投入 10,000,000｜真實累計績效 {_real_sum:+,.0f}")
    _ins_div_m = (snap.get("allianz_ab_monthly", 0) or 0) + (snap.get("firstjin_monthly", 0) or 0)
    try:
        _loans = load_loans(snap, rate_overrides)
        _pledge_m = next((_l["monthly"] for _l in _loans if "保單借貸" in _l["name"]), 14000)
    except Exception:
        _pledge_m = 14000
    _cov = ("✅ 月配息可持續且累計本金+配息為正 → 保單健康（本金+配息 > 借貸成本）"
            if (_ins_div_m >= _pledge_m and _real_sum > 0) else "⚠️ 需檢視：配息或本金覆蓋不足")
    print(f"  月配息估 {_ins_div_m:,.0f} vs 保單借貸月息 {_pledge_m:,.0f}｜{_cov}")

    # ── 國泰轉貸 1,200萬 專區（2026-09-05：成本 vs 現值，統一最新真值）──
    _ct = (snap.get("funds_breakdown", {}) or {}).get("國泰直購", {}) or {}
    _cur12 = sum(_v for _k, _v in _ct.items() if _k != "note" and isinstance(_v, (int, float)))
    _cost12 = 12000000
    print("\n🏦 國泰轉貸 1,200萬 專區（借貸資金：投入帳面、漲跌才計績效）")
    print("-" * 58)
    for _k, _v in sorted(_ct.items()):
        if _k != "note" and isinstance(_v, (int, float)):
            print(f"  {_k:26s} {_v:>12,.0f}")
    if _cur12:
        print(f"  {'合計現值':26s} {_cur12:>12,.0f}  vs 投入 12,000,000 → 損益 {_cur12 - _cost12:+,.0f}（9/3 報價）")
    _cathay_m = 26000     # 12M @2.6% → 月息 ~26,000
    _cathay_div = 45000   # 富達月配估 0.75%/月 × 600萬（與 run_daily 同源）
    print(f"  月配息估 {_cathay_div:,.0f}（富達） vs 國泰月息 {_cathay_m:,.0f} → "
          f"{'✅ 配息可 cover 利息（本金+配息 > 借貸成本）' if _cathay_div >= _cathay_m else '⚠️ 配息不足 cover 利息'}")
    print("口徑：借貸不計績效（投入列帳面、漲跌才計）；配息當月實收；市值含未實現；本金錨=原始成本")

    # ── 儀表板 HTML 自動產生（2026-09-05：整合進 build，cron 每月重產不掉區塊）──
    try:
        pol_rows = [(_nm, _cost, _cur, _cd, _cd + (_cur - _cost), _cur - _cost)
                    for _nm, _cost, _cur, _cd in _pols]
        ct_items = sorted((_k, _v) for _k, _v in _ct.items()
                          if _k != "note" and isinstance(_v, (int, float)))
        write_dashboard_html(mk, class_rows, interest_total, grand, perf, project,
                             load_loans(snap, rate_overrides), pol_rows, _real_sum,
                             _ins_div_m, _pledge_m, _cov, ct_items, _cur12, _cost12,
                             _cathay_div, _cathay_m, snap)
    except Exception as _e:
        print(f"⚠️ HTML 產生失敗（console 輸出仍可用）：{_e}")


if __name__ == "__main__":
    main()
