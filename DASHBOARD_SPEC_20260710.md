# 龍九控股 Dashboard 規格書 + 修正紀錄
## Version: 2026-07-10 V5.0.0

---

## 一、今日修正紀錄

| 時間 | 問題 | 修正內容 | 檔案 |
|------|------|----------|------|
| 22:07 | 分頁切換 TypeError: list indices must be integers or slices, not builtin_function_or_method | `tabs.index` method → 改用整數索引 | dashboard.py:124 |
| 22:07 | Page3 保單現值 / 總成本顯示 0.0 | 加入 `yield_performance` fallback 聚合邏輯 | dashboard.py:390 區段 |
| 22:07 | 手機 sidebar 字體白底白字 | 全域 `!important` contrast 覆寫 + 強制 `display:block` | dashboard.py CSS |
| 22:08 | 甜甜圈圖表在手機寬度被擠掉 | 砍掉 `st.columns([1,1])`→ 改垂直堆疊 `use_container_width=True` | dashboard.py Page1 |
| 22:08 | sidebar / 按鈕對比不足 | `.stButton>button` 加 `background:#1e293b` + sidebar 全域白字 | dashboard.py CSS |
| 22:09 | Railway build cache 舊版 | 刪除舊 snapshot `framework_snapshot_20260709.json` | GitHub |
| 22:10 | Git 歷史洩漏 `.env` | GitHub security 頁面手動 unblock | GitHub UI |
| 22:11 | Page2 資產配置分析數據錯誤 | 重新設計 4-bucket 框架：證券/保單/基金/現金 | framework_snapshot_2026-07-10.json |
| 22:12 | Page3 總報酬率 +0.00% 錯誤 | simple average → value-weighted avg (`with_dividend_pct` weighted by value) | dashboard.py Page3 |
| 22:13 | Page4 安聯收益成長被歸類為銀行帳戶 | 分割銀行活存帳戶 / 保單投資帳戶 + 加入流動水位檢查 | dashboard.py Page4 |

### 套件版本不一致（待修）
- `requirements.txt`: pandas 2.2.3 / numpy 1.26.4 / streamlit 1.39.0
- 本地實際: pandas 3.0.3 / numpy 2.4.6 / streamlit 1.59.1

### 未完成項目
- Page2 Buffett perspective / 穿透式產業曝險 / concentration / leverage 仍為 `null`，待 `full_monitor.py` 補齊
- Page4 近期應付 0 TWD：`full_monitor.py` 上游未寫入
- 儀表板數字目前寫死在 snapshot，應改為 parser 從 Telegram 日報動態提取

---

## 二、五頁儀表板規格

### Page 1｜財富生命線
**對應日報**：Telegram 五張日報之一（第一則）

| KPI | 單位 | 說明 |
|-----|------|------|
| Runway | 月 | 總資產 / 月支出，來源 `page1.runway_months` |
| 資產負債比 | % | 總負債 / 總資產 |
| 工作期月盈餘 | TWD | 薪水 + 差旅 - 支出 |
| 退休後月盈餘 | TWD | 不含薪水的盈餘 |
| 本月收入 | TWD | `actual_cash_flow.income` 總和 |
| 本月支出 | TWD | `actual_cash_flow.expense` 總和 |
| 本月盈餘 | TWD | 收入 - 支出 |

**圖表**：
- 甜甜圈 1：本月收入來源（房租 / 配息 / 薪水）
- 甜甜圈 2：本月支出組成（房貸 / 消費 / 房租）
- 附：收入明細 accordion、支出明細 accordion

---

### Page 2｜戰略異常中心
**對應日報**：Telegram 五張日報之二（第二則）

**資產配置分析（4 部位穿透）**：
- 證券（台股 + 美股）：yfinance 持倉市值加總
- 保單：`page3.policies` 現值加總
- 基金：待測（鉅亨/銀行APP）
- 現金/銀行：`page4.accounts` 活存加總

**穿透分析核心邏輯**：
證券 ETF、保單、基金都是一籃子成分股。必須查詢穿透到**台股 / 美股 / 債券**的實際曝險比例，才能對應 40/35/25 目標。不是只看證券名稱的第一層。

