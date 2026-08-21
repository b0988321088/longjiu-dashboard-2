"""notion_ai_weekly_wrapper.py — Notion AI 週報（每週五 10:00 cron 真值，2026-08-21 建立）
薄轉發器：呼叫 notion_ai_summary.py weekly（唯一真值），確保 BASE = repo 讀最新資料。
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    target = os.path.join(BASE, "notion_ai_summary.py")
    if not os.path.exists(target):
        sys.stderr.write("ERROR: notion_ai_summary.py not found: " + target + chr(10))
        sys.exit(1)
    r = subprocess.run([sys.executable, target, "weekly"],
                       cwd=BASE, capture_output=True, text=True, timeout=900)
    sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
