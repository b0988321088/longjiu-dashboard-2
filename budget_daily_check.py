#!/usr/bin/env python3
"""budget_daily_check.py - 每週信用卡預算管家"""

from pathlib import Path
import csv

BASE = Path("C:/Users/bot/Desktop/龍九系統")
REPORT = BASE / "BUDGET_WEEKLY_REPORT.md"

BUDGET = {
    "玉山": 10569,
    "台新": 6763,
    "永豐": 6135,
    "台北富邦": 4203,
}

CARDS = list(BUDGET.keys())


def parse_moneybook_csv():
    csv_files = list(BASE.glob("*.csv"))
    if not csv_files:
        return None
    csv_path = max(csv_files, key=lambda p: p.stat().st_mtime)
    expenses = {card: 0 for card in CARDS}
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                desc = str(row.get("description", "") + row.get(" Desc", "")).lower()
                amount = float(row.get("amount", 0))
                for card in CARDS:
                    if card.lower() in desc and amount > 0:
                        expenses[card] += amount
    except Exception as e:
        print("CSV parse error: {}".format(e))
        return None
    return expenses


def calculate_budget_status(expenses):
    total_budget = sum(BUDGET.values())
    total_actual = sum(expenses.values())
    variance = total_actual - total_budget
    now_str = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = []
    lines.append("# 每週預算報告")
    lines.append("")
    lines.append("生成時間：{}".format(now_str))
    lines.append("")
    lines.append("## 信用卡明細")
    lines.append("")
    lines.append("| 信用卡 | 預算 | 實際 | 差異 | 狀態 |")
    lines.append("|--------|------|------|------|------|")
    for card in CARDS:
        budget = BUDGET[card]
        actual = expenses.get(card, 0)
        diff = actual - budget
        status = "✅ 額度內" if diff <= 0 else "⚠️ 超支"
        lines.append("| {} | {:,} | {:,.0f} | {:+,.0f} | {} |".format(card, budget, actual, diff, status))
    status = "✅ 總額度內" if variance <= 0 else "⚠️ 總超支"
    lines.append("| **四大主力合計** | **{:,}** | **{:,.0f}** | **{:+,.0f}** | **{}** |".format(
        total_budget, total_actual, variance, status))
    lines.append("")
    lines.append("## 異常警示")
    lines.append("")
    alerts = []
    for card in CARDS:
        actual = expenses.get(card, 0)
        if actual > BUDGET[card] * 1.2:
            alerts.append("- ⚠️ {} 超支 {:.0f}%".format(card, (actual / BUDGET[card] - 1) * 100))
        elif actual > BUDGET[card]:
            alerts.append("- ⚠️ {} 超支 {:.0f}%（輕微）".format(card, (actual / BUDGET[card] - 1) * 100))
    if not alerts:
        lines.append("- ✅ 無異常，四大主力皆在預算範圍內")
    else:
        lines.extend(alerts)
    lines.append("")
    lines.append("## 現金流影響")
    lines.append("")
    monthly_expense_expected = 141958
    lines.append("- 信用卡四大主力：{:,.0f} TWD".format(total_actual))
    lines.append("- 月支出基线：{:,} TWD".format(monthly_expense_expected))
    lines.append("- 預算衝擊：{:+,.0f} TWD".format(variance))
    lines.append("")

    report = "\n".join(lines)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(report)
    return report


def main():
    expenses = parse_moneybook_csv()
    if expenses is None:
        expenses = {card: 0 for card in CARDS}
    report = calculate_budget_status(expenses)
    print(report)
    print("Report written to {}".format(REPORT))


if __name__ == "__main__":
    main()
