#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIO-Gemini 18:00 戰略審計復盤 2026-08-26 → Notion ops_logs 同步寫入（週五復盤底稿）"""
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

SUMMARY = """【龍九控股 18:00 戰略審計與決策復盤 2026-08-26 週三】
Part A 決策實相：✅已核准22筆（7/31-8/22累積，今日無新增核准入檔）。最後核准：8/22 20:14「8/24 保單轉換定案 v2」300萬（PIMCO 120+M&G 100+健康科學A2 50+黃金A10 30）。⚠️今日 14:43 git 出現 decide commit「8/26 保單轉換80萬（M&G→黃金A10 32萬+健康A2 48萬）」已執行，但 dashboard_decisions.json 核准清單未同步入檔（僅加 2 筆 auto 日報）——決策雙軌不同步實錘。⏸️延後0筆正式；實質凍結：科技-2pp再平衡（13.8%紅線下）、00878防守承接（配息合併69.5%）、00983D暫緩、四核架構黃金衛星擱置。⏳Pending 5筆：洲際W轉貸（9/25評估中）、聯博AD美元月配（執行中）、質押富達350萬@2.77%還安聯300+元大50（待PI認證9/3前）、科技-2pp（凍結）、避險衛星131萬（待PI認證9/3前）。營運實相（8/26 15:00穿透）：總資產26,134,323；台股1,940,015(7.4%低於10%目標)、美股11,301,845(43.2%超40%目標)、防守1,015,594(3.9%單獨口徑)、債券6,065,572(23.2%)、現金5,811,297(22.2%)；日報：證券2,868,000 保單9,682,433 配息109,645（多次修正後）。US30Y 5.23%（8/24更新）模式A防禦警戒區5.20-5.30，距5.30凍結紅線0.07pp；macro_regime🟡黃燈；台股+1.47%收45,832。
Part B CIO 對策反抗：
1.質疑盲點：🚨核准標的vs執行標的偏離：8/22核准「貝萊德世界健康科學A2（醫療累積型不配息）」，8/26 fix commit「健康A10非A2，8/26 80萬+8/24 25萬」——A10為月配級別，等於醫療「累積型」設計被改成月配執行，且未以「變更核准」入檔；配息資產合併69.5%已紅線，健康A10月配再推高配息曝險，與「停止新增月配」原則衝突；🚨8/26保單轉換80萬決策已執行但決策檔無核准記錄，核准/執行/登錄三軌脫節（8/24審計已示警「核准流vs執行閘門」問題，本週未改善且惡化）；🚨決策日誌雜訊爆炸：8/26單日 auto 日報+穿透重複執行 86+86 筆（02:27-15:00），疑 cron 重入/無鎖，訊噪比惡化至極，且若管線含交易執行環節有重複下單風險；🚨配息數據當日多次修正（97,233→109,645→135,552→還原重複計入），安聯62,969重複計入問題顯示配息基準治理脆弱；🚨美股43.2%+美元曝險64%（超50%紅線）+席勒PE 41.96 三高並存，40%目標複核未完成；🚨總資產15.9M→26.1M 主要為8/23基金真值入庫後保單底層穿透計入口徑變更，跨期比較易失真。
2.提醒：🔴9/3 PI認證為全鏈臨界路徑（質押還債350萬+避險衛星131萬），8/31設檢查點；9/3未過啟動替代路徑（現金581萬已足，直接還安聯300萬@4.2%鎖利差）；🟡8/31確認國泰1,200萬書面進度+安聯B贖回100萬補現金；🟡US30Y每日盯FRED DGS30（5.30凍結紅線，現距0.07pp）；🟡科技-2pp解凍條件=配息合併口徑回落或科技重回紅線上；🟡9/25洲際W轉貸評估前，9/1前完成國泰VIP/轉貸條件覆核；🟢美股43.2%逢彈減≤20萬/次達標即停；🟢台股7.4%缺口採「慢慢買」補（週額度≤5萬）。
3.隱性風險：🚨決策登錄斷鏈：git decide commit（8/26保單轉換80萬）未同步 dashboard_decisions.json 核准清單，週五復盤將缺今日關鍵決策，建議 establish 單一決策寫入閘門（decide commit 自動附帶核准入檔）；🚨執行標的偏離（A2→A10）未經重新核准即執行，若 A10 配息率與 A2 累積假設不同，醫療曝險與配息口徑同步失真，需於 9 月配息實收後驗證；🚨86次重複執行疑無鎖重入，需查 cron 定義與 run_daily 互斥鎖，防止含交易環節時重複下單；🚨配息重複計入修正歷史顯示數值可信度分級機制（真值/暫估值）應入週報複檢清單；🚨黃金衛星（00635U 105萬+黃金A10 30萬+32萬）三重疊加曝險已超衛星上限5%概念，8/18「黃金≤3-5%非質押」與8/21「避險衛星≤7%」兩版本口徑未裁決合一，週五復盤前須合併裁決。"""

print(SUMMARY[:300])

BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {token}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
name = "CIO 戰略審計復盤 2026-08-26"

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
