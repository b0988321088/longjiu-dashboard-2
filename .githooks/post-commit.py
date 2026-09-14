#!/usr/bin/env python3
"""Git post-commit hook (active): ① scripts 同步到 hermes/scripts/ ② [cioreviewed] 決策軌跡"""
from pathlib import Path
import os, shutil, subprocess, json, sys

BASE = Path(__file__).resolve().parent.parent


def _hermes_dir() -> Path | None:
    """解析 Hermes 資料目錄（Home 下的 AppData/Local/hermes）。

    2026-09-14 INC：原本直接用 Path.home() → 在 HOME 被污染的環境（實測：我的 Python 沙箱
    把 HOME 指向 C:\\...\\Temp\\xxx）會把鏡像寫到不存在的路徑，同步「靜默失敗」
    （traceback 之後照樣 exit 0），repo 改了、cron 端腳本卻是舊的。
    改為多來源解析：HERMES_HOME 環境變數 → USERPROFILE → 固定路徑 → Path.home()，
    取第一個「真的存在」的；全都不存在就大聲失敗，不再靜默。
    """
    cands: list[Path] = []
    env = os.environ.get("HERMES_HOME")
    if env:
        cands.append(Path(env))
    for key in ("USERPROFILE", "HOME"):
        h = os.environ.get(key)
        if h:
            cands.append(Path(h) / "AppData/Local/hermes")
    cands.append(Path(r"C:\Users\bot\AppData\Local\hermes"))
    cands.append(Path.home() / "AppData/Local/hermes")
    for c in cands:
        try:
            if c.is_dir():
                return c
        except OSError:
            continue
    return None


HERMES = _hermes_dir()
if HERMES is None:
    print(
        "  ❌ post-commit 中止：找不到 Hermes 資料目錄（HOME=%s USERPROFILE=%s）"
        % (os.environ.get("HOME"), os.environ.get("USERPROFILE")),
        file=sys.stderr,
    )
    print("     → 本次 commit 的 scripts 鏡像未同步，cron 端可能仍跑舊版邏輯", file=sys.stderr)
    sys.exit(1)
TARGET = HERMES / "scripts"

SCRIPTS = [
    "update_all.py", "run_daily.py", "daily_intel.py",
    "hunter_intel.py", "asset_diff_monitor.py", "daily_deploy.py",
    "pre_push_audit.py", "budget_daily_check.py", "calendar_sync.py",
    "notion_bridge.py", "cost_monitor.py", "penetration_monitor.py",
    "compile_intel.py", "sync_all.py", "decision_json.py",
    # 2026-09-14（P2）：auto_record.py 是自動化路徑的落紀錄 helper，cron/鏡像端腳本會呼叫它
    "auto_record.py", "cio_approve.py",
    # 2026-09-14：auto_push.py 是「紀錄＋重試推送＋遠端驗證」的統一出口，各推送路徑都呼叫它
    "auto_push.py",
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

# ③ 自我驗證（2026-09-14）：複製完「讀回來比對」，不一致就大聲失敗。
#    實測踩過：commit 當下的複製沒有真的落地（5 支腳本在鏡像仍是舊內容，原因未明；
#    手動重跑 hook 才同步）→ 若沒人比對就會靜默漂移，cron 端跑舊版邏輯（與 9/11 同病灶）。
#    ⚠️ 這裡 exit 1 會讓 git commit 回非零碼（commit 本身已完成）→ 呼叫端會視為失敗而不推送，
#       這是刻意的：鏡像沒同步 = cron 會跑錯版本，寧可中斷也要讓人看到。
_marker = BASE / ".git" / "MIRROR_SYNC_FAILED"
bad: list[str] = []
for _name in sorted({*SCRIPTS, *(p.name for p in BASE.glob("*.py"))}):
    _src = BASE / _name
    _dst = TARGET / _name
    if not _src.exists() or not _dst.exists() or _is_forwarder(_dst):
        continue
    try:
        if _src.read_bytes() != _dst.read_bytes():
            bad.append(_name)
    except Exception:
        bad.append(_name)
if bad:
    try:
        _marker.write_text(
            f"{__import__('datetime').datetime.now().isoformat()} 未同步（{len(bad)}）：{', '.join(bad[:10])}\n",
            encoding="utf-8",
        )
    except Exception:
        pass
    print(f"  ❌ 鏡像自我驗證失敗：{len(bad)} 支內容不一致 → {', '.join(bad[:6])}")
    print(f"     → 已寫入 {_marker.name}；cron 端可能仍是舊版邏輯，請查鏡像目標與權限")
    sys.exit(1)
if _marker.exists():
    _marker.unlink()
print(f"  ✅ 鏡像自我驗證通過（{len(SCRIPTS)} 硬編碼清單 + 同名檔逐位元比對）")

# 決策軌跡自動化（2026-09-02 CIO 風險2）：[cioreviewed] commit 同步寫入 trail
try:
    _msg = subprocess.run(
        ["git", "log", "-1", "--format=%s"], capture_output=True, text=True, cwd=BASE
    ).stdout.strip()
    if _msg and "[cioreviewed]" in _msg:
        _hash = subprocess.run(
            ["git", "log", "-1", "--format=%h"], capture_output=True, text=True, cwd=BASE
        ).stdout.strip()
        _trail_dir = HERMES / "data"
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
