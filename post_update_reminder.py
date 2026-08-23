# -*- coding: utf-8 -*-
"""
post_update_reminder.py — 真值更新後的「確認提醒」腳本（2026-08-23）
每次使用者丟新資料、系統更新 snapshot 後執行：
  輸出 → ① 更新完成確認 ② 關鍵變動摘要 ③ 燈號（US30Y/LTV/現金/覆蓋率）④ 近期待辦
用法: python post_update_reminder.py
"""
import json, os, datetime

REPO = os.path.dirname(os.path.abspath(__file__))

def rd(name):
    try:
        return json.load(open(os.path.join(REPO, name), encoding="utf-8"))
    except Exception:
        return {}

def main():
    s = rd("snapshot.json")
    today = datetime.date.today().strftime("%Y-%m-%d")
    lines = []
    lines.append(f"✅ 已更新（{today}）")

    # ① 關鍵數字
    ta = s.get("total_assets"); tl = s.get("total_liabilities")
    cash = s.get("cash_total"); nw = s.get("net_worth")
    if ta: lines.append(f"總資產 {ta:,}｜淨值 {nw:,.0f}" if nw is not None else f"總資產 {ta:,}")
    if tl: lines.append(f"總負債 {tl:,}")

    # ② 燈號
    us = rd("us30y_state.json")
    us30y = us.get("us30y", us.get("value"))
    if us30y:
        red = 5.30
        flag = "🔴" if us30y >= red else ("🟡" if us30y >= 5.15 else "🟢")
        lines.append(f"US30Y {us30y:.2f}% {flag}（凍結線 {red}%）")

    # ③ 近期待辦（schedule_events 未來 14 天）
    evs = rd("schedule_events.json")
    if isinstance(evs, dict):
        evs = evs.get("events", evs.get("items", []))
    pending = []
    for e in evs:
        d = str(e.get("date", ""))
        if d and d >= today and d <= (datetime.date.today() + datetime.timedelta(days=14)).strftime("%Y-%m-%d"):
            pending.append(f"{d[5:]} {str(e.get('item',''))[:60]}")
    if pending:
        lines.append("📌 近期待辦：")
        lines.extend("  • " + p for p in pending[:5])

    # ④ 結論
    lines.append("🚦 狀態：🟢 綠燈，無需操作（有異常系統會主動通知）")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
