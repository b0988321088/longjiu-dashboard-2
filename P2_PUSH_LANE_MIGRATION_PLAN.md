# P2 工單：13 條自動化推送路徑遷移 RECORD 通道

**排定：2026-09-15（使用者 9/14 核准「排明天一次做完」）**
**依據：CIO 對 v4 審查的 required_fixes（commit 9e5c3321）+ 14:14 全 repo 掃描結果**
**目標：`PUSH_LANE.log` 近 24h 只剩 RECORD（純資料 TAG 歸零），`closeout_check.py` ③ 無問題**

---

## 現況（9/14 實掃，勿憑印象）

| 類別 | 路徑 |
|------|------|
| ✅ 真審查（跑 `cio_review.py`，未過不推） | `regenerate_report.py`（07:00 路徑）、`daily_deploy.py`、`safe_update.py`（9/14 改硬擋） |
| ❌ 只靠自打標籤（本工單對象） | `evening_sync.py`、`nightly_dashboard_sync.py`、`radar_push.py`、`radar_weekly.py`、`investment_perf_monthly.py`（以上在 `hermes/scripts` 鏡像）、`update_and_deploy.py`、`refresh_all.py`、`complete_operation.py`、`cio_review_ingest.py`、`pre-run.sh`、`schedule_events_weekly_clean.py`、4 條 cron prompt（月報／週報／週六再平衡） |
| ⚪ 不推（只印提示） | `four_source_sync.py` |

**v4 現行規則**：`[cioreviewed]` 只准推資料/報表；含程式檔會被擋（`TAG-BLOCKED-CODE`）。
所以本工單不是「加審查」，而是「讓資料路徑也有不可自打的落紀錄」→ 走 RECORD。

---

## 步驟 1：新增共用 helper `auto_record.py`（repo 根目錄）

**流程（commit 之後、push 之前呼叫）**

```
1. 取 HEAD 與其 tree：git rev-parse HEAD / HEAD^{tree}
2. 跑 deterministic 檢查（預設 `python cio_review.py`；純資料路徑可用 --check 指定其他檢查器，
   例如 check_penetration_consistency.py / asset_sync.py 的一致性檢查）
   - exit != 0 → 一律「不落地」，印出失敗原因，讓 push 被閘門擋下（＝寧可斷、不要無審上線）
3. 通過 → 落地 RECORD：
   python cio_approve.py --verdict APPROVE --reviewer "AUTO-checker:<腳本名>" \
          --note "<檢查摘要>" --commit <HEAD sha>
```

**必須先加的功能**：`cio_approve.py` 新增 `--commit <sha>`（或 `--tree <sha>`）→ 只寫該 commit 的 tree 一筆。
現有 `--range-base` 依賴「base..HEAD」範圍，自動化路徑在 push 當下不一定有正確 upstream base，
直接指定 commit 最穩。

**驗收**：`python auto_record.py --script <name> --check "python cio_review.py" --dry-run` 能印出將寫入的
tree/reviewer/note，且 `--dry-run` 不動任何檔。

---

## 步驟 2：逐條掛上（每條：commit 後 → `auto_record` → push）

**移除各自 commit message 的 `[cioreviewed]`**（改走 RECORD 後不該再留自打標籤；保留會讓稽核分不清）。

建議順序（低風險 → 高風險，每完成一批就 `git push --dry-run` 驗證）：

1. `nightly_dashboard_sync.py`（22:15，7 個儀表板 JSON）
2. `evening_sync.py`（22:00，四源校準）
3. `radar_push.py` / `radar_weekly.py`（雷達）
4. `investment_perf_monthly.py`（月頻）
5. `schedule_events_weekly_clean.py`（週日 08:00）
6. `complete_operation.py` / `cio_review_ingest.py`
7. `update_and_deploy.py`（`git add -A`，注意會掃到未追蹤檔）
8. `refresh_all.py` / `pre-run.sh`（手動工具，最後做）
9. 4 條 cron prompt（月報／週報／週六再平衡）：改成「產出 → 送 CIO 審查（delegate_task）→
   `cio_approve.py --result` 落地 → push」；一週一次，成本可忽略

**注意**：`hermes/scripts` 鏡像由 post-commit 全量同步（`*.py`）；`.sh`（`pre-run.sh`）不在同步範圍
→ 手動 `cp` 一次。`closeout_check.py` 的鏡像是薄轉發器，**不可**被覆蓋。

---

## 步驟 3：驗證（缺一不可）

1. 每條路徑至少跑一次真實路徑（或該腳本的 dry-run 模式），確認：
   - 檢查沒過 → push 被擋（模擬：故意改壞一個檢查條件）
   - 檢查過 → `PUSH_LANE.log` 出現 `RECORD`，且**沒有** `TAG`
2. `python closeout_check.py --quiet` → ③ 推送通道只有 RECORD、無問題
3. `git push --dry-run origin HEAD:clean-main` 作為回歸檢查
4. 觀察 24h：確認 22:00／22:15／07:00 三班都成功（`cron/output/` 對應 job 的 `last_status`）

## 完成標準

- `PUSH_LANE.log` 近 24h：全部 `RECORD`，`TAG` / `SKIPREVIEW` 為 0
- 無任何自動化路徑的 commit message 還帶 `[cioreviewed]`
- `closeout_check.py` ③ 無問題、三班 cron `last_status = ok`

## 風險與對策

- **檢查器誤擋 → 斷推**：先確認檢查器對該路徑真的是 deterministic 且穩定（跑 3 次結果一致）；
  不確定的路徑就先不掛，寧可留在 TAG（純資料仍受 v4 保護）。
- **改 13 條一次到位**：每批 commit 都要走 CIO 審查 + RECORD（本檔的改動本身也是程式碼，
  v4 會擋 TAG），批次大小以「一次能驗完」為準。
- **`AUTO-checker` 不是真審**：它證明「deterministic 檢查通過」，不證明「設計正確」。
  設計/邏輯改動仍必須走真 CIO 審查，不要在程式改動上偷用 `AUTO-checker`。
