#!/usr/bin/env python3
"""Git post-commit hook (active): ① scripts 同步到 hermes/scripts/ ② [cioreviewed] 決策軌跡"""
from pathlib import Path
import shutil, subprocess, json

BASE = Path(__file__).resolve().parent.parent.parent
TARGET = Path.home() / "AppData/Local/hermes/scripts"

SCRIPTS = [
    "update_all.py", "run_daily.py", "daily_intel.py",
    "hunter_intel.py", "asset_diff_monitor.py", "daily_deploy.py",
    "pre_push_audit.py", "budget_daily_check.py", "calendar_sync.py",
    "notion_bridge.py", "cost_monitor.py", "penetration_monitor.py",
    "compile_intel.py", "sync_all.py", "decision_json.py",
]

ok = 0
for name in SCRIPTS:
    src = BASE / name
    dst = TARGET / name
    if src.exists():
        shutil.copy2(src, dst)
        ok += 1

print(f"  🔁 auto-sync: {ok} scripts -> hermes/scripts/")

# 決策軌跡自動化（2026-09-02 CIO 風險2）：[cioreviewed] commit 同步寫入 trail
try:
    _msg = subprocess.run(
        ["git", "log", "-1", "--format=%s"], capture_output=True, text=True, cwd=BASE
    ).stdout.strip()
    if _msg and "[cioreviewed]" in _msg:
        _hash = subprocess.run(
            ["git", "log", "-1", "--format=%h"], capture_output=True, text=True, cwd=BASE
        ).stdout.strip()
        _trail_dir = Path.home() / "AppData/Local/hermes/data"
        _trail_dir.mkdir(parents=True, exist_ok=True)
        _tf = _trail_dir / "decision_commits.jsonl"
        with open(_tf, "a", encoding="utf-8") as f:
            f.write(json.dumps(
                {"hash": _hash, "ts": __import__("datetime").datetime.now().isoformat(), "msg": _msg},
                ensure_ascii=False,
            ) + "\n")
        print(f"  📜 decision-trail: {_hash} appended")
except Exception as _e:
    print(f"  ⚠️ decision-trail skip: {_e}")
