# 龍九控股 — 代理分工與工作流程 SOP

## 一、角色定義

| 角色 | 模型 | 負責範圍 | 費用 |
|:----|:----|:---------|:----:|
| **Hermes（我）** | DS Flash | 日常機械工作、更新 snapshot、跑管線、改 cron、檔案操作 | ~330 CNY/月 |
| **CIO（代理）** | Gemini 2.5 Flash | 程式重構、正則、HTML排版、策略分析、除錯>3圈 | ~3 CNY/月 |
| **Pro（代理）** | DS V4 Pro | 僅 Gemini quota 用盡或手動指定時使用 | ~9 CNY/月 |

## 二、工作流程

### 發現問題時
1. 先判斷：機械操作 → 我做；複雜程式/分析 → 給 CIO
2. 卡住 2-3 次 → 直接給 CIO，不疊 patch
3. 委派前先問使用者確認方向，不亂猜

### 修復流程
1. 一次改到位，不 patch over patch
2. 修完驗證：跑一次腳本確認無錯誤
3. 累積 3-5 個 commit 才推送（禁止 --force），緊急修復可單獨推送。
4. 推送前確認所有產出檔案都在 commit 中

### 部署流程
1. 確認產出檔案清單：日報、差異分析、緊急應變報告、分析 JSON
2. 執行預部署檢查腳本（結合 longjiu-error-register 技能）。
2. 用 `git add -f` 明確加入每個檔案
3. 用 `git ls-tree` 確認檔案存在
4. 一般 `git push`（不用 --force）

## 三、決策紀錄流程

### 當使用者說 ✅ 核准時
1. 立即寫入 `dashboard_decisions.json`
2. 同時寫入 Notion 分析資料庫（notion_knowledge.py）
3. 記錄 INC 到 error_register.md
4. 更新對應技能 (包含新發現的解決方案、避免的陷阱或最佳實踐)

## 四、API 使用紀律

1. 觸發 LLM 分析前先檢查快取 JSON（有今日資料就不重跑）
2. 委派任務每次間隔 30-60 秒
3. Gemini quota 用完改走 Pro
4. 同 session 最多委派 3 次（超過則應創建新 session 或尋求人工介入）

## 五、禁止事項

1. 禁止 `git push --force`（除非使用者明確授權）
2. 禁止不問方向就委派
3. 禁止同問題 patch 超過 2 次（超過就給 CIO）
4. 禁止修改 snapshot.json、.db、數據檔案（交給使用者確認）
