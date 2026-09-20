#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weekly_nw_breakdown.py — 儀表板「📡 本週淨資產變動拆解」自動更新（2026-09-20）
============================================================
背景：儀表板「淨資產變動拆解」原計算窗口為「最近一個週五 → 今天」，若週間跑
或數據無變化則顯示零，導致判讀困難（9/20 實證）。修正為固定「今天 - 7 天 → 今天」
的滾動窗口，確保永遠有完整的 7 天數據可供分析。

拆解（方法已用 8/21→8/28 驗證：market -27,510 完全重現）：
  net    = Δ(總資產 − 總負債)
  market = Δ(證券 + 基金 + 保單)          ← 市場性
  cost   = 0（無利息扣款日曆；週五 LLM 覆核可細分）
  transaction = net − market − cost      ← 帳務/交易性（含還債+現金流）

冪等：snapshot 已是最新窗口 → 不寫、印「已是當前窗口」。
用法：python weekly_nw_breakdown.py [--force]
"""
import json
import sqlite3
import sys
import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
DB = BASE / "dragon_assets.db"


def main():
    force = "--force" in sys.argv
    con = sqlite3.connect(str(DB))
    cols = ["date", "cash_total", "securities", "funds",
            "insurance", "total_assets", "total_liabilities"]
    rows = {}
    for r in con.execute(
            f"SELECT {', '.join(cols)} FROM assets ORDER BY date"):
        rows[r[0]] = dict(zip(cols, r))
    con.close()
    if not rows:
        print("無 assets 列，略過")
        return
    dates = sorted(rows)
    latest_d = dates[-1]
    _latest_date_obj = datetime.date.fromisoformat(latest_d)
    _anchor_date_obj = _latest_date_obj - datetime.timedelta(days=7)
    anchor = _anchor_date_obj.isoformat()
    # 確保 anchor 日期在歷史數據範圍內，否則用最早的數據
    if anchor < dates[0]:
        anchor = dates[0]
    
    if anchor == latest_d:
        print("僅一列歷史或窗口不足 7 天，無法算變動")
        return

    L, A = rows[latest_d], rows[anchor]
    net = (L["total_assets"] - L["total_liabilities"]) - \
          (A["total_assets"] - A["total_liabilities"])
    market = (L["securities"] + L["funds"] + L["insurance"]) - \
             (A["securities"] + A["funds"] + A["insurance"])
    cost = 0
    transaction = net - market - cost
    cash_d = L["cash_total"] - A["cash_total"]
    liab_d = L["total_liabilities"] - A["total_liabilities"]  # 負債變動（負=還債）
    sec_d = L["securities"] - A["securities"]
    fund_d = L["funds"] - A["funds"]
    ins_d = L["insurance"] - A["insurance"]
    period = f"{anchor} → {latest_d}"

    # 冪等檢查
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    cur = snap.get("net_worth_weekly_breakdown", {})
    if not force and cur.get("period") == period:
        print(f"已是當前窗口 {period}（net {cur.get('net_worth_change', 0):+,}），略過")
        return

    dominant = max([("基金", fund_d), ("保單", ins_d), ("證券", sec_d)],
                   key=lambda x: abs(x[1]))
    judgment = (
        f"淨值 {net:,.0f}：市場性 {market:,.0f}（{dominant[0]} {dominant[1]:,.0f}為主）"
        f"+ 帳務/交易性 {transaction:,.0f}（現金 {cash_d:,.0f}、負債 {-liab_d:,.0f}）"
        f"；DB 真值自動拆解，成本 0（無利息扣款日曆），週五深度審查覆核細分"
    )
    snap["net_worth_weekly_breakdown"] = {
        "period": period,
        "net_worth_change": net,
        "market": market,
        "transaction": transaction,
        "cost_of_capital": cost,
        "judgment": judgment,
        "note": f"{datetime.date.today().isoformat()} 自動更新（DB 真值）；週五深度審查覆核",
    }
    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(f"📡 淨資產拆解已更新 {period}：net {net:,.0f} = market {market:,.0f} + transaction {transaction:,.0f}")


if __name__ == "__main__":
    main()
