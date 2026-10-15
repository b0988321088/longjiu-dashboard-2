#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""常態配息層（2026-10-15 使用者裁決）單元測試。

範圍：passive_caliber.scenarios() 新增 "norm" 情境、div_norm 來源改讀
snapshot.monthly_dividend_normal，以及三層口徑隔離。

正向 P1-P3：常態層值與拆解；壓力情境改用常態配息。
負向 N1-N3：缺鍵回退（不得塌成 0、不得退當月實收冒充）。
回歸 R1-R3：保守層、極端情境／跑道、實收層 逐值不變。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import passive_caliber as pc  # noqa: E402

snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
fails: list[str] = []


def ck(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + (("｜" + detail) if detail and not ok else ""))
    if not ok:
        fails.append(name)


def near(a, b, tol=0.05):
    return abs(float(a) - float(b)) < tol


def main() -> int:
    print("常態配息層 — 單元測試")
    sc = pc.scenarios(snap)
    pi = snap["passive_income"]

    # ── 正向 ──────────────────────────────────────────────────────────────
    ck("P1 常態層＝配息常態 177,072 ＋ 租金常態 80,100 ＝ 257,172（覆蓋 161.5%）",
       near(sc["norm"]["income"], 257172) and near(sc["norm"]["coverage"], 161.5)
       and near(sc["norm"]["surplus"], 97962), f"{sc['norm']}")
    ck("P2 拆解等式：基金常態 80,000 ＋ 保單常態 97,072 ＝ 177,072（snapshot 與計算一致）",
       pi.get("fund_dividend_normal_fund") == 80000 and pi.get("fund_dividend_normal_policy") == 97072
       and pi.get("fund_dividend_normal") == 177072
       and snap.get("monthly_dividend_normal") == 177072
       and sc["div_norm"] == 177072)
    ck("P3 壓力情境改用常態配息：177,072×0.8＋80,100−33,000 ＝ 188,758（118.6%）",
       near(sc["stress"]["income"], 188758, 1.0) and near(sc["stress"]["coverage"], 118.6, 0.1),
       f"{sc['stress']}")

    # ── 負向（缺鍵回退；不得塌成 0、不得用當月實收冒充）─────────────────────
    s1 = copy.deepcopy(snap)
    s1.pop("monthly_dividend_normal", None)
    s1["passive_income"].pop("fund_dividend_normal", None)
    a = pc.scenarios(s1)
    ck("N1 只缺常態鍵 → 回退 fund_dividend_monthly（舊行為 170,586／壓力 115.3%）",
       near(a["div_norm"], 170586) and near(a["stress"]["coverage"], 115.3), f"div_norm={a['div_norm']}")
    ck("N1b 回退時不得用當月實收冒充常態",
       not near(a["div_norm"], a["div_act"]), f"norm={a['div_norm']} act={a['div_act']}")

    s2 = copy.deepcopy(snap)
    s2.pop("monthly_dividend_normal", None)
    s2["passive_income"].pop("fund_dividend_normal", None)
    s2["passive_income"].pop("fund_dividend_monthly", None)
    b = pc.scenarios(s2)
    ck("N2 常態鍵全缺 → 回退 dividend_month_expected，且不拋錯",
       near(b["div_norm"], float(snap.get("dividend_month_expected") or 0)), f"div_norm={b['div_norm']}")

    s3 = copy.deepcopy(snap)
    s3["passive_income"]["fund_dividend_conservative"] = 0
    c = pc.scenarios(s3)
    ck("N3 保守鍵為 0 時：保守層照 0 計（不退回實收），常態層不受影響",
       near(c["div_con"], 0) and near(c["extreme"]["income"], 0 * pc.STRESS_DIV_RATIO + c["rent_norm"] - c["vacancy"])
       and near(c["div_norm"], 177072), f"con={c['div_con']} extreme={c['extreme']['income']}")

    # ── 回歸（三層隔離）────────────────────────────────────────────────────
    ck("R1 保守層不變：180,100／113.1%／盈餘 +20,890",
       near(sc["con"]["income"], 180100) and near(sc["con"]["coverage"], 113.1)
       and near(sc["con"]["surplus"], 20890), f"{sc['con']}")
    # R2（2026-10-15 校正）：極端情境的「口徑」不變，但跑道天數＝可動用現金 ÷（月缺口÷30）
    #   → 會隨現金真值移動（10/15 現金真值 1,055,740 → 1,170,934，使跑道 986 → 1,094 天）。
    #   故此處鎖口徑（所得／覆蓋／缺口）並改為「由當日可動用現金推導」驗證，不再凍結 986 這個數字
    #   （凍結會把真值更新誤判成回歸）。
    _ex = sc["extreme"]
    _cash_avail = float(snap.get("cash_total") or 0) - float((snap.get("restricted_cash") or {}).get("金額") or 0)
    _gap_per_day = abs(_ex["surplus"]) / 30 if _ex["surplus"] else 0
    _runway_expect = _cash_avail / _gap_per_day if _gap_per_day else 0
    ck("R2 極端情境口徑不變（127,100／79.8%／−32,110）＋跑道＝可動用現金÷每日缺口",
       near(_ex["income"], 127100) and near(_ex["coverage"], 79.8)
       and near(_ex["surplus"], -32110)
       and near(_ex["runway_days"] or 0, _runway_expect, 3.0),
       f"{_ex}｜推導跑道 {_runway_expect:.1f} 天（可動用 {_cash_avail:,.0f} ÷ 每日缺口 {_gap_per_day:,.1f}）")
    ck("R3 實收層不變：142,909／89.8%／−16,301",
       near(sc["act"]["income"], 142909) and near(sc["act"]["coverage"], 89.8)
       and near(sc["act"]["surplus"], -16301), f"{sc['act']}")

    print(f"\n結果：{11 - len(fails)} PASS / {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
