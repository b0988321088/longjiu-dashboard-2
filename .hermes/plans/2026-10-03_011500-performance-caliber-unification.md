# 投資績效口徑統一（A 案）施工計畫

> 對應 INC-282（月報「常態績效」以淨資產變化冒充投資績效）。本計畫**只定義怎麼做，不動任何程式**。
> 使用者裁示（2026-10-03）：先查差異 → 定義唯一口徑 → 指定唯一真值 → 改報表讀取 → 加一致性驗證 → 跑完整回歸 → 才考慮上線。

**Goal：** 讓「投資績效」全系統只有**一個定義、一個真值、一個輸出**；同月份在任何報表出現不同值即 FAIL。

**Architecture：** 抽出 `performance_core.py` 為唯一計算層（canonical accessor），`build_mtd_report` / `build_investment_performance` / `monthly_report` / 動態月報全部讀它；再加一支跨產物一致性閘門。

**前提（不可動）：** 不改歷史真值、不改 9 月數字、不動線上版本（本階段只寫計畫）。

---

## 0. 現況：4 個呈現點、3 個值（2026-10-03 唯讀診斷，已查證）

| 呈現點 | 產生者 | 9 月投資績效 | 判定 |
|---|---|---|---|
| 彙整月報 `monthly_report_2026-09.html` | `monthly_report.py:121-129` | **−2,131,153** | ✗ 口徑錯（＝淨資產變化，非績效） |
| 動態月報 `dynamic_monthly_review_2026-09.html` | cron「龍七月報」LLM 直寫 HTML | **+3,404** | ✗ 過期（配息用舊值 167,675） |
| `mtd_performance.html` / `mtd_data.json` | `build_mtd_report.py` | **+6,315** | ✓ |
| `investment_performance.html` ＋ TG 投資績效月報 | `build_investment_performance.py` | **+6,315** | ✓ |

### 0-1 `+3,404` vs `+6,315` 的 2,911 —— 已歸因，**不是公式差異**

- `mtd_data.json` 2026-09：`mkt −122,271 ＋ div 170,586 － interest 42,000 ＝ +6,315`
- 動態月報 2026-09：`mkt −122,271 ＋ div 167,675 － interest 42,000 ＝ +3,404`
- 差額 100% 落在**保單配息**：mtd `97,072` vs 動態月報 `94,161`
  - `94,161 ＝ 安聯撥回 71,869 ＋ 第一金FJ33 9,287 ＋ 第一金IDXX 13,005`
  - mtd 用 `第一金IDXX 15,916`（現行真值）→ 差 `15,916 − 13,005 ＝ 2,911` ✔
- 根因＝**時點差**：動態月報產出於 10/1 18:30；同日深夜兩次配息歸屬校正
  （基準日制 IDXX +15,916／A 制 FA81 −13,005，9 月實收 167,675 → 183,591 → **170,586**）
  **未觸發下游報表重產**。
- ⇒ 結論：兩條程式路徑（mtd、investment_performance）**公式其實已經一致**；壞掉的是
  ①彙整月報另算一套錯口徑 ②LLM 直寫的動態月報會停在舊真值。**缺的是「唯一真值 + 重產觸發 + 閘門」。**

### 0-2 配息是否實收口徑不同？——不是。利息是否重複扣除？——不是。日期切點差異？——不是。

- 配息：mtd（`build_mtd_report.py:185-201`，`bip.classify_dividend`）與月報（`dividend_caliber.bucket_of`）
  對 21 筆 9 月配息**分類結果完全相同**（僅標籤命名不同：`ins/保單`）；差異純粹來自**取值的時間點**。
- 利息：兩邊都只扣校正檔 `利息: {房貸 28,000, 保單借貸 14,000}` ＝ 42,000，**無重複扣除**。
- 切點：兩邊都是 8/31 收盤 → 9/30（校正檔 `市值變化`），同基準。

### 0-3 可用輸入（已確認為單一來源）

