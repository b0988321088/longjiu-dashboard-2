#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIO-Gemini 18:00 戰略審計復盤 2026-08-24 → Notion ops_logs 同步寫入（週五復盤底稿）"""
import os, json, requests
from pathlib import Path

REPO = Path(r"C:/Users/bot/Desktop/longjiu_system")

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

SUMMARY = """【龍九控股 18:00 戰略審計與決策復盤 2026-08-24 週一】
Part A 決策實相：✅核准22筆（7/31-8/22累積），今日關鍵2筆：①8/22 20:14核准「8/24 保單轉換定案 v2」300萬（PIMCO 120+M&G 100+貝萊德世界健康科學A2 50醫療累積型+貝萊德世界黃金A10 30黃金月配特例；8/22實測申請84.5萬被擋待8/24重試；T+4截止）②8/23 04:35核准「基金真值與入口整理」（聯博前10持股NVDA2.31等/安聯前5行業資訊技術13.48/PIMCO前10 NVDA2.1+台積電1.7；穿透科技18.2%；儀表板9報表+2圖表）。⏸️延後0筆正式；實質凍結：科技-2pp再平衡（核准清單標「已核准待執行」vs pending標⏸️凍結，配息資產合併69.7%紅線）、00878防守承接凍結、石油衛星凍結（COT撤離-175.6%）。⏳Pending 5筆：洲際W轉貸（9/25評估中）、聯博AD美元月配分批加碼（執行中觀察穿透）、質押富達350萬@2.77%還安聯300+元大50（待PI認證9/3前→銀行書面）、科技-2pp（凍結）、避險衛星131萬（待PI後撥MMF）。營運實相（8/24 17:27穿透）：總資產26,194,822；台股1,881,461(7.2%)、美股11,284,555(43.1%超40%目標+3.1pp)、防守1,098,782(4.2%)、債券6,100,988(23.3%)、現金5,816,935(22.2%)；US30Y 5.276%（距5.30%凍結紅線僅0.024pp）；macro_regime黃燈，美元信用壓力情境74.2最高分、科技重新定價57.6、確定收益輪動49.8、地緣43.8；席勒PE 41.96；黃金4,696.6美元20日+15.5%；美元曝險64%超紅線50%；現金底線817,539≥70萬✅；乾粉100,272。
Part B CIO 對策反抗：
1.質疑盲點：🚨8/24轉換300萬若以科技基金為來源，等效於「凍結中的科技-2pp」以保單內部互轉名義繞閘執行——科技已13.7-14.3%（紅線30%下），核准軌跡卻無資金來源標註；🚨黃金月配30萬特例違反8/21「累積型優先、停止新增月配」原則且無量化豁免條件，加計00635U黃金105萬=135萬已超衛星上限131萬(5%)；🚨醫療集中雙路徑：保單健康科學50萬+交易計畫醫療40%，醫療曝險快速上升且8/22實測申請曾被擋，執行不確定性未解除；🚨核准/凍結/pending三軌並存：科技-2pp金額三版本（核准101.8萬/DAA建議52.4萬/凍結13.8%紅線下）未裁決；🚨基金真值為落後持股（半年報級），NVDA2.31等單時點數據支撐穿透18.2%有失真風險；🚨美元曝險64%紅線下，8/24轉換仍多為美元計價標的，曝險不降反升。
2.提醒：🔴9/3 PI認證為全鏈臨界路徑（質押還債350萬+黃金衛星131萬），8/25設檢查點；9/3未過啟動替代路徑（現金581萬已足，直接還安聯300萬@4.2%鎖利差）；🟡8/31安聯B贖回100萬補現金、9月中富達/聯博首配息更新配息基準；🟡US30Y 5.276%距紅線0.024pp，每日盯FRED DGS30，突破即債券凍結；🟡科技-2pp解凍條件=配息合併口徑回落或科技重回紅線上；🟡洲際W轉貸9/25前，8/31確認國泰1,200萬書面進度；🟢美股43.1%逢彈減≤20萬/次達標即停。
3.隱性風險：🚨決策治理：核准流vs執行閘門雙軌脫節（核准即擱置）持續第三週，8/21審計已示警未改善，建議核准自動帶gate清單；🚨pending_decisions.json與dashboard_decisions.json雙檔不同步（石油凍結未更新、金額三版本），週五復盤前需合併裁決；🚨黃金20日+15.5%追高風險+月配特例疊加，衛星建倉須嚴守逢回檔分3批50/30/20；🚨決策日誌雜訊：759筆中單日auto日報重複40+筆，復盤底稿訊噪比惡化，建議auto記憶合併壓縮；⚠️席勒PE 41.96歷史極端+美股43.1%超標+美元曝險64%，三高並存，40%美股目標宜複核。"""

print(SUMMARY[:400])

BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {token}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
name = "CIO 戰略審計復盤 2026-08-24"

# 去重：查詢同名事件
q = requests.post(f"{BASE}/databases/{db_id}/query", headers=HEADERS,
                  json={"filter": {"property": "事件名稱", "title": {"equals": name}}}, timeout=60)
q.raise_for_status()
existing = q.json().get("results", [])

props = {
    "事件名稱": {"title": [{"text": {"content": name}}]},
    "來源系統": {"select": {"name": "Hermes"}},
    "執行狀態": {"select": {"name": "完成"}},
    "事件分類": {"select": {"name": "審計"}},
    "CIO摘要": {"rich_text": [{"text": {"content": SUMMARY[:2000]}}]},
}
props["關聯頁面"] = {"url": "https://hermes-agent.nousresearch.com/dashboard_decisions.json"}

if existing:
    pid = existing[0]["id"]
    r = requests.patch(f"{BASE}/pages/{pid}", headers=HEADERS, json={"properties": props}, timeout=60)
    mode = "PATCH(update)"
else:
    r = requests.post(f"{BASE}/pages", headers=HEADERS,
                      json={"parent": {"database_id": db_id}, "properties": props}, timeout=60)
    mode = "POST(new)"
if r.status_code >= 400:
    print(f"[ERROR] Notion ops_log write failed: {r.status_code}: {r.text[:300]}")
    raise SystemExit(2)
print(f"[OK] Ops log {mode} written to Notion: {name} (page {r.json().get('id')})")
