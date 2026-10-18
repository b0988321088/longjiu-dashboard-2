#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薄轉發器 → repo/maintenance.py deep（cron 只吃單一檔名、不傳參數）。

2026-10-12 TD-20261012-25 延伸：deep 班（週一 03:00）過去只把產物留在工作區，
沒有任何提交出口 → 每週固定漏出未提交檔（實例：`.archive/deleted_py_list.txt`、
被插入更正聲明的舊日期報告頁），22:40 收工稽核每晚判「已追蹤未提交」。
改為跑完就地提交自家產物（純資料，逐字宣告清單；判斷與 cost_watch_close 同一套：
只 stage 自家檔案、無變更不 commit、推送走 auto_push.py 唯一出口）。

2026-10-13 修正（實跑踩到）：self_publish 的「本輪起跑時刻」＝該模組被 import 的時刻，
必須**在執行 deep 之前** import（首版放在 deep 之後 → T0 晚於產物 mtime → 一律不認領）。
"""
import os
import subprocess
import sys

REPO = r"C:/Users/bot/Desktop/longjiu_system"
TARGET = os.path.join(REPO, "maintenance.py")

# 逐字宣告的自家產物（本輪確實寫出者才會被認領；mtime 早於本輪起跑者一律不帶走）
# 2026-10-19 使用者裁決：週清不再改寫歷史報告（daily_report_v2_*.html／dynamic_weekly_review_*.html
# 已從本清單移除）；歸檔與報告改寫到 repo 外（state_store.ARCHIVE_DIR），不進版控，
# 因此本 job 正常執行時不再產生任何需要落版的檔案。
OWN = []   # 全部產物已移出 repo（state_store）；本 job 不再 commit／push 任何檔案

if not os.path.exists(TARGET):
    sys.stderr.write(f"ERROR: 找不到真身 {TARGET}\n")
    sys.exit(1)

sys.path.insert(0, REPO)
try:
    from self_publish import commit_own      # 必須在 deep 之前 import（見模組呼叫端契約）
except Exception as e:                                     # import 失敗＝自身產出漏出風險
    sys.stderr.write(f"⛔ 無法載入 self_publish（{e}）→ 產物未提交，需人工處理\n")
    sys.exit(1)

r = subprocess.run([sys.executable, TARGET, "deep"], cwd=REPO)

# 推送失敗要讓 cron 看得到（rc 原樣帶回），deep 本體失敗也不得被靜默
sys.exit(commit_own("maintenance_deep.py", OWN, producer_rc=r.returncode))
