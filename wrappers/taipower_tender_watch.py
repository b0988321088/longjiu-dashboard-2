"""taipower_tender_watch.py — 薄轉發器（2026-11-02 建立）
cron 固定從 HERMES_HOME/scripts/ 執行；本檔轉發到正式 repo（唯一真值），
確保 BASE=repo（snapshot／state 都在 repo），不因 cwd 位移讀不到檔。
"""
import subprocess, sys, os

REPO_DIR = r"C:\Users\bot\Desktop\longjiu_system"
REPO_SCRIPT = os.path.join(REPO_DIR, "taipower_tender_watch.py")


def main():
    if not os.path.exists(REPO_SCRIPT):
        sys.stderr.write("ERROR: repo script not found: " + REPO_SCRIPT + "\n")
        sys.exit(1)
    r = subprocess.run([sys.executable, REPO_SCRIPT] + sys.argv[1:],
                       cwd=REPO_DIR, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    sys.stdout.write(r.stdout or "")
    if r.stderr:
        sys.stderr.write(r.stderr)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
