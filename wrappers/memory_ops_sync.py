#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薄轉發器 → repo/memory_ops.py sync（cron 只吃單一檔名、不傳參數）。"""
import os
import subprocess
import sys

REPO = r"C:/Users/bot/Desktop/longjiu_system"
TARGET = os.path.join(REPO, "memory_ops.py")

if not os.path.exists(TARGET):
    sys.stderr.write(f"ERROR: 找不到真身 {TARGET}\n")
    sys.exit(1)

r = subprocess.run([sys.executable, TARGET, "sync"], cwd=REPO)
sys.exit(r.returncode)
