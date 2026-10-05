#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_verifier_heartbeat.py — 跑驗證器並留下「執行心跳」（P0-1）

為什麼要有這支（2026-10-05 使用者核准）
------------------------------------
`tools/verify_ficriteria.py`（留停 FI 門檻回歸保護）自 2026-10-03 起 AttributeError
全死、連續兩天沒被偵測。根因不是它自己壞，而是**全 repo 與 Hermes cron 都沒有呼叫端**
—— 沒有呼叫端就沒有心跳，「沒跑」與「跑了但失敗」在系統裡是同一個狀態（都＝什麼都沒有）。

本支是唯一責任：**把「驗證器有沒有跑、跑出什麼」變成可被稽核的事實**。
它不改驗證器的任何一條業務斷言（使用者明令：保留 49 PASS / 6 FAIL 的真實結果，
不得為了變綠而降低標準）。

輸出（`data/verifier_heartbeat.json`）
------------------------------------
  last_run_at            本次執行時間（台北 +08:00）
  last_success_at        最近一次 PASS 的時間（沒 PASS 過＝None）
  last_failure_at        最近一次 FAIL 的時間（沒 FAIL 過＝None）
  execution_status       PASS / FAIL / NOT_RUN
  consecutive_failure_count  連續 FAIL 次數（PASS 時歸零；NOT_RUN 不累加、不歸零）
  exit_code / pass_count / fail_count / duration_ms / verifier

三態語義（不得混為一談）
------------------------
  PASS    驗證器跑完且 rc=0
  FAIL    驗證器跑完但 rc≠0（業務斷言未過）
  NOT_RUN 驗證器不存在／逾時／無法執行（＝沒跑，屬「無聲失效」類）

用法
----
    python tools/run_verifier_heartbeat.py            # 跑驗證器 + 寫心跳
    python tools/run_verifier_heartbeat.py --status   # 只印現況心跳（不跑驗證器）

exit code：PASS=0；FAIL=1；NOT_RUN=2（三態不得合併）。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
VERIFIER = TOOLS / "verify_ficriteria.py"
HEARTBEAT = REPO / "data" / "verifier_heartbeat.json"
TPE = timezone(timedelta(hours=8))
TIMEOUT_S = 300

EXIT_PASS, EXIT_FAIL, EXIT_NOT_RUN = 0, 1, 2

_SUMMARY_RE = re.compile(r"==\s*結果：\s*(\d+)\s*PASS\s*/\s*(\d+)\s*FAIL\s*==")


def _now() -> datetime:
    return datetime.now(TPE)


