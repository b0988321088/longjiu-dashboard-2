# Google Sheets 勞健保/薪資表 → 龍九儀表板現金流預估整合：計畫（待核准）

**狀態：📋 計畫（2026-09-15 18:00 產出，未實作；程式碼未動）**
**背景（9/15 待辦 ①）**：勞健保/薪資表目前在 Google Sheets 維護，儀表板現金流預估仍靠人工填 snapshot 欄位；本計畫盤點整合點與工作量，等使用者核准才動工。

---

## 一、現況盤點（repo 實查，非印象）

| 現有來源 | 位置 | 現值 | 問題 |
|---|---|---|---|
| 台電月薪 | `snapshot.monthly_salary`＝`salary` | 42,560 | 只有單一數字，無勞健保/實發明細 |
| 薪資歷史 | `snapshot.salary_records` | 2026-08: 39,727（8/6）／2026-09: 42,560（9/4） | 手動維護，僅「金額+入帳日」 |
| 獎金/第二筆 | `snapshot.second_salary` | 39,121 | 口徑未標（常態/非常態） |
| 儀表板替換 | `build_dashboard.py:349-351` | `tpl.replace("39,727", monthly_salary)` | 只換金額，不含扣繳明細 |
| 行事曆薪資入帳 | `calendar_sync.py:55-57` | **寫死 `$39,727`** | 9/4 已調薪 42,560 → **兩處不同步（既有缺口）** |
| 日報被動月收 | `complete_daily_report.py:290` | 寫死 `160,100 / 82,265 / 69,044` | 已過期快照值 |

> 2026-09-15 執行註記：`complete_daily_report.py` 與 `build_marriage_impact.py` 全 repo／cron 零引用，已於今日移入 `.archive/`（停用可復原）；本列僅存歷史診斷紀錄。
| 現金流腳本 | `cashflow_analysis.py`、`lj.py` | 讀 `asset_diff_history.json` | 與薪資表無關（月現金趨勢用） |
| Google 憑證 | `~/AppData/Local/hermes/google_token.json` | scopes＝**calendar + gmail.modify** | ⚠️ **無 Sheets 權限**（見 §三前置） |

**結論**：repo **沒有任何** gspread/Sheets API 讀取程式（`grep sheets.googleapis|gspread`＝0 命中），此整合＝新建，不是接線。

## 二、建議資料流（單一真值，不覆寫裁示口徑）

```
Google Sheet「勞健保/薪資表」
   └─(每月 1 次 or 入帳日 +1)─► data/salary_sheet.json         ← 新檔，機器寫
                                   ├─► snapshot.salary_records  ← 明細同步（保留 amount/date/note schema）
                                   ├─► calendar_sync.py         ← 修掉寫死 39,727，改讀單一來源
                                   ├─► build_dashboard.py:349   ← 薪資卡/公式行（改讀實發＋扣繳）
                                   └─► build_ceo_dashboard.py   ← 「未來 14 天里程碑」自動列薪資入帳日
```

**建議欄位（Sheets → JSON）**：`月份 / 應發(本薪+加給) / 勞保自付 / 健保自付 / 勞退自提 / 扣繳 / 實發 / 入帳日 / 備註`
- `snapshot.monthly_salary`（42,560）**不自動覆寫**：調薪屬裁示項（9/4 由使用者確認），腳本只同步明細與歷史。
- 獎金/年終一律標「非常態」，不進 `monthly_income`（沿用專案收入處理原則）。
- PII：只落地金額欄位，不落地身分證/地址。

## 三、前置（需使用者本人動作，1 次）

- **OAuth 授權擴充**：現有 token 只涵蓋 calendar＋gmail → 需重跑 `reauth_google.py`（新增 `spreadsheets.readonly`），瀏覽器同意一次即可。
- 提供 **Sheet ID + 分頁名**（或授權我以 Drive 搜尋定位）。
- 替代方案（零授權）：由使用者每月匯出 CSV 到 `data/`，我讀檔同步——自動化程度較低，若不想動 OAuth 可走這條。

## 四、工作量與切分（估 ~3.5h，不含等授權）

| 段 | 內容 | 估時 | 產出 |
|---|---|---|---|
| P1 | `sync_salary_sheet.py`（抓取+dry-run 比對，不寫 snapshot） | ~1h | data/salary_sheet.json |
| P2 | 3 下游改讀單一來源（`calendar_sync`／`build_dashboard`／`build_ceo_dashboard`），順手修 `calendar_sync.py:57` 寫死 39,727 | ~1.5h | 程式 diff |
| P3 | 驗證：四源一致比對、JSON round-trip、入帳日對帳、頁面渲染比對 | ~1h | 驗證紀錄 |
| — | 推送：程式檔（py）→ CIO 審查 + `auto_push.py`（**不得走 `[cioreviewed]` 標籤通道**） | — | RECORD |

**影響的下游報表**：主儀表板（薪資卡/現金流入）、再平衡儀表板（現金流段）、日報第 2 章現金流、CEO 儀表板里程碑、行事曆（薪資入帳提醒）。
**風險**：改到 `build_dashboard` 的替換鍵會影響既有 `data-k` 注入路徑（曾發生「模板寫死值殘留」事故）→ P3 必須做「舊字串 0 命中」驗證。

## 五、需要裁示

1. 走 OAuth（自動）還是 CSV（手動）？
2. `snapshot.monthly_salary` 是否維持「僅使用者確認才改」？（建議：維持）
3. 是否一併修 `calendar_sync.py:57` 寫死薪資金額（同一類缺口，建議一起）？
