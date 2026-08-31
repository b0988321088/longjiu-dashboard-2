#!/usr/bin/env python3
"""sync_all.py — 龍九一鍵同步管線 v2（2026-08-24 檢討修正）
依序執行：資產驗證 → 日報 → 緊急應變 → 穿透 → 四源 → 同義欄位 → 一致性 → 再平衡/週報
v2 修正：①加入 asset_sync.py（同義欄位驗證，2026-08-24 血淚：漏欄位不抓）②輸出完整（非只 tail）③失敗即停
用法：python sync_all.py [date]
"""
import subprocess, sys, datetime, json, re
from pathlib import Path

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
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y-%m-%d")
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
        ("同義欄位驗證", f"python asset_sync.py"),
        ("日報", f"python run_daily.py"),
        # 2026-08-27：gen_emergency_*.py 已刪除（一次性腳本清理），緊急應變僅用 emergency_1330.py（cron 13:00）
        ("台股緊急應變", f"python emergency_1330.py"),
        ("穿透報告", f"python build_penetration_report.py"),
        ("四源同步", f"python four_source_sync.py"),
        ("同義欄位複驗", f"python asset_sync.py"),
        ("一致性檢查", f"python check_penetration_consistency.py {today}"),
        ("再平衡報告", f"python build_rebalance_report.py"),
        # 2026-08-29：再平衡儀表板（雷達+政策面+本週投資計劃）— 之前 sync_all 漏跑，導致雷達更新後儀表板舊
        ("再平衡儀表板", f"python build_rebalance_dashboard.py"),
        ("儀表板注入", "python build_dashboard.py"),
        # 2026-08-29 v4：雷達資料同步驗證（radar_state.json 存在 + 政策面非空 + 三處產出含雷達結論）
        #     血淚：institutional_flow.py 讀 policy_notes 用 .get("內容") 但結構是新聞dict → 政策面空白沒人發現
        ("雷達同步驗證", "python -c \"import json; r=json.load(open('radar_state.json',encoding='utf-8')); pn=r.get('policy_notes') or {}; assert pn.get('新聞1_華許升息') or pn.get('原油綜合判斷'), '❌ radar_state.policy_notes 空白'; sig=r.get('signals') or {}; assert sig, '❌ radar_state.signals 空白'; print('✅ 雷達資料完整（signals', len(sig), '項 + 政策面', len(pn), '筆）')\""),
        # 2026-08-29：產出後驗證 index.html 無配息舊值殘留（build_dashboard rep dict 漏替換防呆）
        # 清單 = 配息口徑舊值 + 穿透卡五桶舊市值 + 保單A舊值 + 當月已收舊值（8/29 血淚全量盤點）+ 監控卡片合計舊值
        # ⚠️ 2026-08-29 v2 血淚：JS 內硬編碼 fallback（Script 6 入帳清單 ['房租已收', 78000] / || 62969）不在 rep dict 範圍 —
        #     build_dashboard 只 rep HTML 顯示值，JS 陣列內的數字是獨立硬編碼！驗證清單必須同時含「JS 內舊值」（78,000/62,969）
        (f"儀表板產出驗證", "python -c \"import re; h=open('index.html',encoding='utf-8').read(); stale=[s for s in ['35,583','63,027','2,723,839','7,753,544','88,507','109,645','143.9%','144%','199,960','62,969','78000','78,000','5,103,722','1,889,388','11,499,725','1,089,462','5,917,259','5,798,988','3,735,174','7,764,551','14.3%','-0.7pp','799,612','815,066','20260821_1','20260829_1','772,607','123,607','27,738','499,316','458,343','20,776','6,960','0 TWD（應收 2,100）'] if s in h]; print('❌ 儀表板殘留舊值: '+str(stale) if stale else '✅ 儀表板無舊值殘留'); import sys; sys.exit(1 if stale else 0)\""),
        # 2026-08-29 v3 血淚：儀表板 HTML 巢狀結構檢查（4 處 <div style="width:N%"</div> 缺 > → 手機瀏覽器吞掉後 3 分頁；
        #     正則標籤平衡抓不到巢狀錯誤，需 HTMLParser 嚴格追蹤開閉順序）
        ("儀表板結構檢查", "python check_dashboard_structure.py index.html"),

        # 2026-08-27：共享渲染組件自測（report_components 異常 → 報表數字不一致）
        ("組件自測", "python -c \"from report_components import render_health_score; import json; print('✅ 組件正常 健康度', render_health_score(json.load(open('snapshot.json',encoding='utf-8')))['分數'])\""),
        ("週報", f"python build_weekly_report.py"),
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
