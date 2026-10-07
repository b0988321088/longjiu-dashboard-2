#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""defense_caliber_trial.py — 卡③「防禦資產」完整口徑【試算，唯讀】。

使用者 2026-10-07 裁決：第 3 張卡只能做到
    現行 49.3% → 候選口徑 X% → 差異原因 → 逐檔證據 → 送 CIO 裁決
**不得改動正式數字**（本檔全程只讀 snapshot，輸出 trial 檔，不寫回 snapshot）。

核心問題：防禦資產應依「資產本質」判定，還是依「來源／桶位」判定？
現行防禦維度公式（snapshot.dual_dimension_metric.防禦維度.公式）：
    債券 + 現金/貨幣 + 低波防禦權益 + 配息型基金權益(平衡型收益基金權益部位) + 避險衛星
→ 「配息型基金權益」目前只算 B11（國泰直購），「低波高股息防禦」只算證券 ETF；
  同樣本質、但放在保單裡的基金完全沒被算到 → 本試算逐檔認定並量化。
"""
import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
TODAY = date.today().isoformat()

DENOM = SNAP["dual_dimension_metric"]["防禦維度"]["分母"]
NOW_SUM = SNAP["dual_dimension_metric"]["防禦維度"]["合計"]
NOW_PCT = SNAP["dual_dimension_metric"]["防禦維度"]["佔比"]
SEC_DEF_ETF = SNAP["dual_dimension_metric"]["防禦維度"]["組成"]["低波高股息防禦"]      # 證券側（0056/00713/00878 等）
SEC_BOND = SNAP["dual_dimension_metric"]["防禦維度"]["組成"]["債券類"]
SEC_FUND_EQ = SNAP["dual_dimension_metric"]["防禦維度"]["組成"]["配息型基金權益"]        # 只含 B11
PEN_BOND = SNAP["penetration"]["actual_twd"]["債券"]

# ── 逐檔判定規則（與公式同一套「本質」規則，不另創標準）─────────────────────
# R1 低波高股息防禦權益：台股高股息、低波動、穩定配息 → 與證券側 0056/00713/00878 同籃
# R2 配息型基金權益：平衡型/多重資產/收益型基金（股債混合、穩定月配）→ 權益＋內部現金進配息型基金權益，債券部位進債券類
# R3 避險衛星：黃金等避險資產 → 進避險衛星（現行以「目標值」計入，實際持倉納入需先解決重複計算）
# R4 不符合：單一產業/成長型權益基金（與證券側科技成長同規則，非防禦）
RULE = {
    "R1 低波高股息防禦權益": "台股高股息、低波動、穩定配息（與證券側 0056/00713/00878 同籃）",
    "R2 配息型基金權益": "平衡型／多重資產／收益型基金：權益＋內部現金部位（B11 已是此口徑）",
    "R3 避險衛星": "黃金等避險資產（現行避險衛星以目標值計入，實際持倉另有重複計算問題）",
    "R4 不符合": "單一產業或成長型權益基金（非防禦本質）",
}
MAP = {
    "元大台灣高股息": ("R1 低波高股息防禦權益", "台股高股息龍頭，配息型；同 0056/00713/00878 本質"),
    "安聯收益成長": ("R2 配息型基金權益", "股債混合穩定月配（收益成長型）"),
    "摩根投資基金 - 多重收益": ("R2 配息型基金權益", "多重收益（股債混合、穩定月配）"),
    "PIMCO收益增長": ("R2 配息型基金權益", "收益增長（債為主、含權益之收益型）"),
    "M&G入息": ("R2 配息型基金權益", "入息型（股債混合、月配）"),
    "貝萊德世界黃金": ("R3 避險衛星", "黃金＝避險資產"),
    "貝萊德世界健康科學": ("R4 不符合", "單一產業權益基金（醫療），非防禦本質"),
}


def judge(name: str):
    for k, v in MAP.items():
        if k in name:
            return v
    return ("待判定", "規則表未涵蓋 → 不臆測，列為待補")


rows, total = [], {}
for policy, key in (("A", "policy_a_funds"), ("B", "policy_b_funds")):
    for name, amt in (SNAP["insurance_breakdown"].get(key) or {}).items():
        rule, why = judge(name)
        rows.append({"保單": policy, "基金": name, "金額": amt, "判定": rule, "依據": why})
        total[rule] = total.get(rule, 0) + amt

sum_r1 = total.get("R1 低波高股息防禦權益", 0)
sum_r2 = total.get("R2 配息型基金權益", 0)
sum_r3 = total.get("R3 避險衛星", 0)
sum_r4 = total.get("R4 不符合", 0)

# ── 候選口徑 ───────────────────────────────────────────────────────────────
opt_a = NOW_SUM + sum_r1                                    # 只納入元大（保守下限）
opt_b_lo = NOW_SUM + sum_r1                                 # R2 待官方成分 → 下限同 A
opt_b_hi = NOW_SUM + sum_r1 + sum_r2                        # R2 整包（必然高估，僅上限）
opt_c = NOW_SUM + sum_r1 + sum_r2 + sum_r3                  # 再加黃金（重複計算風險）

out = {
    "產生時間": TODAY,
    "性質": "試算（唯讀）；未改動 snapshot／正式真值；正式報表仍為 49.3%",
    "現行": {"防禦維度合計": NOW_SUM, "佔比": NOW_PCT, "分母": DENOM,
             "公式": SNAP["dual_dimension_metric"]["防禦維度"]["公式"],
             "組成": SNAP["dual_dimension_metric"]["防禦維度"]["組成"]},
    "判定規則": RULE,
    "逐檔證據": rows,
    "小計": {"R1 低波高股息": sum_r1, "R2 配息型基金權益(待官方成分)": sum_r2,
             "R3 避險衛星(黃金)": sum_r3, "R4 不符合": sum_r4},
    "候選口徑": {
        "A_僅元大": {"合計": opt_a, "佔比": round(opt_a / DENOM * 100, 1),
                     "差異": round((opt_a - NOW_SUM) / DENOM * 100, 2),
                     "說明": "只把本質明確、且與證券側同籃的元大納入（保守下限）"},
        "B_本質一致(下限)": {"合計": opt_b_lo, "佔比": round(opt_b_lo / DENOM * 100, 1),
                             "說明": "R2 需官方成分才能拆分權益/債券 → 未取得前不臆測"},
        "B_本質一致(上限)": {"合計": opt_b_hi, "佔比": round(opt_b_hi / DENOM * 100, 1),
                             "說明": "R2 整包計入＝必然高估（會與債券類重複），僅供包絡"},
        "C_含黃金避險": {"合計": opt_c, "佔比": round(opt_c / DENOM * 100, 1),
                         "說明": "避險衛星現以目標值計入，再加實際黃金持倉＝重複計算風險"},
    },
    "未解阻塞（需裁決或補資料）": [
        f"債券類現行 {SEC_BOND:,} ≠ 穿透債券桶 {PEN_BOND:,.0f}（差 {PEN_BOND - SEC_BOND:,.0f}）"
        f" → 未 itemize 前，R2 的『債券部位進債券類』無法落地（可能重複計算）",
        f"配息型基金權益現行只含 B11 {SEC_FUND_EQ:,}；保單平衡型基金（R2 合計 {sum_r2:,}）之權益比例需官方成分",
        f"避險衛星以目標值 1,310,000 計入（未建倉），而保單已有黃金持倉 {sum_r3:,} → 需決定以『目標』或『實際』為準",
        "分母是否應扣除保單現金價值／保單借款等，屬另一層（9/29 已定案：分母＝總資產−指定用途款）",
    ],
}

(BASE / "data").mkdir(exist_ok=True)
(BASE / f"data/defense_caliber_trial_{TODAY}.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

lines = [f"# 防禦資產完整口徑試算（{TODAY}）", "",
         f"- 現行：{NOW_PCT}%（{NOW_SUM:,} / {DENOM:,.0f}）", "",
         "## 逐檔證據（保單內基金）", ""]
for r in rows:
    lines.append(f"- [{r['保單']}] {r['基金']}｜{r['金額']:,}｜{r['判定']}｜{r['依據']}")
lines += ["", "## 候選口徑", ""]
for k, v in out["候選口徑"].items():
    lines.append(f"- {k}：{v['佔比']}%（{v['合計']:,}）｜{v['說明']}")
lines += ["", "## 未解阻塞", ""] + [f"- {x}" for x in out["未解阻塞（需裁決或補資料）"]]
(BASE / f"data/defense_caliber_trial_{TODAY}.md").write_text("\n".join(lines), encoding="utf-8")

print("\n".join(lines))
print(f"\n（試算檔：data/defense_caliber_trial_{TODAY}.json / .md｜snapshot 未改動）")
