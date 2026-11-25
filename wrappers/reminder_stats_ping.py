#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cron wrapper：提醒回應率週統計（每週一 07:20，no_agent）

統計近 7 天推播／回覆／卡住項目；無紀錄時靜默。
真身在 longjiu_system/reminder_weekly_stats.py。
"""
import subprocess
import sys
from pathlib import Path

TARGET = Path(r"C:\Users\bot\Desktop\longjiu_system\reminder_weekly_stats.py")

if not TARGET.exists():
    print(f"⛔ reminder_weekly_stats.py 不存在（{TARGET}）")
    sys.exit(1)

r = subprocess.run([sys.executable, str(TARGET)], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=90)
out = (r.stdout or "").strip()
if r.returncode != 0:
    tail = ((r.stderr or "").strip().splitlines() or [""])[-1][:160]
    print(f"⚠️ 提醒統計失敗 rc={r.returncode}｜{tail}")
    sys.exit(1)
if out:
    print(out)
