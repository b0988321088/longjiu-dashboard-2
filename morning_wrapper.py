#!/usr/bin/env python3
"""morning_wrapper.py — 龍九晨間自動化：依序執行費用→日曆→日報"""
import subprocess, sys, time
from pathlib import Path
from logging_config import get_logger
logger = get_logger("morning_wrapper")

BASE = Path(__file__).resolve().parent

scripts = [
    ("cost_monitor.py", 3),
    ("calendar_sync.py", 3),
    ("notion_context_loader.py", 2),
    ("update_all.py", 3),
]

for name, wait in scripts:
    path = BASE / name
    if not path.exists():
        logger.warning(f"⚠️ 跳過 {name}：不存在")
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

logger.info("✅ 晨間自動化完成")
