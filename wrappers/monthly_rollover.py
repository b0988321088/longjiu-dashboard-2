#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薄轉發器 → repo/monthly_rollover.py --apply（cron 只吃單一檔名、不傳參數）。

2026-10-01 使用者核准：每月 1 日 06:45 先跑月初校正，再做 07:00 晨間產線
（否則儀表板閘門第 14 條必擋：房租待收 ≠ rent_monthly_gap、當月實收混到上月數字）。
"""
import os
import subprocess
import sys

REPO = r"C:/Users/bot/Desktop/longjiu_system"
TARGET = os.path.join(REPO, "monthly_rollover.py")

if not os.path.exists(TARGET):
    sys.stderr.write(f"ERROR: 找不到真身 {TARGET}\n")
    sys.exit(1)

r = subprocess.run([sys.executable, TARGET, "--apply"], cwd=REPO)
sys.exit(r.returncode)
