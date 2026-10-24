# -*- coding: utf-8 -*-
"""radar_weekly.py — 機構流向雷達 週六再平衡版（08:30 用）
COT/Fed 更新後輸出完整摘要（供再平衡評估 + TG 交付）
2026-09-04 同步更新：雷達產出後即時同步儀表板雷達區塊 + git push（同 radar_push.py）
"""
import subprocess, sys, os
from datetime import date

BASE = r"C:\Users\bot\Desktop\longjiu_system"
TODAY = date.today().isoformat()


def run(cmd, env=None, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=BASE,
                          timeout=timeout, env=env)


def main():
    # 1) 雷達主程式（COT/Fed/法人全量更新）
    r = run([sys.executable, "institutional_flow.py"], timeout=600)
    out = r.stdout or ""
    if r.returncode != 0:
        print(f"📡 機構流向雷達：執行失敗（{(r.stderr or '')[-200:]}）")
        return
    if not out.strip():
        print("📡 機構流向雷達：執行失敗，請檢查 institutional_flow.py")
        return

    # 2) 雷達獨立報告頁 + 儀表板同步（週六 COT/Fed 更新也即時反映）
    rr = run([sys.executable, "build_radar_report.py"], timeout=120)
    if rr.returncode != 0:
        print(f"⚠️ 雷達報告頁產生失敗：{(rr.stderr or '')[-200:]}")
    d = run([sys.executable, "build_dashboard.py"], timeout=180)
    if d.returncode != 0:
        print(f"⚠️ 儀表板雷達同步失敗：{(d.stderr or '')[-200:]}")
    rb = run([sys.executable, "build_rebalance_dashboard.py"], timeout=180)
    if rb.returncode != 0:
        print(f"⚠️ 再平衡儀表板同步失敗：{(rb.stderr or '')[-200:]}")

    # 2026-09-14：commit／紀錄／推送統一走 auto_push.py（clean-stage → commit →
    # 範圍紀錄覆蓋 → 重試推送 → 遠端 sha 驗證）
    # 2026-10-17 修復（每週六 rc=3 假失敗）：不再用 --auto-stage（= git add -A）。
    #   工作區長期常駐其他 producer 的雜檔（.archive／_bak_*／未提交程式／治理紀錄），
    #   add -A 會把它們一起 stage → publish_gate 對「整批變更集合」判定必非 AUTO →
    #   force_cio_paths 整批 unstage（含雷達自家兩檔）→ 無 commit → RANGE_EMPTY 拒推。
    #   改為**只 stage 自家產物**（當日報告頁＋狀態資料），讓變更集合乾淨命中白名單條目。
    _own = [f"radar_report_{TODAY}.html", "radar_state.json", "index.html",
            f"rebalance_dashboard_{TODAY}.html"]
    _exist = [p for p in _own if os.path.exists(os.path.join(BASE, p))]
    # 2026-10-22 P1：提交暫停旗標（只擋 commit/push，不擋產出）
    if os.path.exists(os.path.join(BASE, ".git", "PUSH_HOLD")):
        print("⏸️ PUSH_HOLD 生效：週六雷達已更新，跳過 commit/push；發布待另行授權")
        return 0
    if _exist:
        run(["git", "add", "--"] + _exist, timeout=60)
    ap = run([sys.executable, os.path.join(BASE, "auto_push.py"), "--script", "radar_weekly.py",
              "--commit", f"auto: 週六雷達儀表板同步 {TODAY}"], timeout=900)
    ap_out = ((ap.stdout or "") + (ap.stderr or "")).strip()
    if ap_out:
        print(ap_out[-400:])
    if ap.returncode != 0:
        print(f"⚠️ 未推送上線（rc={ap.returncode}）")
        _push_rc = ap.returncode
    else:
        _push_rc = 0

    # 4) 完整摘要交付 TG
    print(f"📋 週六再平衡 — 機構流向雷達\n{out}")
    # 2026-10-22：推送失敗必須反映到 cron 退出碼（原本只 print，永遠 exit 0）
    return _push_rc


if __name__ == "__main__":
    sys.exit(main() or 0)
