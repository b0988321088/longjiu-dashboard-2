#!/usr/bin/env python3
"""sync_all.py — 龍九一鍵同步管線 v2（2026-08-24 檢討修正）
依序執行：資產驗證 → 日報 → 緊急應變 → 穿透 → 四源 → 同義欄位 → 一致性 → 再平衡/週報
v2 修正：①加入 asset_sync.py（同義欄位驗證，2026-08-24 血淚：漏欄位不抓）②輸出完整（非只 tail）③失敗即停
用法：python sync_all.py [date]
"""
import subprocess, sys, datetime, json
from pathlib import Path

def _validate_date_format(date_str):
    try:
        # Strict YYYY-MM-DD format check
        parsed_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        # Round-trip check to ensure no partial matches like '2026-09-12extra'
        if parsed_date.strftime("%Y-%m-%d") == date_str:
            return date_str
    except ValueError:
        pass
    return None


BASE = Path(__file__).resolve().parent

def run(label, cmd, timeout=300, stop_on_fail=True):
    print(f"\n=== {label} ===")
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(BASE), capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        # 印出關鍵輸出（成功/失敗標記）
        for line in (out or "").splitlines()[-3:]:
            if any(k in line for k in ["✅", "❌", "⚠️", "同步", "一致", "完成", "記憶已寫入"]):
                print("  " + line.strip()[:100])
        if r.returncode != 0:
            for line in (err or "").splitlines()[-2:]:
                print("  ⚠️ " + line.strip()[:100])
            if stop_on_fail:
                print("⛔ 失敗中止（後續步驟未執行）")
                return False
        return r.returncode == 0
    except Exception as e:
        print(f"❌ {e}")
        return False

