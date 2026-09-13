# -*- coding: utf-8 -*-
"""資料層殘留校正：把「9/9 版 350萬@2.8%」狀態更新為 9/11 核定 + 9/12 裁示（2026-09-13）

這些是「資料」不是腳本，但儀表板/日報直接渲染 → 看起來就像貼死的舊文字。
以 2026-09-12 使用者裁示為準：
  540萬@2.77%（9/11 僅額度核定、未撥款；對保後約 2 週撥款 ~9/25）
  用途＝全數優先清償 500萬高息負債（保單400萬@4%＋券商100萬@3.92%）
  10月標案押標金不預留（9月底評估）
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
PEND = BASE / "pending_decisions.json"

NEW = ("540萬@2.77%（9/11 僅完成額度核定、未撥款；對保後約 2 週撥款 ~9/25）"
       "→ 全數優先清償 500萬高息負債（保單質押 400萬@4%＋券商質押 100萬@3.92%）"
       "；10月標案押標金 240萬 不預留（9月底評估）")

# ── snapshot ──
s = json.loads(SNAP.read_text(encoding="utf-8"))
changes = []

cd = s.get("cathay_disbursement", {})
if cd:
    old = cd.get("status", "")
    cd["status"] = ("✅ 8/20-8/23 部署完成（富達600萬＋聯博100萬＋MMF）→ PI 核定 → "
                    f"國泰質押 {NEW}")
    if old != cd["status"]:
        changes.append("cathay_disbursement.status")
    old2 = cd.get("execute_chain", "")
    cd["execute_chain"] = (old2.split("→ PI")[0] + "→ PI 核定（9/8）→ 質押核定 9/11 → "
                           f"{NEW}")
    changes.append("cathay_disbursement.execute_chain")

op = s.get("operation_performance", {})
for tp in (op.get("追蹤點") or []):
    if "PI 認列" in str(tp.get("項目", "")):
        tp["項目"] = f"質押撥款（~9/25）→ 清償 500萬高息負債（月息 16,600 → 12,465）→ 淨資產/覆蓋率跳升"
        changes.append("operation_performance.追蹤點[PI認列]")

if "policy_pledge_loan_note" in s:
    s["policy_pledge_loan_note"] = s["policy_pledge_loan_note"].replace(
        "借款使命完成待 9/3 質押 350萬@2.77% 還掉", "借款使命完成，2026-09-12 裁示以國泰質押 540萬@2.77% 撥款（~9/25）優先清償")
    changes.append("policy_pledge_loan_note")

SNAP.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")

# ── pending_decisions ──
pd = json.loads(PEND.read_text(encoding="utf-8"))
SUPERSEDED = ("⛔ 已被取代（9/11 核定 540萬@2.77%、9/12 裁示 500萬高息負債優先）— "
              f"現行口徑：{NEW}；本條保留為歷史紀錄")
n = 0
for x in (pd if isinstance(pd, list) else []):
    t = f"{x.get('title','')}{x.get('status','')}"
    if ("350萬@2.8%" in t or "350 line" in t or "700萬池" in t) and "9/12" not in str(x.get("date", "")):
        x["status"] = SUPERSEDED
        n += 1
PEND.write_text(json.dumps(pd, ensure_ascii=False, indent=1), encoding="utf-8")

print("snapshot 更新：", changes)
print(f"pending_decisions 標記取代：{n} 筆")
