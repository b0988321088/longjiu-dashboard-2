"""安聯保單（A/B）真值寫入的單一入口 —— 2026-11-11 建立。

為什麼要有這支：11/11 14:59 更新保單B 時，逐檔明細只寫進 `allianz_b_update_20261111`，
canonical `allianz_b_breakdown` 沒動 → 收工檢查的「保單不變式」紅燈，且金額差 37,821
在兩個欄位裡各說各話。同日 A 只有總值沒逐檔，差 2,767 也沒有任何欄位承接。

這支把「寫總值」與「寫逐檔」綁成同一個動作，並在函式內硬性 assert：
  1) 有明細 → 逐檔加總必須等於總值，且明細立刻成為 canonical breakdown（不留在 update 字典裡）。
  2) 只有總值 → breakdown 不動，差額寫進 `allianz_{a,b}_detail_gap`（含 amount/reason/source/as_of），
     且 |差額| ≤ 0.5% 總值；超過就 raise，不准靜默吞掉。
  3) 派生合計（allianz_ab_current_value / allianz_ab / insurance_breakdown.*）同一次寫完。
  4) 不動負債與淨值（那是 rebuild_liabilities 的職責）。

用法：
    from allianz_sync import apply_policy_update, apply_allianz_snapshot
    apply_policy_update(snap, "b", total=2472783, funds={...}, source="安聯 App 14:59", as_of="2026-11-11")

自測：python allianz_sync.py --selftest
"""
from __future__ import annotations

import copy
import re

GAP_LIMIT_PCT = 0.005          # 宣告差額上限 0.5%
_POLICY_ALIASES = {
    "a": ("allianz_policy_a_value", "allianz_a_current_value", "allianz_a", "allianz_a_value", "allianz_a_funds"),
    "b": ("allianz_policy_b_value", "allianz_b_current_value", "allianz_b", "allianz_b_value", "allianz_b_funds"),
}
_IB_KEY = {"a": "policy_a_total", "b": "policy_b_total"}
_IB_FUNDS = {"a": "policy_a_funds", "b": "policy_b_funds"}


def _sum_funds(funds: dict) -> float:
    return float(sum(v for v in (funds or {}).values() if isinstance(v, (int, float))))


def apply_policy_update(snap: dict, policy: str, *, total: float | None = None,
                        funds: dict | None = None, source: str, as_of: str,
                        note: str | None = None, keep_update_dict: bool = True) -> dict:
    """寫入單一保單（A/B）的總值與（可選）逐檔，並維持不變式。回傳變更摘要。"""
    tag = policy.lower()
    if tag not in ("a", "b"):
        raise ValueError(f"policy 必須是 'a' 或 'b'，收到 {policy!r}")
    if total is None and not funds:
        raise ValueError("total 與 funds 至少要給一個（不要用空更新洗掉真值）")
    source = (source or "").strip()
    as_of = (as_of or "").strip()
    if not source or not as_of:
        raise ValueError("source 與 as_of 為必填（宣告差額與審計要靠它）")

    bd_key = f"allianz_{tag}_breakdown"
    cur_bd = {k: v for k, v in (snap.get(bd_key) or {}).items() if isinstance(v, (int, float))}
    cur_sum = _sum_funds(cur_bd)

    if funds:
        new_bd = {k: v for k, v in funds.items() if isinstance(v, (int, float))}
        got = _sum_funds(new_bd)
        if total is None:
            total = got
        if abs(got - float(total)) >= 1:
            raise AssertionError(
                f"保單{tag.upper()} 逐檔合計 {got:,.0f} ≠ 總值 {float(total):,.0f}"
                f"（差 {got - float(total):,.0f}）→ 先確認截圖，不要硬寫")
        snap[bd_key] = new_bd
        gap = 0.0
        gap_reason = "明細與總值一致"
    else:
        total = float(total)
        new_bd = cur_bd
        gap = round(total - cur_sum, 2)
        gap_reason = note or "僅總值更新（逐檔沿用前次評價值，屬評價日差）"
        if abs(gap) > abs(total) * GAP_LIMIT_PCT:
            raise AssertionError(
                f"保單{tag.upper()} 差額 {gap:,.0f} 超過容許上限 {abs(total) * GAP_LIMIT_PCT:,.0f}（0.5%）"
                f"→ 逐檔必須一併更新（breakdown {cur_sum:,.0f} vs 總值 {total:,.0f}）")

    # 總值：所有同義欄位一次寫齊（避免只改到其中一個）
    for k in _POLICY_ALIASES[tag]:
        if k in snap or k in ("allianz_policy_a_value", "allianz_a_current_value",
                              "allianz_policy_b_value", "allianz_b_current_value"):
            snap[k] = int(total)

    # 宣告差額（0 也寫，讓「已核對」與「沒人管」在資料上分得開）
    snap[f"allianz_{tag}_detail_gap"] = {
        "amount": gap, "as_of": as_of, "reason": gap_reason, "source": source,
        "next": "下次逐檔截圖時歸零" if gap else "—",
    }

    # 派生合計
    ib = snap.setdefault("insurance_breakdown", {})
    ib[_IB_KEY[tag]] = int(total)
    if funds:
        ib[_IB_FUNDS[tag]] = dict(snap[bd_key])
    ab = int(snap.get("allianz_policy_a_value") or 0) + int(snap.get("allianz_policy_b_value") or 0)
    snap["allianz_ab_current_value"] = ab
    snap["allianz_ab"] = ab
    snap["allianz_combined"] = ab
    ib["allianz_ab_total"] = ab

    # 更新字典：與 breakdown 同步（收工檢查會比對這兩者）
    if keep_update_dict:
        key = f"allianz_{tag}_update_{re.sub(r'[^0-9]', '', as_of)[:8]}"
        rec = {"時間": source, "合計": int(total), "前值": int(cur_sum),
               "增減": int(total - cur_sum), "來源": source}
        if funds:
            rec["明細"] = dict(snap[bd_key])
        snap[key] = rec

    return {"policy": tag.upper(), "total": int(total), "breakdown": int(_sum_funds(snap[bd_key])),
            "gap": gap, "source": source, "as_of": as_of}


