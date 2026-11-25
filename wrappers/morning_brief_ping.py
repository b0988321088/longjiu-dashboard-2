#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cron wrapper：盤前快報（每日 08:20，no_agent）

四段：夜盤台指期 → 美股隔夜 → 對策方向（動作階梯＋煞車）→ 流向雷達整體評估。
真身：longjiu_system/morning_brief.py
"""
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
r = subprocess.run([sys.executable, str(BASE / "morning_brief.py")],
                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                   cwd=str(BASE))
out = (r.stdout or "").strip()
if out:
    print(out)
elif r.returncode != 0:
    print(f"⚠️ 盤前快報失敗 rc={r.returncode}\n{(r.stderr or '')[-400:]}")
sys.exit(0 if r.returncode == 0 else 1)
