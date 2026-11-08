#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/test_norm_status_closure.py — norm_status 結案語意回歸測試（2026-11-08 INC-300）

病灶：`norm_status` 原把「✅ 開頭」一律判成 已完成 → pending_reconcile 派生的
「✅ 條件已成立（…真值重算）」被寫成結案態，卡片留在 pending 佇列卻標已完成：
  · check_thresholds --sot-only 第 7 類 FAIL
  · closeout_check ② 決策狀態未回收 FAIL（連續多日 22:40 紅）
修法：「條件已成立」先判 已確認；其餘 ✅ 語意不動。

跑法：python tools/test_norm_status_closure.py（全過 exit 0）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pending_engine import STATUS_ENUM, norm_status  # noqa: E402

CASES = [
    # (raw, 期望, 說明)
    ("✅ 條件已成立（2026-11-08 真值重算）：US30Y 5.251%", "已確認", "T1 條件成立≠結案"),
    ("條件已成立（2026-11-08）：解凍三條件達標", "已確認", "T2 無 emoji 亦同"),
    ("✅ 已完成：卡片自 pending 移除", "已完成", "T3 真結案仍為已完成"),
    ("✅ 已實作（2026-09-30）：metrics_registry", "已完成", "T4 既有語意不得改變"),
    ("✅ 已入帳完成 11/17 配息", "已完成", "T5 入帳完成仍為已完成"),
    ("⏸ 條件未成立（2026-11-08）：US30Y 5.35%", "已確認", "T6 未成立為已確認"),
    ("🔄 執行中（2026-11-08）：分批第 2 批", "已確認", "T7 執行中"),
    ("關案：與新案重複", "關案", "T8 關案"),
    ("待補文件：銀行維持率書面", "待處理", "T9 待處理"),
]


def main() -> int:
    fails = []
    for raw, want, tag in CASES:
        got = norm_status(raw)
        ok = got == want
        print(f"{'✅' if ok else '❌'} {tag}：{got}" + ("" if ok else f"（期望 {want}）"))
        if not ok:
            fails.append(tag)
    # 不變量：任何回傳值必須在四態內
    bad = [r for r, _, _ in CASES if norm_status(r) not in STATUS_ENUM]
    if bad:
        fails.append(f"回傳值不在 STATUS_ENUM：{bad}")
    if fails:
        print(f"\n❌ 未通過 {len(fails)} 項：{fails}")
        return 1
    print(f"\n✅ 全數通過（{len(CASES)} 案例）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
