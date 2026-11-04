#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_retirement_rebalance_live.py — 退休規劃頁／再平衡評估頁「應跟隨 snapshot 的欄位」回歸

2026-10-15 使用者裁決（限縮修復）：只修**已確認應跟隨最新 snapshot** 的欄位；政策值與
帶 as-of 標記的歷史段落必須原樣保留。本測試同時驗「舊值不得殘留」與「政策值不得被改」。

A. retirement_plan_<T>.html
   - 不得殘留：舊可動用 639,661／舊真值 1,055,740／舊跑道 986 天・598 天／舊壓力覆蓋 115.3%
   - 必須出現：可動用 1,170,934（live）／跑道 1,094 天（live）／壓力覆蓋 118.6%
   - 政策值不動：底線 700,000／自由現金門檻 1,000,000／跑道門檻 540 天／加碼級 150%
B. rebalance_eval_<T>.html
   - 不得殘留：26,970,031／1,055,740／355,740／1,726,082／36.4%／26.4%／3.9%／66.0%
   - 必須出現：27,085,225／1,170,934／1,679,284／36.2%／26.3%／4.3%／65.7%
   - 政策值不動：桶目標 10%／30%／25%／5%／防守門檻 60／單筆上限 200,000
C. 單元：sot_targets.refresh_rebalance_live_numbers 之覆蓋與冪等；缺 snapshot 時不得謊報
D. 守門有牙（負向自測）：植入舊值必須被判不通過
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

T = date.today().isoformat()
PASS = FAIL = 0
FAILS: list[str] = []


