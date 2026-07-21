#!/usr/bin/env python3
"""Buffett/CTO 穿透分析器（v4 — 動態目標）"""
from __future__ import annotations

import json, os, sqlite3
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
import requests

BASE = Path(__file__).parent.resolve()
load_dotenv(BASE / ".env")
TODAY = date.today().isoformat()

# 5 類穿透目標（固定，對應 asset_class 分類）
TARGETS = {"tw_equity": 35, "us_equity": 30, "defensive": 25, "bond": 5, "cash": 5}
TARGET_LABELS = {"tw_equity":"台股","us_equity":"美股","defensive":"防守","bond":"債券","cash":"現金"}
TARGET_EMOJI = {"tw_equity":"🇹🇼","us_equity":"🇺🇸","defensive":"🛡️","bond":"💵","cash":"💰"}

def _cat_value(db, category: str) -> float:
    """從 asset_class 表計算某分類的穿透市值 (同 _cat2 in run_daily.py)"""
    from collections import defaultdict
    ac = defaultdict(float)
    for r in db.execute("SELECT category, source, SUM(weight) as w FROM asset_class GROUP BY category, source"):
        ac[(r[1], r[0])] = r[2]
    snap = json.loads((BASE / "snapshot.json").read_text("utf-8"))
    def _src_val(src):
        m = {"securities": "securities_total", "fund": "fund_market_value",
             "insurance_fund": "insurance_current_value", "cash": "bonds_cash",
             "bond": "bonds_penetration"}
        k = m.get(src)
        if k == "bonds_cash":
            old_cash = float(snap.get("bonds_cash", 9_697_196) or 0)
            return max(old_cash - 5_812_576, 0) + 33_000
        if k == "bonds_penetration":
            return 2_097_467
        return float(snap.get(k, 0) or 0)
    total = 0
    for (src, cat), weight in ac.items():
        if cat == category:
            sw = sum(w for (s, c), w in ac.items() if s == src)
            total += _src_val(src) * weight / max(sw, 1)
    return total

def penetration_analysis(snapshot: dict) -> dict:
    """動態穿透分析 — 從 db 即時計算"""
    db_path = str(BASE / "dragon_assets.db")
    if not os.path.exists(db_path):
        return {"error": "db not found"}
    db = sqlite3.connect(db_path)
    
    actual = {}
    actual_twd = {}
    for cat in ["tw_equity", "us_equity", "defensive", "bond", "cash"]:
        v = _cat_value(db, cat)
        actual_twd[cat] = v
    db.close()
    
    total_inv = sum(actual_twd.values()) or 1
    for cat in actual_twd:
        actual[cat] = actual_twd[cat] / total_inv * 100
    
    gaps = {}
    for cat in TARGETS:
        gaps[cat] = actual.get(cat, 0) - TARGETS[cat]
    
    growth_pct = actual.get("tw_equity", 0) + actual.get("us_equity", 0)
    defense_pct = actual.get("defensive", 0)
    safety_pct = actual.get("bond", 0) + actual.get("cash", 0)
    growth_target = TARGETS["tw_equity"] + TARGETS["us_equity"]  # 65
    defense_target = TARGETS["defensive"]  # 25
    safety_target = TARGETS["bond"] + TARGETS["cash"]  # 10
    
    key_risk, key_action = "", ""
    max_gap_cat = max(gaps, key=lambda k: abs(gaps[k]))
    if gaps[max_gap_cat] > 5:
        key_risk = f"{TARGET_EMOJI[max_gap_cat]}{TARGET_LABELS[max_gap_cat]} 超標 +{gaps[max_gap_cat]:.1f}pp"
        if max_gap_cat in ("us_equity",):
            key_action = "等反彈確認後減碼至目標"
    elif gaps[max_gap_cat] < -5:
        key_risk = f"{TARGET_EMOJI[max_gap_cat]} {TARGET_LABELS[max_gap_cat]} 不足 {gaps[max_gap_cat]:.1f}pp"
        if max_gap_cat in ("tw_equity", "defensive"):
            key_action = f"逢低補碼至目標 {TARGETS[max_gap_cat]:.0f}%"
    
    return {
        "actual": actual,
        "actual_twd": actual_twd,
        "gaps": gaps,
        "growth_pct": growth_pct,
        "defense_pct": defense_pct,
        "safety_pct": safety_pct,
        "growth_target": growth_target,
        "defense_target": defense_target,
        "safety_target": safety_target,
        "raw": actual_twd,
        "key_risk": key_risk,
        "key_action": key_action,
        "total_inv": total_inv,
    }

