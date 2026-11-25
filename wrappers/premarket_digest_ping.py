#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cron wrapper：盤前 digest（每日 09:10，no_agent）

把原本 09:00–09:20 各自推的 6 支檢查併成一則；全無事項 → 靜默。
真身在 longjiu_system/digest_premarket.py（並行執行，牆鐘約 3 分鐘，timeout 給 420s）。
"""
import subprocess
import sys
from pathlib import Path

TARGET = Path(r"C:\Users\bot\Desktop\longjiu_system\digest_premarket.py")

if not TARGET.exists():
    print(f"⛔ digest_premarket.py 不存在（{TARGET}）→ 盤前 digest 中止")
    sys.exit(1)

r = subprocess.run([sys.executable, str(TARGET)], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=420)
out = (r.stdout or "").strip()
if r.returncode != 0:
    tail = ((r.stderr or "").strip().splitlines() or [""])[-1][:160]
    print(f"⚠️ 盤前 digest 執行失敗 rc={r.returncode}｜{tail}")
    sys.exit(1)
if out:
    print(out)
