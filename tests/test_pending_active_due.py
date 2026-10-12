# -*- coding: utf-8 -*-
"""pending 期限管理只對「進行中」卡生效（結案態不得被要求期限）

2026-10-12：pending_decisions.json 出現第一張結案卡（P0-2 資金鏈閉環，status=已完成）後，
check_dividend_caliber 的「無 due_date 者標記 needs_due_date」立即亮假紅燈——
該檢查隱含假設「所有卡都在進行中」。狀態判定改委派 pending_engine.is_active（單一來源），
結案態（已完成／關案）不進期限管理；狀態機本身未被放寬（仍為四態）。

執行：python -X utf8 tests/test_pending_active_due.py
"""
from __future__ import annotations

import importlib.util as _u
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = _u.spec_from_file_location("pe", REPO / "pending_engine.py")
pe = _u.module_from_spec(_spec)
_spec.loader.exec_module(pe)

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f" ｜{detail}" if detail and not cond else ""))


def flagged(items: list) -> list:
    """複製 check_dividend_caliber 的判定式（只抓進行中卡）。"""
    active = [x for x in items if pe.is_active(x)]
    return [x.get("title") for x in active if not x.get("due_date") and not x.get("needs_due_date")]


print("\n【pending 期限管理＝僅進行中卡】")
check("狀態機未被放寬（STATUS_ENUM 仍四態）",
      pe.STATUS_ENUM == ("待處理", "已確認", "已完成", "關案"), str(pe.STATUS_ENUM))
check("ACTIVE_STATUS 僅含進行中兩態", pe.ACTIVE_STATUS == ("待處理", "已確認"), str(pe.ACTIVE_STATUS))

for st, exp in (("待處理", True), ("已確認", True), ("已完成", False), ("關案", False),
                ("HOLD", False), ("", False)):
    check(f"is_active(status={st or '空字串'}) == {exp}", pe.is_active({"status": st}) is exp)
check("is_active(None) / 缺 status → 非進行中",
      pe.is_active(None) is False and pe.is_active({}) is False)

check("正例：進行中卡無期限且未標記 → 被抓（真紅燈仍有效）",
      flagged([{"title": "A", "status": "待處理"}]) == ["A"], str(flagged([{"title": "A", "status": "待處理"}])))
check("正例：已確認卡無期限且未標記 → 被抓",
      flagged([{"title": "B", "status": "已確認"}]) == ["B"])
check("反例：結案卡無期限 → 不抓（假紅燈消除）",
      flagged([{"title": "P0-2", "status": "已完成"}]) == [], str(flagged([{"title": "P0-2", "status": "已完成"}])))
check("反例：關案卡無期限 → 不抓", flagged([{"title": "C", "status": "關案"}]) == [])
check("反例：進行中卡已標 needs_due_date → 不抓",
      flagged([{"title": "D", "status": "待處理", "needs_due_date": True}]) == [])
check("反例：進行中卡有 due_date → 不抓",
      flagged([{"title": "E", "status": "待處理", "due_date": "2026-10-15"}]) == [])
check("混卡情境：僅進行中那張被抓",
      flagged([{"title": "done", "status": "已完成"},
               {"title": "open", "status": "待處理"}]) == ["open"])

print(f"\n通過 {len(PASS)} 項｜失敗 {len(FAIL)} 項")
sys.exit(1 if FAIL else 0)
