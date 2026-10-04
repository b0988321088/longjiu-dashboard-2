#!/usr/bin/env python3
"""sabbatical_checklist_update.py — 留停驗收表每月更新模組（2026-09-02 定案）
併入既有「每月真值日」流程（不新增 cron）：
  真值日 → 更新資產/負債/現金流 → 跑本模組 → 重算四情境 → 留存當月 → 3個月趨勢 → 紅綠燈
全部動態讀 snapshot.json；寫回 snapshot.sabbatical_checklist。
用法：python sabbatical_checklist_update.py [YYYY-MM]（預設當月）
"""
import json, sys, datetime
from pathlib import Path
import passive_caliber as _pcal  # 2026-09-27 被動收入口徑唯一來源（保守/實收/壓力 + FI 跑道）
from sot_targets import (sot_monthly_expense, sot_monthly_income,  # INC-270 月支出／月收入單一入口
                         cash_floor as _cf_fn)  # 2026-10-04 P0延伸：現金底線單一入口

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"

# 2027/2 目標（使用者 2026-09-02 定案；2026-09-28 大幅改版——見下方門檻說明）
RUNWAY_GATE_DAYS = 540        # 留停門檻：無薪跑道 ≥540 天（≈18 個月）
ACCEL_GATE_PCT = 150          # 加碼級（理想值·非門檻）：保守覆蓋 ≥150%


# 2026-10-04 P0 延伸：原本地 _cash_floor()（＝第二份 accessor，自帶 700000 fallback）已移除，
# 全部改走 sot_targets.cash_floor 單一入口（缺值 fail-closed）。


def targets(exp, cash_floor):
    """留停門檻（2026-09-28 使用者裁示改版）。

    舊制 A 級＝「正常覆蓋 ≥150% ＋ 壓力 ≥100%」。150% 是拿正常情境的餘裕去間接買
    壓力保護，但系統已有直接的壓力情境與跑道指標 → 同一件事算兩次、門檻虛高
    （保守口徑距 150% 還差 64,072/月，而壓力情境已 ≥100%）。
    新制三條：①保守覆蓋 ≥100% ②壓力情境（常態配息×0.8＋常態租金−空置）≥100%
             ③跑道 ≥540 天 ＋ 現金 ≥ 現金底線。
    150% 降為「加碼級」理想值，不影響留停判定。
    """
    return {
        "每月必要生活費": {"goal": f"≤{exp:,.0f}", "type": "le", "val": round(exp)},
        "被動現金流":     {"goal": f"≥{exp:,.0f}（覆蓋 100%）", "type": "ge", "val": round(exp)},
        "生活費覆蓋率":   {"goal": "≥100%（保守底線·判準）", "type": "ge_pct", "val": 100},
        "壓力情境覆蓋率": {"goal": "≥100%（常態配息×0.8 ＋ 房租常態 − 洲際W空置）", "type": "ge_pct", "val": 100},
        "FI 跑道":        {"goal": f"≥{RUNWAY_GATE_DAYS} 天（極端情境口徑：保守配息×0.8＋空置）",
                          "type": "ge", "val": RUNWAY_GATE_DAYS},
        "現金水位":       {"goal": f"≥{cash_floor:,.0f}（生活底線；餘裕＝乾粉）", "type": "ge", "val": round(cash_floor)},
        "加碼級覆蓋率":   {"goal": f"≥{ACCEL_GATE_PCT}%（理想值·非門檻；原 A 級條件，2026-09-28 降級）",
                          "type": "ge_pct", "val": ACCEL_GATE_PCT},
        "房租淨現金流":   {"goal": "維持（＝常態房租收入；房貸月付已列月支出，不重複扣）", "type": "stable"},
        "投資現金流":     {"goal": "穩定", "type": "stable"},
        "每月負債成本":   {"goal": "持續下降", "type": "trend_down"},
        "第二職涯收入":   {"goal": "不設硬性門檻", "type": "observe"},
        "第二職涯工時":   {"goal": "觀察收入/工時", "type": "observe"},
    }

# 留停紅綠燈（2026-09-28 使用者裁示改版）：三條同時達標 = 財務留停安全
#   ①保守覆蓋 ≥100% ②壓力情境 ≥100% ③跑道 ≥540 天 ＋ 現金 ≥ 現金底線
# 150% 不再是門檻（降為加碼級理想值）。
def traffic_light(coverage, stress_cov, runway_days, cash, cash_floor):
    miss = []
    if coverage < 100:
        miss.append(f"保守覆蓋 {coverage}% <100%")
    if stress_cov < 100:
        miss.append(f"壓力情境 {stress_cov}% <100%")
    if runway_days is not None and runway_days < RUNWAY_GATE_DAYS:
        miss.append(f"跑道 {runway_days:,.0f} 天 <{RUNWAY_GATE_DAYS} 天")
    if cash < cash_floor:
        miss.append(f"現金 {cash:,.0f} < 底線 {cash_floor:,.0f}")
    if not miss:
        return "🟢 財務留停安全（保守 ≥100%、壓力 ≥100%、跑道 ≥540 天＋現金 ≥底線）"
    if coverage >= 100:
        return "🟡 可留但先補水庫（未達：" + "、".join(miss) + "）"
    return "🔴 尚未達留停安全（" + "、".join(miss) + "）"

