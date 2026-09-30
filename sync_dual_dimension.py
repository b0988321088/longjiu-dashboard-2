#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_dual_dimension.py — 雙維度佔比／市場情境「現況驗證」單一寫入者

背景（2026-09-30 P0-1，使用者核准）：
  snapshot.dual_dimension_metric 與 snapshot.market_scenario_standards.現況驗證
  原本都是手寫值、**無程式寫入者** → 「現況驗證.防禦 53.8%（合格）」與
  dual_dimension 派生「49.1%（不合格）」並存，同一份報告出現相反結論（雙答案）。

本腳本把兩者一律由真值派生（實作在 sot_targets，邏輯單一）：
  · dual_dimension_metric.防禦維度.佔比 = 組成加總 ÷ (total_assets − restricted_cash)
  · market_scenario_standards.現況驗證   = dual_dimension 佔比 ＋ LTV 真值（基金質押 ÷ 擔保池）

冪等：值未變則不寫檔。用法：
  python sync_dual_dimension.py            # 同步並寫回
  python sync_dual_dimension.py --check    # 只驗證是否已同步（未同步回傳 1）
"""
import argparse
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from sot_targets import build_dual_dimension_metric, sync_scenario_verification  # noqa: E402

SNAP = BASE / "snapshot.json"


def run(check_only: bool = False) -> int:
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    before_ddm = (snap.get("dual_dimension_metric") or {}).get("防禦維度") or {}
    before_sv = (snap.get("market_scenario_standards") or {}).get("現況驗證") or {}

    snap["dual_dimension_metric"] = build_dual_dimension_metric(snap)
    snap["market_scenario_standards"] = sync_scenario_verification(snap)

    # P0-1（2026-09-30）：巢狀同義欄位 — passive_income.monthly_expense / coverage_pct
    # 必須與頂層 monthly_expense 同源。原巢狀值停在 162,781（頂層已 172,543）
    # → 同一系統兩個「月支出」，各報告依讀哪個鍵而異。
    _exp = float(snap.get("monthly_expense") or 0)
    _pi = dict(snap.get("passive_income") or {})
    _changed_pi = False
    if _exp and _pi:
        _old_exp = _pi.get("monthly_expense")
        _tc = float(_pi.get("total_conservative") or 0)
        _cov = round(_tc / _exp * 100, 1) if _tc else None
        _changed_pi = False
        if _old_exp != _exp:
            _pi["monthly_expense"] = _exp
            _changed_pi = True
        if _cov is not None and _pi.get("coverage_pct") != _cov:
            _pi["coverage_pct"] = _cov
            _changed_pi = True
        if _cov is not None:
            _note = str(_pi.get("note") or "")
            _note2 = re.sub(r"覆蓋 [\d.]+%（÷月支出 [\d,]+）", f"覆蓋 {_cov}%（÷月支出 {_exp:,.0f}）", _note)
            if _note2 != _note:
                _pi["note"] = _note2
                _changed_pi = True
        if _changed_pi:
            print(f"🔁 passive_income 同義同步：月支出 {_old_exp} → {_exp:,.0f}；覆蓋 {_cov}%")
            snap["passive_income"] = _pi

    after_ddm = (snap.get("dual_dimension_metric") or {}).get("防禦維度") or {}
    after_sv = (snap.get("market_scenario_standards") or {}).get("現況驗證") or {}

    changed = ((before_ddm.get("佔比") != after_ddm.get("佔比"))
               or (before_sv.get("防禦") != after_sv.get("防禦"))
               or (before_sv.get("結論") != after_sv.get("結論"))
               or (before_sv.get("source") is None)
               or _changed_pi)

    print(f"  雙維度防禦 {after_ddm.get('佔比')}%"
          f"（合計 {after_ddm.get('合計', 0):,.0f}；分母 {after_ddm.get('分母', 0):,.0f}）")
    print(f"  情境現況驗證 防禦 {after_sv.get('防禦')}%／收入 {after_sv.get('收入')}%／LTV {after_sv.get('LTV')}%")
    print(f"    → {after_sv.get('結論')}")

    if check_only:
        if changed:
            print("  ⚠️ --check：stored 值與派生值不一致（尚未同步）")
            return 1
        print("  ✅ --check：已同步（單一來源）")
        return 0

    if changed:
        SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  ✅ 已寫回 snapshot.json")
    else:
        print("  ✓ 無變更，未寫檔")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只驗證是否已同步，不寫檔")
    _a = ap.parse_args()
    sys.exit(run(_a.check))