**目標比例**：
| 部位 | 目標 |
|------|------|
| 證券（台股+美股） | 40-45% |
| 保單 | 20-25% |
| 基金 | 15-20% |
| 現金/銀行 | 10-15% |

**其他區塊**：
- 紅區警示（嚴重溢價 / 槓桿過度）
  - 0056 +40.9% → 減碼
  - 0050 +35.1% → 減碼
  - 006208 +28.5%
  - 009816 +22.3%
  - 00878 +18.7%
- 巴菲特視角：`buffett_decision` + `gemini_analysis`
- 穿透式產業曝險
- Concentration / Leverage

---

### Page 3｜保單接力引擎
**對應日報**：日報第三則 + 保單專頁

| KPI | 單位 | 計算方式 |
|-----|------|----------|
| 保單現值 | TWD | `policies[*].value` 加總 |
| 總成本 | TWD | `policies[*].cost` 加總 |
| 總報酬率 | % | **value-weighted avg of `with_dividend_pct`** |
| 本月配息 | TWD | `monthly_dividend` |

**圖表**：
- 甜甜圈：各保單現值佔比（安聯A / 安聯B / 第一金 / ...）
- 三站接力時間軸（T+2 / T+4 / 月底站）
  - 安聯A/B → M&G 用 T+4
  - 第一金 → 安聯收益成長用 T+2

**70/30 裁決按鈕**：
- 保單現值 / 總成本 / 含息報酬率 計算邏輯必須與日報一致

---

### Page 4｜流動性調度（重點）
**對應日報**：日報第四則

**主要功能**：**流動水位檢查**，不是純列餘額

| 銀行 | 功能 | 最低要求 | 檢查邏輯 |
|------|------|----------|----------|
| 台新 Richart | 主帳戶（調度中心） | 3個月總支出 | 431,874 TWD |
| 玉山銀行 | 房貸扣款 + LINE Pay生活消費 | 3個月房貸 + 3個月LINE Pay | 328,374 TWD |
| 永豐銀行 | 一般消費卡 | 2個月卡片消費緩衝 | 10,000 TWD |
| 台北富邦 | 富邦J卡 + MOMO卡消費 | 2個月卡片消費緩衝 | 16,000 TWD |
| 星展銀行 | 房貸尾數 | 30,000（最低警示線） | refill_alert |
| 國泰活存 | 轉貸專戶 | 2個月支出緩衝 | ~287,916 TWD |
| 現金儲備 | 備用 | 50,000 | 最低標準 |

**圖表**：
- 甜甜圈：帳戶/保單餘額分佈

**警示**：
- 低餘額警示：`refill_alert.low_balance_account` → 建議調度額度
- 近期應付（30天）：表格 + 剩餘天數（待 full_monitor 補齊）

**租賃監控**：
- 大義街 1F：24,000 TWD / 月，到期剩餘天數
- 洲際W 18F-6：33,000 TWD / 月
- 大義街 2-3F：23,100 TWD / 月

---

### Page 5｜戰術任務
**對應日報**：日報第五則

| 區塊 | 內容 |
|------|------|
| P0 任務 | 5 項高優先級行動 |
| 生活行事曆 | 7/10–7/14 行程 + 10月胡志明+洲際W |
| 繳款日程 | 近期應付摘要 |
| 一語煞尾 | Gemini 快速結論 |
| Notion 導航 | 雙資料庫入口（待權限更新後啟用） |

---

## 三、每日例行作業

| 時間 | 作業 |
|------|------|
| 08:00 | Google Calendar 同步未來 7 天行程 |
| 08:50 | Telegram 推播五張日報 + 儀表板連結 |
| 17:00 | 工作總結（今日完成 / 待改進 / 明日待辦 / 近期重要節點） |
| 備註 | 若明日有重要行程、付款截止日或請假，17:00 總結必須特別標註提醒 |

## 四、資料流規範

