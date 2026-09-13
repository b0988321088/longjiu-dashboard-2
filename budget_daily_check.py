#!/usr/bin/env python3
"""budget_daily_check.py - 每週信用卡預算管家

資料來源：
1. Moneybook 帳單 CSV（每卡最新繳費截止日）→ 已出帳實繳
2. Moneybook 帳戶 CSV（信用卡未繳餘額）→ 當期循環
"""

from pathlib import Path
from logging_config import get_logger
logger = get_logger("budget_daily_check")
import csv
import os
import re

BASE = Path(__file__).resolve().parent
REPORT = BASE / "BUDGET_WEEKLY_REPORT.md"

BUDGET = {
    "玉山": 10569,
    "台新": 6763,
    "永豐": 6135,
    "台北富邦": 4203,
}

CARDS = list(BUDGET.keys())

_CC_MAP = {"玉山銀行": "玉山", "台新銀行": "台新", "永豐銀行": "永豐", "台北富邦": "台北富邦"}
# Company_Ledger.md §本月支出：信用卡消費 38,000 = 四大主力卡月均（snapshot cc_low 35,000 / cc_mid 38,000 / cc_high 42,000）
LEDGER_BUDGET = 38000
LEDGER_BAND = (35000, 42000)
MONTHLY_EXPENSE = 162781
SAFETY_LINE = 40000  # 玉山/富邦生活帳戶安全線


def _latest(pattern):
    """v2（2026-09-13 INC-159）：跨目錄蒐集後取「檔名日期最大」者。

    原版只掃 BASE 與 BASE/moneybook 且用「字典序第一個」→ repo 只放 7/27 匯出、
    最新 9/02 匯出在 hermes cache 裡，於是永遠讀到舊檔 → 台新被誤報 P1 超支 117%
    （實際循環 4,383、−35%）。修法：納入 cache/documents（含子目錄）並以檔名日期取最新。
    """
    dirs = [BASE, BASE / "moneybook", BASE / "tmp_mb",
            Path.home() / "AppData" / "Local" / "hermes" / "cache" / "documents"]
    files = []
    for d in dirs:
        if not d.exists():
            continue
        files += list(d.glob(pattern))
        files += list(d.glob("*" + os.sep + pattern))
        files += list(d.glob("*" + os.sep + "*" + os.sep + pattern))
    if not files:
        return None

    def _key(p):
        m = re.search(r"(\d{4})(\d{2})(\d{2})", p.name)
        return (m.group(1) + m.group(2) + m.group(3)) if m else "00000000"

    return max(files, key=lambda p: (_key(p), p.stat().st_mtime))


def _date_from_name(p):
    m = re.search(r"(\d{4})(\d{2})(\d{2})", p.name)
    return "{}-{}-{}".format(*m.groups()) if m else p.name


