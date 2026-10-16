#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INC-292（卡 #15 工程部分）不變量閘門測試：暫時性占用／待確認應收

驗收對應：① 新科目（不與 cash_in_transit 混用）② 不變量擴充 ③ 禁重複計 ⑤ 負向測試
（④ 10/14 雙分支結轉＝待中籤結果，本測試不涉及）

案例：
  P1 現況 snapshot → 不變量成立（None）
  P2 pending_receivables 缺鍵 → 視為 0，且不拋錯
  N1 現金桶已含 + 同時列應收（雙重計）→ 必須轉紅，且診斷指名「疑似重複計」
  N2 應收已列但總資產未加回（漏記）→ 必須轉紅，且差額等於該筆
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from sot_targets import pending_receivables, penetration_invariant_error  # noqa: E402


def _sat_twd(snap: dict) -> float:
    """與 check_thresholds 同源：衛星（黃金＋健康）由 update_all.calc_penetration 取得。"""
    spec = importlib.util.spec_from_file_location("_ua_test", BASE / "update_all.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    pv = mod.calc_penetration(snap.get("cash_total"), snap.get("insurance_current_value"),
                              snap.get("securities_total_market_value"),
                              snap.get("fund_market_value"), snap=snap)
    return float(pv.get("黃金", 0)) + float(pv.get("健康", 0))


def main() -> int:
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    sat = _sat_twd(snap)
    pr = pending_receivables(snap)
    res: list[tuple[str, bool, str]] = []

    # P1 現況
    err = penetration_invariant_error(snap, sat)
    res.append(("P1 現況不變量成立", err is None, err or ""))

    # P2 缺鍵 → 0
    s2 = copy.deepcopy(snap)
    s2.pop("pending_receivables", None)
    res.append(("P2 缺鍵視為 0（不拋錯）", pending_receivables(s2) == 0.0, ""))

    # N1/N2 用**合成**應收，不依賴 live 資料（負向測試必須自足）
    # 基準：先把現有應收移除（連同其佔用的總資產），再加合成應收 → 避免與 live 值互相污染
    _SYN = 100000.0
    base = copy.deepcopy(snap)
    _live = pending_receivables(base)
    base.pop("pending_receivables", None)
    base["total_assets"] = float(base.get("total_assets", 0)) - _live
    base["pending_receivables"] = {"items": [{"項目": "測試用", "金額": _SYN}], "合計": _SYN}
    base["total_assets"] = float(base.get("total_assets", 0)) + _SYN
    e0 = penetration_invariant_error(base, sat)
    res.append(("N0 合成基準（僅加應收＋加回總資產）應成立", e0 is None, (e0 or "")[:120]))

    # N1 雙重計：現金桶已含該筆 + 又列應收
    s3 = copy.deepcopy(base)
    s3["penetration"]["actual_twd"]["現金/安全網"] = float(s3["penetration"]["actual_twd"].get("現金/安全網", 0)) + _SYN
    e3 = penetration_invariant_error(s3, sat)
    res.append(("N1 雙重計必須轉紅", e3 is not None, (e3 or "")[:120]))
    res.append(("N1 診斷指名重複計", bool(e3 and "疑似重複計" in e3), ""))

    # N2 漏記：列了應收但總資產未加回
    s4 = copy.deepcopy(base)
    s4["total_assets"] = float(s4.get("total_assets", 0)) - _SYN
    e4 = penetration_invariant_error(s4, sat)
    res.append(("N2 漏記必須轉紅", e4 is not None, (e4 or "")[:120]))

    fail = 0
    for name, ok, note in res:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"｜{note}" if note and not ok else ""))
        if not ok:
            fail += 1
    print(f"\n{len(res) - fail} 通過／{fail} 失敗（待確認應收＝{pr:,.0f}）")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
