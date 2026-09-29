#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析 Moneybook 2026/08/30–09/29 三檔 CSV → 只輸出已去識別化摘要（safe_read 遮罩 PII）。"""
import sys
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
sys.path.insert(0, str(BASE))
from safe_read import read_csv_rows          # noqa: E402

MB = BASE / "moneybook"
acc = read_csv_rows(str(MB / "Moneybook_帳戶_20260929_1.csv"))
det = read_csv_rows(str(MB / "Moneybook_明細_20260929_1.csv"))
bill = read_csv_rows(str(MB / "Moneybook_帳單_20260929_1.csv"))
print("帳戶欄位:", list(acc[0].keys()) if acc else "空")
print("明細欄位:", list(det[0].keys()) if det else "空")
print("帳單欄位:", list(bill[0].keys()) if bill else "空")

def num(s):
    s = str(s or "").replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0

# ===== 1. 帳戶 =====
print("\n===== 帳戶（台幣活存）=====")
CASH_EX = ("外幣", "貸款", "信貸", "房貸", "透支", "質押")
CC_HINT = ("卡", "unicard", "richart", "cube", "gogo", "sport", "御璽")
cash_items, card_neg, loan_items, other = {}, {}, {}, {}
for r in acc:
    inst = (r.get("機構名稱") or "").strip()
    acct = (r.get("帳戶名稱") or "").strip()
    amt = num(r.get("帳戶金額"))
    key = f"{inst}/{acct}"
    low = key.lower()
    if any(x in key for x in CASH_EX):
        (loan_items if any(x in key for x in ("貸款", "信貸", "房貸")) else other)[key] = amt
    elif any(x in low for x in CC_HINT) or amt < 0:
        card_neg[key] = amt
    else:
        cash_items[key] = amt
tot = sum(v for v in cash_items.values() if v > 0)
for k, v in sorted(cash_items.items(), key=lambda x: -x[1]):
    print(f"  {k:<36} {v:>12,.0f}")
print(f"  {'台幣活存合計（正數）':<36} {tot:>12,.0f}")
print("\n信用卡／負值：")
for k, v in card_neg.items():
    print(f"  {k:<36} {v:>12,.0f}")
print("  信用卡負值加總 =", f"{sum(v for v in card_neg.values() if v < 0):,.0f}")
print("\n貸款／房貸：")
for k, v in loan_items.items():
    print(f"  {k:<36} {v:>14,.0f}")
print("\n其他排除（外幣/質押等）：")
for k, v in other.items():
    print(f"  {k:<36} {v:>12,.0f}")

# ===== 2. 明細 =====
print("\n===== 明細 =====")
rows = []
for r in det:
    rows.append({"inst": (r.get("機構名稱") or ""), "cat": (r.get("分類") or ""),
                 "desc": (r.get("明細描述") or ""), "amt": num(r.get("金額")),
                 "d": (r.get("消費日") or "").strip()})
print(f"筆數 {len(rows)}｜日期 {min(x['d'] for x in rows)} ~ {max(x['d'] for x in rows)}")
inc = sum(x["amt"] for x in rows if x["amt"] > 0)
exp = sum(x["amt"] for x in rows if x["amt"] < 0)
print(f"收入 +{inc:,.0f}｜支出 {exp:,.0f}｜淨 {inc+exp:,.0f}")
cats = {}
for x in rows:
    c = cats.setdefault(x["cat"], [0, 0.0])
    c[0] += 1
    c[1] += x["amt"]
print("\n分類彙總：")
for c, (n, s) in sorted(cats.items(), key=lambda y: -abs(y[1][1])):
    print(f"  {c:<14} {n:>3} 筆 {s:>14,.0f}")
print("\n大額（|金額| ≥ 30,000）：")
for x in sorted([y for y in rows if abs(y["amt"]) >= 30000], key=lambda y: y["d"]):
    print(f"  {x['d']} {x['amt']:>13,.0f} {x['cat']:<8} {x['desc'][:36]} @{x['inst'][:6]}")
print("\n收益類（配息/股息/租金/薪資/撥回，正值）：")
KW = ("配息", "撥回", "股息", "股利", "租金", "房租", "薪資", "薪水")
for x in sorted(rows, key=lambda y: y["d"]):
    if any(k in x["desc"] for k in KW) and x["amt"] > 0:
        print(f"  {x['d']} {x['amt']:>11,.0f} {x['desc'][:34]}")

# ===== 3. 帳單 =====
print("\n===== 帳單 =====")
for r in bill:
    print("  ", {k: (r.get(k) or "") for k in list(r.keys())[:5]})
