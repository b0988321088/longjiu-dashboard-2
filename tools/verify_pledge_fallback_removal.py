#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/verify_pledge_fallback_removal.py — PEND-20261004-02 驗收器

驗的是「舊數字可以救場」是否真的改成「沒有真值就停」，不是驗字串存在。

測項：
  S1  靜態（AST）：run_daily.py 不再有 _dp2／_pool_principal／_pledge_pct 這些識別字，
                  且不再有 `if _pi:`（以 Name('_pi') 當 If 條件）
  S2  accessor 反向：mortgage_principal_cathay 有真值 → 回真值
  S3  accessor 語意邊界：缺鍵／空字串／None／非數值 → None；**明確 0 → 0.0**（真的沒有房貸）
  S4  pledge_truth_present 三態：完整→True；缺 fund_pledge_loan→False；擔保池 0→False
  S5  E2E 真值渲染：卡片含真值三件套；不含舊推導字樣
  S6  E2E 缺值 fail-closed：移除 mortgage_cathay／利率來源 → 卡片不得出現 1,200 萬估算
      （含逗號型 1,200萬——CIO 指出原版只比對無逗號字串會假陰性），須顯示缺真值
  S7  E2E PI 缺值：無有效 PI record → 槓桿風控區塊不渲染，且**明示原因**（不靜默）
  S8  E2E 反向：真值改值 → 卡片跟著改（證明讀真值而非常量）
  S9  反恆真：本檔（測試）與 run_daily.py（生產）不得有恆真斷言字面
  S10 靜態（AST）：`_cg_wan` 與 `CATHAY_MORTGAGE_RATE_FALLBACK` 已從程式碼本體移除
      （兩者都是「舊數字救場」：前者硬編碼 "1,200"，後者常量 0.026）
  S11 E2E 同鏈第二消費者（負債明細表／國泰房貸）：利率缺真值 → 不得印派生假月付
  S12 E2E 同鏈第二消費者（負債明細表／基金質押）：利率或池市值缺真值 → 不得印 2.65%／不得靜默省略
  S13 靜態：`tv.get('fund_pledge_rate') or <常量>` 型式不得復辟

斷言範圍說明：S5/S6/S8 只掃「槓桿風控輸出＋質押口徑卡」區段，不掃整份報告——
整份報告本來就會在別的卡片出現 12,000,000，掃整份會製造假陽性。
S11/S12 反過來只掃「負債明細表」的那兩列。
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import re
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


def _row(html: str, needle: str) -> str:
    """取出含 needle 的那一個 <tr>…</tr>。"""
    for m in re.finditer(r"<tr>.*?</tr>", html, flags=re.S):
        if needle in m.group(0):
            return m.group(0)
    return ""


def _block(html: str, needle: str) -> str:
    """取出含 needle 的那一個區塊（到最近的 </div> 為止）。"""
    i = html.find(needle)
    if i < 0:
        return ""
    j = html.find("</div>", i)
    return html[i:j if j > i else i + 800]


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


def _render_liab(snap_override: Path | None = None,
                 mutate: dict | None = None) -> tuple[str, str]:
    """渲染整份日報（負債明細表在 render_daily_report，不在 _inject_market_intel）。

    tv 由 run_daily.calibrate_sources()（唯讀，只讀三源回傳 dict）產生；
    mutate 用於針對性改鍵（例如把 fund_pledge_rate 設 None）。
    """
    import run_daily as R  # noqa
    _bak = R.SNAPSHOT
    if snap_override is not None:
        R.SNAPSHOT = snap_override
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            tv_liab = dict(R.calibrate_sources())
            # render_daily_report 需要 main() 才補齊的鍵（證券/配息）。本測試只關心負債明細表，
            # 其餘鍵以中性 stub 補齊，避免為了測兩列而重跑整條 main()。
            _stubs = {
                "holdings_count": 0,
                "holdings_top3": [("—", 0.0), ("—", 0.0), ("—", 0.0)],
                "holdings": [],
            }
            for _k, _v in _stubs.items():
                tv_liab.setdefault(_k, _v)
            if mutate:
                tv_liab.update(mutate)
            for _try in range(80):
                try:
                    html = R.render_daily_report(tv_liab)
                    break
                except KeyError as _ke:
                    _k = _ke.args[0]
                    if _k in tv_liab:
                        raise
                    tv_liab[_k] = _stubs.get(_k, 0)
            else:
                raise RuntimeError("render_daily_report 補鍵 80 次仍未收斂（stub 不足）")
    finally:
        R.SNAPSHOT = _bak
    return html, buf.getvalue()


