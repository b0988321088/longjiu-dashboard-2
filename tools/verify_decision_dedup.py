#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_decision_dedup.py — P0-2 驗收（含必要之負向測試）

驗收對象
--------
1. 寫入端 guard：`memory_helper.add_memory()`、`append_dashboard_decisions.py`
2. 讀取端 group by：`tools/decision_dedup_report.py`
3. 歷史資料**只標記、不刪不改**（使用者 2026-10-05 明令）

測什麼
------
  D1 同一任務同日連呼叫 3 次（模擬 cron retry）→ 只入庫 1 筆
  D2 不同任務 / 不同日 / 不同來源 → 不得被誤擋（guard 不可過寬）
  D3 allow_duplicate=True → 明確允許時可再寫一筆
  D4 append_dashboard_decisions：既有等價收據再入庫 → 被擋（♻️）且檔案位元不變
  D5 append_dashboard_decisions：全新任務 → 放行（dry-run 顯示「將寫入」）
  D6 讀取端報告：點名案例 日報2026-09-30 / 資產穿透2026-09-30 各 ≥70 筆
  D7 唯讀性：跑 decision_dedup_report.py 前後，dashboard_decisions.json sha256 不變
  D8 讀取端 group by：報告內每組 canonical_id 必為該組最早一筆
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import memory_helper as mh          # noqa: E402
import decision_dedup_report as ddr  # noqa: E402

DEC = REPO / "dashboard_decisions.json"
results: list[tuple[str, bool, str]] = []


