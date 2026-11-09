#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_penetration_gates.py — 穿透口徑閘門測試（2026-11-09 裁決 A+C）

驗收目標（使用者規格）：
  1. 正常資料 → 閘門 1／2 全 PASS、rc=0
  2. 人為注入錯誤分母 → 閘門 1 FAIL、rc≠0
  3. 人為注入資產不平衡 → 閘門 2 FAIL、rc≠0
  4. 缺少分母宣告 → 閘門 1 FAIL、rc≠0

作法是複製 snapshot 到暫存檔、就地注入，再用 --snapshot 餵給
check_penetration_consistency.py；**不觸碰 repo 內 snapshot.json**。

用法：python tests/test_penetration_gates.py
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CHECKER = BASE / "check_penetration_consistency.py"
DATE = sys.argv[1] if len(sys.argv) > 1 else None


def _run(snap_obj):
    d = Path(tempfile.mkdtemp(prefix="pen_gate_"))
    p = d / "snapshot.json"
    p.write_text(json.dumps(snap_obj, ensure_ascii=False), encoding="utf-8")
    args = [sys.executable, str(CHECKER)]
    if DATE:
        args.append(DATE)
    args += ["--snapshot", str(p)]
    r = subprocess.run(args, cwd=str(BASE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    g1 = "閘門1" in out and "✅ PASS" in [l for l in out.splitlines() if "閘門1" in l][0]
    g2 = "閘門2" in out and "✅ PASS" in [l for l in out.splitlines() if "閘門2" in l][0]
    return r.returncode, g1, g2, out


def main() -> int:
    src = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    pen = src.get("penetration") or {}
    ta = int(float(pen.get("pct_denominator") or src.get("total_assets") or 0))
    rst = int(float(pen.get("restricted_cash") or 0))
    den_def = ta - rst

    cases = []

    def add(name, mutate, expect_rc, expect_g1, expect_g2):
        d = copy.deepcopy(src)
        mutate(d)
        cases.append((name, d, expect_rc, expect_g1, expect_g2))

    add("正常資料（母體）", lambda d: None, 0, True, True)
    add(f"注入錯分母 {den_def:,}（誤用防禦維度分母）",
        lambda d: d["penetration"].__setitem__("pct_denominator", den_def), 1, False, True)
    add("注入資產不平衡（現金桶 +5,000）",
        lambda d: d["penetration"]["actual_twd"].__setitem__(
            "現金/安全網", d["penetration"]["actual_twd"]["現金/安全網"] + 5000), 1, True, False)
    add("缺少分母宣告",
        lambda d: d["penetration"].pop("pct_denominator", None), 1, False, True)

    fails = 0
    print(f"🧪 穿透口徑閘門測試（{len(cases)} 案例，snapshot 總資產 {ta:,}）")
    for name, d, e_rc, e_g1, e_g2 in cases:
        rc, g1, g2, out = _run(d)
        ok = (rc == e_rc) and (g1 is e_g1) and (g2 is e_g2)
        print(f"  {'✅' if ok else '❌'} {name}：rc={rc}(預期{e_rc}) G1={g1} G2={g2}")
        if not ok:
            fails += 1
            print("     " + " / ".join(l.strip() for l in out.splitlines()
                                       if l.strip().startswith("•") or "閘門" in l)[:400])
    print(f"\n{'✅ 全部通過' if not fails else f'❌ {fails} 個案例失敗'}（{len(cases) - fails}/{len(cases)}）")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
