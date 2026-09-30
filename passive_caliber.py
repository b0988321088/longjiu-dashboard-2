# -*- coding: utf-8 -*-
"""被動收入口徑單一來源（2026-09-27 建立）

為什麼有這支：
「保守底線 / 當月實收 / 壓力情境」三條線原本在 build_dashboard、run_daily、
build_retirement_plan、build_rebalance_dashboard 各算一次，每次校正口徑就要
改 4 個地方，漏一個就出現兩份數字（2026-09-27 實例：實收房租 77,100 只在
run_daily 生效，儀表板與退休規劃頁仍用常態 80,100）。這裡集中計算，各報表
只負責顯示。

鐵則（改口徑只改這支，不要在報表內重算）：
1. 保守底線（判準層）＝ passive_income.fund_dividend_conservative；
   缺值時以 0 計，不得用當月實收冒充（沿用 INC-248 對策）。
2. 當月實收＝ dividend_month_actual（配息實收）＋ passive_income.rent_monthly_actual
   （房租實收，真值＝當月入帳加總）。**兩者皆以 0 為有效值**（本月尚未收到就是 0），
   不得用 `or` 退回上月欄位（2026-10-01 修：月初曾把 9 月 147,975 顯示成本月實收）。
3. 壓力情境（正式判準）＝ 常態月配 × STRESS_DIV_RATIO ＋ 房租常態 − 洲際W 空置額
   （空置額讀 snapshot.rent_breakdown.洲際W，不寫死）。
   2026-09-28 使用者裁示：原本用「保守配息再砍 20%」是雙重打折（100,000 本身已是
   下緣），等於把下限再打一次 → 判準虛高。改以常態月配（monthly_dividend_total，
   與 PCCR 正式判準同源）為壓力情境基準。
4. 極端情境（參考軌，非判準）＝ 保守配息 × STRESS_DIV_RATIO ＋ 房租常態 − 洲際W 空置額。
   保留原雙重打折口徑，用途：壓力情境若已無缺口，跑道分母會失效 → FI 跑道改用
   極端情境缺口當分母（現金撐得過「配息掉到保守值再打折＋空置」多久）。
5. FI 跑道＝ 現金 ÷ 月缺口 × 30 天；無缺口回 None（顯示為 ∞）。
"""

from __future__ import annotations

STRESS_DIV_RATIO = 0.8          # 壓力／極端情境：配息砍 20%
_FALLBACK_EXPENSE = 162781.0    # 僅在 snapshot 完全缺值時使用（v4 定版月支出）
_FALLBACK_VACANCY = 33000.0     # 僅在 rent_breakdown 缺值時使用（洲際W 月租）


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def scenarios(snap: dict) -> dict:
    """回傳四情境（保守 con / 實收 act / 壓力 stress / 極端 extreme）的
    月被動、覆蓋率、盈餘、FI 跑道。"""
    snap = snap or {}
    pi = snap.get("passive_income") or {}
    exp = _f(snap.get("monthly_expense") or pi.get("monthly_expense"), _FALLBACK_EXPENSE)
    # 2026-09-29 CIO 審查必修3：FI 跑道（＝留停 A 級門檻「跑道 ≥540 天」判準）不得把
    # 質押撥款指定清償款當可用現金 → cash 一律取「可動用」口徑。
    from sot_targets import restricted_cash as _rst_fn   # 單一實作（CIO minor3）
    _restricted = _rst_fn(snap)
    cash = max(0.0, _f(snap.get("cash_total")) - _restricted)
    div_con = _f(pi.get("fund_dividend_conservative"))

    def _present(*vals):
        """回傳第一個「存在」的值（0 視為有效值）；全缺才回 None。

        2026-10-01（使用者核准）：原寫法 `a or b or c` 在本月真值為 0 時會一路
        退回上個月的欄位（實例：10/1 當月配息 0 → 儀表板把 9 月實收 147,975
        顯示成「當月實收」）。0 是有效值，不得當成缺值。
        """
        for v in vals:
            if v is not None:
                return _f(v)
        return None

    # 當月實收配息（本月尚未收到就是 0，不得退回上月）
    div_act = _present(snap.get("dividend_month_actual"), pi.get("dividend_actual_sum"))
    div_act = 0.0 if div_act is None else div_act
    # 常態月配（壓力情境基準）：刻意不吃當月實收（月初 0 → 判準會塌），
    # 也刻意不吃 monthly_dividend_total（那是 dividend_tracker 每天寫的「當月」值）
    div_norm = _present(pi.get("fund_dividend_monthly"), snap.get("dividend_month_expected"))
    div_norm = 0.0 if div_norm is None else div_norm
    rent_norm = _f(pi.get("rent_monthly"))
    rent_act = _present(pi.get("rent_monthly_actual"))
    rent_act = rent_norm if rent_act is None else rent_act
    rb = snap.get("rent_breakdown") or {}
    vacancy = _f(rb.get("洲際W"), _FALLBACK_VACANCY) or _FALLBACK_VACANCY

    def _one(income: float) -> dict:
        gap = exp - income
        return {
            "income": income,
            "coverage": (income / exp * 100.0) if exp else 0.0,
            "surplus": income - exp,
            "gap": max(gap, 0.0),
            "runway_days": (cash / gap * 30.0) if gap > 0 else None,
        }

    return {
        "expense": exp,
        "cash": cash,
        "div_con": div_con, "div_norm": div_norm, "div_act": div_act,
        "rent_norm": rent_norm, "rent_act": rent_act, "vacancy": vacancy,
        "con": _one(div_con + rent_norm),
        "act": _one(div_act + rent_act),
        "stress": _one(div_norm * STRESS_DIV_RATIO + rent_norm - vacancy),
        "extreme": _one(div_con * STRESS_DIV_RATIO + rent_norm - vacancy),
    }


def runway_ref(sc: dict) -> dict:
    """FI 跑道的參考情境＝極端情境（雙重打折口徑）。
    壓力情境（常態口徑）無缺口時分母為 0、跑道失去意義，故跑道一律以極端情境為分母。"""
    return sc.get("extreme") or sc["stress"]


def runway_days(sc: dict):
    return runway_ref(sc).get("runway_days")


def runway_text(days) -> str:
    """FI 跑道文字；None（無缺口）→ ∞（零缺口）。"""
    if days is None:
        return "∞（零缺口）"
    return f"{days:,.0f} 天"


def surplus_text(v: float) -> str:
    return f"{v:+,.0f}"


def coverage_text(cov: float) -> str:
    return f"{cov:.1f}%"


if __name__ == "__main__":   # 自我檢查：python passive_caliber.py
    import json
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshot.json")
    s = scenarios(json.load(open(p, encoding="utf-8")))
    for k, lab in (("con", "保守底線（判準）"), ("act", "當月實收"),
                   ("stress", "壓力情境（判準）"), ("extreme", "極端情境（參考）")):
        d = s[k]
        print(f"{lab}: 月被動 {d['income']:,.0f}｜覆蓋 {d['coverage']:.1f}%｜"
              f"盈餘 {d['surplus']:+,.0f}｜跑道 {runway_text(d['runway_days'])}")
    print(f"輸入：配息保守 {s['div_con']:,.0f}／常態 {s['div_norm']:,.0f}／實收 {s['div_act']:,.0f}｜"
          f"房租常態 {s['rent_norm']:,.0f}／實收 {s['rent_act']:,.0f}｜空置 {s['vacancy']:,.0f}｜"
          f"支出 {s['expense']:,.0f}｜現金 {s['cash']:,.0f}")
