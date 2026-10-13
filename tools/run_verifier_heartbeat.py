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
  summary_found          本次輸出是否找得到 `== 結果：N PASS / M FAIL ==`（False 時計數一律 None）
  rc_summary_mismatch    驗證器 FAIL 卻回 rc=0 的自我矛盾旗標（True 時以摘要為準＝FAIL）
  snapshot_mtime / verifier_mtime        本次是拿哪一版真值／哪一版驗證器跑的
  inputs_changed_since_prev_run          真值在「上一個心跳」之後又動過（上一次 PASS 已非當期）

三態語義（不得混為一談）
------------------------
  PASS    驗證器跑完、rc=0、且**摘要列 fail_count=0**（三者缺一不可）
  FAIL    驗證器跑完但 rc≠0（業務斷言未過）；或 rc=0 與摘要計數矛盾（fail_count>0）
  NOT_RUN 驗證器不存在／逾時／無法執行／rc=0 但無摘要列（＝無法確認跑完，屬「無聲失效」類）

反「驗證器說謊」契約（2026-10-13 補）
------------------------------------
  1. 狀態**不得只由 rc 決定**：rc=0 但摘要說有 FAIL → 記 FAIL（rc_summary_mismatch）。
     （舊版只要 rc=0 就寫 PASS → 把驗證器自己的謊原封不動轉錄成心跳）
  2. 摘要找不到時，pass_count/fail_count 一律寫 None，**不得沿用上一輪舊值**
     （沿用＝舊數字被讀成「本次結果」，與實跑矛盾）。
  3. PASS 分支必須清掉 `tail`（上一輪 FAIL 的尾巴不得殘留在 PASS 心跳裡）。
  4. 記下本次的 snapshot／驗證器 mtime：心跳才回答得出「這個 PASS 是跑在哪一版真值上」。
     舊痛點：last_run 停在昨天、而 snapshot 今天更新過 → 心跳仍是 PASS 且 48h 內，
     收工檢查讀檔即判綠（＝憑舊結果收工）。

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

SNAP = REPO / "snapshot.json"


def _now() -> datetime:
    return datetime.now(TPE)


