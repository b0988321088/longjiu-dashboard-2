#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIO-Gemini 18:00 戰略審計復盤 2026-08-07 → Notion ops_logs 同步寫入（週五復盤底稿）"""
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

SUMMARY = """【龍九控股 18:00 戰略審計與決策復盤 2026-08-07 週五】
Part A 決策實相：
✅ 已核准累計 8 筆（7/31×3 + 8/4×5），今日(8/7)零新裁決。8/4 五筆：①剩400萬改買市值型(0050/006208/009816,每週≤50萬,原00919轉向) ②00983D下單10張@10.09(約100,900元,方案B慢補恢復) ③資產架構調整指示卡8/4最終版(凍結市值大額單/美股收斂30%/台股單筆≤5萬/優先序現金>防守>台股) ④ETF擁擠交易風險控管(4監控指標) ⑤FL65摩根多重收益分類定案(防守型100%)。
⏸️/⏳ Pending 5 筆：00983D方案B(✅8/4已執行10,000單位@10.12=101,200元)、洲際W轉貸(⏳10/1評估)、築巢優利貸2.185%(⏳10/1生效,第一階段關鍵)、信貸套利(⏸️第二階段待第一階段完成)、剩400萬市值型(🔄執行中每週≤50萬)。延後欄位0筆。
資產實況(週報8/7)：總資產16,842,905(+921,520,+5.8%)；台股市值型9.2% vs 目標22-25%(🔴缺-12.8~-15.8pp)、美股38.3%超標+8.3pp、債券17.7%超標、防守18.2%✅、現金16.6%✅；US30Y仍為8/4舊讀數5.27%<5.30%紅線。

Part B CIO 對策反抗：
1.質疑盲點: 🚨「剩400萬市值型每週≤50萬」8/4核准至今(8/7)零執行紀錄，但證券+143,980含「台股回補」——要嘛靜默執行未登錄、要嘛決策空轉，二擇一皆須追查；若8/10下週才首筆，本週缺口未補。🚨8/4同日「400萬市值型週購」vs「凍結市值大額單+台股單筆≤5萬」矛盾仍懸而未決：50萬週購拆分後單筆是否仍>5萬上限？孰者優先從未裁決(8/5已點名)。🚨00983D成交價兩處紀錄不一致(@10.09 vs @10.12)至今未修正；核准稱「國泰核貸暫緩解除」但週報8/7仍列「國泰核貸追蹤」——解除觸發器無正式紀錄，7/31凍結令(大額調度延後)效力狀態不明。
2.提醒: 🔴國泰核貸原訂8/4撥款未確認→9/25洲際W轉貸評估與10/1築巢優利貸生效的時程鏈需重新定錨，核貸每拖一週即壓縮築巢文件/對保窗口(8月中須啟動)。🔴US30Y監控停滯於8/4舊讀數5.27%，觀察期解除條件「連3日<5.20%」從未被每日驗證(8/3、8/5兩度點名仍未修)。🟠美股38.3%超標，收斂減碼(009824/美股科技)0執行紀錄，外資8/7賣超422億背景下建議下週逢反彈執行第一筆並登錄。🟡pending全無remind_at自動提醒(三度點名)；8/9週日19:00模式B動態週報將自動產出，本次審計應納入其底稿。
3.隱性風險: 🚨數據源校準仍未確認：8/5點名±50萬級跳動(美股5分鐘-498,978/現金±465,000/保單+174,594)後無修復驗證紀錄；今日穿透現金3,283,409 vs 週報3,289,381仍差~6,000。🚨高股息擁擠族群(00878/0056/00919)合計佔證券37.3%+ETF擁擠4指標已核准但無後續監控報告輸出。🚨外資連續賣超+大盤44,225高位震盪下，下週≤50萬市值型建倉若一次下滿，需守單筆≤5萬拆分紀律並留回檔分批空間。"""
print(SUMMARY[:600])

props = {
    "事件名稱": {"title": [{"text": {"content": "CIO 戰略審計復盤 2026-08-07"}}]},
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
print(f"[OK] Ops log written to Notion: CIO 戰略審計復盤 2026-08-07 (page {r.json().get('id')})")
