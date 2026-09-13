# -*- coding: utf-8 -*-
"""最後兩處資料層殘留（2026-09-13）：dashboard_decisions 9/11 條目、snapshot fed_hike_monitor"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
DEC = BASE / "dashboard_decisions.json"

NEW_USE = ("→ 全數優先清償 500萬高息負債（保單質押 400萬@4%＋券商質押 100萬@3.92%）"
           "（2026-09-12 裁示：原『還安聯300萬@4.2%+元大50萬@3.92%』作廢；押標金不預留、9月底評估）")

# 1) dashboard_decisions
dec = json.loads(DEC.read_text(encoding="utf-8"))
n = 0
for x in (dec if isinstance(dec, list) else []):
    for k in ("action", "decision", "status", "summary"):
        v = x.get(k)
        if isinstance(v, str) and "還安聯300萬@4.2%+元大50萬@3.92%" in v:
            x[k] = v.replace("還安聯300萬@4.2%+元大50萬@3.92%", "全數優先清償 500萬高息負債（保單400萬@4%＋券商100萬@3.92%）")
            n += 1
DEC.write_text(json.dumps(dec, ensure_ascii=False, indent=1), encoding="utf-8")

# 2) snapshot.fed_hike_monitor_0901
s = json.loads(SNAP.read_text(encoding="utf-8"))
m = s.get("fed_hike_monitor_0901", {})
hit = 0
for row in (m.get("對應配置") or []):
    if isinstance(row, str) and "質押 350萬@2.77%" in row:
        i = m["對應配置"].index(row)
        m["對應配置"][i] = ("借款：國泰質押 540萬@2.77% 已核定（未撥款，~9/25）→ 全數清償 500萬高息負債；"
                            "升息前鎖低利 = 未來利差擴大")
        hit += 1
SNAP.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")

print(f"dashboard_decisions 修正 {n} 處｜snapshot.fed_hike_monitor 修正 {hit} 處")
print("殘留檢查：", [r for r in (m.get('對應配置') or []) if '350萬@2.77%' in str(r)])
