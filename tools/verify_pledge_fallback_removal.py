#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/verify_pledge_fallback_removal.py — PEND-20261004-02 驗收器

驗的是「舊數字可以救場」是否真的改成「沒有真值就停」，不是驗字串存在。

測項：
  S1 靜態（AST）：run_daily.py 不再有 _dp2／_pool_principal／_pledge_pct 這些識別字，
                 且不再有 `if _pi:`（以 Name('_pi') 當 If 條件）
  S2 accessor 反向：mortgage_principal_cathay 有真值 → 回真值
  S3 accessor 語意邊界：缺鍵／空字串／None／非數值 → None；**明確 0 → 0.0**（真的沒有房貸）
  S4 pledge_truth_present 三態：完整→True；缺 fund_pledge_loan→False；擔保池 0→False
  S5 E2E 真值渲染：卡片含真值三件套；不含舊推導字樣
  S6 E2E 缺值 fail-closed：移除 mortgage_cathay／利率來源 → 卡片不得出現 1,200 萬估算，須顯示缺真值
  S7 E2E PI 缺值：無有效 PI record → 槓桿風控區塊不渲染，且**明示原因**（不靜默）
  S8 E2E 反向：真值改值 → 卡片跟著改（證明讀真值而非常量）
  S9 反恆真：本檔（測試）與 run_daily.py（生產）不得有恆真斷言字面

斷言範圍說明：S5/S6/S8 只掃「槓桿風控輸出＋質押口徑卡」區段，不掃整份報告——
整份報告本來就會在別的卡片出現 12,000,000，掃整份會製造假陽性。
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

_RESULTS: list[tuple[str, bool, str]] = []


def chk(name: str, ok: bool, detail: str = "") -> None:
    _RESULTS.append((name, bool(ok), detail))
    print(("✅ " if ok else "❌ ") + name + (f"｜{detail}" if detail else ""))


def _card(html: str) -> str:
    """只取「槓桿風控輸出」到「市場指標燈號面板」之間的區段（本次修改的兩張卡）。"""
    i = html.find("槓桿風控輸出")
    if i < 0:
        return ""
    j = html.find("市場指標燈號面板", i)
    return html[i:j if j > i else i + 3000]


def _render(tv: dict, snap_override: Path | None = None) -> tuple[str, str]:
    """回傳 (html, stdout)。snap_override：把 run_daily.SNAPSHOT 暫時指向別的檔案。"""
    import run_daily as R  # noqa
    _bak = R.SNAPSHOT
    if snap_override is not None:
        R.SNAPSHOT = snap_override
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            html = R._inject_market_intel("<div></div>", tv, {})
    finally:
        R.SNAPSHOT = _bak
    return html, buf.getvalue()


