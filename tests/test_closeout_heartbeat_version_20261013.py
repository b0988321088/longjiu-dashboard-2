#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_closeout_heartbeat_version_20261013.py

TD-20261013-07（使用者 2026-10-13 裁決）項一／項二的行為驗收：
  ①收工檢查 ⑧ 必須比對「心跳指紋 vs 當前真值／驗證器版本」，不一致即不回 PASS（不得沿用舊 PASS）。
  ②收工檢查輸出必須能區分「排程程序執行成功（cron wrapper，rc 恆 0）」與「驗證器通過」。

全部在暫存目錄操作，**不得**動到真實 data/verifier_heartbeat.json（逐位元比對）。
"""
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
HB_REAL = BASE / "data" / "verifier_heartbeat.json"


def _load_closeout():
    spec = importlib.util.spec_from_file_location("closeout_check_t", BASE / "closeout_check.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["closeout_check_t"] = m
    spec.loader.exec_module(m)
    return m


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "<absent>"


def main() -> int:
    passed = failed = 0
    tmp = Path(tempfile.mkdtemp(prefix="closeout_hbver_"))
    hb_sha_before = _sha(HB_REAL)
    cc = _load_closeout()

    snap = tmp / "snapshot.json"
    verifier = tmp / "verify_ficriteria.py"
    hb = tmp / "verifier_heartbeat.json"
    snap.write_text('{"t":1}', encoding="utf-8")
    verifier.write_text("# v1\n", encoding="utf-8")

    cc.SNAPSHOT_FILE, cc.VERIFIER_FILE, cc.HEARTBEAT_FILE = snap, verifier, hb

    def write_hb(**over):
        import datetime as dt
        tpe = dt.timezone(dt.timedelta(hours=8))
        d = {
            "execution_status": "PASS", "exit_code": 0, "pass_count": 57, "fail_count": 0,
            "consecutive_failure_count": 0,
            "last_run_at": dt.datetime.now(tpe).isoformat(),
            "snapshot_mtime": cc._file_mtime_iso(snap),
            "verifier_mtime": cc._file_mtime_iso(verifier),
            "summary_found": True,
        }
        d.update(over)
        hb.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def check(name, cond, detail=""):
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
        print(f"        {detail}" if not cond else "", end="" if not cond else "\n")

    # T1 指紋一致 → PASS（無問題）
    write_hb()
    r1 = cc.step_verifier_heartbeat(quiet=True)
    check("T1 指紋一致 → 回 PASS（無問題）", r1 == [], f"got={r1}")

    # T2 真值在心跳之後被改寫 → 必須回報「版本落後」，不得沿用舊 PASS
    os.utime(snap, (0, snap.stat().st_mtime + 120))
    r2 = cc.step_verifier_heartbeat(quiet=True)
    check("T2 真值改寫後 → 不回 PASS 且點名版本落後",
          bool(r2) and any("心跳版本落後" in p and "snapshot.json" in p for p in r2), f"got={r2}")
    check("T2b 訊息明確要求重跑心跳",
          bool(r2) and any("run_verifier_heartbeat" in p for p in r2), f"got={r2}")

    # T3 驗證器版本改寫 → 同樣不得沿用
    write_hb()
    os.utime(verifier, (0, verifier.stat().st_mtime + 120))
    r3 = cc.step_verifier_heartbeat(quiet=True)
    check("T3 驗證器改寫後 → 點名 verifier 版本落後",
          bool(r3) and any("心跳版本落後" in p and "verify_ficriteria" in p for p in r3), f"got={r3}")

    # T4 缺指紋（舊版心跳檔）→ 無法證明 → 回報（fail-closed，不得假綠）
    write_hb(snapshot_mtime=None, verifier_mtime=None)
    r4 = cc.step_verifier_heartbeat(quiet=True)
    check("T4 缺指紋 → 回報無法證明（不得假綠）",
          bool(r4) and any("缺 snapshot_mtime 指紋" in p for p in r4), f"got={r4}")

    # T5 心跳 FAIL → 既有 FAIL 語意不回歸（且含 rc）
    write_hb(execution_status="FAIL", exit_code=1, pass_count=55, fail_count=2,
             consecutive_failure_count=5)
    r5 = cc.step_verifier_heartbeat(quiet=True)
    check("T5 心跳 FAIL → 回 FAIL 且帶 rc",
          bool(r5) and any("驗證器 FAIL" in p and "rc=1" in p for p in r5), f"got={r5}")

    # T6 逾期未跑 → NOT_RUN，且註明 cron rc 不具驗證語意
    write_hb(last_run_at="2026-10-01T22:35:00+08:00")
    r6 = cc.step_verifier_heartbeat(quiet=True)
    check("T6 逾期 → NOT_RUN 並區分 cron 與驗證器",
          bool(r6) and any("NOT_RUN" in p and "不代表驗證器通過" in p for p in r6), f"got={r6}")

    # T7 真實心跳檔未被本測試動到
    check("T7 真實心跳檔逐位元未變", _sha(HB_REAL) == hb_sha_before)

    print(f"\n== 結果：{passed} PASS / {failed} FAIL ==")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
