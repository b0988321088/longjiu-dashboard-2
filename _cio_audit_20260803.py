#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIO-Gemini 18:00 戰略審計復盤 → Notion ops_logs 同步寫入（週五復盤底稿）"""
import os, json, requests
from datetime import datetime
from pathlib import Path

REPO = Path(r"C:/Users/bot/Desktop/longjiu_system")

# 1) token: hermes env (project .env 只有 MEM0)
token = ""
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

SUMMARY = """【龍九控股 18:00 戰略審計與決策復盤 2026-08-03】
Part A 決策實相：
✅ 已核准 3 筆(皆 7/31)：①臨時調整規則-國泰核貸審查階段(大額調度全凍結,00878 4週建倉,00983D暫緩,單筆5萬以上暫停,現金底線6個月,US30Y≥5.30%債券凍結) ②動態自我檢討週報整合版驗收(週日19:00 cron) ③動態週報複檢清單整合驗收。
⏸️/⏳ Pending 4 筆：00983D方案B(8/4撥款後評估)、國泰轉貸第一階段(9/25到期)、築巢優利貸2.185%(10/1生效)、信貸套利第二階段(待第一階段完成)。
今日(8/3)無新裁決，僅自動化日報。

Part B CIO 對策反抗：
1.質疑盲點: 國泰凍結令缺「解凍觸發器」與撥款確認清單(8/4撥款就在明天)；單筆5萬硬上限無義務型支出例外(保單續繳9.58M最大資產可能誤傷)；US30Y≥5.30%紅線無監控歸屬；週報首產出8/2 19:10已確認✅但決策軌跡缺首次運行驗證紀錄。
2.提醒: 🔴8/4 00983D復評+撥款確認(全鏈單點)；🟠9/25轉貸第一階段(8月中啟動文件/對保)；🟠10/1築巢生效銜接；🟡信貸套利期間避免聯徵查詢；pending 全無 remind_at 自動提醒。
3.隱性風險: 🚨凍結期間台股+51.4萬(2,766,920→3,281,225)、美股-36.9萬、防守-9.3萬，±50萬級跳動需先驗數據源再談績效(凍結違規 or 數據不一致 or 匯率集中)；🚨決策日誌污染: 8/1數小時內30+筆重複紀錄、配息118,296→0震盪，消費JSON的統計會被污染；🚨單點失效鏈: 8/4→9/25→10/1→信貸套利全押明天撥款，無延誤應變方案。"""

props = {
    "事件名稱": {"title": [{"text": {"content": "CIO 戰略審計復盤 2026-08-03"}}]},
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
print(f"[OK] Ops log written to Notion: CIO 戰略審計復盤 2026-08-03 (page {r.json().get('id')})")
