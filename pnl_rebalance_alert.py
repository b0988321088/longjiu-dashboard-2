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
    lines = ["🔴 **獲利超標提醒：以下部位已賺 >20%，強制進行再平衡評估**"]
    for h in over:
        lines.append(
            f"- {h.get('ticker','?')} {h.get('name','?')}："
            f"**+{h.get('pnl_pct',0):.1f}%**（+{h.get('pnl',0):,.0f} 元，市值 {h.get('value',0):,.0f}）"
        )
    total_pnl = sum(h.get("pnl", 0) for h in over)
    lines.append(f"\n合計未實現獲利：+{total_pnl:,.0f} 元")
    lines.append("📌 建議：依再平衡紀律評估——大盤指數型（0050/006208/009816）可部分獲利了結轉防守，或續抱至超配觸發；高股息（0056）達 +40% 優先檢視。")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
