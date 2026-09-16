#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""登錄今晚（2026-09-15）「舊質押口徑全面清查」的成果：work_log + error_register（INC-190）。
規則沿用 closing_log.py：date/category/item/detail、item 前 25 字去重、寫入前備份、寫入後驗證。
"""
import json
import shutil
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
TPE = timezone(timedelta(hours=8))
TODAY = "2026-09-15"
STAMP = datetime.now(TPE).strftime("%Y%m%d-%H%M%S")

ENTRIES = [
    {"date": TODAY, "category": "完成",
     "item": "舊質押口徑全面清查（MMF＝標案預備金／700萬池押350萬）— 現行層 47 處",
     "detail": "使用者指示「全面檢視並刪除過去的錯誤」。清查範圍＝現行讀取源（snapshot／pending_decisions／dashboard_decisions／schedule_events／entry_plan／calendar_overdue）＋產出腳本＋技能庫＋Notion 共享脈絡。"
                "舊說法三種：①MMF 500/600萬＝10月標案預備金 ②擔保池 700萬×50%＝質押 350萬@2.8% ③10月押標金 240萬由質押撥款餘額支應。現行真值：MMF 9/9 贖回、9/11 轉申購貝萊德B11 → 擔保池 1,200萬×4.5成＝540萬@2.77%（9/11 額度核定、未對保、~9/25 撥款）→ 全數清償 500萬高息負債；押標金來源延 9 月底評估。"
                "做法：舊句一律保留但標「⛔ 已作廢（9/12 取代）＋現行值」（不刪歷史，可追溯）。驗收：現行欄位未標記舊口徑=0、產出物（大轉向 pptx）700萬/350萬=0、國泰貨幣市場基金 key 0 次（原本會印「0 元＝500萬標案預備金」）。"},
    {"date": TODAY, "category": "修正",
     "item": "產出腳本口徑更正 5 檔（大轉向簡報／債務追蹤／稽核儀表板／週報／進場監控）",
     "detail": "build_final.py（含反向寫法「500 萬 MMF」6 處、改讀 B11 實際市值 4,981,060）、debt_restructure_tracker.py（8/20 舊劇本 2 處）、build_audit_dashboard.py（8/25 T+2 與「MMF 剩餘 369萬轉配置」＋歷史推導行標註）、build_weekly_report.py（富達+MMF600萬→台幣貨基500萬）、entry_monitor.py（質押 350萬→540萬）。"
                "CIO 首輪 REJECT（抓到反向寫法漏改 V2/V4/V5），補修後複審 APPROVE（兩顆 commit、tree 972ae8ba／aaf9e66b，V1-V7 全過）。"},
    {"date": TODAY, "category": "完成",
     "item": "技能庫口徑更新 18 支（橫幅）＋9 支就地更正；測試垃圾頁刪除 5 檔",
     "detail": "技能：debt-restructure-execution/arbitrage-engine、financial-report-calibration、fund-component-breakdown/penetration、investment-philosophy、dynamic-asset-allocation、rebalance-monitoring-sop、longjiu-cashflow-analysis、macro-regime-daa-v3、buffett-style-asset-analysis、asset-penetration-update-sop、dashboard-single-source、longjiu-pipeline-governance、python-rendering-pitfalls 等 18 支加「口徑更新（9/15 清查）」橫幅；就地更正 9 支（質押息 8,083→12,465/月、funds_cathay 富達+聯博+B11=11,805,982、投資哲學「目前進行式」等）。"
                "垃圾檔：_css_tab_test／_def_test／_final_css_test／_restore_test／_live_check.html（含大量舊文案的測試殘檔）git rm。"},
    {"date": TODAY, "category": "修正",
     "item": "INC-190：auto_record 遇中文檔名誤擋推送（core.quotepath）",
     "detail": "推送 6 顆 commit 時 auto_record 檢查②回報「大轉向資產配置策略_final.pptx 不存在於工作區」→ 拒落 RECORD、整批不推。"
                "根因：auto_record.py 第 72 行用 `git diff-tree --name-status`（無 -z、無 quotepath 設定）→ 中文檔名被 git 輸出成 \"\\345\\244\\247...\" 轉義字串，存在性檢查找不到檔 → 誤擋。"
                "處置：`git config core.quotepath false`（repo 層設定，非程式改動）後同指令重跑成功，6 顆 commit 全數補落 RECORD 並推送、遠端 sha 驗證通過。"
                "待辦（下次改程式時一起做）：auto_record.py 第 72 行改加 `-z` 或 `-c core.quotepath=false`，讓此類誤擋在程式層根除。"},
    {"date": TODAY, "category": "完成",
     "item": "9/15 深夜口徑清查總整理：8 顆 commit、INC-190、現行層 47 處",
     "detail": "commits dd1f10bd（資料層＋刪 5 檔）→74effeb9（腳本）→c060bfb4（Notion 共享脈絡重產）→a3549a97（第二輪 snapshot 18 處）→f2d08930（補漏）→fb8c6321（第三輪 plan_0820_final 全標作廢）等，雙分支同步 HEAD=fb8c6321。"
                "另發現兩件事實矛盾待使用者確認：①對保狀態（9/12 使用者更正＝未對保 vs 9/13 週報誤記「對保完成」）②dragon_assets.db 少 2026-08-15 列＝nightly_maintenance 刪 30 天前的設計行為。"
                "歷史層（過去日期的日報/週報/穿透報告、備份、work_log 舊紀錄、error_register 既有條目）刻意不動，等使用者指示。"},
]


def append_worklog():
    p = BASE / "work_log.json"
    shutil.copy2(p, BASE / f"work_log.json.bak-{STAMP}")
    data = json.loads(p.read_text(encoding="utf-8"))
    seen = {str(e.get("item", ""))[:25] for e in data}
    added = []
    for e in ENTRIES:
        if e["item"][:25] in seen:
            continue
        data.append(e)
        seen.add(e["item"][:25])
        added.append(e["item"])
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    chk = json.loads(p.read_text(encoding="utf-8"))
    assert len(chk) == len(data)
    print(f"✅ work_log {len(data)-len(added)}→{len(data)} 筆（新增 {len(added)}）")
    for a in added:
        print("   -", a[:80])


def append_inc():
    # 1) inc_events.jsonl
    p = BASE / "inc_events.jsonl"
    now = datetime.now(TPE).isoformat()
    ev = {"id": str(uuid.uuid4()), "ts": now, "source": "stale_pledge_purge",
          "snapshot_date": TODAY,
          "errors": ["auto_record 遇中文檔名誤擋推送（git diff-tree 未 -z／未設 core.quotepath=false）"],
          "severity": "P2", "status": "fixed", "count": 1, "first_seen": now, "last_seen": now}
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print("✅ inc_events.jsonl 已登錄")

    # 2) error_register.md：表格列 + 章節
    er = BASE / "error_register.md"
    shutil.copy2(er, BASE / f"error_register.md.bak-{STAMP}")
    t = er.read_text(encoding="utf-8")
    row = ("| auto_record 遇中文檔名誤擋推送 | 2026-09-15 | 已解（INC-190）｜待程式層根除 | "
           "`git diff-tree --name-status`（無 -z、未設 quotepath）→ 中文檔名被轉義成 \\345\\244\\247… → "
           "存在性檢查找不到檔 → 拒落 RECORD、整批不推。以 `git config core.quotepath false` 解除；"
           "待辦：auto_record.py:72 加 -z 或 -c core.quotepath=false |")
    anchor = "| 穿透五桶被縮放防呆灌大（債券假超標 199 萬） |"
    if "INC-190" not in t and anchor in t:
        idx = t.index(anchor)
        end = t.index("\n", idx)
        t = t[:end + 1] + row + "\n" + t[end + 1:]
        print("✅ error_register 表格列已補")
    elif "INC-190" in t:
        print("ℹ️ error_register 已有 INC-190，略過")

    sec = """
