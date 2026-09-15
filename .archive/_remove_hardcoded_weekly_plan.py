# -*- coding: utf-8 -*-
"""移除 run_daily.py 的硬編碼週計畫 helper（2026-09-13）
該 helper 定義了 plan_summary/plan_table_rows/execution_date_range/execution_records，
但 render_daily_report 直接引用這些變數而從未呼叫它 → 日報 NameError，
且內容是貼死的文字（不會隨 snapshot 更新）。
修法：刪除 helper，改由 snapshot.rotation_recommendation / weekly_ops_closure_* 動態產生。
"""
import re
from pathlib import Path

P = Path(__file__).resolve().parent / "run_daily.py"
src = P.read_text(encoding="utf-8")

start = src.find("def _get_weekly_plan_and_execution()")
end = src.find("def _fmt_rent_status(tv):")
assert start != -1 and end != -1 and start < end, (start, end)

removed = src[start:end]
assert "plan_table_rows" in removed and "execution_records" in removed
src = src[:start] + src[end:]
src = src.replace("\n\n\n\ndef _fmt_rent_status", "\n\n\ndef _fmt_rent_status")

P.write_text(src, encoding="utf-8")

import ast  # noqa: E402
ast.parse(P.read_text(encoding="utf-8"))
print("removed lines:", removed.count("\n"))
print("syntax OK")
print("remaining refs:", re.findall(r"weekly_plan_\w+|weekly_execution_\w+|_get_weekly_plan_and_execution", P.read_text(encoding='utf-8')))
