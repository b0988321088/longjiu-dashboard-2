#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cron wrapper：盤前快報（每日 08:20，no_agent）

四段：夜盤台指期 → 美股隔夜 → 對策方向（動作階梯＋煞車）→ 流向雷達整體評估。
真身：longjiu_system/morning_brief.py

注意：wrapper 會被部署到 hermes/scripts/，那裡的 parents[1] 不是 repo →
      必須寫死 repo 路徑（全體 wrapper 同一慣例），否則 cron 一定 rc=2。
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(r"C:\Users\bot\Desktop\longjiu_system")
TARGET = REPO / "morning_brief.py"

if not TARGET.exists():
    print(f"⛔ morning_brief.py 不存在（{TARGET}）")
    sys.exit(1)

r = subprocess.run([sys.executable, str(TARGET)], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=240, cwd=str(REPO))
out = (r.stdout or "").strip()
if out:
    print(out)
elif r.returncode != 0:
    print(f"⚠️ 盤前快報失敗 rc={r.returncode}\n{(r.stderr or '')[-400:]}")
sys.exit(0 if r.returncode == 0 else 1)
