# -*- coding: utf-8 -*-
"""rotation_engine.py — Phase 3 產業輪動引擎（2026-08-22）
把「產業資金流向（Phase 2 雷達）」×「GICS 產業分布缺口（Phase 1）」結合成輪動建議：
資金流入 + 產業低配 → 乾粉優先吸納；資金流出 + 超配/貼近紅線 → 避開。

輸入：snapshot.industry_penetration + radar_state.sector_flow
輸出：snapshot.rotation_recommendation（儀表板/日報/週六再平衡讀）
"""
import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent.resolve()
TODAY = date.today().isoformat()

# GICS 產業目標（防禦缺口補強口徑，8/22 定版）
GICS_TARGETS = {
    "資訊科技": {"目標": None, "紅線": 30.0, "note": "紅線制：>30% 凍結"},
    "金融": {"目標": 8.0, "note": "穩健防守"},
    "醫療保健": {"目標": 8.0, "note": "防禦缺口補強"},
    "核心消費": {"目標": 5.0, "note": "防禦缺口補強"},
    "公用事業": {"目標": 3.0, "note": "防禦缺口補強"},
    "不動產": {"目標": 0.0, "note": "實體不動產 3,401萬 已超配（佔含不動產總資產 56%）— REITs 不建議加碼"},
    "非核心消費": {"目標": 5.0, "note": ""},
    "工業": {"目標": 5.0, "note": ""},
    "通訊服務": {"目標": 4.0, "note": ""},
    "原物料": {"目標": 3.0, "note": ""},
    "能源": {"目標": 2.0, "note": "石油 Locked（COT 紅燈）"},
}

# 台股資金桶 → GICS 近似映射
TW_FLOW_TO_GICS = {
    "科技": "資訊科技", "台積電": "資訊科技", "通訊服務": "通訊服務",
    "金融": "金融", "高股息防禦": "金融", "生技醫療": "醫療保健",
    "食品": "核心消費", "塑化": "原物料", "鋼鐵": "原物料", "原物料避險": "原物料",
    "能源": "能源", "汽車": "非核心消費", "百貨": "非核心消費",
    "營建": "工業", "航運": "工業", "不動產": "不動產",
}

# 美股板塊 ETF → GICS 映射
US_TK_TO_GICS = {
    "科技(XLK)": "資訊科技", "金融(XLF)": "金融", "醫療(XLV)": "醫療保健",
    "能源(XLE)": "能源", "非核心消費(XLY)": "非核心消費", "核心消費(XLP)": "核心消費",
    "工業(XLI)": "工業", "公用(XLU)": "公用事業", "不動產(XLRE)": "不動產", "原物料(XLB)": "原物料",
}

# 產業 → 可操作標的（台幣優先）
INDUSTRY_TICKERS = {
    "醫療保健": ["00786(醫療)", "00970B(醫療債)"],
    "金融": ["0055(金融)", "00878(含金融)"],
    "高股息防禦": ["00878", "00713", "0056"],
    "資訊科技": ["0050/006208(含台積電50%)", "00924(純科技)"],
    "核心消費": ["00901(新消費)"],
    "公用事業": ["00933B(電信債)"],
    "不動產": ["00908(REITs)"],
    "非核心消費": ["0050(含)"] ,
    "工業": ["0050(含)"],
    "原物料": ["00677U(富時100含原物料)"],
}


def build_recommendation(industry_pen: dict, sector_flow: dict) -> dict:
    """資金分數 × 缺口分數 → 輪動建議"""
    inds = industry_pen.get("產業", {}) if industry_pen else {}
    tw_flow = sector_flow.get("台股", {}) if sector_flow else {}
    us_flow = sector_flow.get("美股", {}) if sector_flow else {}

    # 資金分數：台股桶 + 美股板塊 → GICS
    fund_score = {}
    for bucket, v in tw_flow.items():
        g = TW_FLOW_TO_GICS.get(bucket)
        if g and isinstance(v, dict):
            d = v.get("方向", "neutral")
            fund_score[g] = fund_score.get(g, 0) + (1 if d == "inflow" else (-1 if d == "outflow" else 0))
    for tk, v in us_flow.items():
        g = US_TK_TO_GICS.get(tk)
        if g and isinstance(v, dict):
            d = v.get("方向", "neutral")
            fund_score[g] = fund_score.get(g, 0) + (1 if d == "inflow" else (-1 if d == "outflow" else 0))

    rows = []
    for g, conf in GICS_TARGETS.items():
        cur = inds.get(g, {}).get("佔比", 0) if inds else 0
        tgt, red = conf.get("目標"), conf.get("紅線")
        gap = (tgt - cur) if tgt else None  # 缺口：正=該補
        over = (cur - red) if red else None  # 超紅線：正=超標
        fs = fund_score.get(g, 0)

        reason, action, priority = "", "", 0
        if over and over > 0:
            priority = -3
            action = "🔴 超紅線：凍結加碼"
            reason = f"現況 {cur:.1f}% 超紅線 {red}%"
        elif gap is not None and gap > 2 and fs >= 1:
            priority = 3
            action = "✅ 乾粉優先吸納"
            reason = f"資金流入（{fs:+d}）+ 低配 {cur:.1f}% vs 目標 {tgt:.0f}%（缺口 {gap:.1f}pp）"
        elif gap is not None and gap > 2 and fs == 0:
            priority = 1
            action = "🟡 觀察（資金中性）"
            reason = f"低配 {cur:.1f}% vs 目標 {tgt:.0f}% 但資金未明顯流入"
        elif gap is not None and gap > 2 and fs < 0:
            priority = -1
            action = "⏸ 暫緩（資金流出）"
            reason = f"低配但資金流出（{fs:+d}）— 等止穩"
        elif fs <= -2:
            priority = -2
            action = "⏸ 避開（資金流出）"
            reason = f"資金流出（{fs:+d}）"
        else:
            action = "維持現況"
            reason = f"現況 {cur:.1f}%"

        rows.append({"產業": g, "現況": round(cur, 1), "目標": tgt, "紅線": red,
                     "資金分數": fs, "動作": action, "理由": reason,
                     "標的": INDUSTRY_TICKERS.get(g, [])})

    rows.sort(key=lambda r: -r["資金分數"] * 2 + (r.get("目標") or 0) - (r.get("現況") or 0))
    top = [r for r in rows if r["動作"].startswith("✅")]
    avoid = [r for r in rows if r["動作"].startswith("🔴") or r["動作"].startswith("⏸")]

    summary = "本週乾粉："
    if top:
        summary += "優先 " + "、".join(r["產業"] for r in top[:3])
    summary += "；避開 " + ("、".join(r["產業"] for r in avoid[:3]) if avoid else "無")

    return {"日期": TODAY, "建議": top, "避開": avoid, "全產業": rows, "總結": summary}


