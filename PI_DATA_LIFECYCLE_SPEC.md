# PI 專業投資人｜資料生命週期規格（工單）

**狀態**：`OPEN / SPEC ONLY / NO ENGINEERING`
**裁決日**：2026-10-04（使用者裁定「(a) 保留 PI 功能，但先不施工」）
**前置**：`threshold 30M` 第 0 步唯讀盤點（`mem-20261004211050-1083`）
**本檔性質**：規格／工單，非施工紀錄。使用者未核准前**不得**動任何一行程式。

---

## 0. 為什麼需要這張工單

盤點證實 PI 風控卡不是「有一個 30M fallback 要清」而已，而是**整個功能沒有資料生命週期**：

| 問題 | 實測事實 |
|---|---|
| 無寫入者 | 全 repo 對 `snapshot.professional_investor` **只有讀、零寫入**；snapshot 亦無此鍵 |
| 目前不可達 | `tactical_table.py:286` 的 `if pi:` 恆為 False → **PI 卡從未渲染** |
| 兩個位置 | `entry_monitor.py:46` 讀 `snapshot.pi_status`（頂層）vs `debt_restructure_tracker.py:89` 讀 `snapshot.professional_investor.pi_status`（巢狀） |
| 兩種欄名 | `entry_monitor` 判 `pi.get("認列")`；其餘判 `pi_status` |
| 假真值 | 卡片內**寫死** `現況：金融資產含保單 28,220,311` |

**寫死值已證實為 stale，且方向是「低估缺口」**（2026-10-04 實測 snapshot）：

```
證券 3,007,220 + 基金 12,611,674 + 保單 9,418,965 = 25,037,859（不含現金）
                                    ＋現金 1,753,675 = 26,791,534（＝total_assets，不含不動產）

卡片寫死      28,220,311  → 比含現金真值多 1,428,777
卡片算出的缺口  1,779,689  （30,000,000 − 28,220,311）
真值缺口（含現金）3,208,466
真值缺口（不含現金）4,962,141
```

→ 若 PI 卡開始渲染，會顯示「缺口 178 萬」（看起來快到了），而實際缺口是 **321 萬**。這足以誤導送件時機判斷，屬**假真值**而非單純顯示瑕疵。

---

## 1. 現行消費者清冊（實測，非推測）

| # | 消費者 | 讀取路徑 | 期望欄位 | 缺值現行行為 |
|---|---|---|---|---|
| 1 | `tactical_table.py:269`（轉手）`286` | `snap.professional_investor` → `table` | — | `{}` |
| 2 | `tactical_table.py:290` 卡片列 | `table.professional_investor` | `status`／`threshold`／`gap` | fallback `申請中`／`30_000_000`／`0`；`現況` 為寫死字串 |
| 3 | `tactical_table.py:291-310` | 同上 | `force_order[]`／`macro_triggers{警戒線_5.20}`／`forbidden[]`／`lombard_bridge{business_logic, hard_limits[], carry_trade_warning}` | 各段 `if` 略過（靜默） |
| 4 | `debt_restructure_tracker.py:89,196-199` | `snap.professional_investor.pi_status` | `pi_status ∈ ["未申請","審核中","已正式核准"]` | 預設 `未申請` → **鎖住 Lombard**（`can_do_lombard` 硬閘門） |
| 5 | `debt_restructure_tracker.py:240` | `snap.professional_investor.deployment_plan` | `status`／`phase1_mandatory`／`phase2_optional` | 空 dict → 區塊靜默 |
| 6 | `entry_monitor.py:46-48` | **`snap.pi_status`（頂層）** | `認列`／`status` | `{}` → `pi_done=False` → **台股慢慢買執行鏈不觸發** |
| 7 | `run_daily.py:295` | 轉手傳遞 | — | — |

**結論**：同一組事實有 **2 個儲存位置、2 種欄名、3 個獨立判定點**，且無單一寫入者。