def generate_buffett_report(pen: dict, market_text: str = "") -> list:
    """動態生成巴菲特文字"""
    lines = []
    a, g = pen["actual"], pen["gaps"]
    
    lines.append("🧓 巴菲特式思考（動態穿透模型）")
    if pen["key_risk"]:
        lines.append(f"• 主要偏離：{pen['key_risk']}")
    if pen["key_action"]:
        lines.append(f"• 建議：{pen['key_action']}")
    
    lines.append(f"• 總投資部位：{pen['total_inv']:,.0f} TWD")
    for cat in ["tw_equity", "us_equity", "defensive", "bond", "cash"]:
        v = a.get(cat, 0)
        t = TARGETS[cat]
        gv = g.get(cat, 0)
        sign = "+" if gv >= 0 else ""
        lines.append(f"  {TARGET_EMOJI[cat]} {TARGET_LABELS[cat]}：{v:.1f}%（目標 {t}%，{sign}{gv:.1f}pp）")
    
    lines.append(f"• 成長：{pen['growth_pct']:.1f}%（目標 {pen['growth_target']}%）")
    lines.append(f"• 防禦：{pen['defense_pct']:.1f}%（目標 {pen['defense_target']}%）")
    lines.append(f"• 安全網（債+現金）：{pen['safety_pct']:.1f}%（目標 {pen['safety_target']}%）")
    
    # 風險
    lines.append("")
    lines.append("⚡ 主要風險：")
    for cat in ["tw_equity", "us_equity", "defensive", "bond", "cash"]:
        gv = g.get(cat, 0)
        if abs(gv) > 5:
            direction = "超標" if gv > 0 else "不足"
            lines.append(f"  {TARGET_EMOJI[cat]} {TARGET_LABELS[cat]} {direction} {abs(gv):.1f}pp")
    
    # 安全邊際
    lines.append("")
    lines.append("💡 安全邊際：")
    lines.append(f"  現金佔比 {a.get('cash', 0):.1f}%（目標 {TARGETS['cash']}%）")
    lines.append(f"  債券佔比 {a.get('bond', 0):.1f}%（目標 {TARGETS['bond']}%）")
    
    lines.append("")
    lines.append("🎯 策略建議：")
    for cat in ["tw_equity", "us_equity", "defensive"]:
        gv = g.get(cat, 0)
        if gv < -5:
            lines.append(f"  ✅ {TARGET_LABELS[cat]}逢低補碼{abs(gv):.0f}pp")
        elif gv > 5:
            lines.append(f"  ⚠️ {TARGET_LABELS[cat]}減碼{gv:.0f}pp")
        else:
            lines.append(f"  ✅ {TARGET_LABELS[cat]}合理範圍")
    
    return lines

def generate_cto_report(pen: dict, market_text: str = "") -> list:
    """CTO 技術視角"""
    lines = ["CTO 技術視角", "建議動作："]
    for cat in ["tw_equity", "us_equity", "defensive", "bond", "cash"]:
        gv = pen["gaps"].get(cat, 0)
        if abs(gv) > 5:
            direction = "減碼" if gv > 0 else "補碼"
            lines.append(f"  {cat}：{direction} {abs(gv):.0f}pp")
    lines.append("")
    lines.append("再平衡：優先處理最大偏離類別")
    return lines

def main():
    # 1. 從 snapshot 讀取
    snap = json.loads((BASE / "snapshot.json").read_text("utf-8"))
    
    # 2. 穿透分析
    pen = penetration_analysis(snap)
    if "error" in pen:
        print(f"Error: {pen['error']}"); return
    
    # 3. 市場情報
    market = snap.get("market", {})
    tw_idx = market.get("twii", "N/A")
    
    # 4. 產生報告
    buffett = generate_buffett_report(pen)
    cto = generate_cto_report(pen)
    
    report = "\n".join(buffett) + "\n\n" + "\n".join(cto)
    print(report)
    
    # 5. 存檔
    (BASE / f"buffett_cto_report_{TODAY}.md").write_text(report, encoding="utf-8")
    print(f"\n✅ Report saved to buffett_cto_report_{TODAY}.md")
    
    # 6. Telgram 推（摘要）
    if TG_TOKEN and TG_CHAT_ID:
        msg = f"🧓 Buffett/CTO 動態分析 {TODAY}\n"
        for cat in ["tw_equity", "us_equity", "defensive", "bond", "cash"]:
            v = pen["actual"].get(cat, 0)
            t = TARGETS[cat]
            gv = pen["gaps"].get(cat, 0)
            msg += f"{TARGET_EMOJI[cat]} {v:.1f}%（目標{t}%、{'✅' if abs(gv)<=5 else '+'+str(gv)[:4] if gv>0 else str(gv)[:4]}pp）\n"
        msg += f"\n{pen['key_risk']}\n{pen['key_action']}"
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                         json={"chat_id": TG_CHAT_ID, "text": msg}, timeout=10)
        except: pass

if __name__ == "__main__":
    main()
