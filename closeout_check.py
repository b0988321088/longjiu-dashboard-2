#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""closeout_check.py — 龍九每日收工檢查（一鍵；stdlib only）

把收工要跑的檢查串成一支：原本要手動跑 6 支，現在一支跑完出報告。

步驟
----
1. **排程時點認領偵測**（INC-172）：找出「手動 fire 預先完成未來排程時點」的執行列
   → 這些會讓該次正式排程靜默消失（詳見 release_claimed_occurrences.py 檔頭）。
2. **閉環稽核**：`_audit_closeout.py`（舊值殘留／四源一致／GitHub Pages／git／鏡像／cron／監控檔／認領）。
3. **彙總**：印出結論 + 「需補跑的產出」清單（每筆給可直接複製的指令）。

用法
----
    python closeout_check.py            # 檢查（不動任何東西）
    python closeout_check.py --fix      # 順便釋放被誤認領的時點（先備份 executions.db）
    python closeout_check.py --quiet    # 全綠時只印一行摘要（cron watchdog 用）

exit code：0 = 全部通過；1 = 有問題（或仍有未釋放的認領）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
import release_claimed_occurrences as rco  # noqa: E402


def step_claims(fix: bool, quiet: bool) -> int:
    """回傳『未解決的認領數』。"""
    db = rco.default_db()
    jobs = rco.load_jobs()
    claims = rco.find_claims(db)
    if not claims:
        if not quiet:
            print("① 排程時點認領：✅ 乾淨（沒有被預先完成的未來時點）")
        return 0
    print(f"① 排程時點認領：❌ {len(claims)} 筆未來時點已被手動執行預先完成 → 該次排程會靜默消失")
    for c in claims:
        j = jobs.get(c["job_id"], {})
        print(f"   🔴 {c['job_id'][:12]} {(j.get('name') or '')[:26]}｜認領 {c['scheduled_instant']}")
        print(f"        補跑：{rco.rerun_hint(c['job_id'], jobs)}")
    if fix:
        bak = rco.release(db, claims)
        left = rco.find_claims(db)
        print(f"   🔧 已釋放 {len(claims)} 筆（備份 {bak.name}）→ 殘留 {len(left)} 筆")
        return len(left)
    print("   （未釋放。加 --fix 一鍵釋放後再補跑上面指令）")
    return len(claims)


def step_audit(quiet: bool) -> tuple:
    """回傳 (exit_code, 結論行, 完整輸出)。"""
    p = subprocess.run([sys.executable, str(REPO / "_audit_closeout.py")],
                       capture_output=True, text=True, cwd=str(REPO))
    out = (p.stdout or "") + (p.stderr or "")
    concl = next((l.strip() for l in out.splitlines() if l.startswith("閉環稽核結果")), "（無結論行）")
    if not quiet:
        print("\n② 閉環稽核輸出：\n" + out.rstrip())
    else:
        print(f"② 閉環稽核：{concl}")
    return p.returncode, concl, out


def main() -> int:
    ap = argparse.ArgumentParser(description="龍九每日收工檢查（一鍵）")
    ap.add_argument("--fix", action="store_true", help="釋放被誤認領的排程時點")
    ap.add_argument("--quiet", action="store_true", help="全綠時只印摘要")
    args = ap.parse_args()

    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    if not args.quiet:
        print("=" * 52)
        print(f"龍九收工檢查　{stamp}")
        print("=" * 52)

    left_claims = step_claims(args.fix, args.quiet)
    rc, concl, out = step_audit(args.quiet)

    problems = []
    if left_claims:
        problems.append(f"未釋放的排程認領 {left_claims} 筆")
    if "全部通過" not in concl:
        problems.append(concl.replace("閉環稽核結果：", ""))

    print()
    print("=" * 52)
    if not problems:
        print(f"收工檢查：全部通過 ✅　（{stamp}）")
    else:
        print("收工檢查：❌ 有問題")
        for x in problems:
            print(f"  - {x}")
    print("=" * 52)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
