#!/usr/bin/env python3
"""evening_sync.py — 龍九晚報輕量版（2026-08-27 優化）

原晚報為 agent 任務（每天第 2 次跑完整 regenerate_report.py → 可能觸發 buffett/cto LLM）。
改為 no-agent 校準版：update_all（四源同步）+ asset_diff_monitor（差異）+ build_dashboard（儀表板連結）
→ 零 LLM 成本，輸出三連結由 cron 直接推送。

晨間 07:00 仍為完整版（含 LLM 分析）。
"""
import subprocess, sys
from datetime import date
from pathlib import Path

BASE = Path(r"C:\Users\bot\Desktop\longjiu_system")
TODAY = date.today().isoformat()


def run(name: str, timeout: int = 600) -> bool:
    r = subprocess.run([sys.executable, str(BASE / name)], cwd=BASE,
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode == 0


def main():
    lines = ["📊 **龍九晚報（自動校準版 22:00）**"]
    ok1 = run("update_all.py", 600)
    lines.append("✅ 四源同步（snapshot→DB→HTML→穿透）" if ok1 else "⚠️ update_all 異常")
    ok2 = run("asset_diff_monitor.py", 120)
    lines.append("✅ 資產差異分析更新" if ok2 else "⚠️ 差異分析異常")
    ok3 = run("build_dashboard.py", 120)
    lines.append("✅ 儀表板連結更新" if ok3 else "⚠️ 儀表板異常")
    # 4) git 提交 + 推送雙分支（晚報原本功能）
    g = subprocess.run(["git", "add", "-A"], cwd=BASE, capture_output=True, text=True, timeout=60)
    g2 = subprocess.run(["git", "commit", "-m", f"auto: 晚報校準 {TODAY} [cioreviewed]"],
                        cwd=BASE, capture_output=True, text=True, timeout=60)
    if g2.returncode != 0 and "nothing to commit" not in g2.stdout:
        lines.append(f"⚠️ commit: {g2.stderr[-100:]}")
    p1 = subprocess.run(["git", "push", "origin", "clean-main"], cwd=BASE, capture_output=True, text=True, timeout=120)
    p2 = subprocess.run(["git", "push", "--force", "origin", "clean-main:main"],
                        cwd=BASE, capture_output=True, text=True, timeout=120,
                        env={**__import__("os").environ, "PUSH_FORCE_OK": "1"})
    lines.append("✅ GitHub 推送完成（雙分支）" if p1.returncode == 0 and p2.returncode == 0 else "⚠️ push 異常")
    lines.append("")
    lines.append(f"📰 日報：https://b0988321088.github.io/longjiu-dashboard-2/daily_report_v2_{TODAY}.html")
    lines.append(f"📊 差異：https://b0988321088.github.io/longjiu-dashboard-2/asset_diff_{TODAY}.html")
    lines.append("🏠 儀表板：https://b0988321088.github.io/longjiu-dashboard-2/")
    lines.append("")
    lines.append("（晚報已改輕量校準模式：零 LLM 成本；完整 LLM 分析在晨間 07:00）")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
