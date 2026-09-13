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
| 儀表板「本週完成清單」永不更新 | 2026-09-13 | 已修（INC-161） | 該區塊是 template 手工寫死的 10 行（停在 9/1），管線從不重寫；真值 work_log.json 只餵工作日誌卡。改為 build_dashboard 靜態層（近 7 天「完成」）+ 前端 JS 即時層；順修退休規劃連結被 rebuild 還原（改 glob 動態）。commit 0a22f202 |
| CEO 儀表板 4 張表只剩表頭 | 2026-09-13 | 已修（INC-162） | 9/11 週五三合一 cron 被 gateway 中斷 → ceo_analysis JSON 缺 資產變化/資金流動/里程碑/雙維度，而 build_ceo_dashboard 全靠該 JSON。改為 DB 週 pair／weekly_ops_closure／schedule_events／dual_dimension_metric 現算，LLM 只補文字；加空表驗收 + 指定日期補產。9/11 報告已回補上線 |

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

## INC-2026-09-13（INC-158）watchdog v6.9 — 備援代答被誤判「卡死」，四次自動重置腰斬進行中對話
- 時間：2026-09-13 15:09 / 15:19 / 15:30 / 15:46（同日 4/4 用盡日上限）
- 錯誤：Session 膨脹監控連續自動重置四顆**正常工作中**的 Telegram session，使用者需反覆說「繼續未完成的優化」
- 根因：v6.3 的 `last_fail_seen`「45 分鐘內連續失敗 = dead」判準，遇上「DS 內容過濾每輪都擋、但 Gemini fallback 每輪都救回」的對話一律判死。實證：四顆的 CER 後 1-5 秒都有同 sid 的 Gemini `API call #N` 成功回傳（8/6/5/7 輪 ≥ CER 數），turn 皆 `Turn ended reason=text_response`。真因是 payload 內容觸發 DS 過濾庫（財務資料 + 15.8 萬 token 工具輸出；新 session 開不到 6 分鐘照樣被擋）→ 重置治不了，只腰斬工作
- 修正：watchdog v6.9（INC-158）dead 判定前加 `fallback_completed_since()` 前置關卡 — 失敗行後 15 分鐘內有非 deepseek 的 `API call #` 成功回傳 → 一律 alive 只推 ⚠️（persistent 不得覆蓋）；沒有這種行（備援也掛）才照舊判 dead 重置。⚠️ 文案加「連續 45 分鐘以上擋同一對話 → 建議改用 Gemini 主模型或開新對話」
- 驗證：沙箱 43 檢查全 PASS（新增情境 M 9/13 誤殺重現、N 備援也掛仍重置、O persistent 不覆蓋）；真 agent.log 重播四顆全部命中備援證據；真實 dry-run 靜默（stdout 空、exit 0）。備份 `session_bloat_watch.py.bak-20260913-v68`
- check_rule：CER 之後的卡死判準要看「備援有沒有真的回完（非 DS 的 `API call #`）」，不是「有沒有新訊息」也不是「有沒有啟動 fallback」；內容觸發型 CER（新 session 數分鐘內再犯）**不可用重置處理**
- CIO 複審（Gemini，deleg_ef2fb51a，2026-09-13 15:58）：**5 PASS / 2 PARTIAL / 0 FAIL**。缺口①「長期備援代答無升級機制」、缺口②「尾 2MB 掃描量是硬假設，agent.log 15 分鐘內長超 2MB 或輪替會漏證據 → 誤判卡死」→ 當日一次補完為 **v6.10**：⑬ `_scan_fb_window()` 擴讀（2MB→8MB→…→32MB）＋回頭讀 `agent.log.1`；⑭ `note_fb_escalation()` 連續備援代答 ≥3h → ❗ 升級告警（建議該對話 `/model gemini-2.5-flash` 或另開對話）、6h 節流、只通知不重置。沙箱擴至 **50 檢查全 PASS**（新增 P 尾窗不足擴讀、Q 4h 升級+節流、R 未滿 3h 不升級）；真 log 重播四顆仍全命中（耗時 0.05s／3.1MB）；dry-run 靜默 exit 0。備份 `.bak-20260913-v69`
- 狀態：✅ 已修正（v6.9 → v6.10 → v6.11，CIO 複審缺口 + 省錢分流已補完）
- 後續（9/13 省錢分流方案，使用者核准 A/B/D）：A1 watchdog ❗ 門檻 3h→連續 2 輪（v6.11）；B 每輪 context 成本紀律寫入 `hermes-context-cost-control` 技能；D `ds_balance_alert.py` 門檻改 ≤12 CNY/≤2 天（自算日耗、可覆寫測試）＋ cron 5b2209a814db resume
- C 項（9/13 核准後執行）：三支 agent cron 改 no_agent 零成本 — 晨間自動化→`morning_deploy.py`（順修 regenerate_report.py 緊急應變連結印 WindowsPath 清單的上游 bug）、收工登錄→`closing_log.py`、週四 budgeting→`budget_weekly_alert.py`；各在 longjiu_system + hermes/scripts 兩份；估省 NT$112/月（cron 16.5→12.5/日）。**更正原提案：monitor gate 對此類「輸入每天變」的 job 無效，正解是 no_agent 化**
- E 項（9/13 完成）：`daily_token_account.py`（no_agent，cron 0aa33e190bae 22:30）＝本機算今日 AI 成本帳 — 各模型 NT$（DS 尖峰×2/快取價）、DS/Gemini 分帳與 **Gemini 佔比（目標 <30%）**、cron 佔比與耗最多 job、DS 餘額與剩餘天數；資料源 agent.log(+.1)／usage_audit.jsonl／cost_log.csv，零 API。基線 9/13：DS NT$23.6、Gemini NT$42.2（佔 64%）、合計 NT$65.8
- 省錢分流方案 A/B/C/D/E 五項全部落地（9/13）

