#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIO-Gemini 18:00 戰略審計復盤 2026-08-17 → Notion ops_logs 同步寫入（週五復盤底稿）"""
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

SUMMARY = """【龍九控股 18:00 戰略審計與決策復盤 2026-08-17 週一】
Part A 決策實相：今日核准 0 筆（8/13-8/17 無新核准，累計 10 筆：7/31×3+8/4×5+8/12×2）。⏸️延後 0 筆正式；實質延後：8/10 定案「債券質押5成→還高息」被 8/12 裁決降為階段2選擇性（4門檻全過才執行）。⏳Pending 5 筆：①00983D方案B ✅已執行(8/4) ②8/15國泰撥款部署 📌紀錄停留8/10版(1,200萬→還理財型200萬→1,000萬買債→質押500萬→還高息700萬)，與8/12裁決(800萬清償→現金緩衝→美元直債到期梯；第二層選擇性)競合未裁決 ③洲際W轉貸 🔄10月直接國泰 ④築巢優利貸 ❌取消 ⑤債券質押5成 📌待執行但須過8/12四門檻。營運實況(8/17穿透)：總資產14,537,226；台股1,941,214(13.4%,最終SAA 15%)、美股5,641,399(38.8%,目標30%,+8.8pp超標)、防守3,114,832(21.4%)、債券3,053,675(21.0%,目標30%,-9.0pp)、現金786,106(5.4%,>70萬底線✅)。國泰轉貸：8/16舊永豐代償清償✅、帶出款1,200萬未入帳(預計8/17-8/23)；理財型房貸8/11全數清償✅；總負債18,148,676。US30Y 5.21%(數據停8/13、連3日防禦、距5.30%凍結線僅9bp、8/14週五數據缺失)。配息66,457≈7/31(130,930)之51%。市場：台股45,942/46,028突破4萬6(+0.29~0.47%)、波段反彈逾6千點、ETF下車潮單週-3萬人、CPI 3.5%降溫、美股平盤。

Part B CIO 對策反抗：
1.質疑盲點：🚨1,200萬部署三版競合未裁決(8/4「400萬市值型」vs 8/10「1,000萬買債+質押500萬」vs 8/12「800萬清償+美元直債到期梯」)，緊急應變報告又出現「B方案分批部署400萬」第四種說法；帶出款本週入帳，執行窗口已開，8/14點名後72小時仍未定錨。🚨現金底線85萬→70萬下修無核准紀錄(8/14審計點名現金違規後隨即下修)，gap_rules_0812仍寫85萬，快照內部矛盾——是合理調整(高利活存)還是被動移柱？🚨US30Y數據停8/13，8/14週五缺失，凍結線差9bp，若已觸5.30%系統不知情；階段2門檻1與全域凍結全依賴此數據源。🚨美股38.8%超標+8.8pp，「美股收斂30%」核准10天0筆減碼登錄，再平衡建議減碼127.9萬未執行。⚠️台股13.4% vs 臨時目標23.5%：400萬部署計畫設定於4萬點，現已反彈6千點至4萬6，追高vs低配缺口兩難。⚠️配息66,457僅7/31之51%，8/12底線規則②「被動實收連續2月<80%停建債」監控中，若結構性縮水美元直債建倉須重驗。
2.提醒：🔴帶出款入帳日(8/17-8/23)三件事：①方案競合定錨(執行哪一版) ②800萬高息清償+銷帳驗證(保單400@4%+質押100+理財200) ③現金緩衝基準定錨(70萬vs 6個月利息)。🔴gate_0紀律：入帳前禁止任何換匯/建債/質押。🟡補US30Y 8/14-8/17數據。🟡美股逢反彈分批減碼並登錄。🟡洲際W 10月國泰轉貸待8月部署後評估。🟢築巢已取消。
3.隱性風險：🚨決策治理風險：底線下修、目標改版(現金5%/債券30%)、代償完成等重大變更均未進dashboard核准流，決策軌跡與營運實況脫節，執行者對「現行規則」單一版本事實失去信心。🚨匯率雙向：台幣強升下美股5.64M台幣虛胖，直債到期換回恐匯損；惟此刻換匯建美元債成本下降屬利好窗口。🚨市場轉熱：6千點反彈+ETF下車潮，8/4「禁追漲大額」紀律 vs 400萬部署壓力。🚨系統續航：deepseek餘額46.54估10天，斷供則日報/風控全停。⚠️8/12「階段1禁止質押」vs pending「債券質押5成」，執行順序須以8/12裁決為準。"""
print(SUMMARY[:600])

props = {
    "事件名稱": {"title": [{"text": {"content": "CIO 戰略審計復盤 2026-08-17"}}]},
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
print(f"[OK] Ops log written to Notion: CIO 戰略審計復盤 2026-08-17 (page {r.json().get('id')})")
