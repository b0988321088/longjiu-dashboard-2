# 2026-09-14 更新總整理（9/14 收工）

> 今日 48 個 commit（`738d8cb5` → `1cd39d7d`），全部已推 GitHub；clean-main 與 main 同步於 `1cd39d7d`。
> 分類：四源同步/報表 12｜閘門/治理 10｜其他 9｜成本 6｜監控/稽核 6｜Notion 5

---

## 一、推送閘門與治理（今日主線）

**閘門演進 v2 → v4.1**（CIO 每輪都真的審過，全部走 RECORD 落地）

| 版本 | commit | 內容 |
|------|--------|------|
| v2 | `659eaa34` | 審查紀錄改綁 **tree hash**（`.git/CIO_APPROVED`），取代可自打的 `[cioreviewed]`；新增 `cio_approve.py` |
| v3 | `17baa7d2` | 逐 commit 驗**推送範圍**（不是只看 HEAD）；通道留痕 `PUSH_LANE.log`；reviewer/note sanitize |
| v3+ | `5a0f8b9e` | `cio_approve.py --range-base`（整段範圍一次落地）＋ `--status` 未推 commit 審查狀態 |
| **v4** | `9e5c3321` | **程式檔不得走 `[cioreviewed]` 標籤通道**（擋 `TAG-BLOCKED-CODE`）；`[skipreview]` 含程式檔記 `SKIPREVIEW-CODE` 留痕；每日通道稽核 |
| **v4.1** | `1cd39d7d` | 補**改名繞過**（`--name-status -M` 舊/新路徑都驗）＋清死碼 `git_env`/舊檔頭 |

**P0 推送路徑治理（9/14 使用者核准）**
- 4 處對 `main` 的裸 `--force` → `--force-with-lease`：`regenerate_report.py`（07:00 路徑）、`pre-run.sh`、`refresh_all.py`、`schedule_events_weekly_clean.py`
- 週日 08:00 行事曆收尾：commit 補 `[cioreviewed]`（原靠**已失效**的 `PUSH_FORCE_OK`，9/20 起會靜默斷推）＋移除死碼
- `safe_update.py`：CIO 審查未過改**硬擋**（原只印警告照推）
- `closeout_check.py` 新增 **③ 推送通道稽核**（近 24h 各通道次數，異常列入問題）

**關鍵事實（全 repo 實掃 17 條推送路徑）**：真的跑過審查的只有 `regenerate_report.py` 與 `daily_deploy.py`；其餘 13 腳本＋4 條 cron prompt 原本全靠自打標籤。

**P2 已排定 9/15**：工單 `P2_PUSH_LANE_MIGRATION_PLAN.md`；行事曆事件已建、Google 日曆已回查確認。

---

## 二、成本治理（L1/L4）

- **INC-173**（`fc5c2665`）：`daily_token_account.py` 單價表三處錯誤 → 成本高估 1.6 倍（9/13 NT$498 → **NT$313**）。DS 快取 0.007→0.003、miss 0.22→0.15、out 0.66→0.60；Gemini 快取 0.075→0.03；補 3.6-flash/3.1-flash-lite/2.5-flash-lite
- **INC-174**（`39507c7b`、`ea90225c`）：失敗統計未去重（「額度耗盡 61 次」→ 實際 **57** 件）＋成因誤判（不是餘額耗盡，是**每分鐘輸入 token 速率上限**）
- **成本帳新增失敗統計**（`9b9ed57b`）：CER/429 去重計數（L1 監控）
- **匯率校正**（`dd8947cb`）：CNY_TWD 4.2→4.73、USD_TWD 31.5→31.7；4 檔成本腳本改具名常數
- **Notion 訂閱已無**（`f3e64ec6`）：月固定費 461→**81 台幣**
- **context 尺寸治理定案**：compression threshold 0.5→0.30、proactive prune 0→120,000、min_result_chars 8,000→6,000（技能索引歸檔＝不做，效益近零）

---

## 三、監控與自動化

