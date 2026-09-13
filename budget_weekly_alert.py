#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""budget_weekly_alert.py — 每週信用卡預算提醒（no_agent，零 LLM）

取代原 agent cron「budgeting管家 每週預算檢查」（cccd9faf5428，13 天 NT$13.2
≈ 每月 NT$26）。原 job 的工作是呼叫 budget_daily_check.py 再「轉述」結果 —
而該腳本自己就會算超支率/等級（P1 ≥20%、P2 ≥10%）、寫入
BUDGET_WEEKLY_REPORT.md 並印出完整報告。所以：no_agent 直接跑它即可。

輸出規則（省噪音）：
  - 報告內出現 P1/P2 或「資料品質」警示 → 輸出精簡摘要（超支卡片 + 警示清單）
  - 一切正常 → 靜默（no_agent 無輸出＝不推送）
  - 腳本失敗 → 印錯誤尾段 + 非零碼（cron 發錯誤警報）

用法：python budget_weekly_alert.py
      LJ_BUDGET_FULL=1 python budget_weekly_alert.py   # 一律輸出完整報告（人工檢視用）
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

BASE = Path.home() / "Desktop" / "longjiu_system"
REPORT = BASE / "BUDGET_WEEKLY_REPORT.md"
WARN_RE = re.compile(r"(P1|P2|資料品質|🚨|⚠️)")


def main() -> None:
    if not os.environ.get("LJ_BUDGET_FULL"):
        try:
            r = subprocess.run([sys.executable, str(BASE / "budget_daily_check.py")],
                               cwd=str(BASE), capture_output=True, text=True, timeout=600)
        except Exception as e:
            print(f"⚠️ 預算檢查失敗（無法啟動 budget_daily_check.py）：{e}")
            sys.exit(2)
        text = (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
        if r.returncode != 0:
            print("⚠️ 預算檢查失敗 — 需人工處理")
            print(f"budget_daily_check.py rc={r.returncode}")
            print(text.strip()[-1000:])
            sys.exit(r.returncode)
    else:
        text = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""

    if not WARN_RE.search(text):
        return  # 無異常 → 靜默

    # 精簡摘要：卡片表格的合計列 + 警示清單
    pick = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("生成時間"):
            pick.append(s)
        elif s.startswith("|") and "合計" in s:
            pick.append(s)
        elif s.startswith(("- 🚨", "- ⚠️", "* 🚨", "* ⚠️")):
            pick.append(s)
    if not pick:
        pick = [ln.strip() for ln in text.splitlines() if WARN_RE.search(ln)][:12]
    print("💳 每週預算檢查（異常）")
    print("\n".join(pick))
    print(f"（完整報告：longjiu_system/BUDGET_WEEKLY_REPORT.md）")


if __name__ == "__main__":
    main()
