# -*- coding: utf-8 -*-
"""verify_mtd_baseline_alignment.py — 本月績效頁「基準日事件對齊」永久回歸驗證器。

來源工單（使用者 2026-10-12）：MTD 總資產變化與淨值基準日校正。
根因：質押撥款／保單借貸清償的「資產腿」與「負債腿」入帳日不同（保單公司 3 個工作日），
      月初基準日（上月最後一筆）若夾在兩腿之間，該日淨值被單邊低估
      → 期初期末相減不是本期淨值變化。
修正原則：只調報表比較口徑（事件歸屬），**不改原始交易日期或歷史真值**。

設計紀律（依 cioreview-sop「相對式驗證器設計」）：
  · 期望值一律現算（讀 dragon_assets.db 推導），不寫死當期真值。
  · 負向控制必須「植入缺陷 → 期望對應檢查轉紅」；三個負向案例皆為合成序列，不依賴當期狀態。
  · 只讀 repo 產物；重跑一律在 %TEMP% 沙盒複本，不寫任何 repo 檔。
  · FAIL 一律 exit 1。

用法：python tools/verify_mtd_baseline_alignment.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "dragon_assets.db"
BUILDER = "build_mtd_report.py"
PRODUCT = "mtd_data.json"

PASS, FAIL = [], []


def chk(name: str, ok: bool, detail: str = "") -> bool:
    (PASS if ok else FAIL).append(name + (f" — {detail}" if detail else ""))
    return bool(ok)


def _load_mods():
    sys.path.insert(0, str(REPO))
    import notion_weekly_trend_wrapper as nwtw            # noqa: E402
    import build_mtd_report as bmt                        # noqa: E402
    return nwtw, bmt


def _db_rows(conn, d0: str, d1: str):
    return [{"date": r[0], "total_assets": r[1], "total_liabilities": r[2], "cash_total": r[3]}
            for r in conn.execute(
                "SELECT date, total_assets, total_liabilities, cash_total FROM assets "
                "WHERE date >= ? AND date <= ? ORDER BY date", (d0, d1))]


def _last_day(conn, yyyymm: str):
    r = conn.execute("SELECT MAX(date) FROM assets WHERE date < ?", (f"{yyyymm}-01",)).fetchone()
    return r[0] if r else None


def _latest_day(conn):
    r = conn.execute("SELECT MAX(date) FROM assets").fetchone()
    return r[0] if r else None


# ── 合成序列產生器（負向／正向控制用；參數化的假資料，不引用當期真值）──────────
def _series(rows):
    return [{"date": d, "total_assets": ta, "total_liabilities": tl, "cash_total": 0}
            for d, ta, tl in rows]


def main() -> int:
    nwtw, bmt = _load_mods()
    if not DB.exists():
        chk("dragon_assets.db 存在", False, str(DB))
        return _report()

    conn = sqlite3.connect(str(DB))
    latest = _latest_day(conn)
    base = _last_day(conn, latest[:7])
    chk("基準日（上月最後一筆）可得", bool(base), f"base={base} latest={latest}")
    if not base:
        return _report()

    d0 = (__import__("datetime").date.fromisoformat(base) - __import__("datetime").timedelta(days=14)).isoformat()
    rows = _db_rows(conn, d0, latest)
    metrics = nwtw.compute_daily_metrics(rows)
    structural = [d for d, m in sorted(metrics.items()) if m["structural"]]
    chains = nwtw.detect_event_chains(metrics, structural)
    align = bmt.align_baseline_nw(metrics, chains, base, metrics[latest]["nw"])
    conn.close()

    # 1) 基準日確實落於事件鏈內，且對齊已生效
    chk("基準日落於事件鏈內 → 對齊生效", bool(align["applied"]),
        f"base={base} chains={[c['dates'] for c in chains]}")
    if not align["applied"]:
        return _report()

    chain_days = sorted(align["chain"]["dates"])

    # 2) 對齊後基準日 = 鏈起點之前最後一個有效淨值日（相對斷言，不寫死日期）
    priors = [d for d, m in metrics.items() if m.get("nw") is not None and d < chain_days[0]]
    expect_baseline = max(priors) if priors else None
    chk("對齊後基準日 = 鏈起點前最後有效淨值日",
        align["baseline_aligned"] == expect_baseline,
        f"{align['baseline_aligned']} vs {expect_baseline}")
    chk("對齊後基準日 ≠ 原基準日（否則形同未對齊）",
        align["baseline_aligned"] != align["baseline_raw"])

    # 3) 對齊後淨值變化 = 現算差值（同一組端點），且與帳面值不同
    nw_end = metrics[latest]["nw"]
    expect_chg = nw_end - metrics[expect_baseline]["nw"]
    chk("對齊後淨值變化 = 現算端點差",
        abs(align["net_worth_chg"] - expect_chg) < 0.5,
        f"{align['net_worth_chg']:.0f} vs {expect_chg:.0f}")
    raw_chg = nw_end - metrics[base]["nw"]
    chk("帳面淨值變化（原基準）可現算重現",
        abs(raw_chg - (nw_end - align["nw_raw"])) < 0.5, f"raw_chg={raw_chg:.0f}")
    chk("對齊值與帳面值不同 → 證明對齊有實質效果",
        abs(align["net_worth_chg"] - raw_chg) > 0.5,
        f"aligned={align['net_worth_chg']:.0f} raw={raw_chg:.0f}")

    # 4) 事件鏈兩腿判準成立（資產腿／負債腿不同日；對沖比在容忍帶內）
    chk("事件鏈兩日主導腿不同", align["chain"]["first_leg"] != align["chain"]["reverse_leg"],
        f"{align['chain']['first_leg']} vs {align['chain']['reverse_leg']}")
    ratio = align["chain"]["ratio"]
    chk("事件鏈對沖比落於容許帶",
        nwtw.EVENT_CHAIN_OFFSET_RATIO <= ratio <= 1 / nwtw.EVENT_CHAIN_OFFSET_RATIO,
        f"ratio={ratio:.4f}")

    # 5) 產物（mtd_data.json）與本檔獨立重算一致 —— 同口徑、可重現
    prod_path = REPO / PRODUCT
    if chk(f"{PRODUCT} 存在", prod_path.exists()):
        prod = json.loads(prod_path.read_text(encoding="utf-8"))
        pa = (prod.get("equity") or {}).get("alignment") or {}
        chk("產物 equity.alignment 與獨立重算一致（applied／基準日／值）",
            pa.get("applied") is True
            and pa.get("baseline_aligned") == align["baseline_aligned"]
            and abs((pa.get("net_worth_chg") or 0) - align["net_worth_chg"]) < 0.5,
            f"產物 {pa.get('baseline_aligned')}/{pa.get('net_worth_chg')} "
            f"vs 重算 {align['baseline_aligned']}/{align['net_worth_chg']:.0f}")
        chk("產物 raw 與 aligned 併存（未覆寫來源值）",
            pa.get("nw_raw") is not None and pa.get("nw_aligned") is not None
            and abs(pa["nw_raw"] - align["nw_raw"]) < 0.5,
            f"nw_raw={pa.get('nw_raw')} nw_aligned={pa.get('nw_aligned')}")

    # 6) 負向控制 A：無事件鏈的合成序列 → 不得套用對齊
    flat = _series([("2026-01-01", 1_000_000, 500_000), ("2026-01-02", 1_010_000, 500_000),
                    ("2026-01-03", 1_020_000, 500_000)])
    mA = nwtw.compute_daily_metrics(flat)
    aA = bmt.align_baseline_nw(mA, nwtw.detect_event_chains(mA, []), "2026-01-03")
    chk("[負向A] 無事件鏈 → applied=False", aA["applied"] is False, str(aA["applied"]))

    # 7) 負向控制 B：市場連續下跌（兩腿皆資產腿主導）→ 不得判為事件鏈
    down = _series([("2026-02-01", 2_000_000, 1_000_000), ("2026-02-02", 1_500_000, 1_000_000),
                    ("2026-02-03", 1_100_000, 1_000_000)])
    mB = nwtw.compute_daily_metrics(down)
    chk("[負向B] 市場連續下跌不誤判為事件鏈",
        len(nwtw.detect_event_chains(mB, [])) == 0,
        str([c["dates"] for c in nwtw.detect_event_chains(mB, [])]))

    # 8) 負向控制 C：合成標準事件鏈（資產腿一日、負債腿次日逆向）→ 必須套用且基準回退
    ev = _series([("2026-03-01", 3_000_000, 1_000_000),
                  ("2026-03-02", 1_600_000, 500_000),      # 資產腿主導：資產大減、負債小減
                  ("2026-03-03", 1_600_000, -300_000)])    # 負債腿主導：反向對沖
    mC = nwtw.compute_daily_metrics(ev)
    cC = nwtw.detect_event_chains(mC, [])
    aC = bmt.align_baseline_nw(mC, cC, "2026-03-02")
    chk("[正向C] 合成事件鏈被偵測到", len(cC) >= 1, str([c["dates"] for c in cC]))
    chk("[正向C] 基準日落在鏈內 → 回退至鏈前一日",
        aC["applied"] is True and aC["baseline_aligned"] == "2026-03-01",
        f"applied={aC['applied']} aligned={aC['baseline_aligned']}")

    # 9) 不寫死掃描：build_mtd_report.py 不得出現本輪現算出的當期真值字面（AST 常數）
    import ast
    src = (REPO / BUILDER).read_text(encoding="utf-8")
    tree = ast.parse(src)
    consts = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float, str)):
            consts.add(str(n.value))
    hot = []
    for v in (align["net_worth_chg"], align["nw_raw"], align["nw_aligned"],
              raw_chg, nw_end, align["chain"]["amount"]):
        for form in (f"{int(round(v)):,}", str(int(round(v)))):
            if form in consts:
                hot.append(form)
    chk("build_mtd_report.py 未寫死當期真值字面", not hot, str(sorted(set(hot))))

    # 10) 冪等：沙盒重跑 builder → mtd_data.json 除 generated_at 外逐位元相同
    sb = Path(tempfile.mkdtemp(prefix="verify_mtd_align_"))
    try:
        for f in (BUILDER, "snapshot.json", "dragon_assets.db", "investment_performance_adjust.json",
                  "performance_core.py", "build_investment_performance.py",
                  "notion_weekly_trend_wrapper.py", "dividend_caliber.py", PRODUCT):
            if (REPO / f).exists():
                shutil.copy2(REPO / f, sb / f)
        r = subprocess.run([sys.executable, BUILDER, "--quiet"], cwd=str(sb),
                           capture_output=True, text=True, timeout=300)
        ok_run = r.returncode == 0
        chk("沙盒重跑 builder rc=0", ok_run, (r.stderr or "")[-300:])
        if ok_run:
            def norm(p):
                t = p.read_text(encoding="utf-8")
                return re.sub(r'"generated_at": "[^"]*"', '"generated_at": "X"', t)
            chk("重跑 mtd_data.json 冪等（僅時間戳差異）",
                norm(sb / PRODUCT) == norm(REPO / PRODUCT))
    finally:
        shutil.rmtree(sb, ignore_errors=True)

    return _report()


def _report() -> int:
    print(f"=== 基準日事件對齊驗證：PASS {len(PASS)} / FAIL {len(FAIL)} ===")
    for p in PASS:
        print(f"  ✅ {p}")
    for f in FAIL:
        print(f"  ❌ {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
