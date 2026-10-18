#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""測試 tools/check_bucket_attribution.py（2026-10-18 使用者核准施工的 4 個必測情境）。

情境：
  T1 真實重分類   —— 桶位大額變動、總資產幾乎不動、組成齊備 → 列「待解釋」＋主導來源
  T2 實際買賣     —— 桶位與總資產同幅變動（≥1%）→ 不觸發（不是桶間移動）
  T3 來源缺漏     —— 觸發但缺 components_twd → 無法對帳（fail-closed）
  T4 金額對不上   —— 組成加總變動 ≠ 桶值變動 → 擋下並指名差額
另 T5 門檻邊界     —— 異動略低於門檻 → 不觸發
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "tools"))

from check_bucket_attribution import analyze  # noqa: E402


def mk(day, total, tw, comp=None, us=0, df=0, bond=0, cash=0):
    pen = {
        "actual_twd": {"台股市值型成長": tw, "美股市值型成長": us, "防守型配息": df,
                       "債券": bond, "現金/安全網": cash},
    }
    if comp is not None:
        pen["components_twd"] = {"台股市值型成長": comp}
    return {"date": day, "total_assets": total, "penetration": pen}


def run():
    ok = 0
    fails = []

    # T1 真實重分類：保單穿透 +1,009,467、證券 −229,820 → 桶位 +779,647、總資產 −11,629
    cur = mk("2026-10-16", 26_980_846, 3_375_905,
             comp={"證券": 1_412_360, "平台基金": 954_078, "保單穿透": 1_009_467})
    prev = mk("2026-10-15", 26_992_475, 2_596_258,
              comp={"證券": 1_642_180, "平台基金": 954_078, "保單穿透": 0})
    r = analyze(cur, prev)
    t1 = (len(r["items"]) == 1 and not r["unaccounted"]
          and r["items"][0]["top_driver"]["name"] == "保單穿透"
          and r["items"][0]["status"] == "待解釋")
    ok += t1
    if not t1:
        fails.append(f"T1 真實重分類 未如期（items={r['items']} unacc={r['unaccounted']}）")

    # T2 實際買賣：買 50 萬台股 ETF，總資產同幅增加 → 不應觸發
    cur2 = mk("2026-10-18", 27_480_846, 3_875_905,
              comp={"證券": 1_912_360, "平台基金": 954_078, "保單穿透": 1_009_467})
    prev2 = mk("2026-10-17", 26_980_846, 3_375_905,
               comp={"證券": 1_412_360, "平台基金": 954_078, "保單穿透": 1_009_467})
    r2 = analyze(cur2, prev2)
    t2 = (not r2["items"] and not r2["unaccounted"])
    ok += t2
    if not t2:
        fails.append(f"T2 實際買賣 誤觸發（items={r2['items']}）")

    # T3 來源缺漏：上一日沒有 components_twd
    prev3 = mk("2026-10-15", 26_992_475, 2_596_258)     # 無 comp
    r3 = analyze(cur, prev3)
    t3 = (len(r3["unaccounted"]) == 1 and r3["unaccounted"][0]["status"] == "無法對帳")
    ok += t3
    if not t3:
        fails.append(f"T3 來源缺漏 未擋（unacc={r3['unaccounted']}）")

    # T4 金額對不上：組成合計變動與桶值差 500,000
    cur4 = mk("2026-10-16", 26_980_846, 3_375_905,
              comp={"證券": 1_412_360, "平台基金": 954_078, "保單穿透": 1_009_467})
    prev4 = mk("2026-10-15", 26_992_475, 2_596_258,
               comp={"證券": 1_642_180, "平台基金": 454_078, "保單穿透": 0})
    r4 = analyze(cur4, prev4)
    t4 = (len(r4["unaccounted"]) == 1 and abs(r4["unaccounted"][0].get("gap", 0)) == 500_000)
    ok += t4
    if not t4:
        fails.append(f"T4 金額對不上 未指名差額（unacc={r4['unaccounted']}）")

    # T5 門檻邊界：Δ 299,999 → 不觸發
    cur5 = mk("2026-10-16", 26_980_846, 2_896_257,
              comp={"證券": 1_412_360, "平台基金": 954_078, "保單穿透": 529_819})
    r5 = analyze(cur5, prev)
    t5 = (not r5["items"] and not r5["unaccounted"])
    ok += t5
    if not t5:
        fails.append(f"T5 門檻邊界 誤觸發（items={r5['items']}）")

    print(f"check_bucket_attribution 測試：{ok}/5 PASS")
    for f in fails:
        print("  ❌", f)
    return 0 if ok == 5 else 1


if __name__ == "__main__":
    raise SystemExit(run())
