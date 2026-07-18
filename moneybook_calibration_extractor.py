from __future__ import annotations

"""被動收入提取器：從 Moneybook detail.csv 計算近2個月配息。

規則：
1. 只看 台新銀行 + 永豐銀行
2. 近2個月
3. 關鍵字：配息/安聯/第一金/摩根/M&G/貝萊德/聯博/路博邁/fl65/jpm
4. 排除：贖回、利息、帳戶互轉、小額<50
5. 輸出 mean/std，供 daily_deploy.py 寫入 snapshot
6. 若 snapshot.fund_dividend_monthly 已有人工標註，優先使用
"""

import csv
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

KEYWORDS = ["配息", "安聯", "第一金", "摩根", "m&g", "貝萊德", "聯博", "路博邁", "fl65", "jpm"]
BANKS = ["台新銀行", "永豐銀行"]
MIN_AMOUNT = 50.0


def extract(detail_path: Path, months: int = 2) -> dict:
    if not detail_path.exists():
        return {"monthly_mean": 0.0, "monthly_std": 0.0, "source": "missing"}

    cutoff = (datetime.now() - timedelta(days=30 * months)).strftime("%Y/%m/%d")
    per_month: dict[str, float] = defaultdict(float)
    per_source: dict[str, float] = defaultdict(float)

    with open(detail_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            amt = (row.get("金額") or "").replace(",", "")
            if not amt:
                continue
            try:
                val = float(amt)
            except ValueError:
                continue
            if val < MIN_AMOUNT:
                continue
            desc = row.get("明細描述") or ""
            if "贖回" in desc:
                continue
            bank = row.get("機構名稱") or ""
            if bank not in BANKS:
                continue
            if not any(k in (row.get("分類", "") + desc).lower() for k in KEYWORDS):
                continue
            date_str = row.get("入帳日") or row.get("消費日") or ""
            if date_str < cutoff:
                continue

            month = date_str[:7]
            per_month[month] += val

            if "安聯" in desc:
                src = "安聯"
            elif "第一金" in desc:
                src = "第一金"
            elif "摩根" in desc or "jpm" in desc.lower():
                src = "摩根"
            elif "m&g" in desc.lower():
                src = "M&G"
            elif "貝萊德" in desc:
                src = "貝萊德"
            elif "聯博" in desc:
                src = "聯博"
            elif "路博邁" in desc:
                src = "路博邁"
            else:
                src = "其他"
            per_source[src] += val

    values = list(per_month.values())
    mean = statistics.mean(values) if values else 0.0
    std = statistics.stdev(values) if len(values) > 1 else 0.0

    return {
        "monthly_mean": round(mean, 0),
        "monthly_std": round(std, 0),
        "months": sorted(per_month.keys()),
        "per_month": dict(per_month),
        "per_source": dict(per_source),
        "banks": BANKS,
        "source": "moneybook",
    }


def get_passive_income(snapshot: dict, detail_path: Path, manual_fund_dividend: float | None = None) -> float:
    """Compute passive income for moat monitor.

    Precedence:
    1. manual_fund_dividend if > 0
    2. snapshot.fund_dividend_monthly if > 0
    3. MB computed mean
    4. fallback 0
    """
    if manual_fund_dividend and manual_fund_dividend > 0:
        return float(manual_fund_dividend)
    fund = snapshot.get("fund_dividend_monthly") or 0
    if fund > 0:
        return float(fund)
    mb = extract(detail_path)
    return float(mb["monthly_mean"])


if __name__ == "__main__":
    detail = Path("moneybook/detail.csv")
    result = extract(detail, months=2)
    rent = 80100.0
    total = rent + result["monthly_mean"]
    print(json.dumps({
        "mb_monthly_mean": result["monthly_mean"],
        "rent_monthly_actual": rent,
        "passive_income_total": total,
        "per_source": result["per_source"],
        "months": result["months"],
    }, ensure_ascii=False, indent=2))