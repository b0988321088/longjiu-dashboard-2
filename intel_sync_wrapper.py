#!/usr/bin/env python3
"""intel_sync_wrapper.py — 合併 Hunter情報 + Notion戰略手稿同步"""
import subprocess, sys, time
from pathlib import Path

BASE = Path(__file__).resolve().parent

scripts = [
    ("hunter_intel.py", 5),
    ("notion_bridge.py", 5),
]

for name, wait in scripts:
    path = BASE / name
    if not path.exists():
        print(f"⚠️ 跳過 {name}：不存在")
        continue
    print(f"▶ 執行 {name}...")
    r = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=120)
    if r.returncode == 0:
        print(f"  ✅ {name} 成功")
    else:
        print(f"  ❌ {name} 失敗：{r.stderr[:200]}")
    time.sleep(wait)

print("✅ 情報同步完成")
