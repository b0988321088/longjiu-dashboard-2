#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIO-Gemini 18:00 戰略審計復盤 2026-08-14 → Notion ops_logs 同步寫入（週五復盤底稿）"""
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

SUMMARY = """【龍九控股 18:00 戰略審計與決策復盤 2026-08-14 週五】
Part A 決策實相：今日核准 0 筆（08-13/08-14 無新決策，最近核准為 8/12 兩筆，累計 10 筆：7/31×3+8/4×5+8/12×2）。⏸️延後 0 筆正式（deferred_alerts 僅存 7/19 測試性延後已失效）；動態延後：債券質押5成由 8/10 定案必做降為 8/12 裁決階段2選擇性。⏳Pending 5 筆：①00983D方案B ✅已執行(8/4 10,000單位@10.12) ②8/15國泰撥款部署 📌明日到期但紀錄停留8/10版本（1,200萬→還理財型200萬→1,000萬買債→質押5成500萬→還高息700萬），與8/12裁決競合未裁決 ③洲際W轉貸 🔄評估中(9/25) ④築巢優利貸 ❌取消 ⑤債券質押5成(PI 2.88%)→還高息 📌待執行但須過8/12四門檻。資產實況(8/14穿透)：總投資14,517,659；台股1,947,494(13.4%,目標15%)、美股5,613,257(38.7%,目標30%,+8.7pp超標)、防守3,120,352(21.5%)、債券3,047,430(21.0%)、現金789,126(5.4%,目標15%,-9.6pp)；現金<85萬實線差60,874，連續第3日違規。US30Y 5.24%停於8/12，距凍結線5.30%僅0.06pp，8/13-8/14無新數據。市場：台股46,053突破4萬6、外資暴買756億、台幣強升破32(31.99)、CPI 3.5%降溫、美元指數承壓。

Part B CIO 對策反抗：
1.質疑盲點：🚨8/15撥款在即，1,200萬部署三版本競合（8/4「800萬清償+400萬市值型0050/006208/009816」vs 8/10「1,000萬買債+質押500萬+還高息700萬」vs 8/12「800萬清償+現金緩衝≥6個月利息+剩餘換匯美元直債到期梯、第二層選擇性」），pending_decisions.json仍停留8/10版未同步8/12裁決——儀表板顯示的「定案」實為過期規則，執行者無所適從，8/12審計點名後48小時仍未裁決。🚨現金789,126<85萬實線(差60,874)連3日違規；8/12底線規則②「被動實收連續2月<常態80%停建債」：今日配息66,457僅為7/31(130,930)的51%，若為結構性縮水，8/15建債計畫直接觸發停建。🚨US30Y數據凍結：last_rate 5.24%停在8/12，8/13-8/14零更新，而階段2門檻1與全域凍結線全依賴此數據——凍結線可能已觸發而系統不知情。🚨美股38.7%超標+8.7pp，8/4核准「美股收斂30%」至今0筆減碼登錄（8/12點名後仍無動作），兩層槓桿資金全往債券，股權結構失衡續惡化。
2.提醒：🔴8/15(明日週六)國泰撥款：週六作業可行性至今無確認決策，若無法作業須立即順延8/17(週一)並連動校準全鏈時程；撥款當日三件事——①裁決方案競合定錨 ②800萬高息銷帳驗證 ③現金緩衝基準定錨(85萬生活費vs 6個月利息定義衝突)。🔴撥款未入帳前禁止任何換匯/建債/質押（8/12裁決自帶）。🟡9/25洲際W轉貸：8/15執行後視現金流重啟評估。🟡8/4「剩400萬改買市值型」是否被8/12裁決廢止，需白紙黑字裁決。🟢築巢優利貸已取消無需檢視。
3.隱性風險：🚨決策治理風險：同一1,200萬部署8天內三版(8/4→8/10→8/12)，紀錄未同步，決策軌跡與現行規則脫節。🚨匯率雙向風險：台幣強升31.99+美元資產5.6M——已持美元資產台幣價值虛胖，直債到期換回台幣恐遭匯損侵蝕；但此刻換匯建美元直債成本下降，屬利好窗口，須分批鎖價。🚨配息腰斬風險：66,457 vs 7/31 130,930(-49%)，須確認季節性vs結構性。🚨外資暴買756億、指數破4萬6，市場轉熱考驗8/4「禁追漲大額/ETF擁擠控管」紀律，台股13.4%回補壓力vs追高風險。🚨負債18.1M+兩層槓桿啟動，8/15撥款入帳當日資產負債表瞬時膨脹，須當日快照留存驗證。"""
print(SUMMARY[:600])

props = {
    "事件名稱": {"title": [{"text": {"content": "CIO 戰略審計復盤 2026-08-14"}}]},
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
print(f"[OK] Ops log written to Notion: CIO 戰略審計復盤 2026-08-14 (page {r.json().get('id')})")