def _dump(obj: dict, path: Path) -> Path:
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


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
        sp = _dump(d, tmpd / "snapshot_nokey.json")
        h6, out6 = _render(real_snap, snap_override=sp)
        card6 = _card(h6)
        # CIO 指出的假陰性：原版只比對無逗號 '1200萬'，④ 行的逗號型 '1,200萬' 會漏網。
        no_fake = all(x not in card6 for x in
                      ("1200萬", "1,200萬", "12,000,000", "1,200"))
        said = ("缺真值" in card6) or ("缺真值" in out6)
        chk("S6 E2E（缺值）：卡片不得以常量補出 1,200 萬（含逗號型），且必須明示缺真值",
            bool(card6) and no_fake and said,
            f"無假1200萬={no_fake}｜有明示={said}")

        # 檔 B：只缺「利率來源」（本金仍在）→ 測負債明細表的同鏈第二消費者
        d_b = json.loads(json.dumps(real_snap))
        d_b.pop("mortgage_cathay_rate", None)
        (d_b.get("monthly_fixed_expense") or {}).pop("房貸_國泰", None)
        sp_b = _dump(d_b, tmpd / "snapshot_norate.json")
        h11, out11 = _render_liab(snap_override=sp_b)
        row11 = _row(h11, "國泰房貸")
        fake_pay = bool(row11) and ("月付" in row11) and ("2.6%" in row11)
        chk("S11 E2E（缺值／負債明細表）：國泰房貸利率缺真值 → 不印利率、不由假利率派生月付",
            bool(row11) and (not fake_pay) and ("缺真值" in row11),
            f"列={row11[:130]!r}｜假月付={fake_pay}")

        # 正向對照：確保 S11 不是因為「那一列根本沒渲染」而假通過
        h11r, _ = _render_liab()
        row11r = _row(h11r, "國泰房貸")
        chk("S11b 正向對照：利率真值存在時該列正常顯示利率與月付（S11 非假通過）",
            ("2.6%" in row11r) and ("月付" in row11r), f"列={row11r[:130]!r}")
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)

    # ── S12 同鏈第二消費者：負債明細表／基金質押（pledge chain 本身）────────
    h12, out12 = _render_liab(mutate={"fund_pledge_loan": 5900000,
                                      "fund_pledge_rate": None,
                                      "fund_pledge_pool": None})
    row12 = _row(h12, "基金質押")
    h12r, _ = _render_liab()
    row12r = _row(h12r, "基金質押")
    chk("S12 E2E（缺值／負債明細表）：基金質押利率或池市值缺真值 → 不印 2.65%、不靜默省略"
        "（含正向對照：真值在時須印得出 2.65%）",
        bool(row12) and ("2.65%" not in row12) and ("缺真值" in row12)
        and ("2.65%" in row12r),
        f"缺值列={row12[:130]!r}｜真值列={row12r[:130]!r}")

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
        sp2 = _dump(d2, tmpd2 / "snapshot_alt.json")
        h8, _ = _render(real_snap, snap_override=sp2)
        card8 = _card(h8)
        chk("S8 E2E（反向）：房貸本金真值改變 → 卡片跟著改變（非常量）",
            ("1000萬" in card8) and ("1200萬" not in card8) and ("1,200萬" not in card8),
            f"含1000萬={('1000萬' in card8)}｜仍含1200萬={('1200萬' in card8 or '1,200萬' in card8)}")
    finally:
        shutil.rmtree(tmpd2, ignore_errors=True)

    # ── S10 靜態：舊數字救場的兩個載體都移除 ────────────────────────────────
    dead = sorted(n for n in ("_cg_wan", "CATHAY_MORTGAGE_RATE_FALLBACK") if n in names)
    chk("S10 靜態：`_cg_wan`（硬編碼 \"1,200\"）與 `CATHAY_MORTGAGE_RATE_FALLBACK`（常量 0.026）"
        "已從程式碼本體移除",
        not dead, f"殘留={dead}")

    # ── S13 靜態：`... or <常量利率>` 型式不得復辟 ──────────────────────────
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    pats = ["fund_pledge_rate') " + "or 0", "fund_pledge_pool') " + "or 0",
            "fund_pledge_rate') " + "or 0.0265", "or" + " 12000000"]
    hit13 = [p for p in pats if p in body]
    chk("S13 靜態：`tv.get('fund_pledge_rate')` 搭配常量、以及 12,000,000 常量 fallback 型式不得復辟",
        not hit13, f"命中={hit13}")

    # ── S14 每月固定支出明細 fail-closed（CIO 二審必改1）──────────────────
    tmpd3 = Path(tempfile.mkdtemp(prefix="lj_p0c_"))
    try:
        d3 = json.loads(json.dumps(real_snap))
        _m = dict(d3.get("monthly_fixed_expense") or {})
        for _k in ("生活支出", "醫療_常態回診", "房貸_永豐", "房貸_國泰", "合計"):
            _m.pop(_k, None)
        d3["monthly_fixed_expense"] = _m
        sp3 = _dump(d3, tmpd3 / "snapshot_nomfe.json")
        h14, _ = _render_liab(snap_override=sp3)
        blk = _block(h14, "📌 每月固定支出")
        stale = [x for x in ("28,500", "65,735", "26,000", "15,946") if x in blk]
        chk("S14 E2E（缺值／每月固定支出明細）：不得以舊常數"
            "（生活 28,500／永豐 65,735／國泰 26,000／醫療 15,946）救場",
            bool(blk) and not stale and ("缺真值" in blk),
            f"殘留舊常數={stale}｜明示={('缺真值' in blk)}")
        h14r, _ = _render_liab()
        blk14r = _block(h14r, "📌 每月固定支出")
        chk("S14b 正向對照：真值存在時顯示真值（生活 38,500＋房貸 91,735＋合計 159,210）",
            all(x in blk14r for x in ("38,500", "65,735", "26,000", "91,735", "159,210")),
            f"區塊={blk14r[:170]!r}")
    finally:
        shutil.rmtree(tmpd3, ignore_errors=True)

    # ── S15 資產總表：常態房租／保守配息 fail-closed ────────────────────────
    h15, _ = _render_liab(mutate={"rent_monthly_target": None,
                                  "dividend_month_expected": None})
    i15 = h15.find("被動月收")
    seg15 = h15[i15:i15 + 700] if i15 >= 0 else ""
    chk("S15 E2E（缺值／資產總表）：rent_monthly_target／dividend_month_expected 缺"
        " → 不得以 80,100／100,000 救場",
        bool(seg15) and ("⚠️ 缺真值" in seg15)
        and ("80,100" not in seg15) and ("100,000" not in seg15),
        f"段={seg15[:170]!r}")

    # ── S16 卡片③：常態配息缺 → 覆蓋不得亮綠燈 ─────────────────────────────
    tv_k = {k: v for k, v in real_snap.items() if k != "dividend_month_expected"}
    h16, _ = _render(tv_k)
    card16 = _card(h16)
    i16 = card16.find("③ 月度利息流出")
    seg16 = card16[i16:i16 + 160] if i16 >= 0 else ""
    chk("S16 E2E（缺值／卡片③）：dividend_month_expected 缺 → 覆蓋判斷不得亮綠燈",
        bool(card16) and ("✅ 覆蓋" not in card16) and ("不予判斷" in seg16),
        f"③={seg16!r}")

    # ── S17 卡片③：富達月配缺 → 覆蓋不得亮綠燈 ─────────────────────────────
    tv_f = json.loads(json.dumps(real_snap))
    _ctg17 = (tv_f.get("funds_breakdown", {}) or {}).get("國泰直購", {}) or {}
    tv_f["funds_breakdown"] = dict(tv_f.get("funds_breakdown") or {})
    tv_f["funds_breakdown"]["國泰直購"] = {k: v for k, v in _ctg17.items()
                                            if "富達" not in str(k)}
    h17, _ = _render(tv_f)
    card17 = _card(h17)
    i17 = card17.find("③ 月度利息流出")
    seg17 = card17[i17:i17 + 175] if i17 >= 0 else ""
    chk("S17 E2E（缺值／卡片③）：富達月配缺（國泰直購 無「富達」鍵）→ 覆蓋判斷不得亮綠燈",
        bool(card17) and ("✅ 覆蓋" not in card17) and ("不予判斷" in seg17),
        f"③={seg17!r}")

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
