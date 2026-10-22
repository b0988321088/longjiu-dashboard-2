#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薄轉發器 → repo/data_closeout_commit.py（cron 只吃單一檔名、不傳參數）。

為什麼需要這支（2026-10-22）：cron 的 script 欄位相對 `HERMES_HOME/scripts`
解析 → repo 根目錄的新腳本若不經此轉發器，到點會 `Script not found`。
repo/wrappers/ 是 hermes/scripts 轉發器的唯一來源，post-commit 會部署鏡像。

真身用 `Path(__file__).parent` 當 REPO（要靠 git 操作 repo），**不可**直接鏡像
repo 檔到 hermes/scripts（BASE 會變成 hermes/scripts → 認錯 repo），故以
cwd=REPO 轉呼叫。
"""
import os
import subprocess
import sys

REPO = r"C:/Users/bot/Desktop/longjiu_system"
TARGET = os.path.join(REPO, "data_closeout_commit.py")

if not os.path.exists(TARGET):
    sys.stderr.write(f"ERROR: 找不到真身 {TARGET}\n")
    sys.exit(1)

r = subprocess.run([sys.executable, TARGET, *sys.argv[1:]], cwd=REPO)
sys.exit(r.returncode)
