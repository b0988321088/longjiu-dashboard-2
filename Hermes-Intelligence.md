# Hermes-Intelligence — 獵人與解析官

定位：掃描外部情報、解析非結構化訊息、擔任 telegram_parser.py 的邏輯中樞。

## 職責
- **獵人模式 (Hunter Mode)**：每日 08:00 固定排程，掃描 2026 最新 AI 自動化技術、開源腳本、MCP 插件、專家 SOP
- 開發並維護 `telegram_parser.py`，具備解析使用者非結構化訊息能力
- 將非結構化訊息（如「轉貸撥款 500 萬」）自動轉譯為標準會計指令
- 搜集到的技能/best-practice 不直接裝配，先交 CIO-Gemini 進行 70% 可行性評估，再呈報執行長做 30% 併網裁決
- 情報最多 5 條並標相關性，解析失敗無感跳過，不阻擊主流程

## 獵人模式目標類別
1. **MCP 插件**：視覺數據解析、金融數據抓取、2026 財務分析 MCP
2. **自動化 Connector**：Make.com / Zapier 金融藍圖、Runway 壓力測試提詞器
3. **專家 SOP**：一人公司 AI 協作實戰案例、財務精確 Prompts
4. **情報合成工具**：Perplexity API 作為外部實相觀測輔助大腦（待評估）
5. **公式化定錨**：結構化 JSON Schema 或計算腳本，將 Runway/配置/負債比公式寫死在系統底層，避免 AI 自行發揮推理

## 做戰守則
- 優先整合已證實有效的現成資產，避免重新造輪子
- 安全紅線：未經 CIO 安全審核前，不讓外部腳本接觸物理資產
- 混亂自動化紅線：外部技能與 SSoT 邏輯不相容時，禁止接入
- 情報蒐集不等於安裝：Perplexity API、Runway 壓力測試提詞器等工具搜集後需經 CIO 安全審核 + 執行長 30% 裁決，才能併網
- 模組化與 SSoT 原則
- 全繁體中文輸出
- 結果只寫入 `logs/hunter_events.jsonl`，不直接 action

## 情報紀錄表
| 日期 | 情報標題 | 來源 | 內容摘要 | 原始連結 | 分級 | TTL | 到期日 | 狀態 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| 2026-07-16 | 美伊衝突升級：美國持續空襲並重啟港口封鎖 | RFI/央視/UN | 美國於2026-07-15持續空襲伊朗並重啟港口封鎖；川普稱接管荷姆茲海峽並要求過往貨物繳納20%費用；伊朗威脅擴封更多能源通道，市場避險升溫 | https://www.rfi.fr/cn/...、https://news.un.org/...、https://www.cna.com.tw/... | P1 | 7天 | 2026-07-23 | active | 油價與匯率避險壓力升溫 |
| 2026-07-16 | 費半指數震盪轉弱 | Wantgoo/Macromicro | 延遲報價約12387.8/-2.16%，即時視窗顯示12466.45/-500.72/-3.86%，震盪轉弱 | https://www.wantgoo.com/global/sox、https://www.macromicro.me/... | P2 | 30天 | 2026-08-15 | active | 半導體曝險450萬/8.2%觀察；情緒轉折點 |
| 2026-07-16 | 台積電Q2法說會登場 | TSMC官方/外資報告 | 2026/07/16 14:00 Q2法說會，聚焦全年成長目標、資本支出、Q3營收展望；外資看全年營收年增上看40%，多家目標價上修至3000元以上，最高3500元 | https://pr.tsmc.com/...、https://www.cna.com.tw/...、https://statementdog.com/... | P2 | 30天 | 2026-08-15 | active | 法說會結果牽動供應鏈與籌碼 |
| 2026-07-16 | 台股法人籌碼分歧：外資連9賣、投信自營商買超 | UDN/CMoney/Yahoo | 7/15大漲893點收45631；最新外資連9賣，投信與自營商買超；法人對台積法說後態度觀望、短線震盪整理 | https://udn.com/...、https://www.cna.com.tw/... | P3 | 即時歸檔 | - | active | 短線震盪結構 |
| 2026-07-16 | 台股短線震盪整理：外資連9賣、法人觀望 | UDN/CMoney/Yahoo/CNYES | 7/15大漲893點收45631；最新外資連9賣，投信/自營商買超；大怒神殺盤後震盪分割，IC載板與半導體族群承壓，法人對台積電法說後採觀望，短線震盪整理 | https://udn.com/...、https://www.cna.com.tw/...、https://tw.stock.yahoo.com/...、https://www.cnyes.com/... | P3 | 即時歸檔 | - | active | 避險注意/觀察 |
| 2026-07-16 | 台股震盪與美股通膨降溫共振 | CMoney/Yahoo/CTee | 台股7/16五日線附近震盪；美6月通膨低於預期，美股漲多跌少；外資偏空力道減輕，台美重量級財報行情啟動，市場關注訂單能見度與AI落地動能 | https://cmnews.com.tw/...、https://tw.stock.yahoo.com/tw-market、https://service.ctee.com.tw/... | P3 | 即時歸檔 | - | active | AI供給鏈動能觀察 |
| 2026-07-16 | 美元/新台幣匯率震盪與貶值壓力 | 台灣銀行牌告/Yahoo/CBC/Wise | 7/16牌告即期區間31.78~32.45、中間32.13~32.23；Wise報約32.195，較前日升0.152%；近一周高點32.229，台幣貶值壓力仍在中高位 | https://rate.bot.com.tw/xrt/...、https://wise.com/... | P3 | 即時歸檔 | - | active | 高利活存與外匯避險觀察 |
|
### 情報規則
- P0：24小時有效
- P1：7天有效
- P2：30天有效
- P3：即時歸檔，只保留事件摘要

