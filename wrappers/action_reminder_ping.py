#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cron wrapper：到期與待辦行動提醒（每日 08:10，no_agent）

stdout 直接推 Telegram；當日無 T-3（轉換類 T-7）內項目時輸出為空 → 靜默。
真身在 longjiu_system/action_reminder.py（唯一真值讀取與排版都在那裡）。
"""
import subprocess
import sys
from pathlib import Path

TARGET = Path(r"C:\Users\bot\Desktop\longjiu_system\action_reminder.py")

if not TARGET.exists():
    print(f"⛔ action_reminder.py 不存在（{TARGET}）→ 行動提醒中止")
    sys.exit(1)

r = subprocess.run([sys.executable, str(TARGET)], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=120)
out = (r.stdout or "").strip()
if r.returncode != 0:
    tail = ((r.stderr or "").strip().splitlines() or [""])[-1][:160]
    print(f"⚠️ 行動提醒執行失敗 rc={r.returncode}｜{tail}")
    sys.exit(1)
if out:
    print(out)
