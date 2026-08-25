# -*- coding: utf-8 -*-
"""build_audit_dashboard.py — 每週資產防禦審計儀表板（完整版 2026-08-21）
與文字審計報告同等內容：實相+變動歸因 / Runway 三口徑 / 巴菲特視角 / 行動 / 紅線 / 決策
"""
import json, datetime, os

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
usd_exp = 64.1

recent = [x for x in d["decisions"] if x.get("timestamp", "")[:10] >= "2026-08-08"][-8:][::-1]

def kpi(label, val, sub, color="#3b82f6"):
    return f"""<div style="flex:1;min-width:170px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
  <div style="font-size:12px;color:#6e6e73;margin-bottom:4px">{label}</div>
  <div style="font-size:23px;font-weight:800;color:{color}">{val}</div>
  <div style="font-size:11px;color:#94a3b8;margin-top:4px">{sub}</div></div>"""

W = lambda n: f'style="padding:6px 10px;border-bottom:1px solid #e5e7eb"'
H = lambda t: f"<th style='text-align:left;font-size:12px;color:#6e6e73;padding:6px 10px;border-bottom:2px solid #3b82f6'>{t}</th>"

rows = f"""
<div style="background:#f5f5f7;font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;padding:20px;max-width:1000px;margin:0 auto">
<h1 style="font-size:22px;font-weight:900;margin:0 0 2px">🛡️ 龍九控股 每週資產防禦審計儀表板</h1>
<div style="font-size:13px;color:#6e6e73;margin-bottom:16px">{today} ｜ 真值來源：snapshot.json + Moneybook 8/21 ｜ US30Y {us30y}% {us_light} {mode}</div>

<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">
{kpi("總資產", f"{TA:,}", "不含不動產", "#1d1d1f")}
{kpi("淨值", f"{net_worth:,}", f"資產+不動產−負債", "#3b82f6")}
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
<tr><td {W(0)}>保險</td><td {W(0)} style="text-align:right;font-weight:700">{INS:,}</td><td {W(0)} style="text-align:right">{INS/TA*100:.1f}%</td><td {W(0)} style="color:#6e6e73;font-size:12px">安聯 13:32 7,827,561 + 第一金 FA81 1,939,270</td></tr>
<tr><td {W(0)}>基金</td><td {W(0)} style="text-align:right;font-weight:700">{FUND:,}</td><td {W(0)} style="text-align:right">{FUND/TA*100:.1f}%</td><td {W(0)} style="color:#6e6e73;font-size:12px">鉅亨 801,239 + 國泰 1,200萬（富達600/聯博100/MMF500）</td></tr>
<tr><td {W(0)}>證券</td><td {W(0)} style="text-align:right;font-weight:700">{SEC:,}</td><td {W(0)} style="text-align:right">{SEC/TA*100:.1f}%</td><td {W(0)} style="color:#6e6e73;font-size:12px">16 檔；00888 配息 3,496 入帳</td></tr>
<tr><td {W(0)}>現金</td><td {W(0)} style="text-align:right;font-weight:700">{CASH:,}</td><td {W(0)} style="text-align:right">{CASH/TA*100:.1f}%</td><td {W(0)} style="color:#6e6e73;font-size:12px">8/21 扣 MMF 500萬+聯博 101.5萬 → Moneybook 真值</td></tr>
<tr><td {W(0)}>總資產</td><td {W(0)} style="text-align:right;font-weight:800">{TA:,}</td><td {W(0)}></td><td {W(0)} style="color:#6e6e73;font-size:12px">8/20 撥款 1,200萬 → 部署 600萬富達 + T+2 600萬</td></tr>
<tr><td {W(0)}>總負債</td><td {W(0)} style="text-align:right;font-weight:800;color:#ef4444">{TL:,}</td><td {W(0)}></td><td {W(0)} style="color:#6e6e73;font-size:12px">國泰新貸 1,200萬@2.6%（大義街轉貸）＋ 信用卡 54,402</td></tr>
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
<div style="font-size:12px;color:#6e6e73;margin-top:8px">月固定支出 {FIXED:,} ＝ 生活 {EXP:,} + 房貸 {MORT_MONTHLY:,}（永豐 65,735+國泰 26,000）+ 保單息 {POL_INT:,} + 女友 {GF:,}</div>
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
            f"<span style='color:#22c55e'>✅ 目標內</span>" if abs(diff) <= 1 else
            f"<span style='color:#d97706'>缺 {abs(diff):.1f}pp</span>")
    gap_v = f"{v - tt/100*TA:+,.0f}" if tt else "—"
    rows += f"<tr><td {W(0)}>{t}</td><td {W(0)} style='text-align:right'>{v:,}</td><td {W(0)} style='text-align:right;font-weight:700'>{a:.1f}%</td><td {W(0)} style='text-align:right'>{tt}%</td><td {W(0)} style='text-align:right;font-size:12px'>{mark}（{gap_v}）</td></tr>"
rows += f"""<tr><td {W(0)}>科技曝險</td><td {W(0)} style="text-align:right">{twd.get("美股市值型成長_科技",0):,}</td><td {W(0)} style="text-align:right;font-weight:700">{tech:.1f}%</td><td {W(0)} style="text-align:right">≤15%</td><td {W(0)} style="text-align:right;font-size:12px">{tech_ok}</td></tr>
</table></div>

