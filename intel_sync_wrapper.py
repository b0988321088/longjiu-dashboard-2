#!/usr/bin/env python3
"""intel_sync_wrapper.py — 合併 Hunter情報 + Notion戰略手稿同步"""
import subprocess, sys, time
from pathlib import Path
from self_publish import commit_own   # 必須在「開始做事之前」import：T0 才等於本輪起跑（模組契約）
from logging_config import get_logger
logger = get_logger("intel_sync_wrapper")

BASE = Path(__file__).resolve().parent

scripts = [
    ("hunter_intel.py", 5),
    ("notion_bridge.py", 5),
]

for name, wait in scripts:
    path = BASE / name
    if not path.exists():
        logger.warning(f"⚠️ 跳過 {name}：不存在")
        continue
    print(f"▶ 執行 {name}...")
    r = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=120)
    if r.returncode == 0:
        print(f"  ✅ {name} 成功")
    else:
        print(f"  ❌ {name} 失敗：{r.stderr[:200]}")
    time.sleep(wait)

logger.info("✅ 情報同步完成")

# 2026-10-12 TD-20261012-25 延伸：notion_bridge 的戰術手稿（notion_bridge/<日期>_strategy_handbook.md）
# 過去只留工作區 → 每晚被判「已追蹤未提交」。跑完就地提交自家產物（純資料），走 auto_push 唯一出口。
sys.exit(commit_own("intel_sync_wrapper.py", ["notion_bridge/*.md"]))
