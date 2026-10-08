#!/usr/bin/env python3
"""budget_daily_check.py - 每週信用卡預算管家

資料來源：
1. Moneybook 帳單 CSV（每卡最新繳費截止日）→ 已出帳實繳
2. Moneybook 帳戶 CSV（信用卡未繳餘額）→ 當期循環
"""

from pathlib import Path
from logging_config import get_logger
logger = get_logger("budget_daily_check")
import mb_source  # 2026-10-08 ②-budget：MB 匯入契約（單一來源；禁自建搜尋路徑）

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
# 2026-10-01 INC-270：原月支出基線常數（8 月口徑）已移除——禁寫死退路。
# 月支出基線一律讀 snapshot 單一入口；缺值即 raise（不以舊值頂替）。
def _monthly_expense_baseline() -> float:
    import json as _json
    from sot_targets import sot_monthly_expense
    return sot_monthly_expense(_json.loads((BASE / "snapshot.json").read_text(encoding="utf-8")))
SAFETY_LINE = 40000  # 玉山/富邦生活帳戶安全線


def _load(kind):
    """走 mb_source 匯入契約（單一來源；消費端不自建搜尋路徑）。

    2026-10-08 SEC-P0／②-budget：原版自掃 4 個目錄且只認 *.csv → 使用者上傳的 ZIP 看不到，
    永遠讀到舊匯出（實測停留 9/02）。契約失敗一律回 (None, 原因)，**不得**退回舊檔。
    """
    try:
        d = mb_source.load(kind)
    except mb_source.MBSourceError as e:
        return None, str(e)
    if d is None:
        return None, f"找不到含「{kind}」的 Moneybook 匯出（ZIP 或 CSV）"
    return d, None


