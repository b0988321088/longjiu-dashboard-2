#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""唯讀沙箱自測：決策入庫對帳「收據制時間邊界」（2026-10-02 INC-280）。

修的是 reconcile_decision_intake.py：收據制（單一入庫入口 append_dashboard_decisions.py）
2026-10-02 20:53 才上線，比它更早進檔的決策結構上不可能有收據 → 舊版每跑一次就警示一次
（實例 mem-20261002195408-1056 假缺口）。新版以「收據檔最早一筆 ts」為制度起算點，
早於起算點者列 ℹ️ legacy（不警示），起算點之後仍一律 ⚠️（不放寬）；收據檔無有效時戳時 fail-closed。

做法：把 repo 真身 import 進來，**只改模組常數指向 %TEMP% 夾具**（不碰真 repo、不連網、不寫 repo）。
用法：python tools/verify_decision_intake_epoch.py   （exit 0 = ALL PASS）
"""
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import sys

REPO = pathlib.Path(r"C:/Users/bot/Desktop/longjiu_system")
ROOT = pathlib.Path(os.environ["LOCALAPPDATA"]) / "Temp" / "verify_intake_epoch"
T0 = "2026-10-02T20:53:06.428183+08:00"          # 收據制起算（第一筆收據）
BEFORE = "2026-10-02T19:54:08.000000+08:00"      # 上線前
AFTER = "2026-10-02T21:05:00.000000+08:00"       # 上線後
DAY = "2026-10-02"
FAILS = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("  | " + str(detail)) if detail else ""))
    if not cond:
        FAILS.append(name)


def load_mod():
    spec = importlib.util.spec_from_file_location("rec_mod", str(REPO / "reconcile_decision_intake.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def dec(ids_ts):
    return {"decisions": [{"id": i, "timestamp": t, "source": "user", "task": f"task-{i}"} for i, t in ids_ts],
            "meta": {}}


def rec(ids_ts, ok=True):
    return "".join(json.dumps({"ts": t, "id": i, "task": f"task-{i}", "source": "user", "ok": ok},
                              ensure_ascii=False) + "\r\n" for i, t in ids_ts)


def run(m, case, dec_obj, rec_text=None, rec_missing=False):
    d = ROOT / case
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    dp = d / "dashboard_decisions.json"
    dp.write_text(json.dumps(dec_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    rp = d / "receipts.jsonl"
    if not rec_missing:
        rp.write_text(rec_text or "", encoding="utf-8", newline="")
    m.DEC_FILE = dp
    m.RECEIPT_FILE = rp
    buf = io.StringIO()
    old = sys.argv
    sys.argv = ["reconcile_decision_intake.py", "--date", DAY]
    try:
        with contextlib.redirect_stdout(buf):
            rc = m.main()
    finally:
        sys.argv = old
    return rc, buf.getvalue()


def main():
    if ROOT.exists():
        shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True, exist_ok=True)
    m = load_mod()

    # E1 上線前的歷史入庫 → ℹ️ legacy，不警示、不影響 rc
    rc, out = run(m, "E1", dec([("d0", BEFORE), ("r1", T0)]), rec([("r1", T0)]))
    check("E1 rc=0", rc == 0, rc)
    check("E1 歷史條目列 ℹ️（1 筆）", "ℹ️" in out and "歷史入庫 1 筆" in out, out.strip().splitlines()[-2:])
    check("E1 不再出現 ⚠️", "⚠️" not in out)
    check("E1 仍印 ✅ 一致", "✅ 一致" in out)

    # E2 上線後進檔卻沒收據 → 仍 ⚠️（守門沒被放寬）
    rc, out = run(m, "E2", dec([("r1", T0), ("d9", AFTER)]), rec([("r1", T0)]))
    check("E2 rc=0", rc == 0, rc)
    check("E2 上線後缺收據仍 ⚠️ 且點名 d9", "⚠️" in out and "d9" in out, out.strip().splitlines()[-3:])
    check("E2 無 ℹ️ legacy 行", "ℹ️" not in out)

    # E3 有收據沒進檔 → 真缺口 rc=1（原有行為不變）
    rc, out = run(m, "E3", dec([("r1", T0)]), rec([("r1", T0), ("r2", AFTER)]))
    check("E3 rc=1", rc == 1, rc)
    check("E3 印 ❌ 缺口 1 筆", "❌ 缺口 1 筆" in out, out.strip().splitlines()[-2:])

    # E4 收據檔空 → 無法判定起點 → fail-closed 全列 ⚠️
    rc, out = run(m, "E4", dec([("d1", AFTER), ("d2", BEFORE)]), rec([]))
    check("E4 rc=0", rc == 0, rc)
    check("E4 兩筆都列 ⚠️（不放行）", "⚠️ 2 筆" in out, out.strip().splitlines()[-3:])
    check("E4 明示無法判定起點", "無法判定收據制起點" in out)

    # E5 收據檔不存在 → 同上 fail-closed
    rc, out = run(m, "E5", dec([("d1", AFTER)]), rec_missing=True)
    check("E5 檔案不存在仍列 ⚠️", "⚠️ 1 筆" in out and "無法判定收據制起點" in out, out.strip().splitlines()[-3:])

    # E6 邊界：時戳恰等於起算點 → 不算 legacy（必須帶收據）
    rc, out = run(m, "E6", dec([("r1", T0), ("d3", T0)]), rec([("r1", T0)]))
    check("E6 邊界等於起算點 → ⚠️ 非 legacy", "⚠️" in out and "d3" in out and "ℹ️" not in out, out.strip().splitlines()[-3:])

    # E7 時戳壞字串（仍屬當日字首、但無法解析）→ fail-closed 列 ⚠️
    rc, out = run(m, "E7", dec([("r1", T0), ("d4", "2026-10-02T99:99:99")]), rec([("r1", T0)]))
    check("E7 時戳無法解析 → ⚠️", "⚠️" in out and "d4" in out, out.strip().splitlines()[-3:])

    # E8 起算點由資料現算（不寫死）：更早的收據出現時，legacy 邊界跟著往前
    earlier = "2026-10-02T18:00:00.000000+08:00"
    rc, out = run(m, "E8", dec([("d5", "2026-10-02T18:30:00.000000+08:00")]), rec([("r0", earlier)]))
    check("E8 起算點現算（18:30 > 18:00 → ⚠️）", "⚠️" in out and "d5" in out, out.strip().splitlines()[-3:])
    rc, out = run(m, "E8b", dec([("d6", "2026-10-02T17:30:00.000000+08:00")]), rec([("r0", earlier)]))
    check("E8b 17:30 < 18:00 → ℹ️ legacy", "ℹ️" in out and "d6" in out and "⚠️" not in out, out.strip().splitlines()[-3:])

    print()
    print("結果：" + ("ALL PASS" if not FAILS else f"FAIL {FAILS}"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