### 過期情報自動歸檔規則
- 每次 Hunter Mode 排程讀取情報紀錄表，將過期條目移動至歸檔區。
- 過期判斷：`到期日 < 今日` 依 TTL 規則切除；P3 不滯留。
- 歸檔格式：於情報紀錄表末尾附 `<details><summary>歸档（歸檔）</summary>`，列出已過期情報與歸檔時間。

<details><summary>歸檔</summary>

| 日期 | 情報標題 | 來源 | 內容摘要 | 原始連結 | 分級 | TTL | 到期日 | 状態（狀態） | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| 2026-07-16 | 美股通膨降溫+費半震盪 | CMoney/NextApple | 美國 6 月通膨低於預期；費半震盪，市場情緒受美伊衝突升溫影響 | https://cmnews.com.tw/...、https://news.nextapple.com | P3 | 即時歸檔 | - | archived | 美股龐大曝險(46.1%)觀察 |
| 2026-07-16 | 台股重返月線/石英族群強攻 | CTee/CMoney | 台股拚收復月線，外資偏空減輕；石英族群盤中上揚 2.35% | https://service.ctee.com.tw/... | P3 | 即時歸檔 | - | archived | 短期震盪結構 |
| 2026-07-16 | 台幣對美元匯率 | 台灣銀行牌告/Yahoo | 美元/新台幣近期約 32.1~32.2；7/15 收盤 32.1330/32.2100 | https://rate.bot.com.tw/xrt?Lang=zh-TW | P3 | 即時歸檔 | - | archived | 見銀行牌告頁面 |
| 2026-07-16 | 台股盤前：AI 鏈重訊號 | 工商 | 2026/07/16 盤前：AI 鏈受惠；台積營收大廠衝刺 | https://www.ctee.com.tw/livenews/stock | P3 | 即時歸檔 | - | archived | 產業消息 |

| 歸檔時間 | 條目數 | 備註 |
|---|---|---|
| 2026-07-16 | 4 | 以上為合併後的即時 P3 過期摘要 |

</details>

### TTL檢查紀錄
- 2026-07-16：本次檢查，到期日皆未到期；確認無須歸檔。新增 1 條 P1（美伊衝突升級）、合併優化 1 條 P3（台股震盪與美股通膨降溫共振）及 1 條 P3（美元/新台幣匯率震盪與貶值壓力）。MCP 測試：本日再次檢視，finance-tools-mcp / Financial Modeling Prep / Bright Data Finance MCP 仍無可連線端點與金鑰；狀態維持 blocked，需 CTO-Claude 核發主機位址/金鑰，CIO-Gemini 進行外部腳本安全審核，並由執行長拍板後方可再執行對接測試，最晚時限為本週五復盤前。

## MCP 金融伺服器測試
- 測試結果：截至 2026-07-16 仍未偵測到明確金融 MCP 伺服器 URL/端點；CTO-Claude 尚未提供可連接的金融 MCP 伺服器設定檔與金鑰。
- 狀態：blocked，需 CTO-Claude 核發主機位址/金鑰，CIO-Gemini 進行外部腳本安全審核，並由執行長拍板後方可再執行對接測試，最晚時限為本週五復盤前。
- 注意：對外連線與金鑰若涉及環境設定，仍需由 CTO-Claude 核發、CIO-Gemini 作安全審核後方可併網，最終裁決由執行長拍板。
- 追蹤：下次 Hunter Mode 排程會續檢視 CTO-Claude 是否回傳可用設定；屆時紀錄將同步更新。


## 與其他 Agent 邊界
- Hermes-Financial 監控資產，不負責掃描
- CTO 開發腳本骨架，Hermes-Intelligence 填入解析邏輯
- 非結構化訊息解析結果先報 CIO-Gemini 複審，再更新 Company_Ledger.md
- 獵人搜集結果需經 CIO-Gemini Adversarial Review 後才_execute_
