# 龍九系統腳本／排程整合方案（2026-09-22 提案）

> 現況：cron 58 個 job、repo 約 140 支 .py、hermes/scripts 174 支（cron 直接用 49 支）
> 目標：**同性質功能合併成單一入口 + 子命令**，cron 降到 ~38 個，重複邏輯集中一處
> 原則：先計畫 → 核准 → 執行；每個 Phase 獨立可交付、可回滾；不刪任何東西前先備份

---

## 一、診斷：四個真正的重複熱區

| 熱區 | 現況 | 問題 |
|------|------|------|
| **費用/錢包** | 6 支腳本各自報餘額/花費（ds_balance_alert、wallet_status、gemini_balance_reminder、ai_cost_watch、daily_token_account、fallback_cost_guard）＋1 支停用的 cer_watch | 同一件事（餘額、日耗、儲值、熔斷）散在 7 處，門檻各寫一份 |
| **提醒** | reminder_agent 20:00、entry_monitor 20:30、pnl_rebalance_alert 20:45、health_alert_check 09:10 | 都是「條件式提醒」，卻 4 個 job、4 份排程 |
| **記憶/清理維護** | memory_sync、run_memory_archiver、memory_backup、weekly_system_cleanup、gmail_cleanup、notion_cleanup、nightly(VACUUM)、weekly_db_maintenance、session_poison_sweep、session_bloat_watch | 10 支維護腳本、8 個時段，無統一窗口 |
| **報告/審查** | 日報鏈 5 支（07:00→08:00→22:00→22:15→22:40）＋週報 4 支＋審查 5 支 | 週報/審查內容疑似重疊（技能內原本就列為待辦） |

---

## 二、建議方案（依「效益/風險」排序）

### Phase 1 — 零風險清理（**建議先做**）
1. **刪除 2 個停用 job**
   - `cer_watch.py`（停用）→ 功能**已被 `ai_cost_watch.py` 的 CER 專區＋A2/A5/A9 完全取代**
   - 「離峰工程梯次 18:00」一次性（9/15）→ 已完成，任務殘留
2. **費用/錢包 6 → 2 個入口**
   - `cost_watch.py`（= 現有 `ai_cost_watch.py` 擴充，保留既有 A1–A10）
     - `--digest` 現況摘要（13:30 / 18:30，即現行）
     - `--close` 日結 + 寫帳本（吸收 `daily_token_account.py` 22:30）
     - `--wallet` 餘額 + 日耗 + 儲值連結（吸收 `wallet_status.py`、`gemini_balance_reminder.py`）
   - `cost_guard.py`（新增，只做門檻/熔斷）
     - 合併 `fallback_cost_guard.py`（21:10 熔斷）＋ `ds_balance_alert.py` 門檻警示（09:00）
     - 合併後：**21:10 一次跑**，有觸發才輸出（靜默 watchdog 模式）
   - cron：6 個 → **3 個**（13:30/18:30 digest、21:10 guard、22:30 close）
3. **提醒 4 → 1**
   - `alerts.py`：一次評估所有提醒條件（進場、獲利超標、健康紅線、主動提醒）
   - 保留 2 個時段：`09:10`（盤前）、`20:00`（盤後），**無觸發則零輸出 → 不推播**
   - cron：4 個 → **2 個**

### Phase 2 — 結構整合（中風險，需逐一驗證）
4. **記憶 3 → 1**：`memory_ops.py --backup | --archive | --sync`
   - cron 保留 2 個時段（06:45 備份歸檔／19:00 離峰同步），腳本從 3 支變 1 支
5. **清理維護 10 → 1**：`maintenance.py --level light|deep|db`
   - `light`：`*/10` session_poison_sweep（保留高頻，因是即時防護）
   - `deep`：週一 03:00（合併 weekly_system_cleanup＋gmail_cleanup＋notion_cleanup）
   - `db`：週日 05:00（合併 weekly_db_maintenance＋VACUUM＋prune_state_db_backups）
   - session_bloat_watch（5m watchdog）維持獨立（即時性要求）
6. **Notion 週報 2 → 1**：`notion_weekly.py --ai | --trend`，時段集中週五 10:00

### Phase 3 — 需先確認內容不重疊（先盤點再動）
7. **週報／審查去重**：`龍九週五深度審查（三合一）` vs `龍九動態自我檢討週報（週日 19:00）` vs `技能自我審查（週日 16:00）`
   - 先產出三者「實際輸出內容對照表」，確認重疊比例再決定合併或保留
8. **日報時段鏈合併**：`morning_deploy` + `morning_batch` → 單一 `morning.py`；`evening_sync` + `nightly_dashboard_sync` + `closeout_check` → 單一 `nightly_chain.py`（依序執行，失敗即停）
9. **agent job 降階評估**：8 個 agent（LLM）任務逐一檢視，能改成 `no_agent` 腳本邏輯的就降階（成本直接歸零）

---

## 三、預期效益

| 項目 | 現況 | 目標 |
|------|------|------|
| cron job 數 | 58 | **~38** |
| 費用/錢包相關腳本 | 7（含 1 停用） | **2** |
| 提醒相關腳本 | 4 | **1** |
| 記憶相關腳本 | 3 | **1** |
| 維護相關腳本 | 10 | **2**（1 高頻 watchdog＋1 多層入口） |
| 每週 LLM agent 任務 | 8 | 待 Phase 3 盤點後下修 |

**副作用與緩解**
- 合併 = 單點失效範圍變大 → 用「子命令獨立 try/except、失敗不影響其他子命令、回傳碼分開回報」
- 高頻 watchdog 不合併（即時性 > 整潔）
- 每個 Phase 完成後跑 `closeout_check.py` 驗證，且**保留舊腳本 30 天**（`.archive/deprecated_scripts/`）

---

## 四、執行順序建議

```
Phase 1（今天可做，零風險）  → 驗證 → 推送
Phase 2（本週）              → 逐一實測 → CI 審查 → 推送
Phase 3（先盤點，下週決策）  → 產出對照表 → 你核准後才動
```

> 每一 Phase 都走原本的治理流程：本機實跑 → 異質審查 APPROVE → push 閘門 → 收工稽核。
