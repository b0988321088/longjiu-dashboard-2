#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薄轉發器 → repo/natfund_trigger_watch.py（cron script 只吃 HERMES_HOME/scripts 下的單一檔名）。

真身用 Path(__file__).parent 找 snapshot.json，不可鏡像到 hermes/scripts（BASE 會錯），
故以 cwd=REPO 轉呼叫。空輸出＝靜默（no_agent 模式不推播）。
"""
import os
import subprocess
import sys

REPO = r"C:/Users/bot/Desktop/longjiu_system"
TARGET = os.path.join(REPO, "natfund_trigger_watch.py")

if not os.path.exists(TARGET):
    sys.stderr.write(f"ERROR: 找不到真身 {TARGET}\n")
    sys.exit(1)

r = subprocess.run([sys.executable, TARGET, *sys.argv[1:]], cwd=REPO)
sys.exit(r.returncode)
