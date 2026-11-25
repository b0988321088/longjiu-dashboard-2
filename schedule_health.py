#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""排程健康摘要（2026-11-25 使用者核准，07:30）

為什麼要這支：70 支 cron 裡只要有一支壞掉，它不會告訴你——你會在某天
發現「這個月的績效報告怎麼沒來」。本支只做一件事：**失敗才出聲**。

規則：
- 只掃 enabled 的排程。
- last_status 不是 ok/success/\u2014 → 列為失敗。
- 有 cron 表達式但 last_run 距今超過容忍天數（預設 2 天，interval 型另計）→ 列為疑似未執行。
- 全部正常 → 完全不輸出（cron 靜默）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

JOBS = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\bot\AppData\Local")) / "hermes" / "cron" / "jobs.json"
OK = {"ok", "success", "done", "completed", ""}
TPE = timezone(timedelta(hours=8))


def _load() -> list[dict]:
    d = json.loads(JOBS.read_text(encoding="utf-8"))
    jobs = d if isinstance(d, list) else d.get("jobs", d)
    if isinstance(jobs, dict):
        jobs = list(jobs.values())
    return jobs


def _last_run(j: dict) -> datetime | None:
    for k in ("last_run", "last_run_at", "last_finished_at", "last_result_at"):
        v = j.get(k)
        if not v:
            continue
        try:
            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=TPE)
        except Exception:
            continue
    return None


def _interval_days(sched) -> float | None:
    """粗估該排程的正常間隔（天）；interval 型用 minutes，cron 型看小時欄。"""
    if not isinstance(sched, dict):
        return None
    if sched.get("kind") == "interval":
        m = sched.get("minutes")
        return (float(m) / 1440.0) if isinstance(m, (int, float)) else None
    expr = str(sched.get("expr") or "")
    parts = expr.split()
    if len(parts) < 5:
        return None
    # 2026-11-25 修正：先看「日/月」與「星期」欄，再判日內頻率。
    #   舊寫法把 "0 16 * * 6"（每週六）誤判成每日 → 每支週排程都被當成逾期。
    if parts[2] != "*":
        return 31.0          # 每月
    if parts[4] != "*":
        return 7.0           # 每週
    return 1.0               # 每日或日內多次


def collect(tolerance_days: float = 2.0) -> tuple[list[dict], list[dict], list[dict]]:
    """回傳 (failed, stale, pending_verify)。

    2026-11-25：月排程若上次失敗已是「一個週期以前」，代表那不是現在的問題
    （跑一次就驗得完，且下次執行才刷狀態）→ 歸 pending_verify，只在週一提示，
    避免每天拿 24 天前的舊錯誤疲勞轟炸。
    """
    now = datetime.now(TPE)
    failed, stale, pending = [], [], []
    for j in _load():
        if not j.get("enabled", True):
            continue
        name = str(j.get("name") or j.get("id") or "")[:48]
        st = str(j.get("last_status") or "").strip().lower()
        if st not in OK:
            lr = _last_run(j)
            iv = _interval_days(j.get("schedule")) or 1.0
            gap = ((now - lr).total_seconds() / 86400.0) if lr else None
            row = {"name": name, "status": st, "last": lr, "id": j.get("id"), "gap": gap}
            _thr = max(iv * 1.2, 1.5) if iv <= 7 else 14.0   # 月排程：14 天前的失敗不算現行問題
            if gap is not None and gap > _thr:
                pending.append(row)
            else:
                failed.append(row)
            continue
        lr = _last_run(j)
        iv = _interval_days(j.get("schedule"))
        if lr and iv:
            limit = iv * max(tolerance_days, 1.0) + 1.0
            gap = (now - lr).total_seconds() / 86400.0
            if gap > limit:
                stale.append({"name": name, "gap": gap, "last": lr, "id": j.get("id")})
    return failed, stale, pending


def build(tolerance_days: float = 2.0) -> str:
    failed, stale, pending = collect(tolerance_days)
    show_pending = datetime.now(TPE).weekday() == 0   # 週一才提「待驗證」舊錯誤
    if not failed and not stale and not (show_pending and pending):
        return ""
    now = datetime.now(TPE)
    lines = [f"🩺 排程健康摘要（{now.strftime('%m/%d %H:%M')}）", ""]
    if failed:
        lines.append(f"⛔ 失敗 {len(failed)} 支")
        for f in failed:
            last = f["last"].strftime("%m/%d %H:%M") if f["last"] else "無紀錄"
            lines.append(f"　· {f['name']}｜狀態 {f['status'] or '?'}｜最後執行 {last}")
    if stale:
        lines.append(f"⚠️ 疑似未執行 {len(stale)} 支")
        for s in stale:
            lines.append(f"　· {s['name']}｜已 {s['gap']:.1f} 天未執行（最後 {s['last'].strftime('%m/%d %H:%M')}）")
    if show_pending and pending:
        lines.append(f"⏳ 待下次執行驗證 {len(pending)} 支（上次失敗已超過一個週期，非現行問題）")
        for p_ in pending:
            last = p_["last"].strftime("%m/%d") if p_["last"] else "無紀錄"
            lines.append(f"　· {p_['name']}｜上次 {last} 失敗（{p_['status']}），等排程下次執行刷新")
    lines += ["", "處理方式：這則只在異常時出現；修好後下次 07:30 就不再提。"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tolerance-days", type=float, default=2.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    out = build(a.tolerance_days)
    if not out:
        if a.dry_run:
            print("✅ 全部排程正常 → 靜默")
        return 0
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
