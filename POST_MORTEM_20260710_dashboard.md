# 龍九控股 Dashboard 進化方向
## 2026-07-10 戰役事後檢討（Post-Mortem）

---

## 1. 今日戰役摘要
- **任務**：修復手機版儀表板無法正常顯示 / 頁面切換失效
- **結果**：代碼層已通過本地驗證，部署層仍卡在 Railway build cache + GitHub Push Protection
- **使用者體驗**：執行長用手機操作 Railway 極度困難
- **結論**：代碼問題已定位並修正，需在電腦環境完成 final deploy

---

## 2. 診斷時間線

| 時間 | 發現 | 處理 |
|------|------|------|
| 20:31 | 手機截圖顯示 Page1 KPI=None, Page3=0.0 | 讀取 snapshot，發現缺頂層 total_current_value |
| 20:40 | dashboard.py line 236-260 有 NameError: cf undefined | 修復：cf → acf |
| 20:50 | CSS `lineargradient` 拼寫錯誤 + 手機字色過淡 | 修復拼寫 + 加入 !important |
| 21:00 | 手機版無側邊欄選單 | 修改 lines 98-110 加入水平分頁按鈕 |
| 21:05 | `tabs.index` 是 method，不是 int | TypeError: list indices must be integers |
| 21:10 | Railway 顯示 deploy=1783680879 舊版 | 確認 build cache 卡舊版 |
| 21:30 | 手機截圖仍顯示舊版 | 判定為 Railway container cache 問題 |
| 21:35 | GitHub Push Protection 擋住所有 push | `.env` 歷史 commit 含 API Key |
| 21:49 | 使用者手動 Allow secret | Push Protection 解除 |
| 22:00 | 重寫 dashboard.py v5.0.0 | 乾淨版，消除所有 patch 殘留 |

---

## 3. 根本原因分析（Root Cause Analysis）

### 3.1 代碼層
| 根因 | 影響 | 狀態 |
|------|------|------|
| `cf` 未定義（遺留 rename 殘留） | Page1 全中斷，KPI=None | ✅ 已修復 |
| snapshot 無頂層保單 KPI 總和鍵 | Page3 保單現值/總成本=0.0 | ✅ 已修復（fallback from policies list） |
| `tabs.index` 誤用（method vs int） | 手機版頁面切換 TypeError | ✅ 已修復 |
| 多層導航衝突（sidebar + radio + button） | 手機版無法切頁 | ✅ 重寫，單一 source of truth |
| `deploy=1783680879` 硬編碼 | footer 顯示舊版本號 | ✅ 已移除 |
| 補丁疊加导致代碼 536 行雜亂 | 隱藏 bug 難以發現 | ✅ v5.0.0 乾淨重寫 577 行 |

### 3.2 部署層
| 根因 | 影響 | 狀態 |
|------|------|------|
| Railway build cache 卡舊版 | 手機 viewer 持續吃舊容器 | ⏸️ 需下週用電腦 Redeploy |
| GitHub Push Protection 擋住 push | 所有 git push 失敗 | ✅ 已解除（Allow secret） |
| HTTPS push 在此環境 timeout | 本機 git push 行不通 | ✅ 改走 Contents API |

### 3.3 安全層
| 根因 | 影響 | 狀態 |
|------|------|------|
| `.env` 被 commit 到 repo | API Key / Notion Token 暴露在歷史 | ⚠️ **待處理** |
| 歷史 commit 無法被 push protection 覆盖 | 必須手動 Allow 或清除歷史 | ⚠️ **建議清除歷史** |

---

## 4. 進化方向（ prioritized ）

### P0 — 下週第一個工作日
1. **清除 `.env` git 历史**
   - 使用 `git filter-repo` 或 `bfg` 移除 `.env` 所有歷史
   - 重新 push force，讓 repo 完全乾淨
   
2. **Rotate 所有暴露的凭据**
   - GCP Console → 重新 generate API Key
   - Notion → 重新 rotate Integration Token
   
3. **Railway 重新部署**
   - 用電腦進 Railway → Redeploy
   - 確認 container 吃到最新 dashboard.py
   - 手機驗收：Page1 KPI、Page3 保單數值、頁面切換

### P1 — 技術架構改進
1. **Dashboard 代碼品質**
   - 保持 v5.0.0 乾淨結構
   - 加入單元測試（至少 KPI 計算與 fallback 邏輯）
   
2. **Snapshot 結構標準化**
   - 所有 page 統一使用 `yield_performance.total_current_value` 等頂層摘要鍵
   - 不要讓 dashboard 做太多 fallback，應在 snapshot 生成時完成計算

3. **CI/CD 加固**
   - GitHub Actions 加入 pre-commit hook 阻擋 `.env` 进入 repo
   - Railway 加入 cache clear 步驟避免吃到舊版

### P2 — 使用者體驗
1. **手機優先設計**
   - sidebar 隱藏時自動啟用水平按鈕
   - 所有 KPI 卡片在 < 400px 寬度下仍可讀

2. **錯誤處理**
   - 任何 None/0.0 顯示前都先 fallback
   - 加入 debug mode 顯示當前讀取的 snapshot keys

---

## 5. 經驗教訓（Lessons Learned）

1. **不要疊補丁**：536 行的代碼加了 4 次 hotfix，每次只修一個症狀。正確做法是停下來做根因分析，乾淨重寫。
2. **手機 debug 極度昂貴**：每次截圖 → 解釋 → 操作循環耗時 5-10 分鐘，需要更好的遠端 debug 工具或自動化。
3. **Push Protection 必須事前處理**：commit 前就該檢查 `.env` 是否被追蹤，等 blocked 才處理太晚。
4. **Railway build cache 是隱形殺手**：Git push 成功不代表 container 更新，需要額外驗證步驟。
5. **Subagent 分析有價值**：本次重寫 dashboard.py 交給分析員完成，比逐步 patch 有效率得多。

---

## 6. 行動清單（Action Items）

| 優先度 | 負責人 | 行動 | Deadline |
|--------|--------|------|----------|
| P0 | Hermes | 清除 `.env` git 歷史 | 2026-07-13 |
| P0 | 執行長 | Rotate GCP API Key | 2026-07-13 |
| P0 | 執行長 | Rotate Notion Token | 2026-07-13 |
| P0 | 執行長 | Railway Redeploy | 2026-07-13 |
| P1 | Hermes | 加入 pre-commit secret check | 2026-07-13 |
| P1 | Hermes | dashboard.py 單元測試 | 2026-07-15 |
| P2 | Hermes | snapshot 生成時計算摘要鍵 | 2026-07-15 |
| P2 | 執行長 | 確認手機驗收 OK | 2026-07-13 |

---

*文件建立時間：2026-07-10*
*建立人：Hermes（首席祕書）*
*下次檢討：2026-07-13（週五戰役會議）*
