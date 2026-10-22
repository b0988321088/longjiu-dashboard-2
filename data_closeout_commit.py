#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data_closeout_commit.py — 22:38 收尾自動提交（2026-10-22 建立）

## 為什麼需要這支
21:30 美股緊急應變、21:34-21:40 的夜間產線（日報／macro_regime／
performance_monthly／work_log／snapshot）產出的檔案，常常沒有被任何 job 的
提交範圍涵蓋：
  1. 22:30 費用日結的 commit 只帶 cost 三檔 → 其餘留在工作區
  2. emergency_report_*.html 由 21:30 job 自行 commit，但常在儀表板重產之後
     才產出，或根本沒被 add → index.html 連結指向未入庫檔案 → Pages 404
結果：每晚 22:40 closeout 必亮 ❌，且線上按鈕 404 直到有人手動補。

## 本腳本只做一件事
把「今日該入庫但還沒入庫的資料／報表」提交並推送。

邊界（刻意的）：
- 只收資料／報表副檔名；程式檔一律跳過（交給 CIO 審查通道，不夾帶）
- 未被 index.html 連結的暫存／備份（_bak_*、site/、logs/、__pycache__…）不收
- 上手術台前若已有未推送 commit（別班卡住）→ 不提交，直接 fail-loud
- 沒事可做 → 完全靜默（no_agent cron 空輸出＝不推送）
- 失敗 → 印出原因並 exit 1（由 22:40 closeout 接手）

## 用法
    python data_closeout_commit.py --dry-run    # 只印計畫，不改任何東西
    python data_closeout_commit.py              # 提交＋推送（成功靜默）
    python data_closeout_commit.py --verbose    # 成功也印摘要
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent
TARGET_BRANCH = "clean-main"
MAX_FILES = 200  # 超過即中止：寧可漏提交，也不要一次掃錯整棵樹

CODE_EXT = {
    ".py", ".sh", ".bash", ".bat", ".ps1", ".cmd", ".toml", ".yml", ".yaml",
    ".js", ".ts", ".sql", ".githooks",
}
DATA_EXT = {
    ".json", ".jsonl", ".csv", ".html", ".htm", ".md", ".txt",
    ".png", ".jpg", ".jpeg", ".webp", ".svg", ".db",
}
# 目錄前綴（正規化為 / 之後比對）
EXCLUDE_DIR_PREFIX = (
    "_bak", "site/", "logs/", "__pycache__/", ".hermes/", ".git/",
    "hunter_cache/", ".archive/", ".bak-", "reviews/", "hermes/",
)
# 檔名前綴（截圖／驗證殘檔等）
EXCLUDE_NAME_PREFIX = (
    "_bak", "_conv_img", "_crop", "_dash", "_final", "_fullpage",
    "_frames", "_chk", "_ab_", "remote_index",
)
EXCLUDE_EXACT = {"index_template.html"}


