#!/usr/bin/env python3
"""cron 薄 wrapper：治理巡檢（backfill 缺漏 RECORD → resync 派生欄位 → flush 孤兒產物）。"""

# 為什麼要這支（2026-11-17 實踩）：
#   手動 commit 治理檔（snapshot.json）沒落 RECORD → push gate 對整段待推範圍
#   fail-closed → 22:00 晚報與同輪 25 檔產物全部無法上線（rc=1）；該批產物隨後又因
#   「執行前已 dirty」被 evening_sync 永久排除，工作區卡 7 小時、線上停舊版。
#   兩支本體已存在，這支只負責在固定時點依序叫它們跑，且無事時完全靜默（stdout 空
#   ＝不推播），有事才輸出摘要。
#
# 順序不可顛倒：先補 RECORD（解開 gate），flush 的 commit_code_now 才推得出去。

import os
import subprocess
import sys

# 真身用絕對路徑：本檔會被鏡像到 hermes/scripts/，屆時 __file__ 的 parent 會認錯 repo
# （見 wrappers/data_closeout_commit.py 的同一個坑）。
REPO = r"C:/Users/bot/Desktop/longjiu_system"

STEPS = [
    # 順序不可換：先補 RECORD 解開 push gate，再修派生欄位（讓本輪產物數字正確），
    # 最後才回收產物並推送。
    ("RECORD 巡檢補齊", os.path.join(REPO, "tools", "backfill_records.py"), ["--quiet"]),
    ("派生欄位重算", os.path.join(REPO, "tools", "resync_aliases.py"), ["--fix", "--quiet"]),
    ("孤兒產物回收", os.path.join(REPO, "tools", "flush_leftover_artifacts.py"), ["--quiet"]),
]

blocks = []
rc_all = 0
for label, target, extra in STEPS:
    proc = subprocess.run(
        [sys.executable, target, *extra],
        cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    body = (proc.stdout or "").strip()
    if proc.returncode != 0:
        rc_all = 1
        err = (proc.stderr or "").strip()[:800]
        blocks.append(f"❌ {label} 失敗 rc={proc.returncode}"
                      + (f"\n{body}" if body else "") + (f"\n{err}" if err else ""))
    elif body:
        blocks.append(f"▶ {label}\n{body}")

if blocks:
    print("\n\n".join(blocks))

sys.exit(rc_all)
