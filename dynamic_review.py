#!/usr/bin/env python3
"""dynamic_review.py — 動態自我檢討數據彙整
輸出結構化摘要供 LLM agent 產出「動態自我檢討週報/月報」。
用法：python dynamic_review.py [weekly|monthly]
"""
import json, sqlite3, sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "weekly"
    snap = json.load(open(BASE / "snapshot.json", encoding="utf-8"))
    pen = snap.get("penetration", {})
    atwd = pen.get("actual_twd", {}); apct = pen.get("actual_pct", {})
    hist = json.load(open(BASE / "asset_diff_history.json", encoding="utf-8"))
    db = sqlite3.connect(str(BASE / "dragon_assets.db"))

    print("=== 動態自我檢討數據彙整 ===")
    print(f"[模式] {mode}")
    print(f"[日期] {date.today().isoformat()}")

    # 穿透
    print("\n[穿透配置]")
    for k in ["台股市值型成長", "美股市值型成長", "防守型配息", "債券", "現金/安全網"]:
        print(f"  {k}: {apct.get(k, 0)}% ({atwd.get(k, 0):,.0f})")
    print(f"  總資產: {snap.get('total_assets', 0):,}")

    # 模式
    try:
        st = json.load(open(BASE / "us30y_state.json", encoding="utf-8"))
        print(f"\n[模式] {st.get('mode', '未觸發')} (US30Y 最近: {st.get('last_rate')} @ {st.get('last_date')})")
    except Exception:
        print("\n[模式] 未觸發（無 state）")

    # 本週資產變化
    dates = sorted(hist.keys())
    if mode == "weekly":
        start = dates[-8] if len(dates) >= 8 else dates[0]
    else:
        start = next((d for d in dates if d >= (date.today().replace(day=1) - timedelta(days=45)).isoformat()), dates[0])
    end = dates[-1]
    h0, h1 = hist.get(start, {}), hist.get(end, {})
    print(f"\n[資產變化] {start} → {end}")
    for k, label in [("total_assets", "總資產"), ("insurance_current", "保險"), ("securities_market", "證券"), ("fund_market", "基金"), ("cash", "現金")]:
        v0, v1 = h0.get(k, 0) or 0, h1.get(k, 0) or 0
        print(f"  {label}: {v0:,.0f} → {v1:,.0f} ({v1 - v0:+,.0f})")

    # 負債
    row = db.execute("SELECT * FROM liabilities ORDER BY date DESC LIMIT 1").fetchone()
    if row:
        print(f"\n[負債] 總負債 {row[-2]:,.0f}（房貸 {row[1]:,.0f}+{row[2]:,.0f}+{row[3]:,.0f} 保單借貸 {row[4]:,.0f} 質押 {row[5]:,.0f}）")

    # 被動收入
    print(f"\n[被動收入] 保單 {snap.get('monthly_dividend_total', 0):,.0f} + 房租 {snap.get('rent_monthly_total', 0):,.0f}")

    # 決策回顧（近 14 天）
    dec = json.load(open(BASE / "dashboard_decisions.json", encoding="utf-8"))
    recent = [x for x in dec.get("decisions", []) if x.get("timestamp", "")[:10] >= (date.today() - timedelta(days=14)).isoformat()]
    print(f"\n[近14天決策/事件 {len(recent)} 筆]")
    for x in recent[-10:]:
        print(f"  [{x.get('timestamp','')[:16]}] {x.get('summary', x.get('name',''))[:60]}")

    # 階段狀態
    print(f"\n[階段] 國泰核貸: {snap.get('cathay_refinance_note', '審查中')[:60]}")
    print(f"[現金底線] 現金 {snap.get('real_liquid_assets', 0):,} vs 6個月支出 {snap.get('monthly_expense', 141958) * 6:,.0f}")

    # P0-1 目標-對策對照表（tactical_table.py）
    try:
        from tactical_table import build_table, to_markdown
        us30y = None
        try:
            _st = json.load(open(BASE / "us30y_state.json", encoding="utf-8"))
            us30y = _st.get("last_rate")
        except Exception:
            pass
        _tbl = build_table(snap, us30y)
        print(f"\n[目標-對策對照表] US30Y={us30y} 凍結={_tbl['frozen']}")
        print(to_markdown(_tbl))
        # 儲存快照供閉環追蹤
        try:
            from action_loop import save_snapshot
            save_snapshot(_tbl, snap)
        except Exception as _e:
            print(f"  (快照略過: {_e})")
    except Exception as _e:
        print(f"\n[目標-對策對照表] 產生失敗: {_e}")

    # P1-4 月戰略檢討（僅 monthly 模式）
    if mode == "monthly":
        try:
            from monthly_strategy_review import build_monthly_review, to_markdown as _md
            us30y = None
            try:
                _st = json.load(open(BASE / "us30y_state.json", encoding="utf-8"))
                us30y = _st.get("last_rate")
            except Exception:
                pass
            _rev = build_monthly_review(snap, us30y)
            print(f"\n[月戰略檢討] {_rev['month']}")
            print(_md(_rev))
        except Exception as _e:
            print(f"\n[月戰略檢討] 產生失敗: {_e}")

    db.close()

if __name__ == "__main__":
    main()
