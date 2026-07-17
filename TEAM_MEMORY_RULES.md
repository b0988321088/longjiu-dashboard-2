# 團隊記憶寫入規範

生效：2026-07-16

## 核心鐵則

所有代理（Hermes / Gemini / Claude / 未來 GPT）在**任務完成後**必須執行：

```
memory(action="add", target="memory", content="[agent][YYYY-MM-DD][task] result")
```

範例：
```
[Hermes][2026-07-16][日報重啟] 檔案已推 main，SHA=f8644ba
[Gemini][2026-07-16][審核] 真值校正通過：信用卡38K、國泰專戶50萬
[Claude][2026-07-16][部署] Railway Pages rebuild 完成
```

## 分層讀取

| 場景 | 觸發時機 | 讀取內容 |
|------|----------|----------|
| 日報產出前 | cron 08:50 | 過去 7 天投資決策記錄 |
| Buffett/CTO 分析 | 每次產出前 | 歷史市場判斷準確率 |
| 異常處理 | error detected | 過去錯誤解法 |
| 每日晨會 | 09:00 | 昨日任務完成度 + 今日優先 |

## 規則

1. **不重複**：寫入前先 `fact_store(action='search')` 或 `memory` 確認未存在
2. **可追蹤**：每條必須有 agent + date + task + result
3. **不洩密**：不含 API key / token / 密碼
4. **不限量**：memory store 自動管理容量，寫入不由 agent 把關
