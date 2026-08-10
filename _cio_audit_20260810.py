#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIO-Gemini 18:00 戰略審計復盤 2026-08-10 → Notion ops_logs 同步寫入（週五復盤底稿）"""
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

SUMMARY = """【龍九控股 18:00 戰略審計與決策復盤 2026-08-10 週一】
Part A 決策實相：
✅ 已核准累計 8 筆（7/31×3 + 8/4×5），今日(8/10)零新裁決。8/4 五筆：①剩400萬改買市值型(0050/006208/009816,每週≤50萬) ②00983D下單10張@10.09(方案B慢補恢復) ③資產架構調整指示卡8/4最終版(凍結市值大額單/美股收斂30%/台股單筆≤5萬/優先序現金>防守>台股) ④ETF擁擠交易風險控管(4監控指標) ⑤FL65摩根多重收益分類定案(防守型配息100%)。
⏸️ 延後 0 筆（正式延後欄位；動態延後見 pending：築巢優利貸❌取消改國泰第二間轉貸、洲際W轉貸評估中）。
⏳ Pending 5 筆：00983D方案B(✅8/4已執行10,000單位@10.12=101,200元)、洲際W轉貸(9/25評估中,直接跟國泰辦理)、築巢優利貸2.185%(❌10/1取消)、信貸套利(🔵提前:8/15國泰撥款後先辦兆豐信貸300萬)、剩400萬市值型(🔄執行中每週≤50萬)。
資產實況(8/10)：總資產16,927,488；台股9.3% vs 目標15%(🔴-5.7pp,缺口約96萬)、美股35.1%(+5.1pp超標)、防守18.5%、債券17.6%(vs臨時目標12-14%超標)、現金19.4%(+4.4pp)；US30Y 5.21%警戒區(8/9週報,<5.30%凍結線)。

Part B CIO 對策反抗：
1.質疑盲點: 🚨8/15國泰撥款1,200萬配置出現兩版本矛盾——8/4版「800萬清償+剩400萬市值型」恰等於1,200萬；8/9週報版「800萬清償+先買500萬債券」超支100萬且排擠400萬市值型，500萬債券資金來源(兆豐信貸300+現金200?)從未裁決，8/15當天恐卡關。🚨債券已超標(17.6% vs 臨時目標12-14%)卻再規劃+500萬債券→估升至20.5%，等於未經重新核准的目標框架漂移，須明訂「短債1-3yr收息套利」vs「債券佔比目標」孰者優先。🚨8/7台股穿透1,868,944(較前值+31萬)後8/10回落1,577,309，美股反向-32萬/+30萬，±30萬級跳動再現，數據源校準仍未確認(8/5、8/7兩度點名未修)。🚨台股目標雙軌未統一：巴菲特模型15% vs 週報臨時目標22-25%；400萬全數投入僅約+2.4pp至11.7%，連15%都未達，建倉前須先定錨單一目標。🚨00983D成交價兩處紀錄不一致(@10.09核准 vs @10.12 pending)至今未修正。
2.提醒: 🔴8/14(週三)FL65基準日，配息接力導流00878/00713。🔴8/15國泰撥款1,200萬→①清償800萬高息債(年省11.1萬)②債券500萬③後續再評估；注意8/15為週六，銀行撥款+兆豐信貸300萬作業可行性需確認，若順延8/17(週一)，市值型400萬起跑與債券500萬時程全鏈連動延後。🔴US30Y 5.21%距5.20%解除線僅0.01pp，「連3日<5.20%」每日驗證機制仍缺(4度點名)，一旦跌破即開放市值大額進場。🟡9/25洲際W轉貸評估、10/15信貸套利待辦；pending全無remind_at自動提醒(4度點名)。
3.隱性風險: 🚨dashboard決策軌跡8/8-8/9兩日零紀錄(檔案斷層)，週末管線中斷或未寫入，週五復盤底稿資料不連續。🚨美股35.1%超標+5.1pp，收斂減碼0登錄；US30Y警戒區已自動停購但減碼執行紀錄仍缺。🚨ETF擁擠4指標監控8/4核准後無後續報告輸出。🚨8/15後台股市值型建倉8週×每週≤50萬、單筆≤5萬、回檔小單——若一次下滿違反8/4指示卡紀律。"""
print(SUMMARY[:600])

props = {
    "事件名稱": {"title": [{"text": {"content": "CIO 戰略審計復盤 2026-08-10"}}]},
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
print(f"[OK] Ops log written to Notion: CIO 戰略審計復盤 2026-08-10 (page {r.json().get('id')})")
