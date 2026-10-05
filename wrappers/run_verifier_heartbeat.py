#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薄轉發器 → repo/tools/run_verifier_heartbeat.py（P0-1，2026-10-05 使用者核准）

為什麼需要這支：cron 的 `script` 欄位是相對 `HERMES_HOME/scripts` 解析，
repo 內的檔案不會被找到（2026-09-28 INC：life_account_alert.py 首班 Script not found）。
repo/wrappers/ 才是 hermes/scripts 轉發器的唯一來源（post-commit 會部署）。

行為
----
* 一律以 `--quiet` 執行 → **每次都寫心跳**（data/verifier_heartbeat.json），PASS/FAIL 皆靜默。
  靜默的理由：升級告警由 22:40 `closeout_check.py`（每日 checklist 第 ⑧ 步）負責，
  這裡再推一次＝同一件事推兩個通道（噪音）。
* 只有 `rc=2 (NOT_RUN)` 才吐一行 —— 那代表驗證器根本沒跑（檔不見／逾時／無法執行），
  屬「無聲失效」類，應立即現形，不必等 22:40。
"""
import os
import subprocess
import sys

REPO = r"C:/Users/bot/Desktop/longjiu_system"
TARGET = os.path.join(REPO, "tools", "run_verifier_heartbeat.py")
EXIT_NOT_RUN = 2

if not os.path.exists(TARGET):
    sys.stderr.write(f"ERROR: 找不到真身 {TARGET}\n")
    sys.exit(1)

r = subprocess.run([sys.executable, TARGET, "--quiet"], cwd=REPO,
                   capture_output=True, text=True, timeout=600)
if r.stdout:
    sys.stdout.write(r.stdout)
if r.stderr:
    sys.stderr.write(r.stderr)

if r.returncode == EXIT_NOT_RUN:
    sys.stdout.write("❌ 驗證器心跳：NOT_RUN —— verify_ficriteria 沒跑（無聲失效；"
                     "詳見 data/verifier_heartbeat.json）\n")

# 一律 exit 0：驗證結果的真實性由心跳檔承載，**升級告警的唯一通道是 22:40
# closeout_check.py 第 ⑧ 步**（每日 checklist）。若在此讓 rc≠0，cron 引擎會再送一次
# 「error alert」→ 同一件事推兩個通道（重複警報，違反 monitor-noise-governance）。
# 唯一的例外是轉發器自身故障（找不到真身），那才是這支的責任，已在上面 exit 1。
sys.exit(0)