<div style="flex:1;min-width:340px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">💵 配息資產合併口徑（{dcm.get("佔比","69.5")}%）</h3>
<table style="width:100%;font-size:12.5px;border-collapse:collapse">
<tr>{H('組成')}{H('金額')}{H('佔比')}</tr>
"""
dcc = dcm.get("組成", {})
for name, key in [("保單月配基金","保單月配基金"),("國泰月配(富達C+聯博AD)","國泰月配(富達C+聯博AD)"),("第一金FA81","第一金FA81"),("防守ETF","防守ETF"),("鉅亨月配","鉅亨月配")]:
    v = dcc.get(key, 0)
    rows += f"<tr><td {W(0)}>{name}</td><td {W(0)} style='text-align:right'>{v:,}</td><td {W(0)} style='text-align:right'>{v/TA*100:.1f}%</td></tr>"
rows += f"""<tr><td {W(0)} style="font-weight:700">配息資產合計</td><td {W(0)} style="text-align:right;font-weight:700">{dcm.get("配息資產合計",0):,}</td><td {W(0)} style="text-align:right;font-weight:700">{dcm.get("佔比",0)}%</td></tr>
</table>
<div style="font-size:11px;color:#94a3b8;margin-top:6px">防守桶 4.2% 僅高股息ETF 口徑；合併月配基金後 69.5% — 8/21 裁示防守承接凍結</div>
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
<div style="font-size:26px;font-weight:900">53.8%</div>
<div style="font-size:11px;opacity:.8">債券 22.5% + 現金 22.1% + 低波 4.2% + 避險衛星 5.0%（目標）</div></div>
<div style="flex:1;min-width:220px;background:rgba(255,255,255,.12);border-radius:10px;padding:10px 12px">
<div style="font-size:12px;opacity:.85">💵 收入引擎合計（現金流覆蓋）</div>
<div style="font-size:26px;font-weight:900">69.5%</div>
<div style="font-size:11px;opacity:.8">全配息資產 + 房租 80,100/月</div></div></div>
<div style="font-size:11px;opacity:.8;margin-top:8px">配息≠防守 ｜ 防禦看波動抵抗、現金流看配息收益 ｜ 兩維度獨立計算、互不取代</div>
</div>
<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:14px">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">🎯 四大市場情境門檻（當前：區間震盪 ✅ 全合格）</h3>
<table style="width:100%;font-size:12.5px;border-collapse:collapse">
<tr style="color:#6e6e73"><th style="text-align:left;padding:5px 10px">情境</th><th style="text-align:right;padding:5px 10px">防禦最低</th><th style="text-align:right;padding:5px 10px">收入最低</th><th style="text-align:right;padding:5px 10px">LTV上限</th><th style="text-align:left;padding:5px 10px">核心策略</th></tr>
<tr><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb'>多頭穩定</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥40%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥60%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≤55%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='font-size:11.5px'>追求資本利得</td></tr><tr style="background:#eef2ff;font-weight:700"><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb'>區間震盪（當前）</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥50%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥65%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≤52%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='font-size:11.5px'>穩定擔保、控風險</td></tr><tr><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb'>股債雙殺/升息</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥55%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥70%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≤50%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='font-size:11.5px'>保守、增債保現金</td></tr><tr><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb'>熊市大跌</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥60%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≥70%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='text-align:right'>≤48%</td><td style='padding:5px 10px;border-bottom:1px solid #e5e7eb' style='font-size:11.5px'>全防守、降槓桿</td></tr><tr style="background:#f0f9ff"><td colspan="5" style="padding:6px 10px;font-size:12px">✅ 現況驗證（區間震盪標準）：防禦 <b>53.8%</b> ≥50% ✅ ｜ 收入 <b>69.5%</b> ≥65% ✅ ｜ LTV <b>50%</b> ≤52% ✅ → 完全符合高風險震盪市場最高規格</td></tr>
</table></div>
美元曝險 <b style="color:#ef4444">{usd_exp}%</b>（紅線 50%）→ 選台幣計價避險標的不推高；MMF 轉配置優先累積型</div>
</div></div>

