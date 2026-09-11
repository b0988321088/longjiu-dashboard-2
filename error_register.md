# 龍九控股 異常記錄（error_register.md）

> **2026-09-12 改版**：本檔不再由腳本逐筆自由文字追加。
> - 機器可讀事件流：`inc_events.jsonl`（append-only，同 source/errors/日期 重複只累加 `count`，不重複新增）
> - 查詢／關閉：`python lj_inc.py list`、`python lj_inc.py close <ID前綴>`
> - 完整錯誤知識庫（含 root cause / check_rule）：技能 `longjiu-error-register/references/error_register.md`（INC-152~154 已登記）
> - 2026-07-30~09-12 的自動登記噪音已整併至本檔末段彙總，原始逐筆全文保留於 `error_register_archive_202607-09.md`

## 一、未結案追蹤（需人工處理）

| 項目 | 日期 | 狀態 | 說明 |
|------|------|------|------|
| 未經核准直接推送 | 2026-07-30 | 待檢討 | 標籤動態化+FL65 更新後未先傳本地檔給使用者確認即 git push |
| 一鍵管線三缺陷 | 2026-09-12 | 已修（INC-152/153/154） | 保單口徑漏修／argv 未驗證／登記無去重；9/12 已修並跑通 16 步 |
| CIO 閘門檢查字串假通過 | 2026-09-12 | 已修（INC-155） | cio_review.py 兩處整份日報 substring 搜尋：「來源」靠無關表格「資金來源」過關；Relay 站制找「摩根多重收益」但日報是「摩根JPM多重收益」→ 隨機過／隨機擋。已改為區塊化 + 資料驅動（snapshot.relay_stations） |
| 全庫靜態稽核 9 筆真 bug | 2026-09-12 | 已修（INC-156） | 341 筆掃描中 9 筆會炸/靜默算錯（重複 dict key、未定義名稱、timedelta 被 local import 遮蔽…），5 筆藏在 run_daily `_inject_dashboard` 920 行死函式內。已新增 `static_gate.py` 接為 sync_all 第 1 步自動擋 |

## 二、有根因與 check_rule 的歷史事件（逐筆保留）

## INC-未經核准直接推送（2026-07-30）
- 時間：05:49
- 錯誤：標籤動態化 + FL65更新後，未先傳本地檔給使用者確認，直接 git push
- 根因：違反鐵則「先傳本地檔，核准後才推」
- 狀態：⏳ 待檢討

## INC-2026-08-17 穿透異常 cron 假警報
- 時間：2026-08-17 08:35（重複發送多日）
- 錯誤：穿透異常偵測 cron 重複發「2026-08-10 現金 -30.3%」警報（星展理財型還款舊事件）
- 根因：penetration_monitor.py 用 `Path(__file__).resolve().parent` 找 DB → cron 執行 scripts/ 副本 → 讀 scripts/dragon_assets.db（舊副本只到 8/10）→ 比對 8/8 vs 8/10 → 假警報
- 修復：固定指向 repo 真值 DB（`Path(r"C:\Users\bot\Desktop\longjiu_system")`）；測試輸出「✅ 穿透正常（2026-08-15）」
- check_rule：cron 腳本禁止用 `__file__` parent 找資料檔（scripts 副本可能是舊的）；一律用 longjiu_paths.REPO_BASE 或固定 repo 路徑
- 狀態：✅ 已修（ffa8a8d）

## INC-2026-08-17 DAA 目標改版對策表不同步
- 時間：2026-08-17
- 錯誤：使用者問「DAA 動態理財已達標準為何沒改」
- 根因：8/15 穿透目標改版（現金15→5%、債券20→30%），snapshot.targets 更新但 tactical_table.py STRATEGY 表債券仍是「凍結」（20% 目標時代）→ 對策表顯示「債券 -6pp 卻凍結」；且 tactical_table JSON 未重產
- 修復：STRATEGY 債券 action「凍結」→「增持」（美元直債梯 3-7Y 375+8-10Y 125）；重跑 tactical_table.py + run_daily.py
- check_rule：改穿透目標後三步驟：①grep tactical_table.py STRATEGY 動作對應新目標 ②重產 tactical_table JSON ③重跑日報
- 狀態：✅ 已修（98c7b77）

## INC-2026-08-17 房租未更新
- 時間：2026-08-17
- 錯誤：日報房租只顯示已收 24,000（大義街），缺洲際W 33,000
- 根因：run_daily 執行時 snapshot rent_received_records 尚無洲際W 33,000（其他 session 後寫入）；日報未重跑
- 修復：重跑 run_daily → 已收 57,000、待收 23,100
- check_rule：rent_received_records 更新後必須重跑 run_daily（日報房租金流段動態讀取）
- 狀態：✅ 已修（98c7b77）

## INC-2026-09-10
- 時間：2026-09-10 08:46:46
- 錯誤：Session 膨脹監控（watchdog v6.6）對已結束（session_reset 於 08:45:12）的 session 推殘留 ⚠️「已達 264 則」警報 — active_sessions() 未過濾 ended_at
- 修正：watchdog v6.7（INC-151）WARN/runaway 跳過 ended session，CRIT/AUTO 不動；沙箱 29 檢查全 PASS、真實 dry-run 靜默
- 狀態：✅ 已修正

## 三、自動登記噪音彙總（2026-07-30 ~ 2026-09-12，已不再逐筆追蹤）

| 錯誤類型 | 次數 | 首次 | 最後 | 處置 |
|---------|------|------|------|------|
| 穿透三報表不一致 | 44 | 2026-08-07 | 2026-09-04 | 已整併（見對應 INC／已修） |
| 同義欄位不一致 | 20 | 2026-08-07 | 2026-08-26 | 已整併（見對應 INC／已修） |
| 四源不一致 | 16 | 2026-08-03 | 2026-09-12 | 已整併（見對應 INC／已修） |
| 四源驗證失敗 | 2 | 2026-08-31 | 2026-09-12 | 已整併（見對應 INC／已修） |
| **合計** | **82** | | | |

## 四、隨機污染殘留（2026-09-12 已清除）

- `--check` 參數被當成日期寫入：snapshot.date / dragon_assets.db assets 假列 / asset_diff_history.json key / dashboard_decisions.json 任務字串 / daily_report_v2_--check.html / notion_bridge/--check_strategy_handbook.md
- 已清除並備份為 `*.bak-20260912-checkclean`；防護 = INC-153（sync_all.py argv 嚴格驗證，非法即 exit 2）
