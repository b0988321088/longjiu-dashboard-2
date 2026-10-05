#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""decision_dedup_report.py — dashboard_decisions 等價收據的**讀取端 group by**（P0-2）

用途
----
寫入端的 duplicate guard 只能擋「從現在起」的重复；**既有歷史重複一律不刪、不改寫**
（使用者 2026-10-05 明令）。本支負責把歷史重複「標記出來」，讓讀取端（CIO Part A、
稽核）能 group by 並知道「有效 N 筆／原始 M 筆」。

輸出
----
  data/decision_dedup_report.json
    {
      "generated_at": ...,
      "total_entries": 1113,
      "unique_keys": 1054,
      "duplicate_groups": N,
      "redundant_entries": M,          # 可被去重掉的等價收據數
      "groups": [ {key, count, canonical_id, duplicate_ids:[...]}, ... ],
      "scan_note": "唯讀；本檔不修改 dashboard_decisions.json"
    }

duplicate key = (task, source, 當地日期 YYYY-MM-DD)  ← 與寫入端 memory_helper._dup_key 同一把尺
canonical = 該群**最早**的一筆（保留原 id，不動）。

界線
----
* 唯讀：只讀 dashboard_decisions.json，不寫回、不刪、不改欄位。
* 只輸出「標記報告」；是否回填 canonical/dup_of 欄位須另案核准。
"""
from __future__ import annotations

import json
import sys
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from memory_helper import _dup_key as dup_key   # noqa: E402  ← 與寫入端同一把尺（單一來源）

DEC_FILE = REPO / "dashboard_decisions.json"
OUT_FILE = REPO / "data" / "decision_dedup_report.json"
TPE = timezone(timedelta(hours=8))

# 使用者 2026-10-05 點名必須驗證的兩個重複對
NAMED_CASES = [("日報2026-09-30", 70), ("資產穿透2026-09-30", 70)]


def build_report(decisions: list) -> dict:
    groups: "OrderedDict[tuple, list]" = OrderedDict()
    for i, e in enumerate(decisions):
        if not isinstance(e, dict):
            continue
        k = dup_key(e)
        if k is None:                 # 空任務名 → 無法判定身分，各自一群（不與他人合併）
            k = ("__no_task__", i)
        groups.setdefault(k, []).append(e)

    dup_groups = []
    redundant = 0
    for k, items in groups.items():
        if len(items) < 2:
            continue
        ordered = sorted(items, key=lambda x: str(x.get("timestamp", "")))
        canonical = ordered[0]
        dups = ordered[1:]
        redundant += len(dups)
        dup_groups.append({
            "key": {"task": k[0], "source": k[1] if len(k) > 1 else None,
                    "date": k[2] if len(k) > 2 else "(任務名自帶日期)"},
            "count": len(items),
            "canonical_id": canonical.get("id"),
            "duplicate_ids": [d.get("id") for d in dups],
        })
    dup_groups.sort(key=lambda g: -g["count"])
    return {
        "generated_at": datetime.now(TPE).isoformat(),
        "source_file": DEC_FILE.name,
        "total_entries": len(decisions),
        "unique_keys": len(groups),
        "duplicate_groups": len(dup_groups),
        "redundant_entries": redundant,
        "named_cases": [
            {"task": t, "expected": n,
             "actual": next((g["count"] for g in dup_groups if g["key"]["task"] == t), 0)}
            for t, n in NAMED_CASES
        ],
        "groups": dup_groups,
        "scan_note": "唯讀報告；本檔不修改 dashboard_decisions.json（歷史重複只標記、不刪不改）。",
    }


def main() -> int:
    decisions = (json.loads(DEC_FILE.read_text(encoding="utf-8")) or {}).get("decisions") or []
    rep = build_report(decisions)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"決策入庫去重報告｜總筆數 {rep['total_entries']}｜唯一鍵 {rep['unique_keys']}"
          f"｜重複群 {rep['duplicate_groups']}｜可去重筆數 {rep['redundant_entries']}")
    for c in rep["named_cases"]:
        flag = "✅" if c["actual"] >= c["expected"] else "⚠️"
        print(f"  {flag} {c['task']}：{c['actual']} 筆（點名預期 {c['expected']}）")
    print("  前 5 大重複群：")
    for g in rep["groups"][:5]:
        print(f"    ×{g['count']:<3} {g['key']['date']}｜{str(g['key']['task'])[:36]}"
              f"｜canonical={g['canonical_id']}")
    print(f"  標記報告：{OUT_FILE.relative_to(REPO)}（唯讀，未動 dashboard_decisions.json）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
