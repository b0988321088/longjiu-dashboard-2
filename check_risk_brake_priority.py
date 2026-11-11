#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_risk_brake_priority.py — 風險煞車 vs 動作階梯的優先序，做成可測斷言。

背景（CIO 2026-11-11 18:30 質疑③／建議 2）：
  「美股 +6.1pp 剛好踩到導流門檻、台股 +2.9pp 觀察級，但風險煞車優先於動作階梯 →
   今日正確結論是只回報不動作。這條不能只靠人腦記住。」
  故把「煞車期間任何交易型動作必為 no-op」變成機器可驗的斷言，而不是報告上的一句話。

檢查項（全過 rc=0；任一不過 rc=1）：
  B1 煞車門檻單一來源：us30y_gate.red_line == thresholds_2026_0915.風險煞車.us30y_pct
  B2 契約字面：風險煞車.優先於 必須寫明「動作階梯」
  B3 實況：以現值跑 tactical_table → frozen 且 全列 是否交易=False、無 增持/減碼
  B4 邊界：US30Y == 門檻（5.30）必須視為煞車（≥ 語義，非 >）
  B5 反向：US30Y < 門檻 → 不凍結（防「永久靜音」的假綠）
  B6 繞道：防守型配息合併口徑 <60% 且偏離達交易級時，煞車仍須把它壓成 no-op

用法：python check_risk_brake_priority.py [--snapshot snapshot.json]
"""
import argparse
import copy
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from tactical_table import build_table  # noqa: E402

TRADING_ACTIONS = ("增持", "減碼")


def _brake_line(snap):
    b = (snap.get("thresholds_2026_0915") or {}).get("風險煞車") or {}
    return float(b.get("us30y_pct", 5.30)), b


def _rows_violating_freeze(t):
    bad = []
    for r in t.get("rows", []):
        act = str(r.get("建議動作") or "")
        amt = r.get("精算金額") or 0
        # 金額也必須為 0：萬一日後新增交易型動作用語（不在 TRADING_ACTIONS 內），
        # 只要還算出金額就代表煞車漏了（CIO 2026-11-11 指出的殘留風險）。
        if r.get("是否交易") or any(k in act for k in TRADING_ACTIONS) or float(amt or 0) != 0:
            bad.append(f"{r.get('資產分類')}／動作={act}／交易={r.get('是否交易')}／金額={amt}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default=str(BASE / "snapshot.json"))
    a = ap.parse_args()

    snap = json.loads(Path(a.snapshot).read_text(encoding="utf-8"))
    brake_ln, brake_cfg = _brake_line(snap)
    gate = snap.get("us30y_gate") or {}
    us30y = gate.get("value")
    fails, oks = [], []

    # B1 門檻同源
    red = gate.get("red_line")
    if red is None:
        fails.append("B1 us30y_gate.red_line 缺值 → 煞車門檻無真值可對齊")
    elif abs(float(red) - brake_ln) > 1e-9:
        fails.append(f"B1 門檻分歧：us30y_gate.red_line={red} vs 風險煞車.us30y_pct={brake_ln}")
    else:
        oks.append(f"B1 門檻同源 {brake_ln:g}%")

    # B2 契約字面
    prio = str(brake_cfg.get("優先於") or "")
    if "動作階梯" not in prio:
        fails.append(f"B2 風險煞車.優先於 未寫明動作階梯（現值「{prio}」）")
    else:
        oks.append(f"B2 契約「優先於 {prio}」")

    # B3 實況（值高於門檻必凍結、低於門檻必不凍結；門檻以下時改判 no-op 反向）
    if us30y is None:
        fails.append("B3 us30y_gate.value 缺值 → 無法驗證實況")
    else:
        t = build_table(snap, float(us30y))
        if float(us30y) >= brake_ln:
            if not t.get("frozen"):
                fails.append(f"B3 US30Y {us30y}% ≥ {brake_ln:g}% 卻未凍結")
            else:
                bad = _rows_violating_freeze(t)
                if bad:
                    fails.append("B3 煞車期間仍有交易型動作：" + "；".join(bad))
                else:
                    oks.append(f"B3 實況 US30Y {us30y}% ≥ 門檻 → 全列 no-op（{len(t['rows'])} 列）")
        else:
            if t.get("frozen"):
                fails.append(f"B3 US30Y {us30y}% < {brake_ln:g}% 卻凍結（煞車無法解除）")
            else:
                oks.append(f"B3 實況 US30Y {us30y}% < 門檻 → 未凍結（煞車已解除）")

    # B4 邊界（等於門檻即煞車）
    t_eq = build_table(snap, brake_ln)
    if not t_eq.get("frozen"):
        fails.append(f"B4 US30Y 恰為門檻 {brake_ln:g}% 未凍結（> 與 ≥ 不一致）")
    elif _rows_violating_freeze(t_eq):
        fails.append("B4 邊界情境仍有交易型動作：" + "；".join(_rows_violating_freeze(t_eq)))
    else:
        oks.append(f"B4 邊界 {brake_ln:g}% 視為煞車")

    # B5 反向（低於門檻不凍結）
    below = round(brake_ln - 0.01, 4)
    t_below = build_table(snap, below)
    if t_below.get("frozen"):
        fails.append(f"B5 US30Y {below}% < 門檻卻凍結 → 煞車無法解除（假綠/死鎖）")
    else:
        oks.append(f"B5 反向 {below}% 不凍結")

    # B6 繞道（防守桶分支在 frozen 之前）
    s2 = copy.deepcopy(snap)
    s2["defensive_combined_metric"] = {"佔比": 30, "裁示": ""}
    pen = s2.setdefault("penetration", {})
    pen.setdefault("actual_pct", {})["防守型配息"] = 18.0
    pen.setdefault("targets", {})["防守型配息"] = 30
    t_d = build_table(s2, float(us30y if us30y is not None else brake_ln))
    d_row = next((r for r in t_d.get("rows", []) if r.get("資產分類") == "防守型配息"), None)
    if d_row is None:
        fails.append("B6 找不到防守型配息列 → 無法驗證繞道")
    elif d_row.get("是否交易") or any(k in str(d_row.get("建議動作")) for k in TRADING_ACTIONS):
        fails.append(f"B6 防守桶繞過煞車：動作={d_row.get('建議動作')}／交易={d_row.get('是否交易')}")
    else:
        oks.append(f"B6 防守桶繞道被壓成 no-op（{d_row.get('建議動作')}）")

    print("── 風險煞車優先序檢查 ──")
    for x in oks:
        print("  ✅ " + x)
    for x in fails:
        print("  ❌ " + x)
    print(f"── {'PASS' if not fails else f'FAIL（{len(fails)} 項）'} ──")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
