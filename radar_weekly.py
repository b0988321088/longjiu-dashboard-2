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

    # 3) git commit + 雙分支 push
    g = run(["git", "add", "-A"], timeout=60)
    # P1（2026-09-14）：add -A 會掃進別人未提交的程式改動 → commit 前先排除程式檔
    g = run([sys.executable, os.path.join(BASE, "auto_record.py"), "--clean-stage"], timeout=180)
    if (g.stdout or "").strip():
        print(g.stdout.strip())
    c = run(["git", "commit", "-m", f"auto: 週六雷達儀表板同步 {TODAY}"], timeout=60)
    if c.returncode != 0 and "nothing to commit" not in (c.stdout or "") + (c.stderr or ""):
        print(f"⚠️ git commit 失敗：{(c.stderr or '')[-200:]}")
    # P2（2026-09-14）：有真的 commit → 先落 RECORD（auto_record 結構檢查）再推
    if c.returncode == 0:
        ar = run([sys.executable, os.path.join(BASE, "auto_record.py"), "--script", "radar_weekly.py"], timeout=300)
        if ar.returncode != 0:
            print(f"⚠️ 落紀錄未通過 → 不推送：{((ar.stdout or '') + (ar.stderr or ''))[-200:]}")
            return
    p1 = run(["git", "push", "origin", "clean-main"], timeout=180)
    p2 = run(["git", "push", "origin", "clean-main:main", "--force-with-lease"], timeout=180)
    if p1.returncode != 0 or p2.returncode != 0:
        print(f"⚠️ GitHub push 失敗：{((p1.stderr or '') + (p2.stderr or ''))[-200:]}")

    # 4) 完整摘要交付 TG
    print(f"📋 週六再平衡 — 機構流向雷達\n{out}")


if __name__ == "__main__":
    main()