---

## 2. 待裁示口徑（施工前必須先定，不得由我代決）

### Q1：`professional_investor` 的容器位置
- 建議：**唯一容器＝`snapshot.professional_investor`**；`snapshot.pi_status`（頂層）**廢除**。
- 需你確認：entry_monitor 改讀巢狀欄位，或保留頂層並反向同步（**不建議**，等於第二份真值）。

### Q2：`pi_status` 欄位名與狀態機
- 建議：欄名統一 `pi_status`；**廢除** `認列`。
- 現行三態：`未申請／審核中／已正式核准`（`debt_restructure_tracker.PI_STATES`）。
- 需你確認：是否需要中間態（如 `已送件`／`補件中`），以及「已核准」是否即等於 Lombard 解鎖（現行：是，硬鎖）。

### Q3：「金融資產含保單」的口徑
- 候選 A：`securities + funds + insurance = 25,037,859`（**不含現金**）
- 候選 B：`＋ cash_total = 26,791,534`（＝現行 `total_assets`，不含不動產）
- 需你確認：PI 認定之「金融資產」**是否含存款／現金**（實務多數含存款；不動產不計）。
- 我的建議：**B**，並以單一 accessor 固定口徑，不得由消費者自行加總。

### Q4：「可併配偶」是否保留
- 卡片現行文字含「（可併配偶）」。
- 若保留，需定義配偶資料來源與第二份寫入者；若不保留，從文案移除。
- 需你裁示。

---

## 3. 目標資料模型（規格主體）

```
snapshot.professional_investor = {
  "pi_status":   "未申請" | "審核中" | "已正式核准",   # 唯一狀態來源（取代 認列）
  "updated_at":  "2026-10-04T11:39:57+08:00",          # 寫入者必填
  "source":      "user|system",                        # 稽核用
  "threshold":   30000000,                             # 見 §4：法規常數，由 accessor 注入，非人工維護
  "current":     26791534,                             # 見 §5：金融資產含保單（口徑待裁示 Q3）
  "gap":         3208466,                              # 見 §6：計算值
  "force_order": [ ... ],                              # 選配，卡片用
  "macro_triggers": { "警戒線_5.20": "..." },          # 選配
  "forbidden":   [ ... ],                              # 選配
  "lombard_bridge": { "business_logic": "...", "hard_limits": [...], "carry_trade_warning": {...} }
}
```

**唯一寫入者**：新增 `sync_professional_investor.py`（暫名）為**唯一**寫入入口，規則比照 `append_dashboard_decisions.py`：
- 固定產生 `updated_at`（台北 +08:00）／`source`
- 文字手術寫入（不整檔重排）＋ 寫後三重驗證
- 寫入前經 PII gate
- 允許 `--dry-run`
- **不得**由其他腳本直接寫此鍵

---

## 4. `threshold`：法規常數的唯一位置

- **性質**：台灣「專業投資人」認定門檻＝金融資產 3,000 萬元，**外部法規常數**，非個人政策值 → **不進 snapshot**、**不做 fail-closed**（法規不會因缺值而未知）。
- **唯一位置**：`sot_targets.py` 模組層具名常數
  ```python
  PI_REGULATORY_THRESHOLD_TWD = 30_000_000  # 金管會「專業投資人」金融資產門檻
  ```
- **唯一 accessor**：`pi_regulatory_threshold()`（無參數、回傳常數）。
- 消費端**禁止**再出現 `30_000_000` 字面或 `pi.get('threshold', ...)` 形式。

---

## 5. `current`：金融資產的計算來源

- 唯一 accessor：`pi_financial_assets(snap)`，口徑由 Q3 決定。
- 依賴既有 fail-closed accessor：`securities_total()`／`funds_total()`／`insurance_total()`（＋現金 `total_cash()`，若採口徑 B）。
- **禁止**：任何消費者自行加總、或使用寫死金額（含 `28,220,311`）。

