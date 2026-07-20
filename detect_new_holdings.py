"""
從 Moneybook CSV 自動偵測新持倉
"""
import csv, json
from pathlib import Path
from datetime import date, timedelta

BASE = Path(__file__).parent.resolve()


def scan_new_holdings() -> list:
    """掃描近 3 天的 Moneybook CSV，偵測新的 ETF/股票買入"""
    new = []
    today = date.today()
    mb_dir = BASE / "Moneybook"
    if not mb_dir.exists():
        # 檢查 tmp 下的暫存
        for d in BASE.glob("tmp/mb*"):
            for f in d.glob("Moneybook_明細_*.csv"):
                new.extend(_parse_mb(f))
        return new

    cutoff = today - timedelta(days=3)
    for f in sorted(mb_dir.glob("Moneybook_明細_*.csv"), reverse=True):
        fdate_str = f.stem.replace("Moneybook_明細_", "")
        try:
            fdate = date.fromisoformat(fdate_str[:10])
        except:
            continue
        if fdate < cutoff:
            break
        new.extend(_parse_mb(f))

    return new


def _parse_mb(path: Path) -> list:
    """解析一筆 Moneybook CSV，找出買入的 ETF/股票"""
    found = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                # 欄位：日期、類型、名稱、金額、備註...
                if len(row) < 5:
                    continue
                desc = " ".join(row).lower()
                # 關鍵字：買入、證券、ETF、股票
                if any(k in desc for k in ["買入", "證券", "etf", "股票", "etf "]):
                    name = row[2] if len(row) > 2 else ""
                    amount = row[3] if len(row) > 3 else "0"
                    try:
                        amount = float(amount.replace(",", ""))
                    except:
                        amount = 0
                    if amount > 0:
                        found.append({"name": name, "amount": amount, "file": path.name})
    except Exception:
        pass
    return found


if __name__ == "__main__":
    result = scan_new_holdings()
    if result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("[]")
PYEOF