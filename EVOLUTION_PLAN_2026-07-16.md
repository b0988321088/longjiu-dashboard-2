# 龍九系統進化計劃
**日期**：2026-07-16  
**目標**：讓 Hermes 具備自動產出+推送日報與儀表板的能力，不再依賴對話中手動組合。

---

## 1. 單一 CLI 入口（優先）
**檔案**：`run_daily.py`  
**功能**：一鍵產出
- 日報 `.html`（五大章節 + 真值校準）
- 靜態儀表板 `index.html`（市場情報 + Hunter 情報）
- 差異說明 `.md`（相對於昨天的變動）

**完成條件**：
```bash
python run_daily.py
# 產出：
# - daily_report_v2_{date}.html
# - index.html
# - changelog_{date}.md
```

## 2. 推送前自動檢查清單
**檔案**：`daily_checklist.py`  
**檢查項目**：
- [ ] 五大章節完整（1/5 財富生命線、2/5 戰略異常、3/5 保單接力、4/5 流動性、5/5 決戰日檢核）
- [ ] Relay 為三站制（第一站摩根、第二站安聯收益+M&G、第三站 AI+PIMCO+貝萊德）
- [ ] 四大信用卡列管 + 兩大房貸帳戶
- [ ] 保單現值對齊 `snapshot.json`（安聯 A+B：7,881,584 / 第一金：1,994,698 / 合計：9,876,282）
- [ ] 配息 SOP wording 正確（hold 現金，T+4 最晚申請日才轉換）
- [ ] 無簡體字
- [ ] 無 Railway / dashboard.py / 旗艦版連結
- [ ] Market 情報附可信度標記
- [ ] 巴菲特分析使用確認過的真值
- [ ] 交付格式為「日報連結 + 靜態儀表板連結」

**完成條件**：檢查失敗就中斷，不推送。

## 3. 三源真值自動校準
**讀取來源**：
1. `snapshot.json`（資產負債/月收支/保單現值）
2. `DAILY_REPORT_PIPELINE_RULE.md`（relay 站數/配息數字/支出拆解）
3. `Company_Ledger.md`（銀行餘額/行事曆/配息明細）

**邏輯**：
- 讀取三個來源後交叉比對
- 任一不一致就寫入 `daily_review_queue_{date}.json` 標記為 PENDING
- PENDING 不允許產出日報，必須人類確認後才能解除

## 4. Market 情報可信度評分
**檔案**：`market_intel.py`  
**規則**：
- web_search 結果一致 → ✅ 可信度 90%+，直接寫入
- web_search 結果矛盾 → ⚠️ 可信度 50%，標記「待補齊」
- 無來源或單一匿名來源 → ❌ 可信度 0%，不顯示
- Hunter 情報自動納入：讀取 `hunter_logs/` 最新檔案，解析 P1 訊號

## 5. 自動推送腳本
**檔案**：`daily_deploy.py`  
**功能**：
- 呼叫 `run_daily.py` 產出檔案
- 呼叫 `daily_checklist.py` 檢查
- 呼叫 GitHub Contents API 推送 `daily_report_v2_{date}.html` + `index.html`
- 推送失敗自動 fallback 到 Contents API
- 完成後推送兩個連結到 Telegram

---

## 待辦事項（今日內）
- [ ] 建立 `run_daily.py` 雛形
- [ ] 建立 `daily_checklist.py` 10 項檢查
- [ ] 建立 `market_intel.py` 可信度評分
- [ ] 建立 `daily_deploy.py` 自動推送
- [ ] 測試完整流程 `python run_daily.py && python daily_deploy.py`

---

## 真值錨定（2026-07-16）
- 總資產：50,689,930 TWD
- 保單現值：9,876,282（安聯 A+B：7,881,584 / 第一金 FJ33：1,994,698）
- 本月配息：69,044（安聯 55,451 + 第一金 13,593）
- Relay 三站：摩根 FJ33 → 安聯收益+M&G → AI+PIMCO+貝萊德 A10
- 月收入：218,102 / 月支出：141,958 / 工作期盈餘：+76,144
- 7/17 國泰轉貸面簽/對保（僅剩 1 天）
- 0050 配息 0.6 元縮水 4 成，7/21 除息
