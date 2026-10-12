# -*- coding: utf-8 -*-
"""dividend_tracker 當月總額口徑測試（A1 修正：兩分支口徑不一致）

2026-10-12 真因：main() 在「本次有掃到新配息」的分支把 dividend_month_actual／
monthly_dividend／monthly_dividend_breakdown.total 寫成**本次新增額**，只有「無掃描」
分支才寫**當月全部紀錄合計** → 同一欄位兩套口徑，掃到新配息當天會把當月實收
覆蓋成單次增量（保守底線、覆蓋率、差異分析、FIRE 進度全部連動失真）。
本檔以正反例釘住單一口徑，防止復發。

執行：python -X utf8 tests/test_dividend_tracker_total.py
"""
from __future__ import annotations

import importlib.util as _u
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:          # dividend_tracker 匯入 dividend_caliber（正典分桶器）
    sys.path.insert(0, str(REPO))
_spec = _u.spec_from_file_location("dt", REPO / "dividend_tracker.py")
dt = _u.module_from_spec(_spec)
_spec.loader.exec_module(dt)

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f" ｜{detail}" if detail and not cond else ""))


MONTH = date.today().strftime("%Y-%m")


def _snap(records: dict) -> dict:
    return {"dividend_records": records, "monthly_dividend_breakdown": {}, "date": f"{MONTH}-01"}


def run_main(snap_obj: dict, scan_result: dict) -> dict:
    """以臨時 snapshot 實跑 dt.main()，回傳寫回後的 snapshot。"""
    tmp = Path(tempfile.mkdtemp(prefix="dtt_")) / "snapshot.json"
    tmp.write_text(json.dumps(snap_obj, ensure_ascii=False, indent=1), encoding="utf-8")
    _path, _scan = dt.SNAP_PATH, dt.scan_month_dividends
    dt.SNAP_PATH, dt.scan_month_dividends = str(tmp), lambda m: scan_result
    try:
        dt.main()
    finally:
        dt.SNAP_PATH, dt.scan_month_dividends = _path, _scan
    return json.loads(tmp.read_text(encoding="utf-8"))


print("\n【dividend_tracker 當月總額單一口徑】")
prior = {f"{MONTH}-05": {"安聯保單撥回": 9446},
         f"{MONTH}-08": {"貝萊德智慧數據B11基金配息(國泰)": 49390}}
scan = {f"{MONTH}-12": {"基金配息 聯博美國成長": 34}}
FULL = 9446 + 49390 + 34

s = run_main(_snap(dict(prior)), scan)
check("P1 有掃描時 dividend_month_actual＝當月全部合計（不是本次增量 34）",
      s["dividend_month_actual"] == FULL, f"got {s['dividend_month_actual']}")
check("P2 monthly_dividend 同步同值", s["monthly_dividend"] == FULL, f"got {s['monthly_dividend']}")
check("P3 breakdown.total 與實收同值（口徑一致）",
      s["monthly_dividend_breakdown"]["total"] == FULL, f"got {s['monthly_dividend_breakdown'].get('total')}")
check("P4 保單桶 allianz／insurance 由正典分桶器計算（安聯 → allianz）",
      s["monthly_dividend_breakdown"]["allianz"] == 9446
      and s["monthly_dividend_breakdown"]["insurance"] == 9446,
      str(s["monthly_dividend_breakdown"]))
check("P5 基金桶合計＝基金實收", s["monthly_dividend_breakdown"]["fund"] == 49390 + 34,
      f"got {s['monthly_dividend_breakdown'].get('fund')}")
check("N1 舊缺陷口徑（本次增量 34）不再出現", s["dividend_month_actual"] != 34, "回歸到舊口徑")

s2 = run_main(_snap(dict(prior)), {})
check("P6 無掃描分支口徑相同（＝當月全部合計）", s2["dividend_month_actual"] == 9446 + 49390,
      f"got {s2['dividend_month_actual']}")

s3 = run_main(_snap({f"{MONTH}-05": {"安聯保單撥回": 100, "備註": "字串"},
                     "2026-09-30": {"基金配息 X": 999}}), {})
check("N2 非當月紀錄與非數值不計入", s3["dividend_month_actual"] == 100, f"got {s3['dividend_month_actual']}")

check("P7 month_total 純函式跨月隔離",
      dt.month_total({f"{MONTH}-01": {"a": 3}, "2026-01-01": {"b": 7}}, MONTH) == 3,
      str(dt.month_total({f"{MONTH}-01": {"a": 3}, "2026-01-01": {"b": 7}}, MONTH)))

print(f"\n通過 {len(PASS)} 項｜失敗 {len(FAIL)} 項")
sys.exit(1 if FAIL else 0)
