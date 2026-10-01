#!/usr/bin/env python3
"""INC-270 補丁：為已遷移檔案補上 import，並修 build_audit_dashboard 的保單息/常態配息口徑。

（前一版 ensure_import 誤判：replace 之後檔案已含「使用處」，被當成「已 import」→ 12 檔漏 import。）
用法：python _migrate_fix_imports_1001.py [--apply]
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
APPLY = "--apply" in sys.argv

FILES = ["asset_diff_monitor.py", "build_audit_dashboard.py", "build_dashboard.py",
         "build_rebalance_dashboard.py", "dynamic_review.py", "monthly_report.py",
         "monthly_strategy_review.py", "morning_briefing.py", "report_components.py",
         "run_daily.py", "sabbatical_checklist_update.py", "rotation_engine.py"]

IMPORT_LINE = "from sot_targets import sot_monthly_expense, sot_monthly_income  # INC-270 月支出／月收入單一入口\n"
IMPORT_RE = re.compile(r"^from sot_targets import .*sot_monthly_(expense|income)")

# build_audit_dashboard：保單息改派生、常態配息不要用 153,389 舊預設
AUDIT_EDITS = [
    ('DIV = s.get("monthly_dividend_total", 153389); DIV_ACT = s.get("dividend_month_actual", 97233)',
     'DIV = float((s.get("passive_income") or {}).get("fund_dividend_conservative") or 0)  # 2026-10-01 INC-270：常態保守基本值（原讀 monthly_dividend_total 預設 153,389＝8/30 已廢值；且該鍵月初為 0）\n'
     'DIV_ACT = float(s.get("dividend_month_actual") or 0)'),
    ("MORT = 91735; POL_INT = 13333; GF = 6000",
     "MORT = 91735; POL_INT = int((liability_interest(s) or {}).get(\"保單借貸利息\") or 0); GF = 6000"
     "   # 2026-10-01 INC-270：保單息改讀 sot_targets.liability_interest（保單借貸清償後為 0；原寫死 13,333）"),
]


def add_import(text: str) -> tuple[str, bool]:
    lines = text.splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if IMPORT_RE.match(ln.lstrip()):
            return text, False                      # 已有 import
    for i, ln in enumerate(lines[:120]):
        if ln.lstrip().startswith(("from sot_targets import", "import sot_targets")):
            j = i
            while "(" in lines[j] and ")" not in lines[j] and j < len(lines) - 1:
                j += 1
            lines.insert(j + 1, IMPORT_LINE)
            return "".join(lines), True
    last = 0
    for i, ln in enumerate(lines[:120]):
        if re.match(r"^(import |from )\S", ln):
            last = i
    lines.insert(last + 1, "\n" + IMPORT_LINE)
    return "".join(lines), True


def main() -> int:
    problems: list[str] = []
    for fname in FILES:
        p = BASE / fname
        t0 = p.read_text(encoding="utf-8")
        t1, added = add_import(t0)
        note = []
        if added:
            note.append("＋import")
        if fname == "build_audit_dashboard.py":
            for old, new in AUDIT_EDITS:
                n = t1.count(old)
                if n != 1:
                    if new.split("\n")[0] in t1:
                        note.append("(audit 編輯已套用)")
                        continue
                    problems.append(f"{fname}：audit 編輯命中 {n} 次｜{old[:50]}")
                    continue
                t1 = t1.replace(old, new)
                note.append("＋保單息/配息口徑")
            if "liability_interest" in t1 and not re.search(r"^from sot_targets import .*liability_interest", t1, re.M):
                t1 = t1.replace("from sot_targets import sot_monthly_expense, sot_monthly_income",
                                "from sot_targets import sot_monthly_expense, sot_monthly_income, liability_interest")
        ast.parse(t1)
        if APPLY and t1 != t0:
            p.write_text(t1, encoding="utf-8", newline="\n")
        print(f"{'已改' if APPLY else '待改'} {fname}：{'、'.join(note) if note else '無需變更'}")
    if problems:
        print("\n❌ 問題：")
        for x in problems:
            print("  -", x)
        return 1
    print("\n✅ 完成（語法檢查通過）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
