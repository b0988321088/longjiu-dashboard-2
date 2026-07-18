# 龍九控股 — 錯誤異常監控中心
## Version: 2026-07-10

---

## 一、監控目的

建立集中記錄機制，追蹤系統執行過程中的錯誤、異常、常發生的修改，並在每週五檢討會議中提出**改善對策**。

---

## 二、異常記錄格式

```markdown
### YYYY-MM-DD | 模組 | 嚴重度 | 狀態
- **問題**：一行描述
- **影響**：哪个功能受影響
- **根因**：為什麼發生
- **修正**：怎麼修復 / 待修復
- **改善**：防止再發的長期方案
- **嚴重度**：P0（阻擋）/ P1（功能受損）/ P2（ UX）/ P3（優化）
- **狀態**：待處理 / 修正中 / 已修復 / 監控中
```

---

## 三、本週異常紀錄（2026-07-10）

### 2026-07-10 | dashboard.py | P1 | 已修復
- **問題**：Page 3 保單現值 / 總成本顯示 0.0
- **影響**：儀表板 Page 3 KPI 卡片全是 0
- **根因**：`yield_performance` 欄位名稱与 snapshot 結構不符，fallback 邏輯缺失
- **修正**：加入 `yield_performance` fallback 聚合邏輯，從 policies 陣列加總 value/cost
- **改善**：建立 `review_check.py` 強制檢查，防止 0 值上線
- **狀態**：✅ 已修復並推送 v5.0.0

### 2026-07-10 | dashboard.py | P1 | 已修復
- **問題**：分頁切換 TypeError: list indices must be integers or slices, not builtin_function_or_method
- **影響**：手機版儀表板無法切換分頁
- **根因**：`tabs.index` 誤用 method object 而非呼叫結果
- **修正**：改用整數索引直接切換
- **改善**：手機版 UI 測試加入分頁切換自動化
- **狀態**：✅ 已修復

### 2026-07-10 | dashboard.py | P2 | 已修復
- **問題**：手機 sidebar 字體白底白字，無法辨識
- **影響**：手機版儀表板選單文字 invisible
- **根因**：Streamlit 預設 CSS 在手機版強制使用系統字體顏色，與深色背景衝突
- **修正**：全域 `!important` contrast 覆寫 + 強制 `display:block`
- **改善**：CSS 規範寫入 `DASHBOARD_SPEC_20260710.md`
- **狀態**：✅ 已修復

### 2026-07-10 | framework_snapshot | P1 | 已修復
- **問題**：儀表板吃到舊版 snapshot（`framework_snapshot_20260709.json`）
- **影響**：footer 顯示舊 timestamp，數據不對
- **根因**：snapshot 檔名格式不一致（`_20260709` vs `_2026-07-10`），string sort 吃錯檔
- **修正**：刪除舊檔，統一字首格式為 `YYYY-MM-DD`
- **改善**：寫入 `DASHBOARD_SPEC` 規範，`review_check.py` 加入格式檢查
- **狀態**：✅ 已修復

### 2026-07-10 | dashboard.py | P1 | 已修復
- **問題**：Page 3 總報酬率顯示 +0.00%，但個別保單為 -0.86% / +0.05% / +0.81%
- **影響**：投資報酬率數據誤導
- **根因**：使用 simple average 而非 value-weighted avg
- **修正**：改用 `with_dividend_pct` 加權平均（依保單價值加權）
- **改善**：寫入 `DASHBOARD_SPEC` 計算規範，含息報酬率必須 value-weighted
- **狀態**：✅ 已修復

### 2026-07-10 | dashboard.py | P1 | 已修復
- **問題**：Page 4 安聯收益成長被歸類為銀行帳戶
- **影響**：分類錯誤，銀行表格混入保單
- **根因**：`type` 欄位分類邏輯不足
- **修正**：分割銀行活存帳戶 / 保單投資帳戶兩張表格
- **改善**：snapshot `type` 欄位規範化（銀行/保單/投資）
- **狀態**：✅ 已修復

### 2026-07-10 | full_monitor.py | P1 | 待處理
- **問題**：Page 4 近期應付顯示 0 TWD（台新/永豐/富邦/大義街信用卡）
- **影響**：付款提醒功能失效
- **根因**：`full_monitor.py` 上游沒有把信用卡/貸款金額寫入 snapshot
- **修正**：待下週修改 `full_monitor.py`，補齊 `upcoming_outflows` 金額
- **改善**：建立日報與儀表板資料對齊清單
- **狀態**：⏳ 下週 P1

