#!/usr/bin/env python3
"""INC-270 一次性遷移：月支出／月收入一律走 sot_targets 單一入口（移除寫死 fallback）。

使用者 2026-10-01 核准。可重跑（每處先 assert 命中，已遷移者自動跳過）。
用法：python _migrate_monthly_expense_1001.py [--apply]
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
APPLY = "--apply" in sys.argv

# (檔名, 舊字串, 新字串, 需要的 import 名)
EDITS: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("asset_diff_monitor.py",
     '"monthly_expense": float(snap.get("monthly_expense", 162781)),',
     '"monthly_expense": float(sot_monthly_expense(snap)),',
     ("sot_monthly_expense",)),
    ("build_audit_dashboard.py",
     'EXP = s.get("monthly_expense", 162781); FIXED = s.get("monthly_fixed_expense", {}).get("合計", 162781)',
     'EXP = sot_monthly_expense(s); FIXED = float((s.get("monthly_fixed_expense") or {}).get("合計") or EXP)',
     ("sot_monthly_expense",)),
    ("build_dashboard.py",
     'expense = snap.get("monthly_expense", 162781) or 162781',
     'expense = sot_monthly_expense(snap)\n    if not expense:\n        raise ValueError("snapshot.monthly_expense <= 0：拒絕以 0 當分母（詳見 sot_monthly_expense）")',
     ("sot_monthly_expense",)),
    ("build_dashboard.py",
     '_exp = float(expense or 0) or 162781.0',
     '_exp = float(expense or 0)',
     ()),
    ("build_rebalance_dashboard.py",
     'monthly_exp = s.get("monthly_expense", 162781)',
     'monthly_exp = sot_monthly_expense(s)',
     ("sot_monthly_expense",)),
    ("dynamic_review.py",
     "snap.get('monthly_expense', 162781)",
     "sot_monthly_expense(snap)",
     ("sot_monthly_expense",)),
    ("monthly_report.py",
     '_expense = snap.get("monthly_expense", 162781) or 162781',
     '_expense = sot_monthly_expense(snap)',
     ("sot_monthly_expense",)),
    ("monthly_strategy_review.py",
     "snap.get('monthly_expense',162781)",
     "sot_monthly_expense(snap)",
     ("sot_monthly_expense",)),
    ("morning_briefing.py",
     'expense = snap.get("monthly_expense", 162781)  # 當下真實常態開銷',
     'expense = sot_monthly_expense(snap)  # 當下真實常態開銷（單一入口）',
     ("sot_monthly_expense",)),
    ("report_components.py",
     'expense = snap.get("monthly_expense", 162781)',
     'expense = sot_monthly_expense(snap)',
     ("sot_monthly_expense",)),
    ("run_daily.py",
     'tv.get("monthly_expense", 162781) or 1',
     'sot_monthly_expense(tv) or 1',
     ("sot_monthly_expense",)),
    ("run_daily.py",
     "_exp = _snap_p.get('monthly_expense', 162781)",
     "_exp = sot_monthly_expense(_snap_p)",
     ()),
    ("run_daily.py",
     '_exp = _snap_now.get("monthly_expense") or 162781',
     '_exp = sot_monthly_expense(_snap_now)',
     ()),
    ("sabbatical_checklist_update.py",
     'exp = snap.get("monthly_expense", 162781)',
     'exp = sot_monthly_expense(snap)',
     ("sot_monthly_expense",)),
    ("rotation_engine.py",
     'surplus = snap.get("monthly_income", 228751) - snap.get("monthly_expense", 162781)',
     'surplus = sot_monthly_income(snap) - sot_monthly_expense(snap)',
     ("sot_monthly_income", "sot_monthly_expense")),
]

IMPORT_LINE = "from sot_targets import sot_monthly_expense, sot_monthly_income  # INC-270 單一入口\n"


def ensure_import(text: str, names: tuple[str, ...]) -> tuple[str, bool]:
    """確保檔案有需要的 name import（已 import 就不動，避免重複行）。"""
    if not names:
        return text, False
    missing = [n for n in names if not re.search(rf"\b{n}\b", text)]
    if not missing:
        return text, False
    if "sot_monthly_income" not in text and "sot_monthly_expense" not in text:
        # 尚未有本遷移的 import → 接在既有 sot_targets import 之後，否則接在最後一行 import 之後
        lines = text.splitlines(keepends=True)
        idx = None
        for i, ln in enumerate(lines[:120]):
            if ln.lstrip().startswith(("from sot_targets import", "import sot_targets")):
                idx = i
        if idx is not None:
            # 處理多行括號 import
            j = idx
            while "(" in lines[j] and ")" not in lines[j] and j < len(lines) - 1:
                j += 1
            lines.insert(j + 1, IMPORT_LINE)
        else:
            last = 0
            for i, ln in enumerate(lines[:120]):
                if re.match(r"^(import |from )\S", ln):
                    last = i
            lines.insert(last + 1, "\n" + IMPORT_LINE)
        return "".join(lines), True
    return text, False


def main() -> int:
    touched: dict[str, list[str]] = {}
    problems: list[str] = []
    for fname, old, new, names in EDITS:
        p = BASE / fname
        if not p.exists():
            problems.append(f"缺檔：{fname}")
            continue
        t0 = p.read_text(encoding="utf-8")
        if new.split("\n")[0] in t0 and old not in t0:
            print(f"跳過（已遷移）{fname}｜{old[:45]}…")
            continue
        n = t0.count(old)
        if n not in (1, 2):
            problems.append(f"{fname}：命中 {n} 次（預期 1~2）｜{old[:60]}")
            continue
        if n == 2:
            print(f"  ↳ {fname}：同一字串 {n} 處同義，一併替換")
        t1 = t0.replace(old, new)
        t1, added = ensure_import(t1, names)
        if APPLY:
            p.write_text(t1, encoding="utf-8", newline="\n")
        ast.parse(t1)                     # 語法檢查（不落地也要先驗）
        touched.setdefault(fname, []).append(old[:50] + (" ＋import" if added else ""))
        print(f"{'已改' if APPLY else '待改'} {fname}｜{old[:50]}…")
    print()
    for f, items in touched.items():
        print(f"  {f}：{len(items)} 處")
    if problems:
        print("\n❌ 問題：")
        for x in problems:
            print("  -", x)
        return 1
    print(f"\n✅ 全部 {sum(len(v) for v in touched.values())} 處{'已套用' if APPLY else '待套用'}，語法檢查通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
