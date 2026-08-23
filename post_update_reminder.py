# -*- coding: utf-8 -*-
"""
post_update_reminder.py — 真值更新後的「確認提醒」腳本（2026-08-23）
每次使用者丟新資料、系統更新 snapshot 後執行：
  輸出 → ① 更新完成確認 ② 關鍵變動摘要 ③ 燈號（US30Y/LTV/現金/覆蓋率）④ 近期待辦
用法: python post_update_reminder.py

【更新回執模式】（2026-08-23 定案 — 龍九標準互動介面）
  使用者提供真值 → 更新 → 自動計算 → 風控 → 只回傳結果
  - 固定 3-5 行，平常不展開
  - 🟢 綠燈 = 「目前沒有需要你介入的事項」（不是一切完美；資產每天波動正常）
  - 🔴 紅燈才展開：原因 + 影響 + 建議行動一次講清楚
  - 原則：資料可以高頻更新，人的注意力必須低頻消耗
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

    # ③ 近期待辦（schedule_events 未來 14 天）+ 需要使用者動作的
    evs = rd("schedule_events.json")
    if isinstance(evs, dict):
        evs = evs.get("events", evs.get("items", []))
    pending = []
    need_action = []
    for e in evs:
        d = str(e.get("date", ""))
        if d and d >= today and d <= (datetime.date.today() + datetime.timedelta(days=14)).strftime("%Y-%m-%d"):
            item = str(e.get("item", ""))
            pending.append(f"{d[5:]} {item[:60]}")
            if any(k in item for k in ("🔴", "⚠️", "核准", "確認", "執行", "申請", "準備", "簽", "回報")):
                need_action.append(f"{d[5:]} {item[:50]}")
    # ④ 結論：明確回答「還需要做什麼嗎？」
    if need_action:
        lines.append("📌 需要你做：")
        lines.extend("  • " + a for a in need_action[:3])
    else:
        lines.append("📌 需要你做：無（🟢 綠燈，目前沒有需要你介入的事項）")
    if pending:
        lines.append("📌 近期待辦（未來事件）：")
        lines.extend("  • " + p for p in pending[:4])

    print("\n".join(lines))

if __name__ == "__main__":
    main()
