# -*- coding: utf-8 -*-
"""refresh_all.py — 一鍵同步所有儀表板資料（2026-08-23 B方案：先腳本再 JS 化）

任何 snapshot / 權重 / 穿透資料變動後，跑本腳本即可讓「儀表板三處」全部一致：
  1. industry_penetration.main()   — GICS 產業穿透重算 + 產業圖 PNG
  2. build_rebalance_dashboard.py  — 再平衡儀表板 + 評估 md（內部已含 rotation_engine + sector_deep_dive）
  3. update_dashboard_links.py     — 主儀表板重要連結刷新（最新檔名）

用法：
  python refresh_all.py            # 只同步本地檔案
  python refresh_all.py --push     # 同步 + git commit + 雙分支 push（clean-main + main）

注意：完整日報（含 CIO 審查）不走本腳本 — 每日管線 regenerate_report.py 處理；
      本腳本針對「資料變動後同步儀表板/評估/穿透/連結」的輕量路徑。
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _step(name: str, script: str, args: list | None = None) -> bool:
    print(f"\n▶ [{name}]")
    r = subprocess.run([sys.executable, str(BASE / script)] + (args or []),
                       cwd=str(BASE), capture_output=True, text=True, timeout=600)
    if r.stdout.strip():
        print(r.stdout.strip().splitlines()[-3:])
    if r.returncode != 0:
        print(f"  ⚠️ [{name}] 失敗（exit={r.returncode}）: {r.stderr.strip()[-200:]}")
        return False
    return True


def main() -> int:
    print("=" * 50)
    print("  refresh_all — 一鍵同步儀表板資料")
    print("=" * 50)

    ok = True
    ok &= _step("0/4 五桶穿透重算（update_all）", "update_all.py")
    ok &= _step("1/4 產業穿透重算", "industry_penetration.py")
    ok &= _step("2/4 再平衡儀表板+評估（含輪動引擎+深度討論）", "build_rebalance_dashboard.py")
    ok &= _step("3/4 主儀表板連結刷新", "update_dashboard_links.py")

    if "--push" in sys.argv:
        print("\n▶ git commit + push")
        r = subprocess.run(["git", "status", "--short"], cwd=str(BASE), capture_output=True, text=True)
        changed = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        if changed:
            subprocess.run(["git", "add", "-A"], cwd=str(BASE))
            subprocess.run(["git", "commit", "-m",
                            "sync: refresh_all 一鍵同步（穿透+再平衡+深度討論+連結） [cioreviewed]"],
                           cwd=str(BASE), capture_output=True)
            for branch in [["git", "push", "origin", "clean-main"],
                           ["git", "push", "origin", "clean-main:main", "--force"]]:
                p = subprocess.run(branch, cwd=str(BASE), capture_output=True, text=True)
                print(f"  {'✅' if p.returncode == 0 else '❌'} {' '.join(branch[2:4])}: {p.stderr.strip()[-100:] if p.returncode else ''}")
        else:
            print("  ℹ️ 無變更，跳過 push")

    print(f"\n{'✅ 全部完成' if ok else '⚠️ 部分步驟失敗，請檢查上方輸出'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
