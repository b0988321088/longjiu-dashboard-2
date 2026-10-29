#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第一批驗收測試（P1/P2/P3/P4）— 使用者 2026-10-29 授權範圍

驗收對應：
  P2 日期對應 → fund_pledge_maturity，且不得再綁 mortgage_cathay_grace.撥款日
  P1 總表欄位／缺值處理／舊版相容
  P3 LTV 為主要表達（180% 僅換算參考）
  P4 加總口徑與單池未定義必須揭露
  財務門檻未變：700,000／900,000／180%／1.5pp／30%
跑法：python tests/test_bbd_quarterly_20261029.py（或 pytest）
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bbd_quarterly_check as m  # noqa: E402

SNAP = json.loads((ROOT / "snapshot.json").read_text(encoding="utf-8"))
TODAY = date(2026, 10, 29)


def test_p2_events_bind_pledge_maturity():
    ev = m.collect_events(SNAP, TODAY, horizon_days=800)
    joined = " ".join(ev)
    assert "2027-09-29" in joined, f"缺質押到期日：{ev}"
    assert "2026-08-20" not in joined, f"事件仍綁到房貸撥款日：{ev}"


def test_p3_ltv_primary_and_180_only_reference():
    ev = m.collect_evidence(SNAP, terms_has_written=False)
    metrics = {"cash_unrestricted": 1_140_016, "cash_floor": 700_000, "restricted_cash": 900_000,
               "loan": 5_900_000, "pool": 11_924_797, "ltv_pct": 49.48,
               "stress_drop_pct": 30, "stress_ltv_pct": 70.7,
               "maint_pct": 202.1, "stress_maint_pct": 141.5,
               "interest_monthly": 65_683, "sustainable_cash_monthly": 180_100,
               "coverage_interest_pct": 274.0, "coverage_expense_pct": 113.1,
               "mortgage_balance": 25_005_344, "mortgage_monthly": 91_735,
               "total_liabilities": 30_952_472, "pledge_maturity": "2027-09-29",
               "cathay_grace_end": "2029-08-20"}
    s = m.build_summary(SNAP, TODAY, legacy_gates={"現金關": "PASS", "利差關": "UNKNOWN", "借款關": "FAIL"},
                        metrics=metrics, evidence=ev)
    g1 = " ".join(s["gates"]["G1"]["lines"])
    assert "LTV 49.48%" in g1 and "180% 僅壓力參考" in g1, g1
    assert "單池" in g1 and "加總" in g1, "P4 揭露缺失：" + g1
    assert s["gates"]["G1"]["status"] == "HOLD"


def test_p1_missing_data_never_pass():
    """缺 fund_breakdown_cathay → 不得因缺值而 PASS。"""
    thin = {k: v for k, v in SNAP.items() if k != "fund_breakdown_cathay"}
    ev = m.collect_evidence(thin, terms_has_written=False)
    metrics = {"cash_unrestricted": 0, "cash_floor": 700_000, "restricted_cash": 0,
               "loan": 0, "pool": 0, "ltv_pct": 0.0, "stress_drop_pct": 30,
               "stress_ltv_pct": 0.0, "maint_pct": 0.0, "stress_maint_pct": 0.0,
               "interest_monthly": 0, "sustainable_cash_monthly": 0,
               "coverage_interest_pct": 0.0, "coverage_expense_pct": None,
               "mortgage_balance": 0, "mortgage_monthly": 0,
               "total_liabilities": 0, "pledge_maturity": None, "cathay_grace_end": None}
    s = m.build_summary(thin, TODAY, legacy_gates={"現金關": "FAIL", "利差關": "UNKNOWN", "借款關": "UNKNOWN"},
                        metrics=metrics, evidence=ev)
    assert s["verdict"] == "HOLD", s["verdict"]
    assert all(s["gates"][g]["status"] != "PASS" for g in ("G1", "G2", "G3"))


def test_p1_summary_file_schema_and_legacy_state():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = m.main()
    assert rc == 0
    summary = json.loads((ROOT / "data" / "gate_summary.json").read_text(encoding="utf-8"))
    assert summary["schema"] == "gate_summary/v1"
    assert set(summary["gates"]) == {"G1", "G2", "G3"}
    assert summary["verdict"] in ("HOLD", "待補件", "通過待授權")
    assert summary["authorization"]["fund_action"] is False
    assert summary["authorization"]["publish"] is False
    # 舊版相容：state 仍保留三個舊鍵
    state = json.loads((ROOT / "data" / "bbd_quarterly_state.json").read_text(encoding="utf-8"))
    for k in ("現金關", "利差關", "借款關"):
        assert k in state["gates"], state["gates"]


def test_thresholds_unchanged():
    assert m.CASH_FLOOR == 700_000
    assert m.RESTRICTED_EXPECT == 900_000
    assert m.MAINT_MIN_PCT == 180.0
    assert m.SPREAD_MIN_PP == 1.5
    assert m.STRESS_DROP_PCT == 30.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed} PASS / {failed} FAIL")
    raise SystemExit(1 if failed else 0)
