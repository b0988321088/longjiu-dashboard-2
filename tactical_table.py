#!/usr/bin/env python3
"""tactical_table.py — 目標-對策對照表（P0-1）
從 snapshot 穿透資料產出結構化對策表（JSON + 表格文字）
供週報「資產架構調整指示卡」讀取。

對策邏輯：
- 偏離 ≤2pp：觀察（只寫日誌，不產生交易建議）
- 偏離 2-5pp：戰術觀察（記錄偏移，等資金流入再處理）
- 偏離 5-10pp：中等再平衡（計算調整金額，納入週報指示卡）
- 偏離 >10pp：大規模再平衡（優先等級拉高）
- US30Y >5.30%：整個 TAA 凍結，只保留觀察

輸出：tactical_table_{date}.json
"""
import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent

# 各資產的策略對應（動作/標的/停止條件）
STRATEGY = {
    "台股市值型成長": {
        "action": "增持", "ticker": "00878/0050/006208",
        "note": "00878 每週1,000股建倉；0050 外資連2日買超才加碼",
        "stop": "回到目標區間內｜單筆>5萬停止（核貸前）",
        "freeze_on_us30y": False,
    },
    "美股市值型成長": {
        "action": "減碼", "ticker": "美股科技/00924/00646",
        "note": "8/4核貸後分批；單次≤20萬",
        "stop": "回到目標區間內｜US30Y防禦模式不加碼",
        "freeze_on_us30y": False,
    },
    "防守型配息": {
        "action": "增持", "ticker": "00878/00713/00919",
        "note": "美股減碼資金轉入；等資金流出止穩",
        "stop": "回到目標區間內",
        "freeze_on_us30y": False,
    },
    "債券": {
        "action": "凍結", "ticker": "00983D/PIMCO",
        "note": "00983D不碰（US30Y防禦）；維持底倉",
        "stop": "US30Y<5.20%解除防禦",
        "freeze_on_us30y": True,
    },
    "現金/安全網": {
        "action": "保留", "ticker": "現金",
        "note": "70萬底線不動；超額等核貸後部署",
        "stop": "6個月支出底線",
        "freeze_on_us30y": False,
    },
}

def get_ladder(dev_pct: float) -> dict:
    """階梯式TAA判定（P0-2 共用）"""
    abs_dev = abs(dev_pct)
    if abs_dev <= 2:
        return {"level": "觀察", "priority": "P3", "trade": False,
                "desc": "僅寫入警示日誌，不產生交易建議"}
    if abs_dev <= 5:
        return {"level": "戰術觀察", "priority": "P2", "trade": False,
                "desc": "記錄偏移，等待資金流入再處理，不主動賣出調整"}
    if abs_dev <= 10:
        return {"level": "中等再平衡", "priority": "P1", "trade": True,
                "desc": "計算調整金額，納入週報指示卡"}
    return {"level": "大規模再平衡", "priority": "P0", "trade": True,
            "desc": "優先等級拉高，下週必須處理"}

def build_table(snap: dict, us30y: float = None) -> dict:
    pen = snap.get("penetration", {})
    apct = pen.get("actual_pct", {})
    atwd = pen.get("actual_twd", {})
    targets = pen.get("targets", {})
    total = snap.get("total_assets", 0)

    # 目標區間：目標 ±5pp（可調整）
    target_map = {
        "台股市值型成長": ("台股市值型目標", "台股市值型成長"),
        "美股市值型成長": ("美股市值型目標", "美股市值型成長"),
        "防守型配息": ("配息型目標", "防守型配息"),
        "債券": ("債券型目標", "債券"),
        "現金/安全網": ("現金目標", "現金/安全網"),
    }

    frozen = bool(us30y is not None and us30y > 5.30)
    rows = []
    for asset, (tgt_key, pct_key) in target_map.items():
        tgt = targets.get(tgt_key, 0)
        cur = apct.get(pct_key, 0)
        cur_twd = atwd.get(pct_key, 0)
        dev = cur - tgt
        ladder = get_ladder(dev)

        # 精算調整金額：偏離 × 總資產
        adj_amount = round(abs(dev) / 100 * total) if ladder["trade"] else 0

        strat = STRATEGY.get(asset, {})
        # US30Y 凍結：債券類直接凍結；其他保留觀察
        if frozen and strat.get("freeze_on_us30y"):
            action, trade, amount = "凍結", False, 0
            note = f"US30Y {us30y:.2f}% > 5.30% → TAA凍結（只觀察）"
        elif frozen:
            action, trade, amount = "觀察(凍結期)", False, 0
            note = f"US30Y {us30y:.2f}% 全域凍結，等解除"
        else:
            action = strat.get("action", "觀察")
            trade = ladder["trade"]
            amount = adj_amount
            note = strat.get("note", "")

        rows.append({
            "資產分類": asset,
            "現況占比": round(cur, 1),
            "目標": tgt,
            "目標區間": f"{tgt-5}~{tgt+5}%",
            "偏離pp": round(dev, 1),
            "階梯等級": ladder["level"],
            "優先級": ladder["priority"],
            "建議動作": action,
            "精算金額": amount,
            "觸發條件": ladder["desc"],
            "停止條件": strat.get("stop", ""),
            "是否交易": trade,
        })

    return {
        "date": date.today().isoformat(),
        "us30y": us30y,
        "frozen": frozen,
        "rows": rows,
        "summary": {
            "觀察": sum(1 for r in rows if r["階梯等級"] == "觀察"),
            "戰術觀察": sum(1 for r in rows if r["階梯等級"] == "戰術觀察"),
            "中等再平衡": sum(1 for r in rows if r["階梯等級"] == "中等再平衡"),
            "大規模再平衡": sum(1 for r in rows if r["階梯等級"] == "大規模再平衡"),
        },
        # 專業投資人二策略管控（snapshot professional_investor）
        "professional_investor": snap.get("professional_investor", {}),
    }

