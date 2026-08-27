#!/usr/bin/env python3
"""morning_batch.py — 晨間 no-agent 批次（2026-08-27 cron 合併）

合併原 4 個 cron：
- 龍九主動提醒 08:00（reminder_agent.py，每天）
- 配息入帳提醒 08:00（dividend_reminder.py，週一五）
- 決策自動閉環掃描 08:05（decision_auto_close.py，每天）
- 龍九晨間簡報 08:30（run_morning_briefing.py，週一五）

頻率邏輯：週末跳過配息提醒與晨間簡報（與原排程一致）。
"""
import subprocess, sys
from pathlib import Path
from datetime import date

REPO = Path("C:/Users/bot/Desktop/longjiu_system")
DOW = date.today().weekday()  # 0=Mon .. 4=Fri
IS_WEEKDAY = DOW <= 4


def run(name: str) -> None:
    p = REPO / name
    if not p.exists():
        print(f"⚠️ 跳過 {name}：不存在")
        return
    try:
        r = subprocess.run([sys.executable, str(p)], capture_output=True,
                           text=True, timeout=180)
        out = (r.stdout or "").strip()
        if r.returncode == 0:
            print(f"▶ {name} ✅" + (f"\n{out[:600]}" if out else ""))
        else:
            print(f"▶ {name} ⚠️ rc={r.returncode}: {(r.stderr or '')[:300]}")
    except subprocess.TimeoutExpired:
        print(f"▶ {name} ⏰ 逾時")


# 每天固定
run("reminder_agent.py")
run("decision_auto_close.py")
# 週一至週五限定
if IS_WEEKDAY:
    run("dividend_reminder.py")
    run("run_morning_briefing.py")

print("✅ 晨間批次完成")
