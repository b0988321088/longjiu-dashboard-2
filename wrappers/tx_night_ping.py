#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cron wrapper：台指期夜盤（no_agent 模式，stdout 直接推 Telegram）

被 Hermes cron 每天 23:00（週一至週五）呼叫。實際邏輯在 longjiu_system/tx_night.py，
這裡只負責跑腳本並把 stdout 原樣輸出（cron 負責投遞到 Telegram）。
"""
import subprocess
import sys
from pathlib import Path

TARGET = Path(r"C:\Users\bot\Desktop\longjiu_system\tx_night.py")

if not TARGET.exists():
    print("⛔ tx_night.py 不存在，夜盤監控中止")
    sys.exit(1)

try:
    r = subprocess.run(
        [sys.executable, str(TARGET), "--dry-run"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        cwd=str(TARGET.parent),
    )
except Exception as e:
    print(f"⛔ 執行失敗：{e}")
    sys.exit(1)

out = (r.stdout or "").strip()
err = (r.stderr or "").strip()
if out:
    print(out)
if r.returncode != 0:
    print(f"⛔ 腳本 rc={r.returncode}")
    if err:
        print(err[:300])
