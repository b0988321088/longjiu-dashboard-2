"""
配息自動追蹤器 — 從 Moneybook 明細掃描當月配息入帳，寫入 snapshot.dividend_records
執行：python dividend_tracker.py
自動化：可掛 cron 每日跑一次（lj.py dividend）
"""
import json, csv, os, glob
from datetime import date
from collections import defaultdict
from dividend_caliber import bucket_of, classify_mb_memo

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
            if '配息' not in cat and '配息' not in memo and '股利' not in cat and '撥回' not in memo:
                continue
            try:
                amt = float(amt)
            except (ValueError, TypeError):
                continue
            if amt <= 0:
                continue
            # 分類
            # ⚠️ 保單配息（安聯/第一金）跳過：以 App 累積應收為準（2026-09-01 定案），
            # 由真值日看 App「本月累積配息/撥回」手動記入 dividend_records。
            # tracker 若掃保單，尾批（如基準日 8/27、9/1 才入帳的 13,962）會被記進
            # 次月 → 與當月 App 應收重複計算。tracker 只負責 ETF/基金（實收制）。
            if any(k in memo for k in INSURANCE_KEYS) or '安聯保單撥回' in memo:
                continue
            low = memo.lower()
            # 2026-09-23：分類一律走正典 dividend_caliber（舊版自帶的「ETF 代碼子字串」規則
            # 會把「基金配息 元大0050連結A」（ETF 連結基金）誤判成 ETF、「台灣特品現金股息」誤記基金）。
            _b = classify_mb_memo(memo)
            if _b == "etf":
                code = next((c for c in ETF_CODES if c in low), 'ETF')
                name = f'ETF {code.upper()}'
            elif _b == "oneoff":
                name = '台灣特品現金股息'
            else:
                name = '基金配息'
            records[d][name] = records[d].get(name, 0) + amt
    return dict(records)


def month_total(records: dict, month: str) -> float:
    """當月配息實收合計（單一口徑）。

    2026-10-12（A1 真因）：舊版兩個分支對同一欄位用了兩套口徑——「本次有掃到新配息」
    的分支把 total 寫成**本次新增額**，只有「無掃描」分支才寫**當月全部紀錄合計**。
    於是只要當天掃到新配息，dividend_month_actual／monthly_dividend／mdb.total 就被
    覆蓋成單次增量（保守底線、覆蓋率、差異分析、FIRE 進度全部連動失真）。
    掃描的職責只有「把新紀錄併入 dividend_records」；總額一律由此函式重算。
    """
    tot = 0.0
    for _d, _items in (records or {}).items():
        if str(_d).startswith(month):
            tot += sum(v for v in _items.values() if isinstance(v, (int, float)))
    return tot


def main():
    today = date.today()
    month = today.strftime("%Y-%m")
    snap = json.load(open(SNAP_PATH, encoding="utf-8"))
    dr = snap.get("dividend_records", {}) or {}
    records = scan_month_dividends(month)

    if records:
        # 合併進 dividend_records（保留既有）
        for d, items in records.items():
            merged = dict(dr.get(d, {}))
            for k, v in items.items():
                merged[k] = merged.get(k, 0) + v
            dr[d] = merged
        snap["dividend_records"] = dr
        scanned = sum(v for items in records.values() for v in items.values())
        print(f"✅ 本月({month})本次掃到配息（已併入紀錄）: {scanned:,.0f} TWD")
        for d in sorted(records):
            print(f"  {d}: " + ", ".join(f"{k} {v:,.0f}" for k, v in records[d].items()))

    # 2026-10-12 A1：五欄一律由當月全部紀錄重算（不因有無新掃描而換口徑）
    total = month_total(dr, month)
    snap["dividend_month_actual"] = total
    # 同步 monthly_dividend（其他腳本如 rebalance/morning_briefing 讀此欄位）
    snap["monthly_dividend"] = total
    if records:
        print(f"ℹ️ 本月({month})當月實收合計（含既有紀錄）: {total:,.0f} TWD")
    elif total > 0:
        print(f"ℹ️ 本月({month})無新掃描，保留既有紀錄: {total:,.0f} TWD")
    else:
        print(f"ℹ️ 本月({month})尚未收到配息，顯示 0")

    # 2026-09-04 防復發（35,583/130,930 誤值三犯）：五欄一致鐵則自動校準。
    # monthly_dividend_total / monthly_dividend_breakdown 一律由當月 dividend_records
    # 重算（2026-09-23 起分類一律委派 dividend_caliber.bucket_of，不再自帶抄本規則），
    # 防止任何流程把「常態月配」(allianz_ab_monthly+firstjin_monthly=130,930) 寫回當月欄位。
    _bd = snap.setdefault("monthly_dividend_breakdown", {})
    if isinstance(_bd, dict):
        _by2 = {"allianz": 0, "firstjin": 0, "ins_other": 0, "etf": 0, "fund": 0, "oneoff": 0}
        for _d2, _items2 in (snap.get("dividend_records", {}) or {}).items():
            if not str(_d2).startswith(month):
                continue
            for _k2, _v2 in _items2.items():
                # 2026-10-12：與 month_total 用同一過濾規則（非數值一律不計）。
                # 舊版直接相加 → dividend_records 只要混入一個字串（備註/空值）就
                # TypeError 讓每日 07:00 產線整班失敗；且 total 與分桶若採不同規則
                # 還會出現「三桶加總 ≠ total」的第二種口徑不一致。
                if not isinstance(_v2, (int, float)):
                    continue
                _b2 = bucket_of(_k2)
                if _b2 == "ins":
                    if "安聯" in _k2:
                        _by2["allianz"] += _v2
                    elif "第一金" in _k2:
                        _by2["firstjin"] += _v2
                    else:
                        # 保單但非安聯/第一金子帳：不得靜默塞進 fund（insurance 合計仍須正確）
                        _by2["ins_other"] += _v2
                elif _b2 == "etf":
                    _by2["etf"] += _v2
                elif _b2 == "oneoff":
                    _by2["oneoff"] += _v2
                else:
                    _by2["fund"] += _v2
        if _by2["ins_other"]:
            print(f"[WARN] 保單配息含非安聯/第一金子帳 {_by2['ins_other']:,.0f}：insurance 合計已含，子帳欄未列")
        _bd.update({"allianz": _by2["allianz"], "firstjin": _by2["firstjin"],
                    "insurance": _by2["allianz"] + _by2["firstjin"] + _by2["ins_other"],
                    "etf": _by2["etf"], "fund": _by2["fund"],
                    "oneoff": _by2["oneoff"], "total": total})
    snap["monthly_dividend_total"] = total

    json.dump(snap, open(SNAP_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
