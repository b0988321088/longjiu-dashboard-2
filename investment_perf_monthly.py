# -*- coding: utf-8 -*-
"""investment_perf_monthly.py — 每月投資績效 cron wrapper（每月 1 日 09:00 用）

跑 build_investment_performance.py（預設算上個完整月，含三類損益 + 資金成本儀表板）
→ stdout 推送 TG；同時重產 investment_performance.html 讓線上月報更新。
基準月 = 2026-08（使用者 9/4 裁示）：每月績效與基準月同口徑比較。
"""
import subprocess, sys, os

BASE = r"C:\Users\bot\Desktop\longjiu_system"


def run(cmd, timeout=300, env=None):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=BASE, timeout=timeout, env=env)


def main():
    out_lines = []
    # 1) 算上月績效（stdout = 完整月報文字，含三類損益 + 資金成本儀表板）
    r = run([sys.executable, "build_investment_performance.py"], timeout=300)
    body = r.stdout or ""
    if r.returncode != 0:
        body = f"⚠️ 投資績效計算失敗：{(r.stderr or '')[-300:]}"
    out_lines.append(body)

    # 2) git 無檔案變動則不 push（HTML 基準頁固定，每月績效以文字推送為主）
    g = run(["git", "add", "-A"], timeout=60)
    # P1（2026-09-14）：add -A 會掃進別人未提交的程式改動 → commit 前先排除程式檔
    g = run([sys.executable, os.path.join(BASE, "auto_record.py"), "--clean-stage"], timeout=180)
    if (g.stdout or "").strip():
        out_lines.append(g.stdout.strip())
    c = run(["git", "commit", "-m", "auto: 投資績效月報更新"], timeout=60)
    if c.returncode == 0 or "nothing to commit" in (c.stdout or "") + (c.stderr or ""):
        # 2026-09-14：紀錄＋推送統一走 auto_push.py（範圍紀錄覆蓋／重試／遠端 sha 驗證）
        ap = run([sys.executable, os.path.join(BASE, "auto_push.py"),
                  "--script", "investment_perf_monthly.py"], timeout=600)
        if ap.returncode != 0:
            out_lines.append(f"⚠️ 未推送上線（rc={ap.returncode}）："
                             f"{((ap.stdout or '') + (ap.stderr or '')).strip()[-160:]}")

    print("\n".join(out_lines))


if __name__ == "__main__":
    main()
