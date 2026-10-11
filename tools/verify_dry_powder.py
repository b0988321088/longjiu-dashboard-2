# -*- coding: utf-8 -*-
"""verify_dry_powder.py — 乾粉／現金缺口口徑回歸測試（工單A，唯讀、無副作用）

背景（2026-10-11 一次性工單 A）：乾粉＝可動用現金 − 現金底線，**可為負**（短少）。
舊寫法三處各自 `max(0, …)` 夾成 0，再用 `dry or 舊值` 回退到
`snapshot.乾粉執行_0926.戰術乾粉總額.當前`（2026-09-29 的 119,182）→ 週報／eval 同時
出現「乾粉 119,182（現金 639,661 − 生活底線 700,000）」與「短少 60,339」。

本測試鎖住四件事：
  1. 邊界 699,999／700,000／700,001（含 0 必須是「乾粉 0」而不是「短少 0」）
  2. 10/11 真值回歸：乾粉 = −60,339，且**舊值 119,182 不得出現在任何輸出**
  3. 缺值 fail-closed（不得以 0 冒充）、跨源不一致要標記
  4. 靜態：三個消費端不得再出現舊值回退樣式

用法：python tools/verify_dry_powder.py   （全過 exit 0；任一失敗 exit 1）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import sot_targets as st   # noqa: E402

FAILS: list[str] = []


def rec(tag: str, desc: str, ok: bool, detail: str = "") -> None:
    print(("  ✅ " if ok else "  ❌ ") + f"{tag} {desc}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(tag)


def snap(cash=639661, floor=700000, restricted=0, stale=None, cl_avail=None) -> dict:
    """最小可測 snapshot（**完全隔離**：restricted_cash 一律顯式給，預設 0）。

    ⚠️ 陷阱：sot_targets.restricted_cash(snap) 在傳入 dict 缺 `restricted_cash` 時會**回退讀
    磁碟上的 snapshot.json**（單一真值設計）。測試若不顯式給值，會拿到真實 900,000 →
    邊界案例全部算錯（本測試首版即踩到）。
    """
    s = {
        "cash_total": cash,
        "restricted_cash": {"金額": restricted, "用途": "清償質押（測試）"},
        "cash_floor_rule": {"cash_floor": floor, "rule": "test"},
        "thresholds_2026_0915": {"現金_twd": {"生活底線": floor, "追繳緩衝": 0, "合計底線": floor}},
    }
    if stale is not None:
        s["乾粉執行_0926"] = {"戰術乾粉總額": {"當前": stale, "說明": "9/29 舊值（測試用）"}}
    if cl_avail is not None:
        s["cash_layers"] = {"unrestricted_cash": cl_avail}
    return s


print("== 1. 邊界（可動用 vs 底線）==")
for avail, exp_dry, exp_txt in ((699999, -1, "短少 1"), (700000, 0, "乾粉 0"), (700001, 1, "乾粉 1")):
    d = st.dry_powder(snap(cash=avail))
    rec(f"A-{avail}", f"乾粉={exp_dry}／顯示「{exp_txt}」",
        d["dry"] == exp_dry and st.dry_display(d) == exp_txt,
        f"dry={d['dry']} status={d['status']} 顯示={st.dry_display(d)}")

print("\n== 2. 10/11 真值回歸（舊值 119,182 不得出現）==")
_s = snap(cash=1539661, restricted=900000, stale=119182, cl_avail=639661)
d = st.dry_powder(_s)
rec("B-1", "乾粉 = −60,339（可動用 639,661 − 底線 700,000）",
    d["dry"] == -60339, f"available={d['available']:.0f} floor={d['floor']:.0f} dry={d['dry']}")
rec("B-2", "短少 = 60,339、狀態＝短少", d["shortfall"] == 60339 and d["status"] == "短少",
    f"shortfall={d['shortfall']} status={d['status']}")
_txt = " ".join([st.dry_display(d), st.dry_display(d, "wan")])
rec("B-3", "顯示字串不含舊值 119,182／11.9萬",
    ("119,182" not in _txt) and ("11.9" not in _txt) and ("短少" in _txt), f"顯示={_txt}")
rec("B-4", "長期目標 1,000,000 僅標示、不與硬底線混用",
    d["long_term_goal"] == 1000000 and d["floor"] == 700000,
    f"floor={d['floor']:.0f} long_term_goal={d['long_term_goal']}")
rec("B-5", "跨源一致（cash_layers.unrestricted_cash 相符）→ 無標記",
    d["cross_source_ok"] is True, f"cross_source_gap={d['cross_source_gap']}")

print("\n== 3. 缺值 fail-closed ==")
for tag, bad, why in (
    ("C-1", {"cash_total": "無值", "cash_floor_rule": {"cash_floor": 700000},
             "restricted_cash": {"金額": 0}}, "cash 非數值"),
    ("C-2", {"cash_floor_rule": {"cash_floor": 700000}}, "缺現金鍵"),
    ("C-3", {"cash_total": 100000, "restricted_cash": {"金額": 0}}, "缺底線鍵"),
):
    try:
        _r = st.dry_powder(bad)
        rec(tag, f"{why} → 須 raise（不得以 0 冒充）", False, f"未 raise，回傳 dry={_r['dry']}")
    except Exception as e:                                                    # noqa: BLE001
        rec(tag, f"{why} → raise", True, type(e).__name__)

print("\n== 4. 跨源不一致要標記（不靜默選一個）==")
d2 = st.dry_powder(snap(cash=1539661, restricted=900000, cl_avail=700000))
rec("D-1", "cash_layers.unrestricted_cash 與本函式口徑差 60,339 → 標記不一致",
    d2["cross_source_ok"] is False and d2["cross_source_gap"] == -60339,
    f"gap={d2['cross_source_gap']}")

print("\n== 5. 靜態：消費端不得再回退舊值 ==")
_targets = ["institutional_flow.py", "build_dashboard.py", "build_rebalance_dashboard.py"]
_stale_pat = re.compile(r'乾粉執行_0926[^\n]*\.get\("當前"')
for f in _targets:
    t = (BASE / f).read_text(encoding="utf-8")
    rec(f"E-{f}", "無『乾粉 = max(0,…) 後回退舊值』樣式",
        not _stale_pat.search(t) and 'get("當前", 0)' not in t)
rec("E-sot", "sot_targets.dry_powder 為乾粉唯一入口（有 dry／shortfall／cross_source）",
    all(k in st.dry_powder(snap()).keys() for k in ("dry", "shortfall", "status", "cross_source_ok")))
rec("E-closure", "分層閉合不變式仍成立（底線內＋乾粉＝可動用）",
    (lambda cl: cl["emergency_cash"]["金額"] + cl["dry_powder"] == cl["unrestricted_cash"])(
        st.cash_layers(snap())))

print("\n=== 結果：" + ("PASS（FAIL 0）" if not FAILS else f"FAIL（{len(FAILS)}）：" + "、".join(FAILS)) + " ===")
sys.exit(1 if FAILS else 0)