| 項目 | 來源 | 9 月值 |
|---|---|---|
| 市值變化／新增投入／估值更新 | `investment_performance_adjust.json["2026-09"]` | −122,271（股票 +119,040／基金 −125,976／保單 −115,335） |
| 配息實收 | `snapshot.dividend_records["2026-09"]`（分類 `dividend_caliber.bucket_of`） | 170,586 |
| 投資利息 | 校正檔 `利息` | 42,000（房貸 28,000＋保單借貸 14,000） |
| 申購手續費 | 校正檔 `手續費` | `{}` → 0（**無月度手續費資料**，須明示不得靜默） |
| 專案收入 | 校正檔／`snapshot.project_income_records` | 0 |

---

## 1. 唯一公式（canonical，先定義再施工）

```
perf_net(ym) = Σ_class 市值變化(校正檔)
             + Σ_class 配息實收(snapshot.dividend_records[ym] → bucket_of)
             − Σ 投資利息(校正檔)
             − Σ 申購手續費(校正檔)
```

**明確排除（不得混入）**：薪資、租金、生活消費、借款本金流（撥款／清償）、資金過境（指定款移轉）、
淨資產變化、專案收入（另列，不進 perf_net）。

**適用範圍**：只對「已結束月份」定義。當月（未結束）沿用 mtd 現行「週=帳面、月=扣息」雙口徑，
一致性閘門僅約束**已結束月份**（避免每天假紅燈）。

---

## 2. 施工步驟（任務顆粒度，逐步可驗收）

### Task 1：抽出 canonical 計算層 `performance_core.py`
- 建立 `performance_core.py`，`monthly_performance(ym) -> {mkt, div, interest, fee, net, basis, reliable, missing[]}`
- 移植來源：以 `build_mtd_report.py` 現行 `month_series()`（已是 +6,315、含 basis 與 校正檔覆蓋邏輯）為藍本，
  **不重新發明**；配息一律走 `dividend_caliber.bucket_of`
- 缺件處理（依 `no-hardcode-mandate`）：手續費缺 → 回 `fee=0` 但同時回 `missing=["手續費"]`；
  利息缺 → **raise 或回 `missing`**，禁 `or 0` 偽裝真值
- 驗收：`python -c "import performance_core as p; print(p.monthly_performance('2026-09'))"` → `net == 6315`

### Task 2：兩個產生器改讀 canonical
- `build_mtd_report.py`：刪除自家 `month_series` 計算，改呼叫 `performance_core`
- `build_investment_performance.py`：同上（`grand/interest/fee/perf` 全部由 core 供）
- 驗收：重產後 `mtd_data.json` 與 `investment_performance.html` 的 9 月 net **逐位元相同且仍為 +6,315**
  （`git diff --stat` 應為空或僅格式差異；若數字變動＝移植不忠，退回）

### Task 3：`monthly_report.py` **只改口徑、不改真值**（本卡主體）
- **移除** `_net_chg`（`:122-124`）在「📈 投資績效」卡的位置
- 新「📈 投資績效」卡：讀 `performance_core.monthly_performance(ym)`，
  列 市值變化／配息／利息／手續費／**淨額**；未結算月份顯示「⏳ 當月尚未結算，見績效頁」
- `_net_chg − 專案收入` 若保留 → **正名**「常態淨資產變化（扣專案）」，
  說明欄改真公式 `期末淨資產 − 期初淨資產 − 專案收入`，並加註「此非投資報酬，含融資時點差」
- ⚠️ 不得再出現「說明：薪水+配息+租金 − 消費 − 利息 − 手續費」這句話（該橋接不執行、資料也不足）
- 驗收：重產 `monthly_report_2026-09.html` → 卡片內出現 `+6,315`；全檔 `grep -c "常態績效"` == 0 或僅出現在正名後欄位；
  `grep "薪水+配息+租金"` == 0

### Task 4：動態月報（cron「龍七月報」）——LLM 直寫，只能約束＋兜底
- cron prompt 加硬規則：「投資績效一律**引用** `performance_core` 輸出（腳本印出即貼），
  不得自行以 snapshot 現算；配息口徑修正後必須重產本報告」
- 並在 Task 5 閘門兜底（抓 stale）

### Task 5：一致性閘門 `check_performance_consistency.py`（本卡核心防線）
- 讀四產物同月 `net`：`mtd_data.json`／`investment_performance.html`／`monthly_report_*.html`／
  `dynamic_monthly_review_*.html`（以 regex 抽數字，取最新一份已結束月份）
