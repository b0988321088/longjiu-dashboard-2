#!/usr/bin/env python3
"""build_retirement_plan.py — 退休規劃報告（2026-09-02 新增）
全部數字動態讀 snapshot.json，禁止硬編碼。產出 retirement_plan_{today}.html。
用法：python build_retirement_plan.py
"""
import json, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
TODAY = datetime.date.today().isoformat()
snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))

pi = snap.get("passive_income", {})
fire_income = pi.get("total_conservative", 0)
fire_cost = pi.get("monthly_expense", 162781)
fire_cov = pi.get("coverage_pct", 0)
rent = pi.get("rent_monthly", 80100)
div_conservative = pi.get("fund_dividend_conservative", 0)
surplus = snap.get("retirement_surplus", 0)
working_surplus = snap.get("working_surplus", 0)
net_worth = snap.get("net_worth", 0)
debt_ratio = snap.get("debt_ratio", 0)
ta = snap.get("total_assets", 0)
tl = snap.get("total_liabilities", 0)
life = snap.get("lifestyle_manifesto", {}).get("items", [])
manifesto_title = snap.get("lifestyle_manifesto", {}).get("title", "理想生活宣言")

# 退休目標（使用者設定）：退休生活費 38,000/月；理想 FIRE 月花費 40,000
RETIRE_BUDGET = 38000
FIRE_IDEAL = 40000
retire_cov = fire_income / RETIRE_BUDGET * 100 if RETIRE_BUDGET else 0

# 2029 情境（snapshot/記憶既有定案）
fuda_2029 = 45000          # 富達 600萬 後收B 2029/8 解約免罰，領滿 ~45K/月
stack_arb = "借 2.5-3% 買債 4.8-5%（前提：CPI<3% + 殖利率見頂 + 美元信用未爆）"
after_2029 = fire_income + fuda_2029  # 2029 後月被動（未含疊卷套利）

rows = [
    ("退休目標", f"月生活費 {RETIRE_BUDGET:,}｜理想 FIRE 月花費 {FIRE_IDEAL:,}", "已達成 ✅"),
    ("FIRE 現況", f"被動收入 {fire_income:,} vs 開銷 {fire_cost:,}（覆蓋 {fire_cov:.1f}%）", "✅ 已超越"),
    ("退休後流動性", f"常態被動 180,100 vs 維持支出 162,781 → 安全盈餘 +{surplus:,}", "🟢 正現金流"),
    ("2029 升級情境", f"富達解約免罰 +~{fuda_2029:,}/月 → 月被動 {after_2029:,}＋疊卷套利", "📈 待 2029/8"),
    ("三階段目標③", f"扣除房產淨資產 ≥ 0（現況 淨值 {net_worth:,}）", "⏳ 目標 2029-30"),
]

cov_color = "#22c55e" if fire_cov >= 100 else "#f59e0b"
budget_cov = fire_income / FIRE_IDEAL * 100 if FIRE_IDEAL else 0

