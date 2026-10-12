# -*- coding: utf-8 -*-
"""TD-20261012-25：producer 邊界「既有 dirty 檔定點認領」驗證。

使用者 2026-10-12 核准之必要測試條件：
  1. 既有 dirty ＋ 窗口內重寫且內容與本輪輸出一致 → 修法前 RED、修法後 GREEN
  2. 窗口外 dirty／非候選檔／內容與 HEAD 相同 → 全部不得認領
  3. _UNREADABLE → 繼續 fail-closed（after 或 before 皆然）
  4. 認領不得連帶把其他 dirty 檔納入提交候選
  5. 原有 produced-set 行為（本輪新增檔、內容變更檔）不變

不跑整條管線：以 AST 抽出 regenerate_report.py 的 produced-set 區塊，在暫存 git repo 內用真實檔案
與真實 `git show HEAD:<檔>` 驗證（無 mock）。
"""
import ast
import hashlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "regenerate_report.py"
WANT_FUNCS = {"_snap_root", "_is_produced", "_produced_only", "_head_sha", "_claim_dirty_fixed_point"}
WANT_ASSIGNS = {"_SNAP_EXT", "_SNAP_MAX", "_UNREADABLE", "_RUN_T0"}

_RESULTS = []


def check(name, got, want):
    ok = got == want
    _RESULTS.append((name, ok, got, want))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}（got={got} want={want}）")
    return ok


def load_block(base):
    """抽出 produced-set 區塊（模組層賦值＋函式），以真實 BASE 執行。"""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    ns = {"BASE": base, "subprocess": subprocess, "hashlib": hashlib, "_hl": hashlib,
          "time": time, "_time": time, "Path": Path}
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in WANT_ASSIGNS:
            exec(compile(ast.Module(body=[node], type_ignores=[]), "<blk>", "exec"), ns)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in WANT_FUNCS:
            exec(compile(ast.Module(body=[node], type_ignores=[]), "<blk>", "exec"), ns)
    missing = (WANT_FUNCS | WANT_ASSIGNS) - set(ns)
    if missing:
        raise AssertionError(f"AST 抽取失敗，缺少：{sorted(missing)}")
    return ns


def legacy_is_produced(ns, f, before, after):
    """修法前判準（before == after → 不認領）：用來證明 RED。"""
    a = after.get(f)
    if a is None or a == ns["_UNREADABLE"]:
        return False
    if f not in before:
        return True
    if before[f] == ns["_UNREADABLE"]:
        return False
    return before[f] != a


def git(d, *args):
    return subprocess.run(["git", *args], cwd=str(d), capture_output=True, text=True)


