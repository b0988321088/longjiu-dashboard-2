#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三輪：現行層殘留（CIO 複審後）再清一次。
針對 snapshot 內仍以「現況/待追蹤」姿態出現的舊質押口徑，與 dashboard_decisions 的執行中條目。
歷史塊（weekly_ops_closure_08xx / ruling_* / passive_income_strategy_0826 …）若屬敘述紀錄則只加標記。
"""
import json
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
MARK = "⛔ 已作廢（9/12 取代，口徑清查 9/15）："
NOW = "｜現行＝整池質押 540萬@2.77%（1,200萬×4.5成）清償 500萬高息負債（9/25 撥款）"

ANNOTATE = [   # (路徑, 期望原始片段)
    (".cathay_disbursement.plan_0820_final.執行摘要", "MMF 600萬 轉 10月標案預備金"),
    (".cathay_disbursement.plan_0820_final.時程.PI後", "辦理質押 350萬@2.77%"),
    (".cathay_disbursement.plan_0820_final.質押計畫.安全值_0822.三池現況.富達池.借款", "350萬@2.77%"),
    (".cathay_disbursement.plan_0820_final.質押計畫.安全值_0822.合計.擴張版", "借款 350萬 = LTV 17.9%"),
    (".cathay_disbursement.plan_0820_final.fidelity_fund.風險檢核_20260820.建議[2]", "動用標案預備金還質押"),
    (".rebalance_plan_0819.note_0820", "MMF PI後轉標案預備金"),
    (".usd_hike_evaluation.因應[2]", "質押 350萬利率書面鎖定"),
    (".passive_income_strategy_0826.排序.🥇1", "質押還債（PI後 350萬@2.77%"),
    (".optimization_priority_0828.排序[1].🥈", "PI 質押 350萬 還債"),
    (".weekly_ops_closure_0826.閉環.待追蹤[1]", "質押 350萬還債"),
    (".weekly_ops_closure_0831.閉環.待追蹤[2]", "質押 350萬還債"),
    (".ruling_20260827b.最終指令.質押", "350萬僅還債"),
]
REPLACE = [
    (".weekly_ops_closure_0901.閉環.待追蹤[2]",
     "✅ 質押額度已核定（9/11, 540萬@2.77%＝1,200萬×4.5成）；❌ 尚未對保（9/12 更正）→ 對保後約 2 週撥款 ~9/25 → 清償 500萬高息負債"),
    (".weekly_ops_closure_0908.執行清單[1].狀態",
     "⛔ 已作廢（9/11 取代）：原『國泰貨基 500萬＝標案預備金』→ 實際 9/9 贖回、9/11 轉申購貝萊德B11（質押擔保池）；美債 5 階 ladder 延至 10 月標案結果"),
    (".weekly_ops_closure_0908.執行清單[2].金額",
     "540萬質押（1,200萬×4.5成，9/11 額度核定、未對保）"),
    (".debt_schedule[3].項目",
     "國泰整池質押 540萬@2.77%（額度已核定 9/11、未對保）→ 撥款後清償 500萬高息負債（保單400＋券商100）"),
    (".pending_decision_status_0830.清單[0]",
     "9/11 質押額度核定 540萬@2.77%（未對保、~9/25 撥款）→ 清償 500萬高息負債（原『質押350萬還債』已作廢）"),
]

def getp(d, path):
    cur = d
    for k in path.strip(".").split("."):
        if "[" in k:
            name, idx = k[:-1].split("[")
            cur = cur[name][int(idx)]
        else:
            cur = cur[k]
    return cur

def setp(d, path, val):
    cur = d
    parts = path.strip(".").split(".")
    for k in parts[:-1]:
        if "[" in k:
            name, idx = k[:-1].split("[")
            cur = cur[name][int(idx)]
        else:
            cur = cur[k]
    last = parts[-1]
    if "[" in last:
        name, idx = last[:-1].split("[")
        cur[name][int(idx)] = val
    else:
        cur[last] = val

changes = []
snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
for path, expect in ANNOTATE:
    old = getp(snap, path)
    if not isinstance(old, str):
        changes.append(f"⚠️ 非字串，略過 {path}"); continue
    if old.startswith(MARK):
        continue
    if expect not in old:
        changes.append(f"⚠️ 未命中 {path}（找不到「{expect}」）"); continue
    setp(snap, path, MARK + old + NOW)
    changes.append(f"標記 {path}")

for path, new in REPLACE:
    old = getp(snap, path)
    if old == new:
        continue
    setp(snap, path, new)
    changes.append(f"更正 {path}")

(BASE / "snapshot.json.bak-0915pass3").write_text(
    (BASE / "snapshot.json").read_text(encoding="utf-8"), encoding="utf-8")
(BASE / "snapshot.json").write_text(
    json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))  # 驗證
changes.append("✅ snapshot.json 已寫入並驗證")

# dashboard_decisions：執行中條目
dp = BASE / "dashboard_decisions.json"
dd = json.loads(dp.read_text(encoding="utf-8"))
(dd and None)
for i, e in enumerate(dd.get("decisions", [])):
    st = str(e.get("status", ""))
    if st.startswith("🔄 執行中") and ("350萬" in st or "700萬" in st or "標案預備金" in st):
        e["status"] = ("🔄 執行中（9/11／9/12 最終定案）：整池質押 540萬@2.77%（富達600＋聯博100＋貝萊德B11 500＝1,200萬×4.5成；"
                       "9/11 僅額度核定、未對保，~9/25 撥款）→ 全數清償 500萬高息負債（保單400＋券商100）；"
                       "⛔ 原『700萬池×50%=350萬@2.8%』『MMF 餘350萬＝標案金』已作廢；10月押標金 240萬 來源延 9 月底評估；"
                       "補台幣資產走券商ETF(00878/00713/0050/006208)不買銀行基金")
        changes.append(f"dashboard_decisions.decisions[{i}].status 更正為最終定案")
dp.write_text(json.dumps(dd, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
json.loads(dp.read_text(encoding="utf-8"))
changes.append("✅ dashboard_decisions.json 已寫入並驗證")

print("\n".join(changes))
