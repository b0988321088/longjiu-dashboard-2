#!/usr/bin/env python3
"""sync_all.py — 龍九一鍵同步管線 v2（2026-08-24 檢討修正）
依序執行：資產驗證 → 日報 → 緊急應變 → 穿透 → 四源 → 同義欄位 → 一致性 → 再平衡/週報
v2 修正：①加入 asset_sync.py（同義欄位驗證，2026-08-24 血淚：漏欄位不抓）②輸出完整（非只 tail）③失敗即停
用法：python sync_all.py [date]
"""
import subprocess, sys, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent

def run(label, cmd, timeout=300, stop_on_fail=True):
    print(f"\n=== {label} ===")
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(BASE), capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        # 印出關鍵輸出（成功/失敗標記）
        for line in (out or "").splitlines()[-3:]:
            if any(k in line for k in ["✅", "❌", "⚠️", "同步", "一致", "完成", "記憶已寫入"]):
                print("  " + line.strip()[:100])
        if r.returncode != 0:
            for line in (err or "").splitlines()[-2:]:
                print("  ⚠️ " + line.strip()[:100])
            if stop_on_fail:
                print("⛔ 失敗中止（後續步驟未執行）")
                return False
        return r.returncode == 0
    except Exception as e:
        print(f"❌ {e}")
        return False

def main():
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y-%m-%d")
    print(f"🔁 龍九一鍵同步 v2（{today}）")
    steps = [
        ("同義欄位驗證", f"python asset_sync.py"),
        ("日報", f"python run_daily.py"),
        ("緊急應變", f"python gen_emergency_{today[5:7]}{today[8:10]}.py"),
        ("台股緊急應變", f"python emergency_1330.py"),
        ("穿透報告", f"python build_penetration_report.py"),
        ("四源同步", f"python four_source_sync.py"),
        ("同義欄位複驗", f"python asset_sync.py"),
        ("一致性檢查", f"python check_penetration_consistency.py {today}"),
        ("再平衡報告", f"python build_rebalance_report.py"),
        ("週報", f"python build_weekly_report.py"),
    ]
    ok = True
    for label, cmd in steps:
        r = run(label, cmd)
        if not r:
            ok = False
            break  # 失敗即停（避免在錯誤資料上繼續）
    print(f"\n{'✅ 全部完成（10 步驟）' if ok else '⚠️ 有步驟失敗（見上）'}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
