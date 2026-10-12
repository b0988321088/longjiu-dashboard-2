# -*- coding: utf-8 -*-
"""tests/test_public_exposure.py — 公開產物敏感項守門（2026-10-12 資安處置）

使用者裁決：保留憑證、不撤銷；優先清理公開資料（帳號、銀行餘額、資產分母）。
本測試＝「已經公開的檔案不得再出現這三類」的回歸守門；新產物由產生端 public_mask 保證。
"""
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import public_mask as pm  # noqa: E402

PASS = FAIL = 0
def ck(label, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✅ {label}")
    else: FAIL += 1; print(f"  ❌ {label} {detail}")

PUBLIC = ["index.html", "daily_report_v2_2026-10-12.html", "radar_state.json",
          "rebalance_dashboard_2026-10-12.html", "asset_diff_2026-10-12.html"]
PATTERNS = {"帳號識別碼": r"\b\d{3}\*{2,}\d{2,4}\b", "長帳號": r"\b\d{3}-\d{10,}\b",
            "安全線門檻": r"安全線：\s*[0-9,]{4,}"}

print("=== 公開產物敏感項守門 ===")
for f in PUBLIC:
    p = BASE / f
    if not p.exists():
        ck(f"{f} 存在", False, "缺檔"); continue
    t = p.read_text(encoding="utf-8", errors="replace")
    for name, pat in PATTERNS.items():
        m = re.search(pat, t)
        ck(f"{f}｜{name} 已清除", m is None, m.group(0) if m else "")
print("② radar 資產分母")
rz = json.loads((BASE / "radar_state.json").read_text(encoding="utf-8")) if (BASE / "radar_state.json").exists() else {}
fed_abs = [k for k in ("fed", "data") if isinstance(rz.get(k), dict) and "total_assets" in (rz.get(k) or {}).get("fed", {})]
ck("radar_state.json 不含 total_assets（含巢狀 data.fed）", not fed_abs, str(fed_abs))
print("③ 產生端確有套用遮蔽（防未來重產復發）")
for f in ("build_dashboard.py", "institutional_flow.py", "run_daily.py", "regenerate_report.py"):
    s = (BASE / f).read_text(encoding="utf-8", errors="replace")
    ck(f"{f} 已接防線", ("public_mask" in s) if f != "institutional_flow.py" else ("不得落地 Fed 總資產" in s), "")
print(f"\n== 結果：{PASS} PASS / {FAIL} FAIL ==")
sys.exit(1 if FAIL else 0)