<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:14px">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">🚨 風險紅線檢核</h3>
<table style="width:100%;font-size:13px;border-collapse:collapse">
<tr>{H('紅線')}{H('現況')}{H('判定')}</tr>
<tr><td {W(0)}>US30Y 5.30% 債券凍結</td><td {W(0)}>{us30y}%（警戒區 5.20-5.30）</td><td {W(0)}>{us_light} 距紅線 {max(0, round(5.30-us30y,2)) if us30y else "—"}pp</td></tr>
<tr><td {W(0)}>40,500 停碼</td><td {W(0)}>未觸發</td><td {W(0)}>✅</td></tr>
<tr><td {W(0)}>現金底線 70萬</td><td {W(0)}>{CASH:,}</td><td {W(0)}>{cash_ok}</td></tr>
<tr><td {W(0)}>單次加碼 ≤20萬（核貸期 5萬）</td><td {W(0)}>紀律維持（累積型原則生效）</td><td {W(0)}>✅</td></tr>
<tr><td {W(0)}>美元曝險 ≤50%</td><td {W(0)}>{usd_exp}%</td><td {W(0)}>🔴 超 14.1pp（靠台幣側壓回）</td></tr>
</table></div>

<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px">
<div style="flex:1;min-width:340px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">🧠 巴菲特視角</h3>
<ul style="font-size:13px;line-height:1.95;margin:0;padding-left:20px;color:#1d1d1f">
<li>科技曝險 <b>{tech:.1f}%</b>（≤15 ✅）；富達科技 35% 已納成分拆分</li>
<li>壓力測試：富達 -30%（180萬）+ 聯博 -20%（39萬）≈ 219萬 → 標案池/現金墊 300萬 覆蓋 ✅</li>
<li>0056 質押凍結、00919/00918 停加碼 — 維持</li>
<li>8/31 安聯B 贖回 3% 違約金截止 — 轉換案走 T+4 不受影響</li>
<li>美股 {pen.get("美股市值型成長",0):.1f}% 超目標 4pp — DAA 觀察，不主動新增</li>
</ul></div>
<div style="flex:1;min-width:340px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">🗓️ 下週行動建議</h3>
<ol style="font-size:13px;line-height:1.95;margin:0;padding-left:20px;color:#1d1d1f">
<li><b>8/25（二）T+2 入帳確認</b>：聯博 100萬 + MMF 500萬 入帳 → 四源同步（現金 800,272 → 基金 12,801,239）</li>
<li><b>9/3 PI 認證</b>（2 週到期）：質押 350萬@2.77%（先拿書面）→ 還安聯 300萬 + 元大 50萬；同步避險衛星建倉 131萬（00635U 黃金 105萬 + 00642U 石油 26萬，台幣計價、逢回檔 ≤20萬/次）</li>
<li>MMF 剩餘 ~369萬 → 依「累積型優先」原則轉配置（006208/0050 台幣 + 全球累積 ETF）＋補債券缺口（00983D）→ 壓回美元曝險 &lt;60%</li>
</ol></div></div>

<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">📌 近期決策（近 14 天）</h3>
<table style="width:100%;font-size:12.5px;border-collapse:collapse">
<tr>{H('日期')}{H('決策')}{H('狀態')}</tr>
"""
for x in recent:
    rows += f"<tr><td {W(0)} style='white-space:nowrap'>{x.get('timestamp','')[:10]}</td><td {W(0)}>{x.get('name','')}</td><td {W(0)} style='text-align:right;font-size:12px;color:#6e6e73'>{x.get('status','')}</td></tr>"
rows += f"""</table></div>
<div style="font-size:11px;color:#94a3b8;margin-top:12px;text-align:center">龍九控股自動化審計儀表板（完整版）｜ 下次審計：2026-08-28 17:00 ｜ build_audit_dashboard.py 動態產生</div>
</div>"""

out = os.path.join(REPO, f"audit_dashboard_{today}.html")
open(out, "w", encoding="utf-8").write(rows)
print(f"✅ {out}（{os.path.getsize(out):,} bytes）")
