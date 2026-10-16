#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薄轉發器 → repo/structural_health_push.py（cron 只吃單一檔名、不傳參數）。

真身用 `Path(__file__).resolve().parent` 定位 snapshot.json／導入
build_structural_health，**不可**直接鏡像真身到 hermes/scripts（BASE 會變成
hermes/scripts → 讀不到 snapshot）。故以 cwd=REPO 轉呼叫。

post-commit hook 會把 repo/wrappers/ 的檔案部署到 HERMES_HOME/scripts/。
"""
import os
import subprocess
import sys

REPO = r"C:/Users/bot/Desktop/longjiu_system"
TARGET = os.path.join(REPO, "structural_health_push.py")

if not os.path.exists(TARGET):
    sys.stderr.write(f"ERROR: 找不到真身 {TARGET}\n")
    sys.exit(1)

r = subprocess.run([sys.executable, TARGET, *sys.argv[1:]], cwd=REPO)
sys.exit(r.returncode)
