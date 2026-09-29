#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIO 審查（推送範圍 fail）必修：allianz_a/b_breakdown 等舊欄位同步 9/29 真值。"""
import json
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
P = BASE / "snapshot.json"
s = json.loads(P.read_text(encoding="utf-8"))

A = {"安聯收益成長": 619256, "摩根JPM多重收益": 1715772, "貝萊德世界健康A10": 293508,
     "M&G入息": 752279, "PIMCO收益增長": 1364224, "貝萊德世界黃金A10": 189370}
B = {"安聯收益成長": 486704, "貝萊德世界健康A10": 244414, "M&G入息": 1548321,
     "PIMCO收益增長": 196962, "貝萊德世界黃金A10": 157531}
assert sum(A.values()) == 4934409, sum(A.values())
assert sum(B.values()) == 2633932, sum(B.values())

s["allianz_a_breakdown"] = A
s["allianz_b_breakdown"] = B
# 其餘同名不同名的舊值欄位一併同步（避免下游讀到 9/23 舊值）
s["allianz_a_value"] = 4934409
s["allianz_b_value"] = 2633932
s["allianz_a_current_value"] = 4934409
s["allianz_b_current_value"] = 2633932
s["allianz_policy_a_value"] = 4934409
s["allianz_policy_b_value"] = 2633932
s["allianz_a"] = 4934409
s["allianz_b"] = 2633932
s["allianz_a_funds"] = 4934409
s["allianz_b_funds"] = 2633932
s["allianz_combined"] = 7568341
s["allianz_ab"] = 7568341
s["allianz_ab_current_value"] = 7568341
s["allianz_current_value"] = 7568341
s["allianz_total"] = 7568341
s["allianz_a_performance"] = -2.95
s["allianz_b_performance"] = -2.45
s["allianz_a_breakdown_note"] = (
    "2026-09-29 13:30 保單 QL18610694 截圖逐檔：安聯收益成長 619,256／摩根JPM多重收益 1,715,772／"
    "貝萊德世界健康A10 293,508／M&G入息 752,279／PIMCO收益增長 1,364,224／貝萊德世界黃金A10 189,370；"
    "合計 4,934,409（-2.95%）｜本月累積配息/撥回 A+B 合計 7 筆 52,169")
s["allianz_b_breakdown_note"] = (
    "2026-09-29 13:30 保單 QL1848824 截圖逐檔：安聯收益成長 486,704／貝萊德世界健康A10 244,414／"
    "M&G入息 1,548,321／PIMCO收益增長 196,962／貝萊德世界黃金A10 157,531；"
    "合計 2,633,932（-2.45%）（B 無摩根 JPM 部位）")

for k in ("insurance_total", "insurance_current_value", "insurance"):
    s[k] = 9453825
s["total_assets"] = 31808561

P.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
print("✅ allianz A/B breakdown 與相關同名欄位已同步 9/29 真值")
print("   A 逐檔合計", f"{sum(A.values()):,}", "｜B 逐檔合計", f"{sum(B.values()):,}",
      "｜A+B", f"{sum(A.values())+sum(B.values()):,}")
