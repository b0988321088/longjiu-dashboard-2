#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-09-20 週計畫調整（00921 分 2 批、全走乾粉）＋過期資訊清理＋INC-221/22,180 登記。

來源依據：
  - 使用者 9/20 Telegram：00921×3 張、分兩批、資金全走乾粉
  - US30Y 9/17 收 5.29（< 凍結線 5.30）｜FRED DFEDTARU 9/17 起 4.00
  - 雷達 台股 🟢 外資淨買超 3.8 億（連 3 日，9/18）
  - 00921 9/16 已除息 1 元（10/7 發放）→ 本批領不到
"""
import json, os, shutil, datetime
from pathlib import Path

B = Path(r"C:\Users\bot\Desktop\longjiu_system")
os.chdir(B)
TS = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def load(p):
    return json.loads((B / p).read_text(encoding="utf-8"))

def save(p, d, indent):
    (B / p).write_text(json.dumps(d, ensure_ascii=False, indent=indent), encoding="utf-8", newline="\n")

def bak(p):
    shutil.copy2(B / p, B / f"{p}.bak-20260920")

changes = []

# ── 1) radar_state：本週投資計劃 + 政策面（過期 9/5 → 9/16 FOMC 後事實）────────
r = load("radar_state.json"); bak("radar_state.json")
rows = r["weekly_plan"]["rows"]
old_tw = rows[0]["內容"]
rows[0]["動作"] = "🟡"
rows[0]["內容"] = ("00921（兆豐龍頭等權重）×3 張 ≈70,950｜**分 2 批**：①9/21-9/22 限價 2 張（≈47,300）"
                   "②回檔 -2%（≤23.2）或 10/7 配息發放後補 1 張（≈23,650）｜資金＝**乾粉**"
                   "（現金 916,397 − 底線 700,000 = 216,397）｜解凍依據：US30Y 9/17 收 5.29 < 5.30＋"
                   "外資連 3 日買超 3.8 億🟢＋9/16 FOMC 升息 1 碼利空出盡｜停止條件：US30Y ≥5.30／"
                   "外資轉連續賣超／VIX>25｜註：9/16 已除息 1 元（10/7 發放）本批領不到，下次季配約 12 月")
changes.append(("weekly_plan.台股", old_tw[:60], rows[0]["內容"][:60]))

old_bond = rows[3]["內容"]
rows[3]["內容"] = ("28.8%（目標 25%，超配 +3.8pp）→ 不新增：10Y 月動能 +6.2% 急升🔴；等動能轉緩＋"
                   "US30Y 站穩 5.30 之下再議")
changes.append(("weekly_plan.債券", old_bond[:50], rows[3]["內容"][:50]))

old_cash = rows[4]["內容"]
rows[4]["內容"] = ("3.5%｜底線 700,000 守；乾粉 216,397 → 指派 00921 70,950（分 2 批），餘 145,447 機動"
                   "（質押 540萬 撥款前不減底線）")
changes.append(("weekly_plan.現金", old_cash[:50], rows[4]["內容"][:50]))
r["weekly_plan"]["日期"] = "2026-09-20"

r["policy_notes"] = {
    "來源": "FRED（DFEDTARU/DGS30）＋鉅亨/經濟日報/玉山銀 2026-09-20 更新（原 9/5 非農/FOMC 待決版已汰換）",
    "新聞1_9月FOMC升息1碼": {
        "內容": "9/15-16 FOMC 決議升息 1 碼：政策利率 3.50-3.75% → 3.75-4.00%（FRED DFEDTARU 自 9/17 起 4.00、DFF 3.63→3.88）；台灣央行不跟進、維持利率不變",
        "市場反應": "市場以「利空出盡」解讀：美股大漲、費半領漲；台股 9/18 開 46,449.56、盤中大漲逾 760 點站上 47,000（台積電 +35 元、觸及 2,460）；US30Y 5.34→9/17 收 5.29（長端回落）",
        "對資產影響": "不確定性消除 → 台股順勢（外資連 3 日買超）＝台股分批進場條件成立；債券桶短線仍受 10Y 月動能 +6.2% 壓抑 → 暫不新增",
    },
    "新聞2_後續觀察": {
        "內容": "下次 FOMC 11 月；10 月標案結果（押標金 240萬 來源 9 月底評估）；9/29 貝萊德黃金/健康 9 月配息基準日",
        "市場反應": "10Y 月動能 +6.2%（急升，債券承壓🔴）；USD/TWD 31.76（週 +0.27%，⚪）；黃金 COT 淨多單 230,338（週 -0.7%，🟡）",
        "對資產影響": "若 10Y 續升 → 債券桶維持不新增；台股 00921 分批、避險衛星黃金批次照計畫（單批 ≤20萬、逢回檔）",
    },
    "原油綜合判斷": "COT 淨多單 -17,845（週增 28%，資金面 🟢 順勢）；需求面受升息壓抑、供給面美委/伊朗拉鋸 → 維持 🟡 觀望，石油部位 Locked 不加碼",
    "債券升息敏感度": "升息 1 碼已落地（9/17 起 4.00）；債券桶 28.8%（7,507,641，目標 25% 超配）→ 已反映約 -0.5~-1.5% 價格影響；真正利率敏感＝保單內債券（PIMCO/M&G/摩根，債權重 48-55%）＋00983D；10Y 月動能 +6.2% 急升 → 不新增",
    "記錄時間": f"{TS}（原 2026-09-05 08:40 版已汰換）",
}
save("radar_state.json", r, 1)
changes.append(("policy_notes", "9/5 非農+FOMC待決", "9/16 FOMC 升息1碼已成事實＋後續觀察"))

# ── 2) pending 清理（兩檔同步：刪 3 筆已結案、加 1 筆待對帳）─────────────────
CLOSE_TITLES = [
    "升息警戒決策（9/11 CPI 開關 → 9/16 FOMC 解除）",
    "防守口徑定案＋防禦缺口補法（9/16 授權定案）",
    "AI 成本治理：context 瘦身 + CER 監控（L1/L4 定案）",
]
NEW_PENDING = {
    "date": "2026-09-20",
    "title": "安聯累計現金給付總額對帳（差額 22,180）",
    "status": ("📌 待對帳：安聯 App 累計現金給付 1,782,242（A 1,046,391＋B 735,851）− snapshot 同期 "
               "dividend_records 記錄 129,100（8月 76,931＋9月 52,169）＝ 差 22,180，疑為 7/28 前未入帳批次"),
    "tags": "對帳,安聯,Moneybook",
    "detail": ("2026-09-20：snapshot 的 policy_a/b_cumulative_dividend 自 7/28 起未更新（皆為 943,850/687,112），"
               "已依 9/20 12:17 App 截圖覆蓋為 1,046,391/735,851（+151,280）。與同期 dividend_records 記錄 "
               "129,100 差 22,180 → 下次 Moneybook 匯出時對帳確認（不自行調整 dividend_records，避免重複計）。"),
}

p_std = load("pending_decisions.json"); bak("pending_decisions.json")
removed = [x for x in p_std if str(x.get("title")) in CLOSE_TITLES]
p_std = [x for x in p_std if str(x.get("title")) not in CLOSE_TITLES]
p_std.append(NEW_PENDING)
save("pending_decisions.json", p_std, 2)

d_dash = load("dashboard_decisions.json"); bak("dashboard_decisions.json")
pd = d_dash["pending_decisions"]
removed_d = [x for x in pd if str(x.get("action")) in CLOSE_TITLES]
pd = [x for x in pd if str(x.get("action")) not in CLOSE_TITLES]
pd.append({"date": NEW_PENDING["date"], "action": NEW_PENDING["title"],
           "status": NEW_PENDING["status"], "tags": NEW_PENDING["tags"],
           "detail": NEW_PENDING["detail"]})
d_dash["pending_decisions"] = pd
d_dash["meta"]["updated_at"] = datetime.datetime.now().isoformat()
save("dashboard_decisions.json", d_dash, 2)
changes.append(("pending 清理", f"刪 {len(removed)}(std)/{len(removed_d)}(dash)", f"剩 {len(p_std)} 筆＋新增待對帳 1 筆"))

# ── 3) schedule_events：刪過期/作廢、補本次計畫 ─────────────────────────────
ev = load("schedule_events.json"); bak("schedule_events.json")
events = ev if isinstance(ev, list) else ev["events"]
DROP_MATCH = [
    "🏛️ FOMC 利率決議 → 升息警戒解除/延續（9/5 裁示）",                     # 9/16 已過（結果已入 policy_notes）
    "⏸️ 安聯保單轉換（原：→0056/NTDET0130 台幣化）",                        # 9/15 已閉環作廢
    "📌 安聯保單轉換 T+4 生效 → 更新 snapshot",                              # 9/16 已生效、snapshot 已同步
    "📋 標案前置：建明+謝技師 風險檢查清單",                                  # 9/1 過期
    "🔴 洲際W 轉貸：國泰詹理專洽談啟動",                                     # 9/1 過期（9/9 已延後，另由 pending 追蹤）
    "🛡️ 避險衛星批1 送件：保單B 摩根 20萬",                                  # 9/16 過期（截止日改由 9/23 那筆追蹤）
    "🔴 安聯AI 9/24 除息 T+4 截止",                                          # 9/18 截止已過
]
drop_idx = [i for i, e in enumerate(events)
            if any(str(e.get("item", "")).startswith(m) for m in DROP_MATCH)]
dropped = [events[i].get("item") for i in drop_idx]
events = [e for i, e in enumerate(events) if i not in drop_idx]
# 9/23 那筆 schema 不符（title/type）且與 9/16 已生效的 M&G 轉換重複 → 一併刪
events = [e for e in events if not (e.get("date") == "2026-09-23" and e.get("title") == "M&G 保單轉換執行")]
# 補：本次 00921 計畫 + M&G 配息入帳
events.append({"date": "2026-09-22", "item": "🟡 00921 第1批進場（2 張 ≈47,300，限價）— 資金＝乾粉；停止條件：US30Y ≥5.30／外資轉賣超／VIX>25",
               "status": "⏳ 待執行", "category": "台股", "importance": "high"})
events.append({"date": "2026-10-07", "item": "🟡 00921 第2批檢核（1 張 ≈23,650）：回檔 ≤23.2 或配息發放日；同時檢核 10/7 第一站配息",
               "status": "⏳ 待執行", "category": "台股", "importance": "medium"})
events.append({"date": "2026-09-23", "item": "💰 M&G 首筆配息入帳（基準日 9/18、T+N）→ 寫入 dividend_records 9 月累計",
               "status": "⏳ 待入帳", "category": "保單", "importance": "medium"})
events.sort(key=lambda e: str(e.get("date", "")))
save("schedule_events.json", events, 2)
changes.append(("schedule_events", f"刪 {len(dropped)} 筆過期/作廢", f"新增 3 筆（00921×2＋M&G 入帳），共 {len(events)} 筆"))

# ── 4) work_log：INC-221 ＋ 本次計畫調整 ──────────────────────────────────
wl = load("work_log.json"); bak("work_log.json")
wl.append({"date": "2026-09-20", "category": "修正",
           "item": "INC-221：儀表板舊值殘留檢查抽成 check_dashboard_stale.py（排除註解/cio-old 歸檔區）",
           "detail": ("sync_all 最後一步把 9/16 CIO 審查全文（<details class=\"cio-old\">／JS 註解離線快照）內的"
                      "『可動用 772,607』誤判為殘留舊值而中止管線。改動：邏輯抽成 check_dashboard_stale.py 單一入口，"
                      "掃描前排除 HTML 註解、JS 註解、cio-old 歸檔區；<script> 內 JS 硬編碼仍照掃（不放寬）。"
                      "驗證：正負測試 6/6 PASS（活區塊/JS 陣列注入→命中；cio-old/註解注入→不命中）＋sync_all 10 步驟全過。"
                      "真 CIO 審查（Pollinations 額度用盡 → 改 Gemini 異質審查）APPROVE 0.9；commit 4647cdf3 tree 12ae092f。")})
wl.append({"date": "2026-09-20", "category": "更新",
           "item": "本週投資計劃調整：00921×3 張分 2 批、資金全走乾粉（＋政策面汰換過期 9/5 版）",
           "detail": ("使用者 9/20 指示。解凍依據：US30Y 9/17 收 5.29 < 凍結線 5.30（FRED）＋雷達台股 🟢 外資淨買超 3.8 億"
                      "（連 3 日）＋9/16 FOMC 升息 1 碼（3.50-3.75→3.75-4.00，DFEDTARU 9/17 起 4.00）利空出盡、台股 9/18 大漲逾 760 點。"
                      "計畫：①9/21-9/22 限價 2 張（≈47,300）②回檔 ≤23.2 或 10/7 配息發放後補 1 張（≈23,650）；"
                      "資金＝乾粉（現金 916,397 − 底線 700,000 = 216,397，餘 145,447 機動）；停止條件 US30Y ≥5.30／外資轉賣超／VIX>25。"
                      "註：00921 已於 9/16 除息 1 元（10/7 發放）→ 本批領不到，下次季配約 12 月。"
                      "同步清理：radar policy_notes 汰換 9/5 非農/FOMC 待決版 → 9/16 FOMC 升息已成事實＋後續觀察；"
                      "pending 刪 3 筆已結案（升息警戒/防守口徑定案/AI 成本治理）＋新增『安聯累計給付差額 22,180 待對帳』；"
                      "schedule_events 刪 7 筆過期/作廢＋1 筆重複 schema 項、新增 3 筆。")})
save("work_log.json", wl, 1)

# ── 5) error_register：INC-221 ─────────────────────────────────────────
er = B / "error_register.md"
old = er.read_text(encoding="utf-8")
er.write_text(old.rstrip() + """