def ck(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILS.append(name)
        print(f"  ❌ {name}｜{detail}")


# ── 期望值一律由 snapshot 單一入口派生（2026-10-15 修）
#   原為硬編碼字面值，證券真值更新後「產品已修正、測試反而 FAIL」（例：總資產 27,085,225→26,992,475、
#   防守合併 65.7%→65.9%）。硬編碼會腐化，故改為每次從 snapshot／canonical 函式即時派生；
#   「舊值不得殘留」清單同步扣除與 live 值相同的字串（同一值不可能既是必禁又是必現）。
import sot_targets as _st  # noqa: E402

_S0 = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
_TOT_S = f"{int(_S0['total_assets']):,}"
_AVAIL_S = f"{int(round(_st.allowable_cash(_S0))):,}"
_DEF_S = f"{float(_st.defensive_caliber(_S0)['佔比']):.1f}%"
_AT = (_S0.get("penetration") or {}).get("actual_twd") or {}


def _bpct(key: str) -> str:
    v = _AT.get(key)
    return f"{float(v) / float(_S0['total_assets']) * 100:.1f}%" if v else ""


_TW_S, _US_S, _DEFB_S = _bpct("台股市值型成長"), _bpct("美股市值型成長"), _bpct("防守型配息")
_BOND_S, _CASH_S = _bpct("債券"), _bpct("現金/安全網")

RET_STALE = tuple(k for k in ("639,661", "1,055,740", "986 天", "598 天", "115.3%")
                  if k not in (_AVAIL_S,))
RET_LIVE = tuple(k for k in (_AVAIL_S, "1,094 天", "118.6%") if k)
RET_POLICY = ("700,000", "1,000,000", "540 天", "150%")

_RBL_STALE_RAW = ("26,970,031", "1,055,740", "355,740", "1,726,082", "36.4%", "26.4%", "3.9%", "66.0%")
RBL_LIVE = tuple(k for k in (_TOT_S, _AVAIL_S, _US_S, _DEFB_S, _BOND_S, _CASH_S, _DEF_S, _TW_S) if k)
RBL_STALE = tuple(k for k in _RBL_STALE_RAW if k not in RBL_LIVE)
RBL_POLICY = (">10%<", ">30%<", ">25%<", ">5%<", "門檻 60", "200,000")


def body(p: Path) -> str:
    t = p.read_text(encoding="utf-8", errors="replace")
    return re.sub(r"<[^>]+>", " ", t)


def check_tokens(label: str, text: str, stale=(), live=(), policy=()) -> None:
    s = {k: text.count(k) for k in stale if text.count(k)}
    ck(f"{label}：無舊值殘留", not s, f"殘留 {s}")
    l = {k: text.count(k) for k in live if not text.count(k)}
    ck(f"{label}：live 值已出現", not l, f"缺 {l}")
    p = {k: (text.count(k), text.count(k) - body_orig_count.get(k, 0)) for k in ()}
    return None


body_orig_count: dict[str, int] = {}

print("═══ A. retirement_plan（退休規劃／留停 Gate 頁）═══")
f = BASE / f"retirement_plan_{T}.html"
if not f.exists():
    ck(f"A0 {f.name} 存在", False, "找不到當日產物")
else:
    t = body(f)
    stale = {k: t.count(k) for k in RET_STALE if t.count(k)}
    ck("A1 無舊值殘留（639,661／1,055,740／986 天／598 天／115.3%）", not stale, f"殘留 {stale}")
    live = {k: t.count(k) for k in RET_LIVE if not t.count(k)}
    ck("A2 live 值已出現（1,170,934／1,094 天／118.6%）", not live, f"缺 {live}")
    pol = {k: t.count(k) for k in RET_POLICY if not t.count(k)}
    ck("A3 政策值保留（底線 700,000／門檻 1,000,000／540 天／150%）", not pol, f"缺 {pol}")
    ck("A4 留停 Gate 敘述與 live 一致（🟢 GO）", "🟢 GO" in t, "未見 GO 級判定")

print("═══ B. rebalance_eval（再平衡評估頁）═══")
f = BASE / f"rebalance_eval_{T}.html"
if not f.exists():
    ck(f"B0 {f.name} 存在", False, "找不到當日產物")
else:
    t = body(f)
    stale = {k: t.count(k) for k in RBL_STALE if t.count(k)}
    ck("B1 無舊值殘留（總資產／可動用／理論調整／五桶佔比）", not stale, f"殘留 {stale}")
    live = {k: t.count(k) for k in RBL_LIVE if not t.count(k)}
    ck("B2 live 值已出現（27,085,225／1,679,284／36.2%／26.3%／4.3%／65.7%）", not live, f"缺 {live}")
    raw = f.read_text(encoding="utf-8", errors="replace")
    pol = {k: raw.count(k) for k in RBL_POLICY if not raw.count(k)}
    ck("B3 政策值保留（桶目標 10/30/25/5、門檻 60、單筆上限 200,000）", not pol, f"缺 {pol}")
    ck("B4 帶 as-of 標記的歷史段落原樣保留",
       "本節為 2026-10-13 版" in t or "尚未更新至" in t,
       "未見 as-of 標記（可能被誤改）")

print("═══ C. 單元：覆蓋函式（含冪等）═══")
try:
    import sot_targets as st
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    src = BASE / f"rebalance_summary_{T}.md"
    md = src.read_text(encoding="utf-8") if src.exists() else ""
    ck("C0 測試資料可得（snapshot ＋ 當日 rebalance_summary）", bool(snap and md), "缺資料")
    fixed = st.refresh_rebalance_live_numbers(st.refresh_stale_amounts(md, snap), snap)
    n_stale = {k: fixed.count(k) for k in RBL_STALE if fixed.count(k)}
    ck("C1 覆蓋後片段無舊值", not n_stale, f"殘留 {n_stale}")
    ck("C2 冪等（重跑結果相同）",
       st.refresh_rebalance_live_numbers(fixed, snap) == fixed, "非冪等 → 會累積漂移")
    ck("C3 政策值未被覆蓋（桶目標與門檻）",
       all(fixed.count(k) == md.count(k) for k in RBL_POLICY),
       "政策值被改動")
    ck("C4 缺 penetration 時不改寫（fail-visible，不謊報）",
       st.refresh_rebalance_live_numbers(md, {"total_assets": 100}) == md, "無真值仍改寫")

    print("═══ D. 守門有牙（負向自測）═══")
    planted = (md.replace("五桶 25,343,696", "五桶 26,970,031")
                  .replace("五桶 25,228,502", "五桶 26,970,031")
                  .replace("＝ 總資產 27,085,225", "＝ 總資產 26,970,031")
                  .replace("＝總資產 27,085,225", "＝總資產 26,970,031")
                  .replace("分母 27,085,225", "分母 26,970,031"))
    knocked = st.refresh_rebalance_live_numbers(planted, snap)
    ck("D1 植入舊值後，覆蓋函式必須消除它（有牙）", "26,970,031" not in knocked,
       "植入後仍殘留 → 規則失效")
    ck("D2 守門能辨識未覆蓋文本（負向）",
       any(k in planted for k in RBL_STALE), "植入樣本本身失效")
except Exception as e:  # noqa: BLE001
    ck("C/D 單元測試執行", False, f"{type(e).__name__}: {e}")

print("\n" + "=" * 54)
print(f"測試結果：{PASS} PASS / {FAIL} FAIL")
if FAILS:
    print("失敗項：" + "、".join(FAILS))
sys.exit(1 if FAIL else 0)
