#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIO-Gemini 18:00 戰略審計復盤 2026-08-12 → Notion ops_logs 同步寫入（週五復盤底稿）"""
import os, json, requests
from pathlib import Path

REPO = Path(r"C:/Users/bot/Desktop/longjiu_system")

# 1) token: hermes env (project .env 只有 MEM0)
token = os.environ.get("NOTION_TOKEN", "")
if not token:
    hermes_env = Path.home() / "AppData" / "Local" / "hermes" / ".env"
    if hermes_env.exists():
        for line in hermes_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("NOTION_TOKEN="):
                token = line.split("=", 1)[1].strip()
                break
if not token:
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("NOTION_TOKEN="):
            token = line.split("=", 1)[1].strip()
            break

db_ids = json.loads((REPO / "notion_db_ids.json").read_text(encoding="utf-8"))
db_id = db_ids.get("ops_logs", "")

if not token or not db_id:
    print("FATAL: no token or db_id")
    raise SystemExit(1)

SUMMARY = """【龍九控股 18:00 戰略審計與決策復盤 2026-08-12 週三】
Part A 決策實相：今日核准 2 筆（Laing）：①14:49「兩層槓桿策略修正版」：第一層1,200萬轉貸強制（撥款未入帳禁止任何換匯/建債/質押→償還800萬高息舊債→現金緩衝≥6個月第一層利息→剩餘分批換匯建美元直債到期梯持有到期）；第二層債券質押降為選擇性，4門檻全過才執行（US30Y<5.30%＋壓力測試LTV≤50%＋觀察1-3交易日＋雙層成本<債券殖利率），初始LTV≤50%不打滿，US30Y≥5.30%全域凍結新增質押，禁一周內建債+質押+再投資全套。②17:27「影片對照底線規則落實」：現金≥85萬實線(6個月生活費非僅利息)、被動實收連續2月<常態80%停建債、直債僅美債+投資級(BBB-以上)、單一發行人≤20%。累計核准10筆(7/31×3+8/4×5+8/12×2)。⏸️延後0筆正式；動態延後：債券質押5成改為階段2選擇性(8/12改版)。⏳Pending 5筆：00983D方案B✅已執行、8/15國泰撥款部署🔄執行中、洲際W轉貸🔄評估中(9/25)、築巢優利貸❌取消、債券質押⏸️選擇性。資產實況(8/12)：總投資14,264,173；台股11.0%(目標15%,-4.0pp)、美股41.9%(目標30%,+11.9pp超標)、防守21.8%、債券21.0%、現金4.3%(目標15%,-10.7pp)；安全網25.3%<目標35%；現金總額620,095<85萬實線；US30Y 5.25%(8/10更新,距凍結線5.30%僅0.05pp)；負債18,148,676。

Part B CIO 對策反抗：
1.質疑盲點：🚨現金實線當日即違規：17:27底線規則①現金≥85萬，但今日現金僅620,095(-23萬)，規則上線即踩線且無警示；且兩層槓桿裁決「緩衝≥6個月利息」與85萬(6個月生活費)定義不一致，同日兩裁決互相矛盾，須定錨。🚨1,200萬分配兩版本競合：8/4「800萬清償+400萬市值型(0050/006208/009816)」vs 8/12「800萬清償+現金緩衝+剩餘換匯建美元直債」——400萬市值型是否被8/12裁決廢止從未明說，8/15撥款前必須裁決。🚨第一層無成本門檻：第二層有「雙層成本<殖利率」，第一層強制執行卻無轉貸利率vs舊貸vs直債殖利率比較；若轉貸利率≥直債殖利率，剩餘建債套利空間為負。🚨US30Y監控斷層：us30y_state停在8/10(5.25%)，8/11-8/12零更新，而第二層門檻1與全域凍結線都依賴此數據，8/15前須恢復日更。
2.提醒：🔴8/14(週五)FL65基準日，配息導流00878/00713；🔴8/15(週六)國泰撥款——週六作業可行性需確認，若順延8/17(週一)，階段1時程全鏈連動；撥款前禁止換匯/建債/質押（裁決自帶）。🔴現金62萬<85萬實線：撥款前以優先序現金>防守>台股補足，勿等撥款。🟡9/25洲際W轉貸；質押4門檻逐日驗證，US30Y 5.25%距凍結線僅0.05pp，殖利率反彈即觸發全域凍結。
3.隱性風險：🚨美股41.9%超標+11.9pp，8/4核准「美股收斂30%」至今0筆減碼登錄，兩層槓桿啟動後資金全往債券，結構更失衡。🚨00983D成交價@10.09 vs @10.12不一致懸置未修(3度點名)。🚨負債18.1M>流動資產6.9M，兩層槓桿使負債再升，淨值緩衝需月驗。🚨「禁一周內全套」vs「階段1換匯建直債」時序重疊風險：階段2最早8/20(觀察1-3交易日)可啟動，須嚴格串行——800萬銷帳驗證＋現金緩衝到位才准開階段2。🚨直債集中度：單一發行人≤20%須納入穿透報告，與8/4 ETF擁擠控管同源。"""
print(SUMMARY[:600])

props = {
    "事件名稱": {"title": [{"text": {"content": "CIO 戰略審計復盤 2026-08-12"}}]},
    "來源系統": {"select": {"name": "Hermes"}},
    "執行狀態": {"select": {"name": "完成"}},
    "事件分類": {"select": {"name": "審計"}},
    "CIO摘要": {"rich_text": [{"text": {"content": SUMMARY[:2000]}}]},
}
props["關聯頁面"] = {"url": "https://hermes-agent.nousresearch.com/dashboard_decisions.json"}

payload = {"parent": {"database_id": db_id}, "properties": props}
headers = {
    "Authorization": f"Bearer {token}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
r = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload, timeout=60)
if r.status_code >= 400:
    print(f"[ERROR] Notion ops_log write failed: {r.status_code}: {r.text[:300]}")
    raise SystemExit(2)
print(f"[OK] Ops log written to Notion: CIO 戰略審計復盤 2026-08-12 (page {r.json().get('id')})")
