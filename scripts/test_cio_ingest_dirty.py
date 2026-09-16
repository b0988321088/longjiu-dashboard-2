#!/usr/bin/env python3
"""test_cio_ingest_dirty.py — _needs_commit 四態沙盒驗測（INC-206）

背景：cio_review_ingest.py 舊版用 `git diff --quiet`（只看**未暫存**變更）判斷是否要
commit+push cio_review.json。若檔案已被 `git add` 但未 commit，舊判斷回「乾淨」→ 靜默不推
→ 線上儀表板停在舊審查。本測驗同時證明「舊邏輯會漏、新邏輯不漏」。
"""
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cio_review_ingest as ing  # noqa: E402

results = []


def _run(cmd, cwd):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True)


def _old_logic(d):
    """舊邏輯：git diff --quiet → rc!=0 才算有變更。回傳 True=舊邏輯會推。"""
    r = _run(["git", "diff", "--quiet", "--", "cio_review.json"], d)
    return r.returncode != 0


def case(name, setup, expect_new, expect_old=None):
    d = Path(tempfile.mkdtemp())
    try:
        _run(["git", "init", "-q"], d)
        _run(["git", "config", "user.email", "t@t.t"], d)
        _run(["git", "config", "user.name", "t"], d)
        f = d / "cio_review.json"
        f.write_text('{"a": 1}', encoding="utf-8")
        _run(["git", "add", "cio_review.json"], d)
        _run(["git", "commit", "-q", "-m", "init"], d)
        setup(d, f)
        got_new = ing._needs_commit(f, d)
        got_old = _old_logic(d)
        ok = (got_new == expect_new) and (expect_old is None or got_old == expect_old)
        results.append(ok)
        tag = "PASS" if ok else "FAIL"
        print(f"  {name}")
        print(f"    新邏輯={got_new}（期望 {expect_new}）｜舊邏輯={got_old}"
              + (f"（期望 {expect_old}）" if expect_old is not None else "")
              + f"  {tag}")
        return ok
    finally:
        shutil.rmtree(d, ignore_errors=True)


print("=== _needs_commit 四態驗測（新 vs 舊） ===")
case("A 剛 commit、乾淨            → 不該推", lambda d, f: None, False, False)
case("B 未暫存修改                → 該推", lambda d, f: f.write_text('{"a": 2}', encoding="utf-8"), True, True)


def _staged(d, f):
    f.write_text('{"a": 3}', encoding="utf-8")
    _run(["git", "add", "cio_review.json"], d)


def _untracked(d, f):
    _run(["git", "rm", "--cached", "-q", "cio_review.json"], d)


def _deleted(d, f):
    f.unlink()


case("C 已暫存未 commit（本次修的洞） → 該推", _staged, True, False)
case("D 未追蹤（同一個洞的第二形態）    → 該推", _untracked, True, False)
case("E 檔案被刪除                 → 該推", _deleted, True, True)

p = sum(results)
print(f"\nPASS={p}  FAIL={len(results) - p}")
print("SANDBOX ALL PASS" if p == len(results) else "SANDBOX FAILED")
sys.exit(0 if p == len(results) else 1)
