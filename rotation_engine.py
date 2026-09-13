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
    "醫療保健": ["保單健康科學A2（8/24 轉換 50萬涵蓋）"],  # 2026-08-23：台股無純醫療ETF（00970B實為美元公司債/00786查無）
    "金融": ["0055(金融)"],
    "高股息防禦": ["00878", "00713", "0056"],
    "資訊科技": ["0050/006208(含台積電50%)", "00924(純科技)"],
    "核心消費": ["0050(含核心消費成分:統一/大成等)"],  # 2026-08-26 修正：00901=智能車供應鏈(科技)非核心消費，誤標移除
    "公用事業": ["00933B(金融債)"],  # 2026-08-26 修正：00933B=國泰10Y+金融債，非電信債
    "不動產": ["00908(REITs)"],
    "非核心消費": ["0050(含)", "0051(中型100-消費,回檔-5%再進)"],  # 2026-08-23 新增 0051
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
            # 2026-08-27：帶出雷達具體產業明細（使用者要看到「買食品」而非抽象「核心消費」）
            try:
                _tw_flow = (sector_flow.get("台股") or {})
                _det = []
                for _k, _v in _tw_flow.items():
                    if TW_FLOW_TO_GICS.get(_k) == g and isinstance(_v, dict):
                        _amt = _v.get("法人淨買賣超", 0) or 0
                        if abs(_amt) >= 5e6:
                            _det.append(f"{_k} {_amt/1e6:+.0f}M")
                if _det:
                    reason += f"｜{('、'.join(_det[:3]))}"
            except Exception:
                pass
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

    # 2026-09-06 修正：已由保單轉換涵蓋的產業（醫療保健 8/24 轉換 50萬）不得列為「乾粉優先吸納」
    # — 標的欄已註「涵蓋」= 不需新增現金；避免輸出「建議買醫療」與實際狀態矛盾
    for r in rows:
        _tk_str = "".join(str(t) for t in r.get("標的", []))
        if r["動作"].startswith("✅") and ("涵蓋" in _tk_str or "已轉換" in _tk_str):
            r["動作"] = "✅ 已涵蓋（保單轉換）— 不需新增"
            r["理由"] = r["理由"] + "｜但 8/24 已由保單轉換涵蓋，非現金缺口"

    rows.sort(key=lambda r: -r["資金分數"] * 2 + (r.get("目標") or 0) - (r.get("現況") or 0))
    # top = 真正建議「吸納」者；「已涵蓋」是狀態說明，不列入購買建議
    top = [r for r in rows if r["動作"].startswith("✅ 乾粉")]
    avoid = [r for r in rows if r["動作"].startswith("🔴") or r["動作"].startswith("⏸")]

    summary = "本週乾粉："
    if top:
        summary += "優先 " + "、".join(r["產業"] for r in top[:3])
    else:
        # 2026-09-06：無吸納標的（觀望 Gate / 已由保單涵蓋）→ 輸出「保留」語意，
        # 勿留空造成「本週乾粉：；避開…」殘句（日報/CIO prompt 直接讀總結）
        _cov = [r["產業"] for r in rows if r["動作"].startswith("✅ 已涵蓋")]
        summary += "保留（無新增吸納標的" + (f"；{'、'.join(_cov)}已由保單涵蓋" if _cov else "") + "）"
    summary += "；避開 " + ("、".join(r["產業"] for r in avoid[:3]) if avoid else "無")

    return {"日期": TODAY, "建議": top, "避開": avoid, "全產業": rows, "總結": summary}


def build_trade_plan(rec: dict, snap: dict) -> list:
    """明確交易計畫（2026-08-22：使用者要求「講清楚買什麼」）
    乾粉 = 現金 − 70萬底線 + 月盈餘（保守取一半）；依建議優先序分配金額 + 分批節奏"""
    cash = snap.get("cash_total", 0)
    surplus = snap.get("monthly_income", 228751) - snap.get("monthly_expense", 162781)
    dry = max(cash - snap.get("cash_floor", 700000), 0) + surplus * 0.5  # 保守可動用（底線讀 snapshot）
    plan = []
    
    # 2026-09-13：改為全動態（禁止寫死文字/金額）— 資料源＝snapshot + 資金輪動引擎輸出
    import pledge_status
    pf = pledge_status.pledge_facts(snap)

    # ① 債務優化：質押撥款 → 清償高息負債（金額/撥款狀態/月省息全部由 snapshot 算）
    if pf["清償目標"] > 0:
        plan.append({
            "產業": "債務優化",
            "標的": f"清償保單/券商高息負債（{pf['清償目標萬']}）",
            "金額": int(pf["清償目標"]),
            "節奏": ("質押已撥款 → 立即執行" if pf["已撥款"]
                     else "質押撥款到位即執行（"
                          + (f"預估 {pf['撥款預估日']}" if pf["撥款預估日"] else "對保後約 2 週") + "）"),
            "理由": (f"質押 {pf['可貸萬']}@{pf['利率文字']}：月息 {pf['月息_舊']:,.0f} → "
                     f"{pf['月息_新']:,.0f}，月省 {pf['月省息']:,.0f}（{pf['裁示日']} 裁示）"),
        })

    # ② 產業吸納：資金輪動引擎「建議」中動作 ✅ 者；金額由乾粉平均分配（單筆 ≤5 萬節奏）
    buys = [r for r in rec.get("建議", []) if str(r.get("動作", "")).startswith("✅")]
    used = 0
    if buys:
        alloc = int(dry / len(buys) / 1000) * 1000
        for r in buys:
            amt = max(alloc, 10000)
            batch = max(amt // 50000, 1)
            plan.append({
                "產業": r.get("產業", ""),
                "標的": "、".join(r.get("標的") or []) or "—",
                "金額": amt,
                "節奏": f"分 {batch} 批（單筆 ≤5 萬）",
                "理由": r.get("理由", ""),
            })
            used += amt

    # ③ 現金保留：乾粉餘額（動態）；節奏讀防守合併口徑裁示
    _dcm = snap.get("defensive_combined_metric", {}) or {}
    _dcm_note = (f"防守合併 {_dcm.get('佔比', 0):.1f}%（{_dcm.get('裁示', '')}）"
                 if _dcm else "現金底線制")
    plan.append({
        "產業": "現金保留",
        "標的": "台幣活存/MMF",
        "金額": max(int((dry - used) / 1000) * 1000, 0),
        "節奏": f"守住現金底線 {snap.get('cash_floor', 700000):,}；{_dcm_note}",
        "理由": "乾粉餘額緩衝（底線制，不借錢囤現金）",
    })
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
