"""自動轉貸投資簡報產生器 — 由 cron 呼叫，自動輸出 PPTX 並傳送 Telegram"""
import sys, os, subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

# 1. 先確保資料最新
subprocess.run(["python", str(BASE / "update_all.py")], capture_output=True, timeout=60)

# 2. 產出簡報
result = subprocess.run(["python", str(BASE / "presentation_engine.py")], capture_output=True, text=True, timeout=120)
if result.returncode == 0:
    print(result.stdout.strip())
    print("✅ 自動簡報產出完成")
else:
    print(f"❌ 簡報產出失敗: {result.stderr[:200]}")