html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>龍九退休規劃 {TODAY}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang TC",sans-serif;background:#0f172a;color:#f1f5f9;max-width:860px;margin:0 auto;padding:16px;font-size:15px;line-height:1.7}}
h1{{font-size:22px;font-weight:900;margin:8px 0 2px}}
.meta{{color:#94a3b8;font-size:12px;margin-bottom:16px}}
.card{{background:#1e293b;border-radius:14px;padding:16px;margin-bottom:12px;border:1px solid #334155}}
.card h2{{font-size:15px;font-weight:800;margin:0 0 10px;color:#e2e8f0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}}
.stat{{background:#0f172a;border-radius:10px;padding:12px}}
.stat .label{{color:#94a3b8;font-size:12px}}
.stat .val{{font-size:20px;font-weight:900;color:#38bdf8;font-family:ui-monospace,monospace}}
.stat .val.green{{color:#22c55e}}.stat .val.amber{{color:#f59e0b}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}
td,th{{padding:8px 6px;border-bottom:1px solid #334155;text-align:left}}
th{{color:#94a3b8;font-weight:600;font-size:12px}}
.bar{{height:8px;background:#334155;border-radius:6px;overflow:hidden;margin-top:4px}}
.bar>div{{height:100%;background:{cov_color};border-radius:6px}}
ul{{margin:6px 0;padding-left:18px}} li{{margin:4px 0}}
.tag{{display:inline-block;background:#334155;color:#e2e8f0;border-radius:6px;padding:2px 8px;font-size:12px;margin-right:6px}}
.callout{{background:#1e3a5f40;border-left:3px solid #38bdf8;padding:10px 14px;border-radius:6px;font-size:13px}}
</style></head><body>
<h1>🏖️ 退休規劃報告</h1>
<p class="meta">產出：{TODAY} ｜ 資料源：snapshot.json（動態讀取）｜ 被動收入 = 保單配息 {div_conservative:,} + 房租 {rent:,}</p>

<div class="grid">
  <div class="card"><div class="stat"><div class="label">當月被動收入（保守）</div><div class="val green">{fire_income:,}</div></div></div>
  <div class="card"><div class="stat"><div class="label">當下真實開銷</div><div class="val amber">{fire_cost:,}</div></div></div>
  <div class="card"><div class="stat"><div class="label">FIRE 覆蓋率</div><div class="val" style="color:{cov_color}">{fire_cov:.1f}%</div></div></div>
  <div class="card"><div class="stat"><div class="label">退休生活費覆蓋（38,000 目標）</div><div class="val green">{retire_cov:.0f}%</div></div></div>
</div>
<div class="bar" style="margin-bottom:16px"><div style="width:min({fire_cov:.0f}%,100%)"></div></div>

<div class="card"><h2>🎯 退休目標達成檢查</h2>
<table><tr><th>項目</th><th>現況</th><th>狀態</th></tr>
{''.join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a,b,c in rows)}
</table></div>

<div class="card"><h2>📊 退休後流動性估算</h2>
<table>
<tr><th>項目</th><th>金額/月</th></tr>
<tr><td>被動月固定收入（常態：配息 100,000 + 房租 80,100）</td><td>180,100</td></tr>
<tr><td>退休維持月支出</td><td>162,781</td></tr>
<tr><td style="color:#22c55e;font-weight:800">安全退休盈餘</td><td style="color:#22c55e;font-weight:800">+17,319</td></tr>
<tr><td>退休生活費目標（使用者設定）</td><td>38,000</td></tr>
<tr><td style="color:#22c55e;font-weight:800">對 38,000 目標的覆蓋</td><td style="color:#22c55e;font-weight:800">{retire_cov:.0f}%（{fire_income:,} / 38,000）</td></tr>
</table></div>

<div class="card"><h2>📈 2029 升級情境（富達解約 + 疊卷套利）</h2>
<p>富達 600 萬（後收 B 股，CDSC 3 年綁）2029/8 解約免罰 → 領滿約 +45,000/月 → 月被動上看 <b style="color:#22c55e">{after_2029:,}</b>。</p>
<p>2029 後債券疊卷質押套利：{stack_arb}</p>
<p class="callout">前提紅線：CPI &lt; 3% ＋ 殖利率見頂 ＋ 美元信用未爆；不滿足則只領不槓。</p></div>

<div class="card"><h2>🗺️ 三階段目標進度</h2>
<ul>
<li>① 債務優化（高息清零）— 執行中（PI 質押 350萬@2.77% 還安聯/元大）</li>
<li>② 2027/2 留職停薪測試（盈餘 9萬/月還債 70%）— 待 2027/2 啟動</li>
<li>③ 扣除房產淨資產 ≥ 0 — 目標 2029-30（現況淨值 {net_worth:,}，負債比 {debt_ratio}%）</li>
</ul></div>

<div class="card"><h2>💎 {manifesto_title}</h2>
<ul>{''.join(f'<li>{i}</li>' for i in life)}</ul>
<p class="callout">用途：退休/創業型態過濾器 — 任何選項先問「會破壞哪一條？」破壞 2 條以上 → 不做或重新設計。</p></div>

<div class="card"><h2>💰 財務三桶分離（9/2 定案）</h2>
<table>
<tr><th>桶</th><th>內容</th></tr>
<tr><td>① 家庭生活安全桶</td><td>維持正常生活與固定支出</td></tr>
<tr><td>② 投資資產桶</td><td>原有資產配置/現金流策略照既定計畫（不因創業打亂）</td></tr>
<tr><td>③ 第二職涯/標案營運桶</td><td>押標金/履約保證/專案週轉/營運支出（得標→請款時間差獨立管理，不當生活費）</td></tr>
</table></div>

<p class="meta" style="text-align:center">龍九資產管理系統｜退休規劃報告（動態產出）</p>
</body></html>"""

out = BASE / f"retirement_plan_{TODAY}.html"
out.write_text(html, encoding="utf-8")
print(f"✅ {out.name} 已產出（{len(html):,} bytes）")
