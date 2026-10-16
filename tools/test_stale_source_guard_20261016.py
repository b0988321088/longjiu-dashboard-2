#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_stale_source_guard_20261016.py — 防止舊快照混入報告的回歸（2026-10-16 裁決 ①）

事故（2026-10-16 07:00 產線全停，真 CIO REJECT 實例）：
    rebalance_summary_{today}.md 同時出現兩套真值 —— 「台股 8.9%（snapshot 現況欄）」
    與「9.1%／36.2%／總資產 27,085,225／防守合併 65.7%」（radar_state.weekly_plan 的
    2026-10-15 舊列）。根因＝產出端直接引用非當日的 weekly_plan 文字，沒有任何資料日閘門。

本檔驗的是「根因」而非該次修補的字面值：
  G 系列：取用端資料日閘門（build_rebalance_dashboard.weekly_plan_rows）
  S 系列：科技口徑（sot_targets 的 live 覆蓋不得改寫 GICS 全資產風險行）
  R 系列：真實產物一致性（md 與 eval HTML 同真值、無已知舊值殘留；檔案不存在則略過）

執行：python -X utf8 tools/test_stale_source_guard_20261016.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PASS = FAIL = 0

# 已知的 2026-10-15 舊真值字串（出現在報告中即為舊快照混入）
STALE = ("27,085,225", "17,802,228", "1,679,284", "36.2%", "65.7%", "9.1% vs", "-0.9pp")


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")


def main() -> int:
    import build_rebalance_dashboard as brd
    import sot_targets as st

    print("=== 舊快照混入防線（資料日閘門／口徑一致／真實產物） ===")

    # ── G：取用端資料日閘門 ────────────────────────────────────────────────
    rows = [{"動作": "🟢", "類別": "台股", "內容": "（9.1% vs 目標10%，缺口 -0.9pp）"}]
    got, why = brd.weekly_plan_rows({"weekly_plan": {"日期": "2026-10-15", "rows": rows}}, "2026-10-16")
    check("G1 非當日 weekly_plan → 一列都不引用（不得混入舊真值）", got == [], f"got={got}")
    check("G2 非當日 → 回報原因（可診斷、非靜默）", "不引用" in why and "2026-10-15" in why, why)
    ok_rows, why2 = brd.weekly_plan_rows({"weekly_plan": {"日期": "2026-10-16", "rows": rows}}, "2026-10-16")
    check("G3 當日 weekly_plan → 原樣引用（不得誤擋）", ok_rows == rows and why2 == "",
          f"rows={ok_rows} why={why2}")
    empty, why3 = brd.weekly_plan_rows({"weekly_plan": {"日期": "2026-10-15", "rows": []}}, "2026-10-16")
    check("G4 非當日但空列 → 空且無警示（不製造假紅燈）", empty == [] and why3 == "", f"{empty} {why3}")
    check("G5 缺 weekly_plan 鍵 → 不炸、回空", brd.weekly_plan_rows({}, "2026-10-16") == ([], ""))

    # ── S：科技口徑（GICS 全資產風險行 vs 美股子項）────────────────────────
    snap = json.loads((ROOT / "snapshot.json").read_text(encoding="utf-8"))
    tech_sub = float(((snap.get("penetration") or {}).get("actual_pct") or {})
                     .get("美股市值型成長_科技") or 0)
    gics_tech = float(((snap.get("industry_penetration") or {}).get("產業") or {})
                      .get("資訊科技", {}).get("佔比") or 0)
    fake = (f"高科技 {gics_tech:.1f}%（紅線 30%）：🟢 安全\n"
            f"美股子項：科技 99.9%（3,000,000；硬上限 15%）\n")
    out = st.refresh_rebalance_live_numbers(st.refresh_stale_amounts(fake, snap), snap)
    check("S1 GICS 風險行『高科技 X%（紅線 30%）』不得被子項口徑改寫",
          f"高科技 {gics_tech:.1f}%（紅線 30%）" in out and f"高科技 {tech_sub:.1f}%" not in out,
          out[:120])
    check("S2 美股子項『科技 X%』仍必須改為 live（口徑修正不得使覆蓋失效）",
          f"科技 {tech_sub:.1f}%（3,000,000" not in out and re.search(r"科技\s*99\.9%", out) is None,
          out[:200])

    # ── R：真實產物一致性（今天的情境）────────────────────────────────────
    day = str(snap.get("date") or "")
    md = ROOT / f"rebalance_summary_{day}.md"
    ev = ROOT / f"rebalance_eval_{day}.html"
    if md.exists():
        t = md.read_text(encoding="utf-8")
        hits = {s: t.count(s) for s in STALE if s in t}
        check(f"R1 正典 {md.name} 無已知舊值殘留", not hits, str(hits))
        total = f"{int(snap.get('total_assets') or 0):,}"
        check("R2 正典總資產＝snapshot.total_assets", total in t, total)
        if ev.exists():
            e = ev.read_text(encoding="utf-8")
            hits_e = {s: e.count(s) for s in STALE if s in e}
            check(f"R3 eval HTML 無已知舊值殘留", not hits_e, str(hits_e))
            check("R4 科技口徑一致：md 與 eval HTML 同為 GICS 值",
                  (f"高科技 {gics_tech:.1f}%" in t) and (f"高科技 {gics_tech:.1f}%" in e)
                  and (f"高科技 {tech_sub:.1f}%" not in e),
                  f"gics={gics_tech} sub={tech_sub}")
            for lbl, need in (("總資產", total), ("債券 26.2%" if False else "26.2%", "26.2%")):
                check(f"R5 {lbl} 於兩份產物皆出現", (need in t) and (need in e), need)
        else:
            print(f"  ℹ️  {ev.name} 不存在 → 略過 HTML 比對")
        dr = ROOT / f"daily_report_v2_{day}.html"
        dcm = float((snap.get("defensive_combined_metric") or {}).get("佔比") or 0)
        if dr.exists():
            d = dr.read_text(encoding="utf-8")
            check("R6 日報無『防守合併 65.7%』等舊防守值",
                  "防守合併 65.7%" not in d and f"防守合併 {dcm:.1f}%" in d, f"dcm={dcm}")
    else:
        print(f"  ℹ️  {md.name} 不存在（非當日環境）→ 略過真實產物比對")

    print(f"\n{PASS} 通過／{FAIL} 失敗")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
