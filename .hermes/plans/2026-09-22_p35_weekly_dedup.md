# P3-5 第 2 步計畫：週日動態週報改為「引用單一真值口徑」

日期：2026-09-22｜範圍：**只改一支 cron job**（週日 19:00 動態自我檢討週報 `6a9babc90954`）
狀態：**已套用，測試中**

---

## ⚠️ 修訂（2026-09-22 執行時發現，原計畫前提錯誤）

原計畫要用 `context_from` 串接「週六 16:00 再平衡評估（`f5e412363a17`）」的輸出。**實測發現行不通**：

```
週六 16:00 job 有前置閘門 script = rebalance_sameday_gate.py
  9/12 16:00 → output 174 bytes：「Script gate returned wakeAgent=false — agent skipped」
  9/19 16:00 → 同上
  最後一次真的醒來：9/5
```

`cron/scheduler_prompt.py::_inject_context_from` 讀的是上游 job 在 `cron/output/<job_id>/*.md` 的**最新非靜默輸出**；
沒有輸出時是 **靜默跳過**（第 111 行 `if not latest_output: continue`）。
→ 照原計畫做，週日每週注入到的會是空的，fallback 常態觸發，等於白做。

**修訂後機制（已套用）**：權威改成**檔案**而不是 job 輸出 ——
`rebalance_eval_<日期>.html` 是 **07:00 管線每天產出**（9/15–9/22 連續），內含逐桶佔比／戰略目標／防守合併口徑。
- 存在且 ≤3 天 → 一律引用，寫明來源，不得自行重算；判準沿用「合併口徑 ≥60% 為是否足夠，單桶 30% 僅結構參考」
- 不存在或 >3 天 → 自行全口徑推導，並在模組 0 頂端標「⚠️ 本週無再平衡基準，已自行推導」
- 判讀不同 → 標「⚠️ 與再平衡口徑分歧」＋原因，**禁止默默改數字**
- **不使用 `context_from`** → 少一個失敗模式（不再依賴「上游 agent 有沒有醒」）

---

## 0. 效益更正（實測推翻推估）

用 `state.db` 的 `sessions` 表（`source='cron'`，以 title 比對 job）實測每次執行成本：

| 任務 | 歷史每次成本（USD） | 平均 | 換算每週 |
|---|---|---|---|
| 週日動態週報 19:00 | 0.0238 / 0.0264 / 0.0337 / 0.0437 | 0.0319 | ≈ NT$1.0 |
| 週六再平衡 16:00 | 0.0137 / 0.0155 / 0.0167 | 0.0153 | ≈ NT$0.5 |
| 週五深度審查 18:30 | 0.0262 / 0.0711 / 0.0766 / 0.0304 | 0.0510 | ≈ NT$1.6 |

三支合計 ≈ **NT$3.1/週 ≈ NT$13/月**，佔月總成本 NT$3,384 的 **0.4%**。
> 原估算「可省 NT$150–250/月」**錯了約一個數量級**（那是用日級帳本外推、無法歸戶的產物）。
> **省錢不是理由；真正的理由是口徑一致性。**

---

## 1. 真正的理由：同一個防禦指標，三份報告給的方向不一致

| 報告 | 防守數字 | 框架 |
|---|---|---|
| 週五 audit 9/18 | 17.4% vs 目標 30% | 「缺 12.6pp」 |
| 週六 rebalance 9/19 | 17.4%（單桶）／合併 **68.0%** | 「🟢 已足」 |
| 週日週報 9/20 | 合併口徑 **67.8%** | — |

同一狀態：週五寫「缺」、週六寫「已足」、週日又是另一個數字。9/16 已定案要看合併口徑，但三支各自推導。

---

## 2. 已套用內容

- job `6a9babc90954`：prompt 由 5,489 字 → 6,027 字（前置 539 字「🧷 單一真值口徑」區塊）
- **原始 prompt 逐字保留**（逐字元比對，僅尾端一個換行被 bash `$(cat)` 吃掉 — 語意無影響）
- `context_from` 維持 None／空；schedule `0 19 * * 0`／enabled／skills／toolsets 不變
- 備份：`cron/jobs.json.bak.pre_p35_20260922-105043`；新舊 prompt 全文存於 `Temp/longjiu_backups/p35_new_prompt_lf.txt`、`p35_old_prompt.txt`

### 行尾踩雷（已修）
第一次套用把 prompt 寫成 `\r\r\n`（Python `write_text` 在 Windows 做 LF→CRLF，store 又轉一次）。
**正確做法：餵 LF-only 文字**（`write_text(..., newline='')`），store 自己處理；讀回必驗 `\r\r` 次數 = 0。

---

## 3. 驗收與量測

| 項目 | 方法 | 通過標準 |
|---|---|---|
| 一致性 | 週日報告的配置權重／防守合併口徑 vs `rebalance_eval_<date>.html` | 逐項相同，或有標「分歧」 |
| 來源標註 | 模組 0 出現「口徑來源：rebalance_eval_<日期>」 | 有 |
| Fallback | 情境模擬（最新基準 >3 天） | 走自行推導並出現 ⚠️ 警示句 |
| 成本 | `state.db` sessions 比對每次 run 的 in/out/calls | 基準（9/20）：in=56,649／out=42,096／calls=31／$0.0238 |
| 品質 | 5 大模組不得少章節；首篇送 CIO 審查 | 章節齊全 |

**觀察期**：一週（下次 9/27 週日），回報成本曲線與一致性，再決定第 3 步（週五深度審查改 delta）。

---

## 4. 回復點

```bash
# 還原 prompt（一步）
cp "$LOCALAPPDATA/hermes/cron/jobs.json.bak.pre_p35_20260922-105043" "$LOCALAPPDATA/hermes/cron/jobs.json"
# 或只還原 prompt 文字：
hermes cron edit 6a9babc90954 --prompt "$(cat "$LOCALAPPDATA/Temp/longjiu_backups/p35_old_prompt.txt")"
```

---

## 附錄 A：週日 job prompt 原文（改動前，5,489 字）

見 `$LOCALAPPDATA/Temp/longjiu_backups/p35_old_prompt.txt`（原始備份：
`cron/jobs.json.bak.pre_p35_20260922-105043` 內 `id=6a9babc90954` 的 `prompt` 欄位）。