def _safe_float(v):
    try:
        return float(str(v).replace(",", "") or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_moneybook_bill():
    """各卡最新一期帳單金額。回傳 (expenses, meta)。

    meta 語義分離（②-budget C）：export_date＝檔案匯出日（新鮮度）；statement_due＝帳單期別。
    """
    d, err = _load("帳單")
    if d is None:
        print("⚠️ 帳單來源問題：{}".format(err))
        return None, {"error": err, "export_date": None, "statement_due": None}
    expenses = {card: 0 for card in CARDS}
    latest = {}
    for row in d["rows"]:
        bank = row.get("金融機構", "")
        if bank not in _CC_MAP or row.get("帳單類型", "") != "信用卡":
            continue
        due = str(row.get("繳費截止日", "") or "")
        amt = _safe_float(row.get("帳單金額", 0))
        if amt <= 0:
            continue
        if bank not in latest or due > latest[bank][0]:
            latest[bank] = (due, amt)
    for bank, (due, amt) in latest.items():
        expenses[_CC_MAP[bank]] = int(amt)
    return expenses, {"export_date": d["export_date"], "origin": d["origin"],
                      "container": d["container"], "member": d.get("member"),
                      "statement_due": mb_source.latest_statement_due(d["rows"]), "error": None}


def parse_moneybook_account():
    """信用卡未繳餘額（當期循環）與帳戶水位。"""
    d, err = _load("帳戶")
    if d is None:
        print("⚠️ 帳戶來源問題：{}".format(err))
        return None, {"date": None, "export_date": None, "error": err}
    owed = {card: 0 for card in CARDS}
    other = 0
    cash = {}
    banks = {}
    for row in d["rows"]:
        if row.get("幣別", "TWD") != "TWD":
            continue
        inst = row.get("機構名稱", "")
        name = row.get("帳戶名稱", "") or ""
        amt = _safe_float(row.get("帳戶金額", 0))
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
    return owed, {"date": d["export_date"], "export_date": d["export_date"],
                  "origin": d["origin"], "container": d["container"],
                  "cash": cash, "banks": banks, "other": other, "error": None}


def _pct(actual, budget):
    return (actual / budget - 1) * 100 if budget else 0.0


def _level(pct):
    if pct >= 20:
        return "🚨 P1"
    if pct >= 10:
        return "⚠️ P2"
    return "✅"


def calculate_budget_status(expenses, bill_meta, cycle, acct):
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
    lines.append("| 信用卡 | 月預算 | 最新一期帳單 | 當期未繳(全額扣繳) | 差異(帳單-預算) | 消費速度 | 警示 |")
    lines.append("|--------|------:|------------:|------------:|--------------:|------:|------|")
    for card in CARDS:
        budget = BUDGET[card]
        stmt = expenses.get(card, 0) if expenses else 0
        cur = cycle.get(card, 0) if cycle else 0
        pct = _pct(stmt, budget)
        lines.append("| {} | {:,} | {:,} | {:,} | {:+,} | {:+.1f}% | {} |".format(
            card, budget, stmt, cur, stmt - budget, pct, _level(pct)))
    lines.append("| **四卡合計** | **{:,}** | **{:,}** | **{:,}** | — | — | — |".format(
        total_budget, total_stmt, total_cycle))
    lines.append("")
    lines.append("> 帳本基準（Company_Ledger.md / snapshot 2026-09-10）：四卡月均 **{:,}**（區間 {:,}–{:,}）；**本期帳單合計 {:+,} TWD（{:+.1f}%）**".format(
        LEDGER_BUDGET, LEDGER_BAND[0], LEDGER_BAND[1], total_stmt - LEDGER_BUDGET, _pct(total_stmt, LEDGER_BUDGET)))
    lines.append("")
    lines.append("## 異常警示")
    lines.append("")
    alerts = []
    for card in CARDS:
        budget = BUDGET[card]
        cur = cycle.get(card, 0) if cycle else 0
        stmt = expenses.get(card, 0) if expenses else 0
        pct = _pct(stmt, budget)
        if pct >= 20:
            alerts.append("- 🚨 **P1** {} 本期帳單 {:,} 超預算 {:.1f}%（預算 {:,}；當期未繳 {:,}）".format(
                card, stmt, pct, budget, cur))
        elif pct >= 10:
            alerts.append("- ⚠️ **P2** {} 本期帳單 {:,} 超預算 {:.1f}%（預算 {:,}）".format(card, stmt, pct, budget))
    tot_pct = _pct(total_stmt, LEDGER_BUDGET)
    if tot_pct >= 20:
        alerts.append("- 🚨 **P1** 四卡本期帳單合計 {:+,} TWD（{:+.1f}%）超帳本基準 {:,} TWD；當期未繳（將全額扣繳）{:,} TWD".format(
            total_stmt - LEDGER_BUDGET, tot_pct, LEDGER_BUDGET, total_cycle))
    elif tot_pct >= 10:
        alerts.append("- ⚠️ **P2** 四卡本期帳單合計 {:+,} TWD（{:+.1f}%）高於帳本基準".format(
            total_stmt - LEDGER_BUDGET, tot_pct))
    if bill_meta.get("export_date") and _age(bill_meta["export_date"]) > 14:
        alerts.append("- 🚨 **P1（資料品質）** 帳單匯出檔資料日 {}（{} 天前）逾 14 天未更新；"
                      "請確認 Moneybook ZIP 是否已上傳（契約：ZIP 為 canonical 來源）".format(
                          bill_meta["export_date"], _age(bill_meta["export_date"])))
    elif not bill_meta.get("export_date"):
        alerts.append("- 🚨 **P1（資料品質）** 帳單資料來源失效：{}".format(
            bill_meta.get("error") or "無來源（不得靜默退回舊檔）"))
    if not alerts:
        lines.append("- ✅ 無異常，四大主力皆在預算範圍內")
    else:
        lines.extend(alerts)
    lines.append("")
    lines.append("## 現金流影響")
    lines.append("")
    other = acct.get("other", 0)
    lines.append("- 四卡當期未繳（每月全額自動扣繳，無循環利息）：{:,} TWD".format(total_cycle))
    if other:
        lines.append("- 其他卡（國泰 CUBE 等）當期未繳：{:,} TWD；**全部卡費合計 {:,} TWD**".format(
            other, total_cycle + other))
    lines.append("- 帳本四卡月預算：{:,} TWD（區間 {:,}–{:,}）".format(LEDGER_BUDGET, LEDGER_BAND[0], LEDGER_BAND[1]))
    lines.append("- 月支出基線：{:,} TWD".format(int(_monthly_expense_baseline())))
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
    lines.append("- " + mb_source.describe("帳單", bill_meta))
    lines.append("- " + mb_source.describe("帳戶", acct))
    lines.append("- 帳單期別（最新繳費截止日）：{}".format(bill_meta.get("statement_due") or "—"))
    lines.append("- 語義分離：**匯出日＝資料新鮮度**；**期別＝帳單事件時間**（兩者不同，不得混用）")
    lines.append("- 執行腳本：budget_daily_check.py（來源走 MB 匯入契約 mb_source.py）")
    lines.append("")

    report = "\n".join(lines)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(report)
    return report


def main():
    expenses, bill_meta = parse_moneybook_bill()
    cycle, acct = parse_moneybook_account()
    if expenses is None:
        expenses = {card: 0 for card in CARDS}
    if cycle is None:
        cycle = {card: 0 for card in CARDS}
    report = calculate_budget_status(expenses, bill_meta or {}, cycle, acct or {})
    print(report)
    print("Report written to {}".format(REPORT))


if __name__ == "__main__":
    main()