# 2027/2 留停 Gate（**2026-10-02 使用者裁示改版**）
#   三條硬門檻：自由現金 ≥100 萬＋壓力現金流 ≥100%＋跑道 ≥540 天 → 🟢 GO／🟡 WAIT
#   參考指標（不參與判定）：保守覆蓋、當月實收覆蓋、3 個月趨勢
#   已取消：B 級、A+ 級、健康度分數敘事（保留原始指標供歷史查看）
def acceptance_level(coverage, stress_cov, runway_days, cash, cash_floor, months, trend,
                     free_cash_min=None):
    """留停 Gate（2026-10-02 裁示）：三條硬門檻 → 🟢 GO／🟡 WAIT。

    自由現金 ≥100 萬＋壓力現金流 ≥100%＋跑道 ≥540 天。保守覆蓋與 3 個月趨勢為**參考指標**，
    不參與判定；B 級／A+ 級／健康度分數敘事已取消（原始指標保留供歷史查看）。
    """
    _min = float(free_cash_min or 1000000)
    runway_ok = (runway_days is None) or runway_days >= RUNWAY_GATE_DAYS
    gates = [("自由現金 ≥100 萬", cash >= _min),
             ("壓力現金流 ≥100%", stress_cov >= 100),
             ("跑道 ≥540 天", runway_ok)]
    miss = [n for n, ok in gates if not ok]
    if not miss:
        return "🟢 GO 可以放心留停（Gate 三條全達標）"
    return "🟡 WAIT 尚未取得留停選擇權（未達：" + "、".join(miss) + "）"


