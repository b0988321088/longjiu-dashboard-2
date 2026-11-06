#! /usr/bin/env python3
import json
from datetime import date, timedelta
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent.parent # longjiu_system

def _fmt(n):
    return f"{n:,.0f}"

def generate_quick_actions():
    # --- 讀取其他狀態檔 ---
    us30y_state = json.loads((BASE / "us30y_state.json").read_text(encoding="utf-8")) if (BASE / "us30y_state.json").exists() else {}
    macro_regime_analysis = json.loads((BASE / "data/macro_regime_analysis.json").read_text(encoding="utf-8")) if (BASE / "data/macro_regime_analysis.json").exists() else {}
    today_date_str = date.today().strftime('%Y-%m-%d')
    tactical_table_path = BASE / f"data/tactical_table_{today_date_str}.json"
    tactical_table_data = json.loads(tactical_table_path.read_text(encoding="utf-8")) if tactical_table_path.exists() else {}
    pnl_alert_data = json.loads((BASE / "data/pnl_rebalance_alert.json").read_text(encoding="utf-8")) if (BASE / "data/pnl_rebalance_alert.json").exists() else {}
    debt_tracker_data = json.loads((BASE / "data/debt_restructure_tracker.json").read_text(encoding="utf-8")) if (BASE / "data/debt_restructure_tracker.json").exists() else {}
    pending_decisions_data = json.loads((BASE / "pending_decisions.json").read_text(encoding="utf-8")) if (BASE / "pending_decisions.json").exists() else []

    # --- US30Y 狀態 ---
    us30y_rate = us30y_state.get("last_rate", 0.0)
    us30y_mode_label = us30y_state.get("mode_label", "數據讀取失敗")
    
    # --- PI 狀態 ---
    pi_status = debt_tracker_data.get("3.PI專業投資人狀態", {}).get("PI_approval_status", "未申請")
    
    # --- 獲利超標提醒 ---\n    pnl_alerts = pnl_alert_data.get("alerts", [])
    
    # --- 戰術對策表 ---\n    tactical_rows = tactical_table_data.get("rows", [])
    
    # --- 熔斷閘門狀態 ---\n    safety_breakers = debt_tracker_data.get("7.熔斷閘門檢查", {}).get("breakers", [])
    
    # --- 下週關鍵節點 ---\n    # Filter out today\'s and past events, get next week\'s. Assuming today is Friday, next Monday is +3 days.
    next_monday = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 + 0) # Adjust for next Monday
    next_week_nodes = [\
        node for node in debt_tracker_data.get("下週關鍵節點", [])\
        if date.fromisoformat(node.get("日期")) >= date.today() and date.fromisoformat(node.get("日期")) <= next_monday + timedelta(days=6) # Capture the whole next week\
    ]

    # --- 宏觀引擎建議 ---\n    macro_rebalance_advice = macro_regime_analysis.get("再平衡建議", [])

    quick_actions = []

    # 1. 宏觀情境：US30Y 狀態
    quick_actions.append(f"<span class='text-orange-400 font-bold'>市場警戒：</span>US30Y {us30y_rate:.2f}% ({us30y_mode_label})")

    # 2. 個人財務硬性鎖定：PI 狀態
    if pi_status != "已正式核准":
        quick_actions.append(f"<span class='text-red-400 font-bold'>PI 未核准：</span>禁 Lombard 質押、10/1 洲際W轉增貸建議延後")
    else:
        quick_actions.append(f"<span class='text-emerald-400 font-bold'>PI 已核准：</span>可評估 Lombard 質押及 10/1 轉增貸")

    # 3. 投資策略建議 (結合 DAA & 再平衡)
    # 台股
    for row in tactical_rows:
        if row.get("資產分類") == "台股市值型成長":
            if row.get("動作") == "增持" and us30y_rate >= 5.20:
                quick_actions.append(f"<span class='text-blue-400 font-bold'>台股：</span>{row.get('動作')} {_fmt(row.get('精算金額', 0))} 元（US30Y警戒，單週≤50萬）")
            elif row.get("動作") == "增持":
                quick_actions.append(f"<span class='text-blue-400 font-bold'>台股：</span>{row.get('動作')} {_fmt(row.get('精算金額', 0))} 元")
            break
    # 美股
    for row in tactical_rows:
        if row.get("資產分類") == "美股市值型成長":
            if row.get("動作") == "減碼":
                quick_actions.append(f"<span class='text-blue-400 font-bold'>美股：</span>{row.get('動作')} {_fmt(row.get('精算金額', 0))} 元（US30Y警戒，停止新增/逢彈減碼）")
            break
    # 債券
    if us30y_rate >= 5.20:
        quick_actions.append(f"<span class='text-orange-400 font-bold'>債券：</span>US30Y警戒，不主動大筆新增長債")
    else:
        arbitrage_status = debt_tracker_data.get("6.套利引擎｜實質淨收益計算", {})
        if arbitrage_status.get("③ 階梯投資等級短債（1-3年）", {}).get("淨利差", 0) > 0.0125:
             quick_actions.append(f"<span class='text-emerald-400 font-bold'>債券：</span>套利引擎綠燈，可評估短債建倉")
        else:
             quick_actions.append(f"<span class='text-slate-400 font-bold'>債券：</span>維持現有配置")

    # 避險衛星
    total_hedge_target = (macro_regime_analysis.get("targetAllocation", {}).get("黃金/實質資產(衛星)", 0) or 0) + \
                         (macro_regime_analysis.get("targetAllocation", {}).get("石油/能源(避險衛星)", 0) or 0)
    if total_hedge_target > 0.01: # Check for a non-negligible target
        quick_actions.append(f"<span class='text-purple-400 font-bold'>避險衛星：</span>黃金/石油新增目標 {total_hedge_target:.1f}%")

    # 獲利超標提醒 (非核心)
    for alert in pnl_alerts:
        if alert.get("type") == "建議再平衡評估":
            quick_actions.append(f"<span class='text-yellow-400 font-bold'>獲利了結：</span>{alert.get('name')} {alert.get('pnl_pct'):.1f}%（{_fmt(alert.get('value', 0))}元），可評估部分了結")

    # 4. 債務管理
    quick_actions.append(f"<span class='text-emerald-400 font-bold'>還債：</span>債務重置淨利差 GREEN，優先償還高息負債")

    # 5. 下週關鍵節點 (僅列出下週一的重點，其他可在戰術任務分頁看)
    # Assuming today is Friday, so next Monday is +3 days.
    next_monday_dt = date.today() + timedelta(days=3) # Assuming today is Friday, so next Monday is +3 days.
    next_monday_events = [
        node for node in pending_decisions_data
        if node.get("date") == next_monday_dt.isoformat()
    ]
    if next_monday_events:
        for event in next_monday_events:
            quick_actions.append(f"<span class='text-indigo-400 font-bold'>下週一 {event.get('date')[5:]}：</span>{event.get('title')}")
            if "PI 認證完成確認" in event.get("title", "") and pi_status == "審核中":
                 quick_actions.append(f"<span class='text-indigo-400 font-bold'>PI 認證預期：</span>{event.get('date')[5:]}，屆時啟動質押流程")
    else:
        quick_actions.append(f"<span class='text-slate-400'>下週一：</span>無特別待辦事項")


    quick_actions_html = "\n".join([f"<li>{item}</li>" for item in quick_actions])
    print(quick_actions_html)

if __name__ == "__main__":
    generate_quick_actions()
