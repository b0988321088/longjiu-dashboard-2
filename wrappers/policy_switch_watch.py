#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薄轉發器 → repo/policy_switch_watch.py（cron 只吃單一檔名、不傳參數）。

cron 的 script 欄位是相對 HERMES_HOME/scripts 解析，而真身要靠 __file__ 找
snapshot.json／data／龍九備份，**不可**直接鏡像（BASE 會變成 hermes/scripts → 讀不到真值）。
故以 cwd=REPO 轉呼叫；repo/wrappers/ 是唯一來源，post-commit 自動部署。
"""
import os
import subprocess
import sys

REPO = r"C:/Users/bot/Desktop/longjiu_system"
TARGET = os.path.join(REPO, "policy_switch_watch.py")

if not os.path.exists(TARGET):
    sys.stderr.write(f"ERROR: 找不到真身 {TARGET}\n")
    sys.exit(1)

r = subprocess.run([sys.executable, TARGET, *sys.argv[1:]], cwd=REPO)
sys.exit(r.returncode)
