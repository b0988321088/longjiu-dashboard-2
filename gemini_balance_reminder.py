"""Gemini 餘額提醒（每3天）— no_agent 版。
每次執行必定輸出一則簡短提醒（每3天一則，不洗版）。
資料源：longjiu_system/data/gemini_cost_log.json + 2026-08-01 查得之常數。
"""
import json
from datetime import date, timedelta
from pathlib import Path

LJ = Path.home() / "Desktop" / "longjiu_system"
LOG = LJ / "data" / "gemini_cost_log.json"

# 最後已知狀態（2026-08-01 查得；8/1 入帳 NT$1,400，抵銷 7 月超用 -1,001 後剩 399）
BALANCE_TWD = 399
BALANCE_DATE = date(2026, 8, 1)
DAILY_BURN_TWD = 34
TOPUP_SUGGEST_TWD = 1000


def main():
    today = date.today()
    bal = BALANCE_TWD
    log_note = "log 無新異動"
    if LOG.exists():
        try:
            data = json.loads(LOG.read_text(encoding="utf-8"))
            aug = data.get("2026-08", {})
            if isinstance(aug, dict) and aug.get("balance_twd") is not None:
                bal = float(aug["balance_twd"])
            upd = data.get("updated", "")
            if upd:
                log_note = f"log 更新於 {upd}"
        except Exception as e:
            log_note = f"log 讀取失敗：{e}"

    days_total = max(int(bal / DAILY_BURN_TWD), 0)
    end_date = BALANCE_DATE + timedelta(days=days_total)
    remaining = max((end_date - today).days, 0)

    lines = [f"💰 Gemini 費用提醒（{today.month}/{today.day}）："]
    lines.append(f"- 餘額 NT${bal:.0f}（{BALANCE_DATE.month}/{BALANCE_DATE.day} 查得，{log_note}）")
    lines.append(f"- 日耗約 NT${DAILY_BURN_TWD} → 預估 {end_date.month}/{end_date.day} 用完（剩約 {remaining} 天）")
    if remaining <= 5:
        lines.append(f"- ⚠️ 快用完了！建議盡快儲值 NT${TOPUP_SUGGEST_TWD}（約可撐 1 個月）")
    else:
        lines.append(f"- 建議儲值 NT${TOPUP_SUGGEST_TWD}（約可撐 1 個月）")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
