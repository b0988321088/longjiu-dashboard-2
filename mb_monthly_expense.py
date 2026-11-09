#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mb_monthly_expense.py — Moneybook 明細 → 每月實際支出（可追溯、可重跑、不重複入帳）

為什麼有這支
------------
月度追蹤（monthly_tracker.py）目前支出用「常態 159,210」，是估算不是真值。
使用者 2026-11-01 裁決：批准把 Moneybook 支出匯入，但必須
  ①每月一次、自動、異常才提醒；②不得增加每日人工維護；
  ③估算不得冒充實際；④可追溯／可重跑／不重複入帳。

資料源
------
moneybook_new/Moneybook_明細_YYYYMMDD_*.csv（MB 匯出的「明細」，13 欄）
  → 逐筆：金融機構/帳戶名稱/分類/明細描述/幣別/金額/消費日/入帳日/是否排除收支

設計原則（避開 MB 分類不可信的問題）
--------------------------------
實測 2026-10：MB 分類把 ATM 轉出 200 萬標成「現金消費」、把質押撥款 723 萬標成
「尚未分類」。所以分類不採信 MB 的「分類」欄，改用「帳戶類型 + 描述關鍵字」重建，
並保留每一筆的判定理由（可追溯）。

五種必須防的錯誤（使用者明列）
  1. 信用卡消費 vs 繳信用卡費重複 → 「繳信用卡費」整類排除（消費本身已計）
  2. 帳戶間轉帳 → 轉帳/轉入/轉出/授權轉入/cd轉入/cd轉出/atm 排除
  3. 股票基金買入 → 投資買賣/基金申購/投資獲利 排除
  4. 借款本金償還 → 攤還本金/還本 獨立列示（不混入消費）
  5. 非經常性（修繕/稅金） → 獨立標記 non_recurring

輸出
----
data/mb_expense_<YYYY-MM>.json  （可追溯：來源檔、sha256、每筆判定）
stdout 摘要（cron 每月 1 日推給使用者）

用法
----
  python mb_monthly_expense.py                # 自動抓上月＋最新明細 CSV
  python mb_monthly_expense.py --month 2026-10
  python mb_monthly_expense.py --file path.csv --month 2026-10
  python mb_monthly_expense.py --selftest     # 規則自我測試（不讀真實檔）
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "data"

# ── 規則表（可追溯；順序即優先序）────────────────────────────
EXCLUDE = [
    ("帳戶互轉", r"帳戶互轉"),
    ("信用卡繳款", r"繳信用卡費|信用卡款|繳款"),
    ("轉帳", r"轉帳|轉入|轉出|授權轉入|cd轉入|cd轉出|atm"),
    ("投資買賣", r"投資買賣|基金申購|基金買回|投資獲利|貝萊德全球|申購|贖回"),
    ("外幣買賣", r"外幣買賣|換匯|交易匯率"),
    ("貸款本金", r"攤還本金|還本|本金攤還"),
]
NON_RECUR = [("修繕", r"修繕|裝修|水電修"), ("稅金", r"稅|牌照|燃料費"),
             ("年繳保費", r"人壽保費|年繳|躉繳")]
# 收入白名單（優先於 EXCLUDE；MB 分類可能錯標）
#   006-0005562988013559 = 女友帳戶（ATM 006 敦南Richart），每月 6,000 借款還款，
#   MB 分類標成「利息所得」且描述為「cd轉入 - atm …」，會被「轉帳」排除規則誤攔。
WHITELIST = [
    ("女友還款", r"006-0005562988013559"),
]
INCOME = [
    ("薪資", r"薪資|台電"),
    ("租金", r"租金|房租"),
    ("股利", r"股利|股息"),
    ("配息撥回", r"安聯人壽|第一金人壽|配息|撥回"),
    ("利息", r"利息所得|存款息"),
    ("回饋", r"優惠回饋|回饋"),
]
# 明確的支出分類（MB 原分類可用者）
SPEND_CATS = {"飲食", "交通", "住家", "保險", "休閒娛樂", "購物", "服飾",
              "電子票證加值", "費用/手續費", "現金消費", "教育", "醫療", "寵物", "其他"}


