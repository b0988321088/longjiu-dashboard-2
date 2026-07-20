"""龍九日報流程 — 07:00 離峰執行（無 LLM 呼叫）"""
import subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
result = subprocess.run([sys.executable, str(BASE / "run_daily.py")], capture_output=True, text=True, timeout=300)
print(result.stdout[-500:] if result.stdout else "")
if result.returncode != 0:
    print(f"❌ run_daily 失敗: {result.stderr[-300:]}")
    sys.exit(1)
print("✅ 日報已產出（07:00 離峰完成）")
