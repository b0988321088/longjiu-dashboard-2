#!/usr/bin/env python
"""CIO 審查通過 → 落地紀錄（供 .githooks/pre-push v2 驗證）

閘門設計：**綁定 tree hash**（內容），不是 commit hash（訊息）。
  - 只改 commit message（例如補 [cioreviewed] 標籤）不會讓審查失效
  - 檔案內容任何改動 → tree 改變 → 舊紀錄失效 → 必須重新送審

紀錄檔：<git-dir>/CIO_APPROVED（tab 分隔、append-only）
  TS <TAB> TREE <TAB> COMMIT <TAB> VERDICT <TAB> REVIEWER <TAB> NOTE

用法：
  python cio_approve.py --status
      顯示目前 HEAD 是否已有此 tree 的 APPROVE 紀錄
  python cio_approve.py --verdict APPROVE --reviewer "CIO-Gemini" --note "匯率修正"
      寫入目前 HEAD tree 的通過紀錄（verdict 非 APPROVE 一律拒寫）
  python cio_approve.py --verdict APPROVE --reviewer "CIO-Gemini" --result review.json
      從 CIO 審查回傳的 JSON 讀 verdict（支援 {"verdict": ...} /
      {"results": [{"verdict": ...}]} / {"structured_output": {...}}），
      只有讀到 APPROVE 才會寫入；REJECT 會 exit 1 並印出 blocking 項目。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path


def clean(value: str, maxlen: int = 120) -> str:
    """紀錄檔是 tab 分隔的 append-only 文字檔 → 一律清掉 tab/CR/LF 與控制字元。
    避免 --reviewer/--note 被注入而破壞欄位結構（或偽造出多欄/多列紀錄）。"""
    out = "".join(ch if (ch.isprintable() and ch not in "\t\r\n") else " " for ch in str(value))
    return " ".join(out.split())[:maxlen]


def git(*args: str) -> str:
    p = subprocess.run(["git", *args], capture_output=True, text=True)
    if p.returncode != 0:
        print(f"❌ git {' '.join(args)} 失敗：{p.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return p.stdout.strip()


def git_dir() -> Path:
    return Path(git("rev-parse", "--git-dir")).resolve()


def approve_file() -> Path:
    return git_dir() / "CIO_APPROVED"


def head() -> tuple[str, str]:
    return git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")


def read_rows(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(line.split("\t"))
    return rows


def is_approved(tree: str) -> bool:
    return any(len(r) >= 4 and r[1] == tree and r[3] == "APPROVE" for r in read_rows(approve_file()))


def has_upstream() -> bool:
    p = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "@{u}"],
                       capture_output=True, text=True)
    return p.returncode == 0 and bool(p.stdout.strip())


def extract_verdict(obj) -> tuple[str | None, list[str]]:
    """從各種 CIO 回傳 JSON 形狀中挖出 verdict 與 blocking 項目。"""
    blocks: list[str] = []
    if isinstance(obj, dict):
        if isinstance(obj.get("verdict"), str):
            v = obj["verdict"]
            for k in ("required_fixes", "blocking", "required_changes"):
                if isinstance(obj.get(k), list):
                    blocks += [str(x) for x in obj[k]]
            return v.upper(), blocks
        for key in ("structured_output", "result", "results", "output"):
            if key in obj:
                v, b = extract_verdict(obj[key])
                if v:
                    return v, b + blocks
        return None, blocks
    if isinstance(obj, list):
        for item in obj:
            v, b = extract_verdict(item)
            if v:
                return v, b + blocks
    return None, blocks


def extract_scope(obj) -> tuple[set[str], set[str], bool]:
    """從 CIO 回傳 JSON 挖出「這次審查涵蓋哪些 commit／tree」。

    回傳 (commit sha 集合, tree sha 集合, 是否聲明涵蓋整個推送範圍)。
    支援形狀：reviewed_commit / reviewed_tree（str）、reviewed_commits（list[str|
    {"commit":...,"tree":...}】）、reviewed_range("a..b")。
    ⚠️ 一定要認 `reviewed_tree`：CIO 回傳常有 tree 而沒有 commit（閘門本身就是綁 tree 的）。

    背景（2026-09-14 自踩）：`--range-base` 原本對 base..HEAD 每個 commit 一律寫入同一審查結果，
    於是「只審了 A」的 JSON 會替範圍內尚未審查的 B 背書 → 閘門形同虛設。
    """
    shas: set[str] = set()
    trees: set[str] = set()
    whole = [False]

    def add_commit(it):
        if isinstance(it, str):
            shas.add(it.strip())
        elif isinstance(it, dict):
            if isinstance(it.get("commit"), str):
                shas.add(it["commit"].strip())
            if isinstance(it.get("tree"), str):
                trees.add(it["tree"].strip())

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                kl = k.lower()
                if kl in ("reviewed_commit", "reviewed_tree") and isinstance(v, str):
                    (shas if "commit" in kl else trees).add(v.strip())
                elif kl == "reviewed_trees" and isinstance(v, list):
                    for it in v:
                        if isinstance(it, str):
                            trees.add(it.strip())
                elif kl == "reviewed_commits" and isinstance(v, list):
                    for it in v:
                        add_commit(it)
                elif kl == "reviewed_range" and isinstance(v, str) and ".." in v:
                    whole[0] = True
                else:
                    walk(v)
        elif isinstance(o, list):
            for it in o:
                walk(it)

    walk(obj)
    return {s for s in shas if s}, {t for t in trees if t}, whole[0]


def sha_match(a: str, b: str) -> bool:
    """短/長 sha 互比（至少 7 碼）。"""
    n = min(len(a), len(b), 40)
    return n >= 7 and a[:n].lower() == b[:n].lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="只顯示目前 HEAD 的審查狀態")
    ap.add_argument("--verdict", help="APPROVE / REJECT")
    ap.add_argument("--reviewer", default="CIO", help="審查者標記（例：CIO-Gemini）")
    ap.add_argument("--note", default="", help="備註（例：改動摘要）")
    ap.add_argument("--result", help="CIO 審查回傳的 JSON 檔路徑")
    ap.add_argument("--commit", help="指定要記錄的 commit（預設 HEAD）；寫入該 commit 的 tree 一筆（P2 自動化路徑用）")
    ap.add_argument("--range-base", help="把 <base>..HEAD 之間「審查 JSON 有列到」的 commit tree 寫入紀錄（只會記錄真的被審過的那些）")
    ap.add_argument("--force", action="store_true", help="略過 result 檢查（僅供人工補登，需自行負責）")
    a = ap.parse_args()

    commit, tree = head()
    if a.commit:
        # P2（2026-09-14）：自動化路徑要記錄「自己剛做的那個 commit」，
        # 當下不一定有正確的 upstream base 可用（--range-base 不適用）→ 直接指定 commit 最穩。
        commit = git("rev-parse", f"{a.commit}^{{commit}}")
        tree = git("rev-parse", f"{commit}^{{tree}}")

    if a.status:
        rows = [r for r in read_rows(approve_file()) if len(r) >= 4 and r[1] == tree]
        print(f"HEAD commit = {commit}")
        print(f"HEAD tree   = {tree}")
        print(f"紀錄檔      = {approve_file()}")
        if is_approved(tree):
            r = rows[-1]
            print(f"✅ HEAD 已通過審查（{r[3]} by {r[4] if len(r) > 4 else '?'} @ {r[0]}）")
        else:
            print("❌ HEAD 尚無 APPROVE 紀錄 → push 會被擋")
        up = git("rev-parse", "--verify", "--quiet", "@{u}") if has_upstream() else ""
        if up:
            pend = git("rev-list", f"{up}..HEAD").split()
            print(f"\n未推送 commit（相對 @{{u}}）：{len(pend)} 筆")
            allok = bool(pend)
            for c in pend:
                t = git("rev-parse", f"{c}^{{tree}}")
                ok = is_approved(t)
                allok = allok and ok
                print(f"  {'✅' if ok else '❌'} {c[:12]}  tree {t[:12]}")
            print("✅ 範圍內全部已審" if allok else "❌ 範圍內有未審 commit → push 會被擋（--range-base <base> 只會寫入審查 JSON 有列到的 commit）")
            return 0 if allok else 1
        return 0 if is_approved(tree) else 1

    verdict = (a.verdict or "").upper() or None
    blocks: list[str] = []
    scope: set[str] = set()
    scope_trees: set[str] = set()
    scope_whole = False
    if a.result:
        data = json.loads(Path(a.result).read_text(encoding="utf-8"))
        v, blocks = extract_verdict(data)
        scope, scope_trees, scope_whole = extract_scope(data)
        if not v:
            print("❌ 無法從 result 檔讀到 verdict，拒寫紀錄", file=sys.stderr)
            return 2
        verdict = v
        if a.verdict and a.verdict.upper() != v:
            print(f"❌ --verdict({a.verdict}) 與 result({v}) 不一致，拒寫紀錄", file=sys.stderr)
            return 2

    if not verdict and not a.force:
        print("❌ 需指定 --verdict 或 --result（或 --status）", file=sys.stderr)
        return 2
    if verdict != "APPROVE" and not a.force:
        print(f"⛔ 審查結論為 {verdict or '未提供'} → 不寫入通過紀錄。", file=sys.stderr)
        for b in blocks:
            print(f"   必修：{b}", file=sys.stderr)
        return 1

    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    reviewer = clean(a.reviewer) or "UNKNOWN"
    note = clean(a.note)

    targets = [(commit, tree)]
    skipped: list[str] = []
    if a.range_base:
        cs = git("rev-list", f"{a.range_base}..HEAD").split()
        if not cs:
            print(f"⚠️ {a.range_base}..HEAD 之間沒有 commit，只寫入 HEAD", file=sys.stderr)
        elif not a.result or a.force:
            # 人工補登（無 result 或 --force）：維持舊行為，但明講範圍
            targets = [(c, git("rev-parse", f"{c}^{{tree}}")) for c in cs]
            print(f"⚠️ 未提供 --result（或使用 --force）：對 {a.range_base}..HEAD 全部 {len(cs)} 筆寫入紀錄"
                  f"（人工補登，需自行負責）", file=sys.stderr)
        else:
            # 2026-09-14：只記錄「審查 JSON 真的涵蓋」的 commit，其餘略過（不得替未審 commit 背書）
            # 比對認 commit sha 也認 tree sha（閘門本身綁 tree；CIO 回傳常只有 reviewed_tree）
            def _covered(c: str) -> bool:
                if scope_whole:
                    return True
                if any(sha_match(c, s) for s in scope):
                    return True
                ct = git("rev-parse", f"{c}^{{tree}}").split()[0]
                return any(sha_match(ct, t) for t in scope_trees)
            sel = [c for c in cs if _covered(c)]
            skipped = [c for c in cs if c not in sel]
            if not sel:
                print(f"❌ 審查 JSON 未涵蓋 {a.range_base}..HEAD 內任何 commit"
                      f"（JSON 內 reviewed_commit(s)={sorted(scope) or '無'}／reviewed_tree(s)={sorted(scope_trees) or '無'}）"
                      f" → 不寫入任何紀錄", file=sys.stderr)
                return 2
            targets = [(c, git("rev-parse", f"{c}^{{tree}}")) for c in sel]

    written: list[tuple[str, str]] = []
    with approve_file().open("a", encoding="utf-8") as f:
        for c, t in targets:
            t = t.split()[0]
            line = "\t".join([ts, t, c, "APPROVE", reviewer, note])
            # 寫入前自我檢查：欄位數必須為 6（防注入破壞格式）
            if len(line.split("\t")) != 6:
                print("❌ 紀錄行欄位數異常，拒寫（sanitize 失效）", file=sys.stderr)
                return 2
            f.write(line + "\n")
            written.append((c[:12], t[:12]))

    for c, t in written:
        print(f"✅ 已寫入審查紀錄：commit {c} tree {t} by {reviewer}")
    print(f"   共 {len(written)} 筆 → {approve_file()}")
    if skipped:
        print(f"⚠️ 略過 {len(skipped)} 筆不在審查 JSON 範圍內的 commit（未背書）：", file=sys.stderr)
        for c in skipped:
            print(f"     - {c[:12]}", file=sys.stderr)
        print("   → 這些 commit 仍需各自的審查，否則 push 會被閘門擋下", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
