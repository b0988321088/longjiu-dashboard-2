"""龍九台股緊急應變 13:00 — 刷新情報 + 彙整 + 三份產出"""
import subprocess, sys
from pathlib import Path
from datetime import datetime

LJ = Path.home() / "Desktop" / "龍九系統"
today = __import__("datetime").date.today().isoformat()

def run_step(label, cmd, timeout=120):
    ts = datetime.now().strftime("%H%M")
    print(f"[{ts}] {label}...", end=" ", flush=True)
    r = subprocess.run(cmd, cwd=str(LJ), capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        print(f"❌ 失敗\n{r.stderr[:200]}")
        return False
    out = r.stdout.strip()
    if out:
        for l in out.split("\n")[-3:]:
            print(f"  {l}")
    print(f"✅")
    return True

ts = datetime.now().strftime("%H%M")
print(f"\n[{ts}] 🚨 台股緊急應變啟動")

run_step("刷新情報", [sys.executable, str(LJ / "daily_intel.py")], 60)
run_step("彙整情報", [sys.executable, str(LJ / "compile_intel.py")], 30)

# snapshot 市場數據（inline 腳本需自帶 import）
_snap_script = f"""
import json, sqlite3
from pathlib import Path
LJ = Path(r'{LJ}')
db = sqlite3.connect(str(LJ / 'dragon_assets.db'))
r = db.execute("SELECT tw_index, tw_change FROM market_intel WHERE date=? ORDER BY id DESC LIMIT 1", ('{today}',)).fetchone()
snap = json.loads((LJ / 'snapshot.json').read_text('utf-8'))
if r and r[0]:
    snap['market'] = {{'twii': f'{{r[0]:,.2f}} ({{r[1]:+.2f}}%)'}}
# 若無資料則保留 snapshot 原有市場值，不覆蓋
(LJ / 'snapshot.json').write_text(json.dumps(snap, ensure_ascii=False, indent=2), 'utf-8')
db.close()
print(f'市場指數: {{r[0]:,.2f}} ({{r[1]:+.2f}}%)' if r and r[0] else '無指數資料')
"""
run_step("更新 snapshot 市場數據", [sys.executable, "-c", _snap_script], 30)

# 3.5 若 market_intel 有今日本日最新指數資料，更新 snapshot

run_step("日報+儀表板", [sys.executable, str(LJ / "run_daily.py")], 120)
run_step("差異分析", [sys.executable, str(LJ / "asset_diff_monitor.py")], 60)
run_step("推送", [sys.executable, str(LJ / "daily_deploy.py")], 120)

print(f"\n✅ [{datetime.now().strftime('%H%M')}] 緊急應變完成")
