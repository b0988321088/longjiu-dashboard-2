#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薄轉發器 → repo/pledge_maintenance_alert.py（cron 只吃單一檔名、不傳參數）。

為什麼需要這支（2026-09-28 INC 的同一條規則）：
    cron 的 script 欄位是相對 HERMES_HOME/scripts 解析，只有 repo 根的檔案會 Script not found。
    repo/wrappers/ 是 hermes/scripts 轉發器的唯一來源（post-commit 自動部署）。

注意：真身用 `Path(__file__).parent` 找 snapshot.json，不可直接鏡像 repo 檔到 hermes/scripts，
      故以 cwd=REPO 轉呼叫。
"""
import os
import subprocess
import sys

REPO = r"C:/Users/bot/Desktop/longjiu_system"
TARGET = os.path.join(REPO, "pledge_maintenance_alert.py")

if not os.path.exists(TARGET):
    sys.stderr.write(f"ERROR: 找不到真身 {TARGET}\n")
    sys.exit(1)

r = subprocess.run([sys.executable, TARGET, *sys.argv[1:]], cwd=REPO)
sys.exit(r.returncode)
