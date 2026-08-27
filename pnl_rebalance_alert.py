#!/usr/bin/env python3
"""pnl_rebalance_alert.py — 獲利 >20% 強制提醒（2026-08-27 使用者裁示）

規則：任一證券部位報酬率 ≥ 20% → 輸出提醒（TG 主動通知「強制再平衡評估」）
無任何部位 ≥20% → 靜默（watchdog 模式）

資料源：snapshot.json securities.holdings（成本 vs 現價 = 真值）
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
THRESHOLD = 20.0  # 獲利門檻 %

# 繼續持有部位（2026-08-27 使用者裁示：不因獲利>20% 觸發賣出建議）
# 核心長抱（台50 指數核心）：僅超配>5pp 或科技紅線才評估
CORE_HOLD = {"0050", "006208", "009816"}
# 質押中續抱：0056（8/27 裁示：質押狀況下繼續放著，不賣）
PLEDGED_HOLD = {"0056"}


def main():
    if not SNAP.exists():
        return
    try:
        snap = json.loads(SNAP.read_text(encoding="utf-8"))
    except Exception:
        return
    holdings = (snap.get("securities") or {}).get("holdings", [])
    if not holdings:
        return

    over = [h for h in holdings if (h.get("pnl_pct") or 0) >= THRESHOLD]
    if not over:
        return  # 靜默

    over.sort(key=lambda x: -(x.get("pnl_pct") or 0))
    core = [h for h in over if h.get("ticker") in CORE_HOLD]
    pledged = [h for h in over if h.get("ticker") in PLEDGED_HOLD]
    others = [h for h in over if h.get("ticker") not in CORE_HOLD and h.get("ticker") not in PLEDGED_HOLD]

    lines = ["🔴 **獲利超標提醒：以下部位已賺 >20%**"]
    if core:
        lines.append("\n✅ **核心長抱（不賣，僅超配>5pp 或科技紅線才評估）：**")
        for h in core:
            lines.append(
                f"- {h.get('ticker','?')} {h.get('name','?')}："
                f"**+{h.get('pnl_pct',0):.1f}%**（+{h.get('pnl',0):,.0f} 元，市值 {h.get('value',0):,.0f}）"
            )
    if pledged:
        lines.append("\n🔒 **質押中續抱（不賣）：**")
        for h in pledged:
            lines.append(
                f"- {h.get('ticker','?')} {h.get('name','?')}："
                f"**+{h.get('pnl_pct',0):.1f}%**（+{h.get('pnl',0):,.0f} 元，市值 {h.get('value',0):,.0f}）"
            )
    if others:
        lines.append("\n⚠️ **建議再平衡評估（非核心，可考慮部分獲利了結）：**")
        for h in others:
            lines.append(
                f"- {h.get('ticker','?')} {h.get('name','?')}："
                f"**+{h.get('pnl_pct',0):.1f}%**（+{h.get('pnl',0):,.0f} 元，市值 {h.get('value',0):,.0f}）"
            )
    if others:
        lines.append("\n📌 依再平衡紀律評估是否部分獲利了結；核心長抱部位續抱。")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
