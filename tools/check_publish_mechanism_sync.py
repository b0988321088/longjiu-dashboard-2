#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""發布機制檔同步檢查（TD-20261031-01 防再發）。

## 為什麼要有這支

2026-10-31 INC-236 事故隔離期間，一次性發布授權機制（release_auth.py、
.githooks/pre-push、auto_push.py 的整合）只改在**工作區**；當時 PUSH_HOLD
禁止 commit，所以機制「能用」但 HEAD 沒有。事後補入庫才補回（819ddcae）。

若再發生一次：clone 或 checkout 後機制就消失 → fail-closed 不會誤發布，
但會變成「明明授權了卻推不出去」而且沒人知道為什麼。

## 判準

發布機制檔必須同時滿足：
1. 已被 git 追蹤（否則只在這一台機器生效）
2. 工作區內容 == HEAD（否則 git 用工作區版本、其他 clone 用 HEAD 版本 → 行為分裂）

## 用法

  python tools/check_publish_mechanism_sync.py        # rc=0 一致 / 1 有問題
  python tools/check_publish_mechanism_sync.py -v     # 逐檔列出狀態

由 closeout_check.py 的 step_publish_mechanism() 呼叫（22:40 收工檢查）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# 這些檔案一旦「工作區 ≠ HEAD」，就代表發布防線有兩份版本在跑。
MECH_FILES = (
    "release_auth.py",
    "auto_push.py",
    ".githooks/pre-push",
    ".githooks/pre-commit",
)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def check(root: Path | str | None = None) -> list[str]:
    """回傳問題清單（空 = 全部一致）。純讀，不寫任何檔案。"""
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    problems: list[str] = []
    for rel in MECH_FILES:
        p = root / rel
        if not p.exists():
            problems.append(f"{rel}：檔案不存在（機制缺口）")
            continue
        tracked = _git(root, "ls-files", "--error-unmatch", rel)
        if tracked.returncode != 0:
            problems.append(f"{rel}：未追蹤 → 只在工作區生效，clone／checkout 後消失")
            continue
        diff = _git(root, "diff", "--numstat", "HEAD", "--", rel)
        if diff.returncode != 0:
            problems.append(f"{rel}：git diff 失敗（{diff.stderr.strip()[:80]}）")
            continue
        if diff.stdout.strip():
            parts = diff.stdout.split()
            problems.append(
                f"{rel}：工作區與 HEAD 不一致（+{parts[0]}/-{parts[1]} 行）"
                f"→ 兩份機制版本並存，先 commit 或還原")
    return problems


def main(argv: list[str]) -> int:
    problems = check()
    if "-v" in argv or "--verbose" in argv:
        for rel in MECH_FILES:
            print(f"  · {rel}")
    if problems:
        print("❌ 發布機制檔未同步：")
        for x in problems:
            print(f"  - {x}")
        return 1
    print(f"✅ 發布機制檔與 HEAD 一致（{len(MECH_FILES)} 檔）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
