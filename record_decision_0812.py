# -*- coding: utf-8 -*-
"""2026-08-12 兩層槓桿策略修正版裁決 — 決策治理六步 Step1/2"""
import json, datetime

now = datetime.datetime.now().isoformat(timespec="seconds")
d = json.load(open("dashboard_decisions.json", encoding="utf-8"))

# Step 1: dashboard_decisions.json 追加（source: user）
decision = {
    "timestamp": now,
    "source": "user",
    "category": "決策",
    "action": "核准",
    "name": "兩層槓桿策略修正版（8/12 裁決）",
    "status": "已核准",
    "user": "Laing",
    "idem_key": f"hermes-{int(datetime.datetime.now().timestamp())}",
    "summary": "核心：優先執行第一層1,200萬轉貸（償還800萬高息舊債→現金緩衝≥6個月利息→剩餘分批換匯建美元直債到期梯，持有到期）。第二層債券質押為選擇性加分動作，4門檻全過才執行（US30Y<5.30%＋壓力測試LTV≤50%＋觀察1-3交易日＋雙層成本<債券殖利率），任一不達即終止維持單層。初始質押LTV≤50%不打滿，資金僅限現金流類資產，禁止一周內建債+質押+再投資全套。US30Y≥5.30%全域凍結新增質押。轉貸/質押資金禁止生活消費擴張。",
    "detail": "階段1（強制，不受殖利率紅線約束）：1,200萬撥款未入帳禁止任何換匯/建債/質押；撥款後優先償還800萬高息舊負債並驗證銷帳；保留台幣現金緩衝≥6個月第一層利息；剩餘台幣分批換匯建美元直債到期梯底倉；階段1期間嚴格禁止任何債券質押。階段2（選擇性）：門檻1 US30Y<5.30%；門檻2 壓力測試（美債+50bp+美元貶值3%）LTV≤50%；門檻3 觀察1-3交易日無跳空劇烈波動；門檻4 雙層合計年化借貸成本<債券組合平均到期殖利率。後續應變：已開第二層後US30Y≥5.30%→停止新增質押+逐步降LTV。儀表板&日報強制輸出：單層/雙層年化借貸成本、實際LTV+雙利空模擬LTV、月度利息流出vs現金流入對照、負債vs債券到期日錯配標黃、US30Y凍結線標示。",
    "tags": ["債務重組", "兩層架構", "8/15", "質押", "LTV", "US30Y"],
}
d["decisions"].append(decision)

# Step 2: pending_decisions.json 更新 8/15 部署（改版為階段1/階段2）
pend = d.get("pending_decisions", [])
updated = False
for p in pend:
    if "8/15國泰撥款部署" in p.get("action", ""):
        p["status"] = "🔄 執行中（8/12 改版）：階段1 撥款1,200萬→償還800萬高息舊債→現金緩衝≥6個月利息→剩餘分批換匯建美元直債到期梯（持有到期）；階段2 債券質押為選擇性，4門檻全過才執行"
        p["detail"] = "8/12 裁決：第二層降為選擇性加分，非強制；LTV初始≤50%；US30Y≥5.30%全域凍結新增質押；禁一周內建債+質押+再投資全套"
        updated = True
    if "債券質押 5 成" in p.get("action", ""):
        p["status"] = "⏸️ 選擇性（8/12 改版）：改為階段2，4門檻全過才執行（US30Y<5.30%＋壓力測試LTV≤50%＋觀察期＋成本比較）；不達標維持單層"
        updated = True
if not updated:
    pend.append({
        "date": "2026-08-15", "action": "8/15國泰撥款部署（8/12 改版）",
        "status": "🔄 執行中：階段1 撥款1,200萬→償還800萬高息舊債→現金緩衝→建美元直債梯；階段2 選擇性",
        "tags": "債務重組,8/15,質押",
    })
d["pending_decisions"] = pend

json.dump(d, open("dashboard_decisions.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("✅ dashboard_decisions.json: 追加 8/12 兩層槓桿裁決（source=user）+ pending 更新")
n_user = sum(1 for x in d["decisions"] if x.get("source") == "user")
print(f"   source=user 決策總數: {n_user}")
