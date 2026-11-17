#!/usr/bin/env python3
"""回收「孤兒產物」：與 HEAD 不同、且屬本專案報表類的 dirty 檔 → 一條龍 commit。

為什麼要這支（2026-11-17 實踩）：
    evening_sync.py 的 produced = after−before「且執行前乾淨」。某輪沒收走（例如 push
    gate 被別顆無 RECORD 的 commit 卡住而整批撤回），之後每一輪該檔都算「執行前已
    dirty」→ 永遠不進 commit scope。工作區持續累積、線上停舊版；當晚 25 檔卡 7 小時。

設計原則（不可放寬）：
    · 白名單。絕不用 `git add -u` / `-A` —— 工作區長期躺著上千個非產物檔（備份、
      一次性腳本、使用者丟進來的檔案），全掃會把不該落版的東西推上線。
    · 只收報表／資料產物，不收程式檔（.py 走 tools/commit_code_now.py）。
    · 只收「已受版控、內容真的變了」的檔；不新增檔案。

用法：
    python tools/flush_leftover_artifacts.py --list        # 只列出（預設參數）
    python tools/flush_leftover_artifacts.py               # 一條龍（commit→真審查→push）
    python tools/flush_leftover_artifacts.py --min-age 0   # 連剛寫入的也收（趕收工時用）
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# 固定檔名（與日期無關的產物）
EXACT = {
    "snapshot.json", "index.html", "mtd_data.json", "mtd_performance.html",
    "performance_monthly.html", "cost.html", "cost_data.json",
    "dashboard_decisions.json", "pending_decisions.json", "work_log.json",
    "usd_fx_state.json", "dragon_assets.db", "asset_diff_history.json",
    "macro_regime.json",
}

# 帶日期或編號的產物
PATTERNS = [
    re.compile(r"^(daily_report_v2|daily_report|asset_diff|penetration_report|"
               r"emergency_report|emergency_taiex_report|structural_health|"
               r"retirement_plan|rebalance_dashboard|rebalance_eval|stress_test|"
               r"monthly_report|weekly_report|risk_factor_penetration|"
               r"audit_dashboard|macro_regime)[^/]*\.(html|png|json)$"),
    re.compile(r"^data/(artifact_manifest|dis_status_\d{4}-\d{2}-\d{2}|"
               r"emergency_llm_analysis|ai_cost_daily|monthly_risk_shadow)"
               r"\.(json|jsonl)$"),
    re.compile(r"^logs/pipeline_llm_usage\.jsonl$"),
]

# 永不回收：備份、封存、程式、版控內部
DENY_PARTS = (".bak", "_bak_", ".backup", "backups/", "archive", "/.git/", "wrappers/")
DENY_SUFFIX = (".py", ".sh", ".bat", ".ps1", ".cmd", ".toml", ".yml", ".yaml", ".md")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(BASE), capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def is_artifact(path: str) -> bool:
    p = path.replace("\\", "/")
    if any(d in f"/{p}" for d in DENY_PARTS):
        return False
    if p.endswith(DENY_SUFFIX):
        return False
    return Path(p).name in EXACT or any(rx.match(p) for rx in PATTERNS)


def dirty_artifacts(min_age_min: float = 5.0) -> list[str]:
    """已受版控、內容變了、屬產物白名單、且 mtime 早於 min_age 分鐘的檔。"""
    out: list[str] = []
    now = time.time()
    for ln in git("status", "--porcelain").splitlines():
        if len(ln) < 4:
            continue
        status, path = ln[:2], ln[3:].strip().strip('"')
        if " -> " in path:                      # rename：取新路徑
            path = path.split(" -> ", 1)[1].strip().strip('"')
        if status == "??":                      # 只收已受版控的檔，不新增
            continue
        if not is_artifact(path):
            continue
        fp = BASE / path
        try:
            if min_age_min > 0 and (now - fp.stat().st_mtime) < min_age_min * 60:
                continue                        # 可能他班正在寫入 → 這輪先不收
        except OSError:
            continue
        out.append(path)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="回收 evening_sync 邊界排除後殘留的產物")
    ap.add_argument("--list", action="store_true", help="只列出，不 commit")
    ap.add_argument("--min-age", type=float, default=5.0,
                    help="只收 mtime 超過 N 分鐘的檔（預設 5；0=連剛寫入的也收）")
    a = ap.parse_args()

    files = dirty_artifacts(a.min_age)
    if not files:
        print("✅ 無孤兒產物（工作區產物與 HEAD 一致）")
        return 0
    print(f"🧺 孤兒產物 {len(files)} 檔（執行前已 dirty、非本輪 produced → evening_sync 收不走）：")
    for f in files:
        print(f"   · {f}")
    if a.list:
        print("\n（--list：未 commit、未推送）")
        return 0

    # 大檔提醒（審查會切多段，成本隨之上升）
    big = [f for f in files if (BASE / f).stat().st_size > 2_000_000]
    if big:
        print(f"⚠️ {len(big)} 檔 > 2MB（{', '.join(big[:3])}）→ 審查會分段，屬正常")

    msg = f"data: 回收未落版產物 {len(files)} 檔（evening_sync 邊界排除後殘留，{datetime.now():%m-%d %H:%M}）"
    print(f"\n▶ 走一條龍：commit → 真審查 → RECORD → push\n  {msg}")
    rc = subprocess.run([sys.executable, str(BASE / "tools" / "commit_code_now.py"), msg,
                         "--only", *files], cwd=str(BASE)).returncode
    if rc != 0:
        print("❌ 一條龍失敗 → 產物仍在工作區、未上線（見上方訊息）")
        return rc
    left = dirty_artifacts(0)
    if left:
        print(f"⚠️ 仍有 {len(left)} 檔未回收（可能剛被重寫）：{', '.join(left[:5])}")
        return 1
    print("✅ 回收完成，工作區產物與 HEAD 一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