def main():
    tmp = tempfile.mkdtemp(prefix="td25_produced_")
    repo = Path(tmp) / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    git(repo, "config", "core.autocrlf", "false")

    ns = load_block(repo)
    T0 = ns["_RUN_T0"]
    U = ns["_UNREADABLE"]

    def write(name, content):
        p = repo / name
        p.write_text(content, encoding="utf-8")
        return p

    def commit_all(msg="c"):
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", msg)

    # ── 準備：三個已提交（=HEAD）的乾淨檔
    write("dirty_report.html", "A-v1")          # 之後會變成 dirty 且定點
    write("other_dirty.md", "B-v1")             # 之後會變成 dirty（窗口外）
    write("clean.html", "C-v1")                 # 保持乾淨
    write("scope_guard.md", "D-v1")             # 之後骯髒＋窗口內（用於範圍防線）
    commit_all("init")

    # 讓它們相對 HEAD 變成 dirty（內容 ≠ HEAD blob）
    write("dirty_report.html", "A-v2-fixed-point")
    write("other_dirty.md", "B-v2-fixed-point")
    write("scope_guard.md", "D-v2-fixed-point")
    now = time.time()
    os.utime(repo / "dirty_report.html", (now + 1, now + 1))        # 窗口內
    os.utime(repo / "scope_guard.md", (now + 1, now + 1))           # 窗口內
    os.utime(repo / "other_dirty.md", (T0 - 3600, T0 - 3600))       # 窗口外

    before = ns["_snap_root"](repo)              # 本輪進場快照
    after = ns["_snap_root"](repo)               # 本輪收尾快照（內容相同 → 定點）
    bad = {f: U for f in ["unreadable_after.html"]}

    print("── 條件 1：既有 dirty ＋ 窗口內重寫＋內容與本輪輸出一致 → RED / GREEN")
    check("RED（舊判準不得認領）",
          legacy_is_produced(ns, "dirty_report.html", before, after), False)
    check("GREEN（新判準必須認領）",
          ns["_is_produced"]("dirty_report.html", before, after), True)

    print("── 條件 2：窗口外 dirty／非候選／內容與 HEAD 相同 → 不得認領")
    check("窗口外 dirty（mtime < 起跑時刻）",
          ns["_is_produced"]("other_dirty.md", before, after), False)
    check("內容與 HEAD 相同（乾淨檔）",
          ns["_is_produced"]("clean.html", before, after), False)
    keep, drop = ns["_produced_only"](["dirty_report.html"], before, after)
    check("非候選檔不得因認領而被帶入", "other_dirty.md" in keep, False)
    check("候選清單外的 dirty 檔不在 produced", drop, [])

    print("── 條件 3：_UNREADABLE 繼續 fail-closed")
    check("after 不可讀 → False",
          ns["_is_produced"]("unreadable_after.html", before, {**after, **bad}), False)
    check("before 不可讀 → False",
          ns["_is_produced"]("clean.html", {**before, "clean.html": U}, after), False)

    print("── 條件 4：認領只對單檔作答，不連帶其他 dirty 檔")
    keep2, drop2 = ns["_produced_only"](["dirty_report.html", "other_dirty.md", "clean.html"],
                                        before, after)
    check("produced 恰為被窗口內寫過且 dirty 的候選", keep2, ["dirty_report.html"])
    check("排除清單＝其餘候選", sorted(drop2), ["clean.html", "other_dirty.md"])

    print("── 條件 5：原有 produced-set 行為不變")
    check("本輪新增檔 → 認領（新舊一致）",
          (ns["_is_produced"]("brand_new.html", before, {**after, "brand_new.html": "x"}),
           legacy_is_produced(ns, "brand_new.html", before, {**after, "brand_new.html": "x"})),
          (True, True))
    check("內容變更檔 → 認領（新舊一致）",
          (ns["_is_produced"]("clean.html", before, {**after, "clean.html": "C-v2"}),
           legacy_is_produced(ns, "clean.html", before, {**after, "clean.html": "C-v2"})),
          (True, True))
    check("與 HEAD 相同的定點候選 → 不認領", ns["_is_produced"]("clean.html", before, after), False)

    print("── 追加防線：認領仍須落在原允許範圍（副檔名／大小）")
    _saved = ns["_SNAP_EXT"]
    ns["_SNAP_EXT"] = {".html"}                  # 暫時把 .md 移出允許範圍
    check("超出允許範圍的候選 → 不認領",
          ns["_is_produced"]("scope_guard.md", before, after), False)
    ns["_SNAP_EXT"] = _saved
    check("恢復允許範圍後 → 認領",
          ns["_is_produced"]("scope_guard.md", before, after), True)

    print("── 條件 4b：認領路徑不得改動 staging／HEAD／工作區（進場狀態保留）")

    def _snap_state():
        return (git(repo, "rev-parse", "HEAD").stdout.strip(),
                git(repo, "diff", "--cached", "--name-only").stdout,
                git(repo, "status", "--porcelain").stdout,
                git(repo, "rev-list", "--count", "HEAD").stdout.strip())

    s_before = _snap_state()
    for f in ["dirty_report.html", "other_dirty.md", "clean.html", "scope_guard.md"]:
        ns["_is_produced"](f, before, ns["_snap_root"](repo))
    ns["_produced_only"](["dirty_report.html", "other_dirty.md", "clean.html"], before, after)
    s_after = _snap_state()
    check("HEAD 未變", s_after[0], s_before[0])
    check("staging（index）未變", s_after[1], s_before[1])
    check("工作區狀態未變", s_after[2], s_before[2])
    check("未產生新 commit", s_after[3], s_before[3])

    _src_text = SRC.read_text(encoding="utf-8")
    _blk = "".join(ast.get_source_segment(_src_text, n) or ""
                   for n in ast.parse(_src_text).body
                   if isinstance(n, ast.FunctionDef) and n.name in WANT_FUNCS)
    check("認領區塊內不含 push／commit／add 呼叫（結構性證明，無遠端可動）",
          any(k in _blk for k in ['"push"', '"commit"', '"add"', "'push'", "'commit'", "'add'"]), False)

    total = len(_RESULTS)
    failed = [r for r in _RESULTS if not r[1]]
    print(f"\n=== {total - len(failed)}/{total} PASS ===")
    for n, _ok, got, want in failed:
        print(f"  ❌ {n}（got={got} want={want}）")
    print(f"（暫存 repo：{repo}；可丟棄）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
