#!/usr/bin/env python3
"""sabbatical_checklist_update.py — 留停驗收表每月更新模組（2026-09-02 定案）
併入既有「每月真值日」流程（不新增 cron）：
  真值日 → 更新資產/負債/現金流 → 跑本模組 → 重算三情境 → 留存當月 → 3個月趨勢 → 紅綠燈
全部動態讀 snapshot.json；寫回 snapshot.sabbatical_checklist。
用法：python sabbatical_checklist_update.py [YYYY-MM]（預設當月）
"""
import json, sys, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"

# 2027/2 目標（使用者 2026-09-02 定案）
TARGETS = {
    "每月必要生活費": {"goal": "≤162,781", "type": "le", "val": 162781},
    "被動現金流":     {"goal": "≥244,172（162,781×1.5）", "type": "ge", "val": 244172},
    "生活費覆蓋率":   {"goal": "≥150%", "type": "ge_pct", "val": 150},
    "壓力情境覆蓋率": {"goal": "逐步突破 100%", "type": "ge_pct", "val": 100},
    "房租淨現金流":   {"goal": "持續改善", "type": "trend_up"},
    "投資現金流":     {"goal": "穩定", "type": "stable"},
    "現金水位":       {"goal": "持續增加", "type": "trend_up"},
    "每月負債成本":   {"goal": "持續下降", "type": "trend_down"},
    "第二職涯收入":   {"goal": "不設硬性門檻", "type": "observe"},
    "第二職涯工時":   {"goal": "觀察收入/工時", "type": "observe"},
}

# 留停紅綠燈（使用者定案）：正常覆蓋率 ≥150% 且 壓力情境 ≥100% 同時達標 = 財務留停安全
def traffic_light(coverage, stress_cov):
    if coverage >= 150 and stress_cov >= 100:
        return "🟢 財務留停安全（雙指標達標）"
    if coverage >= 150:
        return "🟡 基本安全＋水庫防守（正常達標但壓力情境 <100%）"
    return "🔴 尚未達留停安全（覆蓋率或壓力情境未達）"

# 2027/2 財務驗收等級（2026-09-02 定案）：
# 判斷權重：當月 < 3個月趨勢 < 壓力情境 < 現金水位
# A = 正常≥150 + 壓力≥100 + 3月趨勢無惡化 + 現金≥70萬安全網
# B = 正常≥120 但未全達 A（延後/先補水庫）
# C = 正常<120 或 壓力明顯<100 且無改善趨勢
def acceptance_level(coverage, stress_cov, cash, months, trend):
    cash_ok = cash >= 700000
    trend_ok = len(months) >= 3 and all(
        trend[m]["生活費覆蓋率"] >= trend.get(months[i-1], {}).get("生活費覆蓋率", 0) - 2
        for i, m in enumerate(months[1:], 1) if m in trend and months[i-1] in trend
    ) if months else False
    if coverage >= 150 and stress_cov >= 100 and cash_ok and trend_ok:
        return "A級 🟢 可以放心留停"
    if coverage >= 150:
        why = "壓力情境未破 100%" if stress_cov < 100 else ("現金水位不足" if not cash_ok else "趨勢未滿 3 個月")
        return f"B級 🟡 可以留但先降風險（{why}）"
    if coverage >= 120:
        return "B級 🟡 持續改善中（尚未達 150%，延後或先補水庫）"
    return "C級 🔴 繼續留台電，先修財務結構"

def compute_kpis(snap):
    exp = snap.get("monthly_expense", 162781)
    pi = snap.get("passive_income", {})
    passive = pi.get("total_conservative", 0) or 0
    rent = pi.get("rent_monthly", 80100) or 0
    div_c = pi.get("fund_dividend_conservative", 0) or 0
    cash = snap.get("cash_total", 794992) or 0
    rent_net = rent - 26000          # 房租 − 大義街房貸（口徑：9/2 定案）
    liab_cost = 16600                 # 保單借貸 13,333 + 元大證金 3,267（利息）
    coverage = round(passive / exp * 100, 1) if exp else 0
    stress = round((div_c * 0.8 + rent - 33000) / exp * 100, 1) if exp else 0
    extreme_income = div_c * 0.7 + rent - 33000
    extreme_gap = max(exp - extreme_income, 0)
    extreme_months = round((cash - 300000) / extreme_gap, 1) if extreme_gap > 0 else 999
    return {
        "每月必要生活費": exp, "被動現金流": passive, "房租淨現金流": rent_net,
        "投資現金流": div_c, "現金水位": cash, "每月負債成本": liab_cost,
        "生活費覆蓋率": coverage, "壓力情境覆蓋率": stress,
        "極端情境": {"缺口": round(extreme_gap), "水庫撐月數": extreme_months},
        "第二職涯收入": 0, "第二職涯工時": 0,
        "紅綠燈": traffic_light(coverage, stress),
    }

def main():
    month = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y-%m")
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    cl = snap.setdefault("sabbatical_checklist", {})
    cl.setdefault("標題", "留停驗收表（2027/2 前每月記錄）")
    cl["目標_2027_02"] = TARGETS
    cl.setdefault("記錄", {})

    kpis = compute_kpis(snap)
    # 保留既有 職涯收入/工時（真值日手動帶入，勿覆寫）
    prev = cl["記錄"].get(month, {})
    kpis["第二職涯收入"] = prev.get("第二職涯收入", 0)
    kpis["第二職涯工時"] = prev.get("第二職涯工時", 0)
    kpis["備註"] = "每月真值日自動重算；職涯收入/工時由真值日人工帶入"

    cl["記錄"][month] = kpis
    # 3 個月趨勢：取最近 3 個月覆蓋率（含當月）
    months = sorted(cl["記錄"].keys())[-3:]
    trend = {m: {"生活費覆蓋率": cl["記錄"][m].get("生活費覆蓋率"),
                 "壓力情境覆蓋率": cl["記錄"][m].get("壓力情境覆蓋率"),
                 "被動現金流": cl["記錄"][m].get("被動現金流")} for m in months}
    cl["趨勢_近3月"] = trend
    # 2027/2 財務驗收等級（權重：當月 < 趨勢 < 壓力 < 現金水位）
    lvl = acceptance_level(kpis["生活費覆蓋率"], kpis["壓力情境覆蓋率"], kpis["現金水位"], months, trend)
    cl["驗收等級"] = {"月份": month, "等級": lvl, "權重": "當月 < 3個月趨勢 < 壓力情境 < 現金水位"} 
    kpis["驗收等級"] = lvl
    cl["記錄"][month] = kpis

    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 留停驗收表 {month} 已更新（寫回 snapshot.sabbatical_checklist）")
    print(f"   被動 {kpis['被動現金流']:,} / 必要生活費 {kpis['每月必要生活費']:,} → 覆蓋率 {kpis['生活費覆蓋率']}%")
    print(f"   壓力情境 {kpis['壓力情境覆蓋率']}%｜極端缺口 {kpis['極端情境']['缺口']:,}/月 → 水庫撐 {kpis['極端情境']['水庫撐月數']} 個月")
    print(f"   {kpis['紅綠燈']}")
    print(f"   驗收等級：{kpis.get('驗收等級', lvl)}")
    if len(months) >= 2:
        covs = [cl["記錄"][m].get("生活費覆蓋率") for m in months]
        print(f"   覆蓋率趨勢: " + " → ".join(f"{m[2:]}月 {c}%" for m, c in zip(months, covs)))

if __name__ == "__main__":
    main()
