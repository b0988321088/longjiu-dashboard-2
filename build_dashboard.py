#!/usr/bin/env python3
"""build_dashboard.py — 儀表板動態注入（2026-08-26 建立）
問題：index_template.html 大量寫死財務值（保單/現金/配息/房租）→ 一鍵更新後儀表板舊值
解法：每次從 snapshot.json 讀真值 → replace 模板寫死值 → 產 index.html
用法：python build_dashboard.py（sync_all 已整合為步驟）
"""
import json, re
from pathlib import Path

BASE = Path(__file__).resolve().parent

def _fmt(n):
    return f"{n:,.0f}"

def main():
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    tpl = (BASE / "index_template.html").read_text(encoding="utf-8")

    # ── 從 snapshot 計算真值 ──
    cash = snap.get("cash_total", 0) or 0
    ins = snap.get("insurance_total", 0) or 0
    allianz = snap.get("allianz_combined", 0) or 0
    firstjin = snap.get("firstjin_fl65_current_value", snap.get("firstjin_current_value", 0)) or 0
    cum_div = snap.get("firstjin_cum_dividend", 111513) or 0
    mdb = snap.get("monthly_dividend_breakdown", {}) or {}
    div_ins = mdb.get("insurance", 0) or 0
    div_total = mdb.get("total", 0) or 0
    firstjin_div = mdb.get("firstjin", 0) or 0
    expense = snap.get("monthly_expense", 162781) or 162781
    salary = 39727

    # 租金已收（8 月）
    rent_got = 0
    for k, v in (snap.get("rent_received_records", {}) or {}).items():
        if str(k).startswith("2026-08"):
            if isinstance(v, dict):
                rent_got += sum(x for x in v.values() if isinstance(x, (int, float)))
            elif isinstance(v, (int, float)):
                rent_got += v
    got_total = salary + div_total + rent_got

    # ── replace 模板寫死值（2026-08-26 盤點清單）──
    rep = {
        "9,682,433": _fmt(ins),            # 保單總值
        "7,753,544": _fmt(allianz),        # 安聯 A+B
        "1,928,889": _fmt(firstjin),       # 第一金現值
        "111,513": _fmt(cum_div),          # 第一金累計配息
        "88,507": _fmt(div_ins),           # 保單配息合計
        "25,538": _fmt(firstjin_div),      # 第一金本月領息
        "815,066": _fmt(cash),             # 現金
        "227,372": _fmt(got_total),        # 當月已收合計
        "109,645": _fmt(div_total),        # 配息實收
        "78,000": _fmt(rent_got),          # 租金已收
        "162,781": _fmt(expense),          # 月支出
    }
    hits = 0
    for old, new in rep.items():
        if old in tpl:
            tpl = tpl.replace(old, new)
            hits += 1
    (BASE / "index.html").write_text(tpl, encoding="utf-8")
    print(f"✅ 儀表板注入完成（{hits} 組值已更新）｜現金 {_fmt(cash)} / 保單 {_fmt(ins)} / 配息 {_fmt(div_total)} / 租金 {_fmt(rent_got)}")

if __name__ == "__main__":
    main()
