#!/usr/bin/env python3
"""sabbatical_checklist_update.py — 留停驗收表每月更新模組（2026-09-02 定案）
併入既有「每月真值日」流程（不新增 cron）：
  真值日 → 更新資產/負債/現金流 → 跑本模組 → 重算三情境 → 留存當月 → 3個月趨勢 → 紅綠燈
全部動態讀 snapshot.json；寫回 snapshot.sabbatical_checklist。
用法：python sabbatical_checklist_update.py [YYYY-MM]（預設當月）
"""
import json, sys, datetime
from pathlib import Path
import passive_caliber as _pcal  # 2026-09-27 被動收入口徑唯一來源（保守/實收/壓力 + FI 跑道）

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
    # 2026-09-27：三情境改由 passive_caliber 單一來源計算（原本這裡自算一份，
    # 且寫死 33,000 空置／80,100 房租 fallback → 與其他報表各說各話）
    _pcs = _pcal.scenarios(snap)
    passive = _pcs["con"]["income"]
    rent = _pcs["rent_norm"]
    div_c = _pcs["div_con"]
    cash = snap.get("cash_total", 794992) or 0
    rent_net = rent - 26000          # 房租 − 大義街房貸（口徑：9/2 定案）
    liab_cost = 16600                 # 保單借貸 13,333 + 元大證金 3,267（利息）
    coverage = round(_pcs["con"]["coverage"], 1)
    stress = round(_pcs["stress"]["coverage"], 1)
    extreme_income = div_c * 0.7 + rent - _pcs["vacancy"]
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

def sync_acceptance_block(snap, kpis, month):
    """驗收標準區塊的「當期數字」動態化（2026-09-27 校正）。

    背景：原本這段文字是 2026-09-02 手寫進 snapshot 的，之後 9/23 口徑校正
    （保守配息 130,930→100,000）沒回頭重算 → 留下作廢值 129.6%/93.3%/差 33,142，
    且沒有任何腳本會更新它（孤兒死資料，只會被誤讀）。
    修法：由 passive_caliber 真值即時生成，並同步寫入兩處副本
    （sabbatical_checklist 與 startup_plan_three_track 存檔），兩份永遠一致。
    """
    exp = kpis["每月必要生活費"]
    con = kpis["生活費覆蓋率"]
    stress = kpis["壓力情境覆蓋率"]
    passive = kpis["被動現金流"]
    gap_150 = round(exp * 1.5 - passive)
    gap_stress = round(_pcal.scenarios(snap)["stress"]["gap"])
    if con >= 150 and stress >= 100:
        verdict = (f"🟢 已達 A 級門檻（正常 {con}% ≥150%、壓力 {stress}% ≥100%）"
                   f"→ 2027/2 驗收")
    else:
        verdict = (f"{kpis['紅綠燈']}（正常 {con}%／壓力 {stress}%；"
                   f"目標 正常 ≥150%、壓力 ≥100%）→ 持續改善 → 2027/2 再驗收")
    dyn = {
        "現況判定": verdict,
        "現況判定_基準月": month,
        "焦點三件事": [
            f"① 生活費覆蓋率 {con}%→150%（差 {gap_150:,}/月：降支出/降利息→增淨租金→提高投資現金流）",
            f"② 壓力情境 {stress}%→100%（差 {gap_stress:,}/月；買的是抗波動能力，非更高報酬）",
            "③ 3個月趨勢（結構性改善 vs 單月配息時間差）",
        ],
    }
    targets = [
        (snap.setdefault("sabbatical_checklist", {}), "驗收標準_2027_02"),
        ((((snap.get("startup_plan_three_track_0901") or {}).get("final_v2_20260902") or {})
          ), "2027_02財務驗收_A級B級C級"),
    ]
    for holder, key in targets:
        blk = holder.get(key)
        if not isinstance(blk, dict):
            continue
        blk.pop("現況判定_2026_09", None)      # 移除停滯的過期 key
        blk.pop("焦點三件事_舊", None)
        blk.update(dyn)
        holder[key] = blk
    return dyn


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

    # 驗收標準區塊的當期數字動態化（2026-09-27 校正：原本 9/2 手寫、9/23 校正後成孤兒舊值）
    dyn = sync_acceptance_block(snap, kpis, month)

    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")  # INC-184：snapshot canonical=1
    print(f"✅ 留停驗收表 {month} 已更新（寫回 snapshot.sabbatical_checklist）")
    print(f"   被動 {kpis['被動現金流']:,} / 必要生活費 {kpis['每月必要生活費']:,} → 覆蓋率 {kpis['生活費覆蓋率']}%")
    print(f"   壓力情境 {kpis['壓力情境覆蓋率']}%｜極端缺口 {kpis['極端情境']['缺口']:,}/月 → 水庫撐 {kpis['極端情境']['水庫撐月數']} 個月")
    print(f"   {kpis['紅綠燈']}")
    print(f"   驗收等級：{kpis.get('驗收等級', lvl)}")
    if len(months) >= 2:
        covs = [cl["記錄"][m].get("生活費覆蓋率") for m in months]
        print("   覆蓋率趨勢: " + " → ".join(f"{m[2:]}月 {c}%" for m, c in zip(months, covs)))

if __name__ == "__main__":
    main()
