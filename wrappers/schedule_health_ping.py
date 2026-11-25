#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cron wrapper：排程健康摘要（每日 07:30，no_agent）

只做一件事：失敗才出聲。全部正常 → 無輸出（靜默）。
真身在 longjiu_system/schedule_health.py。
"""
import subprocess
import sys
from pathlib import Path

TARGET = Path(r"C:\Users\bot\Desktop\longjiu_system\schedule_health.py")

if not TARGET.exists():
    print(f"⛔ schedule_health.py 不存在（{TARGET}）→ 無法檢查排程健康")
    sys.exit(1)

r = subprocess.run([sys.executable, str(TARGET)], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=90)
out = (r.stdout or "").strip()
if r.returncode != 0:
    tail = ((r.stderr or "").strip().splitlines() or [""])[-1][:160]
    print(f"⚠️ 排程健康檢查失敗 rc={r.returncode}｜{tail}")
    sys.exit(1)
if out:
    print(out)
