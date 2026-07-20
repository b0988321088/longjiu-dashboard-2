"""龍九日報推送 — 08:30 執行（CIO審查 + git push + Telegram）"""
import subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
result = subprocess.run([sys.executable, str(BASE / "daily_deploy.py")], capture_output=True, text=True, timeout=300)
print(result.stdout[-500:] if result.stdout else "")
if result.returncode != 0:
    print(f"❌ deploy 失敗: {result.stderr[-300:]}")
    sys.exit(1)
print("✅ 日報已推送（08:30）")
