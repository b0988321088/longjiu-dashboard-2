# 龍九控股 Operations Manual v1.0
> 建立日期：2026-07-18 | 維護者：Hermès（首席秘書）
> 原則：系統 > 紀律。所有異常都應在此登記，避免重複踩坑。

---

## 1. 每日自動管線（daily_deploy.py）

### 1.1 執行時序
| 時間 | 動作 | 負責人 |
|------|------|--------|
| 08:00 | Windows 排程觸發 daily_deploy.py | 系統 |
| 08:05 | run_daily.py 產出日報 HTML + changelog | Hermès |
| 08:10 | cio_review.py 靜態規則審查 | CIO |
| 08:12 | gemini_review.py 情報驅動 Buffett/CTO 分析 | CIO-Gemini |
| 08:15 | git push → GitHub Pages | Hermès |
| 08:20 | Telegram 推送日報連結 | Hermès |

### 1.2 真值層級（嚴格遵守）
1. **Moneybook (MB)** — 銀行/信用卡實際流水，唯一真值
2. **snapshot.json** — 系統快照，必須以 MB 校準
3. **Company_Ledger.md** — 參考用，不可與 MB 矛盾
4. **攻擊側截圖（凱基/鉅亨）** — 現值 = exact truth

### 1.3 常見故障與修復 SOP

#### SOP-001：月支出數字異常（暴降/暴升）
**現象**：run_daily.py 產出的月支出與 MB 不一致。  
**根因**：calibrate_sources() 多來源衝突，legacy Company_Ledger 覆寫 MB。  
**修復**：確認 `run_daily.py` 中 `monthly_expense` 只讀 `monthly_expense_mb_override`，移除其他來源校準。

#### SOP-002：儀表板顯示 0 或假數據
**現象**：index.html 顯示基金/保單配息為 0。  
**根因**：`_inject_dashboard()` 讀不到 daily_analysis.json 的 allocation block，fallback 到 0。  
**修復**：確認 daily_analysis.json 包含 `allocation` 區塊，或改從 snapshot 推算。

#### SOP-003：git push timeout / Railway 未更新
**現象**：`git push` 卡住，儀表板未 rebuild。  
**修復**：使用 GitHub Contents API fallback 上傳單檔，或等待 timeout 後重試。長期方案：改用 SSH deploy key。

#### SOP-004：Notion API 400 validation_error
**現象**：`Could not find property with name or id: Name`。  
**根因**：`_create_or_update()` 的 title_prop 偵測只認 `資產名稱/項目/Name`，跳過 `事件名稱/基金名稱`。  
**修復**：確認 `notion_ingest.py` 的 `title_map` 包含所有表的 title property。

#### SOP-005：Notion API SSL handshake timeout
**現象**：`ReadTimeoutError: api.notion.com`。  
**修復**：`notion_ingest.py` 已內建 retry（3 次，指數退避）。若持續失敗，檢查網路或改為手動觸發。

#### SOP-006：Gemini review 產出 generic 內容
**現象**：Buffett/CTO 分析與前日相同，無環境感知。  
**修復**：確認 `gemini_review.py` 有讀取 `daily_analysis.json` 的新聞與市場情報，不使用靜態模板。

### 1.4 禁止事項
- ❌ 禁止手動修改 GitHub Pages 上的 HTML（會被 git push 覆蓋）
- ❌ 禁止在 .env 中明文 expose API key（使用時讀取，用完即棄）
- ❌ 禁止修改 snapshot.json 而不通知 MB 校準

---

## 2. Team Chain v5.4 職能

| 角色 | 模型 | 職責 | 狀態 |
|------|------|------|------|
| Hermès（身體） | Stepfun free | 記錄、SOP 維護、Notion Ingest | ✅ 穩定 |
| CIO（審查） | Gemini 2.5 Flash | 靜態規則 + 情報驅動巴菲特/CTO | ✅ 情報化 |
| CEO（大腦） | Gemini 2.5 Flash | 深度戰略分析 | ⏸️ 暫缓（月底重評估） |
| Notion AI（審計） | — | 週五 17:00 復盤、歷史對照 | ✅ 31 頁底稿 |

---

## 3. 資產管理規則

### 3.1 半導體曝險上限
- 0050/006208 中台積電佔比 >59%，全持倉半導體曝險 >70%
- **動作**：0056 減碼、00878/00713 補位評估中

### 3.2 配息 Relay T+4 規則
- 除息日 + 4 個交易日 = 轉換生效日
- 0050 除息 2026/07/21，縮水 40%（0.6 元 vs 1.0 元）
- 替代方案：00878/009816 進場評估

### 3.3 安全偏好
- 不 expose Notion token / API key
- 截圖（凱基/鉅亨）= 現值 = authoritative
- 零散推送 = 禁止，一次完整交付

---

## 4. 聯絡與通訊

- Hermès 故障 = 檢查 ops_logs + daily_review_queue
- 緊急聯繫 = Telegram DM
- 檔案路徑 = C:/Users/bot/Desktop/龍九系統
