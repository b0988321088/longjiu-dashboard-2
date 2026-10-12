#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薄轉發器 → repo/maintenance.py deep（cron 只吃單一檔名、不傳參數）。

2026-10-12 TD-20261012-25 延伸：deep 班（週一 03:00）過去只把產物留在工作區，
沒有任何提交出口 → 每週固定漏出未提交檔（實例：`.archive/deleted_py_list.txt`、
被插入更正聲明的舊日期報告頁），22:40 收工稽核每晚判「已追蹤未提交」。
改為跑完就地提交自家產物（純資料，逐字宣告清單；判斷與 cost_watch_close 同一套：
只 stage 自家檔案、無變更不 commit、推送走 auto_push.py 唯一出口）。
"""
import os
import subprocess
import sys

REPO = r"C:/Users/bot/Desktop/longjiu_system"
TARGET = os.path.join(REPO, "maintenance.py")

# 逐字宣告的自家產物（本輪確實寫出者才會被認領；mtime 早於本輪起跑者一律不帶走）
OWN = [
    ".archive/deleted_py_list.txt",
    "daily_report_v2_*.html",
    "dynamic_weekly_review_*.html",
]

if not os.path.exists(TARGET):
    sys.stderr.write(f"ERROR: 找不到真身 {TARGET}\n")
    sys.exit(1)

sys.path.insert(0, REPO)
r = subprocess.run([sys.executable, TARGET, "deep"], cwd=REPO)

try:
    from self_publish import commit_own
except Exception as e:                                     # import 失敗＝自身產出漏出風險
    sys.stderr.write(f"⛔ 無法載入 self_publish（{e}）→ 產物未提交，需人工處理\n")
    sys.exit(1 if r.returncode == 0 else r.returncode)

# 推送失敗要讓 cron 看得到（rc 原樣帶回），deep 本體失敗也不得被靜默
sys.exit(commit_own("maintenance_deep.py", OWN, producer_rc=r.returncode))