## INC-190 auto_record 遇中文檔名誤擋推送（2026-09-15）
- 症狀：推送 6 顆 commit 時 auto_record 檢查② 回報「大轉向資產配置策略_final.pptx 不存在於工作區」→ 拒落 RECORD → auto_push 整批不推（rc=0 但遠端未前進）。
- 根因：`auto_record.py:72` 用 `git diff-tree --no-commit-id --name-status -M -r <sha>` 取變更檔清單，**沒有 `-z`、也沒設 `core.quotepath=false`** → 非 ASCII 檔名被 git 轉義成 `"\\345\\244\\247..."` 形式，後續 `Path.exists()` 檢查自然找不到 → 誤判為缺檔。
- 修法（本次）：`git config core.quotepath false`（repo 層設定，不動程式）；同指令重跑即通過，6 顆 commit 全數補落 RECORD、推送成功（HEAD fb8c6321，雙分支 sha 驗證）。
- check_rule：① 任何地方解析 git 檔名清單都要 `-z` 或明確設 `core.quotepath=false`；② 見「某檔不存在於工作區」但 `ls` 看得到 → 先懷疑 git 輸出轉義，不要重跑或改資料。
- 待辦：auto_record.py:72 改加 `-z`（程式層根除），改動須走 CIO 真審。
"""
    if "## INC-190" not in t:
        marker = "## INC-186 穿透五桶被縮放防呆灌大（2026-09-15）"
        t = t.replace(marker, sec + "\n" + marker, 1)
        print("✅ error_register INC-190 章節已補")
    er.write_text(t, encoding="utf-8")


append_worklog()
append_inc()
