#!/usr/bin/env python3
"""build_retirement_plan.py — 退休規劃報告（2026-09-02 新增）
全部數字動態讀 snapshot.json，禁止硬編碼。產出 retirement_plan_{today}.html。
用法：python build_retirement_plan.py
"""
import json, datetime
import pledge_status as _pf  # 2026-09-13 質押文字唯一來源（動態）
from pathlib import Path

BASE = Path(__file__).resolve().parent
TODAY = datetime.date.today().isoformat()
snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))

pi = snap.get("passive_income", {})
# 2026-09-15：台電月薪（單一真值 snapshot）——原字串寫死 39,727（8 月值），9 月起常態調薪 42,560
sal = int(snap.get("monthly_salary") or snap.get("salary") or 0)
fire_income = pi.get("total_conservative", 0)
fire_cost = pi.get("monthly_expense", 162781)
fire_cov = pi.get("coverage_pct", 0)
rent = pi.get("rent_monthly", 80100)
div_conservative = pi.get("fund_dividend_conservative", 0)
net_worth = snap.get("net_worth", 0)
debt_ratio = snap.get("debt_ratio", 0)
ta = snap.get("total_assets", 0)
tl = snap.get("total_liabilities", 0)
life = snap.get("lifestyle_manifesto", {}).get("items", [])
manifesto_title = snap.get("lifestyle_manifesto", {}).get("title", "理想生活宣言")
# 留停壓力測試/驗收表用別名（2026-09-02）
expense = fire_cost
div_c = div_conservative
cash = snap.get("cash_total", 794992)
liab_cost = 16600  # 保單借貸 13,333 + 元大證金 3,267（利息口徑）

# ── 2026-09-23：本檔過去有多處以字面值寫死「當期」數字（覆蓋率／缺口／驗收等級／
# 基準月標籤／2027/2 目標值），改為一律由 snapshot 動態派生；否則真值校正後
# 報告仍會念舊數字，形成「JSON 已校正、報告沒跟上」的分歧。
_sch = snap.get("sabbatical_checklist", {}) or {}
_sc_t = _sch.get("目標_2027_02", {}) or {}
stress_cov = (div_c * 0.8 + rent - 33000) / expense * 100 if expense else 0.0
cov_band = "非常安全" if fire_cov >= 150 else ("基本安全" if fire_cov >= 120 else "不能完全依賴資產")
cov_band_cls = "green" if fire_cov >= 150 else ("amber" if fire_cov >= 120 else "red")
need_to_150 = max(1.5 * expense - fire_income, 0)
sc_level = (_sch.get("驗收等級", {}) or {}).get("等級", "") or "（待真值日重算）"
sc_level_cls = "green" if sc_level.startswith("A級") else ("amber" if sc_level.startswith("B級") else "red")
goal_expense = (_sc_t.get("每月必要生活費", {}) or {}).get("goal", "—")
goal_passive = (_sc_t.get("被動現金流", {}) or {}).get("goal", "—")
# 成對顯示（2026-09-23）：保守底線＝下緣（風控判斷用）、當月實收＝現況；兩者必須同時出現
div_actual = float(snap.get("dividend_month_actual") or snap.get("monthly_dividend_total") or 0)
fire_income_actual = div_actual + rent          # 當月實收口徑＝配息實收＋房租（與保守底線成對）
fire_cov_actual = fire_income_actual / expense * 100 if expense else 0.0
actual_band = "非常安全" if fire_cov_actual >= 150 else ("基本安全" if fire_cov_actual >= 120 else "不能完全依賴資產")
actual_band_cls = "green" if fire_cov_actual >= 150 else ("amber" if fire_cov_actual >= 120 else "red")
sc_month = (_sch.get("驗收等級", {}) or {}).get("月份", "")
_rec = ((_sch.get("記錄", {}) or {}).get(sc_month, {}) or {}) if sc_month else {}
career_income = _rec.get("第二職涯收入", 0) or 0
career_hours = _rec.get("第二職涯工時", 0) or 0
sc_light = _rec.get("紅綠燈", "") or "（待真值日重算）"

