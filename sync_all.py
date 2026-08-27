#!/usr/bin/env python3
"""sync_all.py — 龍九一鍵同步管線 v2（2026-08-24 檢討修正）
依序執行：資產驗證 → 日報 → 緊急應變 → 穿透 → 四源 → 同義欄位 → 一致性 → 再平衡/週報
v2 修正：①加入 asset_sync.py（同義欄位驗證，2026-08-24 血淚：漏欄位不抓）②輸出完整（非只 tail）③失敗即停
用法：python sync_all.py [date]
"""
import subprocess, sys, datetime, json, re
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
    print(f"🔁 龍九一鍵同步 v4（{today}）")
    # v4 檢查 0：儀表板模板硬編碼檢查（2026-08-25：改口徑後 index_template.html 殘留舊值 → 儀表板顯示舊數字）
    try:
        _tpl = (BASE / "index_template.html").read_text(encoding="utf-8")
        _stale = ["152,781", "141,958", "73,137", "27,319", "156,835", "151,958", "143.9%", "144%", "800,272"]
        _hits = [s for s in _stale if s in _tpl]
        if _hits:
            print(f"  ⚠️ index_template.html 殘留舊口徑硬編碼: {_hits} — 儀表板會顯示舊數字，請修正 template（改 monthly_expense 後必查）")
        else:
            print("  ✅ 儀表板模板無舊口徑硬編碼")
    except Exception as e:
        print(f"  ⚠️ 儀表板模板檢查失敗: {e}")
    # v3 自動修復 1：snapshot.date 同步為 today（2026-08-25 血淚：date 停在 8/24 → four_source 檢查舊日期 → 假失敗）
    try:
        sp = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        if sp.get("date") != today:
            old = sp.get("date")
            sp["date"] = today
            (BASE / "snapshot.json").write_text(json.dumps(sp, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
            print(f"  🔧 snapshot.date {old} → {today}")
    except Exception as e:
        print(f"  ⚠️ snapshot.date 修復失敗: {e}")
    # （2026-08-27：gen_emergency_*.py 已刪除，此自動建立邏輯移除；緊急應變僅 emergency_1330.py）
    steps = [
        ("同義欄位驗證", f"python asset_sync.py"),
        ("日報", f"python run_daily.py"),
        # 2026-08-27：gen_emergency_*.py 已刪除（一次性腳本清理），緊急應變僅用 emergency_1330.py（cron 13:00）
        ("台股緊急應變", f"python emergency_1330.py"),
        ("穿透報告", f"python build_penetration_report.py"),
        ("四源同步", f"python four_source_sync.py"),
        ("同義欄位複驗", f"python asset_sync.py"),
        ("一致性檢查", f"python check_penetration_consistency.py {today}"),
        ("再平衡報告", f"python build_rebalance_report.py"),
        ("儀表板注入", "python build_dashboard.py"),
        # 2026-08-27：共享渲染組件自測（report_components 異常 → 報表數字不一致）
        ("組件自測", "python -c \"from report_components import render_health_score; import json; print('✅ 組件正常 健康度', render_health_score(json.load(open('snapshot.json',encoding='utf-8')))['分數'])\""),
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
