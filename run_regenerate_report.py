"""run_regenerate_report.py — 在正式 repo 內執行 regenerate_report.py（cron 入口）

背景（2026-08-04 修正）：
cron job 的 script 欄位只會解析到 HERMES_HOME/scripts/ 下的檔案。
若直接把 script 指向 regenerate_report.py，該檔的 BASE = hermes/scripts
（非 git repo、資料檔停留在上次 sync 的舊版），導致：
  1. git add/commit/push 全部失敗（❌ 推到 clean-main）
  2. GitHub Pages 404
本 wrapper 改為：cd 到正式 repo（Desktop/longjiu_system）再執行
repo 內的 regenerate_report.py，讓 BASE = repo（git repo + 最新資料），
產出、commit、雙分支 push、HTTP 200 驗證一次完成。
"""
import subprocess, sys, os

CRON_WORKDIR = "C:/Users/bot/Desktop/longjiu_system"
TARGET_SCRIPT = "regenerate_report.py"

target_full_path = os.path.join(CRON_WORKDIR, TARGET_SCRIPT)

if not os.path.exists(target_full_path):
    sys.stderr.write(f"ERROR: Target script not found: {target_full_path}\n")
    sys.exit(1)

try:
    r = subprocess.run(
        [sys.executable, target_full_path] + sys.argv[1:],
        cwd=CRON_WORKDIR,
        capture_output=True,
        text=True,
        timeout=600,
    )
    sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write("SUBPROCESS STDERR:\n")
        sys.stderr.write(r.stderr)
    sys.exit(r.returncode)
except Exception as e:
    sys.stderr.write(f"ERROR: Subprocess execution failed: {e}\n")
    sys.exit(1)