# 退休目標（使用者設定）：退休生活費 38,000/月；理想 FIRE 月花費 40,000
RETIRE_BUDGET = 38000
FIRE_IDEAL = 40000
retire_cov = fire_income / RETIRE_BUDGET * 100 if RETIRE_BUDGET else 0
retire_cov_actual = fire_income_actual / RETIRE_BUDGET * 100 if RETIRE_BUDGET else 0

# 極端情境（配息 −30% ＋ 一間無租 ＋ 大型支出 30萬）：分母可能 ≤0，先算好避免 ZeroDivisionError
_ext_income = div_c * 0.7 + rent - 33000
_ext_cov = (_ext_income / expense * 100) if expense else 0.0
_ext_gap = expense - _ext_income
_ext_months = max(1, round((cash - 300000) / _ext_gap)) if _ext_gap > 0 else 0

# 2029 情境（snapshot/記憶既有定案）
fuda_2029 = 45000          # 富達 600萬 後收B 2029/8 解約免罰，領滿 ~45K/月
stack_arb = "借 2.5-3% 買債 4.8-5%（前提：CPI<3% + 殖利率見頂 + 美元信用未爆）"
after_2029 = fire_income + fuda_2029  # 2029 後月被動（未含疊卷套利）

rows = [
    ("退休目標", f"月生活費 {RETIRE_BUDGET:,}｜理想 FIRE 月花費 {FIRE_IDEAL:,}", "已達成 ✅"),
    ("FIRE 現況", f"被動收入 保守 {fire_income:,}／當月實收 {fire_income_actual:,.0f} vs 開銷 {fire_cost:,}（覆蓋 {fire_cov:.1f}%／{fire_cov_actual:.1f}%）", "✅ 已超越"),
    ("退休後流動性", f"保守 {fire_income:,} vs 維持支出 {fire_cost:,} → 盈餘 +{fire_income - fire_cost:,.0f}；當月實收 {fire_income_actual:,.0f} → +{fire_income_actual - fire_cost:,.0f}", "🟢 正現金流"),
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
.red{{color:#ef4444}}.green{{color:#22c55e}}.amber{{color:#f59e0b}}</style></head><body>
<h1>🏖️ 退休規劃報告</h1>
<p class="meta">產出：{TODAY} ｜ 資料源：snapshot.json（動態讀取）｜ 被動收入 保守底線 = 配息 {div_conservative:,} ＋ 房租 {rent:,} ／ 當月實收 = 配息 {div_actual:,.0f} ＋ 房租 {rent:,}（{sc_month or '當月'}）</p>

<div class="grid">
  <div class="card"><div class="stat"><div class="label">當月被動收入（保守底線·判準）</div><div class="val green">{fire_income:,}</div><div class="label" style="margin-top:4px">配息 {div_conservative:,} ＋ 房租 {rent:,}</div></div></div>
  <div class="card"><div class="stat"><div class="label">當月被動收入（當月實收）</div><div class="val" style="color:#38bdf8">{fire_income_actual:,.0f}</div><div class="label" style="margin-top:4px">配息 {div_actual:,.0f} ＋ 房租 {rent:,}（{sc_month or '當月'}）</div></div></div>
  <div class="card"><div class="stat"><div class="label">當下真實開銷</div><div class="val amber">{fire_cost:,}</div></div></div>
  <div class="card"><div class="stat"><div class="label">FIRE 覆蓋率（保守／實收）</div><div class="val" style="color:{cov_color}">{fire_cov:.1f}% <span style="font-size:15px;color:#94a3b8">／</span> <span class="{actual_band_cls}">{fire_cov_actual:.1f}%</span></div><div class="label" style="margin-top:4px">保守底線（判準）／當月實收</div></div></div>
  <div class="card"><div class="stat"><div class="label">退休生活費覆蓋（38,000 目標）</div><div class="val green">{retire_cov:.0f}% <span style="font-size:15px;color:#94a3b8">／</span> {retire_cov_actual:.0f}%</div><div class="label" style="margin-top:4px">保守底線／當月實收</div></div></div>
</div>
<div class="bar" style="margin-bottom:6px"><div style="width:min({fire_cov:.1f}%,100%)"></div></div>
<div class="bar" style="margin-bottom:6px"><div style="width:min({fire_cov_actual:.1f}%,100%);background:#38bdf8"></div></div>
<p class="meta" style="margin-bottom:16px">覆蓋率條：上＝保守底線 {fire_cov:.1f}%（判準）｜下＝當月實收 {fire_cov_actual:.1f}%（{actual_band}）</p>

<div class="card"><h2>🎯 退休目標達成檢查</h2>
<table><tr><th>項目</th><th>現況</th><th>狀態</th></tr>
{''.join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a,b,c in rows)}
</table></div>

<div class="card"><h2>📊 退休後流動性估算（保守底線 vs 當月實收）</h2>
<table>
<tr><th>項目</th><th>保守底線（判準）</th><th>當月實收（現況）</th></tr>
<tr><td>被動月固定收入（配息＋房租 {rent:,}）</td><td>{fire_income:,}</td><td>{fire_income_actual:,.0f}</td></tr>
<tr><td>退休維持月支出</td><td>{fire_cost:,}</td><td>{fire_cost:,}</td></tr>
<tr><td style="color:#22c55e;font-weight:800">安全退休盈餘</td><td style="color:#22c55e;font-weight:800">+{fire_income - fire_cost:,.0f}</td><td style="color:#22c55e;font-weight:800">+{fire_income_actual - fire_cost:,.0f}</td></tr>
<tr><td>退休生活費目標（使用者設定）</td><td>{RETIRE_BUDGET:,}</td><td>{RETIRE_BUDGET:,}</td></tr>
<tr><td style="color:#22c55e;font-weight:800">對 {RETIRE_BUDGET:,} 目標的覆蓋</td><td style="color:#22c55e;font-weight:800">{retire_cov:.0f}%（{fire_income:,}）</td><td style="color:#22c55e;font-weight:800">{retire_cov_actual:.0f}%（{fire_income_actual:,.0f}）</td></tr>
</table>
<p class="meta">保守底線＝配息基本值 {div_conservative:,}（9/5 定版）＋房租；當月實收＝{sc_month or '當月'}配息實收 {div_actual:,.0f}＋房租。判準一律走保守底線。</p></div>

<div class="card"><h2>📈 2029 升級情境（富達解約 + 疊卷套利）</h2>
<p>富達 600 萬（後收 B 股，CDSC 3 年綁）2029/8 解約免罰 → 領滿約 +45,000/月 → 月被動上看 <b style="color:#22c55e">{after_2029:,}</b>。</p>
<p>2029 後債券疊卷質押套利：{stack_arb}</p>
<p class="callout">前提紅線：CPI &lt; 3% ＋ 殖利率見頂 ＋ 美元信用未爆；不滿足則只領不槓。</p></div>

<div class="card"><h2>🗺️ 三步驟離職計畫 × 財務驗證（8/23 核准主軸）</h2>
<table>
<tr><th>步驟</th><th>期間</th><th>財務關卡（通過才算數）</th></tr>
<tr><td>① 債務優化（高息清零）</td><td>現在 ~ 2027/2</td><td>{_pf.pledge_status_line()}；洲際W轉貸 ≤2.5%；築巢 2.185% 生效 → 負債成本逐階下探</td></tr>
<tr><td>② 留職停薪測試</td><td>2027/2 ~ 2027/8</td><td>薪資 {sal:,} 暫停後，月現金流 = 被動 {fire_income:,}（保守底線）／{fire_income_actual:,.0f}（當月實收） − 支出 {fire_cost:,} = <b style="color:#22c55e">+{fire_income - fire_cost:,}</b>（保守）／<b style="color:#38bdf8">+{fire_income_actual - fire_cost:,.0f}</b>（實收）（不含標案收入）；標案收入為增量；目標盈餘 9萬/月還債 70%</td></tr>
<tr><td>③ 扣除房產淨資產 ≥ 0</td><td>2029-30</td><td>富達解約免罰 +45,000/月 + 債券疊卷套利；高息清零 + 還債進度 → 被動 &gt; 支出、淨資產轉正（現況 {net_worth:,}）</td></tr>
</table>
<p class="callout">關鍵：決策 A（轉型）/ B（延長）/ C（回台電）<b>不影響退休基本盤</b> — 被動收入已覆蓋支出（保守底線 {fire_cov:.1f}%／當月實收 {fire_cov_actual:.1f}%），三步驟的財務關卡是「職業轉換的安全網」，退休規劃獨立運作（財務三桶分離）。</p></div>

<!-- 留停壓力測試（2026-09-02 定位提升：留停=人生財務系統壓力測試） -->
<div class="card"><h2>🧪 留停壓力測試（2027/2 留停 = 財務系統驗證，非單純職涯測試）</h2>
<table>
<tr><th>情境</th><th>假設</th><th>月被動</th><th>覆蓋率</th><th>判定</th></tr>
<tr><td>🟢 正常</td><td>配息/房租/支出正常（保守底線）</td><td>{fire_income:,}</td><td>{fire_cov:.1f}%</td><td class="{cov_band_cls}">{'🟢' if fire_cov>=150 else ('🟡' if fire_cov>=120 else '🔴')} {cov_band}</td></tr>
<tr><td>🟢 正常（當月實收）</td><td>配息實收 {div_actual:,.0f} ＋ 租金 {rent:,}</td><td>{div_actual + rent:,.0f}</td><td>{fire_cov_actual:.1f}%</td><td class="{actual_band_cls}">{'🟢' if fire_cov_actual>=150 else ('🟡' if fire_cov_actual>=120 else '🔴')} {actual_band}</td></tr>
<tr><td>🟡 壓力</td><td>配息 −20% ＋ 洲際W 空置</td><td>{div_c*0.8 + rent - 33000:,.0f}</td><td class="red">{stress_cov:.1f}%</td><td class="red">🔴 &lt;100% → 靠現金水庫</td></tr>
<tr><td>🔴 極端</td><td>配息 −30% ＋ 一間無租 ＋ 大型支出 30萬</td><td>{_ext_income:,.0f}</td><td class="red">{_ext_cov:.1f}%</td><td class="red">🔴 缺口 {_ext_gap:,.0f}/月 → 現金水庫撐 {_ext_months} 個月</td></tr>
</table>
<p class="callout">覆蓋率三層：🟢 &gt;150% 非常安全｜🟡 120-150% 基本安全｜🔴 &lt;120% 不能完全依賴資產（<b>不含一次性資本利得</b>）。<br>
現況 <b class="{cov_band_cls}">{fire_cov:.1f}% = {cov_band}</b>（保守底線）｜當月實收 <b class="{actual_band_cls}">{fire_cov_actual:.1f}% = {actual_band}</b>；壓力情境 {stress_cov:.1f}% 未破 100% — 這是留停前要改善的重點（降負債成本/提高房租淨現金流）。<br>
2027/8-9 雙軌判斷：財務穩定 × 職涯成立 → 第二職涯；財務穩但職涯觀望 → 延長測試；任一不成立 → 回台電（保留台電）。</p></div>

<div class="card"><h2>📋 留停驗收表（每月真值日自動更新 · 3個月趨勢）</h2>
<table>
<tr><th>指標</th><th>{sc_month or '當月'} 基準</th><th>2027/2 目標</th></tr>
<tr><td>每月必要生活費</td><td>{expense:,}</td><td>{goal_expense}</td></tr>
<tr><td>被動現金流（保守底線·判準）</td><td>{fire_income:,}（覆蓋 {fire_cov:.1f}%）</td><td>{goal_passive}</td></tr>
<tr><td>被動現金流（當月實收）</td><td>{div_actual + rent:,.0f}（配息 {div_actual:,.0f}＋租金 {rent:,}，覆蓋 {fire_cov_actual:.1f}%）</td><td>觀察（勿與判準混用）</td></tr>
<tr><td>生活費覆蓋率（判準·保守底線）</td><td class="{('red' if fire_cov<150 else 'green')}">{fire_cov:.1f}%</td><td>≥150%</td></tr>
<tr><td>壓力情境覆蓋率</td><td class="red">{stress_cov:.1f}%</td><td>≥100%</td></tr>
<tr><td>房租淨現金流</td><td>{rent - 26000:,}</td><td>持續改善</td></tr>
<tr><td>投資現金流</td><td>{div_c:,}</td><td>穩定</td></tr>
<tr><td>現金水位</td><td>{cash:,}</td><td>持續增加</td></tr>
<tr><td>每月負債成本</td><td>{liab_cost:,}</td><td>持續下降</td></tr>
<tr><td>第二職涯收入</td><td>{career_income:,}</td><td>不設硬性門檻（負責驗證職涯＋加速還債）</td></tr>
<tr><td>第二職涯工時</td><td>{career_hours:,}</td><td>觀察收入/工時</td></tr>
</table>
<p class="callout"><b>留停紅綠燈（雙指標同時達標才算）</b>：🟢 正常覆蓋率 ≥150% ＋ 🟢 壓力情境 ≥100% ＝ 財務留停安全。<br>
現況：正常 {fire_cov:.1f}%（保守底線·判準）／{fire_cov_actual:.1f}%（當月實收） ＋ 壓力 {stress_cov:.1f}% → <b class="red">{sc_light}</b>（保守底線 {cov_band}；水庫防守）。<br>
被動收入負責基本生活；標案/顧問只負責驗證第二職涯＋加速還債 — 兩者不綁死，才不會為了急著賺錢跑回現場監工。<br>
每月 1 日真值日自動重算（sabbatical_checklist_update.py），留存 3 個月趨勢驗證「結構性改善」非單月巧合。</p></div>

<div class="card"><h2>🎯 2027/2 財務驗收標準（A/B/C 級，判斷權重：當月 &lt; 趨勢 &lt; 壓力 &lt; 現金水位）</h2>
<table>
<tr><th>等級</th><th>條件</th><th>行動</th></tr>
<tr><td>A級 🟢</td><td>正常 ≥150% ＋ 壓力 ≥100% ＋ 3個月趨勢無明顯惡化 ＋ 現金 ≥70萬安全網</td><td>可以放心留停（取得「薪水非生存必需品」選擇權）</td></tr>
<tr><td>B級 🟡</td><td>正常 ≥150% 但壓力接近 100%，或現金水位不足；或正常 120-150% 持續改善中</td><td>延後一點／先補水庫</td></tr>
<tr><td>C級 🔴</td><td>正常未達 120%，或壓力明顯 &lt;100% 且改善無趨勢</td><td>繼續留台電，先修財務結構</td></tr>
</table>
<p class="callout">現況（{sc_month}）：正常 {fire_cov:.1f}%（保守底線·判準）／{fire_cov_actual:.1f}%（當月實收） ／ 壓力 {stress_cov:.1f}% ／ 現金 {cash:,} → <b class="{sc_level_cls}">{sc_level}</b>（維持 🔴 不准留停，2027/2 再驗收）。<br>
三件事：① 保守底線 {fire_cov:.1f}%→150%（差 {need_to_150:,.0f}/月：降支出/降利息→增淨租金→提高投資現金流）② 壓力 {stress_cov:.1f}%→100%（買抗波動能力非更高報酬）③ 3個月趨勢（結構性改善 vs 單月配息時間差）。<br>
核心：2027/2 不是「要不要辭台電」，是「資產系統是否成熟到暫時不依賴薪水」。</p></div>

<div class="card"><h2>🗺️ 三階段目標進度</h2>
<ul>
<li>① 債務優化（高息清零）— 執行中（{_pf.pledge_status_line(style='short')}）</li>
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
