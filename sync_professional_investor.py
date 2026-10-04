#!/usr/bin/env python3
"""sync_professional_investor.py — PI 專業投資人「唯一寫入者」（使用者 2026-10-04 裁決）

唯一有權寫入 snapshot.professional_investor 的程式；其他腳本一律不得直接寫此鍵。

寫入欄位（真值）
  application_status  ：未申請／已送件／補件中／審核中
  approval_status     ：未核准／已核准／未通過／失效
  note（選配）、source、updated_at

拒寫欄位（衍生值 → 一律即時計算、不得落地）
  threshold_twd ／ financial_assets_proxy_twd ／ gap_twd ／ meets_financial_threshold
  理由：落地值會隨資產變動而過期 —— 2026-10-04 實證的 28,220,311 即此型 stale 假真值。

紅線
  財力達標 ≠ 已核准。writer **不得**依資產推導／自動填入「已核准」；
  只有明確的核准事實才能寫入 approval_status="已核准"。

用法
  python sync_professional_investor.py --application-status 已送件 --approval-status 未核准
  python sync_professional_investor.py --application-status 未申請 --approval-status 未核准 --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP_PATH = BASE / "snapshot.json"
KEY = "professional_investor"
DERIVED_KEYS = ("threshold_twd", "financial_assets_proxy_twd", "gap_twd",
                "meets_financial_threshold", "current")
ALLOWED_EXTRA = ("note", "force_order", "macro_triggers", "forbidden",
                 "lombard_bridge", "risk_warning", "strategy")


def _states():
    sys.path.insert(0, str(BASE))
    import sot_targets as sot
    return sot.PI_APPLICATION_STATES, sot.PI_APPROVAL_STATES, sot


def main() -> int:
    ap = argparse.ArgumentParser(description="PI 唯一寫入者（snapshot.professional_investor）")
    ap.add_argument("--application-status", required=True)
    ap.add_argument("--approval-status", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--source", default="user")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    app_states, apv_states, sot = _states()
    if a.application_status not in app_states:
        print(f"❌ application_status={a.application_status!r} 非合法狀態（合法：{'／'.join(app_states)}）")
        return 2
    if a.approval_status not in apv_states:
        print(f"❌ approval_status={a.approval_status!r} 非合法狀態（合法：{'／'.join(apv_states)}）")
        return 2

    raw = SNAP_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    # round-trip 安全檢查：本檔必須能用 indent=1 無損還原，否則不得整檔重寫
    if json.dumps(data, ensure_ascii=False, indent=1) != raw:
        print("❌ snapshot.json 無法以 indent=1 無損 round-trip → 中止（不得整檔重排）")
        return 3

    _known = set(ALLOWED_EXTRA) | {"application_status", "approval_status", "source", "updated_at"}
    old = data.get(KEY)
    bad = [k for k in (old or {}) if (k not in _known) or (k in DERIVED_KEYS)]
    if bad:
        print(f"⚠️ 既有記錄含衍生／未知欄位，將移除：{bad}")

    rec = {k: v for k, v in (old or {}).items() if k not in DERIVED_KEYS}
    rec["application_status"] = a.application_status
    rec["approval_status"] = a.approval_status
    if a.note:
        rec["note"] = a.note
    rec["source"] = a.source
    rec["updated_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    data[KEY] = rec

    print(f"=== PI 唯一寫入者{'（DRY-RUN）' if a.dry_run else ''} ===")
    print(f"  舊：{json.dumps(old, ensure_ascii=False) if old else '（不存在）'}")
    print(f"  新：{json.dumps(rec, ensure_ascii=False)}")
    proxy = sot.pi_financial_asset_proxy(data)
    thr = sot.pi_regulatory_threshold()
    print(f"  財力軌（即時計算、不落地）：proxy {proxy:,.0f} ／ 門檻 {thr:,}"
          f"｜缺口 {max(0, thr - proxy):,.0f}｜{'達標' if proxy >= thr else '未達'}")
    print(f"  資格軌：{'🔓 解鎖' if rec['approval_status'] == '已核准' else '🔒 鎖定'}（僅 approval_status=已核准 可解鎖）")

    if a.dry_run:
        print("  [dry-run] 未寫入任何檔案")
        return 0

    bak = SNAP_PATH.with_name(SNAP_PATH.name + ".bak-pi-" + dt.datetime.now().strftime("%Y%m%d%H%M%S"))
    shutil.copy2(SNAP_PATH, bak)

    new_txt = json.dumps(data, ensure_ascii=False, indent=1)
    SNAP_PATH.write_text(new_txt, encoding="utf-8")

    # 三重驗證：①目標鍵正確 ②其他鍵逐鍵不變 ③檔案可被重新解析
    chk = json.loads(SNAP_PATH.read_text(encoding="utf-8"))
    assert chk[KEY] == rec, "目標鍵寫入不符"
    diff = [k for k in set(chk) | set(json.loads(raw)) if chk.get(k) != json.loads(raw).get(k)]
    if diff != [KEY]:
        shutil.copy2(bak, SNAP_PATH)
        print(f"❌ 驗證失敗：非目標鍵被改動 {diff} → 已還原；備份 {bak.name}")
        return 4
    print(f"  ✅ 已寫入（三重驗證通過：目標鍵正確／其他鍵不變／可重新解析）；備份 {bak.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