def compute_kpis(snap):
    exp = sot_monthly_expense(snap)
    pi = snap.get("passive_income", {})
    # 2026-09-27：三情境改由 passive_caliber 單一來源計算（原本這裡自算一份，
    # 且寫死 33,000 空置／80,100 房租 fallback → 與其他報表各說各話）
    _pcs = _pcal.scenarios(snap)
    passive = _pcs["con"]["income"]
    rent = _pcs["rent_norm"]
    div_c = _pcs["div_con"]
    # 2026-09-29 CIO major：留停 A/B/C 級驗收的現金水位必須是可動用（扣指定用途款），否則 fail-open
    from sot_targets import restricted_cash as _rst_fn
    cash = max(0.0, float(snap.get("cash_total", 0) or 0) - _rst_fn(snap))
    cash_floor = _cf_fn(snap)
    # 2026-09-28 使用者裁示：房貸月付已計入月支出（monthly_fixed_expense 的房貸項），
    # 在房租端再扣一次＝重複計算；且常態房租 80,100 是兩間房的合計，不應拿去減
    # 單一間房的貸款。故房租淨現金流 ＝ 常態房租收入本身（房租無直接成本項）。
    # （同日先前「只扣大義街」與「扣兩筆合計」兩版皆作廢。）
    rent_net = rent
    # 2026-09-30 使用者核准：改由 sot_targets 單一來源動態計算（原寫死 16,600＝保單 13,333＋元大 3,267，
    # 券商清償後不會降、新基金質押月息 13,029 也不會被計入）。
    from sot_targets import liability_interest as _li_fn
    liab_cost = int(_li_fn(snap)["合計"])
    coverage = round(_pcs["con"]["coverage"], 1)
    stress = round(_pcs["stress"]["coverage"], 1)
    # 2026-09-28：極端情境改讀 passive_caliber（原本此處自算 div_c×0.7＋空置，
    # 與壓力情境口徑不一致）；跑道分母同源，現金撐月數＝跑道天數÷30。
    extreme = _pcs["extreme"]
    extreme_gap = extreme["gap"]
    runway_days = _pcal.runway_days(_pcs)
    extreme_months = round(cash / extreme_gap, 1) if extreme_gap > 0 else 999
    return {
        "每月必要生活費": exp, "被動現金流": passive, "房租淨現金流": rent_net,
        "投資現金流": div_c, "現金水位": cash, "現金底線": cash_floor,
        "每月負債成本": liab_cost,
        "生活費覆蓋率": coverage, "壓力情境覆蓋率": stress,
        "壓力情境": {"月被動": _pcs["stress"]["income"], "缺口": round(_pcs["stress"]["gap"])},
        "極端情境": {"月被動": extreme["income"], "缺口": round(extreme_gap),
                     "現金撐月數": extreme_months},
        "FI 跑道天數": runway_days,
        "加碼級缺口_150": round(exp * ACCEL_GATE_PCT / 100 - passive),
        "第二職涯收入": 0, "第二職涯工時": 0,
        "紅綠燈": traffic_light(coverage, stress, runway_days, cash, cash_floor),
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
    _sc = _pcal.scenarios(snap)
    gap_150 = round(exp * ACCEL_GATE_PCT / 100 - passive)      # 加碼級（理想值·非門檻）
    gap_stress = round(_sc["stress"]["gap"])
    _runway = kpis.get("FI 跑道天數")
    _runway_txt = _pcal.runway_text(_runway)
    _floor = float(kpis.get("現金底線") or _cf_fn(snap))
    _cash = float(kpis.get("現金水位") or 0)
    if "🟢" in kpis["紅綠燈"]:
        verdict = (f"🟢 已達留停門檻（保守 {con}% ≥100%、壓力 {stress}% ≥100%、"
                   f"跑道 {_runway_txt} ≥540 天、現金 {_cash:,.0f} ≥底線 {_floor:,.0f}）"
                   f"→ 2027/2 驗收")
    else:
        verdict = (f"{kpis['紅綠燈']}（保守 {con}%／壓力 {stress}%／跑道 {_runway_txt}／"
                   f"現金 {_cash:,.0f} 對底線 {_floor:,.0f}）→ 持續改善 → 2027/2 再驗收")
    dyn = {
        "現況判定": verdict,
        "現況判定_基準月": month,
        # 2026-09-28：等級定義文字同步改版（原本 9/2 手寫，A 級 150% 門檻已被裁示降級為加碼級）
        "定義": "2027/2 是否申請留停 = 看紅綠燈是否連續達標，不靠感覺",
        "判斷權重": "當月數字 < 3個月趨勢 < 壓力情境 < 現金水位（當月最輕、水庫最重）",
        "A級_可以放心留停": (f"保守覆蓋 ≥100% ＋ 壓力情境 ≥100%"
                            f"（常態配息×0.8＋常態租金−洲際W空置） ＋ FI跑道 ≥{RUNWAY_GATE_DAYS} 天"
                            f" ＋ 現金 ≥底線 ＋ 至少3個月趨勢無明顯惡化"
                            f" → 🟢 可以放心留停（取得「薪水非生存必需品」選擇權）"),
        "B級_可以留但先補水庫": "保守 ≥100% 但壓力 <100%、跑道 <540 天或現金不足 → 🟡 可以留但先補水庫",
        "C級_繼續留台電": "保守 <100%（現金流本身不足） → 🔴 繼續留台電，先修財務結構",
        "加碼級_150": f"保守覆蓋 ≥{ACCEL_GATE_PCT}% ＝ 理想值·非門檻（2026-09-28 由 A 級門檻降級）",
        # 2026-09-27：結構化缺口（退休規劃頁等顯示端直接讀，避免各頁各自再算一份口徑）
        # 2026-09-28：A 級門檻由 150% 改為三條（保守 100%／壓力 100%／跑道540天＋現金底線）
        #             → 缺口結構改列「距門檻缺口」，150% 另列「加碼級（理想值）」
        "門檻定義": {
            "保守覆蓋_pct": 100, "壓力情境_pct": 100,
            "FI跑道_天": RUNWAY_GATE_DAYS, "現金_底線": round(_floor),
            "加碼級_覆蓋_pct": ACCEL_GATE_PCT,
        },
        "距門檻缺口": {
            "生活費覆蓋率": {"現況_pct": con, "目標_pct": 100, "月缺口": round(max(exp - passive, 0))},
            "壓力情境覆蓋率": {"現況_pct": stress, "目標_pct": 100, "月缺口": gap_stress},
            "FI 跑道": {"現況_天": _runway, "目標_天": RUNWAY_GATE_DAYS,
                       "文字": _runway_txt,
                       "缺口_天": round(max(RUNWAY_GATE_DAYS - (_runway or 0), 0))},
            "現金水位": {"現況": round(_cash), "底線": round(_floor), "餘裕": round(_cash - _floor)},
        },
        "距加碼級缺口_150": {
            "現況_pct": con, "目標_pct": ACCEL_GATE_PCT, "月缺口": gap_150,
            "說明": "理想值·非門檻（原 A 級條件，2026-09-28 降級；不影響留停判定）",
        },
        "焦點三件事": [
            f"① 門檻三條全達標：保守 {con}%、壓力 {stress}%、跑道 {_runway_txt}＋現金 {_cash:,.0f}",
            f"② 加碼級（理想值·非門檻）：覆蓋 {con}%→150% 還差 {gap_150:,}/月（不影響留停判定）",
            "③ 3個月趨勢（結構性改善 vs 單月配息時間差）",
        ],
    }
    targets = [
        ("sabbatical_checklist", snap.setdefault("sabbatical_checklist", {}), "驗收標準_2027_02"),
        ("startup_plan_three_track_0901.final_v2_20260902",
         ((snap.get("startup_plan_three_track_0901") or {}).get("final_v2_20260902") or {}),
         "2027_02財務驗收_A級B級C級"),
    ]
    missing = []
    for label, holder, key in targets:
        blk = holder.get(key)
        if not isinstance(blk, dict):
            # 2026-09-27：缺塊不可靜默跳過（單邊區塊被刪 → 兩副本無聲漂移，正是本次舊值殘留的成因模式）
            missing.append(f"{label}.{key}")
            continue
        blk.pop("現況判定_2026_09", None)      # 移除停滯的過期 key
        blk.pop("焦點三件事_舊", None)
        # 2026-09-28：門檻改版 → 清掉舊結構 key（否則舊 150% 缺口／78.1% 壓力值會永久殘留，
        # 顯示端一讀就回到舊口徑，這正是 9/23 與 9/27 各踩一次的「孤兒舊值」型態）
        for _legacy in ("距A級缺口", "B級_延後或先補水庫"):
            blk.pop(_legacy, None)
        blk.update(dyn)
        holder[key] = blk
    return dyn, missing


def main():
    month = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y-%m")
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    cl = snap.setdefault("sabbatical_checklist", {})
    cl.setdefault("標題", "留停驗收表（2027/2 前每月記錄）")
    cl.setdefault("記錄", {})

    kpis = compute_kpis(snap)
    # 2026-09-28：目標改由 targets() 依當期支出與現金底線動態生成（不寫死金額）
    cl["目標_2027_02"] = targets(kpis["每月必要生活費"],
                                 kpis.get("現金底線") or _cf_fn(snap))
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
    lvl = acceptance_level(kpis["生活費覆蓋率"], kpis["壓力情境覆蓋率"], kpis.get("FI 跑道天數"),
                           kpis["現金水位"], kpis.get("現金底線") or _cf_fn(snap),
                           months, trend)
    cl["驗收等級"] = {"月份": month, "等級": lvl,
                      "門檻": "保守≥100% ＋ 壓力≥100% ＋ 跑道≥540天 ＋ 現金≥底線 ＋（3月趨勢）",
                      "加碼級": f"覆蓋≥{ACCEL_GATE_PCT}% 為理想值·非門檻",
                      "權重": "當月 < 3個月趨勢 < 壓力情境 < 現金水位"}
    kpis["驗收等級"] = lvl
    cl["記錄"][month] = kpis

    # 驗收標準區塊的當期數字動態化（2026-09-27 校正：原本 9/2 手寫、9/23 校正後成孤兒舊值）
    dyn, missing = sync_acceptance_block(snap, kpis, month)

    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")  # INC-184：snapshot canonical=1
    print(f"✅ 留停驗收表 {month} 已更新（寫回 snapshot.sabbatical_checklist）")
    print(f"   被動 {kpis['被動現金流']:,} / 必要生活費 {kpis['每月必要生活費']:,} → 覆蓋率 {kpis['生活費覆蓋率']}%")
    print(f"   壓力情境 {kpis['壓力情境覆蓋率']}%（常態配息口徑）｜極端缺口 {kpis['極端情境']['缺口']:,}/月"
          f" → 現金撐 {kpis['極端情境']['現金撐月數']} 個月（跑道 {_pcal.runway_text(kpis.get('FI 跑道天數'))}）")
    print(f"   現金 {kpis['現金水位']:,} 對底線 {kpis['現金底線']:,}｜加碼級(150%) 還差 {kpis['加碼級缺口_150']:,}/月（非門檻）")
    print(f"   {kpis['紅綠燈']}")
    print(f"   驗收等級：{kpis.get('驗收等級', lvl)}")
    if len(months) >= 2:
        covs = [cl["記錄"][m].get("生活費覆蓋率") for m in months]
        print("   覆蓋率趨勢: " + " → ".join(f"{m[2:]}月 {c}%" for m, c in zip(months, covs)))
    if missing:
        print("⚠️ 驗收標準區塊缺失、未同步（兩副本漂移風險）：" + "、".join(missing), file=sys.stderr)
        sys.exit(2)          # 主工作已完成，但異常需讓 cron 看見（不靜默）

if __name__ == "__main__":
    main()