## INC-2026-09-13（INC-159）資料源/提交範圍/排程路徑三修（P0）
- 時間：2026-09-13 16:2x（使用者核准 P0-1/2/3）
- 錯誤①：預算報告讀到舊資料 → 誤報「台新 P1 超支 117.3%」。根因：`budget_daily_check._latest()` 只掃 repo 兩個目錄且取字典序第一個 → repo 僅有 7/27 匯出、最新 9/02 匯出在 `hermes/cache/documents/mb_0902/`。修法：跨目錄（含 cache 子目錄）蒐集並以**檔名日期最大**者為準；資料品質警語去硬編碼。驗證：資料日 7/27→2026-09-02，台新 −35.2% ✅、玉山 +5.7% ✅、四卡循環 25,494→15,793（−58.4%），僅剩永豐 P2（帳單 16,613 高於預算）。commit 1e004407
- 錯誤②：`radar_push.py` 用 `git add -A` → 9/13 一次把 **582 個無關的 `data/buffett_*`/`data/cto_*` 快取刪除**＋其他流程 6 檔掃進「auto: 雷達儀表板同步」commit（9573bedf）。影響面：該批快取為單日 LLM 快取，分析器只讀當日 → **對任何報告指標數字零影響**；唯一成本風險是同日快取被刪會讓同日重跑多付 NT$2-3（當日快取現為 0 檔）。修法：改白名單 add（`radar_state.json`/`radar_report_{TODAY}.html`/`index.html`）+ add 失敗即 return。驗證：髒檔誘餌測試 — 新 commit 97884836 只含 radar_report/radar_state 兩檔，BUDGET 報告等髒檔仍留在工作區未提交
- 錯誤③：每週日 DB 保養 job 9/13 05:00 失敗（`can't open file 'C:\c\Users\...\main.py'`）→ 本週 optimize-storage 未跑。根因：bash `$HOME`（MSYS `/c/...`）作為參數傳給原生 python.exe 被轉成 `C:\c\...`。修法：`HOME_WIN="$(cygpath -m "$HOME")"` 拼原生路徑，找不到即 exit 1（不再 fallback 被封鎖的 hermes shim）。驗證：手跑 SH_RC=0、log 見 done，備份輪替釋放 3,061 MB，index 已 compact 故 optimize 秒回
- check_rule：① 讀檔類腳本一律「跨目錄 + 以檔名日期取最新」，不可只掃 repo ② cron 自動 commit 一律白名單自身產物，並用髒檔誘餌驗證 ③ bash 呼叫原生 exe 的路徑參數一律 `cygpath -m` ④ 清快取禁刪當日檔
- 狀態：✅ 已修正（P0-1/2/3）；P1-4 snapshot 卡片口徑比對與 P2 待核

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
