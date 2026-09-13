#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""release_claimed_occurrences.py — 釋放被「手動 fire」誤認領的排程時點（stdlib only，零 LLM）

背景（2026-09-14 INC-172）
------------------------
這個 Hermes 版本，任何手動 fire —— 工具 ``cronjob(action='run')`` 或 CLI ``hermes cron run``
—— 都會把 job 的「**下一個**排程時點」寫進 ``executions.scheduled_instant`` 並標記 completed。
等到那個時點真的到來，cron tick 用 ``cron/occurrences.py::completed_occurrence()``
（查 ``job_id + scheduled_instant + status='completed'``）判定「已完成」→ **直接跳過**並把
``next_run_at`` 推進到再下一次。因為 ``mark_job_run`` 事後會把 next_run_at 重算回正常值，
``jobs.json`` 看起來完全正常（稽核也全綠），所以這個漏跑是靜默的。

實測證據（2026-09-13/14）
- 9/13 五次驗證性手動 run 吃掉 5 個時點：收工登錄 9/13 21:40、AI 成本帳 9/13 22:30、
  預算檢查 9/17 18:30、法人雷達 9/14 16:15、美股緊急應變 9/14 21:30。
- 探針 job（daily 03:00）用 **CLI** ``hermes cron run`` 觸發 → 執行列 scheduled_instant
  = 隔日 03:00Z、``completed_occurrence=True``、next_run_at 顯示正常 → 換 CLI 一樣中。

修法原理
--------
手動執行的列本來就不該帶「排程時點身分」（``cron/jobs.py`` 的手動路徑即 ``_scheduled_instant=None``），
所以只要把這些列的 ``scheduled_instant`` 清成 NULL（**保留歷史列**）即可讓正式排程恢復可執行。
不動 jobs.json、不動 next_run_at。

用法
----
    python release_claimed_occurrences.py                      # 只偵測（dry-run，預設）
    python release_claimed_occurrences.py --fix                # 偵測 + 釋放（釋放前自動備份 DB）
    python release_claimed_occurrences.py --include-past --fix # 連「過去時點」的認領一起清（歷史整理）
    python release_claimed_occurrences.py --db <path>          # 指定 DB（測試／驗證用）
    python release_claimed_occurrences.py --quiet              # 全乾淨時不輸出（cron watchdog 用）

輸出：被認領的排程時點清單 + 對應的「補跑指令」建議。exit code：0 = 乾淨／已修好，1 = 仍有認領（dry-run 下）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path


def hermes_home() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "hermes"


def default_db() -> Path:
    return hermes_home() / "cron" / "executions.db"


def load_jobs() -> dict:
    """job_id → job dict（讀 cron/jobs.json）。"""
    p = hermes_home() / "cron" / "jobs.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    jobs = data.get("jobs", data) if isinstance(data, dict) else data
    if isinstance(jobs, dict):
        jobs = list(jobs.values())
    return {str(j.get("id")): j for j in jobs if isinstance(j, dict)}


def _parse(instant: str):
    try:
        d = dt.datetime.fromisoformat(instant)
    except Exception:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def find_claims(db_path: Path, include_past: bool = False) -> list:
    """回傳 [{id, job_id, started_at, scheduled_instant, future}]。

    判定：``status='completed'`` 且 ``scheduled_instant`` 非空 —— 這代表某次執行「預先完成」了
    一個排程時點。``future=True``（時點還沒到卻已完成）才是真正會讓正式排程消失的有害列。
    """
    if not Path(db_path).exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = list(conn.execute(
            "SELECT id, job_id, started_at, scheduled_instant, source, status "
            "FROM executions WHERE status='completed' AND scheduled_instant IS NOT NULL "
            "ORDER BY scheduled_instant"))
    finally:
        conn.close()
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for r in rows:
        d = _parse(r["scheduled_instant"])
        if d is None:
            continue
        future = d > now
        if future or include_past:
            out.append({
                "id": r["id"], "job_id": str(r["job_id"]), "started_at": r["started_at"],
                "scheduled_instant": (d.isoformat().replace("+00:00", "Z")), "future": future,
            })
    return out


def release(db_path: Path, claims: list) -> Path:
    """備份 DB 後，把指定列的 scheduled_instant 清成 NULL（歷史列保留）。回傳備份路徑。"""
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = Path(str(db_path) + f".bak-releaseclaim-{ts}")
    shutil.copy2(db_path, bak)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany("UPDATE executions SET scheduled_instant=NULL WHERE id=?",
                         [(c["id"],) for c in claims])
        conn.commit()
    finally:
        conn.close()
    return bak


def rerun_hint(job_id: str, jobs: dict) -> str:
    """該 job 的補跑建議（shell 直跑腳本，不碰 cron 帳務 → 不會再消費時點）。"""
    j = jobs.get(job_id)
    if not j:
        return "（job 已不存在，無需補跑）"
    script = j.get("script") or j.get("prompt", "")[:40] or "（LLM job）"
    if script.endswith((".py", ".sh")):
        workdir = j.get("workdir") or ""
        cand = Path(workdir) / script if workdir else None
        if cand and cand.exists():
            return f'python "{cand}"'
        alt = hermes_home() / "scripts" / script
        if alt.exists():
            return f'python "{alt}"'
        return f"（腳本 {script} 找不到，請人工確認）"
    return f"（LLM 驅動 job：{j.get('name','')[:30]} — 需人工決定是否補跑）"


def main() -> int:
    ap = argparse.ArgumentParser(description="釋放被手動 fire 誤認領的排程時點")
    ap.add_argument("--fix", action="store_true", help="實際釋放（預設只偵測）")
    ap.add_argument("--include-past", action="store_true", help="連過去時點的認領一起清")
    ap.add_argument("--db", default=None, help="指定 executions.db（測試用）")
    ap.add_argument("--quiet", action="store_true", help="全乾淨時不輸出")
    args = ap.parse_args()

    db_path = Path(args.db) if args.db else default_db()
    jobs = load_jobs()
    claims = find_claims(db_path, include_past=args.include_past)
    harmful = [c for c in claims if c["future"]]

    if not claims:
        if not args.quiet:
            print("✅ 排程時點認領檢查：沒有任何被預先完成（認領）的時點")
        return 0

    if not args.quiet:
        print(f"⚠️ 發現 {len(claims)} 筆『已被預先完成』的排程時點"
              f"（其中 {len(harmful)} 筆時點還沒到 = 該次排程會靜默消失）：")
        for c in claims:
            j = jobs.get(c["job_id"], {})
            tag = "🔴 未來" if c["future"] else "⚪ 過去"
            print(f"  {tag} {c['job_id'][:12]} {(j.get('name') or '')[:26]}"
                  f"｜手動執行 {str(c['started_at'])[:16]} 認領了 {c['scheduled_instant']}")
            if c["future"]:
                print(f"       補跑建議：{rerun_hint(c['job_id'], jobs)}")

    if not args.fix:
        if not args.quiet:
            print("（dry-run：未更動任何東西。要釋放請加 --fix）")
        return 1

    bak = release(db_path, claims)
    left = find_claims(db_path, include_past=args.include_past)
    if not args.quiet:
        print(f"🔧 已釋放 {len(claims)} 筆（備份：{bak.name}）；殘留 {len(left)} 筆")
        for c in left:
            print(f"  ❌ 仍被佔：{c['job_id']} @ {c['scheduled_instant']}")
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())
