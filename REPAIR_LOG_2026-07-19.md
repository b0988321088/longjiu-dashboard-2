# 錯誤與修復紀錄 2026-07-19

## 問題 1：Telegram 只在讀專案 .env，沒讀 Hermes .env
- 現象：`asset_diff_monitor.py` 一直顯示「TELEGRAM_BOT_TOKEN / CHAT_ID 未設定」
- 根因：專案 `.env` 只有 `TG_CHAT_ID`，沒有 `TELEGRAM_BOT_TOKEN`；真實憑證在 `C:/Users/bot/AppData/Local/hermes/.env`
- 修復：在 `asset_diff_monitor.py` 增加 fallback，當專案 `.env` 讀不到時自動讀取 `C:/Users/bot/AppData/Local/hermes/.env`
- 狀態：✅ 已修復，`Telegram 200`

## 問題 2：只傳文字訊息，沒有附上 HTML / DOCX 檔案
- 現象：Telegram 只收到摘要文字，沒有看到網頁版與 Word 檔
- 修復：在 `asset_diff_monitor.py` 增加 `send_telegram_document()`，產出檔案後一併上傳 `asset_diff_YYYY-MM-DD.html` 與 `asset_diff_YYYY-MM-DD.docx`
- 狀態：✅ 已修復，待驗證

## 問題 3：現金部位與資產結構多個版本並存
- 現象：snapshot 內出現多組舊真值（6,890,791 / 5,271,753 / 3,071,343）
- 修復：統一為 `real_liquid_assets = 3,853,985`（Moneybook 20260718 正數合計）
- 狀態：✅ 已修正，不可再回滾

## 問題 4：保單總帳面 11,791,280 與明細加總不符
- 現象：安聯A+B+第一金FL65 明細加總 9,802,995，但 `insurance_total = 11,791,280`
- 結論：snapshot 的 `insurance_total` 已含配息，為 canonical 值
- 狀態：✅ 不動，加註「含配息」

## 問題 5：資產佔比分母包含不動產
- 修復：分母改為 `total_assets - real_estate_value`，證券/保單/基金/現金 = 100%
- 狀態：✅ 已修正

## 問題 6：資產變化表格式未經確認改來改去
- 修復：寫入 `longjiu-asset-reporting` skill，禁止未確認先改
- 狀態：✅ 已建立 skill
