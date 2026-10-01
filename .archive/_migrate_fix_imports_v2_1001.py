#!/usr/bin/env python3
"""INC-270 補丁 v2：以 AST 定位最後一個 top-level import，補上 sot_targets 單一入口 import。

（v1 用 regex 猜位置，在 build_dashboard.py 插到區塊中間 → IndentationError，未落地。）
用法：python _migrate_fix_imports_v2_1001.py [--apply]
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
APPLY = "--apply" in sys.argv

FILES = ["build_dashboard.py", "build_rebalance_dashboard.py", "dynamic_review.py",
         "monthly_report.py", "monthly_strategy_review.py", "morning_briefing.py",
         "report_components.py", "run_daily.py", "sabbatical_checklist_update.py",
         "rotation_engine.py"]

IMPORT_LINE = "from sot_targets import sot_monthly_expense, sot_monthly_income  # INC-270 月支出／月收入單一入口\n"
IMPORT_RE = re.compile(r"^from sot_targets import .*sot_monthly_(expense|income)", re.M)


def add_import(text: str) -> tuple[str, bool, str]:
    if IMPORT_RE.search(text):
        return text, False, "已有 import"
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    last: ast.stmt | None = None
    for node in tree.body:                       # 只認 module 層級（非函式內）的 import
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last = node
    if last is None:
        idx = 0
        if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(getattr(tree.body[0], "value", None), ast.Constant):
            idx = tree.body[0].end_lineno
        lines.insert(idx, "\n" + IMPORT_LINE)
        pos = idx
    else:
        end = last.end_lineno                    # 1-based；含多行括號 import 的整段
        pos = end
        lines.insert(end, IMPORT_LINE)
    return "".join(lines), True, f"插在第 {pos + 1} 行前（top-level import 之後）"


def main() -> int:
    for fname in FILES:
        p = BASE / fname
        t0 = p.read_text(encoding="utf-8")
        t1, added, note = add_import(t0)
        ast.parse(t1)                            # 先驗語法，過了才落地
        if APPLY and added:
            p.write_text(t1, encoding="utf-8", newline="\n")
        print(f"{'已改' if (APPLY and added) else ('待改' if added else '跳過')} {fname}：{note}")
    print("\n✅ 全部語法檢查通過" + ("（已落地）" if APPLY else "（dry-run）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
