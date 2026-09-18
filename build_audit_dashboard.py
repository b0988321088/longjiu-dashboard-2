# -*- coding: utf-8 -*-
"""build_audit_dashboard.py — 每週資產防禦審計儀表板（完整版 2026-08-21）
與文字審計報告同等內容：實相+變動歸因 / Runway 三口徑 / 巴菲特視角 / 行動 / 紅線 / 決策
"""
import json, datetime, os
import pledge_status as _pf  # 2026-09-13 質押文字唯一來源（動態）

REPO = os.path.dirname(os.path.abspath(__file__))
today = datetime.date.today().strftime("%Y-%m-%d")

s = json.load(open(os.path.join(REPO, "snapshot.json"), encoding="utf-8"))
us = json.load(open(os.path.join(REPO, "us30y_state.json"), encoding="utf-8"))
d = json.load(open(os.path.join(REPO, "dashboard_decisions.json"), encoding="utf-8"))

TA = s["total_assets"]; TL = s["total_liabilities"]; RE = s.get("real_estate_value", 34017063)
INS = s["insurance_current_value"]; SEC = s["securities_total_market_value"]; FUND = s["fund_market_value"]
CASH = s["cash_total"]; RENT = s.get("rent_monthly_total", 80100)
DIV = s.get("monthly_dividend_total", 153389); DIV_ACT = s.get("dividend_month_actual", 97233)
EXP = s.get("monthly_expense", 162781); FIXED = s.get("monthly_fixed_expense", {}).get("合計", 162781)
MORT = 91735; POL_INT = 13333; GF = 6000
pen = s["penetration"]["actual_pct"]; twd = s["penetration"]["actual_twd"]; tgt = s["penetration"]["targets"]
us30y = us.get("last_rate"); mode = us.get("mode_label", us.get("mode", "—"))
hs = s.get("hedge_satellite", {}); dcm = s.get("defensive_combined_metric", {})
# INC-201：雙維度與情境門檻改為派生（原為硬編碼 53.8%/69.5%，與 snapshot.dual_dimension_metric 脫節）
ddm = s.get("dual_dimension_metric", {}) or {}
dd_def = ddm.get("防禦維度", {}) or {}
dd_inc = ddm.get("收入維度", {}) or {}
dd_c = dd_def.get("組成", {}) or {}
_def_pct = dd_def.get("佔比", "—")
_inc_pct = dd_inc.get("佔比", "—")
_ms = s.get("market_scenario_standards", {}) or {}
_sc_cur = next((k for k, v in (_ms.get("情境") or {}).items() if v.get("當前")), "")
_sc = (_ms.get("情境") or {}).get(_sc_cur, {}) or {}
_v = _ms.get("現況驗證", {}) or {}
_ltv_v = _v.get("LTV")
_def_ok = isinstance(_def_pct, (int, float)) and _def_pct >= _sc.get("防禦最低", 0)
_inc_ok = isinstance(_inc_pct, (int, float)) and _inc_pct >= _sc.get("收入最低", 0)
_ltv_ok = isinstance(_ltv_v, (int, float)) and _ltv_v <= _sc.get("LTV上限", 100)
_all_ok = _def_ok and _inc_ok and _ltv_ok
_def_break = " + ".join(f"{k.replace('(目標)','')} {round(v/TA*100,1)}%" for k, v in dd_c.items())
MORT_MONTHLY = s.get("mortgage_cathay_monthly", 26000) + s.get("mortgage_sinopac_monthly", 65735)

debt_ratio = TL / (TA + RE) * 100
net_worth = TA + RE - TL
runway = CASH / EXP if EXP else 0
cov = (DIV + RENT) / EXP * 100
cov_act = (DIV_ACT + RENT) / EXP * 100
cov_fixed = (DIV + RENT) / FIXED * 100
rent_cov_mort = RENT / MORT * 100

