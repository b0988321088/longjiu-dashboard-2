#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提醒回應率週統計（2026-11-25 使用者核准 P2-②，週一 07:20）

目的：提醒系統最容易死於「推了沒人理」。這支每週算一次：
- 推了幾則（data/reminder_log.jsonl 的無 reply 紀錄）
- 你回了幾則（reply 紀錄：done／snooze／void）
- 回應率 = 有回覆的 key ÷ 出現過的 key
- 「卡住」清單：連續 ≥3 天被推、你一次都沒回 → 建議作廢或降級成週報

判讀原則（避免自我欺騙）：回應率低不代表要推更多，通常代表該少推或該作廢。
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
RLOG = BASE / "data" / "reminder_log.jsonl"


def _rows(since: date) -> list[dict]:
    if not RLOG.exists():
        return []
    out = []
    for line in RLOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            d = date.fromisoformat(str(r.get("date")))
        except Exception:
            continue
        if d >= since:
            out.append(r)
    return out


def build(days: int = 7, ref: date | None = None) -> str:
    ref = ref or date.today()
    since = ref - timedelta(days=days - 1)
    rows = _rows(since)
    pushes = [r for r in rows if "reply" not in r]
    replies = [r for r in rows if "reply" in r]
    if not rows:
        return ""

    per_key = Counter()
    for r in pushes:
        for k in r.get("keys") or []:
            per_key[k] += 1
    replied = set()
    for r in replies:
        replied.add(str(r.get("key")))
    pushed_keys = set(per_key)
    hit = pushed_keys & replied if replied else set()
    rate = (len(pushed_keys & replied) / len(pushed_keys) * 100) if pushed_keys else 0.0

    stuck = [(k, n) for k, n in per_key.items() if n >= 3 and k not in replied]
    lines = [f"📊 提醒回應率（{since.month}/{since.day:02d}–{ref.month}/{ref.day:02d}）",
             f"· 推播 {len(pushes)} 則／涵蓋 {len(pushed_keys)} 個項目",
             f"· 你的回覆 {len(replies)} 筆（" +
             "／".join(f"{a} {sum(1 for r in replies if r.get('reply') == a)}"
                       for a in ("done", "snooze", "void")) + "）",
             f"· 回應率 {rate:.0f}%（{len(hit)}/{len(pushed_keys)}）"]
    if stuck:
        lines.append("· 卡住的項目（推 ≥3 次、你沒回）：")
        for k, n in sorted(stuck, key=lambda x: -x[1]):
            lines.append(f"　– {k}：{n} 次 → 建議作廢或改列週報，不要每天出現")
    else:
        lines.append("· 沒有卡住的項目")
    if rate < 30 and pushed_keys and len(pushes) >= 3:
        lines.append("· 判讀：回應率 <30% → 下週減量（寧可少推、每則都要能行動）")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--today", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    ref = date.fromisoformat(a.today) if a.today else None
    out = build(a.days, ref)
    if not out:
        if a.dry_run:
            print("無推播紀錄（首次統計前會靜默）")
        return 0
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
