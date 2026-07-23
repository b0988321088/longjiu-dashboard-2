#!/usr/bin/env python3
"""sync_all.py — 一鍵同步 longjiu_system/ 腳本到 hermes/scripts/"""

from pathlib import Path
from logging_config import get_logger
logger = get_logger("sync_all")
import shutil

BASE = Path(__file__).resolve().parent
TARGET = Path.home() / "AppData/Local/hermes/scripts"

SCRIPTS = [
    "update_all.py",
    "run_daily.py",
    "daily_intel.py",
    "hunter_intel.py",
    "asset_diff_monitor.py",
    "daily_deploy.py",
    "pre_push_audit.py",
    "budget_daily_check.py",
    "calendar_sync.py",
    "notion_bridge.py",
    "cost_monitor.py",
    "penetration_monitor.py",
    "compile_intel.py",
    "sync_all.py",  # 也同步自己
]

ok, fail = 0, 0
for name in SCRIPTS:
    src = BASE / name
    dst = TARGET / name
    if src.exists():
        shutil.copy2(src, dst)
        print(f"  ✅ {name}")
        ok += 1
    else:
        print(f"  ⚠️  {name} 不存在，跳過")
        fail += 1

print(f"\n✅ 同步完成：{ok} 成功，{fail} 跳過")
# auto-sync test 12:45