us_light = "🔴" if us30y and us30y >= 5.30 else ("🟡" if us30y and us30y >= 4.8 else "🟢")
tech = pen.get("美股市值型成長_科技", 0)
tech_ok = "✅ 紅線下" if tech <= 15 else "⚠️ 超標"
cash_ok = "✅" if CASH >= 700000 else "🔴"
# INC-215（2026-09-18 週五審計抓到）：美元曝險原寫死 64.1（8/22 舊值 + 舊 50% 紅線），
# 與 snapshot.usd_exposure_monitor（9/14 定案 engine 口徑 59.0%、門檻已放寬 60%）脫節 →
# 一律讀 snapshot，門檻/緩衝/判定全部現算。
_usd_m = s.get("usd_exposure_monitor", {}) or {}
usd_thr = float(_usd_m.get("threshold") or 60)
usd_exp = float((_usd_m.get("current") or {}).get("合計") or 0)
usd_gap = round(usd_exp - usd_thr, 1)
usd_col = "#22c55e" if usd_exp <= usd_thr else "#ef4444"
usd_verdict = (f"🟢 未觸線（緩衝 {abs(usd_gap):.1f}pp）" if usd_exp <= usd_thr
               else f"🔴 超 {usd_gap:.1f}pp（靠台幣側壓回）")
# Moneybook 真值日期（原寫死 8/21）與下次審計日（原寫死 2026-08-28）
_mbd = str(s.get("moneybook_date") or "")[:8]
mb_txt = (f"{int(_mbd[4:6])}/{int(_mbd[6:8])}"
          if len(_mbd) == 8 and _mbd.isdigit() else "—")
