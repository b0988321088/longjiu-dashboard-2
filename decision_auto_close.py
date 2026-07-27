#!/usr/bin/env python3
"""決策自動閉環引擎 — 每日掃描，條件滿足自動 ✅"""
import json, sys
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
DECISIONS = BASE / "pending_decisions.json"
SNAP = BASE / "snapshot.json"
NOTION_LOG = BASE / "notion_decision_logger.py"

def load_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except:
        return []

def save_json(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def check_conditions(d):
    """回傳 (auto_close: bool, reason: str)"""
    title = d.get("title", "")
    status = d.get("status", "")
    today = date.today()

    # ── 00983D方案B ──
    if "00983D" in title and "方案B" in title:
        snap = load_json(SNAP)
        for h in snap.get("securities", {}).get("holdings", []):
            if h["ticker"] == "00983D":
                current_shares = h["shares"]
                target_shares = 100000  # ~100萬/10元
                if current_shares >= target_shares * 0.9:
                    return True, f"00983D已達 {current_shares} 股（目標 {target_shares}）"
                break
        # 也檢查006208和00713是否增加了
        tw_added = False
        for h in snap.get("securities", {}).get("holdings", []):
            if h["ticker"] == "006208" and h["shares"] > 2000:
                tw_added = True
        if tw_added:
            return True, "006208已加碼"
        return False, ""

    # ── 國泰轉貸 ──
    if "國泰轉貸" in title:
        if today >= date(2026, 9, 25):
            snap = load_json(SNAP)
            old_liab = snap.get("mortgage_balance", 0)
            # 如果負債結構改變了，視為已完成
            if old_liab != 13159422:  # 原始值變了
                return True, "房貸結構已變更"
            return False, "9/25到期檢查"
        return False, ""

    # ── 築巢優利貸 ──
    if "築巢" in title or "台銀" in title:
        if today >= date(2026, 10, 1):
            return True, "10/1築巢優利貸生效日已到"
        return False, ""

    # ── 其他：超過30天自動歸檔 ──
    d_date = d.get("date", "")
    try:
        dt = datetime.strptime(d_date, "%Y-%m-%d").date()
        if (today - dt).days > 30 and "待執行" in status:
            return True, f"超過30天未執行，自動歸檔"
    except:
        pass

    return False, ""

def auto_close():
    decisions = load_json(DECISIONS)
    updated = []
    closed = 0
    alerts = []

    for d in decisions:
        auto_close, reason = check_conditions(d)
        if auto_close:
            closed += 1
            # 更新 Notion
            title = d.get("title", "")
            try:
                import subprocess
                subprocess.run(
                    [sys.executable, str(NOTION_LOG), f"✅ {title}", f"自動閉環：{reason}", "", ""],
                    capture_output=True, text=True, timeout=10
                )
            except:
                pass
            print(f"  ✅ {title} → {reason}")
        else:
            # 檢查是否異常（日期過了但條件未達成）
            status = d.get("status", "")
            d_date = d.get("date", "")
            if "等待" in status or "進行中" in status:
                try:
                    dt = datetime.strptime(d_date, "%Y-%m-%d").date()
                    if date.today() > dt:
                        alerts.append(f"⚠️ {d['title']} 預計 {d_date} 完成，已逾期")
                except:
                    pass
            updated.append(d)

    # 更新檔案（移除已閉環的）
    save_json(DECISIONS, updated)

    print(f"\n📋 決策摘要：{len(decisions)} 筆，自動閉環 {closed} 筆，進行中 {len(updated)} 筆")
    for a in alerts:
        print(f"  {a}")

    return closed, alerts

if __name__ == "__main__":
    print(f"🔍 決策自動閉環掃描 — {date.today()}")
    auto_close()
