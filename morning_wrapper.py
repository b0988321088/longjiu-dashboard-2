#!/usr/bin/env python3
"""morning_wrapper.py — 龍九晨間自動化：依序執行費用→日曆→日報"""
import subprocess, sys, time
from pathlib import Path

BASE = Path(__file__).resolve().parent

scripts = [
    ("cost_monitor.py", 3),
    ("calendar_sync.py", 5),
    ("update_all.py", 3),
]

for name, wait in scripts:
    path = BASE / name
    if not path.exists():
        print(f"⚠️ 跳過 {name}：不存在")
        continue
    print(f"▶ 執行 {name}...")
    try:
        r = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            print(f"  ✅ {name} 成功")
        else:
            print(f"  ⚠️ {name} 返回碼 {r.returncode}：{r.stderr[:200]}")
    except subprocess.TimeoutExpired:
        print(f"  ⏰ {name} 逾時")
    time.sleep(wait)

print("✅ 晨間自動化完成")
