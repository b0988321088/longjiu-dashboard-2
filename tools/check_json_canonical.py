#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_json_canonical.py — canonical indent 守門（2026-11-22 INC）

為什麼有這支：
    2026-11-16 一次人工寫入把 schedule_events.json 從 canonical indent=2 寫成 indent=1，
    之後每天 22:15 / 22:38 的 cron 都在 commit 時被 json_guard 判「整檔重排」擋下，
    連續 6 天沒有人發現（json_guard 只在 commit 時抱怨，產線只在 log 裡失敗）。
    2026-11-22 週日清理腳本以正確 indent=2 寫回，反而被當成「重排」擋住 → 才暴露。

    這支檢查把「檔案實際 indent」與 canonical 對齊，讓格式漂移在下一個班次就被抓到，
    不等它變成 commit 阻塞。

canonical 依據：
    schedule_events / pending_decisions / dashboard_decisions = 2
    snapshot / work_log / radar_state = 1
    （2026-09 定案；只列行數 >200、會被 json_guard 判重排的檔案）

用法：python tools/check_json_canonical.py [-v]
     rc=0 全數符合；rc=1 有漂移（印出檔名、實際、預期）
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CANON = {
    "snapshot.json": 1,
    "work_log.json": 1,
    "radar_state.json": 1,
    "schedule_events.json": 2,
    "dashboard_decisions.json": 2,
}


def detect_indent(path: Path) -> int | None:
    """取第 2~3 行的前導空白寬度（JSON 若有縮排，第一層物件必在此出現）。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for ln in lines[1:4]:
        stripped = ln.lstrip(" ")
        if stripped and stripped != ln:
            return len(ln) - len(stripped)
    return 0


def main() -> int:
    verbose = "-v" in sys.argv[1:]
    bad = []
    checked = 0
    for name, expect in CANON.items():
        p = REPO / name
        if not p.exists():
            print(f"⚠️  {name}: 檔案不存在，跳過", file=sys.stderr)
            continue
        checked += 1
        actual = detect_indent(p)
        if actual is None:
            print(f"⚠️  {name}: 無法讀取，跳過", file=sys.stderr)
            continue
        if actual != expect:
            bad.append((name, actual, expect))
        elif verbose:
            print(f"  ✅ {name}: indent={actual}")

    if bad:
        print("❌ canonical indent 漂移（會被 json_guard 判整檔重排、擋住 commit）：", file=sys.stderr)
        for name, actual, expect in bad:
            print(f"   · {name}: 實際 indent={actual}，應為 {expect}", file=sys.stderr)
        print("   修正：用 tools/json_guard.py 的 safe_json_write() 或 "
              "json.dump(..., ensure_ascii=False, indent=<canonical>) 重寫後重新 add。",
              file=sys.stderr)
        return 1

    if verbose:
        print(f"✅ canonical indent 全數符合（{checked} 檔）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