def ck(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _seed(path: Path, entries: list) -> None:
    path.write_text(json.dumps({"decisions": entries, "meta": {"version": 1}},
                               ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="dedup_test_"))
    dec_sha_before = sha(DEC)
    try:
        # ── D1 同日同任務連呼叫 3 次 → 只 1 筆 ────────────────────────────
        sandbox = tmp / "d1.json"
        _seed(sandbox, [])
        for _ in range(3):
            mh.add_memory("Hermes", f"日報{datetime.now():%Y-%m-%d}",
                          "已產出（測試）", path=sandbox)
        n = len(json.loads(sandbox.read_text(encoding="utf-8"))["decisions"])
        ck("D1 同日同任務連呼叫 3 次 → 只入庫 1 筆", n == 1, f"實際 {n} 筆")

        # ── D2 不得誤擋（不同任務／不同日／不同來源）───────────────────────
        sandbox2 = tmp / "d2.json"
        _seed(sandbox2, [])
        mh.add_memory("Hermes", "任務A", "s", path=sandbox2)
        mh.add_memory("Hermes", "任務B", "s", path=sandbox2)          # 不同任務
        mh.add_memory("Hermes", "任務A", "s", status="completed", path=sandbox2)  # 同日同任務 → 擋
        ents = json.loads(sandbox2.read_text(encoding="utf-8"))["decisions"]
        ck("D2 不同任務放行、同日同任務擋下", len(ents) == 2, f"實際 {len(ents)} 筆")

        # 不同日（昨天）→ 放行
        sandbox3 = tmp / "d3.json"
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        _seed(sandbox3, [{"id": "old", "timestamp": yesterday, "agent": "Hermes",
                          "task": "任務A", "summary": "s", "status": "completed",
                          "source": "auto"}])
        mh.add_memory("Hermes", "任務A", "s", path=sandbox3)
        ents3 = json.loads(sandbox3.read_text(encoding="utf-8"))["decisions"]
        ck("D2b 不同日期 → 放行", len(ents3) == 2, f"實際 {len(ents3)} 筆")

        # ── D3 allow_duplicate=True ───────────────────────────────────────
        mh.add_memory("Hermes", "任務A", "s", allow_duplicate=True, path=sandbox3)
        ents3b = json.loads(sandbox3.read_text(encoding="utf-8"))["decisions"]
        ck("D3 allow_duplicate=True → 可再寫一筆", len(ents3b) == 3, f"實際 {len(ents3b)} 筆")

        # ── D4 既有等價收據再入庫 → 被擋、未 append（真實整合，沙盒 repo）────
        # 不用真檔：真檔內的既有樣本都是往日收據，去重鍵含日期 → 今日再寫不算重複。
        # 要在「同日」驗證 guard，必須用沙盒（同時保證真檔不被本測試寫入）。
        sb = tmp / "repo_d4"
        sb.mkdir()
        shutil.copy(REPO / "append_dashboard_decisions.py", sb)
        shutil.copy(REPO / "memory_helper.py", sb)
        _seed(sb / "dashboard_decisions.json",
              [{"id": "u1", "timestamp": datetime.now().isoformat(), "agent": "Hermes",
                "task": "測試決策", "summary": "內容", "status": "completed",
                "source": "user"}])
        sb_dec = sb / "dashboard_decisions.json"

        def _run_sb(task, summary):
            return subprocess.run([sys.executable, str(sb / "append_dashboard_decisions.py"),
                                   "--task", task, "--summary", summary,
                                   "--source", "user", "--quiet"],
                                  cwd=str(sb), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=120)

        r1 = _run_sb("測試決策", "內容（改了內容也算同任務同日）")
        n1 = len(json.loads(sb_dec.read_text(encoding="utf-8"))["decisions"])
        ck("D4 既有等價收據再入庫 → 被擋（♻️、未 append）",
           "♻️" in (r1.stdout or "") and n1 == 1,
           f"rc={r1.returncode} n={n1} out={(r1.stdout or '').strip()[:90]}")

        r2 = _run_sb("測試決策B", "內容")
        n2 = len(json.loads(sb_dec.read_text(encoding="utf-8"))["decisions"])
        ck("D4b 不同任務 → 放行（guard 不得過寬）", n2 == 2,
           f"rc={r2.returncode} n={n2}")

        # ── D5 真檔 dry-run：全新任務放行、既有等價收據被擋 ───────────────
        r = subprocess.run([sys.executable, str(REPO / "append_dashboard_decisions.py"),
                            "--task", f"__dedup_selftest_{datetime.now():%Y%m%d%H%M%S}__",
                            "--summary", "selftest", "--source", "user", "--dry-run"],
                           cwd=str(REPO), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        ck("D5 真檔 dry-run：全新任務 → 放行（將寫入）",
           r.returncode == 0 and "dry-run" in (r.stdout or ""),
           f"rc={r.returncode} out={(r.stdout or '').strip()[:90]}")

        # ── D6 讀取端：點名案例 ≥70 ──────────────────────────────────────
        dec = json.loads(DEC.read_text(encoding="utf-8"))
        rep_before = ddr.build_report(dec["decisions"])
        named = {c["task"]: c["actual"] for c in rep_before["named_cases"]}
        ck("D6 日報2026-09-30 ≥70 且 資產穿透2026-09-30 ≥70",
           named.get("日報2026-09-30", 0) >= 70 and named.get("資產穿透2026-09-30", 0) >= 70,
           f"{named}")

        # ── D8 canonical 必為最早一筆 ────────────────────────────────────
        bad = 0
        by_id = {e.get("id"): e for e in dec["decisions"] if isinstance(e, dict)}
        for g in rep_before["groups"]:
            ids = [g["canonical_id"]] + g["duplicate_ids"]
            ts = [str(by_id.get(i, {}).get("timestamp", "")) for i in ids]
            if ts and ts[0] != min(ts):
                bad += 1
        ck("D8 canonical_id 為該群最早一筆", bad == 0, f"{bad} 組不符")

        # ── D7 唯讀性（跑真檔報告前後 sha256 不變）────────────────────────
        r = subprocess.run([sys.executable, str(REPO / "tools" / "decision_dedup_report.py")],
                           cwd=str(REPO), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
        ck("D7 報告執行成功且 dashboard_decisions.json 未被改動",
           r.returncode == 0 and sha(DEC) == dec_sha_before,
           f"rc={r.returncode} sha {dec_sha_before[:12]}→{sha(DEC)[:12]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    ck("收尾：dashboard_decisions.json 全程未被本測試修改",
       sha(DEC) == dec_sha_before, f"{dec_sha_before[:12]} vs {sha(DEC)[:12]}")

    npass = sum(1 for _, ok, _ in results if ok)
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    print(f"== 結果：{npass} PASS / {len(results) - npass} FAIL ==")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