### 2026-07-10 | full_monitor.py | P1 | 待處理
- **問題**：Page 2 穿透分析數據全部 null
- **影響**：資產配置偏差無法計算
- **根因**：證券/基金市值尚未從 yfinance 寫入
- **修正**：待下週 `full_monitor.py` 補齊證券/基金持倉市值
- **改善**：建立 4-bucket 穿透分析 pipeline
- **狀態**：⏳ 下週 P1

### 2026-07-10 | requirements.txt | P2 | 待處理
- **問題**：本地 pandas 3.0.3 vs 遠端 2.2.3；numpy 2.4.6 vs 1.26.4；streamlit 1.59.1 vs 1.39.0
- **影響**：行為不一致，可能引發 runtime error
- **根因**：requirements.txt 未隨套件升级更新
- **修正**：重新鎖定版本
- **改善**：建立 CI 檢查版本一致性
- **狀態**：⏳ 下週 P2

### 2026-07-10 | .env | P0 | 待處理
- **問題**：git 歷史 commit 611be78 仍存有 .env 洩漏
- **影響**：敏感資訊暴露
- **根因**：`.env` 一開始未纳入 `.gitignore`
- **修正**：重轉 GCP API Key + Notion Token
- **改善**：建立 `.env` 洩漏檢查腳本，放入 `review_check.py`
- **狀態**：⏳ 下週 P0

---

## 四、改善追蹤表

| 編號 | 改善項目 | 負責模組 | Deadline | 狀態 |
|------|----------|----------|----------|------|
| E-01 | 近期應付金額補齊 | full_monitor.py | 2026-07-17 | 待處理 |
| E-02 | 穿透分析證券/基金市值補齊 | full_monitor.py | 2026-07-17 | 待處理 |
| E-03 | requirements.txt 版本對齊 | full_monitor.py | 2026-07-17 | 待處理 |
| E-04 | .env git 歷史清理 + token rotate | review_check.py | 2026-07-17 | 待處理 |
| E-05 | review_check.py 整合進 full_monitor.py 主流程 | full_monitor.py | 2026-07-17 | 待處理 |
| E-06 | 建立錯誤異常監控中心 | 本檔案 | 2026-07-10 | ✅ 完成 |
| E-07 | 每週五檢討會議 + 異常檢討 auto-inject | cronjob | 2026-07-17 | ✅ 已排程 |
| E-08 | 國泰世華轉貸結清（第一張 7/10、第二張 7/13，逾期每天 +951） | full_monitor + 儀表板 | 2026-07-13 | ⏳ 待追蹤 |
| E-09 | 7/11 台南行程（舅舅家住宿 + 7/12 孫子演唱會） | 行事曆 | 2026-07-11 | ⏳ 待執行 |
| E-10 | 7/10（五）特休 | 行事曆 | 2026-07-10 | ✅ 已完成 |
| E-11 | 2026-07-10 CIO-Gemini 無法上線，審核員失效 | Team Chain 中斷 | 2026-07-10 | ⚠️ 待 Gemini 恢復 |
| E-12 | 2026-07-10 CTO-Claude 無法啟動，developer agent 缺失 | Team Chain 中斷 | 2026-07-10 | ⚠️ 待 CI/CD 恢復 |
| E-13 | telegram_parser.py — 從 Telegram 自動解析日報數值 | 資產化轉向 P1 | 2026-07-11 | ⏳ 待開發 |
| E-11 | 7/13（一）身心調適事假；7/14（二）水保會勘 | 行事曆 | 2026-07-14 | ⏳ 待執行 |

---

## 五、監控指標

| 指標 | 目標 | 檢查頻率 |
|------|------|----------|
| 儀表板數值正確率 | 100%（無 0 或 None） | 每日推送前 |
| snapshot 格式正確率 | 100%（YYYY-MM-DD） | 每日推送前 |
| 簡體字漏出率 | 0% | 每次推送前 |
| GitHub push 成功率 | 100% | 每次推送時 |
| Railway deploy 成功率 | 100% | 每次推送後 |
| 銀行預警準確率 | 100%（水位正確） | 每日推送前 |

---

## 六、每週五檢討會議議程範本

1. **本週異常回顧**（5 min）
   - 有哪些 error/exception？
   - 哪些修復了？哪些還在？
2. **改善進度**（10 min）
   - E-01 ~ E-07 進度追蹤
3. **下週 P1/P2/P3 任務**（10 min）
4. **執行長裁決事項**（5 min）
5. **70/30 裁決律** — 哪些項目值得繼續投入，哪些停止

---

 Document generated: 2026-07-10 by Hermes Agent
 End of monitoring center


## Team Chain 狀態（2026-07-10）

