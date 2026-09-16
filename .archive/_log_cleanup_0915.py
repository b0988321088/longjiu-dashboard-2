# -*- coding: utf-8 -*-
"""一次性：把今晚（9/15）對保查證＋衝突加註＋過去事件/過時檔案清理登錄 work_log.json。"""
import json, pathlib

P = pathlib.Path('work_log.json')
d = json.loads(P.read_text(encoding='utf-8'))
before = len(d)

new = [
    dict(date='2026-09-15', category='查證', 
         item='對保狀態查證：Gmail/本機皆無對保證據 → 維持「未對保」',
         detail='使用者要求查證 9/11 質押是否已對保。查證方式：①Gmail 搜「國泰 質押／對保／撥款／專業投資人／板橋」（after:2026/09/05）→ 僅行銷信與 9/12 消費彙整通知，無銀行對保/撥款通知 ②本機 find 質押/對保/國泰 相關文件截圖 → 無 ③產線腳本 grep「對保完成」→ 無硬編碼。結論：系統內唯一權威為使用者 9/12 更正（9/11 僅完成質押額度核定，未對保）；9/13 日報與週報的「對保完成」為當日產線文字錯誤。現行口徑維持「額度已核定、未對保、預估 ~9/25 撥款」，待使用者向國泰確認或等撥款事實關帳。'),
    dict(date='2026-09-15', category='修正',
         item='事實衝突處理：9/13 日報＋週報「對保完成」加註更正橫幅',
         detail='衝突點：daily_report_v2_2026-09-13.html（1 處「對保完成待撥款」）與 dynamic_weekly_review_2026-09-13.html（4 處「9/11 對保完成」）vs 使用者 9/12 更正「未對保」＋entry_plan.json／entry_monitor.py／notion_shared_context.md 的正確口徑。處理原則比照口徑清查：歷史檔不竄改內容，於 <body> 後插入橘色更正橫幅（「⛔ 2026-09-15 更正：9/11 僅完成質押額度核定、尚未對保」），兩檔各 1 處橫幅。'),
    dict(date='2026-09-15', category='修正',
         item='過去事件清理：schedule_events 82→69、pending 16→15、dashboard 404、備份 73→38',
         detail='依使用者指示「過去的事件的刪除」。①schedule_events.json：移除 13 筆 2026-08-01 前已過期行程（7/11 台南、7/17 段部上課/辦理國泰轉貸、7/19 打牌/給媽媽稅金、7/21 轉 79 萬星展、7/24 確認轉貸進度、7/27 台新扣款、7/29 峨眉初驗 等），歸檔 .archive/removed_schedule_events_2026h1.json。②pending_decisions.json 16→15、dashboard_decisions.json pending 11→10：移除已結案且 9/1 前者（9 月保單轉換定案卡，已結案）。③備份檔 73→38（每類保留最新 2，其餘刪；git 歷史與 snapshot 本體保留）。④dashboard_decisions.decisions 394 筆（記憶/審計日誌）不動。'),
    dict(date='2026-09-15', category='修正',
         item='過時檔案刪除：7 月期文件 7 份',
         detail='刪除 DAILY_CHECKLIST_20260713.md、EVOLUTION_PLAN_2026-07-16.md、CIO_EVOLUTION_2026-07-16.md、FIXLOG_2026-07-18.md、framework_snapshot_2026-07-10.json、asset_pledge_plan.txt、國泰世華辦事指引_20260713.md（共約 54KB）；內容已入 git 歷史，本機副本移至 .archive/。'),
    dict(date='2026-09-15', category='修正',
         item='淘汰腳本刪除：產線 4 支（0 引用）＋ ad-hoc 11 支（移入 .archive）',
         detail='產線腳本 build_pptx.py、build_rate_hike_dashboard.py、gen_emergency_us_0914.py、gen_emergency_us_0915.py：實查 0 引用（import/subprocess/cron 皆無）後刪除（共 1016 行）。一次性 ad-hoc 腳本 11 支（_canonicalize_stale_records/2、_clean_rebalance_dashboard、_fix_stale_text、_remove_hardcoded_weekly_plan、_snapshot_pledge_canonical_20260913、_sync_pledge_text/2/3、_verify_notion_decision、_verify_receivable）移至 .archive/（內容保留）。CIO 複審 APPROVE 後推送。'),
    dict(date='2026-09-15', category='修正',
         item='過期事件擴大清理：schedule_events 69→53（使用者指示「過期/已決定的事件一直放著沒意思」）',
         detail='①跑既有機制 schedule_events_weekly_clean.py（9/4 核准的每週收尾腳本，cron 週日 08:00）→ 自動刪 14 筆：已完成/已結案（9/5 轉換生效、9/8 T+4 截止、9/10 例行檢核、9/10 洲際W洽談已暫緩、9/11 CPI、9/11 Gate 複核、9/11 質押簽約、9/14 配息基準日維持不轉換）＋純提醒類過期行程 6 筆（8/1 高雄二日遊、8/3 體檢、8/4 地政、8/7 教育訓練、8/13 新展、8/2 轉貸預計完成）→ commit 6e3dbe60。②再刪垃圾/測試殘留 2 筆（date=「待處理」的 0050 配息確認、date=4050-04-18 的測試行程）。保留 3 筆「過期但仍在追蹤」事件（9/1 標案前置、9/1 洲際W 已延後、9/10 FJ33→M&G 轉換中 T+4）—— 屬追蹤語意，依既有規則不自動刪。'),
    dict(date='2026-09-15', category='修正',
         item='已決定待辦卡清理：pending_decisions 15→12、dashboard 待辦 10→9',
         detail='依「已決定的事件留著沒意思」刪除 status 以 ✅/☑/❌ 開頭的已定案卡：①第一金 FA81→FJ33 摩根（☑ 9/1 已送出，已被 9/10 FJ33→M&G 取代）②9/12 週六再平衡自動減碼（✅ 已核准並執行）③0050 加碼評估（✅ 9/15 已定案不增）。保留追蹤中的卡（⏳ 待觸發／🔄 執行中／🟡 部分執行／⏸️ 凍結／📌 已定調待時機，共 12 張）。dashboard_decisions.decisions 394 筆為代理記憶／審計日誌，屬歷史紀錄不刪。'),
    dict(date='2026-09-15', category='完成',
         item='9/15 儀表板重產＋三顆 commit 推送（清理總收尾）',
         detail='本機重產 index.html（placeholder 殘留 0）、閉環稽核全部通過 ✅；推送 c607ab3c（清理資料層）+5ff58057（刪除腳本）+e9b230fc（刪辦事指引），clean-main/main 雙分支同步。備註：使用者已裁示不做資料公開治理（維持公開 Pages），本次不再提。'),
]

d.extend(new)
P.write_text(json.dumps(d, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
json.loads(P.read_text(encoding='utf-8'))
print(f'work_log: {before} → {len(d)} 筆（新增 {len(new)}）')
for e in new:
    print('  +', e['category'], '|', e['item'][:56])
