#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""artifact_commit.py — 受控資料產物提交（2026-10-15 P1-2；單一責任、唯一處理者）

背景（B1 審查 blocking：asset_diff_history.json 提交責任鏈斷裂）
  `asset_diff_history.json` 原本靠 `emergency_1330._commit_own()` 提交；該出口依 §4 裁決
  改為預設停用後，此檔失去處理者 → 永久停在 dirty。而 `evening_sync.py` 的 producer 規則
  （執行前已 dirty 者一律不帶走）永遠不會收它 → 一般同步流程也不會暗中提交它。

本檔＝**明確、唯一、可驗證**的處理者，只做三件事：
  1. 只提交「宣告清單 DECLARED」內的檔案（顯式 pathspec；禁 `git add -A`、禁泛指全樹）
  2. commit 前驗證「變更／已 stage 集合 ⊆ 宣告清單」；不符即 fail-closed 不提交
     （不擴大提交範圍、不帶走他班 dirty、不留半成品 index）
  3. 無實質變更 → rc=0 並明說「無變更」（不製造空 commit）

★ 2026-10-15 使用者裁決（方案 b）：**提交與發布分離**。
  本檔不再提供 `--push`，也**不得**以任何形式呼叫 `auto_push.py`：
    ‧ 理由：宣告清單兩檔（`asset_diff_history.json`／`buffett_cto_report_*.md`）未在 AUTO
      白名單 → 每顆收尾提交都需真 CIO 才能推；若由本檔嘗試推送，會每晚產生一顆「未落紀錄」
      commit 留在 `origin/clean-main..HEAD`，把**所有** producer 的推送一起擋住（留推不動 commit）。
    ‧ 不擴大白名單是刻意的：不用「讓每晚自動推得出去」交換發布權限。
  推送責任＝獨立審查車道（真 CIO 審查 → RECORD → 既有產線出口 `auto_push.py`），本檔不涉入。
  失敗一律非零 rc（呼叫端／cron 看得見）；不吞例外、不改資料檔內容。

用法：
  python artifact_commit.py                 # 只提交（本機；推送待獨立審查）
  python artifact_commit.py --root <dir>     # 測試用（沙盒 repo）
  python artifact_commit.py --message <msg>  # 自訂 commit 訊息
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

# ── 宣告清單（唯一權威；只有這裡列出的路徑可被本檔提交）────────────────────────
#  改清單＝治理行為；測試 tools/test_artifact_commit_responsibility.py 會釘住下列不變量：
#    ‧ 不含萬用全樹（*、.、./）；`buffett_cto_report_*.md` 為單層日期檔家族、僅限根目錄。
#    ‧ 執行前已 dirty 的**非宣告**檔案永遠不會被帶進 commit。
DECLARED: tuple[str, ...] = ("asset_diff_history.json", "buffett_cto_report_*.md")


def _git(root: Path, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=timeout)


def declared_paths(root: Path = BASE) -> list[str]:
    """展開宣告清單為「repo 根目錄下實際存在的檔名」（禁子目錄、禁遞迴）。"""
    out: list[str] = []
    for pat in DECLARED:
        for p in sorted(root.glob(pat)):
            if p.is_file() and p.parent == root:
                out.append(p.name)
    return sorted(set(out))


def commit_artifacts(root: Path = BASE, message: str | None = None) -> tuple[int, str]:
    """提交宣告清單內有變更的檔案。回傳 (rc, 訊息)；rc≠0 一律代表未完成（fail-closed）。

    ★ 本函式**不做推送**（2026-10-15 使用者裁決 b：提交與發布分離）：
      沒有 push 參數、不呼叫 `auto_push.py`（測試 R9/R10/R12 以靜態＋沙盒釘住）。
    """
    if not (root / ".git").exists():
        return 1, f"不是 git 工作區（{root}）→ 拒絕執行（fail-closed）"
    files = declared_paths(root)
    if not files:
        return 0, f"宣告清單內無實際檔案（{DECLARED}）→ 無事可做"
    st = _git(root, "status", "--porcelain", "--", *files)
    if st.returncode != 0:
        return 1, f"git status 失敗（rc={st.returncode}）：{(st.stderr or '').strip()[:200]}"
    changed = sorted({ln[3:].strip() for ln in (st.stdout or "").splitlines() if ln.strip()})
    if not changed:
        return 0, f"無變更（{len(files)} 檔已與 HEAD 一致）→ 不製造空 commit"
    extra_changed = sorted(set(changed) - set(files))
    if extra_changed:
        return 1, f"變更集合超出宣告清單（{extra_changed}）→ fail-closed，不提交"
    add = _git(root, "add", "--", *changed)
    if add.returncode != 0:
        _git(root, "reset", "-q", "HEAD", "--", *changed)
        return 1, f"git add 失敗（rc={add.returncode}）：{(add.stderr or '').strip()[:200]}"
    staged = sorted({ln.strip() for ln in (_git(root, "diff", "--cached", "--name-only").stdout or "").splitlines() if ln.strip()})
    extra = sorted(set(staged) - set(files))
    if extra:
        # 只撤銷「本檔自己 stage 的」，他班既有 staged 狀態原樣保留（不擴大動作）
        _git(root, "reset", "-q", "HEAD", "--", *changed)
        return 1, (f"index 另有非宣告檔已 stage（{extra}）→ fail-closed 不提交"
                   f"（已撤回本檔 stage，內容保留在工作區）")
    msg = message or f"data: 資產資料產物收尾提交 {__import__('datetime').date.today().isoformat()}"
    c = _git(root, "commit", "-m", msg, "--", *changed)
    out = ((c.stdout or "") + (c.stderr or "")).strip()
    if c.returncode != 0:
        if "nothing to commit" in out or "no changes added" in out:
            return 0, "無實質變更（git 正規化後與 HEAD 相同）→ 略過提交"
        return 1, f"git commit 失敗（rc={c.returncode}）：{(out.splitlines()[-1] if out else '')[:200]}"
    head = out.splitlines()[0] if out else "已提交"
    # ★ 提交與發布分離（裁決 b）：此處一律回報「提交完成、推送待獨立審查」——
    #   不得宣稱已推送、不得代為呼叫 auto_push.py（rc=0 只代表本機 commit 成立）。
    return 0, f"已提交（推送待獨立審查）：{head}"


def main() -> int:
    ap = argparse.ArgumentParser(description="受控資料產物提交（宣告清單 + pathspec；推送不在本檔職責）")
    ap.add_argument("--root", default=None, help="工作區根目錄（預設＝本檔所在目錄；測試用）")
    ap.add_argument("--message", default=None, help="commit 訊息（預設為制式訊息）")
    a = ap.parse_args()
    rc, msg = commit_artifacts(Path(a.root).resolve() if a.root else BASE, message=a.message)
    print(("✅ " if rc == 0 else "❌ ") + msg)
    return rc


if __name__ == "__main__":
    sys.exit(main())
