#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIO-Gemini 18:00 戰略審計復盤 2026-08-21 → Notion ops_logs 同步寫入（週五復盤底稿）"""
import os, json, requests
from pathlib import Path

REPO = Path(r"C:/Users/bot/Desktop/longjiu_system")

# token: hermes env (project .env 只有 MEM0)
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

SUMMARY = """【龍九控股 18:00 戰略審計與決策復盤 2026-08-21 週五】
Part A 決策實相：✅核准3筆+定案1筆：①DAA v3動態再平衡引擎定案A版(macro_regime.py 4情境→燈號→建議金額，已上線GitHub Pages；驗證US30Y 5.24/VIX 16/黃金月+14.2%/席勒PE 42.15；SAA台10/美40/防20/債25/現金5+黃金衛星≤5%；同日完成紀錄重複登錄) ②科技-2pp再平衡(科技15.2%超紅線→減碼101.8萬=貝萊德科技A10 89.8萬轉PIMCO/M&G+鉅亨半導體12萬贖回→~11.3%；00878週額度≤5萬承接+2pp) ③避險衛星建倉(00635U黃金~105萬+00642U石油~26萬，台幣計價不增美元曝險，PI後分批執行) ④定案-基金原則：累積型優先、停止新增月配。⚙️執行3筆：買聯博全球多元收益AD美元月配100萬首筆(MMF贖回轉申購)、第一金保單FL65→FA81轉換當日生效(編號9900408867)、聯博100萬+MMF 500萬同步下單(T+2 8/23入帳→PI認證9/3前→質押350萬@2.77%還安聯300+元大50)。⏸️延後0筆正式；實質凍結：科技-2pp核准但pending標⏸️凍結(配息資產合併69.5%紅線)、00878防守承接凍結。⏳Pending 5筆：洲際W轉貸(9/25評估中)、聯博分批加碼(觀察穿透後再進)、質押富達350萬還債鏈(待PI認證→銀行書面)、科技-2pp(凍結)、避險衛星建倉(待PI後撥MMF~131萬)。營運(8/21穿透)：總資產26,204,672；台股1,889,388(7.2%)、美股11,044,993(42.1%,超40%目標)、防守3,028,732(11.6%)、債券3,429,177(13.1%)、現金6,812,382(26.0%)；現金較8/19(819,424)暴增約599萬，來源未登錄。
Part B CIO 對策反抗：
1.質疑盲點：🚨現金實線將失守——8/23 T+2扣款後現金6,812,382-600萬≈81.2萬<85萬實線(141,958×6=851,748)，且MMF 500萬為已承諾用途(質押350+衛星131=481萬)，實質自由現金僅~33萬；當日核准鏈未驗證現金底線即放行雙下單。🚨核准與凍結並存：13:58核准科技-2pp，pending同步標⏸️凍結——名義核准vs執行閘門脫節，「紙上核准」空轉決策。🚨金額口徑三版本打架：核准「減碼101.8萬」vs pending「DAA建議524,093(52.4萬)」vs凍結狀態「科技13.8%紅線下」(核准時15.2%超紅線)——執行恐超減/不足。🚨同日自相矛盾：16:29定案「停止新增月配級別」，同日09:53/13:41下單聯博AD月配100萬+13:27保單轉入FA81(月配級別)——新原則與當日執行衝突，未註明豁免範圍。🚨8/18 vs 8/21黃金矛盾：8/18核准「黃金衛星暫不執行，待撥款+500-500-200配置後」；8/21核准00635U黃金~105萬建倉——前置條件未驗證、無取代標註。🚨現金暴增599萬來源未登錄：若為國泰撥款，8/18還債順序(安聯300萬第一優先)應已執行卻未執行；若非撥款，來源不明。⚠️席勒PE 42.15歷史極端+美股42.1%超標，美股整體目標40%仍偏高。
2.提醒：🔴PI認證9/3為全鏈臨界路徑(質押還債350萬+避險衛星131萬+科技減碼)，建議8/25設檢查點；9/3未過啟動替代還債路徑(如用已到位現金還安聯300萬)。🟡8/23入帳後立即重算：自由現金<85萬則暫緩衛星建倉或縮MMF額度；配息合併69.5%紅線回落即解凍科技-2pp與00878承接。🟡洲際W轉貸9/25與PI相隔3週，8/31前確認國泰撥款狀態。🟡00983D方案B(8/4核准)進度無登錄，補登或結案。🟢DAA v3上線後首個週五，下週日19:00週報驗收引擎輸出與人工裁決一致性。
3.隱性風險：🚨決策治理：核准流與執行閘門(凍結紅線)雙軌並存未整合，「核准即擱置」侵蝕決策可信度；建議核准時自動帶gate清單(現金底線/合併配息紅線/PI前置)。🚨單點失效：PI認證為三案共同前置且無替代路徑，單點卡死全鏈。🚨流動性：自由現金~33萬為8月最薄，1,200萬撥款若再延則實線失守且現金重建無源。⚠️估值：席勒PE 42.15+科技/美股雙高，40%美股目標宜複核。⚠️保單轉換頻繁(FL65→FA81當日生效，同日又核准貝萊德科技A10轉出)，手續費/匯率摩擦成本未入決策軌跡。"""
print(SUMMARY[:600])

props = {
    "事件名稱": {"title": [{"text": {"content": "CIO 戰略審計復盤 2026-08-21"}}]},
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
print(f"[OK] Ops log written to Notion: CIO 戰略審計復盤 2026-08-21 (page {r.json().get('id')})")
