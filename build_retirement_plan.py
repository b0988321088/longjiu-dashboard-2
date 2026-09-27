#!/usr/bin/env python3
"""build_retirement_plan.py — 退休規劃報告（2026-09-02 新增）
全部數字動態讀 snapshot.json，禁止硬編碼。產出 retirement_plan_{today}.html。
用法：python build_retirement_plan.py
"""
import json, datetime
import pledge_status as _pf  # 2026-09-13 質押文字唯一來源（動態）
import passive_caliber as _pcal  # 2026-09-27 被動收入口徑唯一來源（保守/實收/壓力 + FI 跑道）
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
# 現金底線單一來源（9/27 裁示＝70 萬；此處只讀 snapshot，不再寫死）
_thr_cash = ((snap.get("thresholds_2026_0915") or {}).get("現金_twd") or {})
_floor_s = float(_thr_cash.get("合計底線")
                 or (float(_thr_cash.get("生活底線") or 0) + float(_thr_cash.get("追繳緩衝") or 0))
                 or 700000)

# ── 2026-09-23：本檔過去有多處以字面值寫死「當期」數字（覆蓋率／缺口／驗收等級／
# 基準月標籤／2027/2 目標值），改為一律由 snapshot 動態派生；否則真值校正後
# 報告仍會念舊數字，形成「JSON 已校正、報告沒跟上」的分歧。
_sch = snap.get("sabbatical_checklist", {}) or {}
_sc_t = _sch.get("目標_2027_02", {}) or {}
# 2026-09-28：壓力／極端情境一律讀 passive_caliber 單一來源（原本此處自算 div_c×0.8＋空置，
# 口徑校正要改兩處）。壓力＝常態配息×0.8＋常態租金−空置（正式判準）；極端＝保守配息再打折。
# 使用者 2026-09-28 裁示：A 級門檻由「正常 ≥150%」改為三條（保守100%＋壓力100%＋跑道540天
# ＋現金底線），150% 降為加碼級理想值 → 本頁所有門檻文字同步改版。
_SC = _pcal.scenarios(snap)
_stress_income = _SC["stress"]["income"]
stress_cov = _SC["stress"]["coverage"]
_stress_cls = "red" if stress_cov < 100 else "green"
_stress_txt = (f"🔴 &lt;100% → 靠現金水庫" if stress_cov < 100
               else f"🟢 覆蓋 {stress_cov:.1f}% ≥100% → 水庫不動")
_stress_note = (f"壓力情境 {stress_cov:.1f}% 未破 100% — 這是留停前要改善的重點（降負債成本/提高房租淨現金流）"
                if stress_cov < 100 else f"壓力情境 {stress_cov:.1f}% 已 ≥100% — 通過壓力測試")
cov_band = "非常安全" if fire_cov >= 150 else ("基本安全" if fire_cov >= 120 else "不能完全依賴資產")
cov_band_cls = "green" if fire_cov >= 150 else ("amber" if fire_cov >= 120 else "red")
# 2026-09-27：need_to_150 已移除 — 缺口一律讀 snapshot.驗收標準_2027_02（單一來源）
# 2026-09-28：欄位更名「距門檻缺口」（三條門檻）＋「距加碼級缺口_150」（理想值）
sc_level = (_sch.get("驗收等級", {}) or {}).get("等級", "") or "（待真值日重算）"
# 2026-09-28：新增 A+級（加碼級）標籤 → 綠燈；其餘依原規則
sc_level_cls = ("green" if sc_level.startswith(("A級", "A+級"))
                else ("amber" if sc_level.startswith("B級") else "red"))
