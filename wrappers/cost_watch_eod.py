#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""費用收日班 23:55：把 18:30 之後的花費當天收進帳本（2026-10-01 使用者核准）。

問題：帳本 data/ai_cost_daily.jsonl 只在 digest 班（13:30／18:30）更新，
      18:30 之後的花費（晚間對話、21:30 美股班）當天不入帳；
      偏偏 regenerate_report.py 會在緊急應變時重產費用頁 → 頁面 generated_at
      前進到 21:33，數字卻還是 18:30 的帳本值（9/30 實例：頁面顯示 981 次／NT$46，
      全天真值 1,464 次／NT$64），要等隔天 13:30 回填才補得回來。

作法：不自帶 git／推送邏輯，直接轉呼叫已驗證的 wrappers/cost_watch_digest.py
      （帳本 upsert → 費用頁重產 → stage 自家三檔 → auto_push 唯一出口）。
      它的報告輸出在成功時吞掉（22:30 已推日結，23:55 再推一次是噪音）；
      失敗時才印尾端輸出，讓 cron 端看得到（cron no_agent：無輸出＝靜默不推播）。
"""
import subprocess
import sys
from pathlib import Path

BASE = Path(r"C:\Users\bot\Desktop\longjiu_system")
TARGET = BASE / "wrappers" / "cost_watch_digest.py"


def main() -> int:
    if not TARGET.exists():
        sys.stderr.write(f"ERROR: 找不到真身 {TARGET}\n")
        return 1
    try:
        r = subprocess.run([sys.executable, str(TARGET)], cwd=str(BASE),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900)
    except subprocess.TimeoutExpired:
        print("⚠️ 費用收日班逾時（900s）")
        return 1
    if r.returncode == 0:
        return 0  # 靜默：成功不輸出 → cron 不推播
    print("⚠️ 費用收日班失敗（23:55，費用頁／帳本可能停在 18:30 版）")
    for line in ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-8:]:
        print("  " + line)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