---

## 6. `gap` 與顯示規則

```
gap   = max(0, threshold − current)
達標  = current >= threshold     → gap 顯示「✅ 已達標」
未達標 = current <  threshold     → gap 顯示金額＋距門檻百分比
```
- 邊界定義：`current == threshold` 屬**達標**。
- 顯示格式由單一函式產生（不得各報表自行格式化）。

---

## 7. 缺值規則（fail-closed）

| 情況 | 規定行為 |
|---|---|
| `professional_investor` 不存在或空 | **不得**靜默隱藏卡片、**不得**填 `申請中`／`30000000`／`0`；改印 `⛔ PI 資料缺真值（拒絕顯示）` 並留 WARN |
| `pi_status` 缺或不在三態內 | **raise**（沿用現行 PI_STATES 驗證），不得回退 `未申請` |
| `current` 計算所需任一來源缺 | 由 §5 accessor raise → 整卡 fail-closed |
| `threshold` | 不缺（法規常數），不參與 fail-closed 判定 |

> 注意：現行 `debt_restructure_tracker.py:198` 對非法狀態**回退 `未申請`**（fail-open），此行為需改為 raise。

---

## 8. 須消除的舊路徑（清單）

| 位置 | 現況 | 目標 |
|---|---|---|
| `tactical_table.py:290` | `pi.get('threshold', 30_000_000)` | 讀 `pi_regulatory_threshold()` |
| `tactical_table.py:290` | `現況：金融資產含保單 28,220,311`（寫死） | 讀 `pi_financial_assets(snap)`（**刪除字面**） |
| `tactical_table.py:290` | `pi.get('gap', 0)` | 讀 §6 計算結果 |
| `tactical_table.py:290` | `pi.get('status','申請中')` | 缺值 fail-closed |
| `build_weekly_report.py:145,195` | 顯示文字「3,000萬」 | 改由常數格式化 |
| `entry_monitor.py:46` | `snap.get("pi_status", {})`＋`認列` | 改讀 `snap.professional_investor.pi_status` |
| `debt_restructure_tracker.py:198` | 非法狀態回退 `未申請` | raise |

---

## 9. 驗收（三組＋一項反寫死測試）

| 測項 | 內容 | 通過條件 |
|---|---|---|
| **有值** | 寫入完整 `professional_investor` | 卡片／tracker／entry_monitor 三者數字與 accessor 逐位一致 |
| **無值** | 移除 `professional_investor` | 三處皆 fail-closed，輸出**不得出現任何金額**（含 30,000,000／28,220,311） |
| **跨 30M** | `current = 29,000,000 / 30,000,000 / 31,000,000` | 未達標／達標（gap=0）／超標 三態正確，邊界 `==` 判達標 |
| **反寫死** | 改動來源數值（如現金 +50 萬） | 卡片數字**跟著變**（證明非寫死；沿用 cash_floor 批次的「位移測試」手法） |

另：靜態複掃 `28,220,311`／`30_000_000` 在 live 程式＝0 殘留（顯示文字除外，另判）。

---

## 10. 施工順序（不可跳）

```
① 裁示 Q1–Q4 口徑
② 建 PI_REGULATORY_THRESHOLD_TWD ＋ accessor（pi_regulatory_threshold／pi_financial_assets）
③ 建唯一寫入者 sync_professional_investor.py（含 dry-run、PII gate）
④ 接消費端（tactical_table／debt_restructure_tracker／entry_monitor，全部改走 accessor）
⑤ 清 §8 舊路徑（含 28,220,311）
⑥ 跑 §9 四組測試 ＋ 靜態複掃 ＋ regression ＋ 獨立審查 ＋ 遠端 SHA
```

**在 ① 完成前不得進入 ②–⑥。** 這一步不能為了「消掉一個硬編碼」而先造一個未經裁決的新真值。