def to_markdown(table: dict) -> str:
    """輸出週報可讀的 Markdown 表格（含視覺進度條）"""
    lines = ["| 資產分類 | 進度視覺 | 現況% | 目標 | 偏離pp | 動作 | 精算金額 | 階梯 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in table["rows"]:
        # 視覺進度條：現況/目標比例（滿 20 格）
        _bar_len = max(1, min(20, int(abs(r["現況占比"]) / max(r["目標"], 1) * 20)))
        _bar = "█" * _bar_len + "░" * (20 - _bar_len)
        lines.append(
            f"| {r['資產分類']} | `{_bar}` | {r['現況占比']}% | {r['目標']}% | "
            f"{r['偏離pp']:+.1f} | {r['建議動作']} | {r['精算金額']:,} | "
            f"{r['階梯等級']} |"
        )
    # 專業投資人風控卡（核心-衛星策略）
    pi = table.get("professional_investor", {}) or {}
    if pi:
        lines.append("")
        lines.append("**🎫 專業投資人風控卡｜核心‑衛星保守成長（零槓桿預設）**")
        lines.append(f"- 狀態：{pi.get('status', '申請中')}｜門檻：{pi.get('threshold', 30_000_000):,}｜現況：金融資產含保單 28,220,311｜缺口：{pi.get('gap', 0):,}（可併配偶）")
        _fo = pi.get("force_order", [])
        if isinstance(_fo, list) and _fo:
            lines.append(f"- 強制順序：{' > '.join(_fo[:2])}")
        _mt = pi.get("macro_triggers", {})
        if _mt:
            lines.append(f"- 🔴 宏觀紅線：30Y美債 >5.20% → {_mt.get('警戒線_5.20','停止新增長債/平衡基金')}")
            lines.append(f"- 🟢 友善線：<4.80% 才可評估小槓桿（需高息負債全清+現金≥300萬+擔保≤4成）")
        _fb = pi.get("forbidden", [])
        if isinstance(_fb, list) and _fb:
            lines.append(f"- ⛔ 禁止：{'；'.join(_fb[:2])}")
        # Lombard 橋接還貸（若已定義）
        _lb = pi.get("lombard_bridge", {}) or {}
        if _lb:
            lines.append(f"- 🔁 Lombard橋接：{_lb.get('business_logic','')}")
            _lb_hl = _lb.get("hard_limits", [])
            if isinstance(_lb_hl, list) and _lb_hl:
                lines.append(f"- 🔒 硬性限制：{_lb_hl[0]}；{_lb_hl[1]}")
                if len(_lb_hl) > 2:
                    lines.append(f"   {_lb_hl[2]}")
                    if len(_lb_hl) > 3:
                        lines.append(f"   {_lb_hl[3]}")
            _cw = _lb.get("carry_trade_warning", {}) or {}
            if _cw:
                lines.append(f"- ⚠️ 套利警告：{_cw.get('summary','')}（{_cw.get('positioning','')}）")
                _ag = _cw.get("activation_gates", [])
                if isinstance(_ag, list) and _ag:
                    lines.append(f"- 🔓 開啟門檻（全要達成）：{'；'.join(_ag)}")
            _su = _lb.get("suitable_scenarios", [])
            if isinstance(_su, list) and _su:
                lines.append(f"- ✅ 適合情境：{_su[0][:60]}；{_su[1][:50]}")
            _fb2 = _lb.get("forbidden_scenarios", [])
            if isinstance(_fb2, list) and _fb2:
                lines.append(f"- ⛔ 禁止情境：{_fb2[0][:55]}；{_fb2[1][:50]}")
            _mg = _lb.get("mandatory_gates", [])
            if isinstance(_mg, list) and _mg:
                lines.append(f"- 🔒 強制門檻：{'；'.join(_mg)}")
                lines.append(f"- 🚨 {_lb.get('red_alert_rule','任一不滿足→週報紅色警示，禁止執行')}")
        lines.append(f"- ⚠️ 風險警示：{pi.get('risk_warning', '專業投資人不受金融消保法保障')}")
    return "\n".join(lines)

def main():
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    us30y = None
    try:
        st = json.loads((BASE / "us30y_state.json").read_text(encoding="utf-8"))
        us30y = st.get("last_rate")
    except Exception:
        pass
    table = build_table(snap, us30y)
    out = BASE / f"tactical_table_{date.today().isoformat()}.json"
    out.write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 對策表產出: {out.name}")
    print(f"   US30Y: {us30y} | 凍結: {table['frozen']}")
    print(f"   階梯分布: {table['summary']}")
    print()
    print(to_markdown(table))

if __name__ == "__main__":
    main()
