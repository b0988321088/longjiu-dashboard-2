#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行動提醒的回覆落地（2026-11-25 使用者核准 P1 閉環）

為什麼要這支：提醒如果只能「看」，就會變成背景噪音。使用者回一句
「✅ OI-07 已處理 / 延後 OI-07 7天 / 作廢 OI-07」，就要有人把狀態改掉、
把裁決寫進 dashboard_decisions（CIO 唯一讀取面），否則下次提醒又出現同一件事。

支援：
    python apply_action_reply.py --done OI-07 --note "12/02 已送件，單號 xxx"
    python apply_action_reply.py --snooze OI-07 --days 7
    python apply_action_reply.py --void OI-08 --note "級別不可選，作廢"
    （加 --dry-run 只看會做什麼；PD-*/CV-* 這類非台帳項只寫決策紀錄）

邊界：只改 data/weekly_open_items.json 與 dashboard_decisions.json；
不動 snapshot 真值、不動部位。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
OEI = BASE / "data" / "weekly_open_items.json"
APPEND = BASE / "append_dashboard_decisions.py"


def _load():
    return json.loads(OEI.read_text(encoding="utf-8"))


def _save(d):
    d.setdefault("_meta", {})["updated"] = date.today().isoformat()
    OEI.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _record(task: str, summary: str, dry: bool):
    if dry:
        print(f"[dry-run] 會寫入決策：{task}")
        return
    r = subprocess.run([sys.executable, str(APPEND), "--task", task,
                        "--summary", summary, "--status", "已核准"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=str(BASE))
    print((r.stdout or "").strip().splitlines()[-1] if r.stdout else f"⚠️ 決策寫入失敗 rc={r.returncode}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--done")
    ap.add_argument("--snooze")
    ap.add_argument("--void")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--note", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    key = a.done or a.snooze or a.void
    if not key:
        ap.error("要指定 --done / --snooze / --void 其中一個")
    oi_like = key.startswith("OI-")
    d = _load()
    item = next((i for i in d.get("items", []) if i.get("id") == key), None)

    if a.done:
        if oi_like and item:
            item["status"] = "CLOSED"
            item["closed"] = date.today().isoformat()
            item["close_note"] = a.note or "使用者回覆已處理"
        _save(d) if (oi_like and item and not a.dry_run) else None
        print(f"{'[dry-run] ' if a.dry_run else ''}✅ {key} 標記 CLOSED")
        _record(f"行動提醒結案：{key}", f"使用者回覆已處理。備註：{a.note or '—'}", a.dry_run)

    elif a.snooze:
        until = (date.today() + timedelta(days=a.days)).isoformat()
        if oi_like and item:
            item["snooze_until"] = until
            if not a.dry_run:
                _save(d)
        print(f"{'[dry-run] ' if a.dry_run else ''}⏰ {key} 延後至 {until}")
        _record(f"行動提醒延後：{key}", f"延後 {a.days} 天至 {until}。備註：{a.note or '—'}", a.dry_run)

    else:
        if oi_like and item:
            item["status"] = "WAIVED"
            item["closed"] = date.today().isoformat()
            item["close_note"] = a.note or "使用者裁定作廢"
        if oi_like and item and not a.dry_run:
            _save(d)
        print(f"{'[dry-run] ' if a.dry_run else ''}🗑️ {key} 作廢")
        _record(f"行動提醒作廢：{key}", f"使用者裁定作廢。備註：{a.note or '—'}", a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
