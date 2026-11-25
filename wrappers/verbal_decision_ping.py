#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cron wrapper：口頭裁決偵測（每日 22:35，no_agent）

對話有裁決語句、但 dashboard_decisions 當日沒有對應筆數 → 出聲提醒補登；一致則靜默。
真身在 longjiu_system/verbal_decision_watch.py。
"""
import subprocess
import sys
from pathlib import Path

TARGET = Path(r"C:\Users\bot\Desktop\longjiu_system\verbal_decision_watch.py")

if not TARGET.exists():
    print(f"⛔ verbal_decision_watch.py 不存在（{TARGET}）")
    sys.exit(1)

r = subprocess.run([sys.executable, str(TARGET)], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=180)
out = (r.stdout or "").strip()
if r.returncode != 0:
    tail = ((r.stderr or "").strip().splitlines() or [""])[-1][:160]
    print(f"⚠️ 口頭裁決偵測失敗 rc={r.returncode}｜{tail}")
    sys.exit(1)
if out:
    print(out)
