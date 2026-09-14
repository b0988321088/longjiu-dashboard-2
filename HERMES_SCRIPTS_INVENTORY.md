# hermes/scripts 鏡像清單（P1-2 盤點）

產出時間：2026-09-14 14:54｜產出工具：`gen_mirror_inventory.py`

鏡像目錄＝cron 實際執行位置：`C:\Users\bot\AppData\Local\hermes\scripts`

## A. 受版控（repo 有同名檔 → post-commit 自動同步）

共 136 支。狀態：`轉發器`（鏡像端刻意保留、指向 repo 真值，內容本就不同）／
`同步`（與 repo 一致）／`❗漂移`（應一致卻不一致 → 需查為何沒同步）。

- ❗ auto_record.py（09-14 14:53）
- ❗ complete_operation.py（09-14 14:51）
- ❗ evening_sync.py（09-14 14:51）
- ❗ investment_perf_monthly.py（09-14 14:51）
- ❗ radar_weekly.py（09-14 14:51）

（轉發器 39 支、內容一致 92 支、真漂移 5 支）

## B. 只在鏡像、未受版控

共 24 支。判定依據：**是否含 git 操作**（會 push/commit 的才需要納入
版控與推送閘門）→ 實測全部 **無** git 操作，因此沒有斷推風險、不急著納入版控。

⚠️ 含 git 操作者：**無**（本日實測 grep `"push"`／`git push`／`"commit"` 全 0 命中）

| 腳本 | 含 git 操作 | 最後修改 |
|---|---|---|
| `daily_deploy_wrapper.py` | 無 | 2026-07-23 13:18 |
| `dashboard.py` | 無 | 2026-08-10 22:06 |
| `ds_topup_reminder.py` | 無 | 2026-08-16 09:22 |
| `ds_topup_reminder_0908.py` | 無 | 2026-09-05 21:58 |
| `gateway_guard.py` | 無 | 2026-09-11 16:26 |
| `gmail_triage.py` | 無 | 2026-08-26 07:36 |
| `health_alert_check.py` | 無 | 2026-09-05 21:47 |
| `income_dashboard.py` | 無 | 2026-08-10 22:06 |
| `lj_structure_check.py` | 無 | 2026-09-02 10:19 |
| `longjiu_paths.py` | 無 | 2026-08-10 22:05 |
| `manual_session_reset.py` | 無 | 2026-09-11 16:37 |
| `mirror_appdata.py` | 無 | 2026-09-05 19:58 |
| `monday_decision_reminder_0824.py` | 無 | 2026-08-22 17:50 |
| `notion_ai_daily_wrapper.py` | 無 | 2026-07-23 13:17 |
| `prune_state_db_backups.py` | 無 | 2026-09-05 12:30 |
| `rebalance_md2html.py` | 無 | 2026-09-05 21:05 |
| `run_memory_sync_daily.py` | 無 | 2026-07-26 19:08 |
| `run_morning_wrapper.py` | 無 | 2026-07-24 10:11 |
| `run_penetration_monitor.py` | 無 | 2026-07-24 10:11 |
| `run_reminder_agent.py` | 無 | 2026-07-24 10:10 |
| `session_bloat_watch.py` | 無 | 2026-09-14 02:21 |
| `tg_flood_escalate.py` | 無 | 2026-09-08 14:22 |
| `tg_flood_probe.py` | 無 | 2026-09-08 14:19 |
| `tg_flood_retest.py` | 無 | 2026-09-08 13:59 |

## C. 決策（2026-09-14）

1. 會 push／寫 repo 產物的腳本 → **必須納入版控**（本日已完成 4 支：radar_push、radar_weekly、
   nightly_dashboard_sync、investment_perf_monthly）。
2. 其餘僅讀取/告警的腳本 → 不強制納入版控，改**季度盤點**（重跑本工具）＋本次清單留痕。
3. 若日後任一支新增 git 操作 → 依第 1 點立即納入版控（本工具的 C 類檢查會標出來）。
