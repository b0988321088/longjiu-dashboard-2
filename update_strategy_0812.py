# -*- coding: utf-8 -*-
"""2026-08-12 兩層槓桿修正版 — snapshot deployment_plan + rhythm08 + schedule_events 同步"""
import json

SNAP = "snapshot.json"

s = json.load(open(SNAP, encoding="utf-8"))
pi = s.setdefault("professional_investor", {})

# ===== 1) deployment_plan 完整重寫（8/12 版，取代 5-5-2）=====
pi["deployment_plan"] = {
    "status": "兩層槓桿修正版【8/12 裁決】（取代5-5-2；第二層質押降為選擇性加分，非強制）",
    "core_position": "優先執行第一層1,200萬轉貸（負債重組+美元直債底倉，持有到期）；第二層質押是加分題不是必做題，條件不達標就放棄，優先保全策略安全邊界",
    "total": 12000000,
    "phase1_mandatory": {
        "gate_0": "1,200萬撥款未入帳前，禁止任何前置換匯、建債、質押動作",
        "repay_800w": "撥款到帳後優先償還800萬高息舊負債，驗證舊債完整銷帳",
        "cash_buffer": "保留台幣現金緩衝，規模至少覆蓋6個月第一層轉貸利息支出",
        "build_ladder": "剩餘台幣資金分批換匯，搭建美元直債到期梯底倉（3-7Y 375萬 + 8-10Y 125萬；禁30Y；持有到期為核心）",
        "complete_standard": "階段1完成標準：舊負債清除＋直債底倉建立＋現金緩衝到位",
        "forbidden": "階段1期間嚴格禁止任何債券質押；不開啟第二層槓桿；就算收益誘人也不執行",
    },
    "phase2_optional": {
        "nature": "選擇性加分動作，非強制執行；以下門檻全部同時滿足才可執行，任一不滿足直接終止第二層，維持階段1狀態",
        "gate_1": "US30Y殖利率 < 5.30%",
        "gate_2": "壓力測試：美債殖利率再上行50bp + 美元貶值3%，模擬得出 LTV ≤ 50%",
        "gate_3": "階段1全部完成後，觀察1-3個交易日，債券價格、USD/TWD匯率無突發跳空劇烈波動",
        "gate_4": "雙層槓桿合計年化借貸成本，確實低於債券組合平均到期殖利率",
        "constraints": [
            "質押初始LTV最高50%，不得打滿上限",
            "質押釋放資金僅限投入現金流類資產：直債、配息ETF、美債梯；禁止配置成長投機類標的",
            "禁止同一周內完成「建債+質押+再投資」全套連續動作",
        ],
    },
    "global_freeze": "US30Y ≥ 5.30%：全域凍結紅線，禁止新增債券質押（已開啟第二層者：停止所有新增質押，啟動逐步降LTV規劃）",
    "fund_ban": "轉貸、質押取得的資金，禁止用於生活消費擴張",
    "benefit_calc": "階段1單層即具套息價值：800萬×~4.2%高息置換為2.6% ≈ 年省利息32萬；無質押追保機制，債券市價/匯率波動僅承擔每月利息，可安心持有到期",
    "superseded": "5-5-2（2026-08-11）：500萬直接還債+500萬美債+200萬水庫，Lombard 150-175萬 LTV 30-35% — 質押部分被8/12改版取代（還債500萬→800萬、質押150-175萬→階段2選擇性LTV≤50%、5.30%五因子→全域凍結質押）",
}

# ===== 2) rhythm08 rules_note 更新（質押凍結語意）=====
r8 = s.setdefault("rhythm08", {})
rules = r8.get("rules_note", [])
if isinstance(rules, str):
    rules = rules.split("；")
# 更新/追加第 5.30 凍結質押規則
rules = [r for r in rules if "新增債券質押" not in r]
rules.append("US30Y≥5.30%：全域凍結紅線，禁止新增債券質押（8/12 裁決，取代五因子非凍結判斷）")
r8["rules_note"] = rules

json.dump(s, open(SNAP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("✅ snapshot: deployment_plan 8/12 版 + rhythm08 凍結質押規則")

# ===== 3) schedule_events.json 8/15 事件更新 =====
se = json.load(open("schedule_events.json", encoding="utf-8"))
events = se if isinstance(se, list) else se.get("events", [])
n = 0
for e in events:
    txt = str(e.get("item", "")) + str(e.get("title", "")) + str(e.get("note", ""))
    if "8/15" in txt or "國泰" in txt or "撥款" in txt:
        e["note"] = "8/12改版：階段1撥款1,200萬→償還800萬高息舊債(驗證銷帳)→現金緩衝≥6月利息→剩餘分批換匯建美元直債到期梯(3-7Y375+8-10Y125,禁30Y,持有到期)；階段2質押為選擇性(4門檻全過才做,LTV≤50%)；US30Y≥5.30%全域凍結質押"
        n += 1
out = se if isinstance(se, list) else {"events": events}
json.dump(out, open("schedule_events.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"✅ schedule_events: 更新 {n} 筆 8/15/國泰/撥款 事件")
