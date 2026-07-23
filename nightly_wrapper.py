#!/usr/bin/env python3
"""nightly_wrapper.py — 龍九夜間維護：Notion同步 → 夜間整理"""
import subprocess, sys, time
from pathlib import Path
from logging_config import get_logger
logger = get_logger("nightly_wrapper")

BASE = Path(__file__).resolve().parent

scripts = [
    ("notion_sync.py", 5),
    ("nightly_maintenance.py", 0),
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

logger.info("✅ 夜間維護完成")
