#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""life_account_alert.py — 生活帳戶水位每日提醒（2026-09-28 使用者裁示）

玉山／台北富邦＝信用卡自動扣繳的生活帳戶，安全線 40,000（刻意常數：只扣信用卡，
不是月支出×3）。餘額低於安全線 → 提醒補足；全部達標 → 不輸出任何內容
（no_agent watchdog 模式：空 stdout＝不推播，零噪音）。

用法：python life_account_alert.py            # 直接跑（cron no_agent）
      python life_account_alert.py --always   # 強制輸出（人工檢查用）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SAFE_LINE = 40_000        # 生活帳戶安全線（玉山／富邦；刻意常數）
ACCOUNTS = (               # (顯示名, snapshot cash_detail 鍵, 主要用途)
    ("玉山銀行", "臺幣綜存", "信用卡自動扣繳"),
    ("台北富邦", "數位活儲", "信用卡自動扣繳"),
)


def main() -> int:
    always = "--always" in sys.argv
    try:
        snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    except Exception as e:                      # 讀不到就安靜退出（別在 08:30 推技術錯誤）
        print(f"⚠️ life_account_alert：無法讀 snapshot.json（{type(e).__name__}: {e}）", file=sys.stderr)
        return 1
    cd = snap.get("cash_detail") or {}
    low = []
    for name, key, use in ACCOUNTS:
        bal = float(cd.get(key) or 0)
        if bal < SAFE_LINE:
            low.append((name, bal, SAFE_LINE - bal, use))
    if not low and not always:
        return 0                                # 達標 → 不推播
    out = [f"🏦 生活帳戶水位提醒（{snap.get('date', '')}）"]
    for name, bal, gap, use in low:
        out.append(f"🔴 {name} {bal:,.0f} < 安全線 {SAFE_LINE:,.0f}｜缺口 {gap:,.0f}"
                   f"（{use}帳戶，扣款失敗會影響信用）→ 建議自台新／國泰轉入補足")
    if not low:
        out.append("🟢 玉山／台北富邦皆高於安全線 40,000")
    out.append("（口徑：生活帳戶只扣信用卡 → 安全線 40,000 常數；2026-09-28 使用者裁示列入每日提醒）")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
