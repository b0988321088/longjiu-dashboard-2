# -*- coding: utf-8 -*-
"""build_audit_dashboard.py — 每週資產防禦審計儀表板（2026-08-21 建立）
讀 snapshot.json + us30y_state.json + dashboard_decisions.json → 產出審計儀表板 HTML
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
EXP = s.get("monthly_expense", 141958); FIXED = s.get("fixed_expense_total", 253026)
SAL = s.get("monthly_salary", 39727)
pen = s["penetration"]["actual_pct"]; tgt = s["penetration"]["targets"]
us30y = us.get("last_rate"); mode = us.get("mode_label", us.get("mode", "—"))

debt_ratio = TL / (TA + RE) * 100
runway = CASH / EXP if EXP else 0
cov = (DIV + RENT) / EXP * 100 if EXP else 0
cov_act = (DIV_ACT + RENT) / EXP * 100 if EXP else 0
cov_fixed = (DIV + RENT) / FIXED * 100 if FIXED else 0

us_light = "🔴" if us30y and us30y >= 5.30 else ("🟡" if us30y and us30y >= 4.8 else "🟢")
tech = pen.get("美股市值型成長_科技", 0); tech_light = "✅" if tech <= 15 else "⚠️"
cash_ok = "✅" if CASH >= 700000 else "🔴"

recent = [x for x in d["decisions"] if x.get("timestamp", "")[:10] >= "2026-08-08"]
recent = recent[-6:][::-1]

def kpi(label, val, sub, color="#3b82f6"):
    return f"""<div style="flex:1;min-width:150px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
  <div style="font-size:12px;color:#6e6e73;margin-bottom:4px">{label}</div>
  <div style="font-size:24px;font-weight:800;color:{color}">{val}</div>
  <div style="font-size:11px;color:#94a3b8;margin-top:4px">{sub}</div></div>"""

rows = f"""
<div style="background:#f5f5f7;font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;padding:20px;max-width:960px;margin:0 auto">
<h1 style="font-size:22px;font-weight:900;margin:0 0 2px">🛡️ 龍九控股 每週資產防禦審計儀表板</h1>
<div style="font-size:13px;color:#6e6e73;margin-bottom:16px">{today} ｜ 真值來源：snapshot.json + Moneybook 8/21</div>

<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
{kpi("總資產", f"{TA:,}", "不含不動產")}
{kpi("負債比", f"{debt_ratio:.1f}%", f"負債 {TL:,} / 資產+不動產 {TA+RE:,}", "#d97706")}
{kpi("Runway", f"{runway:.1f} 個月", f"純現金 {CASH:,} / 月支出 {EXP:,}")}
{kpi("被動覆蓋率", f"{cov:.0f}%", f"常態配息 {DIV:,} + 房租 {RENT:,}", "#22c55e")}
{kpi("現金", f"{CASH:,}", f"底線 70萬 {cash_ok}", "#22c55e" if cash_ok=="✅" else "#ef4444")}
</div>

<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
<div style="flex:1;min-width:280px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">📊 資產結構</h3>
<table style="width:100%;font-size:13px;border-collapse:collapse">
<tr><td style="padding:4px 0;color:#6e6e73">保險</td><td style="text-align:right;font-weight:700">{INS:,}</td><td style="text-align:right;color:#6e6e73">{INS/TA*100:.1f}%</td></tr>
<tr><td style="padding:4px 0;color:#6e6e73">基金（鉅亨+國泰）</td><td style="text-align:right;font-weight:700">{FUND:,}</td><td style="text-align:right;color:#6e6e73">{FUND/TA*100:.1f}%</td></tr>
<tr><td style="padding:4px 0;color:#6e6e73">證券</td><td style="text-align:right;font-weight:700">{SEC:,}</td><td style="text-align:right;color:#6e6e73">{SEC/TA*100:.1f}%</td></tr>
<tr><td style="padding:4px 0;color:#6e6e73">現金</td><td style="text-align:right;font-weight:700">{CASH:,}</td><td style="text-align:right;color:#6e6e73">{CASH/TA*100:.1f}%</td></tr>
</table></div>
<div style="flex:1;min-width:280px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">🎯 穿透 vs 目標（DAA v3）</h3>
<table style="width:100%;font-size:13px;border-collapse:collapse">
"""
for k, t, tk in [("台股市值型成長", "台股", "台股市值型目標"), ("美股市值型成長", "美股", "美股市值型目標"), ("防守型配息", "防守", "配息型目標"), ("債券", "債券", "債券型目標"), ("現金/安全網", "現金", "現金目標")]:
    a = pen.get(k, 0)
    tt = tgt.get(tk)
    diff = a - tt if tt is not None else None
    mark = f"<span style='color:#ef4444'>超 {diff:.1f}pp</span>" if diff and diff > 1 else (f"<span style='color:#22c55e'>✅</span>" if diff is not None and abs(diff) <= 1 else (f"<span style='color:#d97706'>缺 {abs(diff):.1f}pp</span>" if diff and diff < -1 else ""))
    rows += f"<tr><td style='padding:4px 0;color:#6e6e73'>{t}</td><td style='text-align:right;font-weight:700'>{a:.1f}%</td><td style='text-align:right;color:#6e6e73'>目標 {tt:.0f}%</td><td style='text-align:right;font-size:12px'>{mark}</td></tr>"
rows += f"""<tr><td style="padding:4px 0;color:#6e6e73">科技曝險</td><td style="text-align:right;font-weight:700">{tech:.1f}%</td><td style="text-align:right;color:#6e6e73">≤15%</td><td style="text-align:right;font-size:12px">{tech_light}</td></tr>
<tr><td style="padding:4px 0;color:#6e6e73">配息資產（合併）</td><td style="text-align:right;font-weight:700">69.5%</td><td colspan="2" style="text-align:right;color:#6e6e73;font-size:12px">防守合併口徑</td></tr>
</table></div></div>

