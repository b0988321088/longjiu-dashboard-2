#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_auto_push_baseline.py — 防再發守門（2026-11-20 INC：22:00 晚報自鎖 rc=3）

背景：
    產線若「先自己 git commit、再呼叫 auto_push.py」，必須傳 --baseline <commit 前 HEAD>。
    漏傳時 auto_push 會把呼叫端自己剛產生的 commit 誤判為「陌生的未審查 commit」→ rc=3 拒絕推送，
    留下毒藥 commit，連帶讓下一個 job（22:15 nightly）以「佇列在本輪前已有 1 顆 commit」fail-closed。
    2026-11-20 實例：evening_sync.py（538aaad0 卡住 22:00/22:15 兩支 cron）、pre-run.sh（同型）。

判定規則（靜態，不看執行期）：
    ① 找出所有「呼叫 auto_push.py」的檔案（呼叫行含 auto_push.py，且該行像指令：python/[ / runner(/subprocess）
    ② 若該檔同時有「自行 commit」（git commit 或 ["git","commit"]）→ 必須在檔案內出現 --baseline，否則 FAIL
    ③ 若呼叫行自帶 --commit（由 auto_push 代為 commit）→ 豁免（此時不需要 baseline）
    ④ 豁免路徑：.archive/、.git/、tests/fixtures、本檔

用法：
    python tools/check_auto_push_baseline.py          # 有 FAIL → exit 1
    python tools/check_auto_push_baseline.py -v       # 印每個呼叫點判定
"""
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
EXTS = {".py", ".sh", ".bat", ".ps1", ".cmd"}
SKIP_DIRS = {".git", ".archive", "node_modules", "__pycache__", "tests", "quarantine"}
SELF = Path(__file__).resolve()

_CALL = re.compile(r"auto_push\.py")
_GIT_COMMIT = re.compile(r"git['\"]?\s*,\s*['\"]commit['\"]|git commit\b")


def iter_files():
    for p in BASE.rglob("*"):
        if p.suffix.lower() not in EXTS or not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.resolve() == SELF:
            continue
        yield p


def main() -> int:
    verbose = "-v" in sys.argv
    fails, oks, exempt = [], [], []

    for p in iter_files():
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        rel = p.relative_to(BASE).as_posix()
        # 呼叫區塊＝含 auto_push.py 的行 ±2 行（參數常跨行）；必須帶 --script 才算真呼叫
        real = []
        for i, ln in enumerate(lines):
            if not _CALL.search(ln) or ln.lstrip().startswith("#"):
                continue
            win = " ".join(lines[max(0, i - 1): i + 3])
            if "--script" not in win:
                continue
            real.append(win.strip())
        if not real:
            continue

        if any("--commit" in w for w in real):
            oks.append((rel, "auto_push 代 commit（--commit）→ 不需 baseline"))
            continue

        if not _GIT_COMMIT.search(text):
            oks.append((rel, "未自行 commit → 不需 baseline"))
            continue

        if "--baseline" in text:
            oks.append((rel, "自行 commit 且有 --baseline"))
        else:
            fails.append((rel, "自行 commit 但呼叫 auto_push 未傳 --baseline"))
            if verbose:
                for ln in real:
                    print(f"    {rel}: {ln.strip()[:110]}")

    print("=== auto_push --baseline 守門 ===")
    print(f"掃描檔案：{len(list(iter_files()))}｜通過 {len(oks)}｜FAIL {len(fails)}")
    if verbose:
        for rel, why in oks:
            print(f"  ✅ {rel}｜{why}")
    if fails:
        print("⛔ FAIL：以下檔案先 commit 再呼叫 auto_push，卻沒傳 --baseline（會 rc=3 自鎖）：")
        for rel, why in fails:
            print(f"  ❌ {rel}｜{why}")
        print("修法：commit 前取 HEAD，呼叫時加 --baseline <sha>（參考 evening_sync.py `_publish`）")
        return 1
    print("✅ PASS：所有先 commit 的呼叫端都有 --baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