_next_audit = (datetime.date.fromisoformat(today) + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
LIFE = (s.get("monthly_fixed_expense", {}) or {}).get("生活支出", EXP)
# INC-215b：實相表分項改讀 snapshot 真值（原為寫死金額與舊檔數字：安聯/第一金/鉅亨/信用卡待繳/證券檔數）
ALLZ = s.get("allianz_ab_current_value", 0)
FJ = s.get("firstjin_current_value", 0)
FUND_CT = s.get("funds_cathay_market_value", 0)
FUND_JZ = FUND - FUND_CT
# 證券檔數＝snapshot.securities.holdings 長度（DB 兜底）；未實現損益＝securities.unrealized_pnl；
# 信用卡待繳＝snapshot.credit_card_pending（與 credit_card 四卡合計一致）。
_sec_obj = s.get("securities", {}) or {}
SEC_N = len(_sec_obj.get("holdings", []) or [])
if not SEC_N:
    try:
        import sqlite3 as _sq
        _cx = _sq.connect(os.path.join(REPO, "dragon_assets.db"))
        SEC_N = int(_cx.execute("SELECT COUNT(*) FROM holdings WHERE category='securities'").fetchone()[0])
        _cx.close()
    except Exception:
        SEC_N = 0
SEC_PNL = int(_sec_obj.get("unrealized_pnl", s.get("securities_unrealized_pnl", 0)) or 0)
CC_PEND = int(s.get("credit_card_pending", 0) or 0)
# INC-217：保險列標籤與基金列描述改讀 snapshot 真值（原標籤所指之基金代碼已於 9/16 轉換生效、原描述為
# 四捨五入後的近似金額）→ 標籤取 insurance_label_b、分項金額由 funds_cathay_breakdown 實算。
FJ_NAME = str(s.get("insurance_label_b") or s.get("firstjin_fund_name") or "第一金保單").split("（")[0].strip()
_fcb = s.get("funds_cathay_breakdown", {}) or {}
def _wan(_v):
    try:
        _v = float(_v or 0)
    except (TypeError, ValueError):
        return "—"
    return f"{_v / 10000:,.0f}萬" if _v else "—"
FD = next((_v for _k, _v in _fcb.items() if _k.startswith("富達")), 0)
LB = next((_v for _k, _v in _fcb.items() if _k.startswith("聯博")), 0)
BL = next((_v for _k, _v in _fcb.items() if "貝萊德" in _k and "B11" in _k), 0)

_dec_from = (datetime.date.fromisoformat(today) - datetime.timedelta(days=14)).isoformat()
recent = [x for x in d["decisions"] if x.get("timestamp", "")[:10] >= _dec_from][-8:][::-1]

def kpi(label, val, sub, color="#3b82f6"):
    return f"""<div style="flex:1;min-width:170px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
  <div style="font-size:12px;color:#6e6e73;margin-bottom:4px">{label}</div>
  <div style="font-size:23px;font-weight:800;color:{color}">{val}</div>
  <div style="font-size:11px;color:#94a3b8;margin-top:4px">{sub}</div></div>"""

W = lambda n: 'style="padding:6px 10px;border-bottom:1px solid #e5e7eb"'
H = lambda t: f"<th style='text-align:left;font-size:12px;color:#6e6e73;padding:6px 10px;border-bottom:2px solid #3b82f6'>{t}</th>"

rows = f"""
<div style="background:#f5f5f7;font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;padding:20px;max-width:1000px;margin:0 auto">
<h1 style="font-size:22px;font-weight:900;margin:0 0 2px">🛡️ 龍九控股 每週資產防禦審計儀表板</h1>
<div style="font-size:13px;color:#6e6e73;margin-bottom:16px">{today} ｜ 真值來源：snapshot.json + Moneybook {mb_txt} ｜ US30Y {us30y}% {us_light} {mode}</div>

<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">
{kpi("總資產", f"{TA:,}", "不含不動產", "#1d1d1f")}
{kpi("淨值", f"{net_worth:,}", "資產+不動產−負債", "#3b82f6")}
{kpi("負債比", f"{debt_ratio:.1f}%", f"負債 {TL:,}", "#d97706")}
{kpi("純現金", f"{CASH:,}", f"底線 70萬 {cash_ok}", "#22c55e" if CASH>=700000 else "#ef4444")}
{kpi("Runway", f"{runway:.1f} 月", f"現金 / 月支出 {EXP:,}")}
{kpi("被動覆蓋", f"{cov:.0f}%", f"配息 {DIV:,} + 房租 {RENT:,}", "#22c55e")}
</div>

<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px">
<div style="flex:1.2;min-width:380px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">一、實相更新（本週變動歸因）</h3>
<table style="width:100%;font-size:13px;border-collapse:collapse">
<tr>{H('項目')}{H('金額')}{H('佔比')}{H('本週變動歸因')}</tr>
<tr><td {W(0)}>保險</td><td {W(0)} style="text-align:right;font-weight:700">{INS:,}</td><td {W(0)} style="text-align:right">{INS/TA*100:.1f}%</td><td {W(0)} style="color:#6e6e73;font-size:12px">安聯 {ALLZ:,}（己型+戊型） + {FJ_NAME} {FJ:,}</td></tr>
<tr><td {W(0)}>基金</td><td {W(0)} style="text-align:right;font-weight:700">{FUND:,}</td><td {W(0)} style="text-align:right">{FUND/TA*100:.1f}%</td><td {W(0)} style="color:#6e6e73;font-size:12px">鉅亨 {FUND_JZ:,}（一般申購+自由Pay） + 國泰 {FUND_CT:,}（富達 {_wan(FD)}／聯博 {_wan(LB)}／貝萊德B11 {_wan(BL)} 月配主力）</td></tr>
<tr><td {W(0)}>證券</td><td {W(0)} style="text-align:right;font-weight:700">{SEC:,}</td><td {W(0)} style="text-align:right">{SEC/TA*100:.1f}%</td><td {W(0)} style="color:#6e6e73;font-size:12px">{SEC_N} 檔；未實現 {SEC_PNL:,}</td></tr>
<tr><td {W(0)}>現金</td><td {W(0)} style="text-align:right;font-weight:700">{CASH:,}</td><td {W(0)} style="text-align:right">{CASH/TA*100:.1f}%</td><td {W(0)} style="color:#6e6e73;font-size:12px">Moneybook 銀行帳戶真值（{mb_txt}）；不含 MMF/外幣定存（該部位列基金桶）</td></tr>
<tr><td {W(0)}>總資產</td><td {W(0)} style="text-align:right;font-weight:800">{TA:,}</td><td {W(0)}></td><td {W(0)} style="color:#6e6e73;font-size:12px">8/20 撥款 1,200萬 → 部署 600萬富達 + T+2 600萬</td></tr>
<tr><td {W(0)}>總負債</td><td {W(0)} style="text-align:right;font-weight:800;color:#ef4444">{TL:,}</td><td {W(0)}></td><td {W(0)} style="color:#6e6e73;font-size:12px">國泰新貸 1,200萬@2.6%（大義街轉貸）＋ 信用卡 {CC_PEND:,}</td></tr>
</table></div>

<div style="flex:1;min-width:340px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">二、Runway 與被動覆蓋（三種口徑）</h3>
<table style="width:100%;font-size:13px;border-collapse:collapse">
<tr>{H('口徑')}{H('月收')}{H('覆蓋率')}</tr>
<tr><td {W(0)}>純現金 Runway</td><td {W(0)} style="text-align:right">{CASH:,} / {EXP:,}</td><td {W(0)} style="text-align:right;font-weight:700">{runway:.1f} 個月</td></tr>
<tr><td {W(0)}>被動覆蓋（常態配息）</td><td {W(0)} style="text-align:right">{DIV+RENT:,}</td><td {W(0)} style="text-align:right;font-weight:700;color:#22c55e">{cov:.0f}%</td></tr>
<tr><td {W(0)}>被動覆蓋（當月實收）</td><td {W(0)} style="text-align:right">{DIV_ACT+RENT:,}</td><td {W(0)} style="text-align:right;font-weight:700">{cov_act:.0f}%</td></tr>
<tr><td {W(0)}>全口徑（含房貸/保單息/女友）</td><td {W(0)} style="text-align:right">{DIV+RENT:,} / {FIXED:,}</td><td {W(0)} style="text-align:right;font-weight:700;color:{'#22c55e' if cov_fixed>=100 else '#d97706'}">{cov_fixed:.0f}%</td></tr>
<tr><td {W(0)}>房租覆蓋房貸</td><td {W(0)} style="text-align:right">{RENT:,} / {MORT_MONTHLY:,}</td><td {W(0)} style="text-align:right;font-weight:700">{rent_cov_mort:.0f}%</td></tr>
</table>
<div style="font-size:12px;color:#6e6e73;margin-top:8px">月固定支出 {FIXED:,}（v4 定版）＝ 生活 {LIFE:,} + 房貸 {MORT_MONTHLY:,}（永豐 65,735+國泰 26,000）+ 保單息 {POL_INT:,} + 女友 {GF:,} + 醫療/元大證金等</div>
</div></div>

<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px">
<div style="flex:1.3;min-width:400px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">🎯 穿透五桶 vs DAA v3 目標</h3>
<table style="width:100%;font-size:13px;border-collapse:collapse">
<tr>{H('桶')}{H('金額')}{H('現況')}{H('目標')}{H('差距')}</tr>
"""
for k, t, tk in [("台股市值型成長","台股","台股市值型目標"),("美股市值型成長","美股","美股市值型目標"),("防守型配息","防守","配息型目標"),("債券","債券","債券型目標"),("現金/安全網","現金","現金目標")]:
    a = pen.get(k, 0); v = twd.get(k, 0); tt = tgt.get(tk)
    diff = a - tt
    mark = (f"<span style='color:#ef4444;font-weight:700'>超 {diff:+.1f}pp</span>" if diff > 1 else
            "<span style='color:#22c55e'>✅ 目標內</span>" if abs(diff) <= 1 else
            f"<span style='color:#d97706'>缺 {abs(diff):.1f}pp</span>")
    gap_v = f"{v - tt/100*TA:+,.0f}" if tt else "—"
    rows += f"<tr><td {W(0)}>{t}</td><td {W(0)} style='text-align:right'>{v:,}</td><td {W(0)} style='text-align:right;font-weight:700'>{a:.1f}%</td><td {W(0)} style='text-align:right'>{tt}%</td><td {W(0)} style='text-align:right;font-size:12px'>{mark}（{gap_v}）</td></tr>"
rows += f"""<tr><td {W(0)}>科技曝險</td><td {W(0)} style="text-align:right">{twd.get("美股市值型成長_科技",0):,}</td><td {W(0)} style="text-align:right;font-weight:700">{tech:.1f}%</td><td {W(0)} style="text-align:right">≤20%</td><td {W(0)} style="text-align:right;font-size:12px">{tech_ok}</td></tr>
</table></div>

<div style="flex:1;min-width:340px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">💵 配息資產合併口徑（{dcm.get("佔比","69.5")}%）</h3>
<table style="width:100%;font-size:12.5px;border-collapse:collapse">
<tr>{H('組成')}{H('金額')}{H('佔比')}</tr>
"""
dcc = dcm.get("組成", {})
_dc_order = ["保單月配基金", "國泰月配(富達C+聯博AD)", "防守ETF", "鉅亨月配"]
_dc_items = [(k, k) for k in _dc_order if k in dcc] + [(k, k) for k in dcc if k not in _dc_order]
for name, key in _dc_items:
    v = dcc.get(key, 0)
    rows += f"<tr><td {W(0)}>{name}</td><td {W(0)} style='text-align:right'>{v:,}</td><td {W(0)} style='text-align:right'>{v/TA*100:.1f}%</td></tr>"
rows += f"""<tr><td {W(0)} style="font-weight:700">配息資產合計</td><td {W(0)} style="text-align:right;font-weight:700">{dcm.get("配息資產合計",0):,}</td><td {W(0)} style="text-align:right;font-weight:700">{dcm.get("佔比",0)}%</td></tr>
</table>
<div style="font-size:11px;color:#94a3b8;margin-top:6px">防守桶 {pen.get("防守型配息",0)}% 僅高股息ETF 口徑；合併月配基金後 {dcm.get("佔比",0)}% — 8/21 裁示防守承接凍結</div>
<h3 style="font-size:14px;font-weight:800;margin:16px 0 8px">🛡️ 避險衛星（8/21 核准待 PI）</h3>
<table style="width:100%;font-size:12.5px;border-collapse:collapse">
<tr>{H('衛星')}{H('目標')}{H('現況')}{H('缺口')}</tr>
<tr><td {W(0)}>黃金（00635U）</td><td {W(0)} style="text-align:right">4.0%（105萬）</td><td {W(0)} style="text-align:right">{hs.get("黃金現況",0):,}</td><td {W(0)} style="text-align:right;color:#ef4444;font-weight:700">~104萬</td></tr>
<tr><td {W(0)}>石油（00642U）</td><td {W(0)} style="text-align:right">1.0%（26萬）</td><td {W(0)} style="text-align:right">{hs.get("石油現況",0):,}</td><td {W(0)} style="text-align:right;color:#ef4444;font-weight:700">~26萬</td></tr>
<tr><td {W(0)}>合計 ≤7%</td><td {W(0)} style="text-align:right">5.0%（131萬）</td><td {W(0)} style="text-align:right">~8千</td><td {W(0)} style="text-align:right;color:#ef4444;font-weight:700">~130萬</td></tr>
</table>
<div style="font-size:11px;color:#94a3b8;margin-top:6px"><div style="background:linear-gradient(135deg,#8b5cf6,#6d28d9);border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.1);margin-bottom:14px;color:#fff">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px;color:#fff">🧭 雙維度資產定位（2026-08-21 定稿）</h3>
<div style="display:flex;gap:12px;flex-wrap:wrap">
<div style="flex:1;min-width:220px;background:rgba(255,255,255,.12);border-radius:10px;padding:10px 12px">
<div style="font-size:12px;opacity:.85">🛡️ 防禦維度合計（抗跌/LTV保護）</div>
<div style="font-size:26px;font-weight:900">{_def_pct}%</div>
<div style="font-size:11px;opacity:.8">{_def_break}</div></div>
<div style="flex:1;min-width:220px;background:rgba(255,255,255,.12);border-radius:10px;padding:10px 12px">
<div style="font-size:12px;opacity:.85">💵 收入引擎合計（現金流覆蓋）</div>
<div style="font-size:26px;font-weight:900">{_inc_pct}%</div>
<div style="font-size:11px;opacity:.8">全配息資產 + 房租（合併口徑 {dcm.get("佔比",0)}%）</div></div></div>
<div style="font-size:11px;opacity:.8;margin-top:8px">配息≠防守 ｜ 防禦看波動抵抗、現金流看配息收益 ｜ 兩維度獨立計算、互不取代</div>
</div>
<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:14px">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">🎯 四大市場情境門檻（當前：{_sc_cur} {"✅ 全合格" if _all_ok else "⚠️ 需調整"}）</h3>
<table style="width:100%;font-size:12.5px;border-collapse:collapse">
<tr style="color:#6e6e73"><th style="text-align:left;padding:5px 10px">情境</th><th style="text-align:right;padding:5px 10px">防禦最低</th><th style="text-align:right;padding:5px 10px">收入最低</th><th style="text-align:right;padding:5px 10px">LTV上限</th><th style="text-align:left;padding:5px 10px">核心策略</th></tr>
<tr><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb'>多頭穩定</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥40%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥60%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≤55%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='font-size:11.5px'>追求資本利得</td></tr><tr style="background:#eef2ff;font-weight:700"><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb'>區間震盪（當前）</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥50%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥65%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≤52%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='font-size:11.5px'>穩定擔保、控風險</td></tr><tr><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb'>股債雙殺/升息</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥55%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥70%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≤50%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='font-size:11.5px'>保守、增債保現金</td></tr><tr><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb'>熊市大跌</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥60%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥70%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≤48%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='font-size:11.5px'>全防守、降槓桿</td></tr><tr style="background:#f0f9ff"><td colspan="5" style="padding:6px 10px;font-size:12px">{"✅" if _all_ok else "⚠️"} 現況驗證（{_sc_cur}標準）：防禦 <b>{_def_pct}%</b> ≥{_sc.get("防禦最低",0)}% {"✅" if _def_ok else "❌"} ｜ 收入 <b>{_inc_pct}%</b> ≥{_sc.get("收入最低",0)}% {"✅" if _inc_ok else "❌"} ｜ LTV <b>{_ltv_v}%</b> ≤{_sc.get("LTV上限",0)}% {"✅" if _ltv_ok else "❌"} → 防禦/收入＝dual_dimension_metric 定稿公式派生（不含未建倉部位調整）</td></tr>
</table></div>
美元曝險 <b style="color:{usd_col}">{usd_exp:.1f}%</b>（紅線 {usd_thr:.0f}%）→ 選台幣計價避險標的不推高；MMF 轉配置優先累積型</div>
</div></div>

<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:14px">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">🚨 風險紅線檢核</h3>
<table style="width:100%;font-size:13px;border-collapse:collapse">
<tr>{H('紅線')}{H('現況')}{H('判定')}</tr>
<tr><td {W(0)}>US30Y 5.30% 債券凍結</td><td {W(0)}>{us30y}%（警戒區 5.20-5.30）</td><td {W(0)}>{us_light} 距紅線 {max(0, round(5.30-us30y,2)) if us30y else "—"}pp</td></tr>
<tr><td {W(0)}>40,500 停碼</td><td {W(0)}>未觸發</td><td {W(0)}>✅</td></tr>
<tr><td {W(0)}>現金底線 70萬</td><td {W(0)}>{CASH:,}</td><td {W(0)}>{cash_ok}</td></tr>
<tr><td {W(0)}>單次加碼 ≤20萬（核貸期 5萬）</td><td {W(0)}>紀律維持（累積型原則生效）</td><td {W(0)}>✅</td></tr>
<tr><td {W(0)}>美元曝險 ≤{usd_thr:.0f}%</td><td {W(0)}>{usd_exp:.1f}%</td><td {W(0)}>{usd_verdict}</td></tr>
</table></div>

<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px">
<div style="flex:1;min-width:340px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">🧠 巴菲特視角</h3>
<ul style="font-size:13px;line-height:1.95;margin:0;padding-left:20px;color:#1d1d1f">
<li>科技曝險 <b>{tech:.1f}%</b>（≤20 ✅）；富達科技 35% 已納成分拆分</li>
<li>壓力測試：富達 -30%（180萬）+ 聯博 -20%（39萬）≈ 219萬 → 標案池/現金墊 300萬 覆蓋 ✅</li>
<li>0056 質押凍結、00919/00918 停加碼 — 維持</li>
<li>8/31 安聯B 贖回 3% 違約金截止 — 轉換案走 T+4 不受影響</li>
<li>美股 {pen.get("美股市值型成長",0):.1f}% 超目標 4pp — DAA 觀察，不主動新增</li>
</ul></div>
<div style="flex:1;min-width:340px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">🗓️ 下週行動建議</h3>
<ol style="font-size:13px;line-height:1.95;margin:0;padding-left:20px;color:#1d1d1f">
<li><b>8/25（二）T+2 入帳確認（歷史）</b>：聯博 100萬 + 台幣貨基 500萬 入帳 → 四源同步（現金 800,272 → 基金 12,801,239）｜後續：該 500 萬 9/9 贖回、9/11 轉申購貝萊德 B11（質押擔保池）</li>
<li><b>質押（動態）</b>：{_pf.pledge_status_line()}</li>
<li>⛔ 原「MMF 剩餘 ~369萬 轉配置」已作廢（MMF 9/9 贖回、9/11 轉申購 B11）→ 現行補充資金＝現金流滾存＋9 月底評估押標金來源</li>
</ol></div></div>

<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">📌 近期決策（近 14 天）</h3>
<table style="width:100%;font-size:12.5px;border-collapse:collapse">
<tr>{H('日期')}{H('決策')}{H('狀態')}</tr>
"""
for x in recent:
    rows += f"<tr><td {W(0)} style='white-space:nowrap'>{x.get('timestamp','')[:10]}</td><td {W(0)}>{x.get('name') or x.get('task') or x.get('summary','')}</td><td {W(0)} style='text-align:right;font-size:12px;color:#6e6e73'>{x.get('status','')}</td></tr>"
rows += f"""</table></div>
<div style="font-size:11px;color:#94a3b8;margin-top:12px;text-align:center">龍九控股自動化審計儀表板（完整版）｜ 下次審計：{_next_audit} 17:00 ｜ build_audit_dashboard.py 動態產生</div>
</div>"""

_HEAD = ("<!DOCTYPE html>\n<html lang=\"zh-Hant\">\n"
         "<head><meta charset=\"utf-8\">"
         "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
         "<title>龍九控股稽核儀表板</title></head>\n<body>\n")


def _close_html(html: str) -> str:
    """確保文件以 </body></html> 收尾（缺則補、已有則原樣）— INC-203。
    2026-09-16：audit_dashboard 輸出沒有關閉標籤 → auto_record 截斷檢查擋下整段推送。"""
    h = html.rstrip()
    if not h.lstrip().lower().startswith("<!doctype"):
        h = _HEAD + h
    low = h[-60:].lower()
    if "</html>" in low:
        return h + "\n"
    if "</body>" not in low:
        h += "\n</body>"
    return h + "\n</html>\n"


out = os.path.join(REPO, f"audit_dashboard_{today}.html")
open(out, "w", encoding="utf-8").write(_close_html(rows))
print(f"✅ {out}（{os.path.getsize(out):,} bytes）")
