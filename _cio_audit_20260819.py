#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIO-Gemini 18:00 戰略審計復盤 2026-08-19 → Notion ops_logs 同步寫入（週五復盤底稿）"""
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

SUMMARY = """【龍九控股 18:00 戰略審計與決策復盤 2026-08-19 週三】
Part A 決策實相：今日 0 筆新核准（最近 8/18×3：安聯保單借貸300萬@4.2%最優先、國泰VIP最低資格+還債順序①安聯300②元大證金100③第一金3.51%暫緩④其餘4%+高息、四核架構現金/黃金擱置）。⏸️延後 0 筆正式；實質延後：黃金衛星≤5%暫不執行、第一金還款暫緩、400萬市值型部署未執行、美股收斂30%減碼無登錄。⏳Pending 6 筆：①00983D方案B ✅已執行(8/4) ②8/15國泰撥款部署 📌紀錄停留8/10版(1,200萬→還理財型200萬→1,000萬買債→質押500萬→還高息700萬)，與8/12/8/18裁決競合未整合 ③洲際W轉貸 🔄9/25評估 ④築巢優利貸 ❌取消(10/1) ⑤債券質押5成 📌待執行 ⑥核貸後還債順序+VIP 🔄等撥款入帳。營運實況(8/19穿透)：總資產14,455,660；台股1,921,554(13.3%,目標23.5%)、美股5,159,332(35.7%,目標30%,+5.7pp超標)、防守3,080,245(21.3%)、債券3,475,105(24.0%)、現金819,424(5.7%)；負債18,148,676未動、淨值-3,693,016、配息66,725≈7/31之51%。🚨US30Y 5.31%（us30y_state last_date 8/17、模式A streak 5）連續第二日站上5.30%凍結線，8/18系統燈號已切全域凍結。市場：費半8/18 -4.98%近期最大單日跌幅、台股8/19 -1.61%連二跌、台積電2,345。
Part B CIO 對策反抗：
1.質疑盲點：🚨撥款狀態三系統矛盾——8/16週報與8/18/8/19緊急報告稱「8/15已撥款✅」，dashboard pending卻「等撥款入帳」、snapshot cathay_refinance_amount=null、負債18.1M未動、Moneybook同步停在8/10；若已撥款現金不可能仍低於底線，若未撥款則週報✅為誤報，兩者必有一假，8/12階段1禁令是否解除無從判定。🚨pending「債券質押5成」仍標待執行，但US30Y 5.31%已觸發凍結，8/12四門檻之門檻1(US30Y<5.30%)失效，8/10版部署與現行裁決競合未裁決。🚨目標版次混亂：債券目標30%(8/17)vs13%(8/19)、現金底線85萬(8/12核准)vs70萬(週報/8/14下修無核准)vs85.2萬(8/19緊急報告)，同資產多版本並存。🚨現金819,424僅覆蓋5.8個月生活費(141,958×6=851,748)，實線失守約3.2萬。⚠️美股35.7%超標+費半-4.98%重挫為波動主源，收斂核准無執行登錄。⚠️台股-10.2pp低配vs 4萬6高位，400萬部署計畫設定於4萬點，追高vs低配兩難，幸8/19大跌緩解追高壓力。
2.提醒：🔴撥款入帳確認為第一優先——入帳當日執行①還債順序(安聯300→元大100→其餘4%+)②銷帳驗證③現金緩衝定錨(70萬vs85.2萬)；若8/23前未入帳須追蹤國泰並修正週報誤報。🟡US30Y每交易日更新(已停8/17)，觀察位5.20%防禦/5.30%解凍。🟡美股反彈日分批減碼登錄。🟢00983D(已執行)與築巢(取消)建議移出pending結案，僅留4筆有效。🟡洲際W 9/25待8月部署後評估。🟡四核/黃金待撥款+500-500-200配置後依LTV再評估。
3.隱性風險：🚨決策治理：底線/目標/撥款狀態多版本衝突未進dashboard核准流，週五復盤前須整併「規則單一事實版本」。🚨流動性：現金5.7%+負債18.1M+配息腰斬，撥款再延則實線持續失守且現金重建無源。🚨利率：US30Y續漲則債券24%淨值續壓+美股估值雙殺，凍結紀律已啟動不得新增。⚠️今夜費半若續跌-3%觸發「只減不加」，8/4禁追漲/ETF擁擠控管受考驗。⚠️匯率：台幣強升美股台幣價值虛胖，但換匯建美元債成本下降為利好窗口。⚠️系統：自動化產線間缺撥款狀態校驗，建議加gate防誤導輸出。"""
print(SUMMARY[:600])

props = {
    "事件名稱": {"title": [{"text": {"content": "CIO 戰略審計復盤 2026-08-19"}}]},
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
print(f"[OK] Ops log written to Notion: CIO 戰略審計復盤 2026-08-19 (page {r.json().get('id')})")
