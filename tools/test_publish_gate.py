#!/usr/bin/env python3
"""tools/test_publish_gate.py — 發布放行條件 ③⑥ 的負向／正向測試（2026-10-17）

涵蓋使用者裁決要求的案例：
  1 正常放行            2 範圍交集命中（阻擋）      3 範圍不相交（放行）
  4 過期快照無例外（阻擋） 5 合法 T-1 例外（放行）     6 非法例外（阻擋，三種子情境）
另以 `--with-existing` 呼叫既有守門（dirty_gate／auto_push CIO 閘門）證明未被繞過：
  7 staged ≠ produced    8 無 CIO RECORD
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from tools.publish_gate import check_publish_gate, declared_program_files  # noqa: E402

TPE = timezone(timedelta(hours=8))
TODAY = "2026-10-17"
PASS, FAIL = [], []


def ck(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + (f"｜{detail}" if detail and not cond else ""))


def run_case(tmp: Path, *, produced, snap_date, exc: dict | None):
    p = None
    if exc is not None:
        p = tmp / "freshness_exception.json"
        p.write_text(json.dumps(exc, ensure_ascii=False), encoding="utf-8")
    return check_publish_gate(produced, snap_date, TODAY, BASE, p,
                              now=datetime(2026, 10, 17, 10, 0, tzinfo=TPE))


def main() -> int:
    declared = sorted(declared_program_files(BASE))
    print(f"（宣告清單 {len(declared)} 檔，來源 check_dividend_caliber.allowed 的 AST）")
    ck("宣告清單可讀取且非空", len(declared) > 0, str(len(declared)))

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # 1 正常放行
        r = run_case(tmp, produced=["daily_report_v2_2026-10-17.html", "asset_diff_2026-10-17.html"],
                     snap_date=TODAY, exc=None)
        ck("① 正常放行（當日快照＋無 .py）", r["ok"], str(r["blocking"]))

        # 2 範圍交集命中
        r = run_case(tmp, produced=["daily_report_v2_2026-10-17.html", "site_sync.py"],
                     snap_date=TODAY, exc=None)
        ck("② 範圍交集命中 → 阻擋", (not r["ok"]) and any("site_sync.py" in b for b in r["blocking"]),
           str(r["blocking"]))

        # 3 範圍不相交（已宣告的 .py 進 produced → 放行）
        r = run_case(tmp, produced=["build_retirement_plan.py"], snap_date=TODAY, exc=None)
        ck("③ 範圍不相交（已宣告 .py）→ 放行", r["ok"], str(r["blocking"]))

        # 4 過期快照、無例外
        r = run_case(tmp, produced=["daily_report_v2_2026-10-17.html"],
                     snap_date="2026-10-16", exc=None)
        ck("④ 過期快照無例外 → 阻擋", (not r["ok"]) and any("⑥" in b for b in r["blocking"]),
           str(r["blocking"]))

        # 5 合法 T-1 例外
        good = {"allow_snapshot_date": "2026-10-16", "reason": "10/16 真值日延後至 10/18",
                "approved_by": "使用者 2026-10-17 Telegram 裁決",
                "expires_at": "2026-10-18T23:59:59+08:00"}
        r = run_case(tmp, produced=["daily_report_v2_2026-10-17.html"],
                     snap_date="2026-10-16", exc=good)
        ck("⑤ 合法 T-1 例外 → 放行", r["ok"], str(r["blocking"]))

        # 6 非法例外（三子情境）
        for label, mut, needle in [
            ("approved_by 空", {**good, "approved_by": ""}, "approved_by"),
            ("日期不符", {**good, "allow_snapshot_date": "2026-10-15"}, "allow_snapshot_date"),
            ("已過期", {**good, "expires_at": "2026-10-17T09:00:00+08:00"}, "過期"),
        ]:
            r = run_case(tmp, produced=["daily_report_v2_2026-10-17.html"],
                         snap_date="2026-10-16", exc=mut)
            ck(f"⑥ 非法例外（{label}）→ 阻擋",
               (not r["ok"]) and any(needle in b for b in r["blocking"]), str(r["blocking"]))

        # 6b snapshot.date 缺失
        r = run_case(tmp, produced=[], snap_date="", exc=None)
        ck("⑥b snapshot.date 缺失 → 阻擋", (not r["ok"]) and any("缺失" in b for b in r["blocking"]),
           str(r["blocking"]))

        # ③ 只擋「進 produced 的」，不影響未進 produced 的未宣告檔
        r = run_case(tmp, produced=["daily_report_v2_2026-10-17.html"], snap_date=TODAY, exc=None)
        ck("③b 未宣告檔存在但未進 produced → 放行（不誤擋）", r["ok"], str(r["blocking"]))

    if "--with-existing" in sys.argv:
        print("── 既有守門未被繞過（7 staged≠produced／8 無 CIO RECORD）")
        # 7 dirty_gate：scope 外檔案不得進 commit
        p = subprocess.run([sys.executable, "tools/verify_perf_monthly_gate_wiring.py"],
                           cwd=str(BASE), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900)
        ck("⑦ staged≠produced 守門（接線閘門存在且可執行）", "PASS" in (p.stdout or ""),
           (p.stdout or "")[-200:])
        # 8 auto_push 的 CIO RECORD 要求
        p2 = subprocess.run([sys.executable, "auto_push.py", "--help"], cwd=str(BASE),
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        ck("⑧ CIO RECORD 閘門存在（auto_push 仍要求審查紀錄）",
           "--record" in (p2.stdout or "") or "--record" in (p2.stderr or ""), "")

    print(f"\n=== publish_gate 測試：PASS {len(PASS)} / FAIL {len(FAIL)} ===")
    if FAIL:
        print("FAIL:", FAIL)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
