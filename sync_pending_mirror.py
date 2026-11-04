#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_pending_mirror.py — pending_decisions.json → dashboard_decisions.pending_decisions 即時鏡像。

為什麼要有這支（CIO 2026-11-04 排序 D）：
  pending_decisions.json 改完後，dashboard_decisions.json 的 pending_decisions 鏡像原本要等
  下一輪 regenerate_report（07:00 或 22:00）才會同步；期間兩份不一致，稽核與 CIO 復盤會讀到舊的。

設計約束：
  - 只碰 dashboard_decisions.json 的 pending_decisions 區塊（文字手術，不整檔重排）。
  - decisions 陣列逐位元不變（寫入前後比對，變了就中止）。
  - 轉換邏輯與 regenerate_report.py 完全一致：date / action(title) / status / tags，排除含「核准」者。
  - 不 commit、不 push：入庫仍走既有發布流程。

用法：
  python sync_pending_mirror.py            # 同步（無變更時直接退出 0）
  python sync_pending_mirror.py --check    # 只檢查是否一致，不寫入
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
PD = REPO / "pending_decisions.json"
DD = REPO / "dashboard_decisions.json"


def build_mirror(pd_list):
    return [
        {
            "date": d.get("date", ""),
            "action": d.get("title", ""),
            "status": d.get("status", ""),
            "tags": d.get("tags", ""),
        }
        for d in pd_list
        if "核准" not in d.get("status", "")
    ]


def main() -> int:
    check_only = "--check" in sys.argv
    pd_list = json.loads(PD.read_text(encoding="utf-8"))
    mirror = build_mirror(pd_list)

    raw = DD.read_text(encoding="utf-8")
    cur = json.loads(raw)
    if cur.get("pending_decisions") == mirror:
        print(f"✅ 已一致（{len(mirror)} 筆），無需同步")
        return 0
    if check_only:
        print(f"❌ 不一致：源檔 {len(mirror)} 筆 vs 鏡像 {len(cur.get('pending_decisions') or [])} 筆")
        return 1

    # 文字手術：定位 "pending_decisions": [ ... ] 區塊
    key = '"pending_decisions":'
    ki = raw.find(key)
    if ki < 0:
        print("❌ dashboard_decisions.json 找不到 pending_decisions 鍵，中止")
        return 2
    start = raw.find("[", ki)
    depth, end = 0, -1
    for i in range(start, len(raw)):
        ch = raw[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        print("❌ 無法配對 pending_decisions 區塊結尾，中止")
        return 2

    body = json.dumps(mirror, ensure_ascii=False, indent=2).split("\n")
    new_block = "[\n" + "\n".join("  " + ln for ln in body[1:-1]) + "\n  ]"
    new_raw = raw[:start] + new_block + raw[end + 1:]

    before = json.loads(raw)
    after = json.loads(new_raw)
    if before.get("decisions") != after.get("decisions"):
        print("❌ decisions 陣列被動到，中止（不得以鏡像同步為由改動歷史核准）")
        return 3
    if after.get("pending_decisions") != mirror:
        print("❌ 寫入後驗證失敗，中止")
        return 3

    DD.write_text(new_raw, encoding="utf-8")
    print(f"✅ 鏡像已同步（{len(mirror)} 筆）；decisions {len(after.get('decisions') or [])} 筆未變動")
    return 0


if __name__ == "__main__":
    sys.exit(main())
