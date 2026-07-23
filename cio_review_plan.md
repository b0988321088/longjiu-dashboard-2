# 情報系統改善方案 — 供 CIO-Gemini 審查

## 問題
情報產出鏈過長、資料源不一致，導致每日重複錯誤：
1. 曝險數據讀 snapshot 穿透值（舊）而非 holdings 表（即時）
2. market_intel 的 tw_index=0（compile_intel 從舊 snapshot 讀市場數據）
3. daily_analysis.json → compile_intel → snapshot → run_daily 四層傳遞，每層都可能出錯

## 改善方案

### ① 曝險即時計算 ✅ 已套用
- from: `snapshot.penetration.actual_twd.台股市值型成長`（舊值 101 萬）
- to: `holdings 表 × App 股價即時計算`（正確值 242 萬）
- 風險：股價字典需手動更新（可後續改 TWSE API 自動抓）

### ② market_intel 直接寫入 ⏸️ 未完成
- from: daily_intel → daily_analysis.json → compile_intel → market_intel（繞路）
- to: daily_intel 產出情報後直接 INSERT market_intel 表（唯一源頭）
- 好處：compile_intel 就不再需要讀 snapshot 市場數據
- 風險：INSERT OR REPLACE 可能覆蓋舊資料，需確認 timestamp 為最新

### ③ compile_intel 簡化 ⏸️ 未完成
- 移除 snapshot 市場數據讀取
- 只保留 hunter 訊號彙整 + market_intel 補充寫入

### ④ Gemini 審查注入日報 ✅ 已套用
- deploy 時 gemini_review 結果自動寫入日報尾部
- 含評分、摘要、待改善事項

## 預期效益
- 曝險不再出現 101 萬 vs 242 萬的誤差
- 加權指數不再顯示 0
- 日報尾端可看到 CIO 審查意見

---

**請審查：以上方案有無問題或補充？**
