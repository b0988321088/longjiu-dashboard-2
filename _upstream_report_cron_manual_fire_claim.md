# 上游回報草稿：手動 fire 會「預先完成」下一個排程時點，該次正式排程靜默消失

> 狀態：草稿（2026-09-14 建立）。用途：回報 Hermes upstream（Discord `#plugins-skills-and-skins` 或 GitHub issue）。
> 檔名以 `_` 開頭 → 不進閉環稽核的舊值掃描範圍。

## 一句話

`cronjob(action='run')` 與 CLI `hermes cron run` 都會把 job 的**下一個排程時點**寫進
`executions.scheduled_instant` 並標記 `completed`；到點時 scheduler 用 `completed_occurrence()`
判定「已完成」→ 跳過該次排程。因為 `mark_job_run()` 事後把 `next_run_at` 重算回正常值，
`jobs.json` 看起來完全正常，`hermes cron list` 也顯示健康 → **漏跑完全靜默**。

## 環境

- Hermes Agent（Windows 11 / MSYS bash，Python 3.11.15），`HERMES_HOME=%LOCALAPPDATA%\hermes`
- 症狀觀測期間：2026-09-13 ~ 09-14，gateway 內建 ticker（`21a21c39c51f` 每 5 分鐘的 watchdog 證明
  scheduler 在該分鐘有正常 tick）

## 重現步驟（最小）

1. `cronjob(action='create', schedule='0 3 * * *', script='test_claim_probe.py', no_agent=True, deliver='local')`
   → job 建立，`next_run_at = 次日 03:00`
2. 用 **CLI** 觸發：`hermes cron run <job_id>`（輸出 `Triggered job: … / Ran now: succeeded.`）
3. 查 `~/AppData/Local/hermes/cron/executions.db`：
   ```sql
   SELECT job_id, started_at, source, status, scheduled_instant FROM executions WHERE job_id='<job_id>';
   ```
   實測結果：`source='direct'`, `status='completed'`, `scheduled_instant='2026-09-13T19:00:00+00:00'`
   （= 次日 03:00 本地）
4. 用 Hermes 自己的判定函式查同一筆：
   ```python
   from cron.occurrences import completed_occurrence
   completed_occurrence({"id": job_id}, "2026-09-13T19:00:00+00:00")  # → True
   ```
5. 等次日 03:00 到 → 沒有執行列、沒有交付；`jobs.json.next_run_at` 已被推進到隔天（看起來一切正常）。

同一路徑用 **工具** `cronjob(action='run')` 觸發也一樣會認領（`source='direct'` + 非空 `scheduled_instant`）。

## 預期 vs 實際

- **預期**：手動 run 是「額外跑一次」，不應影響正式排程；`trigger_job()` 的存在暗示這是設計意圖
  （它會蓋 `manual_run_at`，並在 `claim_job_for_fire()` 內被 `manual = force or job["manual_run_at"] == job["next_run_at"]` 消費）。
- **實際**：手動 run 等於「預先消費下一次排程」。實測 `manual_run_at` 在 claim 當下為 `None`
  （`jobs.json` 讀到的值），所以 `manual` 判斷落空 → `instant = scheduled_instant(next_run_at)` 被寫入執行列。

## 程式碼座標

- `cron/jobs.py::claim_job_for_fire()`（約 L2493-2537）：`manual` 判斷與 `job["fire_claim"]` /
  `next_run_at` 推進；`return_job=True` 才會回傳帶 `_scheduled_instant` 的 job。
- `cron/jobs.py::trigger_job()`（L2006-2028）：刻意把 `next_run_at` 與 `manual_run_at` 都設成 `now`。
- `cron/scheduler.py::_evaluate_due_job()`（L2935）：`manual_run = job.get("manual_run_at") == next_run`，
  L2950 才把 `_scheduled_instant` 設為 `None`（手動）。
- `cron/scheduler.py::run_one_job()`（L2522）/ `_run_one_job_body()`（L2895）：
  `create_execution(job_id, source="direct", scheduled_instant=job.get("_scheduled_instant"))`。
- `cron/occurrences.py::completed_occurrence()`：以 `(job_id, scheduled_instant, status='completed')` 判重。
- 工具端：`tools/cronjob_tools.py::_claim_for_manual_run()`（L182-196）呼叫
  `claim_job_for_fire(job_id, return_job=True)`（**未帶 `force=True`**）→ 會被視為非手動而認領下一時點。

## 影響

- 任何「為了驗證而手動 run 一次」的操作，都會讓該 job 的**下一次正式排程消失**；一天內手動 run 幾個
  job 就吃掉幾個時點。實測：一次驗證日吃掉 5 個時點（含隔日的緊急應變與法人雷達推播）。
- 稽核/健康監控看不到：`jobs.json` 正常、`last_status=ok`、只有 executions 少一列。

## 建議修法（任一）

1. **工具端**：`_claim_for_manual_run()` 改走 `trigger_job()` 或呼叫 `claim_job_for_fire(..., force=True)`，
   讓手動 fire 不取得 occurrence 身分（`_scheduled_instant=None`）。
2. **核心端**：`claim_job_for_fire()` 在 `force=True` 或 CLI/工具手動路徑時，別把 `scheduled_instant`
   寫進執行列（手動 = 無 occurrence 身分），避免誤判為「該時點已完成」。
3. **防禦**：`completed_occurrence()` 忽略 `scheduled_instant > now` 的列（未來時點不可能真的完成）。

## 本機 workaround（已實作於龍九系統）

- 驗證腳本一律 **shell 直跑** `python <script>.py`（完全不碰 cron 帳務）。
- 稽核第 8 類：掃「`status='completed'` 且 `scheduled_instant` 在未來」→ ❌。
- `release_claimed_occurrences.py --fix`：釋放被誤認領的時點（只清 `scheduled_instant`，保留歷史列）。
- `closeout_check.py`：收工檢查一鍵（認領偵測 + 閉環稽核 + 補跑清單）。
