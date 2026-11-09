#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_denominator_label_guard.py — 分母標籤守門單測（2026-11-09 裁決 A）

驗的是 daily_report_assembly.relabel_denominator_labels：LLM 若把「防禦維度分母」
寫成「配置分母」，注入日報前會被按金額改回正確名稱；金額對不上時只能加「（待核對）」，
不得自行補值（使用者規格：不得自行補值）。

用法：python tests/test_denominator_label_guard.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from daily_report_assembly import relabel_denominator_labels  # noqa: E402

SNAP = {
    "total_assets": 26_496_691,
    "penetration": {"pct_denominator": 26_496_691, "restricted_cash": 900_000},
}


def main() -> int:
    cases = [
        # (名稱, 原文, 期待包含, 期待不含, 期待統計)
        ("防禦維度分母誤寫成配置分母",
         "• 總資產 26,496,691；防禦與配置分母 25,596,691（扣除指定用途款 900,000）。",
         "防禦維度分母 25,596,691（＝總資產−指定用途款 900,000）", "配置分母 25,596,691", {"def": 1}),
        ("總資產誤寫成配置分母",
         "五桶配置分母 26,496,691。",
         "五桶配置分母 26,496,691（＝總資產，含指定款／在途／衛星）", "配置分母 26,496,691。", {"ta": 1}),
        ("金額對不上 → 只標待核對、不改數字",
         "配置分母 24,000,000。",
         "配置分母 24,000,000（待核對）", None, {"unknown": 1}),
        ("正常文字不動",
         "• 總資產 26,496,691；防禦維度分母 25,596,691。",
         "防禦維度分母 25,596,691", None, {}),
    ]
    fails = 0
    print(f"🧪 分母標籤守門單測（{len(cases)} 案例）")
    for name, text, must_have, must_not, stat in cases:
        out, st = relabel_denominator_labels(text, SNAP)
        ok = must_have in out
        if must_not:
            ok = ok and (must_not not in out)
        if stat:
            ok = ok and all(st.get(k) == v for k, v in stat.items())
        else:
            ok = ok and (out == text)
        print(f"  {'✅' if ok else '❌'} {name}｜統計 {st}")
        if not ok:
            fails += 1
            print(f"     實際輸出：{out}")
    print(f"\n{'✅ 全部通過' if not fails else f'❌ {fails} 個案例失敗'}（{len(cases) - fails}/{len(cases)}）")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