def build_trade_plan(rec: dict, snap: dict) -> list:
    """明確交易計畫（2026-08-22：使用者要求「講清楚買什麼」）
    乾粉 = 現金 − 70萬底線 + 月盈餘（保守取一半）；依建議優先序分配金額 + 分批節奏"""
    cash = snap.get("cash_total", 0)
    surplus = snap.get("monthly_income", 225918) - snap.get("monthly_expense", 152781)
    dry = max(cash - 700000, 0) + surplus * 0.5  # 保守可動用
    plan = []
    # 分配比例：醫療 40% / 高股息防禦 40% / 金融 20%（高股息=台股法人流入最強+防守優先裁示）
    alloc = {"醫療保健": 0.40, "高股息防禦": 0.40, "金融": 0.20}
    tickers = {"醫療保健": "00786(醫療)、00970B(醫療債)", "高股息防禦": "00878、00713、0056",
               "金融": "0055(金融)"}
    reasons = {
        "醫療保健": "資金流入(美股XLV RS最強) + 低配缺口",
        "高股息防禦": "台股法人 +29百萬流入（最強）+ 防守優先裁示",
        "金融": "資金中性 + 金融 7.3% 穩健",
    }
    # 2026-08-23 修正：高股息防禦（00878/00713/0056）不再直接納入 —
    # 8/21 裁示「防守承接凍結」（defensive_combined_metric 69.7% 已足），引擎須讀 snapshot 狀態
    _dcm = snap.get("defensive_combined_metric", {}) or {}
    _def_frozen = "凍結" in str(_dcm.get("裁示", "")) or float(_dcm.get("佔比", 0) or 0) >= 60
    rec_inds = {r["產業"] for r in rec.get("建議", [])}
    target_inds = [i for i in ["醫療保健", "金融"] if i in rec_inds]
    if not _def_frozen:
        target_inds.insert(0, "高股息防禦")  # 防守合併未足（<60%）才買高股息
    used = 0
    for ind in target_inds:
        ratio = alloc.get(ind, 0.20)
        amt = int(dry * ratio / 1000) * 1000
        if amt < 10000:
            amt = 10000
        batch = max(amt // 10000, 1)
        plan.append({
            "產業": ind,
            "標的": tickers.get(ind, ""),
            "金額": amt,
            "節奏": f"分 {batch} 批 × {amt//batch//1000}千/週（單筆≤5萬）",
            "理由": reasons.get(ind, ""),
        })
        used += amt
    plan.append({"產業": "現金保留", "標的": "台幣活存/MMF", "金額": max(int((dry - used) / 1000) * 1000, 0),
                 "節奏": "等 8/24 轉換 + 9/3 PI 再動", "理由": "乾粉餘額緩衝"})
    return plan


def main():
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    radar = json.loads((BASE / "radar_state.json").read_text(encoding="utf-8"))
    # 實體資產扣減（2026-08-22：持有實體不動產 → 金融 REITs 目標歸零，避免引擎建議加碼已超配資產）
    re_val = snap.get("real_estate_value", 0)
    if re_val > 0:
        GICS_TARGETS["不動產"]["目標"] = 0.0
        GICS_TARGETS["不動產"]["note"] = f"實體不動產 {re_val/1e4:.0f}萬 已超配（含不動產總資產 {re_val/(snap.get('total_assets',0)+re_val)*100:.0f}%）— REITs 不建議加碼"
    rec = build_recommendation(snap.get("industry_penetration", {}), radar.get("sector_flow", {}))
    rec["交易計畫"] = build_trade_plan(rec, snap)
    snap["rotation_recommendation"] = rec
    (BASE / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ rotation_recommendation 已寫入 snapshot（{TODAY}）")
    print(f"總結：{rec['總結']}")
    for r in rec["建議"]:
        print(f"  ✅ {r['產業']}：{r['理由']}｜標的 {r['標的']}")
    for r in rec["避開"][:3]:
        print(f"  {r['動作']} {r['產業']}：{r['理由']}")


if __name__ == "__main__":
    main()