- **同月差異必須 = 0**；≠0 → 印出四個值＋歸因（配息/利息/mkt）→ `exit 1`
- 掛載：`regenerate_report.py` 產出後＋獨立 cron；僅約束已結束月份
- 已知邊界：LLM 直寫 HTML 的抽取是 regex，若文案改寫可能抽不到 → 抽不到一律列 FAIL（fail-closed）

### Task 6：完整回歸
1. 三份報表全部重產（mtd / investment_performance / monthly_report；動態月報需重跑 cron prompt）
2. `check_performance_consistency.py` → 0 差異
3. 既有全套閘門（`check_dashboard_sync`／`check_dividend_caliber`／`check_thresholds`）**基準線比對**：
   `git stash` 證明無新增 FAIL（既有 FAIL 不混入本批）
4. 8 月回歸：8 月 net 應為 **+428,802**，四處一致

### Task 7：上線
- CIO 真實審查（0 required fixes）→ 程式／資料分開 commit → `cio_approve` / `auto_record` → `auto_push`
- 上線後跑一致性閘門＋`check_dashboard_sync --post-push`

---

## 3. 檔案清單

**新增**
- `performance_core.py`（canonical 計算層）
- `check_performance_consistency.py`（跨產物一致性閘門）
- `tools/verify_performance_core.py`（唯讀驗證器，含負向對照）

**修改**
- `build_mtd_report.py`（刪自家計算，改讀 core）
- `build_investment_performance.py`（同上）
- `monthly_report.py:121-129、184-191`（改口徑，不動真值）
- `regenerate_report.py`（掛一致性閘門）
- cron「龍七月報」prompt（引用制＋重產規則）

**不動**：`asset_diff_history.json`、`snapshot.json` 的 9 月真值、`investment_performance_adjust.json["2026-09"]`、
線上版本、INC-278／INC-281 相關檔

---

## 4. 驗證器設計（防三值再度分裂）

- **V1**：四個產物同月 `net` 相等（差 0）；任一缺檔 → FAIL（fail-closed）
- **V2**（負向對照）：把動態月報的配息改回 `167,675` → 必須 FAIL 且指名差額 2,911
- **V3**：`monthly_report_*.html` 不得出現「薪水+配息+租金」字樣、不得出現兩個同值列
- **V4**：8 月回歸（+428,802）四處一致
- **V5**：`performance_core` 缺件不得靜默歸零 → 手續費/利息缺件時 `missing` 非空且報表明示

---

## 5. 風險、取捨、開放問題

1. **利息口徑未定案（既有）**：目前只扣校正檔 42,000（房貸 28,000＋保單借貸 14,000）；
   `investment_performance_adjust.json` 備註載明「國泰轉貸 26,000／元大 3,267 未計，若採純投資槓桿口徑應為 43,267/月，需另案定案後回溯」。
   → 本批**沿用既有裁示**，不改；但閘門要在報表揭露「本口徑未含國泰/元大」。
2. **手續費無資料**：以 0 計並明示來源，不得靜默（INC-278 同族原則）。
3. **動態月報為 LLM 直寫**：程式無法強制，只能 prompt 約束＋閘門兜底（stale 一律 FAIL）。
4. **當月 vs 已結束月**：閘門只約束已結束月，避免與 mtd 週口徑衝突造成每日假紅燈。
5. **重產觸發**：配息/校正檔變更後誰負責重產動態月報？建議列入 Task 4 的 cron 規則（口徑修正批次必須同時重產）。
6. **不改歷史**：8 月以前月份不回改，僅讀值回歸。

---

## 6. 待使用者裁定（施工前）

- **Q1**：正名後的「常態淨資產變化（扣專案）」是否保留在月報？（保留＝資訊完整；移除＝版面乾淨）
- **Q2**：一致性閘門要掛在 `regenerate_report.py`（每日）還是獨立 cron（每月 1 日）？
  建議：**每日**（口徑修正後當天就會被抓）。
- **Q3**：動態月報是否納入閘門硬擋（抽不到數字即 FAIL），或先列警告一週觀察？
