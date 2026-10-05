#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_verifier_heartbeat.py — P0-1 驗收（含必要之負向測試）

驗收對象
--------
1. `tools/run_verifier_heartbeat.py`：把「驗證器有沒有跑」變成事實，三態分明。
2. `closeout_check.step_verifier_heartbeat()`：每日 checklist 讀心跳並升級。

測什麼（全部為**負向**優先）
---------------------------
  N1 心跳檔不存在            → 必須回報問題（NOT_RUN，無聲失效）
  N2 心跳逾期（>48h 未跑）    → 必須回報問題（NOT_RUN；cron 呼叫端可能沒跑）
  N3 心跳 FAIL               → 必須回報問題，且帶 PASS/FAIL 計數
  N4 心跳 PASS 且新鮮        → 必須「無」問題（否則就是無條件紅燈）
  N5 心跳檔壞掉（非 JSON）    → 必須回報問題（不得 traceback）
  N6 驗證器檔案不存在        → runner 記 NOT_RUN，且**不得**累加連續失敗次數
  N7 驗證器逾時／無法執行    → runner 記 NOT_RUN（同上，不累加）
  N8 runner 連續 FAIL       → consecutive_failure_count 逐次 +1；PASS 後歸零

邊界
----
* 只在本檔的暫存目錄與 monkeypatch 上作業；**不觸碰真實心跳檔與 dashboard 資料**。
* 跑完比對真實心跳檔位元組（sha256）＝跑前一致；不一致即 FAIL。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import closeout_check as cc            # noqa: E402
import run_verifier_heartbeat as rvh   # noqa: E402

TPE = timezone(timedelta(hours=8))
REAL_HB = REPO / "data" / "verifier_heartbeat.json"

results: list[tuple[str, bool, str]] = []


def ck(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))


def _hb(**over) -> dict:
    base = {
        "verifier": "tools/verify_ficriteria.py",
        "last_run_at": datetime.now(TPE).isoformat(),
        "last_success_at": None,
        "last_failure_at": None,
        "execution_status": "PASS",
        "consecutive_failure_count": 0,
        "exit_code": 0,
        "pass_count": 55,
        "fail_count": 0,
        "duration_ms": 200,
    }
    base.update(over)
    return base


