#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debt_restructure_tracker.py — 每週日 08:50 追蹤債務重整進度
讀 snapshot.deployment_plan + pending_decisions.json + schedule_events.json，
輸出：各階段狀態、下週關鍵節點、待辦事項。
"""
import json, sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path("C:/Users/bot/Desktop/longjiu_system")
today = date.today()

def load(name):
    try:
        return json.load(open(BASE / name, encoding="utf-8"))
    except Exception as e:
        print(f"⚠️ {name} 讀取失敗: {e}")
        return {}

def main():
    snap = load("snapshot.json")
    pi = snap.get("professional_investor", {})
    plan = pi.get("deployment_plan", {})
    pending = load("pending_decisions.json")
    events = load("schedule_events.json")

    print("=" * 56)
    print(f"🔁 龍九債務重整進度追蹤 | {today.isoformat()}（週日）")
    print("=" * 56)

    # 階段狀態
    timeline = plan.get("timeline", {})
    strat = plan.get("strategy", {})
    print("\n【策略：B先A後（2026-08-09 定案）】")
    if strat:
        ph1 = strat.get("phase1", {})
        ph2 = strat.get("phase2", {})
        print(f"  🔵 第一階段（方案B）: {' / '.join(ph1.get('actions', []))} → 現金 {ph1.get('cash_after','')}")
        print(f"  🟣 第二階段（方案A）: 條件={' + '.join(ph2.get('conditions', []))} → {' / '.join(ph2.get('actions', []))}")
    print("\n【階段時程】")
    for k, v in timeline.items():
        label = {"phase1": "🔵 第一階段 8/15", "phase1b": "🔵 撥款後先辦兆豐信貸 300萬",
                 "phase2": "🟣 洲際W轉貸（國泰）"}.get(k, k)
        print(f"  {label}: {v}")

    # 下週關鍵節點（7 天內）
    print(f"\n【下週關鍵節點（{today.isoformat()} ~ {(today + timedelta(days=7)).isoformat()}）】")
    found = False
    if isinstance(events, list):
        for e in events:
            d = str(e.get("date", e.get("start", "")))[:10]
            try:
                ed = date.fromisoformat(d)
            except:
                continue
            if today <= ed <= today + timedelta(days=7):
                print(f"  📅 {d}: {e.get('item', e.get('title', e.get('summary', '?')))}")
                found = True
    if not found:
        print("  （無）")

    # Pending 決策狀態
    print("\n【執行中決策】")
    pd_list = pending if isinstance(pending, list) else pending.get("decisions", [])
    for d in pd_list:
        t = str(d.get("title", ""))
        if any(k in t for k in ["洲際", "築巢", "信貸", "國泰", "轉貸"]):
            print(f"  ⏳ {d.get('date','?')} {t}: {d.get('status','?')}")

    # 待辦提醒（依日期）
    print("\n【待辦提醒】")
    today_s = today.isoformat()
    if today >= date(2026, 8, 15):
        print("  ✅ 8/15 已到：確認國泰撥款 → 清償 800萬 → 買 500萬債券 → 辦兆豐信貸 300萬")
    else:
        print(f"  ⏳ 8/15 國泰撥款（還有 {(date(2026,8,15)-today).days} 天）→ 清償800萬→買500萬債券→兆豐信貸300萬")
    print("  ⏳ 洲際W（第二間）轉貸：直接跟國泰辦理（非台銀築巢）")
    if today >= date(2026, 9, 25):
        print("  ✅ 9/25 已到：洲際W轉貸評估")
    else:
        print(f"  ⏳ 9/25 洲際W轉貸評估（還有 {(date(2026,9,25)-today).days} 天）")

    # 紀律提醒
    print("\n【紀律提醒】")
    print("  🎵 Rhythm-08：US30Y 警戒區（5.2-5.3）→ 台股≤50萬/週・美股停購・長債不疊")
    print("  💰 500萬債券：短中期 1-3yr 為主，>5yr 凍結；質押等利率<3%確認+成數≤4成")
    print("  🛡️ 現金底線 85萬（6個月）不可破")
    print("=" * 56)

if __name__ == "__main__":
    main()