def _read() -> dict:
    try:
        return json.loads(HEARTBEAT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(hb: dict) -> None:
    HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT.write_text(json.dumps(hb, ensure_ascii=False, indent=1), encoding="utf-8")


def status_text(hb: dict) -> str:
    st = hb.get("execution_status") or "NOT_RUN"
    c = hb.get("consecutive_failure_count") or 0
    if st == "PASS":
        return f"PASS（連續失敗 {c}）"
    if st == "FAIL":
        return (f"FAIL（{hb.get('pass_count')} PASS / {hb.get('fail_count')} FAIL；"
                f"連續失敗 {c}）")
    return "NOT_RUN（驗證器沒跑 —— 屬無聲失效，未執行驗證）"


def run_once(quiet: bool = False) -> int:
    """跑驗證器一次並寫心跳；回傳三態 exit code。"""
    prev = _read()
    prev_status = prev.get("execution_status")
    prev_streak = int(prev.get("consecutive_failure_count") or 0)
    prev_success = prev.get("last_success_at")
    prev_failure = prev.get("last_failure_at")

    now = _now()
    hb = dict(prev)
    try:
        _vrel = str(VERIFIER.relative_to(REPO)).replace("\\", "/")
    except ValueError:            # 測試沙盒：驗證器可能在 repo 之外
        _vrel = str(VERIFIER)
    hb.setdefault("verifier", _vrel)
    hb["last_run_at"] = now.isoformat()
    hb["last_success_at"] = prev_success
    hb["last_failure_at"] = prev_failure

    if not VERIFIER.exists():
        # 沒跑（不是失敗）—— 不得累加連續失敗次數、不得動 last_*_at
        hb["execution_status"] = "NOT_RUN"
        hb["exit_code"] = None
        hb["pass_count"] = None
        hb["fail_count"] = None
        hb["duration_ms"] = 0
        hb["not_run_reason"] = f"驗證器不存在：{VERIFIER}"
        _write(hb)
        if not quiet:
            print(f"❌ 驗證器心跳：NOT_RUN — 驗證器不存在（{VERIFIER}）")
        return EXIT_NOT_RUN

    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, str(VERIFIER)], cwd=str(REPO),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=TIMEOUT_S)
        out = (p.stdout or "") + ("\n" + p.stderr if (p.stderr or "").strip() else "")
        rc = p.returncode
    except subprocess.TimeoutExpired:
        hb["execution_status"] = "NOT_RUN"
        hb["exit_code"] = None
        hb["duration_ms"] = int((time.time() - t0) * 1000)
        hb["not_run_reason"] = f"逾時（>{TIMEOUT_S}s）"
        _write(hb)
        if not quiet:
            print(f"❌ 驗證器心跳：NOT_RUN — 逾時（>{TIMEOUT_S}s）")
        return EXIT_NOT_RUN
    except Exception as e:  # noqa: BLE001
        hb["execution_status"] = "NOT_RUN"
        hb["exit_code"] = None
        hb["duration_ms"] = int((time.time() - t0) * 1000)
        hb["not_run_reason"] = f"無法執行：{type(e).__name__}: {e}"
        _write(hb)
        if not quiet:
            print(f"❌ 驗證器心跳：NOT_RUN — 無法執行（{type(e).__name__}: {e}）")
        return EXIT_NOT_RUN

    hb["duration_ms"] = int((time.time() - t0) * 1000)
    hb["exit_code"] = rc
    hb.pop("not_run_reason", None)
    m = _SUMMARY_RE.search(out)
    if m:
        hb["pass_count"] = int(m.group(1))
        hb["fail_count"] = int(m.group(2))

    if rc == 0:
        hb["execution_status"] = "PASS"
        hb["consecutive_failure_count"] = 0
        hb["last_success_at"] = now.isoformat()
        if not quiet:
            print(f"✅ 驗證器心跳：PASS（{hb.get('pass_count')} PASS / {hb.get('fail_count')} FAIL）")
        _write(hb)
        return EXIT_PASS

    hb["execution_status"] = "FAIL"
    hb["consecutive_failure_count"] = (prev_streak + 1) if prev_status in ("FAIL", "NOT_RUN") else 1
    hb["last_failure_at"] = now.isoformat()
    hb["tail"] = "\n".join(out.rstrip().splitlines()[-6:])
    if not quiet:
        print(f"❌ 驗證器心跳：FAIL（{hb.get('pass_count')} PASS / {hb.get('fail_count')} FAIL；"
              f"連續失敗 {hb['consecutive_failure_count']}）")
    _write(hb)
    return EXIT_FAIL


def print_status() -> int:
    hb = _read()
    if not hb:
        print("❌ 驗證器心跳：無心跳檔（NOT_RUN）— 驗證器從未被本機制執行過")
        return EXIT_NOT_RUN
    print(f"驗證器心跳（{HEARTBEAT.name}）")
    print(f"  execution_status        : {hb.get('execution_status')}")
    print(f"  last_run_at             : {hb.get('last_run_at')}")
    print(f"  last_success_at         : {hb.get('last_success_at')}")
    print(f"  last_failure_at         : {hb.get('last_failure_at')}")
    print(f"  consecutive_failure_count: {hb.get('consecutive_failure_count')}")
    print(f"  細節                    : {status_text(hb)}")
    return {"PASS": EXIT_PASS, "FAIL": EXIT_FAIL}.get(hb.get("execution_status"), EXIT_NOT_RUN)


def main() -> int:
    ap = argparse.ArgumentParser(description="驗證器執行心跳（P0-1）")
    ap.add_argument("--status", action="store_true", help="只印現況心跳，不跑驗證器")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    return print_status() if a.status else run_once(quiet=a.quiet)


if __name__ == "__main__":
    sys.exit(main())
