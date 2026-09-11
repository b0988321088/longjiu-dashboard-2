#!/usr/bin/env python3
"""Git post-commit hook (active): ① scripts 同步到 hermes/scripts/ ② [cioreviewed] 決策軌跡"""
from pathlib import Path
import shutil, subprocess, json

BASE = Path(__file__).resolve().parent.parent
TARGET = Path.home() / "AppData/Local/hermes/scripts"

SCRIPTS = [
    "update_all.py", "run_daily.py", "daily_intel.py",
    "hunter_intel.py", "asset_diff_monitor.py", "daily_deploy.py",
    "pre_push_audit.py", "budget_daily_check.py", "calendar_sync.py",
    "notion_bridge.py", "cost_monitor.py", "penetration_monitor.py",
    "compile_intel.py", "sync_all.py", "decision_json.py",
]


def _is_forwarder(p: Path) -> bool:
    """薄轉發器 = cron 端刻意保留的轉發層（指向 repo 真值），不可被真身覆蓋。"""
    try:
        t = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return ("薄轉發器" in t) or ("REPO_SCRIPT" in t)


ok = 0
# ① 硬編碼清單（hermes-only 或缺檔時補齊）
for name in SCRIPTS:
    src = BASE / name
    dst = TARGET / name
    if src.exists() and not _is_forwarder(dst):
        shutil.copy2(src, dst)
        ok += 1

# ② 全量鏡像：repo 與 hermes/scripts 同名的非轉發器檔一律對齊
#    （2026-09-11 INC：舊版只同步硬編碼 15 檔，其餘 18 檔靜默漂移，
#     導致 cron 跑 6 週前的邏輯 — pnl 門檻仍 20%、cio_review_ingest 落後 109 行）
mirrored = 0
for src in sorted(BASE.glob("*.py")):
    dst = TARGET / src.name
    if not dst.exists() or _is_forwarder(dst):
        continue
    try:
        if dst.read_bytes() != src.read_bytes():
            shutil.copy2(src, dst)
            mirrored += 1
    except Exception as e:
        print(f"  ⚠️ sync skip {src.name}: {e}")

print(f"  🔁 auto-sync: {ok} scripts -> hermes/scripts/ (+{mirrored} 全量鏡像修正)")

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
