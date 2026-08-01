"""
配息自動追蹤器 — 從 Moneybook 明細掃描當月配息入帳，寫入 snapshot.dividend_records
執行：python dividend_tracker.py
自動化：可掛 cron 每日跑一次（lj.py dividend）
"""
import json, csv, os, glob
from datetime import date
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
SNAP_PATH = os.path.join(BASE, "snapshot.json")
MB_DIR = os.path.join(BASE, "moneybook")

# ETF 代碼（證券帳戶）vs 基金（鉅亨/保單）
ETF_CODES = ['00981a', '00713', '00918', '00919', '0050', '006208', '00878', '00888',
             '00984a', '00983d', '009823', '009824', '0056', '00646']
INSURANCE_KEYS = ['安聯人壽', '第一金人壽']  # 保單配息


def latest_mb_file():
    """找最新 Moneybook 明細 CSV"""
    files = sorted(glob.glob(os.path.join(MB_DIR, "Moneybook_明細_*.csv")))
    return files[-1] if files else None


def scan_month_dividends(target_month: str):
    """掃描某月（YYYY-MM）的配息入帳，回傳 {日期: {名稱: 金額}}"""
    path = latest_mb_file()
    if not path:
        return {}
    records = defaultdict(dict)
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.reader(f):
            if len(r) < 10 or r[0] == '金融機構/手動新增':
                continue
            cat, memo, amt, d = r[4], r[5], r[7], r[8]
            if not (d or '').startswith(target_month):
                continue
            if '配息' not in cat and '配息' not in memo and '股利' not in cat:
                continue
            try:
                amt = float(amt)
            except (ValueError, TypeError):
                continue
            if amt <= 0:
                continue
            # 分類
            low = memo.lower()
            if '安聯人壽' in memo:
                name = '安聯配息'
            elif '第一金人壽' in memo:
                name = '第一金配息'
            elif any(k in low for k in ETF_CODES):
                # 找代碼
                code = next((c for c in ETF_CODES if c in low), 'ETF')
                name = f'ETF {code.upper()}'
            else:
                name = '基金配息'
            records[d][name] = records[d].get(name, 0) + amt
    return dict(records)


def main():
    today = date.today()
    month = today.strftime("%Y-%m")
    snap = json.load(open(SNAP_PATH, encoding="utf-8"))
    records = scan_month_dividends(month)

    if records:
        # 合併進 dividend_records（保留既有）
        dr = snap.get("dividend_records", {}) or {}
        for d, items in records.items():
            merged = dict(dr.get(d, {}))
            for k, v in items.items():
                merged[k] = merged.get(k, 0) + v
            dr[d] = merged
        snap["dividend_records"] = dr
        total = sum(v for items in records.values() for v in items.values())
        snap["dividend_month_actual"] = total
        # 同步 monthly_dividend（其他腳本如 rebalance/morning_briefing 讀此欄位）
        snap["monthly_dividend"] = total
        print(f"✅ 本月({month})已追蹤配息: {total:,.0f} TWD")
        for d in sorted(records):
            print(f"  {d}: " + ", ".join(f"{k} {v:,.0f}" for k, v in records[d].items()))
    else:
        # 當月尚無配息 → 歸零
        snap["dividend_month_actual"] = 0
        snap["monthly_dividend"] = 0
        print(f"ℹ️ 本月({month})尚未收到配息，顯示 0")

    json.dump(snap, open(SNAP_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