goal_expense = (_sc_t.get("每月必要生活費", {}) or {}).get("goal", "—")
goal_passive = (_sc_t.get("被動現金流", {}) or {}).get("goal", "—")
# 成對顯示（2026-09-23）：保守底線＝下緣（風控判斷用）、當月實收＝現況；兩者必須同時出現
# 2026-09-27：情境口徑改由 passive_caliber 單一來源計算（_SC 已於上方建立，勿重複建）。
div_actual = _SC["div_act"]
div_norm = _SC["div_norm"]           # 2026-09-28：壓力情境基準（常態月配）
rent_actual = _SC["rent_act"]
fire_income_actual = _SC["act"]["income"]       # 當月實收＝配息實收＋房租實收
fire_cov_actual = _SC["act"]["coverage"]
actual_band = "非常安全" if fire_cov_actual >= 150 else ("基本安全" if fire_cov_actual >= 120 else "不能完全依賴資產")
actual_band_cls = "green" if fire_cov_actual >= 150 else ("amber" if fire_cov_actual >= 120 else "red")
# ── 2026-09-28：覆蓋率條圖尺標改 0–150%（加碼級＝滿格）──
# 原寫法 min(覆蓋%,100%) 會把所有 >100% 的覆蓋率夾成滿格：110.6%（保守）與 138.3%（實收）
# 兩條看起來一樣長，使用者 9/28 提問「綠線藍線一樣長是什麼意思」→ 改為固定尺標＋100% 門檻線。
_BAR_SCALE = 150.0                        # 滿格＝加碼級理想值 150%
_BAR_GATE_X = 100.0 / _BAR_SCALE * 100.0  # 100% 留停門檻線位置（%）
def _bar_w(v):
    return max(0.0, min(float(v) / _BAR_SCALE * 100.0, 100.0))
sc_month = (_sch.get("驗收等級", {}) or {}).get("月份", "")
_rec = ((_sch.get("記錄", {}) or {}).get(sc_month, {}) or {}) if sc_month else {}
career_income = _rec.get("第二職涯收入", 0) or 0
career_hours = _rec.get("第二職涯工時", 0) or 0
sc_light = _rec.get("紅綠燈", "") or "（待真值日重算）"
# ── 2026-09-27：驗收標準區塊改讀 snapshot 單一來源（由 sabbatical_checklist_update.sync_acceptance_block
# 生成），本頁不再自己組文字／自己算缺口。同型分歧（JSON 改了、報告還在念舊值）9/23 與 9/27 各踩一次。
_acc = (_sch.get("驗收標準_2027_02", {}) or {})
_acc_verdict = _acc.get("現況判定", "") or "（待真值日重算）"
_acc_month = _acc.get("現況判定_基準月", "") or sc_month
_acc_gaps = _acc.get("距門檻缺口", {}) or {}
_acc_accel = _acc.get("距加碼級缺口_150", {}) or {}
_acc_todo = [t for t in (_acc.get("焦點三件事", []) or []) if t]


def _runway_gap_row(label, d):
    """跑道缺口列（鍵名與覆蓋率列不同：現況_天／目標_天／缺口_天）。"""
    if not d:
        return ""
    cur = d.get("現況_天")
    tv = d.get("目標_天") or 0
    gap = d.get("缺口_天") or 0
    cls = "green" if gap <= 0 else "red"
    cur_txt = "∞（零缺口）" if cur is None else f"{cur:,.0f} 天"
    gap_txt = "已達標 ✅" if gap <= 0 else f"還缺 {gap:,.0f} 天"
    return (f'<tr><td>{label}</td><td>{cur_txt}</td><td>≥{tv:,.0f} 天</td>'
            f'<td class="{cls}">{gap_txt}</td></tr>')


def _gap_row(label, d):
    if not d:
        return ""
    pv = d.get("現況_pct") or 0
    tv = d.get("目標_pct") or 0
    gap = d.get("月缺口") or 0
    cls = "green" if gap <= 0 else "red"
    gap_txt = "已達標 ✅" if gap <= 0 else f"+{gap:,.0f}/月"
    return (f'<tr><td>{label}</td><td>{pv:.1f}%</td><td>≥{tv}%</td>'
            f'<td class="{cls}">{gap_txt}</td></tr>')


_gap_rows = "".join([
    _gap_row("保守覆蓋率（判準）", _acc_gaps.get("生活費覆蓋率")),
    _gap_row("壓力情境覆蓋率（常態配息口徑）", _acc_gaps.get("壓力情境覆蓋率")),
    _runway_gap_row("FI 跑道（極端情境口徑）", _acc_gaps.get("FI 跑道")),
])
_cash_g = _acc_gaps.get("現金水位") or {}
# 單一來源：餘裕/底線都讀 snapshot（本頁不再自算 cash − 底線，避免頁內第二份實作）
_cash_margin = _cash_g.get("餘裕") or 0
_gfloor = _cash_g.get("底線") or 0
_cash_status = (f'<b class="green">餘裕 {_cash_margin:,}</b>' if _cash_margin >= 0
                else f'<b class="red">不足 {abs(_cash_margin):,}</b>')