def main() -> int:
    real_snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))

    # ── S1 靜態 AST ─────────────────────────────────────────────────────────
    src = (BASE / "run_daily.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    banned = sorted(n for n in ("_dp2", "_pool_principal", "_pledge_pct") if n in names)
    if_tests = {t.id for n in ast.walk(tree) if isinstance(n, ast.If)
                for t in [n.test] if isinstance(t, ast.Name)}
    chk("S1 靜態：舊識別字與 `if _pi:` gating 已從程式碼本體移除",
        not banned and "_pi" not in if_tests,
        f"殘留識別字={banned}｜If 條件含 _pi={'_pi' in if_tests}")

    # ── S2/S3 房貸本金 accessor ─────────────────────────────────────────────
    import sot_targets as st
    v_ok = st.mortgage_principal_cathay({"mortgage_cathay": 12000000})
    miss_vals = [st.mortgage_principal_cathay(d) for d in
                 ({}, {"mortgage_cathay": ""}, {"mortgage_cathay": None},
                  {"mortgage_cathay": "abc"})]
    v_zero = st.mortgage_principal_cathay({"mortgage_cathay": 0})
    chk("S2 accessor 反向：有真值時回真值", v_ok == 12000000.0, f"got={v_ok}")
    chk("S3 accessor 語意邊界：缺鍵/空/None/非數值 → None；明確 0 → 0.0",
        all(b is None for b in miss_vals) and v_zero == 0.0,
        f"缺值組={miss_vals}｜明確0={v_zero}")

    # ── S4 質押真值存在性 ───────────────────────────────────────────────────
    t_full = st.pledge_truth_present(real_snap)
    t_miss = st.pledge_truth_present({k: v for k, v in real_snap.items() if k != "fund_pledge_loan"})
    _z = json.loads(json.dumps(real_snap))
    _z["cathay_pledge_0911"] = dict(_z.get("cathay_pledge_0911") or {})
    _z["cathay_pledge_0911"]["擔保池"] = {"合計": 0}
    _z.pop("funds_cathay_market_value", None)
    t_zero = st.pledge_truth_present(_z)
    chk("S4 pledge_truth_present 三態（完整 True／缺鍵 False／池 0 False）",
        t_full and not t_miss and not t_zero, f"full={t_full} miss={t_miss} zero={t_zero}")

    # ── S5 E2E 真值渲染（限卡片區段）────────────────────────────────────────
    html, _ = _render(real_snap)
    card5 = _card(html)
    must = ["質押品市值 11,779,326", "實際動用 5,900,000", "2.65%", "LTV 50.1%",
            "銀行核定授信額度：未取得", "13,029/月", "1200萬"]
    must_not = ["額度計算", "19,273", "❺", "餘 ", "富達600＋聯博100", "可貸 5,900,000"]
    miss = [k for k in must if k not in card5]
    bad = [k for k in must_not if k in card5]
    chk("S5 E2E（真值）：卡片含真值三件套與 SoT 月息，且無舊推導字樣",
        bool(card5) and not miss and not bad, f"區段長={len(card5)}｜缺={miss}｜殘留={bad}")

    # ── S6 E2E 缺值 fail-closed（限卡片區段）────────────────────────────────
    tmpd = Path(tempfile.mkdtemp(prefix="lj_p0_"))
    try:
        d = json.loads(json.dumps(real_snap))
        d.pop("mortgage_cathay", None)
        d.pop("mortgage_cathay_rate", None)
        (d.get("monthly_fixed_expense") or {}).pop("房貸_國泰", None)
        sp = tmpd / "snapshot_nokey.json"
        sp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        h6, out6 = _render(real_snap, snap_override=sp)
        card6 = _card(h6)
        no_fake = ("1200萬" not in card6) and ("12,000,000" not in card6)
        said = ("缺真值" in card6) or ("缺真值" in out6)
        chk("S6 E2E（缺值）：卡片不得以常量補出 1,200 萬，且必須明示缺真值",
            bool(card6) and no_fake and said,
            f"無假121200萬={no_fake}｜有明示={said}")
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)

    # ── S7 E2E PI 缺值 → 不渲染 + 明示 ──────────────────────────────────────
    tv_nopi = {k: v for k, v in real_snap.items() if k != "professional_investor"}
    h7, out7 = _render(tv_nopi)
    chk("S7 E2E（PI 缺值）：槓桿風控區塊不渲染，且明示略過原因（不靜默）",
        ("槓桿風控輸出" not in h7) and ("PI 無有效真值" in out7),
        f"區塊在={('槓桿風控輸出' in h7)}｜訊息在={('PI 無有效真值' in out7)}")

    # ── S8 E2E 反向：真值改值 → 卡片跟著改（限卡片區段）──────────────────────
    tmpd2 = Path(tempfile.mkdtemp(prefix="lj_p0b_"))
    try:
        d2 = json.loads(json.dumps(real_snap))
        d2["mortgage_cathay"] = 9999999
        sp2 = tmpd2 / "snapshot_alt.json"
        sp2.write_text(json.dumps(d2, ensure_ascii=False), encoding="utf-8")
        h8, _ = _render(real_snap, snap_override=sp2)
        card8 = _card(h8)
        chk("S8 E2E（反向）：房貸本金真值改變 → 卡片跟著改變（非常量）",
            ("1000萬" in card8) and ("1200萬" not in card8),
            f"含1000萬={('1000萬' in card8)}｜仍含1200萬={('1200萬' in card8)}")
    finally:
        shutil.rmtree(tmpd2, ignore_errors=True)

    # ── S9 反恆真（測試檔掃全部樣式；生產檔只掃恆真斷言）────────────────────
    SELF_BANNED = ["or" + " True", "assert" + " True", "or" + " 1"]
    PROD_BANNED = ["or" + " True", "assert" + " True"]
    self_src = Path(__file__).read_text(encoding="utf-8")
    hits = ([b for b in SELF_BANNED if b in self_src]
            + [f"run_daily.py:{b}" for b in PROD_BANNED if b in src])
    chk("S9 反恆真（測試檔全樣式；生產檔恆真斷言）", not hits, f"命中={hits}")

    print("=" * 56)
    _p = sum(1 for _, ok, _ in _RESULTS if ok)
    print(f"PEND-20261004-02 驗收｜合計 {len(_RESULTS)} 項｜PASS {_p}｜FAIL {len(_RESULTS) - _p}")
    print("=" * 56)
    return 0 if _p == len(_RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