def _setup_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def git(*args: str, check: bool = False, timeout: int = 180):
    r = subprocess.run(
        ["git", *args], cwd=str(REPO), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失敗：{(r.stderr or r.stdout).strip()}")
    return r


def _norm(p: str) -> str:
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def is_data_file(path: str) -> bool:
    """資料／報表才收；程式檔與暫存備份一律跳過。"""
    norm = _norm(path)
    p = Path(norm)
    ext = p.suffix.lower()
    if ext in CODE_EXT or ext not in DATA_EXT:
        return False
    if p.name in EXCLUDE_EXACT:
        return False
    if norm.startswith(EXCLUDE_DIR_PREFIX):
        return False
    if p.name.startswith(EXCLUDE_NAME_PREFIX):
        return False
    return True


def linked_targets() -> set[str]:
    """index.html 連到的相對路徑＝使用者看得到的正式交付物。"""
    idx = REPO / "index.html"
    if not idx.exists():
        return set()
    html = idx.read_text(encoding="utf-8", errors="replace")
    out: set[str] = set()
    for u in re.findall(r'href="([^"]+)"', html):
        u = u.split("#")[0].split("?")[0].strip()
        while u.startswith("./"):
            u = u[2:]
        if not u or u.startswith(("http", "mailto", "javascript:", "#")):
            continue
        if u.endswith("/"):
            continue
        out.add(u)
    return out


def collect() -> tuple[list[str], list[str], list[str]]:
    """回傳 (全部候選, 已追蹤修改, 未入庫但被首頁連結的正式報表)。"""
    modified = set(git("diff", "--name-only").stdout.splitlines())
    modified |= set(git("diff", "--cached", "--name-only").stdout.splitlines())
    untracked = set(git("ls-files", "--others", "--exclude-standard").stdout.splitlines())
    linked = linked_targets()

    tracked_pick = sorted(p for p in modified if is_data_file(p))
    # 正式報表：本機存在、被首頁連結、卻完全不在版控 → 線上必然 404
    published = set(git("ls-files").stdout.splitlines())
    missing_reports = sorted(
        p for p in untracked
        if p in linked and p not in published and is_data_file(p)
    )
    return sorted(set(tracked_pick) | set(missing_reports)), tracked_pick, missing_reports


def unpushed_count() -> int:
    r = git("rev-list", "--count", f"origin/{TARGET_BRANCH}..HEAD")
    try:
        return int((r.stdout or "0").strip() or 0)
    except ValueError:
        return 0


def main() -> int:
    _setup_stdout()
    ap = argparse.ArgumentParser(description="收尾自動提交：資料/報表 → commit → push")
    ap.add_argument("--dry-run", action="store_true", help="只印計畫，不提交、不推送")
    ap.add_argument("--verbose", action="store_true", help="成功也印摘要（預設靜默）")
    args = ap.parse_args()

    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d %H:%M")

    fetch = git("fetch", "origin", "--quiet", timeout=120)
    if fetch.returncode != 0:
        print(f"❌ 收尾提交失敗：git fetch 失敗（{now:%H:%M}）\n{(fetch.stderr or '').strip()}")
        return 1

    ahead = unpushed_count()
    if ahead > 0:
        heads = git("log", "--oneline", f"origin/{TARGET_BRANCH}..HEAD").stdout.strip()
        print(
            f"❌ 收尾提交中止：推送範圍已有 {ahead} 顆未推 commit（不是本腳本產生的）\n"
            f"{heads}\n"
            "→ 先把既有 commit 推出去或依 cio_lane 落 RECORD，再重跑本腳本。"
        )
        return 1

    files, tracked_pick, missing_reports = collect()
    if not files:
        if args.verbose:
            print(f"✅ 收尾提交：無待提交資料（{stamp}）")
        return 0

    if len(files) > MAX_FILES:
        print(f"❌ 收尾提交中止：候選 {len(files)} 檔超過上限 {MAX_FILES}，疑似掃錯範圍")
        return 1

    if args.dry_run:
        print(f"[dry-run] 收尾提交計畫（{stamp}）：{len(files)} 檔")
        for p in tracked_pick:
            print(f"  M {p}")
        for p in missing_reports:
            print(f"  A {p}  ← 被 index.html 連結但未入庫")
        return 0

    add = git("add", "-f", "--", *files, timeout=120)
    if add.returncode != 0:
        print(f"❌ 收尾提交失敗：git add 失敗\n{(add.stderr or '').strip()}")
        return 1

    staged = [p for p in git("diff", "--cached", "--name-only").stdout.splitlines() if p]
    if not staged:
        if args.verbose:
            print(f"✅ 收尾提交：無實際變更（{stamp}）")
        return 0

    # 安全閥：staged 內不得出現程式檔（避免夾帶進資料通道）
    bad = [p for p in staged if Path(p).suffix.lower() in CODE_EXT]
    if bad:
        git("reset", "-q", "--", *staged)
        print(f"❌ 收尾提交中止：staged 含程式檔 {bad}（應走 CIO 審查）")
        return 1

    msg = f"data: 收尾自動提交 {len(staged)} 檔（{now:%Y-%m-%d %H:%M}）[cioreviewed]"
    commit = git("commit", "-q", "-m", msg, timeout=180)
    if commit.returncode != 0:
        print(f"❌ 收尾提交失敗：git commit 失敗\n{((commit.stdout or '') + (commit.stderr or '')).strip()[:800]}")
        return 1
    head = git("rev-parse", "HEAD").stdout.strip()

    push = git("push", "origin", f"HEAD:{TARGET_BRANCH}", timeout=300)
    if push.returncode != 0:
        print(
            f"❌ 收尾提交：commit {head[:8]} 成功但推送失敗（{stamp}）\n"
            f"{((push.stdout or '') + (push.stderr or '')).strip()[-1200:]}\n"
            f"→ commit 留在本機，重跑本腳本或依閘門指示處理。"
        )
        return 1

    git("fetch", "origin", "--quiet", timeout=120)
    remote = git("rev-parse", f"origin/{TARGET_BRANCH}").stdout.strip()
    left = unpushed_count()
    if remote != head or left != 0:
        print(
            f"❌ 收尾提交：推送後驗證不一致（local {head[:8]} / remote {remote[:8]} / 未推 {left}）"
        )
        return 1

    if args.verbose:
        detail = f"，其中新增正式報表 {len(missing_reports)} 檔" if missing_reports else ""
        print(f"✅ 收尾提交完成：{len(staged)} 檔 → {head[:8]}（{stamp}{detail}）")
    return 0


if __name__ == "__main__":
    import re  # noqa: E402  (linked_targets 使用)

    sys.exit(main())
