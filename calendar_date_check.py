#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calendar_date_check.py — 行事曆日期防呆驗證（INC-136 防範）
在 calendar_sync.py 前執行：列出未來 7 天事件 + 檢查可疑日期。
用法：python calendar_date_check.py [--fix]
"""
import json, sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path("C:/Users/bot/Desktop/longjiu_system")
today = date.today()

def main():
    se = json.load(open(BASE / "schedule_events.json", encoding="utf-8"))
    evs = se if isinstance(se, list) else se.get("events", [])
    
    print(f"📅 行事曆日期檢查｜今天 {today.isoformat()}")
    print("=" * 55)
    
    # 1. 列出未來 7 天事件
    print("\n【未來 7 天事件】")
    found = False
    for e in sorted(evs, key=lambda x: x.get("date", "")):
        d = str(e.get("date", ""))[:10]
        try:
            ed = date.fromisoformat(d)
        except:
            continue
        if today <= ed <= today + timedelta(days=7):
            print(f"  {d}: {e.get('item', '?')}")
            found = True
    if not found:
        print("  （無）")
    
    # 2. 檢查可疑日期（過去 30 天內仍標「行程/待辦」的事件）
    print("\n【⚠️ 可疑事件（已過期仍非完成狀態）】")
    suspicious = 0
    for e in evs:
        d = str(e.get("date", ""))[:10]
        status = str(e.get("status", ""))
        try:
            ed = date.fromisoformat(d)
        except:
            continue
        if ed < today and "完成" not in status and "已" not in status and "✅" not in status:
            print(f"  ⚠️ {d}: {e.get('item', '?')}（status: {status}）")
            suspicious += 1
    if not suspicious:
        print("  ✅ 無")
    
    # 3. 檢查重複（同日期+同 item）
    print("\n【重複檢查】")
    from collections import Counter
    c = Counter((e.get("date", ""), e.get("item", "")) for e in evs)
    dups = {k: v for k, v in c.items() if v > 1}
    if dups:
        for (d, item), n in dups.items():
            print(f"  ⚠️ [{n}次] {d}: {item}")
    else:
        print("  ✅ 無重複")
    
    print("\n" + "=" * 55)
    print("✅ 檢查完成 — 確認無誤後再執行 calendar_sync.py")

if __name__ == "__main__":
    main()
