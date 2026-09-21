# -*- coding: utf-8 -*-
"""質押狀態文字唯一來源（動態，2026-09-13 建立）

背景：質押敘述句原本被「貼死」在各生成腳本裡（build_*／run_daily／institutional_flow），
使用者裁示改了 snapshot 之後，報表文字不會跟著動 → 每個腳本各寫一份、各自過期。

鐵則：任何腳本要輸出質押敘述，一律呼叫 pledge_status_line() / pledge_facts()，
不得再自行寫死文字或金額。資料源（皆為 snapshot 真值）：
  - cathay_pledge_0911   擔保池／額度／成數／利率／撥款狀態／撥款預估日
  - policy_pledge_loan + liabilities_build_up.券商質押  清償目標與其利率
  - ruling_20260912      用途裁示（540萬全數優先清償高息負債）
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def load_snapshot() -> dict:
    return json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))


def _is_paid(p: dict) -> bool:
    """「是否已撥款」：優先吃 snapshot 明示布林；沒有布林時才退回文字判斷。
    （2026-09-21 實踩：純文字判斷下，撥款欄改成「預計 9/29」就讓判斷回 True → 全系統誤報已撥款。）"""
    flag = p.get("已撥款")
    if isinstance(flag, bool):
        return flag
    txt = str(p.get("撥款") or "")
    return bool(txt) and ("未撥款" not in txt) and ("預計" not in txt)


def _wan(v: float) -> str:
    if v is None:
        return "—"
    return f"{v / 10000:,.0f}萬"


def pledge_facts(snap: dict | None = None) -> dict:
    """把質押相關真值集中算出，回傳 dict（不做任何寫死）。"""
    s = snap or load_snapshot()
    p = s.get("cathay_pledge_0911", {}) or {}
    pool = p.get("額度_本金") or 0
    amt = p.get("可貸金額") or 0
    rate_pct = p.get("利率") or "—"
    try:
        rate = float(str(rate_pct).replace("%", "")) / 100.0
    except ValueError:
        rate = 0.0

    lb = s.get("liabilities_build_up", {}) or {}
    target = (s.get("policy_pledge_loan") or 0) + (lb.get("券商質押") or 0)
    r_policy = s.get("policy_pledge_rate") or 0
    r_broker = lb.get("券商質押利率") or 0
    # 被清償負債的加權月息 vs 質押新增月息
    old_month = ((s.get("policy_pledge_loan") or 0) * r_policy
                 + (lb.get("券商質押") or 0) * r_broker) / 12
    new_month = amt * rate / 12
    net_save_month = old_month - new_month

    return {
        "池本金": pool,
        "池本金萬": _wan(pool),
        "成數": p.get("成數_數值") or (amt / pool if pool else 0),
        "成數文字": f"{(p.get('成數_數值') or (amt / pool if pool else 0)) * 10:.1f}成",
        "可貸": amt,
        "可貸萬": _wan(amt),
        "利率": rate,
        "利率文字": f"{rate_pct}" if isinstance(rate_pct, str) else f"{rate * 100:.2f}%",
        "對保": p.get("對保") or "",
        "對保摘要": p.get("對保摘要") or "",
        "撥款": p.get("撥款") or "",
        "撥款預估日": p.get("撥款預估日") or "",
        "已撥款": _is_paid(p),
        "用途": p.get("用途") or "",
        "清償目標": target,
        "清償目標萬": _wan(target),
        "保單借貸": s.get("policy_pledge_loan") or 0,
        "保單利率": r_policy,
        "券商質押": lb.get("券商質押") or 0,
        "券商利率": r_broker,
        "月息_舊": old_month,
        "月息_新": new_month,
        "月省息": net_save_month,
        "LTV": p.get("LTV") or "",
        "裁示日": "2026-09-12",
    }


def pledge_status_line(snap: dict | None = None, style: str = "full") -> str:
    """質押狀態句。

    style="full"  → 報表/日報用完整句（含用途）
    style="short" → 卡片/表格用一句話
    style="card"  → 排程卡用（含撥款預估日）
    """
    f = pledge_facts(snap)
    base = (f"擔保池 {f['池本金萬']}（富達600＋聯博100＋貝萊德B11 500）×{f['成數文字']}"
            f" = {f['可貸萬']}@{f['利率文字']}")
    if f["已撥款"]:
        pay_status = "已撥款"
    else:
        # 文字一律由 snapshot 欄位組出（不得再寫死「對保完成後約 2 週」這類會過期的描述）
        _dj = f.get("對保摘要") or ""
        if not _dj:
            _d = str(f.get("對保") or "")
            _dj = _d.split("（")[0].replace("✅", "").strip() if _d else ""
        _parts = [x for x in (_dj, (f"預計 {f['撥款預估日']} 撥款" if f["撥款預估日"] else "")) if x]
        pay_status = "❌ 尚未撥款" + (f"（{'；'.join(_parts)}）" if _parts else "")
    use = (f"用途：優先清償 {f['清償目標萬']}高息負債（保單質押 {_wan(f['保單借貸'])}"
           f"@{f['保單利率'] * 100:.1f}% ＋ 券商質押 {_wan(f['券商質押'])}"
           f"@{f['券商利率'] * 100:.2f}%）— 月息 {f['月息_舊']:,.0f} → {f['月息_新']:,.0f}"
           f"，月省約 {f['月省息']:,.0f}（{f['裁示日']} 裁示；10月標案押標金不預留，9月底評估）")

    if style == "short":
        return f"質押 {f['可貸萬']}@{f['利率文字']}（{pay_status}）"
    if style == "card":
        return (f"整池 {f['池本金萬']}×{f['成數文字']} = {f['可貸萬']}@{f['利率文字']}質押"
                f"（{pay_status}）")
    return f"🔍 質押：{base}；{pay_status} → {use}"


if __name__ == "__main__":
    for st in ("full", "short", "card"):
        print(f"[{st}] {pledge_status_line(style=st)}")
