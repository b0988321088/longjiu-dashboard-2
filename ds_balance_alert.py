"""DeepSeek 餘額警報 — no_agent watchdog。
先跑 cost_monitor.py 更新 cost_log.csv / daily_analysis.json（維持歷史記錄），
再依門檻決定輸出：餘額 < 50 CNY 或剩餘天數 < 7 → 印出警報（傳送）；否則靜默（不發訊息）。
2026-08-27：加月預算制（每月上限 400 CNY，用滿 80% 提醒檢討）。
"""
import json
import subprocess
import sys
import csv
from datetime import datetime
from pathlib import Path

LJ = Path.home() / "Desktop" / "longjiu_system"
COST = LJ / "cost_monitor.py"
DA = LJ / "daily_analysis.json"
LOG = LJ / "cost_log.csv"

THRESHOLD_BALANCE_CNY = 50.0
THRESHOLD_DAYS = 7
MONTHLY_BUDGET_CNY = 400.0
BUDGET_WARN_RATIO = 0.8


def monthly_spend() -> float:
    """本月（cost_log 同月日期）累計花費 CNY"""
    if not LOG.exists():
        return 0.0
    month = datetime.now().strftime("%Y-%m")
    total = 0.0
    try:
        for row in csv.DictReader(LOG.open(encoding="utf-8")):
            if str(row.get("date", "")).startswith(month):
                total += float(row.get("daily_cost_cny", 0) or 0)
    except Exception:
        pass
    return total


def main():
    # 1) 跑 cost_monitor.py：更新 cost_log.csv 與 daily_analysis.json（含最新餘額）
    try:
        subprocess.run([sys.executable, str(COST)], cwd=str(LJ),
                       capture_output=True, timeout=90)
    except Exception as e:
        print(f"⚠️ DeepSeek 餘額檢查失敗（cost_monitor 執行錯誤）：{e}")
        return

    # 2) 從 daily_analysis.json 讀最新數據
    if not DA.exists():
        print("⚠️ DeepSeek 餘額檢查：無法讀取 daily_analysis.json")
        return
    try:
        data = json.loads(DA.read_text(encoding="utf-8"))
        info = data.get("deepseek_cost", {})
        bal = float(info.get("balance", 0) or 0)
        days = int(info.get("estimated_days", 999) or 999)
    except Exception as e:
        print(f"⚠️ DeepSeek 餘額檢查失敗：{e}")
        return

    # 3) 月預算檢查（2026-08-27 新增）
    spent = monthly_spend()
    budget_msgs = []
    if spent > BUDGET_WARN_RATIO * MONTHLY_BUDGET_CNY:
        budget_msgs.append(
            f"📊 本月 DS 已用 {spent:.0f}/{MONTHLY_BUDGET_CNY:.0f} CNY（{spent/MONTHLY_BUDGET_CNY*100:.0f}%），"
            f"接近月預算上限，建議檢討任務清單。")

    # 4) 門檻判斷
    if bal < THRESHOLD_BALANCE_CNY or days < THRESHOLD_DAYS:
        print(f"⚠️ DeepSeek 餘額警報：{bal:.2f} CNY（約 {bal*4.2:.0f} 台幣），"
              f"預估僅剩 {days} 天，建議盡快儲值。")
    if budget_msgs:
        print("\n".join(budget_msgs))
    # 未達門檻 → 無輸出（靜默）


if __name__ == "__main__":
    main()