def main() -> int:
    real_before = hashlib.sha256(REAL_HB.read_bytes()).hexdigest() if REAL_HB.exists() else None
    tmp = Path(tempfile.mkdtemp(prefix="vhb_test_"))
    sandbox_hb = tmp / "verifier_heartbeat.json"
    orig_hb_file = cc.HEARTBEAT_FILE
    orig_rvh_hb = rvh.HEARTBEAT
    orig_rvh_verifier = rvh.VERIFIER
    try:
        cc.HEARTBEAT_FILE = sandbox_hb

        # N1 檔不存在
        if sandbox_hb.exists():
            sandbox_hb.unlink()
        p = cc.step_verifier_heartbeat(quiet=True)
        ck("N1 心跳檔不存在 → 回報問題（NOT_RUN）",
           len(p) == 1 and "不存在" in p[0] and "NOT_RUN" in p[0], str(p)[:160])

        # N2 逾期未跑（狀態 PASS 但 3 天前）
        old = (datetime.now(TPE) - timedelta(days=3)).isoformat()
        sandbox_hb.write_text(json.dumps(_hb(last_run_at=old), ensure_ascii=False), encoding="utf-8")
        p = cc.step_verifier_heartbeat(quiet=True)
        ck("N2 逾期未跑（>48h）→ 回報問題（NOT_RUN）",
           len(p) == 1 and "NOT_RUN" in p[0] and "未在" in p[0], str(p)[:160])

        # N3 FAIL
        sandbox_hb.write_text(json.dumps(
            _hb(execution_status="FAIL", exit_code=1, pass_count=49, fail_count=6,
                consecutive_failure_count=2, last_failure_at=datetime.now(TPE).isoformat()),
            ensure_ascii=False), encoding="utf-8")
        p = cc.step_verifier_heartbeat(quiet=True)
        ck("N3 心跳 FAIL → 回報問題且帶計數",
           len(p) == 1 and "FAIL" in p[0] and "49" in p[0] and "6" in p[0], str(p)[:160])

        # N4 PASS 且新鮮 → 無問題
        sandbox_hb.write_text(json.dumps(_hb(), ensure_ascii=False), encoding="utf-8")
        p = cc.step_verifier_heartbeat(quiet=True)
        ck("N4 PASS 且新鮮 → 無問題", p == [], str(p)[:160])

        # N5 壞檔
        sandbox_hb.write_text("{not json", encoding="utf-8")
        p = cc.step_verifier_heartbeat(quiet=True)
        ck("N5 心跳檔壞掉 → 回報問題（不 traceback）",
           len(p) == 1 and "無法解析" in p[0], str(p)[:160])

        # N6 驗證器不存在 → NOT_RUN 且不累加連續失敗
        rvh.HEARTBEAT = tmp / "hb_runner.json"
        rvh.HEARTBEAT.write_text(json.dumps(
            _hb(execution_status="FAIL", consecutive_failure_count=4), ensure_ascii=False),
            encoding="utf-8")
        rvh.VERIFIER = tmp / "no_such_verifier.py"
        rc = rvh.run_once(quiet=True)
        hb = json.loads(rvh.HEARTBEAT.read_text(encoding="utf-8"))
        ck("N6 驗證器不存在 → NOT_RUN 且不累加連續失敗",
           rc == rvh.EXIT_NOT_RUN and hb["execution_status"] == "NOT_RUN"
           and hb["consecutive_failure_count"] == 4 and "not_run_reason" in hb,
           f"rc={rc} status={hb.get('execution_status')} streak={hb.get('consecutive_failure_count')}")

        # N7 逾時／無法執行（用一個會 sleep 的假驗證器模擬，縮短 timeout）
        fake = tmp / "slow_verifier.py"
        fake.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        rvh.VERIFIER = fake
        orig_to = rvh.TIMEOUT_S
        rvh.TIMEOUT_S = 2
        try:
            rc = rvh.run_once(quiet=True)
        finally:
            rvh.TIMEOUT_S = orig_to
        hb = json.loads(rvh.HEARTBEAT.read_text(encoding="utf-8"))
        ck("N7 驗證器逾時 → NOT_RUN（不累加）",
           rc == rvh.EXIT_NOT_RUN and hb["execution_status"] == "NOT_RUN"
           and hb["consecutive_failure_count"] == 4,
           f"rc={rc} reason={hb.get('not_run_reason')}")

        # N8 FAIL 累加 / PASS 歸零（用假驗證器控制 rc）
        # 先歸零：N6/N7 留下 NOT_RUN（語義＝不累加不歸零），須從乾淨狀態起算才可歸因。
        rvh.HEARTBEAT.write_text(json.dumps(
            _hb(execution_status="PASS", consecutive_failure_count=0), ensure_ascii=False),
            encoding="utf-8")
        for label, body, expect_streak in (("FAIL", "import sys\nsys.exit(1)\n", 1),
                                           ("FAIL", "import sys\nsys.exit(1)\n", 2),
                                           ("PASS", "print('== 結果：55 PASS / 0 FAIL ==')\n", 0)):
            fake2 = tmp / f"fake_{label}_{expect_streak}.py"
            fake2.write_text(body, encoding="utf-8")
            rvh.VERIFIER = fake2
            rvh.run_once(quiet=True)
            hb = json.loads(rvh.HEARTBEAT.read_text(encoding="utf-8"))
            ck(f"N8 {label} → streak={expect_streak}",
               hb["consecutive_failure_count"] == expect_streak
               and hb["execution_status"] == label,
               f"streak={hb['consecutive_failure_count']} status={hb['execution_status']}")

        # N9 三態 exit code 不得合併
        ck("N9 三態 exit code 互異",
           len({rvh.EXIT_PASS, rvh.EXIT_FAIL, rvh.EXIT_NOT_RUN}) == 3,
           f"{rvh.EXIT_PASS}/{rvh.EXIT_FAIL}/{rvh.EXIT_NOT_RUN}")
    finally:
        cc.HEARTBEAT_FILE = orig_hb_file
        rvh.HEARTBEAT = orig_rvh_hb
        rvh.VERIFIER = orig_rvh_verifier
        shutil.rmtree(tmp, ignore_errors=True)

    real_after = hashlib.sha256(REAL_HB.read_bytes()).hexdigest() if REAL_HB.exists() else None
    ck("真實心跳檔未被本測試動到（sha256 前後一致）", real_before == real_after,
       f"{real_before} vs {real_after}")

    npass = sum(1 for _, ok, _ in results if ok)
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if (detail and not ok) else ""))
    print(f"== 結果：{npass} PASS / {len(results) - npass} FAIL ==")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
