#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每月現金流報告（cron：每月 1 日 09:00，產出「上月」現金流）

2026-11-01 重寫原因：原版硬編碼「7月-8月」（2026-07/2026-08），但 asset_diff_history.json
只保留近 32 天滾動，7-8 月早已不存在 → dates 為空 → prev=None、start=None →
`net = prev - start` TypeError（cron rc=1，每月 1 日必失敗）。

改為：
  1. 目標月動態＝上月（可用 argv 指定 YYYY-MM）
  2. 資料不足 2 筆 → 明確錯誤訊息 + rc=1（不再 traceback）
  3. 全部數值走 snapshot 衍生的 asset_diff_history 真值，不自算、不補值

用法：python cashflow_analysis.py [YYYY-MM]
"""
import json
import sys
import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent


def prev_month(today: datetime.date) -> str:
    first = today.replace(day=1)
    return (first - datetime.timedelta(days=1)).strftime("%Y-%m")


def main() -> int:
    hist = json.loads((BASE / "asset_diff_history.json").read_text(encoding="utf-8"))
    month = sys.argv[1] if len(sys.argv) > 1 else prev_month(datetime.date.today())

    keys = sorted(k for k in hist if str(k).startswith(month))
    if len(keys) < 2:
        avail = sorted(hist)
        print(f"❌ 現金流報告 {month}：asset_diff_history 只有 {len(keys)} 筆，至少需 2 筆才能算淨變動")
        if avail:
            print(f"   現有範圍：{avail[0]} ~ {avail[-1]}（共 {len(avail)} 筆）")
        print("   處理：等當日產線補上 snapshot 後重跑，或指定有資料的月份（python cashflow_analysis.py 2026-10）")
        return 1

    rows = []
    for d in keys:
        e = hist.get(d) or {}
        try:
            cash = float(e.get("cash") or 0)
            total = float(e.get("total_assets") or 0)
        except (TypeError, ValueError):
            continue
        rows.append((d, cash, total))

    if len(rows) < 2:
        print(f"❌ 現金流報告 {month}：有效資料列不足（cash/total_assets 解析失敗）")
        return 1

    start_d, start_cash, start_total = rows[0]
    end_d, end_cash, end_total = rows[-1]
    net = end_cash - start_cash

    daily = []
    for i in range(1, len(rows)):
        daily.append((rows[i][0], rows[i][1] - rows[i - 1][1]))
    biggest_in = max(daily, key=lambda x: x[1])
    biggest_out = min(daily, key=lambda x: x[1])

    print(f"💧 每月現金流報告 {month}")
    print(f"資料區間：{start_d} ~ {end_d}（{len(rows)} 個觀測日）")
    print("─" * 34)
    print(f"期初現金   {start_cash:>14,.0f}")
    print(f"期末現金   {end_cash:>14,.0f}")
    print(f"淨變動     {net:>+14,.0f}")
    print("─" * 34)
    print(f"總資產     {start_total:,.0f} → {end_total:,.0f}（{end_total - start_total:+,.0f}）")
    print(f"最大單日流入 {biggest_in[0][5:]} {biggest_in[1]:+,.0f}")
    print(f"最大單日流出 {biggest_out[0][5:]} {biggest_out[1]:+,.0f}")
    pos = sum(1 for _, v in daily if v > 0)
    print(f"流入/流出日數 {pos}／{len(daily) - pos}")

    # 明細（只在筆數不多時列出，避免 Telegram 長訊息）
    if len(rows) <= 12:
        print("─" * 34)
        for i, (d, cash, _t) in enumerate(rows):
            diff = "" if i == 0 else f"{cash - rows[i - 1][1]:+,.0f}"
            print(f"{d[5:]}  {cash:>12,.0f}  {diff:>+12s}" if diff else f"{d[5:]}  {cash:>12,.0f}  {'-':>12s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