def _mtime_iso(p: Path):
    """檔案 mtime → 台北時區 ISO 字串；檔不存在或讀不到回 None（不得 raise）。"""
    try:
        return datetime.fromtimestamp(p.stat().st_mtime, TPE).isoformat()
    except Exception:  # noqa: BLE001
        return None


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

    # 輸入指紋：記下本次是拿哪一版真值／哪一版驗證器跑的。
    # 沒有這個，心跳只能回答「跑過了」，回答不出「跑的是當期真值嗎」——2026-10-13 的
    # 實際事故正是這樣：last_run 停在 10/12 22:35（PASS），snapshot.json 於 10/13
    # 16:29／16:41 連兩次更新（台電薪資、六批資料同步），心跳卻仍在 48h 內＝新鮮，
    # 22:40 closeout 讀檔就會憑前一版真值的結果判綠。
    hb["snapshot_mtime"] = _mtime_iso(SNAP)
    hb["verifier_mtime"] = _mtime_iso(VERIFIER)
    _prev_snap_mtime = prev.get("snapshot_mtime")
    # None＝上一個心跳沒有指紋（無法比較）→ 寫 None，**不得**寫 False 假裝「沒變過」
    hb["inputs_changed_since_prev_run"] = (
        None if not _prev_snap_mtime
        else bool(hb["snapshot_mtime"] and _prev_snap_mtime != hb["snapshot_mtime"]))

    if not VERIFIER.exists():
        # 沒跑（不是失敗）—— 不得累加連續失敗次數、不得動 last_*_at
        hb["execution_status"] = "NOT_RUN"
        hb["exit_code"] = None
        hb["pass_count"] = None
        hb["fail_count"] = None
        hb["summary_found"] = False
        hb["duration_ms"] = 0
        hb["not_run_reason"] = f"驗證器不存在：{VERIFIER}"
        hb.pop("tail", None)                 # 上一輪 FAIL 的尾巴不得留在 NOT_RUN 心跳裡
        hb.pop("rc_summary_mismatch", None)
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
        # 逾時＝沒跑完：上一輪的計數與 FAIL 尾巴一律清掉，不得被讀成本次結果
        hb["pass_count"] = None
        hb["fail_count"] = None
        hb["summary_found"] = False
        hb.pop("tail", None)
        hb.pop("rc_summary_mismatch", None)
        hb["duration_ms"] = int((time.time() - t0) * 1000)
        hb["not_run_reason"] = f"逾時（>{TIMEOUT_S}s）"
        _write(hb)
        if not quiet:
            print(f"❌ 驗證器心跳：NOT_RUN — 逾時（>{TIMEOUT_S}s）")
        return EXIT_NOT_RUN
    except Exception as e:  # noqa: BLE001
        hb["execution_status"] = "NOT_RUN"
        hb["exit_code"] = None
        hb["pass_count"] = None
        hb["fail_count"] = None
        hb["summary_found"] = False
        hb.pop("tail", None)
        hb.pop("rc_summary_mismatch", None)
        hb["duration_ms"] = int((time.time() - t0) * 1000)
        hb["not_run_reason"] = f"無法執行：{type(e).__name__}: {e}"
        _write(hb)
        if not quiet:
            print(f"❌ 驗證器心跳：NOT_RUN — 無法執行（{type(e).__name__}: {e}）")
        return EXIT_NOT_RUN

    hb["duration_ms"] = int((time.time() - t0) * 1000)
    hb["exit_code"] = rc
    hb.pop("not_run_reason", None)

    # ── 真實性關卡（2026-10-13）：狀態不得只由 rc 決定 ──────────────────────
    # 業務斷言的真相在摘要列（N PASS / M FAIL），rc 只是驗證器「自稱」的結果。
    # 兩者矛盾時（FAIL 卻回 0）＝驗證器說謊：必須以摘要為準記 FAIL 並留旗標；
    # 只信 rc 會把謊言原封不動轉錄成心跳，只信摘要則會漏掉「跑完但 rc≠0」的失敗。
    m = _SUMMARY_RE.search(out)
    if m:
        hb["pass_count"] = int(m.group(1))
        hb["fail_count"] = int(m.group(2))
    else:
        hb["pass_count"] = None      # 沒有本次計數就寫 None：沿用舊值＝與實跑矛盾
        hb["fail_count"] = None
    hb["summary_found"] = bool(m)
    _n_fail = int(hb["fail_count"] or 0)

    if rc == 0 and m and _n_fail > 0:
        hb["rc_summary_mismatch"] = True
    else:
        hb.pop("rc_summary_mismatch", None)

    if rc == 0 and not m:
        # 回 0 卻沒有結果列：驗證器可能早退／輸出被截 → 無法確認跑完，不得宣告 PASS
        hb["execution_status"] = "NOT_RUN"
        hb["not_run_reason"] = ("驗證器回 rc=0 但輸出無「== 結果：N PASS / M FAIL ==」摘要列 "
                                "→ 無法確認跑完（無聲失效）")
        hb.pop("tail", None)
        _write(hb)
        if not quiet:
            print("❌ 驗證器心跳：NOT_RUN — rc=0 但無結果摘要列（無法確認驗證器跑完）")
        return EXIT_NOT_RUN

    if rc == 0 and _n_fail == 0:
        hb["execution_status"] = "PASS"
        hb["consecutive_failure_count"] = 0
        hb["last_success_at"] = now.isoformat()
        hb.pop("tail", None)         # 上一輪 FAIL 的尾巴不得留在 PASS 心跳裡
        if not quiet:
            print(f"✅ 驗證器心跳：PASS（{hb.get('pass_count')} PASS / {hb.get('fail_count')} FAIL）")
        _write(hb)
        return EXIT_PASS

    hb["execution_status"] = "FAIL"
    hb["consecutive_failure_count"] = (prev_streak + 1) if prev_status in ("FAIL", "NOT_RUN") else 1
    hb["last_failure_at"] = now.isoformat()
    hb["tail"] = "\n".join(out.rstrip().splitlines()[-6:])
    if not quiet:
        _mismatch = ("｜⚠️ rc=0 與摘要矛盾（驗證器回傳碼不可信）"
                     if hb.get("rc_summary_mismatch") else "")
        print(f"❌ 驗證器心跳：FAIL（{hb.get('pass_count')} PASS / {hb.get('fail_count')} FAIL；"
              f"連續失敗 {hb['consecutive_failure_count']}）{_mismatch}")
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
