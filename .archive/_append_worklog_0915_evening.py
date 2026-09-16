#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性：把 2026-09-15 晚間的修改與內容 append 進 work_log.json。
規則沿用 closing_log.py：date/category/item/detail、item 前 25 字去重、寫入前備份、寫入後驗證。
"""
import datetime as dt
import json
import shutil
from pathlib import Path

BASE = Path.home() / "Desktop" / "longjiu_system"
WORKLOG = BASE / "work_log.json"
DEDUP = 25
DATE = "2026-09-15"

NEW = [
    {
        "category": "修正",
        "item": "本週投資計劃標題日期動態化（institutional_flow.py；原寫死 8/29）",
        "detail": "標題字串寫死「8/29 全資產面結論」→ 16:15 雷達 cron 標題日期永久停在 8/29（內容一直是動態的）。"
                  "改 date.today()，與本檔後段寫入 radar_state.weekly_plan.日期 用同一運算式；刻意不讀 radar_state.json"
                  "（本次執行尚未寫檔，讀檔會拿到前一次日期 → 標題滯後一天，邊界測試證實）。"
                  "驗證：正式檔實跑標題 9/15、假 radar_state(9/14) 副本標題仍 9/15。commit 818365ca。",
    },
    {
        "category": "修正",
        "item": "寫死金額/日期批次修正（薪資 39,727、里程碑 8/31、乾粉分配、月配息 10 萬）＋死碼封存",
        "detail": "① calendar_sync.py 行事曆「台電薪資入帳 $39,727」（8 月值）→ 讀 snapshot.monthly_salary（42,560），"
                  "缺值顯示「金額待確認」不用歷史常數 ② build_rebalance_dashboard.py 新增 milestones_next()／dry_alloc()："
                  "里程碑改讀 schedule_events 未來事件（同日取一、排除已完成、上限 6 天）、乾粉段落與長條圖改讀 "
                  "snapshot.乾粉執行_0926.分配表，md + html 共用同一 helper ③ build_dashboard／monthly_report 移除薪資 fallback 39,727、"
                  "月報配息改讀 snapshot.dividend_month_expected（原寫死 100,000）④ 零引用死碼 complete_daily_report.py／"
                  "build_marriage_impact.py 封存 .archive/。驗證：AST 全過、parse_events 4 筆皆 42,560、再平衡儀表板無 8/31 殘留、"
                  "月報 0 筆 39,727、稽核四源/Pages 全綠。commit 027b84c0。",
    },
    {
        "category": "修正",
        "item": "收工稽核新增「寫死日期/金額」掃描（第 1b 區）＋退休/現金流文案舊薪資動態化",
        "detail": "_audit_closeout.py 掃現行 .py 的寫死日期/金額（計畫標題日期、「N月新增」、「N月台幣乾粉分配」、舊薪資 39,727），"
                  "排除 .archive/、_ 開頭檔、純註解行與含「寫死/舊/歷史/INC-/已作廢」的敘述行；"
                  "自踩修正：註解判斷原用單一 '#' → CSS 顏色 #22c55e 會把真缺陷誤放行，改 lstrip().startswith('#')。"
                  "build_retirement_plan.py、moneybook_6m_analysis.py 改讀 snapshot.monthly_salary／second_salary（後者並補 CSV 快取缺失的明確錯誤訊息）。"
                  "驗證：稽核 1b 由 ❌1 處轉 ✅0 處、退休報告實跑含「薪資 42,560 暫停後」。commit 9c4f67cc。",
    },
    {
        "category": "修正",
        "item": "日報基金部位顯示修正（補回 <p class=\"text-lead\"> 包裹與配息明細）",
        "detail": "run_daily.py 基金部位那行漏掉 <p class=\"text-lead\"> 包裹與 {_fund_detail}（配息明細）→ 段落破版、明細整段消失。"
                  "補回後日報 HTML 恢復正常。commit d27b1a77。",
    },
    {
        "category": "修正",
        "item": "收工稽核 TAG-BLOCKED-CODE／range-missing 誤報修正（新增 sha_state 四態判定）",
        "detail": "closeout_check.py 新增 sha_state(sha) → approved／remote／obsolete／pending：被閘門擋下或 range-missing 的 commit "
                  "若之後改走 RECORD 重做成新 commit，舊 commit 成孤兒卻仍在稽核掛 24h（每晚誤報一次），實際無事待處理。"
                  "現在只有 pending（仍在 HEAD 歷史、未上遠端、又無審查紀錄）才列 ❌，其餘列 ℹ️ 已解決並附原因。commit d27b1a77。",
    },
    {
        "category": "完成",
        "item": "9/15 離峰A 治理：P2 推送通道遷移條目補標完成 ＋ Google Sheets 薪資表整合計畫（待核准）",
        "detail": "schedule_events.json 的 9/15 P2 條目改 ✅（9/14 已完成，勿重做）；Google Sheets 條目加註計畫已產出。"
                  "新增 GSHEETS_CASHFLOW_INTEGRATION_PLAN.md（含零引用死碼 .archive/ 註記）→ 待使用者核准。commit 86f3a0c7。",
    },
    {
        "category": "完成",
        "item": "9/15 更新總整理（收工）：32 commits、4 筆 INC、寫死日期/金額批次動態化",
        "detail": "今日 32 commits（afcd5fb0→78fd2a04），雙分支同步。晚間主線＝寫死日期/金額批次動態化（薪資 42,560／"
                  "里程碑＋乾粉改讀 schedule_events 與 snapshot／月配息 100,000 移除／radar 標題日期）＋稽核新增 1b 類＋"
                  "收工稽核誤報修正（sha_state）。當日 INC：186 穿透五桶被縮放防呆灌大（幽靈扣減 498 萬 ×1.652；真值 台7.5／美40.6／防17.4／債27.6／現3.4）、"
                  "187 門檻散落 7 處→snapshot.thresholds_2026_0915 單一真值＋check_thresholds.py、"
                  "188 日報基金部位用反推錯帳（鉅亨真值 822,162；禁 A−B 反推）、189 Contents API 逐檔上傳卡死兩分支（歷史重建）。"
                  "產物重產：日報／再平衡儀表板＋評估／月報／退休規劃／index.html；index.html 與線上 Pages 逐字一致、無殘留佔位符。",
    },
]


def main() -> int:
    log = json.loads(WORKLOG.read_text(encoding="utf-8"))
    if not isinstance(log, list):
        print("❌ work_log.json 不是陣列，中止")
        return 2
    keys = [str(x.get("item", ""))[:DEDUP] for x in log if isinstance(x, dict)]

    def dup(item: str) -> bool:
        k = item[:DEDUP]
        if k in keys:
            return True
        return any(e and (item.startswith(e) or k.startswith(e)) for e in keys)

    rows = [{"date": DATE, "category": n["category"], "item": n["item"][:180],
             "detail": n["detail"][:120]} for n in NEW]
    # detail 上限比照 closing_log（120）會截掉重點 → 保留完整 detail，長度不截
    rows = [dict(r, detail=n["detail"]) for r, n in zip(rows, NEW)]
    rows = [r for r in rows if not dup(r["item"])]
    if not rows:
        print("ℹ️ 全部重複，未新增")
        return 0

    bak = WORKLOG.with_name(f"work_log.json.bak-{dt.datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(WORKLOG, bak)
    merged = log + rows
    WORKLOG.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    check = json.loads(WORKLOG.read_text(encoding="utf-8"))
    if not isinstance(check, list) or len(check) != len(merged):
        shutil.copy2(bak, WORKLOG)
        print("❌ 驗證失敗，已還原")
        return 3
    print(f"✅ 已新增 {len(rows)} 筆（work_log {len(log)}→{len(merged)}；備份 {bak.name}）")
    for r in rows:
        print(" -", r["category"], "|", r["item"][:80])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
