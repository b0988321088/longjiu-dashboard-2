#!/usr/bin/env python3
"""7月現金流分析"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
hist = json.loads((BASE / "asset_diff_history.json").read_text(encoding="utf-8"))

dates = sorted(d for d in hist if "2026-07" in d)
print("=== 7月現金流趨勢 ===")
print(f"{'日期':12s} {'現金':>12s} {'增減':>10s} {'總資產':>12s}")
print("-" * 46)

prev = None
start = None
for d in dates:
    e = hist[d]
    c = e.get("cash", 0)
    t = e.get("total_assets", 0)
    if prev is not None:
        diff = c - prev
        ds = f"{diff:+,}"
    else:
        diff = 0
        ds = "-"
        start = c
    print(f"{d:12s} {c:>12,.0f} {ds:>10s} {t:>12,.0f}")
    prev = c

print("-" * 46)
net = prev - start
print(f"期初: {start:,.0f}  期末: {prev:,.0f}  淨變動: {net:+,.0f}")