def apply_allianz_snapshot(snap: dict, *, a_total=None, a_funds=None, b_total=None, b_funds=None,
                           source: str, as_of: str) -> list:
    """A/B 一次寫（合計會重算兩次，成本可忽略）。回傳兩筆摘要。"""
    out = []
    if a_total is not None or a_funds:
        out.append(apply_policy_update(snap, "a", total=a_total, funds=a_funds, source=source, as_of=as_of))
    if b_total is not None or b_funds:
        out.append(apply_policy_update(snap, "b", total=b_total, funds=b_funds, source=source, as_of=as_of))
    return out


def _selftest() -> int:
    base = {"allianz_policy_a_value": 1000, "allianz_a_current_value": 1000,
            "allianz_policy_b_value": 2000, "allianz_b_current_value": 2000,
            "allianz_a_breakdown": {"f1": 600, "f2": 400}, "allianz_b_breakdown": {"g1": 2000},
            "allianz_ab_current_value": 3000, "insurance_breakdown": {}}
    fails = []

    def chk(name, cond):
        print(("  ✅ " if cond else "  ❌ ") + name)
        if not cond:
            fails.append(name)

    # T1 逐檔寫入 → 總值/breakdown/gap 全部一致
    s = copy.deepcopy(base)
    r = apply_policy_update(s, "b", total=2200, funds={"g1": 2200}, source="t", as_of="2026-11-12")
    chk("T1 逐檔寫入後總值=明細", s["allianz_b_breakdown"] == {"g1": 2200} and s["allianz_policy_b_value"] == 2200)
    chk("T1 gap=0", s["allianz_b_detail_gap"]["amount"] == 0)
    chk("T1 合計重算", s["allianz_ab_current_value"] == 3200 and s["insurance_breakdown"]["allianz_ab_total"] == 3200)

    # T2 只有總值、差額在容許內 → 接受並宣告
    s = copy.deepcopy(base)
    apply_policy_update(s, "a", total=1004, source="t", as_of="2026-11-12")
    chk("T2 宣告差額 4", s["allianz_a_detail_gap"]["amount"] == 4 and s["allianz_a_breakdown"] == {"f1": 600, "f2": 400})

    # T3 只有總值、差額過大 → 必須 raise（不准靜默吞）
    s = copy.deepcopy(base)
    try:
        apply_policy_update(s, "a", total=1200, source="t", as_of="2026-11-12")
        chk("T3 差額超限應 raise", False)
    except AssertionError:
        chk("T3 差額超限應 raise", True)

    # T4 逐檔合計對不上總值 → 必須 raise
    s = copy.deepcopy(base)
    try:
        apply_policy_update(s, "b", total=9999, funds={"g1": 2200}, source="t", as_of="2026-11-12")
        chk("T4 明細≠總值應 raise", False)
    except AssertionError:
        chk("T4 明細≠總值應 raise", True)

    # T5 缺 source/as_of → 必須 raise
    s = copy.deepcopy(base)
    try:
        apply_policy_update(s, "b", total=2000, source="", as_of="")
        chk("T5 缺來源應 raise", False)
    except ValueError:
        chk("T5 缺來源應 raise", True)

    # T6 update 字典必須帶明細（收工檢查靠這個比對）
    s = copy.deepcopy(base)
    apply_policy_update(s, "b", total=2200, funds={"g1": 2200}, source="t", as_of="2026-11-12")
    upd = s.get("allianz_b_update_20261112") or {}
    chk("T6 update 字典同步", upd.get("明細") == {"g1": 2200})

    total_checks = 7
    print(f"\n== 結果：{total_checks - len(fails)} PASS / {len(fails)} FAIL ==")
    return 0 if not fails else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