_cash_line = (f'現金 {_cash_g.get("現況", 0):,} 對底線 {_gfloor:,} → {_cash_status}'
              if _cash_g else '現金水位（待真值日重算）')
_cash_row = (f'<tr><td>現金水位</td><td>{_cash_g.get("現況", 0):,}</td>'
             f'<td>≥{_cash_g.get("底線", 0):,}</td>'
             f'<td class="{"green" if (_cash_g.get("餘裕") or 0) >= 0 else "red"}">'
             f'{"餘裕" if (_cash_g.get("餘裕") or 0) >= 0 else "不足"} '
             f'{abs(_cash_g.get("餘裕", 0)):,}</td></tr>') if _cash_g else ""
_acc_todo_html = "<br>".join(_acc_todo) if _acc_todo else "（待真值日重算）"
_g150 = _acc_accel.get("月缺口") or 0          # 距加碼級（150%）缺口：理想值·非門檻
_gstress = (_acc_gaps.get("壓力情境覆蓋率") or {}).get("月缺口") or 0
_gcon = (_acc_gaps.get("生活費覆蓋率") or {}).get("月缺口") or 0
_stress_gap_txt = "已達標 ✅" if _gstress <= 0 else f"還缺 <b class=\"red\">+{_gstress:,.0f}</b>／月"

# 退休目標（使用者設定）：退休生活費 38,000/月；理想 FIRE 月花費 40,000
RETIRE_BUDGET = 38000
FIRE_IDEAL = 40000
retire_cov = fire_income / RETIRE_BUDGET * 100 if RETIRE_BUDGET else 0
retire_cov_actual = fire_income_actual / RETIRE_BUDGET * 100 if RETIRE_BUDGET else 0

# 極端情境（配息保守值再 −20% ＋ 洲際W 空置）：單一來源 passive_caliber，
# 與 FI 跑道同分母（現金續航＝跑道天數÷30）；分母可能為 0，先算好避免 ZeroDivisionError
_ext_income = _SC["extreme"]["income"]
_ext_cov = _SC["extreme"]["coverage"]
_ext_gap = _SC["extreme"]["gap"]
_ext_months = round(cash / _ext_gap, 1) if _ext_gap > 0 else 0
_ext_cls = "red" if _ext_gap > 0 else "green"
# ── FI 跑道（現金續航）：四情境一律由 passive_caliber 單一來源（2026-09-28 移除本頁自算）──
_rw_normal = _pcal.runway_text(_SC["con"]["runway_days"])
_rw_actual = _pcal.runway_text(_SC["act"]["runway_days"])
_rw_stress = _pcal.runway_text(_SC["stress"]["runway_days"])
_rw_ext = _pcal.runway_text(_SC["extreme"]["runway_days"])