def num(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or "").replace(",", "").replace("，", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def month_of(row) -> str:
    d = (row.get("入帳日") or row.get("消費日") or "").strip()
    m = re.match(r"(\d{4})/(\d{1,2})", d)
    return f"{m.group(1)}-{int(m.group(2)):02d}" if m else ""


def classify(row) -> tuple[str, str]:
    """回 (bucket, reason)。bucket ∈ exclude/spend/income/non_recurring/unknown。"""
    acc = row.get("帳戶名稱", "") or ""
    cat = (row.get("分類", "") or "").strip()
    desc = (row.get("明細描述", "") or "").strip()
    amt = num(row.get("金額"))
    text = f"{cat} {desc}"

    if (row.get("是否排除收支") or "").strip() == "是":
        return "exclude", "MB 標記排除收支"
    # 收入白名單：必須早於 EXCLUDE（女友還款走 cd轉入／atm，會被「轉帳」規則誤攔）
    for name, pat in WHITELIST:
        if re.search(pat, text, re.I):
            return "income", f"白名單：{name}"
    # 貸款帳戶：利息＝支出（房貸），本金＝獨立列示
    if "貸款" in acc:
        if "本金" in desc:
            return "exclude", "貸款本金（獨立列示，不計消費）"
        if "利息" in desc:
            return "spend", f"貸款利息（{acc}）"
    for name, pat in EXCLUDE:
        if re.search(pat, text, re.I):
            return "exclude", f"規則：{name}"
    if cat in SPEND_CATS:
        for name, pat in NON_RECUR:
            if re.search(pat, text):
                return "non_recurring", f"非經常性：{name}"
        return "spend", f"MB 分類：{cat}"
    for name, pat in INCOME:
        if re.search(pat, text, re.I):
            return "income", f"收入：{name}"
    if amt > 0:
        return "income", "收入（正值，未命中規則）"
    # MB 未分類的小額卡片/提款消費：仍屬生活支出，但標「未細分」不假裝分類；
    # 大額或非卡片帳戶未分類 → 留在 unknown 觸發 HOLD（不猜）。
    if abs(amt) < 20000 and ("卡" in acc or cat in ("尚未分類", "現金消費")):
        return "spend", f"未分類小額消費（MB：{cat or '空'}）"
    return "unknown", f"待分類（MB：{cat or '空'}）"


def analyze(rows, month: str) -> dict:
    buckets = {"spend": [], "income": [], "exclude": [], "non_recurring": [], "unknown": []}
    for r in rows:
        if month_of(r) != month:
            continue
        b, why = classify(r)
        buckets[b].append({"date": month_of(r), "account": r.get("帳戶名稱"),
                           "cat": r.get("分類"), "desc": (r.get("明細描述") or "")[:60],
                           "amount": num(r.get("金額")), "bucket": b, "reason": why})

    spend = -sum(x["amount"] for x in buckets["spend"] if x["amount"] < 0)
    spend_pos = sum(x["amount"] for x in buckets["spend"] if x["amount"] > 0)  # 退款
    nonrec = -sum(x["amount"] for x in buckets["non_recurring"] if x["amount"] < 0)
    income = sum(x["amount"] for x in buckets["income"] if x["amount"] > 0)
    unknown_amt = -sum(x["amount"] for x in buckets["unknown"] if x["amount"] < 0)

    total_rows = sum(len(v) for v in buckets.values())
    unknown_ratio = (unknown_amt / spend) if spend else 0.0
    holds = []
    if total_rows < 10:
        holds.append(f"當月有效筆數僅 {total_rows} 筆，疑似匯出缺漏")
    if unknown_ratio > 0.03:
        holds.append(f"待分類金額 {unknown_amt:,.0f} 占支出 {unknown_ratio:.1%}（>3%），需人工指定分類")
    recurring = spend - spend_pos
    return {
        "month": month,
        "rows_in_month": total_rows,
        # 實際支出＝經常性＋非經常性（非經常性只是「另外標記」，不從總額排除）
        "expense_actual": round(recurring + nonrec, 2),
        "expense_recurring": round(recurring, 2),
        "expense_non_recurring": round(nonrec, 2),
        "income_in_mb": round(income, 2),
        "excluded_count": len(buckets["exclude"]),
        "unknown": {"count": len(buckets["unknown"]), "amount": round(unknown_amt, 2),
                    "ratio": round(unknown_ratio, 4),
                    "items": buckets["unknown"][:30]},
        "holds": holds,
        "detail": {k: v for k, v in buckets.items()},
    }


def pick_source(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise SystemExit(f"❌ 找不到檔案：{p}")
        return p
    cands = sorted(BASE.glob("moneybook_new/Moneybook_明細_*.csv"))
    cands += sorted(Path.home().glob("Downloads/Moneybook_明細_*.csv"))
    if not cands:
        raise SystemExit("❌ 找不到 Moneybook_明細_*.csv（請放 moneybook_new/ 或 Downloads/）")
    return max(cands, key=lambda p: p.stat().st_mtime)


def selftest() -> int:
    cases = [
        ({"帳戶名稱": "文心綜活儲存款-薪轉", "分類": "尚未分類", "明細描述": "cd轉入 - atm 013-000006", "金額": "1,092,935", "入帳日": "2026/10/01", "是否排除收支": "否"}, "exclude"),
        ({"帳戶名稱": "敦南Richart數位一般帳", "分類": "現金消費", "明細描述": "cd轉出 - atm 017-0099", "金額": "-1,006,900", "入帳日": "2026/10/01", "是否排除收支": "否"}, "exclude"),
        ({"帳戶名稱": "CUBE御璽卡Visa", "分類": "尚未分類", "明細描述": "全支付—巧味牛雜湯", "金額": "-170", "入帳日": "2026/10/06", "是否排除收支": "否"}, "spend"),
        ({"帳戶名稱": "臺幣綜存", "分類": "尚未分類", "明細描述": "大額不明轉出", "金額": "-300,000", "入帳日": "2026/10/06", "是否排除收支": "否"}, "unknown"),
        ({"帳戶名稱": "Unicard－正卡", "分類": "飲食", "明細描述": "連加*新光三越", "金額": "-65", "入帳日": "2026/10/01", "是否排除收支": "否"}, "spend"),
        ({"帳戶名稱": "房屋貸款", "分類": "貸款繳納", "明細描述": "利息 - 房屋貸款", "金額": "-25,644", "入帳日": "2026/10/20", "是否排除收支": "否"}, "spend"),
        ({"帳戶名稱": "房屋貸款", "分類": "貸款繳納", "明細描述": "攤還本金", "金額": "11,945", "入帳日": "2026/10/27", "是否排除收支": "否"}, "exclude"),
        ({"帳戶名稱": "文心綜活儲存款-薪轉", "分類": "薪資", "明細描述": "台電薪資", "金額": "39,777", "入帳日": "2026/10/06", "是否排除收支": "否"}, "income"),
        ({"帳戶名稱": "文心綜活儲存款-薪轉", "分類": "住家", "明細描述": "冷氣修繕", "金額": "-8,000", "入帳日": "2026/10/09", "是否排除收支": "否"}, "non_recurring"),
    ]
    bad = 0
    for row, want in cases:
        got, why = classify(row)
        ok = got == want
        bad += 0 if ok else 1
        print(f"{'✅' if ok else '❌'} 期望 {want:<14} 得到 {got:<14} {why}")
    print(f"自測 {len(cases) - bad}/{len(cases)} PASS")
    return 0 if bad == 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month")
    ap.add_argument("--file")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()

    month = a.month or (dt.date.today().replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    src = pick_source(a.file)
    raw = src.read_bytes()
    rows = list(csv.DictReader(raw.decode("utf-8-sig", errors="replace").splitlines()))
    res = analyze(rows, month)
    res["source"] = {"file": str(src.relative_to(BASE)) if str(src).startswith(str(BASE)) else str(src),
                     "sha256": hashlib.sha256(raw).hexdigest(),
                     "rows_total": len(rows),
                     "generated_at": dt.datetime.now().isoformat(timespec="seconds")}

    if a.selftest is False:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUT_DIR / f"mb_expense_{month}.json"
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    if not a.quiet:
        print(f"💸 Moneybook 實際支出 {month}｜來源 {res['source']['file']}")
        print(f"   實際支出 {res['expense_actual']:,.0f}＝經常性 {res['expense_recurring']:,.0f}"
              f"＋非經常性 {res['expense_non_recurring']:,.0f}")
        print(f"   MB 內收入 {res['income_in_mb']:,.0f}｜排除筆數 {res['excluded_count']}")
        if res["unknown"]["count"]:
            print(f"   ⚠️ 待分類 {res['unknown']['count']} 筆 / {res['unknown']['amount']:,.0f}（{res['unknown']['ratio']:.1%}）")
        if res["holds"]:
            for h in res["holds"]:
                print(f"   ⛔ HOLD：{h}")
        else:
            print("   ✅ 無異常（分類覆蓋率達標）")
        print(f"   → data/mb_expense_{month}.json")
    return 0 if not res["holds"] else 3


if __name__ == "__main__":
    sys.exit(main())
