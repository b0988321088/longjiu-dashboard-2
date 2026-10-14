#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⑨ Pages 部署稽核（closeout_check.step_pages_deploy）單元測試。

涵蓋 4 個狀態 + 1 個真實整合：
  A 成功          → 無問題
  B 失敗／逾時     → ❌ 問題（指名 run id 與結論）
  C 進行中／剛推送 → 無問題（⏳，不得誤報）
  D 查不到 API     → 無問題（⚠️ 未驗證，不得偽裝通過、不得誤報失敗）
  E 真實整合       → 直接讀 GitHub 公開 API 對當前部署來源 sha 給出結論

用法：python tools/test_pages_deploy_check.py（不需 token）
"""
from __future__ import annotations

import io
import contextlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import closeout_check as cc  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}{('｜' + extra) if extra else ''}")
    else:
        FAIL += 1
        print(f"  ❌ {name}{('｜' + extra) if extra else ''}")


def run_with(runs, sha: str) -> tuple[list, str]:
    orig_runs, orig_sha = cc._pages_runs, cc._git
    cc._pages_runs = lambda slug, timeout=15: runs
    cc._git = lambda *a: (sha if a[:2] == ("rev-parse", cc.DEPLOY_REF) else orig_sha(*a))
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            probs = cc.step_pages_deploy(False)
    finally:
        cc._pages_runs, cc._git = orig_runs, orig_sha
    return probs, buf.getvalue()


def mk(status: str, conclusion, sha: str, name: str = cc.PAGES_WORKFLOW, rid: int = 1) -> dict:
    return {"id": rid, "name": name, "status": status, "conclusion": conclusion,
            "head_sha": sha, "html_url": f"https://github.com/o/r/actions/runs/{rid}"}


SHA = "a" * 40


def main() -> int:
    print("⑨ Pages 部署稽核 — 單元測試")
    # A 成功
    probs, out = run_with([mk("completed", "success", SHA)], SHA)
    check("A 部署成功 → 無問題", probs == [], f"probs={probs}")
    check("A 成功訊息含 ✅ 與 run 資訊", "✅" in out and SHA[:8] in out)

    # B 失敗／逾時
    for concl in ("failure", "timed_out", "startup_failure"):
        probs, out = run_with([mk("completed", concl, SHA, rid=42)], SHA)
        check(f"B {concl} → ❌ 指名問題",
              len(probs) == 1 and "Pages 部署失敗" in probs[0] and "#42" in probs[0], str(probs)[:120])

    # C 進行中／剛推送（不得誤報）
    probs, out = run_with([mk("in_progress", None, SHA)], SHA)
    check("C 進行中 → 無問題（⏳）", probs == [] and "⏳" in out, str(probs)[:120])
    probs, out = run_with([mk("queued", None, SHA)], SHA)
    check("C 佇列中 → 無問題（⏳）", probs == [] and "⏳" in out)

    # D 查不到 API
    probs, out = run_with(None, SHA)
    check("D API 查不到 → 無問題（⚠️ 未驗證）", probs == [] and "⚠️" in out, str(probs)[:120])

    # C2 剛 push 尚無 run（寬限期內）→ 非問題；超過寬限 → 問題
    import datetime as dt
    recent = dt.datetime.now(dt.timezone.utc).isoformat()
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=5)).isoformat()
    orig_git, orig_runs2 = cc._git, cc._pages_runs
    for label, ts, expect_problem in (("剛推送 5 分", recent, False), ("推送 5 小時仍無 run", old, True)):
        def fake_git(*a, _ts=ts, _orig=orig_git):
            if a[:2] == ("rev-parse", cc.DEPLOY_REF):
                return SHA                      # 部署來源 sha（真實形狀）
            if a[:2] == ("show", "-s"):
                return _ts                      # commit 時間（本測試要控制的自變數）
            return _orig(*a)
        cc._pages_runs = lambda slug, timeout=15: []
        cc._git = fake_git
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                probs = cc.step_pages_deploy(False)
        finally:
            cc._git = orig_git
        check(f"C2 {label} → {'❌ 問題' if expect_problem else '無問題'}"
              f"（{'未觸發' if expect_problem else '寬限內'}）",
              (len(probs) == 1 and "未觸發" in probs[0]) if expect_problem else probs == [],
              str(probs)[:120])

    # E 真實整合（公開 API）
    cc._pages_runs = orig_runs2
    ubuf = io.StringIO()
    with contextlib.redirect_stdout(ubuf):
        _ = cc.step_pages_deploy(False)
    real = ubuf.getvalue().strip()
    check("E 真實整合：有結論（不拋錯）", real.startswith("⑨ Pages 部署："), real[:160])

    print(f"\n結果：{PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
