"""rebalance_sameday_gate.py — 週六再平衡同日去重 gate（P3.1, 2026-09-06）

作為 cron prerun script（wake-gate）：當日已產出 rebalance_summary_{today}.md
→ 末行輸出 {"wakeAgent": false} → agent 完全跳過（零 LLM 零推播），
防止同日重複執行（9/5 曾 16:03 + 20:58 雙跑 = 重複燒 ~1.8 CNY）。
未產出 → 空輸出 → 正常喚醒。

強制重跑方式：先刪除 rebalance_summary_{today}.md 再手動 run。
純 stdlib；輸出禁止時間戳。
"""
import sys
from datetime import date
from pathlib import Path

LJ = Path.home() / "Desktop" / "longjiu_system"


def gate(today: str) -> str:
    """回傳 gate 輸出：同日已產出 → wakeAgent false；否則空字串。純函數供測試。"""
    if (LJ / f"rebalance_summary_{today}.md").exists():
        return '{"wakeAgent": false}'
    return ""


def main() -> None:
    out = gate(date.today().isoformat())
    if out:
        print(out)


if __name__ == "__main__":
    main()
