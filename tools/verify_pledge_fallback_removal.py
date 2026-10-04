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


def _render_card_live(snap_override: Path | None = None) -> tuple[str, str]:
    """槓桿風控卡（實際在 run_daily._inject_market_intel 內）——**tv 由 calibrate_sources() 產生**。

    2026-10-04 CIO 三審必改6：S15/S16 原本以 raw snapshot 直接當 tv 傳入，
    繞過 calibrate_sources 的 producer 端 default（L271／L298）→ 測不到真值缺鍵的實際行為
    （假信心）。此 helper 一律走「snapshot 檔移除鍵 → calibrate_sources() → 渲染」的真管線。
    """
    import run_daily as R  # noqa
    _bak = R.SNAPSHOT
    if snap_override is not None:
        R.SNAPSHOT = snap_override
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            tv = dict(R.calibrate_sources())
            _stubs = {
                "holdings_count": 0,
                "holdings_top3": [("—", 0.0), ("—", 0.0), ("—", 0.0)],
                "holdings": [],
            }
            for _k, _v in _stubs.items():
                tv.setdefault(_k, _v)
            for _try in range(80):
                try:
                    html = R._inject_market_intel("<div></div>", tv, {})
                    break
                except KeyError as _ke:
                    _k = _ke.args[0]
                    if _k in tv:
                        raise
                    tv[_k] = _stubs.get(_k, 0)
            else:
                raise RuntimeError("_inject_market_intel 補鍵 80 次仍未收斂（stub 不足）")
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

    # ── S15 資產總表：常態房租／保守配息 fail-closed（2026-10-04 CIO 三審必改6：
    #    改走「snapshot 檔移除鍵 → calibrate_sources()」真管線，不再用 mutate 注入 tv）──
    tmpd5 = Path(tempfile.mkdtemp(prefix="lj_p0e_"))
    try:
        d15 = json.loads(json.dumps(real_snap))
        d15.pop("rent_monthly_total", None)
        d15.pop("dividend_month_expected", None)
        sp15 = _dump(d15, tmpd5 / "snapshot_no_rent_dme.json")
        h15, _ = _render_liab(snap_override=sp15)
        i15 = h15.find("被動月收")
        seg15 = h15[i15:i15 + 700] if i15 >= 0 else ""
        chk("S15 E2E（缺值／資產總表）：rent_monthly_total／dividend_month_expected 缺"
            " → 不得以 80,100／100,000 救場",
            bool(seg15) and ("⚠️ 缺真值" in seg15)
            and ("80,100" not in seg15) and ("100,000" not in seg15),
            f"段={seg15[:170]!r}")

        # ── S16 卡片③：常態配息缺 → 覆蓋不得亮綠燈（真管線）───────────────────
        d16 = json.loads(json.dumps(real_snap))
        d16.pop("dividend_month_expected", None)
        sp16 = _dump(d16, tmpd5 / "snapshot_no_dme_card.json")
        h16, _ = _render_card_live(snap_override=sp16)
        card16 = _card(h16)
        i16 = card16.find("③ 月度利息流出")
        seg16 = card16[i16:i16 + 160] if i16 >= 0 else ""
        chk("S16 E2E（缺值／卡片③／經 calibrate_sources）：dividend_month_expected 缺"
            " → 覆蓋判斷不得亮綠燈",
            bool(card16) and ("✅ 覆蓋" not in card16) and ("不予判斷" in seg16),
            f"③={seg16!r}")

        # ── S17 卡片③：富達月配缺 → 覆蓋不得亮綠燈（真管線）───────────────────
        d17 = json.loads(json.dumps(real_snap))
        _ctg17 = (d17.get("funds_breakdown", {}) or {}).get("國泰直購", {}) or {}
        d17["funds_breakdown"] = dict(d17.get("funds_breakdown") or {})
        d17["funds_breakdown"]["國泰直購"] = {k: v for k, v in _ctg17.items()
                                              if "富達" not in str(k)}
        sp17 = _dump(d17, tmpd5 / "snapshot_no_fidelity.json")
        h17, _ = _render_card_live(snap_override=sp17)
        card17 = _card(h17)
        i17 = card17.find("③ 月度利息流出")
        seg17 = card17[i17:i17 + 175] if i17 >= 0 else ""
        chk("S17 E2E（缺值／卡片③／經 calibrate_sources）：富達月配缺（國泰直購 無「富達」鍵）"
            " → 覆蓋判斷不得亮綠燈",
            bool(card17) and ("✅ 覆蓋" not in card17) and ("不予判斷" in seg17),
            f"③={seg17!r}")
    finally:
        shutil.rmtree(tmpd5, ignore_errors=True)

    # ══ S18–S23：CIO 三審六項必改（生產端 default／硬編碼／驗收器假信心）══════
    # 關鍵差異：一律走「snapshot 檔移除鍵 + calibrate_sources()」的真實管線；
    # 不用 mutate 直接注入 tv——後者正是三審指出 S15/S16「假信心」的根因。
    import sot_targets as _sot
    tmpd4 = Path(tempfile.mkdtemp(prefix="lj_p0d_"))
    try:
        import run_daily as _R4
        _bak4 = _R4.SNAPSHOT

        # ── S18 生產端：（必改1）remove dividend_month_expected → tv 必須 None ──
        d4 = json.loads(json.dumps(real_snap))
        d4.pop("dividend_month_expected", None)
        sp4 = _dump(d4, tmpd4 / "snapshot_no_dme.json")
        try:
            _R4.SNAPSHOT = sp4
            _tv4 = dict(_R4.calibrate_sources())
        finally:
            _R4.SNAPSHOT = _bak4
        chk("S18 生產端（必改1）：snapshot 移除 dividend_month_expected → calibrate_sources() 回 None"
            "（原 default 100_000 使顯示端與卡片③永遠收不到 None）",
            _tv4.get("dividend_month_expected") is None,
            f"tv={_tv4.get('dividend_month_expected')!r}")
        h18, _ = _render_liab(snap_override=sp4)
        _i18 = h18.find("被動月收")
        seg18 = h18[_i18:_i18 + 700] if _i18 >= 0 else ""
        chk("S18b E2E（經完整 calibrate_sources 管線）：資產總表不得出現配息保守 100,000",
            bool(seg18) and ("⚠️ 缺真值" in seg18) and ("100,000" not in seg18),
            f"段={seg18[:170]!r}")

        # ── S19 生產端：（必改2）remove rent_monthly_total → 必須 None ──────────
        d5 = json.loads(json.dumps(real_snap))
        _srent5 = d5.get("rent_monthly")
        d5.pop("rent_monthly_total", None)
        sp5 = _dump(d5, tmpd4 / "snapshot_no_rent.json")
        try:
            _R4.SNAPSHOT = sp5
            _tv5 = dict(_R4.calibrate_sources())
        finally:
            _R4.SNAPSHOT = _bak4
        chk("S19 生產端（必改2）：snapshot 移除 rent_monthly_total → rent_monthly_target 為 None"
            "（原 `or s_rent or 0` 會靜默退成當月實收／0）",
            _tv5.get("rent_monthly_target") is None,
            f"tv={_tv5.get('rent_monthly_target')!r}（當月實收={_srent5!r}）")
        h19, _ = _render_liab(snap_override=sp5)
        _i19 = h19.find("被動月收")
        seg19 = h19[_i19:_i19 + 700] if _i19 >= 0 else ""
        chk("S19b E2E（經完整管線）：資產總表不得出現常態房租 80,100",
            bool(seg19) and ("⚠️ 缺真值" in seg19) and ("80,100" not in seg19),
            f"段={seg19[:170]!r}")
        # 必改4 動態驗證：雙維度資產定位 callout 原寫死「房租 80,100/月」（S21 只驗靜態）；
        # 這裡要求缺鍵時**整份報告**都不得再冒出該數字。
        chk("S19c E2E（必改4 動態）：rent_monthly_total 缺 → 雙維度 callout 與全份報告"
            "皆不得再出現「房租 80,100」（證明為動態派生，非硬編碼）",
            "房租 80,100" not in h19 and "房租 ⚠️ 缺真值" in h19,
            f"全份殘留={'房租 80,100' in h19}｜示缺真值={'房租 ⚠️ 缺真值' in h19}")

        # ── S20 生產端：（必改3）liability_interest 拔 dflt_rate ───────────────
        d6 = json.loads(json.dumps(real_snap))
        _lb6 = dict(d6.get("liabilities_build_up") or {})
        _rl6 = _lb6.pop("基金質押利率", None)
        d6["liabilities_build_up"] = _lb6
        _li6 = _sot.liability_interest(d6)
        chk("S20 生產端（必改3）：移除 基金質押利率 → 該項與合計皆 None"
            "（原 dflt_rate 2.65% 會算出 13,029）",
            _li6.get("基金質押利息") is None and _li6.get("合計") is None
            and "基金質押利率" in (_li6.get("_缺真值") or []),
            f"基金質押={_li6.get('基金質押利息')!r}｜合計={_li6.get('合計')!r}"
            f"｜缺={_li6.get('_缺真值')!r}（原利率={_rl6!r}）")
        sp6 = _dump(d6, tmpd4 / "snapshot_no_pledge_rate.json")
        h20, _ = _render_card_live(snap_override=sp6)
        card20 = _card(h20)
        _i20 = card20.find("② 負債月息")
        seg20 = card20[_i20:_i20 + 260] if _i20 >= 0 else ""
        chk("S20b E2E：卡片② 缺質押利率 → 不得再印「基金質押 13,029/月」，須示缺真值",
            bool(seg20) and ("13,029" not in seg20) and ("缺真值" in seg20),
            f"②={seg20!r}")

        # ── S21 靜態：（必改4）房租硬編碼 ─────────────────────────────────────
        _hard21 = [p for p in ("房租 80,100", "80100", "80_100") if p in body]
        chk("S21 靜態（必改4）：run_daily.py 不得硬編碼房租 80,100（雙維度資產定位 callout）",
            not _hard21, f"命中={_hard21}")

        # ── S22 必改5：卡片③ 房租鍵名（tv 從不具 rent_monthly_total → 房租恆 0）
        _bad22 = [p for p in ('tv.get("rent_monthly_total")', "tv.get('rent_monthly_total')")
                  if p in body]
        chk("S22 靜態（必改5）：卡片③ 不得讀 tv 不存在的鍵 rent_monthly_total（會把房租當 0，"
            "卻仍標示「配息＋房租」）",
            not _bad22, f"命中={_bad22}")
        h22, _ = _render_card_live()
        card22 = _card(h22)
        _i22 = card22.find("③ 月度利息流出")
        seg22 = card22[_i22:_i22 + 320] if _i22 >= 0 else ""
        chk("S22b E2E：卡片③ 流入＝常態配息＋房租 180,100（與資產總表同口徑，不得只算配息 100,000）",
            ("180,100" in seg22) and ("100,000" not in seg22),
            f"③={seg22!r}")

        # ── S23 驗收器自證：（必改6）證明測的是 producer，不是 mutate 注入 ──────
        try:
            _R4.SNAPSHOT = _bak4
            _tv_ok = dict(_R4.calibrate_sources())
        finally:
            _R4.SNAPSHOT = _bak4
        chk("S23 驗收器自證（必改6）：同一路徑下「真值檔回真值、缺鍵檔回 None」"
            "→ 證明驗的是 calibrate_sources 生產端（非 mutate 注入的假 None）",
            _tv_ok.get("dividend_month_expected") == real_snap.get("dividend_month_expected")
            and _tv_ok.get("rent_monthly_target") == real_snap.get("rent_monthly_total")
            and _tv4.get("dividend_month_expected") is None
            and _tv5.get("rent_monthly_target") is None,
            f"真值檔={_tv_ok.get('dividend_month_expected')!r}/{_tv_ok.get('rent_monthly_target')!r}"
            f"｜缺鍵檔={_tv4.get('dividend_month_expected')!r}/{_tv5.get('rent_monthly_target')!r}")
        # ── S24（CIO 四審 R1）：負債明細表不得因缺真值而靜默漏列 ─────────────────
        d7 = json.loads(json.dumps(real_snap))
        d7.pop("mortgage_cathay", None)
        sp7 = _dump(d7, tmpd4 / "snapshot_no_mortgage_cathay.json")
        chk("S24a 靜態（R1）：producer 端不得再以 `snap.get(\"mortgage_cathay\", 0)` 供預設 0",
            'snap.get("mortgage_cathay", 0)' not in body,
            "命中" if 'snap.get("mortgage_cathay", 0)' in body else "未命中")
        h24, _ = _render_liab(snap_override=sp7)
        r24 = _row(h24, "國泰房貸")
        chk("S24b E2E（R1／缺值）：mortgage_cathay 缺 → 負債明細表仍須有『國泰房貸』列"
            "且明示缺真值（原 gate `> 0` 會讓整列靜默消失＝1,200 萬負債憑空不見）",
            bool(r24) and ("缺真值" in r24) and ("12,000,000" not in r24),
            f"列={r24[:230]!r}")
        h24r, _ = _render_liab()
        r24r = _row(h24r, "國泰房貸")
        chk("S24c 正向對照（真值）：國泰房貸列顯示本金／利率／月付，且本金不得出現 float 尾綴"
            "（accessor 回 float → 原 f\"{:,}\" 會印 12,000,000.0）（S24b 非假通過）",
            bool(r24r) and all(x in r24r for x in ("12,000,000", "2.6%", "26,000"))
            and ("12,000,000.0" not in r24r),
            f"列={r24r[:230]!r}")
        _LK24 = ("mortgage_yy", "mortgage_yydu", "mortgage_xz", "mortgage_cathay",
                 "financial_mortgage", "policy_loan", "pledge_loan")
        _hit24d = [k for k in _LK24 if ("tv['" + k + "'] > 0") in body]
        chk("S24d 靜態（R1）：負債明細表不得再用 `if tv['<負債鍵>'] > 0:` 型式"
            "（缺真值會被靜默吞列）",
            not _hit24d, f"殘留={_hit24d}")

        # ── S25（CIO 四審 R2）：render_health_score 缺真值不得崩 ────────────────
        import report_components as _rc25
        d8 = json.loads(json.dumps(real_snap))
        d8.pop("rent_monthly_total", None)
        _ok25 = True
        _err25 = ""
        try:
            _d25 = _rc25.render_health_score(d8)
        except Exception as _e25:      # noqa: BLE001
            _ok25 = False
            _err25 = f"{type(_e25).__name__}: {_e25}"
        chk("S25 E2E（R2）：render_health_score 缺 rent_monthly_total → 不得 raise"
            "（原 L207 直接除 cov → TypeError，sync_all 組件自測會崩）",
            _ok25 and (_d25.get("覆蓋缺真值") is True)
            and (_d25.get("覆蓋") is None) and (_d25.get("覆蓋標準") == 0),
            f"例外={_err25 or '無'}｜覆蓋缺真值={(_d25.get('覆蓋缺真值') if _ok25 else 'N/A')}"
            f"｜分數={(_d25.get('分數') if _ok25 else 'N/A')}")
        d9 = json.loads(json.dumps(real_snap))
        _ok25b = True
        try:
            _d25b = _rc25.render_health_score(d9)
        except Exception as _e25b:     # noqa: BLE001
            _ok25b = False
            _err25b = f"{type(_e25b).__name__}: {_e25b}"
        chk("S25b 正向對照（R2／真值）：真值齊全時健康度正常（覆蓋 113、分數與第三審一致）",
            _ok25b and _d25b.get("覆蓋") is not None and _d25b.get("覆蓋") >= 100,
            f"覆蓋={(_d25b.get('覆蓋') if _ok25b else 'N/A')}｜分數={(_d25b.get('分數') if _ok25b else 'N/A')}")

    finally:
        shutil.rmtree(tmpd4, ignore_errors=True)

    # ══ S26–S29：CIO 五審殘留（M1 基金質押列／M2 LTV／M7 晨報硬編碼）══════════
    tmpd6 = Path(tempfile.mkdtemp(prefix="lj_p0f_"))
    try:
        # S26（M1）fund_pledge_loan 缺 → 基金質押列不得靜默消失
        d10 = json.loads(json.dumps(real_snap))
        d10.pop("fund_pledge_loan", None)
        sp10 = _dump(d10, tmpd6 / "snapshot_no_fund_pledge.json")
        h26, _ = _render_liab(snap_override=sp10)
        r26 = _row(h26, "基金質押")
        chk("S26a E2E（M1／缺值）：fund_pledge_loan 缺 → 負債明細表仍須有『基金質押』列"
            "且明示缺真值（原 gate `> 0` 會讓 5,900,000 整列靜默消失）",
            bool(r26) and ("缺真值" in r26) and ("5,900,000" not in r26),
            f"列={r26[:220]!r}")
        h26r, _ = _render_liab()
        r26r = _row(h26r, "基金質押")
        chk("S26b 正向對照（真值）：基金質押列顯示 5,900,000／2.65%（S26a 非假通過）",
            bool(r26r) and all(x in r26r for x in ("5,900,000", "2.65%")),
            f"列={r26r[:220]!r}")

        # S27（M2）render_health_score：缺質押鍵 → 不得少算分子後靜默變健康
        import report_components as _rc27
        _d27 = _rc27.render_health_score(json.loads(json.dumps(d10)))
        _t27 = _rc27.render_health_score(json.loads(json.dumps(real_snap)))
        chk("S27 E2E（M2）：缺 fund_pledge_loan → LTV 系列為 None（非 0.0）、LTV缺真值=True、"
            "該維度 0 分；原 `or 0` 會讓 LTV 由 24.4% 靜默變 0.0%（看起來更健康）",
            _d27.get("LTV") is None and _d27.get("LTV缺真值") is True
            and _d27.get("LTV分") == 0 and _d27.get("分數") < _t27.get("分數")
            and abs(_t27.get("LTV") - 24.3746) < 0.01,
            f"缺值 LTV={_d27.get('LTV')!r}／分數={_d27.get('分數')}｜真值 LTV={_t27.get('LTV')!r}／"
            f"分數={_t27.get('分數')}")

        # S28（M7）晨報／FIRE 常態對照不得用硬編碼舊真值救場
        import morning_briefing as _mb28
        import fire_progress as _fp28
        _s28 = json.loads(json.dumps(real_snap))
        _s28.pop("dividend_month_expected", None)
        _s28.pop("rent_monthly_total", None)
        _l28 = "".join(_mb28.get_fire(_s28))
        _l28t = "".join(_mb28.get_fire(json.loads(json.dumps(real_snap))))
        _bad28 = [x for x in ("100,000", "80,100", "180,100", "113.1%") if x in _l28]
        chk("S28 E2E（M7）：晨報常態對照缺真值 → 不得再印硬編碼舊真值"
            "（100,000／80,100／180,100／113.1%），須明示缺真值",
            (not _bad28) and ("缺真值" in _l28) and ("180,100" in _l28t),
            f"殘留={_bad28}｜示缺真值={'缺真值' in _l28}")
        _f28 = _fp28.calc.__module__ and "" or ""
        _src28 = Path(_fp28.__file__).read_text(encoding="utf-8")
        _bad28b = [p for p in ("dividend_month_expected', 100_000",
                               "rent_monthly_total', 80_100") if p in _src28]
        chk("S28b 靜態（M7）：fire_progress.py 常態對照不得再用硬編碼 default",
            not _bad28b, f"命中={_bad28b}")

        # S29（M3–M7）靜態：同型 `or <舊常數>` 不得復辟
        _files29 = ("build_penetration_report.py", "build_dashboard.py",
                    "morning_briefing.py", "fire_progress.py", "report_components.py")
        _pats29 = ('fund_pledge_rate") or 0.0265', "fund_pledge_rate') or 0.0265",
                   'dividend_month_expected", 100_000', "dividend_month_expected', 100_000",
                   'rent_monthly_total", 80_100', "rent_monthly_total', 80_100",
                   'mortgage_cathay") or 0', 'mortgage_cathay_rate") or 0')
        _hit29 = []
        for _fn29 in _files29:
            _tx29 = "\n".join(l for l in (BASE / _fn29).read_text(encoding="utf-8").splitlines()
                              if not l.lstrip().startswith("#"))
            _hit29 += [f"{_fn29}:{p}" for p in _pats29 if p in _tx29]
        chk("S29 靜態（M3–M7）：canonical 鍵不得再以 `or <舊常數>` 型式供假真值"
            "（2.65%／100,000／80,100／mortgage_cathay 0）",
            not _hit29, f"命中={_hit29}")
    finally:
        shutil.rmtree(tmpd6, ignore_errors=True)

    # ══ S30–S32：CIO 六審 8 項（sot_targets LTV／真值層寫入器／mortgage_rate）══════
    import sot_targets as _sot30
    import asset_sync as _as30
    import mortgage_rate as _mr30
    _d30 = json.loads(json.dumps(real_snap))
    _d30.pop("fund_pledge_loan", None)
    _v30d = _sot30.sync_scenario_verification(_d30)["現況驗證"]
    _v30t = _sot30.sync_scenario_verification(json.loads(json.dumps(real_snap)))["現況驗證"]
    chk("S30（六審1）：sot_targets 缺 fund_pledge_loan → LTV 為 None 且 LTV合格=False"
        "（原 `or 0.0` 會給 LTV 0.0%、合格=True＝「LTV 0.0%（≤52% ✅）」並寫回 snapshot）",
        _v30d.get("LTV") is None and _v30d.get("LTV合格") is False
        and "缺真值" in str(_v30d.get("結論"))
        and abs(_v30t.get("LTV") - 50.1) < 0.5 and _v30t.get("LTV合格") is True,
        f"缺值 LTV={_v30d.get('LTV')!r}／合格={_v30d.get('LTV合格')}｜"
        f"真值 LTV={_v30t.get('LTV')!r}／合格={_v30t.get('LTV合格')}")

    # S31 真值層寫入器：缺鍵 → 不寫入（保留原值、不編造）
    _s31 = json.loads(json.dumps(real_snap))
    _tl31_before = _s31.get("total_liabilities")
    _lb31_before = json.dumps(_s31.get("liabilities_build_up"), ensure_ascii=False, sort_keys=True)
    _s31.pop("fund_pledge_loan", None)
    _s31 = _as30.rebuild_liabilities(_s31)
    _lb31_after = json.dumps(_s31.get("liabilities_build_up"), ensure_ascii=False, sort_keys=True)
    chk("S31（六審2／真值層寫入器）：缺 fund_pledge_loan → total_liabilities 與 liabilities_build_up"
        "**保留原值**（不編造 0／不編造 2.65%），且 net_worth 不得由 −417.6 萬翻正為 +172.4 萬",
        _s31.get("total_liabilities") == _tl31_before and _lb31_after == _lb31_before,
        f"total {_tl31_before}→{_s31.get('total_liabilities')}｜build_up 未變={_lb31_after == _lb31_before}")

    # S32 mortgage_rate：缺真值不得退回硬編碼 0.026／26,000
    _s32 = json.loads(json.dumps(real_snap))
    for _k32 in ("mortgage_cathay_rate", "mortgage_cathay", "mortgage_cathay_monthly"):
        _s32.pop(_k32, None)
    _s32["monthly_fixed_expense"] = {k: v for k, v in (_s32.get("monthly_fixed_expense") or {}).items()
                                     if k != "房貸_國泰"}
    chk("S32（六審4）：mortgage_rate 缺真值 → cathay_rate()／cathay_monthly() 回 None、"
        "cathay_rate_pct() 示缺真值（原退回硬編碼 0.026／26,000）",
        _mr30.cathay_rate(_s32) is None and _mr30.cathay_monthly(_s32) is None
        and "缺真值" in _mr30.cathay_rate_pct(_s32)
        and abs(_mr30.cathay_rate(json.loads(json.dumps(real_snap))) - 0.026) < 1e-9,
        f"缺值 rate={_mr30.cathay_rate(_s32)!r}／monthly={_mr30.cathay_monthly(_s32)!r}／"
        f"pct={_mr30.cathay_rate_pct(_s32)!r}｜真值 rate={_mr30.cathay_rate(real_snap)!r}")

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
