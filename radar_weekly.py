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

    # 2026-09-14：commit／紀錄／推送統一走 auto_push.py（add -A → clean-stage → commit →
    # 範圍紀錄覆蓋 → 重試推送 → 遠端 sha 驗證）
    ap = run([sys.executable, os.path.join(BASE, "auto_push.py"), "--script", "radar_weekly.py",
              "--auto-stage", "--commit", f"auto: 週六雷達儀表板同步 {TODAY}"], timeout=900)
    ap_out = ((ap.stdout or "") + (ap.stderr or "")).strip()
    if ap_out:
        print(ap_out[-400:])
    if ap.returncode != 0:
        print(f"⚠️ 未推送上線（rc={ap.returncode}）")

    # 4) 完整摘要交付 TG
    print(f"📋 週六再平衡 — 機構流向雷達\n{out}")


if __name__ == "__main__":
    main()