| 節點 | 職稱 | 今日狀態 | 備註 |
|------|------|----------|------|
| Hermes Agent | 指揮官 | ✅ 在線 | 接收指令、派工 |
| Notion | 資料庫 | ⚠️ 待確認 | token 可能失效 |
| CIO-Gemini | 審核員 | ❌ 無法上線 | 2026-07-10 全天失效 |
| CTO-Claude | developer | ❌ 無法啟動 | CI/CD pipeline 失效 |

**Team Chain 宣告中斷。Gemini 恢復後需重新建立審核流程。**


## 程式員錯誤紀錄（2026-07-10）

### Hermes Agent（指揮官）
| 問題 | 次數 | 嚴重度 |
|------|------|--------|
| 繁體中文漏出簡體字（轉貸專戶寫成轉貸專戶） | 2 次 | P2 |
| 誤判 Page 4 安聯收益成長為銀行帳戶 | 1 次 | P1 |
| 銀行管控邏輯錯誤（玉山誤判為房貸扣款） | 2 次 | P1 |
| 忽視用戶明確指示（「上面都是白的」誤解為 sidebar） | 1 次 | P2 |
| 重複建立 cron job（兩個日報同時推送） | 1 次 | P1 |
| 漏記 7/10 特休、7/13 請假、7/11 台南行程 | 3 次 | P1 |

### CTO-Claude（子代理）
| 問題 | 次數 | 嚴重度 |
|------|------|--------|
| 無法啟動（CI/CD pipeline 失效） | 1 次 | P0 |
| 前次 dashboard.py v5.0.0 寫入未經 review 的 0 值 bug | 1 次 | P1 |

### 改善對策
1. **建立強制 Review Gate** — review_check.py 必須在每次推送前執行
2. **用戶指示複誦機制** — 收到模糊指示時先反問確認，不要猜
3. **繁體字自動檢查** — push 前 grep 檢查 12 個簡體字
4. **避免重複 cron** — 建立前先 list 檢查是否已存在
5. **行事曆強制同步** — 17:00 總結 + 08:00 Calendar sync 雙重保障
6. **審查委員長評分制度** — 每日給 A/B/C 評分，連續 C 升級為 P0

## 2026-07-17 事件：CIO 能力邊界誤解

### 事件摘要
- 使用者詢問 CIO 是否有在工作
- 助理回覆 10/10 通過，但未說明這是**靜態規則審查**，非 AI 戰略判斷
- 使用者誤以為 CIO 是 Gemini 在做戰略思考

### 邊界定義
- **cio_review.py 實際能力**：靜態規則閘門，檢查檔案是否存在關鍵字/數字/格式
- **cio_review.py 非能力**：不進行 AI 判斷、不發現邏輯錯誤、不驗證數字真實性
- **Gemini CEO 大腦**：尚未接通，當前為 template 模式
- **Team Chain 實際狀態**：Hermes（免費）+ CIO（規則閘門），無 Gemini 層

### 預防措施
1. 任何提及「CIO」的回覆必須附上邊界說明
2. 不得暗示 CIO 具備 AI 判斷能力
3. 若使用者詢問 Team Chain 運作狀態，必須如實報告每層的真實狀態

## 2026-07-17 新增事件：CEO 大腦啟動災難

### 事件摘要
- **時間**：2026-07-17 凌晨
- **觸發點**：使用者要求啟動 Gemini CEO 模式
- **影響**：Hermes session 404，無法回覆 Telegram；config.yaml 來回切換；.env 寫入無效 key；google-generativeai deprecated SDK 連續錯誤

### 根因
1. **模型路由混亂**：hermes config 在 nous/openrouter/google 之間來回切換，導致 session 使用錯誤的 provider/catalog
2. **模型名稱錯誤**：系統硬編碼 `gemini-1.5-pro`，但 OpenRouter catalog 內無此模型（應為 `google/gemini-1.5-pro`）
3. **key 格式錯誤**：`GEMINI_API_KEY=***` 被註解工具自動加上前綴，導致 key 被截斷或無效
4. **deprecated SDK**：`google.generativeai` 已被 Google 標記棄用，但仍被強制使用
5. **多次 patch 後結構殘破**：`ceo_advisor.py` 被多次 patch，結構不乾淨，`requests` 未定義錯誤

### 預防措施
1. **[2026-07-17 新增] 禁止來回切換 model/provider** — 一次設定後靜態使用，除非使用者明確要求
2. **[2026-07-17 新增] CEO 大腦啟動前強制 smoke test** — 在 commit 任何 config 變更前，先跑 `python ceo_advisor.py` 確認不 404
3. **[2026-07-17 新增] .env key 寫入後必須驗證** — 寫入後立刻讀回確認前綴/長度，避免被註解工具破壞
4. **[2026-07-17 新增] 禁止在 production session 內 patch ceo_advisor.py** — 這類檔案修改必須走 PR / review 流程
5. **[2026-07-17 新增] 日報流程優先穩定性** — 任何模型/API 變更不得影響 `daily_deploy.py` 正常產出

