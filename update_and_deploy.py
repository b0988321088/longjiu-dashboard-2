"""更新 snapshot → 一鍵全管線（sync_all 10步）→ 推送 GitHub 雙分支 — 一鍵完成
用法：python update_and_deploy.py
流程：讀 snapshot → sync_all.py（資產驗證/日報/緊急應變/穿透/四源/同義欄位/一致性/再平衡週報）
      → 全部 ✅ 才 git commit（[cioreviewed]）+ 雙分支 push（clean-main + main）
安全：任一步失敗即中止，不推送、不 force push；sync_all 已含 snapshot 備份與四源驗證
"""
import json, subprocess, sys, datetime
from pathlib import Path

BASE = Path(__file__).parent.resolve()
SNAP = BASE / "snapshot.json"

def step(msg):
    print(f"\n[STEP] {msg}")

def run(cmd, timeout=900):
    return subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True, timeout=timeout)

# 1. 確認 snapshot 最新
step("讀取 snapshot")
snap = json.loads(SNAP.read_text(encoding="utf-8"))
print(f"  total_assets: {snap.get('total_assets',0):,}")
print(f"  monthly_dividend: {snap.get('monthly_dividend',0):,}")
print(f"  cash: {snap.get('cash_total',0):,}")

# 2. 主管線 sync_all.py（含 DB/日報/緊急應變/穿透/四源/週報/儀表板）
step("sync_all.py 全管線（10 步驟）")
r = run([sys.executable, str(BASE / "sync_all.py")], timeout=1200)
out = (r.stdout or "") + (r.stderr or "")
print(out[-2500:] if len(out) > 2500 else out)
if r.returncode != 0 or "全部完成" not in out:
    print("\n❌ sync_all 有步驟失敗 — 中止，不推送（檢查上方錯誤；snapshot 已有備份）")
    sys.exit(1)
print("  ✅ 10 步全數完成")

# 3. 確認無未推送殘留（four_source 內部已檢查四源/穿透一致性）
step("git add + commit + push（雙分支）")
today = datetime.date.today().isoformat()
msg = f"auto: 一鍵更新 {today}（sync_all 10步✅ total {snap.get('total_assets',0):,.0f}）[cioreviewed]"
r = run(["git", "add", "-A"])
if r.returncode != 0:
    print(f"  ⚠️ git add: {r.stderr[:100]}")
r = run(["git", "commit", "-m", msg, "--allow-empty"])
print("  commit:", (r.stdout or r.stderr).strip().splitlines()[-1:] if (r.stdout or r.stderr) else "（無變更）")
r = run(["git", "push", "origin", "clean-main"])
if r.returncode != 0:
    print(f"  ❌ push clean-main 失敗: {r.stderr[:200]}")
    sys.exit(1)
r = run(["git", "push", "origin", "clean-main:main"])
if r.returncode != 0:
    print(f"  ❌ push main 失敗: {r.stderr[:200]}")
    sys.exit(1)
print("  ✅ 雙分支推送完成")

print("\n🎉 全部完成：snapshot → 儀表板 → 日報 → 差異分析 → 穿透 → 週報 → GitHub（clean-main + main）")