- **INC-172**（`e1d97244`）：手動 fire 會吃掉下一個排程時點（5 個 job 中彈）→ 稽核第 8 類＋`release_claimed_occurrences.py`＋`closeout_check.py`；`ds_balance_alert` 門檻 12→30 CNY／2→3 天
- **收工檢查自動化**（`4c9caf6d`、`ca055b74`）：`closeout_check.py --silent-ok`＋cron **22:40**（no_agent，全綠靜默、有問題才吐報告）
- **INC-175**（`f8a5761e`）：watchdog v6.13 — 尺寸規則不再清理已輪替的死 session（停掉假事故通知）
- 稽核器修正 3 筆（`f64dc328`、`71b04997`、`b2cb583c`）：基準日 T 動態化、歷史列改全歷史重疊日一致性、髒檔改用 `git diff --name-only`

---

## 四、資產真值與報表（9/14 真值日）

- **真值日四源同步**（`66a9df06`，10 張截圖＋Moneybook 9/14）：現金 **885,890**／證券 **2,922,190**／基金 **12,647,084**（含 B11 在途 500 萬）／保單 **7,580,361**／當月配息 **109,371**
- **美元曝險口徑定案 59.0%**（`5900a6ba`，引擎口徑、B11 不重複計入）→ snapshot/radar_state/緊急應變/利率情境/週報/日報/儀表板全同步
- **緊急應變重跑**（`1b85c387`）：六章節 2,857 字＋market_snapshot KPI；修掉台股證券舊值
- **配息桶別修正**（`66411e59`）：00878/00983D 歸 ETF（原誤入基金桶）→ 保單 36,228／ETF 16,340／基金 56,803
- **儀表板**：被動收入條改動態（移除寫死 18/45/36%、135%、薪水 39,727 等，`af343aa6`）；新增「📈 升息情境」連結與儀表板（`ed027ee2`、`b707bb8e`）
- **再平衡評估 HTML 產生器補上**（`9b26db7f`、`07d2d029`）：原缺產生器導致按鈕停在 9/5

---

## 五、今日 INC 登記（4 筆，`error_register.md`）

INC-172 手動 fire 吃排程時點｜INC-173 成本高估 1.6 倍｜INC-174 失敗統計未去重＋429 成因誤判｜INC-175 watchdog 清理已輪替死 session

---

## 六、待辦（明日之後）

- **9/15（已排）**：P2 — 13 條推送路徑遷移 RECORD（工單 `P2_PUSH_LANE_MIGRATION_PLAN.md`）
- **DS 儲值**：餘額 8.02 CNY ≈ 0.8 天，歸零後全流量走 12 倍單價的 Gemini（最大成本風險）
- **9/16**：FOMC；第一金 FJ33→M&G T+4 生效 → 更新 firstjin 成分／重算穿透（債券桶↑ 美股桶↓）
- 成本治理驗證點：9/15 比對 `agent.log` in= p50/p90 與每日成本帳

---

*產出：Hermes（9/14 收工整理）。資料來源：git log、`work_log.json`（9 筆）、`error_register.md`、`PUSH_LANE.log`、`dashboard_decisions.json`*

---

## 七、收工後追加（14:00 之後）

- **DS 儲值入帳修復**（`bf7b076e`）：使用者儲值 8.02 → 198.25 CNY；查出 `cost_monitor.save_entry()` 見當天已有記錄就早退 → 當天儲值永不入帳 → 隔天 09:00 會發「建議儲值」假警報。改為「同日跳升（儲值）破例寫一列、同日下降仍略過」；沙箱 4 案例＋實跑驗證、`ds_balance_alert` 恢復靜默。
- **收工稽核去硬編碼**（`2bc6c17f`）：22:40 每晚假 ❌（信用卡寫死 34,025，真值 9/14 已 60,810；應收款寫死 290,500）→ 三處改跨源動態比對（含 GitHub Pages 線上那條，CIO 首輪 REJECT 指出）。
- **INC-176：`cio_approve.py --range-base` 替未審 commit 背書**（`9d765476`）：自踩自修 —— 記錄範圍現在必須是審查 JSON 真的有涵蓋的 commit（認 `reviewed_tree`），未涵蓋者列示略過，全未命中拒寫；被 REJECT 的 tree 改寫 commit 讓它不進推送範圍。
- **今日總計**：本日累計 **52 個 commit**（`738d8cb5` → `9d765476`，此數字不含本記錄本身的 commit），clean-main ＝ main ＝ `9d765476`；INC 共 5 筆（172/173/174/175/176）。
- **CIO 審查**：本日共 6 輪（v2→v4.1 五輪＋成本/稽核各輪），其中 2 輪 REJECT（都是真問題：v2 的 HEAD-only 驗證、稽核漏改 Pages 那行），全部修完才推。
