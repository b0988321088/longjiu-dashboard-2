# 龍九控股系統錯誤流程記錄
**期間**：2026-07-14 ~ 2026-07-18  
**狀態**：已記錄，供日後複盤與改進

---

## 1. 日報排版誤判

| 項目 | 說明 |
|------|------|
| 現象 | 手機版日報純 Markdown 表格，無框線/背景色 |
| 用戶指令 | 「這兩種排版不一樣 我要這種排版」— 要 bordered tables with background fill |
| 修正方向 | 改為 HTML/CSS 卡片式佈局：`.table-wrap+table`、白底框線、alternating rows、數字右靠 |
| 教訓 | 用戶說「排版不一樣」時，不要先改內容，先確認是 CSS 還是 Markdown 結構問題 |

---

## 2. Git Push 失敗 → Contents API Fallback

| 項目 | 說明 |
|------|------|
| 現象 | `git push` 逾時/失敗（本地 73 commits vs 遠端 48 commits，歷史不一致） |
| 處理 | 改用 GitHub Contents API 直接上傳檔案，避免 git 歷史問題 |
| 後續 | 待有空再解開本地/遠端歷史不一致的根本問題 |
| 教訓 | Git 歷史不一致時，Contents API 是有效的單檔 workaround |

---

## 3. 配息數字多次修正

| 項目 | 說明 |
|------|------|
| 第1版 | 80,000 TWD/月（用戶主觀值） |
| 第2版 | 72,798 TWD/月（MB 近2個月月均，保守） |
| 第3版 | 維護 72,798，8月驗證後校正 |
| 原因 | MB detail.csv 只有 2 個月數據，7月結算未完成造成 spike |
| 教訓 | 統計要有備註「保守估計，待月底驗證」，不要直接寫入 snapshot 就視為真值 |

---

## 4. Moneybook 路徑與安全

| 項目 | 說明 |
|------|------|
| 問題 | CSV 曾被 commit 進 git，敏感資料暴露風險 |
| 修正 | 移除 CSV + 加入 .gitignore + 使用 `os.environ.get("LOCALAPPDATA")` 動態路徑 |
| 教訓 | 任何腳本都不要硬編碼 `C:/Users/bot`，要用環境變數或相對路徑 |

---

## 5. 本地/遠端 Git 歷史不一致

| 項目 | 說明 |
|------|------|
| 現象 | 本地 73 commits，遠端 48 commits |
| 處理 | 先用 Contents API 單檔上傳 bypass |
| 待解 | 需要清理本地歷史或重建 repo |
| 優先 | 低（不影響日常使用） |

---

## 6. 儀表板數據不一致

| 項目 | 說明 |
|------|------|
| 發現 | `snapshot.json` 頂層正確，但 `page1` 內有舊值（配息 80,000） |
| 修正 | 已統一為 72,798 |
| 驗證 | `moat_report` 與 `snapshot` 定義不同：覆蓋率 vs Runway，需區分說明 |

---

## 7. 決策閘門演化

| 版本 | 說明 |
|------|------|
| v1 | app.py 動態儀表板（本地 Streamlit） |
| v2 | decision_webhook.py（Railway deploy，需要 HTTPS） |
| v3 | decision_poller.py（本地輪詢，有 dependency 問題） |
| **v4** | **Hermes 對話即閘門（文字版）** |
| **v5** | **Hermes 對話 + Telegram 底部鍵盤按鈕** |
| 定案 | 不需要 webhook/poller/雲端，Hermes 直接處理 + 記錄 + Notion |

---

## 8. Out-of-Scope / 延期

| 項目 | 說明 |
|------|------|
| PDF OCR | 20260716145351.pdf，pymupdf 返回 0 字元，暫緩 |
| Finance Hub 5-table | 已完成，0 錯誤 |
| CEO-Gemini 模型評估 | 月底前評估是否導入 OpenAI/Claude |
| Wellness monitoring | 延期 |
| Legal firewall | 設計階段 |

---

## 9. 下次複盤建議

- 檢視此文件是否涵蓋所有重大異常
- 評估 git 歷史重建時機
- 月底配息校準後更新本章第 3 節
