"""更新 snapshot → 產出儀表板+日報 → 推送 GitHub — 一鍵完成"""
import json, subprocess, sys
from pathlib import Path

BASE = Path(__file__).parent.resolve()
SNAP = BASE / "snapshot.json"

def step(msg):
    print(f"\n[STEP] {msg}")

def run(cmd, timeout=120):
    return subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True, timeout=timeout)

# 1. 確認 snapshot 最新
step("讀取 snapshot")
snap = json.loads(SNAP.read_text())
print(f"  snapshot: {SNAP.name}")
print(f"  total_assets: {snap.get('total_assets',0):,}")
print(f"  monthly_dividend: {snap.get('monthly_dividend',0):,}")

# 2. 跑 run_daily（產出 index.html + daily_report）
step("run_daily.py 產出儀表板+日報")
r = run([sys.executable, str(BASE / "run_daily.py")])
if r.returncode != 0:
    print(f"  ❌ 失敗: {r.stderr[:200]}")
    sys.exit(1)
print(f"  ✅ 產出完成")

# 3. 跑 asset_diff
step("asset_diff_monitor.py 產出差異分析")
r = run([sys.executable, str(BASE / "asset_diff_monitor.py")])
if r.returncode != 0:
    print(f"  ⚠️ asset_diff 警告: {r.stderr[:200]}")
print(f"  ✅ 差異分析完成")

# 4. git push
step("git add + commit + push")
r = run(["git", "add", "-f", "index.html", "snapshot.json"])
if r.returncode != 0:
    print(f"  ⚠️ git add: {r.stderr[:100]}")
r = run(["git", "commit", "-m", "auto: snapshot→dashboard→deploy", "--allow-empty"])
r = run(["git", "push", "--force", "origin", "main:clean-main"])
if r.returncode != 0:
    print(f"  ❌ git push 失敗: {r.stderr[:200]}")
    sys.exit(1)
print(f"  ✅ GitHub 推送完成")

print(f"\n🎉 全部完成：snapshot → 儀表板 → 日報 → 差異分析 → GitHub")
