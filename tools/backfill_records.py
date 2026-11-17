#!/usr/bin/env python3
"""待推範圍內「無有效 RECORD」的 commit → 逐顆真 CIO 審查補紀錄。

為什麼要這支（2026-11-17 實踩）：
    手動 commit snapshot.json（治理檔）後沒落 RECORD，留下一顆無紀錄 commit 在
    origin/clean-main..HEAD；push gate 對整段範圍 fail-closed，22:00 晚報連同當輪
    25 檔產物全部無法上線（cron rc=1）。規則不該靠「記得」—— 補救要能被時間觸發。

判定與 .githooks/pre-push v4.2 對齊：
    tree hash 在 .git/CIO_APPROVED 有一筆 APPROVE（且 note 非 SELF-DECLARED:*）即視為
    有效；其餘一律補真審查（含僅有 AUTO-checker／TAG／SKIP 者 —— 多審一顆的成本遠低於
    錯放一顆，且審查 REJECT 時本工具不落紀錄）。

用法：
    python tools/backfill_records.py --check     # 只列出待補的 commit，不改任何狀態
    python tools/backfill_records.py             # 逐顆真審查補紀錄（fail-closed）
    python tools/backfill_records.py --limit 1   # 只補最舊的 1 顆（測試用）
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
GITDIR = BASE / ".git"
APPROVE_FILE = GITDIR / "CIO_APPROVED"
BASE_REF = "origin/clean-main"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(BASE), capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def approved_trees() -> set[str]:
    """CIO_APPROVED 內「有效 APPROVE」的 tree 集合（排除自宣告）。"""
    out: set[str] = set()
    if not APPROVE_FILE.exists():
        return out
    for ln in APPROVE_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = ln.split("\t")
        if len(parts) < 4:
            continue
        # 欄序（cio_approve.py 寫入格式）：時間 / tree / commit / verdict / reviewer / note
        tree, verdict = parts[1].strip(), parts[3].strip()
        note = parts[5].strip() if len(parts) > 5 else ""
        if verdict == "APPROVE" and not note.startswith("SELF-DECLARED:"):
            out.add(tree)
    return out


def pending_commits() -> list[tuple[str, str, str]]:
    """(sha, tree, subject) —— 待推範圍內缺有效 RECORD 者，由舊到新。"""
    has = approved_trees()
    shas = [s for s in git("rev-list", "--reverse", f"{BASE_REF}..HEAD").split() if s]
    todo: list[tuple[str, str, str]] = []
    for sha in shas:
        tree = git("rev-parse", f"{sha}^{{tree}}").strip()
        if tree and tree not in has:
            subj = git("log", "-1", "--format=%s", sha).strip()
            todo.append((sha, tree, subj))
    return todo


def main() -> int:
    ap = argparse.ArgumentParser(description="補齊待推範圍內缺 RECORD 的 commit")
    ap.add_argument("--check", action="store_true", help="只列出，不改狀態")
    ap.add_argument("--limit", type=int, default=0, help="最多補幾顆（0=全部，最舊優先）")
    a = ap.parse_args()

    total_ahead = git("rev-list", "--count", f"{BASE_REF}..HEAD").strip() or "0"
    todo = pending_commits()
    print(f"待推範圍 {BASE_REF}..HEAD：{total_ahead} 顆｜缺有效 RECORD：{len(todo)} 顆")
    if not todo:
        print("✅ 全部 commit 都有有效 RECORD（閘門無事可擋）")
        return 0
    for sha, tree, subj in todo:
        print(f"   · {sha[:12]}  tree {tree[:12]}  {subj[:70]}")

    if a.check:
        print("\n（--check：未補紀錄、未推送）")
        return 0

    batch = todo[:a.limit] if a.limit > 0 else todo
    tag = f"backfill_{datetime.now():%Y%m%d_%H%M%S}"
    for i, (sha, _tree, _subj) in enumerate(batch, 1):
        print(f"\n[{i}/{len(batch)}] 真審查 {sha[:12]} …")
        rc = subprocess.run([sys.executable, str(BASE / "tools" / "review_commit_and_record.py"),
                             sha, f"{tag}_{i}"], cwd=str(BASE)).returncode
        if rc != 0:
            print(f"❌ {sha[:12]} 審查未通過 → 停止（fail-closed，不推送；其餘未處理）")
            return 1

    left = pending_commits()
    if left:
        print(f"\n⚠️ 仍有 {len(left)} 顆缺紀錄（--limit 或新 commit）：{', '.join(s[:12] for s, _, _ in left)}")
        return 1
    print("\n✅ 全部補齊。接著執行：python auto_push.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