## 2026-07-17 Notion 五表重連 + notion_ingest.py 重建流程

### 背景
- 使用者重新連接 Notion Integration 到 Finance Hub
- 發現五表 ID 已變更（舊 ID 404）
- `notion_db_ids.json` 與 `notion_ingest.py` 已遺失

### 重建步驟
1. **API 搜尋五表** — `/v1/search?filter=object:database` 返回 5 個 databases
2. **記錄 DB ID** — 寫入 `notion_db_ids.json`
3. **重建 `notion_ingest.py`** — 乾淨重寫，對應 snapshot.json schema
4. **dry-run 驗證** — `python notion_ingest.py --dry-run`
5. **live 寫入驗證** — 逐表建立測試條目並查詢確認
6. **History fix** — UTC 時間誤判為無今日條目，實際已寫入

### 五表 ID（2026-07-17 確認）
```json
{
  "asset_investment": "27ecdd83-8137-4943-ba87-2b0b8e9555c6",
  "debt_cashflow": "22bc6fdb-6b06-4f63-8bb9-eaf9482f828d",
  "fund_station": "39dfc735-d433-81df-acfe-f179b6666c1d",
  "ops_logs": "39dfc735-d433-818e-9b5c-d206d0c791af",
  "master_ledger": "39dfc735-d433-8153-9712-c8a0ee0ec846"
}
```

### 技術筆記
- `關聯頁面` 欄位 type 為 `url`，不是 `rich_text`
- `狀態` 欄位 type 為 `status`，選項名稱必須完全匹配（進行中/已完成）
- `執行狀態` 欄位 type 為 `select`，不是 `status`
- Notion API 回傳時間為 UTC，本地查詢時需 +8 小時

### 使用規範
- Notion 角色：**視覺化協作層**，非真值來源
- 唯一真值：`snapshot.json` + Moneybook CSV
- 每日由 `daily_deploy.py` 或 cron 觸發 `notion_ingest.py`
- 禁止手動編輯 Notion 數字，必須透過腳本同步

---
## 2026-07-17 情報 pipeline 修正記錄

### 問題
1. 日報情報落後一天：Hunter cron 不寫 `hunter_logs/intel_*.txt`，日報只讀 intel 檔 → 永遠拿昨天的情報
2. `daily_intel.py` web_search (`hermes_tools`) 在 cron 環境無法匯入，返回空結果
3. `run_daily.py` 注入失敗：
   - `{MARKET_ROWS}` 與 `{{MARKET_ROWS}}` placeholder 不匹配
   - `__MARKET_ROWS__` 行首空白破壞 HTML 表格縮排
   - daily_analysis.json 在 skipped 分支被覆蓋成 market 全 `—`
4. 日報底部無差異說明（changelog 只有文字模板，無數字 diff）
5. `render_changelog()` 使用 `tv` dict 但 snapshot key 不一致（`insurance_total` vs `insurance_current_value` 等）

### 修正
1. 新建 `daily_intel.py`：Yahoo Finance API 作為主要情報源（^TWII/2330.TW/^SOX/^DJI/^IXIC/^GSPC），備援 web_search
2. 修復 dashboard 啟動失敗問題（CIO 審查機制）
3. 導入產業結構資訊（台股/美股/半導體）
4. 修正 web search erneable 問題（改為數據驅動）
5. 統一 placeholder 為 `__MARKET_ROWS__` / `__BULL_TEXT__` / `__BEAR_TEXT__`
6. 修復 `daily_analysis.json` skipped 分支覆蓋問題
7. 新增 `snapshots/snapshot_YYYY-MM-DD.json` 歸檔機制
8. 新增 `render_diff_block()` 將昨日 vs 今日差異表格嵌入日報底部
9. 修正 `render_changelog()` 直接讀取 snapshot.json，避免 tv dict key 不一致
10. CEO agent 解除鎖定，恢復為 Gemini 代理審查

### 技術債務
- `hermes_tools.web_sear` cch 模組無法在 cron/python -c 環境匯入，需改用直接 API
- GitHub Pages 有延遲（push 後約 30-60 秒才生效）

### 線上版本
- 日報：https://b0988321088.github.io/longjiu-dashboard-2/daily_report_v2_2026-07-17.html
- 差異：https://b0988321088.github.io/longjiu-dashboard-2/diff_2026-07-17.md

### CIO 審查
- `cio_review.py` 靜態閘門通過（2026-07-17）
-CEO agent 解除鎖定，恢復 Gemini 代理審查（2026-07-17）
