#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薄轉發器 → repo/life_account_alert.py（cron 只吃單一檔名、不傳參數）。

為什麼需要這支（2026-09-28 INC）：`life_account_alert.py` 當時只存在 repo 根目錄，
而 cron 的 script 欄位是相對 `HERMES_HOME/scripts` 解析 → 08:30 第一班直接
`Script not found`。repo/wrappers/ 才是 hermes/scripts 轉發器的唯一來源，
新腳本要上 cron 一律在 repo/wrappers/ 放一支同名轉發器（post-commit 會部署）。

注意：真身用 `Path(__file__).parent` 找 snapshot.json，**不可**直接鏡像 repo 檔到
hermes/scripts（BASE 會變成 hermes/scripts → 讀不到 snapshot）。故以 cwd=REPO 轉呼叫。
"""
import os
import subprocess
import sys

REPO = r"C:/Users/bot/Desktop/longjiu_system"
TARGET = os.path.join(REPO, "life_account_alert.py")

if not os.path.exists(TARGET):
    sys.stderr.write(f"ERROR: 找不到真身 {TARGET}\n")
    sys.exit(1)

r = subprocess.run([sys.executable, TARGET, *sys.argv[1:]], cwd=REPO)
sys.exit(r.returncode)
