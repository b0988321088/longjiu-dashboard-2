#!/usr/bin/env python3
"""sync_all.py — 龍九一鍵同步管線（2026-08-24 建立）
依序執行：日報 → 緊急應變 → 穿透 → 四源 → 一致性 → 週報/再平衡
用法：python sync_all.py [date]
"""
import subprocess, sys, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent

def run(label, cmd, timeout=300):
    print(f"\n=== {label} ===")
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(BASE), capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "").strip().splitlines()
        print(out[-1] if out else f"exit={r.returncode}")
        if r.returncode != 0:
            err = (r.stderr or "").strip().splitlines()
            print("⚠️ ", err[-1] if err else "unknown error")
        return r.returncode == 0
    except Exception as e:
        print(f"❌ {e}")
        return False

def main():
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y-%m-%d")
    print(f"🔁 龍九一鍵同步（{today}）")
    steps = [
        ("日報", f"python run_daily.py"),
        ("緊急應變", f"python gen_emergency_{today[5:7]}{today[8:10]}.py"),
        ("台股緊急應變", f"python emergency_1330.py"),
        ("穿透報告", f"python build_penetration_report.py"),
        ("四源同步", f"python four_source_sync.py"),
        ("一致性檢查", f"python check_penetration_consistency.py {today}"),
        ("再平衡報告", f"python build_rebalance_report.py"),
        ("週報", f"python build_weekly_report.py"),
    ]
    ok = True
    for label, cmd in steps:
        ok = run(label, cmd) and ok
    print(f"\n{'✅ 全部完成' if ok else '⚠️ 有步驟失敗（見上）'}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
