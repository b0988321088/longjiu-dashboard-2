#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIO-Gemini 18:00 戰略審計復盤 2026-08-05 → Notion ops_logs 同步寫入（週五復盤底稿）"""
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

SUMMARY = """【龍九控股 18:00 戰略審計與決策復盤 2026-08-05 週三】
Part A 決策實相：
✅ 已核准 8 筆（7/31×3 + 8/4×5）。8/4 五筆：①剩400萬改買市值型(0050/006208/009816,每週≤50萬,原00919轉向) ②00983D下單10張@10.09(約100,900元,方案B慢補恢復,稱國泰核貸暫緩解除) ③資產架構調整指示卡8/4最終版(凍結市值大額單/美股收斂30%/台股單筆≤5萬/優先序現金>防守>台股,流動性觀察期解除條件=US30Y連3日<5.20%) ④ETF擁擠交易風險控管(4監控指標) ⑤FL65摩根多重收益分類定案(防守型100%)。
⏸️/⏳ Pending 5 筆：00983D方案B(✅8/4已執行10,000單位@10.12)、國泰轉貸第一階段(⏳9/25到期)、築巢優利貸2.185%(⏳10/1生效)、信貸套利(⏸️第二階段待第一階段完成)、剩400萬市值型(🔄執行中每週≤50萬)。
今日(8/5)無新裁決——但為大漲日(台股+2.88%/外資買超903億/費半+6.55%)，回補訊號觸發卻零決策紀錄。

Part B CIO 對策反抗：
1.質疑盲點: 🚨00983D買入的解除前提未驗證——核准摘要稱「國泰核貸暫緩解除」，但8/5快照仍標註「核貸進行中」(原訂8/4撥款、利率2.6%)，7/31凍結令(大額調度延後)技術上仍有效；解除觸發器從未被正式紀錄。🚨8/4同日上午核准「400萬市值型週購」、下午卡片卻「凍結市值大額單」，兩決策互相矛盾且未裁決孰者優先；每週≤50萬是否屬「大額」未定義。🚨台股8/5單日+346,800(1,522,144→1,868,944,+22.8%)遠超2.88%漲幅應有之+43,800，無任何下單決策紀錄——真實買單未登錄 or 資料錯位，二擇一皆須追查。
2.提醒: 🔴國泰撥款8/4未如期確認，轉貸時程須重新定錨(9/25到期線重算)；🔴US30Y監控自8/1後無新讀數(streak=1@5.21%)，觀察期解除條件「連3日<5.20%」從未被監控驗證；🟠築巢10/1生效，8月中啟動文件/對保；🟠美股34.2%>30%目標，收斂計畫0賣單執行，Burry警告1987式崩盤下不宜再拖；🟡信貸套利10/15前避免聯徵查詢；pending全無remind_at自動提醒(8/3已點名仍未修)。
3.隱性風險: 🚨美股15:17→15:22五分鐘內-498,978、現金±465,000擺盪、保單+174,594異常跳增——穿透數據源仍未校準(8/3已點名±50萬級跳動,未修復)；🚨00983D成交價兩處紀錄不一致(@10.09 vs @10.12)；🚨大漲日無決策=回補訊號(外資買超+大盤+1%+費半+3%三條件全中)被靜默忽略或靜默執行，戰術表與核准軌跡脫節。"""
print(SUMMARY[:600])

props = {
    "事件名稱": {"title": [{"text": {"content": "CIO 戰略審計復盤 2026-08-05"}}]},
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
print(f"[OK] Ops log written to Notion: CIO 戰略審計復盤 2026-08-05 (page {r.json().get('id')})")