def main():
    if len(sys.argv) > 1:
        today_arg = sys.argv[1]
        today = _validate_date_format(today_arg)
        if today is None:
            print(f"❌ 無效的日期參數 '{today_arg}'. 請使用 YYYY-MM-DD 格式 (例如: 2026-09-12).")
            sys.exit(2)
    else:
        today = datetime.date.today().strftime("%Y-%m-%d")

    print(f"🔁 龍九一鍵同步 v4（{today}）")
    # v4 檢查 0：儀表板模板硬編碼檢查（2026-08-25：改口徑後 index_template.html 殘留舊值 → 儀表板顯示舊數字）
    # ⚠️ 2026-08-29：勿把「rep dict 錨點值」（35,583/63,027/2,723,839 等）加入此清單 —
    #     模板保留錨點是 build_dashboard 替換機制的正常設計，含錨點≠殘留；
    #     殘留檢查應針對「產出檔 index.html」（見「儀表板產出驗證」步驟）
    try:
        _tpl = (BASE / "index_template.html").read_text(encoding="utf-8")
        _stale = ["152,781", "141,958", "73,137", "27,319", "156,835", "151,958", "143.9%", "144%", "800,272"]
        _hits = [s for s in _stale if s in _tpl]
        if _hits:
            print(f"  ⚠️ index_template.html 殘留舊口徑硬編碼: {_hits} — 儀表板會顯示舊數字，請修正 template（改 monthly_expense 後必查）")
        else:
            print("  ✅ 儀表板模板無舊口徑硬編碼")
    except Exception as e:
        print(f"  ⚠️ 儀表板模板檢查失敗: {e}")
    # v3 自動修復 1：snapshot.date 同步為 today（2026-08-25 血淚：date 停在 8/24 → four_source 檢查舊日期 → 假失敗）
    try:
        sp = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        if sp.get("date") != today:
            old = sp.get("date")
            sp["date"] = today
            (BASE / "snapshot.json").write_text(json.dumps(sp, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
            print(f"  🔧 snapshot.date {old} → {today}")
    except Exception as e:
        print(f"  ⚠️ snapshot.date 修復失敗: {e}")
    # 2026-08-31 血淚：total_assets 必須 = 保險+證券+基金+現金 動態重算（禁止差額法 — 上次只加現金差額漏 sec/fund → 穿透檢查抓「總資產不一致」）
    # 手動改 snapshot 後跑 sync_all 也會自動校正
    try:
        sp2 = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        _ta = (sp2.get("insurance_total", 0) or 0) + (sp2.get("securities_total_market_value", 0) or 0) \
            + (sp2.get("fund_market", 0) or 0) + (sp2.get("cash_total", 0) or 0)
        if abs((sp2.get("total_assets", 0) or 0) - _ta) > 1:
            _old_ta = sp2.get("total_assets")
            sp2["total_assets"] = _ta
            (BASE / "snapshot.json").write_text(json.dumps(sp2, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
            print(f"  🔧 total_assets 自動重算 {_old_ta:,} → {_ta:,}（= ins+sec+fund+cash）")
    except Exception as e:
        print(f"  ⚠️ total_assets 重算失敗: {e}")
    # （2026-08-27：gen_emergency_*.py 已刪除，此自動建立邏輯移除；緊急應變僅 emergency_1330.py）
    steps = [
        # 2026-09-12 新增（INC-156）：致命類靜態閘門 — F821 未定義名稱／F823 先用後賦值／
        #     F811 重複定義／F601 重複 dict key。血淚：同日全庫掃描 341 筆中僅 7 筆會炸，
        #     但 run_daily.py 的 `intel_text`、`timedelta` 遮蔽、`monthly_income` 重複 key
        #     全靠人工看才發現；此步讓它們在產報前就被自動擋下。
        ("靜態閘門", "python static_gate.py"),
        # 2026-09-15 INC-187：門檻單一真值檢查（SoT 完整性 + 消費端引用 + 舊門檻字面殘留）
        ("門檻SoT檢查", "python check_thresholds.py"),
        ("同義欄位驗證", "python asset_sync.py"),
        ("日報", "python run_daily.py"),
        # 2026-09-02 血淚：緊急應變必須在穿透報告「之後」執行 — emergency_1330.py 讀的是
        # snapshot.penetration.actual_pct 快取，穿透報告才寫入；順序反了會用到上一輪舊值
        # → check_penetration_consistency 擋推送（上午實踩 3 次）
        ("穿透報告", "python build_penetration_report.py"),
        ("台股緊急應變", "python emergency_1330.py"),
        ("四源同步", "python four_source_sync.py"),
        ("同義欄位複驗", "python asset_sync.py"),
        ("一致性檢查", f"python check_penetration_consistency.py {today}"),
        ("再平衡報告", "python build_rebalance_report.py"),
        # 2026-08-29：再平衡儀表板（雷達+政策面+本週投資計劃）— 之前 sync_all 漏跑，導致雷達更新後儀表板舊
        ("再平衡儀表板", "python build_rebalance_dashboard.py"),
        # 2026-09-06：雷達週計畫重產 — institutional_flow.py 更新 radar_state.weekly_plan
        #     （行動儀表板 JS 即時讀取）。血淚：rotation_engine 修正後沒人重跑 → weekly_plan 殘留舊建議
        #     （「乾粉優先醫療」），使用者抓包；加此步驟確保 sync_all 後行動儀表板與引擎同步
        ("雷達週計畫重產", "python institutional_flow.py"),
        # 2026-09-21 治本（INC-234）：雷達資金流更新後必須重算產業輪動建議，並以守衛驗證
        #     ① 建議依據的雷達時間 == 現行 radar_state.sector_flow.generated_at（不得落後）
        #     ② 產業現況不得全為 0（防呼叫端誤傳整份 snapshot → 全部算成最大缺口）
        #     血淚：9/21 金融資金分數停在 9/20 的 -3，被誤列「避開」；日報/儀表板/LLM 全複述。
        #     （institutional_flow.py 內部已在算完 sector_flow 後就地重算，此步純守衛）
        ("產業輪動一致性", "python check_rotation_freshness.py"),
        ("儀表板注入", "python build_dashboard.py"),
        # 2026-08-29 v4：雷達資料同步驗證（radar_state.json 存在 + 政策面非空 + 三處產出含雷達結論）
        #     血淚：institutional_flow.py 讀 policy_notes 用 .get("內容") 但結構是新聞dict → 政策面空白沒人發現
        ("雷達同步驗證", "python -c \"import json; r=json.load(open('radar_state.json',encoding='utf-8')); pn=r.get('policy_notes') or {}; assert any(str(_k).startswith('新聞') for _k in pn) or pn.get('原油綜合判斷'), '❌ radar_state.policy_notes 空白'; sig=r.get('signals') or {}; assert sig, '❌ radar_state.signals 空白'; print('✅ 雷達資料完整（signals', len(sig), '項 + 政策面', len(pn), '筆）')\""),
        # 2026-08-29：產出後驗證 index.html 無配息舊值殘留（build_dashboard rep dict 漏替換防呆）
        # 清單 = 配息口徑舊值 + 穿透卡五桶舊市值 + 保單A舊值 + 當月已收舊值（8/29 血淚全量盤點）+ 監控卡片合計舊值
        # ⚠️ 2026-08-29 v2 血淚：JS 內硬編碼 fallback（Script 6 入帳清單 ['房租已收', 78000] / || 62969）不在 rep dict 範圍 —
        #     build_dashboard 只 rep HTML 顯示值，JS 陣列內的數字是獨立硬編碼！驗證清單必須同時含「JS 內舊值」（78,000/62,969）
        # 2026-09-20（INC-221）：邏輯抽成 check_dashboard_stale.py（單一入口）—— 原內嵌比對分不清
        #     「活的顯示值」與「引用的歷史文字」，9/16 CIO 審查全文（<details class="cio-old">／JS 註解離線快照）
        #     內的『可動用 772,607』被誤判殘留，sync_all 最後一步中止（實為假陽性，其餘步驟全過）。
        #     排除僅限「不渲染／已歸檔」區塊（HTML/JS 註解、cio-old），<script> 內的 JS 硬編碼仍照掃（不放寬）。
        ("儀表板產出驗證（舊值殘留，排除註解/cio-old 歸檔區）", "python check_dashboard_stale.py"),
        # 2026-08-29 v3 血淚：儀表板 HTML 巢狀結構檢查（4 處 <div style="width:N%"</div> 缺 > → 手機瀏覽器吞掉後 3 分頁；
        #     正則標籤平衡抓不到巢狀錯誤，需 HTMLParser 嚴格追蹤開閉順序）
        ("儀表板結構檢查", "python check_dashboard_structure.py index.html"),

        # 2026-08-27：共享渲染組件自測（report_components 異常 → 報表數字不一致）
        ("組件自測", "python -c \"from report_components import render_health_score; import json; print('✅ 組件正常 健康度', render_health_score(json.load(open('snapshot.json',encoding='utf-8')))['分數'])\""),
        ("週報", "python build_weekly_report.py"),
    ]
    ok = True
    for label, cmd in steps:
        r = run(label, cmd)
        if not r:
            ok = False
            break  # 失敗即停（避免在錯誤資料上繼續）
    print(f"\n{'✅ 全部完成（10 步驟）' if ok else '⚠️ 有步驟失敗（見上）'}")

    # 2026-08-31 血淚：Moneybook 解壓目錄含身分證欄位（曾被 commit 進 git！）→ 每次同步後強制清理
    for _d in ["moneybook_tmp", "moneybook", "mb_tmp"]:
        _p = BASE / _d
        if _p.exists():
            try:
                import shutil
                shutil.rmtree(_p)
                print(f"🧹 已清理個資目錄 {_d}/（含身分證欄位，勿 commit）")
            except Exception as _e:
                print(f"⚠️ 清理 {_d}/ 失敗: {_e}")

    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