## 2026-09-20（INC-221）儀表板舊值殘留檢查把「歷史引文」誤判為殘留 → 管線最後一步中止

- **症狀**：sync_all.py 執行到最後「儀表板產出驗證」時報 `❌ 儀表板殘留舊值: ['772,607']` 並中止（後續 3 步驟未跑）。
- **根因**：原檢查內嵌在 sync_all 步驟清單（一行 `python -c` 的 `值 in html` 比對），無法分辨「活的顯示值」與「引用的歷史文字」。`772,607` 只出現在（a）`<details class="cio-old">` 歸檔的 9/16 CIO 審查全文、（b）JS `/* ... */` 註解內的離線快照 fallback；實際現金顯示值為 916,397。
- **修法**（`4647cdf3` tree `12ae092f`）：抽出 `check_dashboard_stale.py` 單一入口，掃描前剔除 HTML 註解、JS 註解、`cio-old` 歸檔區；**`<script>` 內 JS 硬編碼照掃**（維持 8/29 覆蓋率，不放寬）。
- **驗證**：正負測試 6/6（活區塊/JS 陣列注入→命中；cio-old/JS 註解/HTML 註解注入→不命中）；sync_all 全管線 10 步驟全過；真 CIO 審查（Pollinations 額度用盡 → 改 Gemini 異質審查）APPROVE、confidence 0.9。
- **教訓**：**「值比對」型檢查必須先界定「活的內容邊界」** —— 報表會引用歷史全文（CIO 審查、復盤），這些引文裡的舊數字是正確的歷史，不是殘留。檢查若不先剔除，就會在「改對之後」被自己的歷史擋住；同理可推及任何掃「舊值/舊日期」的稽核（如 closeout 的 1b 掃描已用排除清單解決同類問題）。
""", encoding="utf-8")
changes.append(("error_register.md", "無 INC-221", "已登記"))

print("=== 變更摘要 ===")
for label, old_v, new_v in changes:
    print(f"  {label}\n     舊: {old_v}\n     新: {new_v}")
print(f"\n  schedule_events 刪除項：")
for d in dropped:
    print("   -", str(d)[:70])
print("\n✅ 全部寫入完成（.bak-20260920 備份）")
