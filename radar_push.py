# -*- coding: utf-8 -*-
"""radar_push.py — 機構流向雷達 cron 推送 wrapper（每日 16:15 用）
流程：institutional_flow.py（更新 radar_state.json）→ build_dashboard.py（儀表板雷達區塊同步）→ git push
黃/紅燈才輸出（stdout 非空 → TG 推）；全綠 = 安靜（watchdog 模式）
2026-09-04 使用者指示：每天產出的機構流向雷達必須即時更新儀表板內雷達區塊（不能再等 22:00 晚報）
"""
import subprocess, sys, os
from datetime import date

BASE = r"C:\Users\bot\Desktop\longjiu_system"
TODAY = date.today().isoformat()


def run(cmd, env=None, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=BASE,
                          timeout=timeout, env=env)


def main():
    # 1) 雷達主程式（更新 radar_state.json；stdout 為摘要/警報）
    r = run([sys.executable, "institutional_flow.py"], timeout=600)
    out = r.stdout or ""
    if r.returncode != 0:
        print(f"⚠️ 機構流向雷達執行失敗：{(r.stderr or '')[-300:]}")
        return

    # 2) 雷達獨立報告頁（build_radar_report.py → radar_report_{date}.html）
    rr = run([sys.executable, "build_radar_report.py"], timeout=120)
    if rr.returncode != 0:
        print(f"⚠️ 雷達報告頁產生失敗：{(rr.stderr or '')[-200:]}")

    # 3) 儀表板同步：build_dashboard 讀 radar_state.json → index.html 雷達區塊即時更新
    d = run([sys.executable, "build_dashboard.py"], timeout=180)
    if d.returncode != 0:
        print(f"⚠️ 儀表板雷達同步失敗：{(d.stderr or '')[-300:]}")

    # 4) git commit + 雙分支 push（同 evening_sync 慣例，GitHub Pages 即時反映）
    # 2026-09-13 INC-159：原 `git add -A` 會把工作區「所有」變更掃進本 job 的 commit
    # （實證：一次掃入 582 個無關的 data/ 快取刪除 + 其他流程 6 個檔案，commit 訊息卻掛
    #  「雷達儀表板同步」）→ 改白名單，只提交本 job 自身產物。
    own_files = ["radar_state.json", f"radar_report_{TODAY}.html", "index.html"]
    own_files = [f for f in own_files if os.path.exists(os.path.join(BASE, f))]
    g = run(["git", "add"] + own_files, timeout=60)
    if g.returncode != 0:
        print(f"⚠️ git add 失敗（{own_files}）：{(g.stderr or '')[-200:]}")
        return
    c = run(["git", "commit", "-m", f"auto: 雷達儀表板同步 {TODAY}"], timeout=60)
    if c.returncode != 0 and "nothing to commit" not in (c.stdout or "") + (c.stderr or ""):
        print(f"⚠️ git commit 失敗：{(c.stderr or '')[-200:]}")
    # 2026-09-14：紀錄＋推送統一走 auto_push.py（範圍紀錄覆蓋／重試／遠端 sha 驗證）。
    # --own：本 job 產出（radar_state/雷達報告/儀表板）若沒進 commit → 直接擋下，
    # 不再出現「推成功但線上其實是舊的」。
    ap = run([sys.executable, os.path.join(BASE, "auto_push.py"), "--script", "radar_push.py",
              "--own", "radar_state.json", "radar_report_*.html", "index.html"], timeout=600)
    ap_out = ((ap.stdout or "") + (ap.stderr or "")).strip()
    if ap.returncode != 0:
        print(f"⚠️ 未推送上線（rc={ap.returncode}）：{ap_out[-300:]}")
        return

    # 4) 黃/紅燈才輸出摘要（TG 推）；全綠安靜
    if "⚠️ ALERTS" in out:
        print(out)


if __name__ == "__main__":
    main()
