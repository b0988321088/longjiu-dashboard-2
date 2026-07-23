#!/usr/bin/env python3
"""budget_daily_check.py - 每週信用卡預算管家"""

from pathlib import Path
import csv

BASE = Path(__file__).resolve().parent
REPORT = BASE / "BUDGET_WEEKLY_REPORT.md"

BUDGET = {
    "玉山": 10569,
    "台新": 6763,
    "永豐": 6135,
    "台北富邦": 4203,
}

CARDS = list(BUDGET.keys())


def parse_moneybook_bill():
    """從 MB 最新帳單 CSV 讀取信用卡本期應付金額"""
    _mb_dir = BASE / "moneybook"
    _mb_bill = sorted(_mb_dir.glob("*帳單*.csv"), reverse=True)
    if not _mb_bill:
        return None
    expenses = {card: 0 for card in CARDS}
    _cc_map = {"玉山銀行": "玉山", "台新銀行": "台新", "永豐銀行": "永豐", "台北富邦": "台北富邦"}
    _latest = {}
    try:
        with open(_mb_bill[0], "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                bank = row.get("金融機構", "")
                if bank in _cc_map:
                    due = row.get("繳費截止日", "")
                    amt = float(row.get("帳單金額", 0))
                    if bank not in _latest or due > _latest[bank][0]:
                        _latest[bank] = (due, amt)
        for bank, (_, amt) in _latest.items():
            if amt > 0:
                expenses[_cc_map[bank]] = int(amt)
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
    expenses = parse_moneybook_bill()
    if expenses is None:
        expenses = {card: 0 for card in CARDS}
    report = calculate_budget_status(expenses)
    print(report)
    print("Report written to {}".format(REPORT))


if __name__ == "__main__":
    main()
