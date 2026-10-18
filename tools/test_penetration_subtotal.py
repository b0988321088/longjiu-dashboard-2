#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""測試 update_all.calc_penetration 的「通路小計列」排除（2026-10-18 台股桶對帳工單）。

修前：頂層鍵「一般申購_平台小計 389,525」被當成一檔基金 → 走 else 分支進台股桶，
      同時其成分明細也在 → 基金分類合計超出 fund_market_value → 觸發全基金等比縮放，
      台股桶被虛增（實測 360,330），五桶一起被扭曲。
修後：鍵名含「小計」一律視為彙總列，不進展平表。

斷言：
  T1 有 小計 列時，台股桶 == 明細金額（不多算小計）
  T2 無 小計 列時，結果不變（零回歸）
  T3 小計列金額任意大，都不影響任何桶
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import update_all  # noqa: E402

TGT = {"thresholds_2026_0915": {"桶目標_pct": {
    "台股市值型": 10, "美股市值型": 30, "防守型配息": 30, "債券": 25, "現金/安全網": 5}}}


def calc(fb: dict, funds: float):
    snap = {"funds_breakdown": fb, "insurance_breakdown": {}, "securities": {}, **TGT}
    return update_all.calc_penetration(0, 0, 0, funds, snap=snap)


def main() -> int:
    ok, fails = 0, []

    # T1 含小計列（小計 = 明細同額，模擬平台畫面「一般申購 389,525」）
    p1 = calc({"一般申購": {"某台股基金": 100_000}, "一般申購_平台小計": 100_000}, 100_000)
    t1 = abs(p1["台股市值型成長"] - 100_000) < 2
    ok += t1
    if not t1:
        fails.append(f"T1 含小計列 → 台股 {p1['台股市值型成長']:,}（期望 100,000）")

    # T2 無小計列（零回歸）
    p2 = calc({"一般申購": {"某台股基金": 100_000}}, 100_000)
    t2 = abs(p2["台股市值型成長"] - 100_000) < 2
    ok += t2
    if not t2:
        fails.append(f"T2 無小計列 → 台股 {p2['台股市值型成長']:,}（期望 100,000）")

    # T3 小計金額任意大也不影響
    p3 = calc({"一般申購": {"某台股基金": 100_000}, "一般申購_平台小計": 9_999_999}, 100_000)
    t3 = abs(p3["台股市值型成長"] - 100_000) < 2
    ok += t3
    if not t3:
        fails.append(f"T3 巨額小計 → 台股 {p3['台股市值型成長']:,}（期望 100,000）")

    print(f"calc_penetration 小計排除測試：{ok}/3 PASS")
    for f in fails:
        print("  ❌", f)
    return 0 if ok == 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