def parse_moneybook_bill():
    """從 MB 最新帳單 CSV 讀取各卡最新一期帳單金額。回傳 (dict, 資料日)"""
    f = _latest("*帳單*.csv")
    if f is None:
        return None, None
    expenses = {card: 0 for card in CARDS}
    latest = {}
    try:
        with open(f, "r", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                bank = row.get("金融機構", "")
                if bank not in _CC_MAP or row.get("帳單類型", "") != "信用卡":
                    continue
                due = row.get("繳費截止日", "")
                amt = float(row.get("帳單金額", 0) or 0)
                if amt <= 0:
                    continue
                if bank not in latest or due > latest[bank][0]:
                    latest[bank] = (due, amt)
        for bank, (due, amt) in latest.items():
            expenses[_CC_MAP[bank]] = int(amt)
    except Exception as e:
        print("CSV parse error: {}".format(e))
        return None, None
    return expenses, _date_from_name(f)


def parse_moneybook_account():
    """從 MB 最新帳戶 CSV 讀取信用卡未繳餘額（當期循環）與帳戶水位。"""
    f = _latest("*帳戶*.csv")
    if f is None:
        return None, {}
    owed = {card: 0 for card in CARDS}
    other = 0
    cash = {}
    banks = {}
    try:
        with open(f, "r", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                if row.get("幣別", "TWD") != "TWD":
                    continue
                inst = row.get("機構名稱", "")
                name = row.get("帳戶名稱", "") or ""
                try:
                    amt = float(row.get("帳戶金額", 0) or 0)
                except ValueError:
                    continue
                if "卡" in name:
                    card = _CC_MAP.get(inst)
                    if amt < 0:
                        if card:
                            owed[card] += int(-amt)
                        else:
                            other += int(-amt)
                    continue
                if "貸款" in name or "房貸" in name:
                    continue
                if inst in ("玉山銀行", "台北富邦", "台新銀行", "永豐銀行") and amt > 0:
                    cash[inst] = cash.get(inst, 0) + amt
                if "活" in name and amt > 0:
                    banks[inst] = banks.get(inst, 0) + amt
    except Exception as e:
        print("Account CSV parse error: {}".format(e))
        return None, {}
    return owed, {"date": _date_from_name(f), "cash": cash, "banks": banks, "other": other}


def _pct(actual, budget):
    return (actual / budget - 1) * 100 if budget else 0.0


def _level(pct):
    if pct >= 20:
        return "🚨 P1"
    if pct >= 10:
        return "⚠️ P2"
    return "✅"


def calculate_budget_status(expenses, bill_date, cycle, acct):
    total_budget = sum(BUDGET.values())
    total_stmt = sum(expenses.values()) if expenses else 0
    total_cycle = sum(cycle.values()) if cycle else 0
    variance = total_cycle - LEDGER_BUDGET
    now_str = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
    today = __import__("datetime").datetime.now().date()

    def _age(d):
        try:
            y, m, dd = [int(x) for x in d.split("-")]
            return (today - __import__("datetime").date(y, m, dd)).days
        except Exception:
            return -1

    lines = []
    lines.append("# 每週預算報告")
    lines.append("")
    lines.append("生成時間：{}".format(now_str))
    lines.append("")
    lines.append("## 信用卡明細")
    lines.append("")
    lines.append("| 信用卡 | 月預算 | 最新一期帳單 | 當期循環未繳 | 差異(循環-預算) | 超支率 | 警示 |")
    lines.append("|--------|------:|------------:|------------:|--------------:|------:|------|")
    for card in CARDS:
        budget = BUDGET[card]
        stmt = expenses.get(card, 0) if expenses else 0
        cur = cycle.get(card, 0) if cycle else 0
        pct = _pct(cur, budget)
        lines.append("| {} | {:,} | {:,} | {:,} | {:+,} | {:+.1f}% | {} |".format(
            card, budget, stmt, cur, cur - budget, pct, _level(pct)))
    lines.append("| **四卡合計** | **{:,}** | **{:,}** | **{:,}** | — | — | — |".format(
        total_budget, total_stmt, total_cycle))
    lines.append("")
    lines.append("> 帳本基準（Company_Ledger.md / snapshot 2026-09-10）：四卡月均 **{:,}**（區間 {:,}–{:,}）；當期循環合計 {:+,} TWD（{:+.1f}%）".format(
        LEDGER_BUDGET, LEDGER_BAND[0], LEDGER_BAND[1], total_cycle - LEDGER_BUDGET, _pct(total_cycle, LEDGER_BUDGET)))
    lines.append("")
    lines.append("## 異常警示")
    lines.append("")
    alerts = []
    for card in CARDS:
        budget = BUDGET[card]
        cur = cycle.get(card, 0) if cycle else 0
        stmt = expenses.get(card, 0) if expenses else 0
        pct = _pct(cur, budget)
        if pct >= 20:
            alerts.append("- 🚨 **P1** {} 超支 {:.1f}%（循環 {:,} vs 預算 {:,}；最新帳單 {:,}）".format(
                card, pct, cur, budget, stmt))
        elif pct >= 10:
            alerts.append("- ⚠️ **P2** {} 超支 {:.1f}%（循環 {:,} vs 預算 {:,}）".format(card, pct, cur, budget))
        elif stmt > budget * 1.2:
            alerts.append("- ⚠️ **P2** {} 上期帳單 {:,} 高於預算 {:,}（{:.1f}%），本期循環已回落".format(
                card, stmt, budget, _pct(stmt, budget)))
    tot_pct = _pct(total_cycle, LEDGER_BUDGET)
    if tot_pct >= 20:
        alerts.append("- 🚨 **P1** 四卡循環合計 {:+,} TWD（{:+.1f}%）超帳本基準 {:,} TWD".format(
            total_cycle - LEDGER_BUDGET, tot_pct, LEDGER_BUDGET))
    elif tot_pct >= 10:
        alerts.append("- ⚠️ **P2** 四卡循環合計 {:+,} TWD（{:+.1f}%）高於帳本基準".format(
            total_cycle - LEDGER_BUDGET, tot_pct))
    if bill_date and _age(bill_date) > 14:
        alerts.append("- 🚨 **P1（資料品質）** 帳單匯出資料日 {}，已 {} 天未更新；循環數據以帳戶 CSV {} 為準".format(
            bill_date, _age(bill_date), acct.get("date", "?")))
    if not alerts:
        lines.append("- ✅ 無異常，四大主力皆在預算範圍內")
    else:
        lines.extend(alerts)
    lines.append("")
    lines.append("## 現金流影響")
    lines.append("")
    other = acct.get("other", 0)
    lines.append("- 四卡當期循環未繳：{:,} TWD".format(total_cycle))
    if other:
        lines.append("- 其他卡（國泰 CUBE 等）當期未繳：{:,} TWD；**全部卡費合計 {:,} TWD**".format(
            other, total_cycle + other))
    lines.append("- 帳本四卡月預算：{:,} TWD（區間 {:,}–{:,}）".format(LEDGER_BUDGET, LEDGER_BAND[0], LEDGER_BAND[1]))
    lines.append("- 月支出基線：{:,} TWD".format(MONTHLY_EXPENSE))
    lines.append("- 相對帳本基準衝擊：{:+,} TWD".format(total_cycle - LEDGER_BUDGET))
    cash = acct.get("cash", {})
    if cash:
        lines.append("- 帳戶水位（{}）：{}".format(
            acct.get("date", "?"), "、".join("{} {:,}".format(k, int(v)) for k, v in sorted(cash.items()))))
        for bank in ("玉山銀行", "台北富邦"):
            bal = cash.get(bank)
            card = _CC_MAP[bank]
            if bal is None:
                continue
            after = int(bal - (cycle.get(card, 0) if cycle else 0))
            flag = "🔴 扣卡費後跌破安全線" if after < SAFETY_LINE else "🟢 安全"
            lines.append("- {} 扣抵 {} 卡費 {:,} 後餘 {:+,}（安全線 {:,}）→ {}".format(
                bank, card, cycle.get(card, 0) if cycle else 0, after, SAFETY_LINE, flag))
    lines.append("")
    lines.append("## 資料來源")
    lines.append("")
    lines.append("- 帳單：{}".format(bill_date or "無"))
    lines.append("- 帳戶/循環：{}".format(acct.get("date", "無")))
    lines.append("- 執行腳本：budget_daily_check.py")
    lines.append("")

    report = "\n".join(lines)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(report)
    return report


def main():
    expenses, bill_date = parse_moneybook_bill()
    cycle, acct = parse_moneybook_account()
    if expenses is None:
        expenses = {card: 0 for card in CARDS}
    if cycle is None:
        cycle = {card: 0 for card in CARDS}
    report = calculate_budget_status(expenses, bill_date, cycle, acct)
    print(report)
    print("Report written to {}".format(REPORT))


if __name__ == "__main__":
    main()