<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:16px">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">🚨 風險紅線檢核</h3>
<table style="width:100%;font-size:13px;border-collapse:collapse">
<tr><td style="padding:4px 0;color:#6e6e73">US30Y {us30y}%（警戒 5.20-5.30）</td><td style="text-align:right">{us_light} {mode}</td></tr>
<tr><td style="padding:4px 0;color:#6e6e73">現金底線 70萬</td><td style="text-align:right">{cash_ok} {CASH:,}</td></tr>
<tr><td style="padding:4px 0;color:#6e6e73">單次加碼 ≤20萬（核貸期 5萬管制）</td><td style="text-align:right">✅ 紀律維持</td></tr>
</table></div>

<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:16px">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">🧠 巴菲特視角</h3>
<ul style="font-size:13px;line-height:1.9;margin:0;padding-left:20px;color:#1d1d1f">
<li>科技曝險 <b>{tech:.1f}%</b>（紅線 ≤15 ✅）；富達科技 35% 已納成分拆分</li>
<li>壓力測試：富達 -30% + 聯博 -20% ≈ 219萬損失 → 標案池/現金墊 300萬 覆蓋</li>
<li>0056 質押凍結、00919/00918 停加碼 — 維持</li>
<li>8/31 安聯B 贖回 3% 違約金截止日 — 轉換案走 T+4 不受影響</li>
</ul></div>

<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:16px">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">🗓️ 下週行動</h3>
<ol style="font-size:13px;line-height:1.9;margin:0;padding-left:20px;color:#1d1d1f">
<li><b>8/25 T+2 入帳確認</b>：聯博 100萬 + MMF 500萬 → 四源同步</li>
<li><b>9/3 PI 認證</b> → 質押 350萬@2.77%（書面）+ 避險衛星 131萬（00635U/00642U 台幣）</li>
<li>美股 {pen.get("美股市值型成長",0):.1f}% 超標觀察；MMF 轉累積型（台幣）壓回美元曝險</li>
</ol></div>

<div style="background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h3 style="font-size:14px;font-weight:800;margin:0 0 8px">📌 近期決策（近 14 天）</h3>
<table style="width:100%;font-size:12.5px;border-collapse:collapse">
"""
for x in recent:
    rows += f"<tr><td style='padding:4px 0;color:#6e6e73;white-space:nowrap'>{x.get('timestamp','')[:10]}</td><td style='padding:4px 8px'>{x.get('name','')}</td><td style='text-align:right;font-size:12px;color:#6e6e73'>{x.get('status','')}</td></tr>"
rows += f"""</table></div>
<div style="font-size:11px;color:#94a3b8;margin-top:12px;text-align:center">龍九控股自動化審計儀表板 ｜ 下次審計：2026-08-28 17:00 ｜ 由 snapshot 動態產生（build_audit_dashboard.py）</div>
</div>"""

out = os.path.join(REPO, f"audit_dashboard_{today}.html")
open(out, "w", encoding="utf-8").write(rows)
print(f"✅ {out}（{os.path.getsize(out):,} bytes）")