_ext_txt = (f"🔴 缺口 {_ext_gap:,.0f}/月 → 現金水庫撐 {_ext_months} 個月"
            if _ext_gap > 0 else "🟢 無缺口（水庫不受壓）")

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
.bar{{height:10px;background:#334155;border-radius:6px;overflow:hidden;margin-top:4px;position:relative}}
.bar>div{{height:100%;background:{cov_color};border-radius:6px}}
.bar>i{{position:absolute;top:0;height:100%;width:2px;background:#fbbf24}}
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
<div class="label" style="margin-top:12px">保守底線（判準）<b style="color:#e2e8f0"> {fire_cov:.1f}%</b></div>
<div class="bar"><div style="width:{_bar_w(fire_cov):.1f}%"></div><i style="left:{_BAR_GATE_X:.1f}%"></i></div>
<div class="label" style="margin-top:10px">當月實收 <b class="{actual_band_cls}"> {fire_cov_actual:.1f}%</b></div>
<div class="bar"><div style="width:{_bar_w(fire_cov_actual):.1f}%;background:#38bdf8"></div><i style="left:{_BAR_GATE_X:.1f}%"></i></div>
<p class="meta" style="margin-bottom:16px">尺標 0–{_BAR_SCALE:.0f}%（{_BAR_SCALE:.0f}%＝加碼級理想值滿格）｜黃線＝100% 留停門檻｜上＝保守底線 {fire_cov:.1f}%（判準）、下＝當月實收 {fire_cov_actual:.1f}%（{actual_band}）</p>

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
<tr><th>情境</th><th>假設</th><th>月被動</th><th>覆蓋率</th><th>判定</th><th>現金續航（FI 跑道）</th></tr>
<tr><td>🟢 正常（保守底線）</td><td>配息/房租/支出正常（保守底線 100,000 判準）</td><td>{fire_income:,}</td><td>{fire_cov:.1f}%</td><td class="{cov_band_cls}">{'🟢' if fire_cov>=150 else ('🟡' if fire_cov>=120 else '🔴')} {cov_band}</td><td>{_rw_normal}</td></tr>
<tr><td>🟢 正常（當月實收）</td><td>配息實收 {div_actual:,.0f} ＋ 租金 {rent_actual:,.0f}</td><td>{div_actual + rent_actual:,.0f}</td><td>{fire_cov_actual:.1f}%</td><td class="{actual_band_cls}">{'🟢' if fire_cov_actual>=150 else ('🟡' if fire_cov_actual>=120 else '🔴')} {actual_band}</td><td>{_rw_actual}</td></tr>
<tr><td>🟡 壓力（判準）</td><td>常態配息 −20%（{div_norm:,.0f}→{div_norm*0.8:,.0f}）＋ 洲際W 空置</td><td>{_stress_income:,.0f}</td><td class="{_stress_cls}">{stress_cov:.1f}%</td><td class="{_stress_cls}">{_stress_txt}</td><td>{_rw_stress}</td></tr>
<tr><td>🔴 極端（參考）</td><td>配息掉到保守值 {div_c:,} 再 −20%（≈常態 −46%）＋ 洲際W 空置</td><td>{_ext_income:,.0f}</td><td class="{_ext_cls}">{_ext_cov:.1f}%</td><td class="{_ext_cls}">{_ext_txt}</td><td>{_rw_ext}</td></tr>
</table>
<p class="callout">覆蓋率三層（<b>經驗級距·非留停門檻</b>，僅作相對水位參考）：🟢 &gt;150% 非常安全｜🟡 120-150% 基本安全｜🔴 &lt;120% 不能完全依賴資產（<b>不含一次性資本利得</b>）。留停判定請看三條門檻（保守 ≥100%、壓力 ≥100%、跑道 ≥540 天＋現金 ≥底線），150% 另列為加碼級理想值。<br>
留停門檻＝<b>壓力情境 ≥100%</b>（不是正常 150%）；<b>150% 為加碼級理想值</b>（2026-09-28 使用者裁示降級：壓力情境與跑道指標已直接衡量下檔，150% 屬重複保守）。<br>
現況 <b class="{cov_band_cls}">{fire_cov:.1f}% = {cov_band}</b>（保守底線）｜當月實收 <b class="{actual_band_cls}">{fire_cov_actual:.1f}% = {actual_band}</b>；{_stress_note}。<br>
2027/8-9 雙軌判斷：財務穩定 × 職涯成立 → 第二職涯；財務穩但職涯觀望 → 延長測試；任一不成立 → 回台電（保留台電）。</p></div>

<div class="card"><h2>📋 留停驗收表（每月真值日自動更新 · 3個月趨勢）</h2>
<table>
<tr><th>指標</th><th>{sc_month or '當月'} 基準</th><th>2027/2 目標</th></tr>
<tr><td>每月必要生活費</td><td>{expense:,}</td><td>{goal_expense}</td></tr>
<tr><td>被動現金流（保守底線·判準）</td><td>{fire_income:,}（覆蓋 {fire_cov:.1f}%）</td><td>{goal_passive}</td></tr>
<tr><td>被動現金流（當月實收）</td><td>{div_actual + rent:,.0f}（配息 {div_actual:,.0f}＋租金 {rent:,}，覆蓋 {fire_cov_actual:.1f}%）</td><td>觀察（勿與判準混用）</td></tr>
<tr><td>保守覆蓋率（判準·保守底線）</td><td class="{('red' if fire_cov<100 else 'green')}">{fire_cov:.1f}%</td><td>≥100%（門檻）</td></tr>
<tr><td>壓力情境覆蓋率（常態配息口徑）</td><td class="{_stress_cls}">{stress_cov:.1f}%</td><td>≥100%（門檻）</td></tr>
<tr><td>FI 跑道（極端情境口徑）</td><td class="{('green' if (_SC['extreme']['runway_days'] or 0)>=540 else 'red')}">{_rw_ext}</td><td>≥540 天（門檻）</td></tr>
<tr><td>房租淨現金流</td><td>{rent - 26000:,}</td><td>持續改善</td></tr>
<tr><td>投資現金流</td><td>{div_c:,}</td><td>穩定</td></tr>
<tr><td>現金水位</td><td>{cash:,}</td><td>≥{_floor_s:,.0f}（底線）</td></tr>
<tr><td>加碼級覆蓋率（理想值·非門檻）</td><td class="{('green' if fire_cov>=150 else 'amber')}">{fire_cov:.1f}%</td><td>≥150%</td></tr>
<tr><td>每月負債成本</td><td>{liab_cost:,}</td><td>持續下降</td></tr>
<tr><td>第二職涯收入</td><td>{career_income:,}</td><td>不設硬性門檻（負責驗證職涯＋加速還債）</td></tr>
<tr><td>第二職涯工時</td><td>{career_hours:,}</td><td>觀察收入/工時</td></tr>
</table>
<p class="callout"><b>留停紅綠燈（2026-09-28 改版：三條同時達標才算）</b>：🟢 保守覆蓋 ≥100% ＋ 🟢 壓力情境 ≥100% ＋ 🟢 跑道 ≥540 天 ＋ 🟢 現金 ≥底線 ＝ 財務留停安全。<br>
現況：保守 {fire_cov:.1f}%（判準）／{fire_cov_actual:.1f}%（當月實收） ＋ 壓力 {stress_cov:.1f}% ＋ 跑道 {_rw_ext} → <b class="{'green' if '🟢' in sc_light else ('amber' if '🟡' in sc_light else 'red')}">{sc_light}</b>（保守底線 {cov_band}；水庫防守）。<br>
被動收入負責基本生活；標案/顧問只負責驗證第二職涯＋加速還債 — 兩者不綁死，才不會為了急著賺錢跑回現場監工。<br>
每月 1 日真值日自動重算（sabbatical_checklist_update.py），留存 3 個月趨勢驗證「結構性改善」非單月巧合。</p></div>

<div class="card"><h2>🎯 2027/2 財務驗收標準（A/B/C 級，判斷權重：當月 &lt; 趨勢 &lt; 壓力 &lt; 現金水位）</h2>
<table>
<tr><th>等級</th><th>條件</th><th>行動</th></tr>
<tr><td>A級 🟢</td><td>保守 ≥100% ＋ 壓力 ≥100% ＋ 跑道 ≥540 天 ＋ 現金 ≥底線 ＋ 3個月趨勢無明顯惡化</td><td>可以放心留停（取得「薪水非生存必需品」選擇權）</td></tr>
<tr><td>A+級 🟦</td><td>再加「保守覆蓋 ≥150%」＝加碼級理想值（<b>非門檻</b>；2026-09-28 由門檻降級）</td><td>緩衝更厚，可加速布局</td></tr>
<tr><td>B級 🟡</td><td>保守 ≥100% 但壓力 &lt;100%、跑道 &lt;540 天或現金不足</td><td>可以留但先補水庫</td></tr>
<tr><td>C級 🔴</td><td>保守 &lt;100%（現金流本身不足）</td><td>繼續留台電，先修財務結構</td></tr>
</table>
<p class="callout" style="border-left-color:#ef4444"><b>📏 距門檻缺口（基準月 {_acc_month} · 動態讀 snapshot）</b><br>
保守覆蓋率 {('已達標 ✅' if _gcon <= 0 else '還缺 <b class="red">+' + format(_gcon, ',.0f') + '</b>／月')}、壓力情境 {_stress_gap_txt}；{_cash_line}<br>
<b>加碼級（理想值·非門檻）</b>：覆蓋 {fire_cov:.1f}% → 150% 還差 <b>{_g150:,.0f}</b>／月 — 不影響留停判定。</p>
<table>
<tr><th>指標</th><th>現況</th><th>門檻</th><th>缺口</th></tr>
{_gap_rows}{_cash_row}
</table>
<p class="callout">現況（{sc_month}）：保守 {fire_cov:.1f}%（判準）／{fire_cov_actual:.1f}%（當月實收） ／ 壓力 {stress_cov:.1f}% ／ 跑道 {_rw_ext} ／ 現金 {cash:,} → <b class="{sc_level_cls}">{sc_level}</b><br>
{_acc_verdict}<br>
三件事：<br>{_acc_todo_html}<br>
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
