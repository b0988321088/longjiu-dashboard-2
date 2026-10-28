#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""commit_code_now.py — 「改完程式就跑這一支」：把 dirty 的程式檔一次走完
commit → 真 CIO 審查 → RECORD → push → remote sha 驗證。

為什麼要這支（2026-10-28 兩次實踩）：
  ① 早上手動 `git add memory_archiver.py && git commit` 後沒送審 → 07:00 產線因
     「待推範圍含未落紀錄的舊 commit」fail-closed 全停。
  ② 晚上改了 run_daily.py＋tools/verify_performance_core_task12.py 卻只 commit 了
     cio_review.py → 22:40 收工檢查抓「未提交: [...]」整班 FAIL。
兩者同型：**程式檔只要離開工作區，就一定得走完審查與推送**，中間任何半套狀態
（已 commit 未審查／已改未 commit）都會在下一個自動班引爆。

行為（fail-closed）：
  · 只挑 dirty 的「程式檔」（副檔名白名單），不動資料檔、不動 _bak_*／備份目錄
  · 無 dirty 程式檔 → 直接 rc=0（可安全放進任何收尾流程）
  · 有 → git add 這些檔 → commit → tools/review_commit_and_record.py → auto_push.py
  · 審查 REJECT／閘門不過 → 不推送、rc=1（留下的 commit 仍待處理，訊息會講清楚）

用法：
  python tools/commit_code_now.py "fix(x): 說明"   # 預設訊息見 DEFAULT_MSG
  python tools/commit_code_now.py --check          # 只檢查有沒有 dirty 程式檔
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CODE_EXTS = {".py", ".sh", ".bat", ".ps1", ".cmd", ".toml", ".yml", ".yaml",
             ".js", ".ts", ".sql", ".githooks"}
# 不該被本工具掃進來的目錄（備份／證據／外部快照）
SKIP_PARTS = ("_bak", "_r2_evidence", ".archive", "longjiu_backups", "node_modules",
              "__pycache__", "moneybook", "tmp_mb", ".git/")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(BASE), capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def dirty_code_files(include_untracked: bool = False) -> list[str]:
    """預設只收「已受版控的修改」（M/A/R/D）；未追蹤新檔要明示 --include-untracked。

    為什麼：repo 裡長期躺著一批一次性／測試腳本（apply_truth_*.py、mb_peek_*.py、
    tools/test_*.py）從未入版控，若一併掃進來就會變成一顆 27 檔的巨型 commit，
    審查被稀釋、也把不該落版的東西落版。收工檢查抱怨的「未提交」是**已追蹤**的修改。
    """
    out = []
    for ln in git("status", "--porcelain").splitlines():
        if len(ln) < 4:
            continue
        status, path = ln[:2], ln[3:].strip().strip('"')
        if " -> " in path:                     # rename：取新路徑
            path = path.split(" -> ", 1)[1].strip().strip('"')
        untracked = status == "??"
        if untracked and not include_untracked:
            continue
        if any(p in path for p in SKIP_PARTS):
            continue
        suffix = Path(path).suffix.lower()
        if suffix in CODE_EXTS or path.startswith(".githooks/"):
            out.append(path)
    return out


def run(*cmd: str) -> int:
    p = subprocess.run([sys.executable, *cmd], cwd=str(BASE))
    return p.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="dirty 程式檔 → commit → 真 CIO 審查 → push")
    ap.add_argument("message", nargs="?", default="")
    ap.add_argument("--check", action="store_true", help="只列出 dirty 程式檔，不改任何狀態")
    ap.add_argument("--include-untracked", action="store_true",
                    help="連未追蹤的新程式檔一起收（新增工具時用）")
    ap.add_argument("--only", nargs="*", default=[], help="只處理指定路徑（可多個）")
    a = ap.parse_args()

    files = a.only or dirty_code_files(a.include_untracked)
    if not files:
        print("✅ 無 dirty 程式檔（工作區程式碼乾淨）")
        return 0
    print(f"📋 dirty 程式檔 {len(files)} 支：")
    for f in files:
        print(f"   · {f}")
    if a.check:
        return 0

    msg = a.message or f"chore: 程式檔整批落版（{datetime.now():%Y-%m-%d %H:%M}）"
    if subprocess.run(["git", "add", "--", *files], cwd=str(BASE)).returncode != 0:
        print("❌ git add 失敗 → 中止")
        return 1
    if subprocess.run(["git", "commit", "-q", "-m", msg], cwd=str(BASE)).returncode != 0:
        print("❌ git commit 失敗 → 中止（未推送）")
        return 1
    sha = git("rev-parse", "--short", "HEAD").strip()
    print(f"✅ 已 commit {sha}：{msg}")

    tag = f"code_{datetime.now():%Y%m%d_%H%M%S}"
    if run(str(BASE / "tools" / "review_commit_and_record.py"), sha, tag) != 0:
        print(f"❌ 真 CIO 審查未通過 → 不推送。修完後重跑：python tools/commit_code_now.py")
        print(f"   （commit {sha} 仍在本地、尚未取得 RECORD，勿留過夜）")
        return 1
    if run(str(BASE / "auto_push.py")) != 0:
        print("❌ push 失敗 → 遠端未更新（見上方 auto_push 訊息）")
        return 1

    ahead = git("rev-list", "--count", "origin/clean-main..HEAD").strip()
    remote = subprocess.run(["git", "ls-remote", "origin", "clean-main"], cwd=str(BASE),
                            capture_output=True, text=True).stdout.strip()[:12]
    head = git("rev-parse", "--short", "HEAD").strip()
    ok = ahead == "0" and remote.startswith(head[:8])
    print(f"{'✅' if ok else '❌'} 驗證：未推 {ahead}｜local {head}｜remote {remote}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
