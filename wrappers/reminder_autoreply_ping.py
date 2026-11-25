#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cron wrapper：提醒回覆自動落庫（每 10 分鐘，08:00–23:59，no_agent）

抓到「編號＋動作」的短回覆就落地並回收據；沒回覆完全靜默。
真身：longjiu_system/reminder_autoreply.py（單一寫入入口仍是 apply_action_reply.py）
"""
import subprocess
import sys
from pathlib import Path

TARGET = Path(r"C:\Users\bot\Desktop\longjiu_system\reminder_autoreply.py")

if not TARGET.exists():
    print(f"⛔ reminder_autoreply.py 不存在（{TARGET}）")
    sys.exit(1)

r = subprocess.run([sys.executable, str(TARGET)], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=240)
out = (r.stdout or "").strip()
if r.returncode != 0:
    tail = ((r.stderr or "").strip().splitlines() or [""])[-1][:160]
    print(f"⚠️ 回覆自動落庫失敗 rc={r.returncode}｜{tail}")
    sys.exit(1)
if out:
    print(out)