```
full_monitor.py
    ├──  Telegram 五張日報（唯一真值）
    └── framework_snapshot_YYYY-MM-DD.json（結構化備援）

review_check.py  ← 每次上傳強制檢查
    ├── KPI 範圍
    ├── 結構完整性
    └── 數值合理性

dashboard.py（Railway）
    ├── 框架：CSS + 導航 + 圖表模板
    ├── 數值：目前從 snapshot 讀取
    └── 分析：巴菲特視角 / 穿透分析（待補）

telegram_parser.py（下週）
    └── 從 Telegram 抓最新消息 → regex 提取數值
        減少 snapshot 依賴
```

---

## 四、儀表板撰寫規範

### 編碼規則
- 全部繁體中文，無英文標籤
- 金額單位 **TWD**，比率單位 **%**，月份單位 **月**
- 函數：`fmt_twd(n)` = `"{:,.0f} TWD".format(n)`

### CSS 規範
- 全域 `!important` dark mode
- sidebar 文字 `color:#ffffff !important`
- KPI light 卡片背景上的文字 `color:#0f172a !important`
- 按鈕 `background:#1e293b !important; color:#ffffff !important`
- 手機版按鈕 color=primary = `#2563eb`

### 計算規範
- **含息報酬率** = value-weighted avg of `with_dividend_pct`（不是 simple avg）
- **Runway** = 總資產 / 月支出
- 扣款規則：依 `full_monitor.py` 的 `actual_cash_flow` 為準

### Review Gate 規範
每次推送儀表板前自動檢查：
- ❌ 保單現值 = 0 → 中斷
- ❌ Runway = None → 中斷
- ⚠️ 月底配息 = 0 → 警告（可能尚未到帳）
- ❌ 必要 key 缺失 → 中斷

---

## 五、已知待補項目（下週）

| 項目 | 負責模組 | 原因 |
|------|----------|------|
| Page2 穿透分析數據 | full_monitor.py | 證券/基金市值尚未寫入 |
| Page2 Buffett 視角 | full_monitor.py | `buffett_decision` / `gemini_analysis` 為 null |
| Page4 近期應付 | full_monitor.py | 上游未寫入信用卡/貸款金額 |
| 近期應付剩餘天數 | full_monitor.py | `days_left` 欄位缺失 |
| dashboard 數字動態化 | telegram_parser.py | 目前硬編碼在 snapshot |
| requirements.txt 版本對齊 | full_monitor | local vs remote 不一致 |
| .env git 歷史清理 | review_check.py + full_monitor | rotate GCP/Notion token |

---

## 六、戰役決策紀錄

### 2026-07-10 關鍵決定
1. dashboard.py v5.0.0 乾淨重寫，消除 patch 殘留
2. Review Gate 強制每次上傳檢查
3. 手機版儀表板分頁切換修復 + 對比度強化
4. Page2 資產配置改為四部位：證券 / 保單 / 基金 / 現金
5. Page3 含息報酬率改為 value-weighted avg
6. Page4 改為流動水位檢查，按銀行功能性逐筆比對
7. 儀表板架構方向：靜態框架 + 日報動態數值 + Review Gate

---

 Document generated: 2026-07-10 by Hermes Agent
 End of specification


## 七、P1 資產化轉向任務（存證）

### P1-TASK-001：telegram_parser.py
- **目標**：從 Telegram 日報自動解析數值，消除手動維護 snapshot 的認知摩擦
- **輸入**：Telegram 五張日報文字
- **輸出**：結構化 JSON，對應 snapshot 格式
- **意義**：這是從「靜態展示台」進化為「實時偵察機」的關鍵一步
- **Deadline**：2026-07-17（下週五前）
- **狀態**：⏳ 待開發


### 負債明細（2026-07-11 確認）
- 星展一般房貸：4,800,000 TWD（本月結清）
- 星展理財型房貸：額度 5,000,000 / 已動用 4,000,000 / 月息 10,000（隨後轉貸國泰）
- 永豐房貸：6,000,000 TWD
- 永豐週轉金：7,000,000 TWD
| 凱基質押 | 1,000,000 TWD |
| 保單借貸 | 4,000,000 TWD |
| **總負債** | **26,800,000 TWD** |
| **負債比** | **48.3%** |
