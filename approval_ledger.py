#!/usr/bin/env python
"""核准紀錄帳本（.git/CIO_APPROVED）的唯一讀取／查核實作。

2026-11-27 核准鏈修復專案（使用者裁決）：
  根因不是「某支工具寫錯」，而是核准鏈上有三套不同標準——
  cio_gemini_review 落紀錄時一律取 HEAD 的 tree（不管 --commits 指定誰）、
  auto_push 用 commit sha 查核、pre-push hook 用 tree 查核。
  同一份內容在 reset／合併後 commit 變了，於是「hook 放行、auto_push 擋下」。

本模組把查核收斂成單一實作，所有消費端（cio_approve／auto_push／測試）都呼叫它。

紀錄檔格式（tab 分隔、append-only）：
  TS <TAB> TREE <TAB> COMMIT <TAB> VERDICT <TAB> REVIEWER <TAB> NOTE

查核規則（刻意嚴格，寧可擋下也不猜）：
  R1 主鍵＝(commit, tree) **成對相符**。只有 tree 相符不算通過——
     因為「被發布的對象」是 commit，核准憑證必須指向同一個對象。
  R2 內容沒變、commit 被改寫（reset/合併/補訊息）→ 舊紀錄不自動沿用。
     正解是用 cio_approve.py --commit <new> --expect-tree <原tree> 重新綁定：
     tree 相同代表內容相同，可重用同一份已 APPROVE 的審查 JSON，不必重跑審查。
  R3 只有 verdict == "APPROVE" 才算核准；REJECT／其他一律不算。
  R4 紀錄行欄位不足 6 欄、或 commit/tree 欄為空 → 該筆無效（不猜、不補）。
  R5 檔案不存在＝沒有任何核准（不是「全部放行」）。
  R6 同一 (commit, tree, verdict, reviewer) 重複寫入時，寫入端應去重（見 cio_approve）。

為什麼不是「tree 相符就放行」：
  2026-09-14 起閘門刻意綁 tree，優點是改 commit message 不必重審；
  但代價是 reset 後 commit 換了、紀錄仍停在舊 commit，
  於是「紀錄看起來有、查核卻對不上」。本專案依使用者要求改為雙綁，
  並提供 --expect-tree 讓「內容未變的重新綁定」變成一鍵、可審計的動作。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

FIELDS = 6
VERDICT_OK = "APPROVE"


def git_dir(base: str | Path = ".") -> Path:
    p = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=str(base),
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"不是 git repo：{p.stderr.strip()}")
    return Path(str(base), p.stdout.strip()).resolve()


def ledger_path(base: str | Path = ".") -> Path:
    return git_dir(base) / "CIO_APPROVED"


def read_records(path: Path | None = None, base: str | Path = ".") -> tuple[list[dict], list[str]]:
    """回傳 (有效紀錄, 損壞行)。損壞行只描述不修復——歷史只能追加。"""
    path = path or ledger_path(base)
    if not path.exists():
        return [], []
    good: list[dict] = []
    bad: list[str] = []
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        f = line.split("\t")
        if len(f) < FIELDS or not f[1].strip() or not f[2].strip():
            bad.append(f"L{i}: {line[:80]}")
            continue
        good.append({
            "ts": f[0].strip(), "tree": f[1].strip(), "commit": f[2].strip(),
            "verdict": f[3].strip().upper(), "reviewer": f[4].strip(),
            "note": "\t".join(f[5:]).strip(), "line": i,
        })
    return good, bad


def sha_match(a: str, b: str) -> bool:
    """短／長 sha 互比（至少 7 碼；避免 3 碼碰撞）。"""
    n = min(len(a), len(b), 40)
    return n >= 7 and a[:n].lower() == b[:n].lower()


def find_approval(commit: str, tree: str, records: list[dict],
                  allow_self_declared: bool = True,
                  allow_auto_checker: bool = True) -> dict | None:
    """找 (commit, tree) 成對相符且 verdict==APPROVE 的紀錄（後寫者優先）。"""
    hits = [r for r in records
            if r["verdict"] == VERDICT_OK
            and sha_match(r["commit"], commit)
            and sha_match(r["tree"], tree)]
    if not hits:
        return None
    if not allow_self_declared:
        hits = [r for r in hits if not r["reviewer"].startswith("SELF-DECLARED:")] or []
    if not allow_auto_checker:
        hits = [r for r in hits if not r["reviewer"].startswith("AUTO-checker")] or []
    return hits[-1] if hits else None


def approved_by_tree_only(commit: str, tree: str, records: list[dict]) -> dict | None:
    """內容已核准、但綁在別的 commit 上（reset／合併後的典型狀態）。
    僅用於產生「請重新綁定」的明確提示，**不得**當作放行依據。"""
    others = [r for r in records
              if r["verdict"] == VERDICT_OK
              and sha_match(r["tree"], tree)
              and not sha_match(r["commit"], commit)]
    return others[-1] if others else None


def is_duplicate(commit: str, tree: str, verdict: str, reviewer: str,
                 records: list[dict]) -> bool:
    return any(r["verdict"] == verdict.upper()
               and sha_match(r["commit"], commit)
               and sha_match(r["tree"], tree)
               and r["reviewer"] == reviewer
               for r in records)


def verify_commit(commit: str, tree: str, base: str | Path = ".",
                  allow_self_declared: bool = True,
                  allow_auto_checker: bool = True) -> tuple[bool, str, dict | None]:
    """單一 commit 的放行查核。回傳 (ok, 人類可讀原因, 命中的紀錄)。"""
    records, bad = read_records(base=base)
    hit = find_approval(commit, tree, records,
                        allow_self_declared=allow_self_declared,
                        allow_auto_checker=allow_auto_checker)
    if hit:
        return True, f"APPROVE by {hit['reviewer']} @ {hit['ts']}（紀錄 L{hit['line']}）", hit
    stale = approved_by_tree_only(commit, tree, records)
    if stale:
        return False, (f"內容（tree {tree[:12]}）已核准，但憑證綁在 commit {stale['commit'][:12]}，"
                       f"與待推 commit {commit[:12]} 不符 → 需重新綁定："
                       f"cio_approve.py --commit {commit} --expect-tree {tree}"), None
    if bad:
        return False, f"無 (commit, tree) 成對相符的 APPROVE 紀錄（另有 {len(bad)} 行損壞已忽略）", None
    return False, "無 (commit, tree) 成對相符的 APPROVE 紀錄", None


def pending_commits(head: str = "HEAD", base_ref: str = "origin/clean-main",
                    cwd: str | Path = ".") -> list[tuple[str, str]]:
    """實際待推送的 commit 清單 [(sha, tree)]——以推送範圍為準，不用 HEAD 猜。"""
    def run(*a):
        p = subprocess.run(["git", *a], cwd=str(cwd), capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else ""

    base = ""
    for ref in (base_ref, "origin/main", "@{u}"):
        base = run("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        if base:
            break
    if not base:
        return []
    shas = run("rev-list", f"{base}..{head}").split()
    return [(s, run("rev-parse", f"{s}^{{tree}}")) for s in shas]
