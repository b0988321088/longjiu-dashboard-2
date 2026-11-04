#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/test_artifact_commit_responsibility.py — P1-2「提交責任鏈」驗收測試（2026-10-15）

對應使用者 2026-10-15 裁決（P1-2｜提交責任鏈），並依同日第二裁決修正為**方案 b**：
  「移除 artifact_commit 的 --push，提交與推送分離，推送交由獨立審查車道。
    保留 classify_paths、宣告清單與 staged 範圍檢查，不得降低 fail-closed 保護。」
  → R9/R10/R11/R13 已改寫為「本檔不得推送」的不變量：
     R9  靜態（AST）：不得匯入／呼叫 auto_push、不得有 push 字面、CLI 不得註冊 --push、函式簽名無 push
     R10 沙盒：有變更／無變更／fail-closed 三條路徑皆不得觸及替身 auto_push.py
     R11 訊息語意：只能講「已提交（推送待獨立審查）」，不得宣稱已推送／已發布；
         舊呼叫 `--push` 必須被 argparse 明確拒絕（非零 rc，且不留 commit）
     R13 接線：evening_sync 呼叫不帶 --push，且晚報的「已推送並驗證」只依真正推送結果
     R14 發布閘門仍完整：唯一推送出口存在、仍走 publish_gate、無其他呼叫鏈、無 --push 呼叫者

原始裁決（P1-2）：
  「新增 artifact_commit.py 並接入 evening_sync 後，尚未執行責任鏈測試。
    必須證明未宣告檔案不會被提交，且失敗時不會誤傷既有 staged 內容。」

不變量（本測試釘住的行為契約）：
  R1  宣告清單形狀：無全樹樣式、展開僅 repo 根目錄單層檔、不含程式副檔名
  R2  靜態守門：stage 唯一的呼叫點、一律顯式 pathspec（`--`）、禁用 add -A／--all／全樹
  R3  正向：宣告檔變更 → 產生 commit，且 commit 內容**恰為**宣告檔集合
  R4  未宣告檔（同輪 dirty）永遠不被帶進 commit，且維持原 dirty 狀態
  R5  子目錄同名檔不得被誤納（不遞迴、不跨目錄）
  R6  無變更 → rc=0、不製造空 commit、HEAD 不動
  R7  fail-closed：index 另有非宣告檔已 stage → 不提交、**既有 staged 內容原樣保留**、
      本檔自己的 stage 撤回、工作區內容不遺失
  R8  非 git 工作區 → rc≠0，且目錄內容逐檔不變（不寫任何東西）
  R9  push=False → 絕不呼叫 auto_push.py（唯一推送出口不得被隱式觸發）
  R10 push=True → 呼叫 auto_push.py 一次，且轉發 `--own <宣告清單>`（不自稱授權、帶精確清單）
  R11 推送失敗（auto_push rc≠0）→ 本檔 rc≠0，但**已產生的 commit 保留**（不清 HEAD、不改內容）
  R12 commit hook 失敗 → rc≠0、HEAD 不動、既有 staged 不受影響

全程離線、真 git（沙盒＝$TEMP 下的獨立 repo），不觸碰產線 repo 的 index／HEAD／remote。
執行：python -X utf8 tools/test_artifact_commit_responsibility.py
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "artifact_commit.py"
EVENING = ROOT / "evening_sync.py"
PASS = FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120)


def _load_module():
    """載入受測模組（不執行產線副作用；artifact_commit 匯入期不碰 git）。"""
    spec = importlib.util.spec_from_file_location("ac_under_test", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)   # noqa: S102
    return mod


def _sandbox(name: str, files: dict[str, str], fake_auto_push_rc: int = 0) -> Path:
    """建立獨立 git 沙盒：1 顆初始 commit ＋（可選）假的 auto_push.py。"""
    d = Path(tempfile.mkdtemp(prefix=f"lj_p12_{name}_"))
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@example.invalid")
    git(d, "config", "user.name", "t")
    git(d, "config", "core.autocrlf", "false")
    for rel, body in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8", newline="\n")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "base")
    if fake_auto_push_rc is not None:
        (d / "auto_push.py").write_text(
            "import sys, pathlib\n"
            f"pathlib.Path('PUSH_CALLED.txt').write_text(' '.join(sys.argv[1:]), encoding='utf-8')\n"
            f"sys.exit({fake_auto_push_rc})\n", encoding="utf-8", newline="\n")
    return d


def _porcelain(root: Path) -> set[str]:
    out = git(root, "status", "--porcelain").stdout or ""
    return {ln[3:].strip().strip('"') for ln in out.splitlines() if ln.strip()}


def _head(root: Path) -> str:
    return (git(root, "rev-parse", "HEAD").stdout or "").strip()


def _commit_count(root: Path) -> int:
    return len([x for x in (git(root, "rev-list", "HEAD").stdout or "").split() if x])


def _commit_files(root: Path) -> set[str]:
    out = git(root, "show", "--name-only", "--format=", "HEAD").stdout or ""
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


def test_declared_shape(mod) -> None:
    """R1／R2：宣告清單與 stage 寫入面的靜態性質。"""
    print("=== R1/R2 宣告清單形狀 ＋ 靜態 stage 守門 ===")
    decl = list(mod.DECLARED)
    check("R1a 宣告清單非空且為字串", bool(decl) and all(isinstance(x, str) and x for x in decl))
    bad = [d for d in decl if d.strip() in {"*", "**", ".", "./", "*.*", "/*"}
           or d.strip().startswith(("/", "..")) or ".." in d]
    check("R1b 無全樹／目錄／絕對路徑樣式", not bad, str(bad))
    check("R1c 宣告清單不含程式副檔名（不得自行認領程式碼）",
          not [d for d in decl if Path(d).suffix.lower() in
               {".py", ".sh", ".bat", ".ps1", ".cmd", ".toml", ".yml", ".yaml", ".js", ".ts", ".sql"}],
          str(decl))
    # 展開只取根目錄單層檔：沙盒中放「根目錄 1 檔 ＋ 子目錄 1 同名檔」
    d = _sandbox("shape", {"asset_diff_history.json": '{"v":1}',
                           "extra/asset_diff_history.json": '{"v":2}'})
    try:
        got = mod.declared_paths(d)
        check("R1d 展開僅得「已存在的根目錄單層檔」", got == ["asset_diff_history.json"], str(got))
        check("R1e 子目錄同名檔不被展開（不遞迴）", all("/" not in g for g in got), str(got))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    adds, bad_args, shell_true = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            seg = ast.get_source_segment(SRC.read_text(encoding="utf-8"), node) or ""
            if "shell=True" in seg:
                shell_true.append(node.lineno)
            # _git(root, "add"/"commit", ...) 形式（含 g("add", ...) 不在此檔）
            if isinstance(node.func, ast.Name) and node.func.id == "_git" and len(node.args) >= 3:
                verb = node.args[1]
                if isinstance(verb, ast.Constant) and verb.value in {"add", "commit"}:
                    rest = [a.value for a in node.args[2:] if isinstance(a, ast.Constant)]
                    if "*" in rest or "-A" in rest or "--all" in rest or "." in rest or "./" in rest:
                        bad_args.append((node.lineno, rest))
                    if verb.value == "add":
                        adds.append((node.lineno, "--" in rest))
    check("R2a 全檔只有一個 stage 呼叫點（單一寫入面）", len(adds) == 1, f"adds={adds}")
    check("R2b 該 stage 呼叫顯式 pathspec（帶 `--`）", bool(adds) and adds[0][1], f"adds={adds}")
    check("R2c add／commit 參數不含 -A／--all／全樹", not bad_args, str(bad_args))
    check("R2d 無 shell=True（不經 shell 展開）", not shell_true, str(shell_true))


def test_positive_commit(mod) -> None:
    """R3：宣告檔變更 → commit 內容恰為宣告檔。"""
    print("=== R3 正向：宣告檔提交，且 commit 內容恰為宣告檔 ===")
    d = _sandbox("pos", {"asset_diff_history.json": '{"v":1}',
                         "buffett_cto_report_2026-10-15.md": "old",
                         "snapshot.json": '{"t":1}', "index.html": "<p>1</p>", "helper.py": "x=1"})
    try:
        (d / "asset_diff_history.json").write_text('{"v":2}', encoding="utf-8", newline="\n")
        before = _head(d)
        rc, msg = mod.commit_artifacts(d)
        check("R3a rc=0、且訊息明示『推送待獨立審查』（裁決 b：提交 ≠ 發布）",
              rc == 0 and "推送待獨立審查" in msg, f"rc={rc} msg={msg}")
        check("R3b HEAD 前進 1 顆", _head(d) != before and _commit_count(d) == 2, f"head={_head(d)}")
        check("R3c commit 內容恰為宣告檔（僅 1 檔）",
              _commit_files(d) == {"asset_diff_history.json"}, str(_commit_files(d)))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_undeclared_untouched(mod) -> None:
    """R4／R5：未宣告檔與子目錄同名檔永不被帶走。"""
    print("=== R4/R5 未宣告 dirty 不被提交、維持原狀 ===")
    d = _sandbox("decoy", {"asset_diff_history.json": '{"v":1}',
                           "extra/asset_diff_history.json": '{"v":1}',
                           "snapshot.json": '{"t":1}', "index.html": "<p>1</p>", "helper.py": "x=1"})
    try:
        for rel, body in {"asset_diff_history.json": '{"v":2}',
                          "extra/asset_diff_history.json": '{"v":2}',
                          "snapshot.json": '{"t":2}',
                          "index.html": "<p>2</p>",
                          "helper.py": "x=2"}.items():
            (d / rel).write_text(body, encoding="utf-8", newline="\n")
        dirty_before = _porcelain(d)
        rc, msg = mod.commit_artifacts(d)
        dirty_after = _porcelain(d)
        check("R4a rc=0 且 submit 成功", rc == 0 and _commit_files(d) == {"asset_diff_history.json"},
              f"rc={rc} files={_commit_files(d)}")
        check("R4b 未宣告檔全數維持 dirty（一個都沒被帶走）",
              {"snapshot.json", "index.html", "helper.py"} <= dirty_after
              and {"snapshot.json", "index.html", "helper.py"} <= dirty_before,
              f"after={sorted(dirty_after)}")
        check("R5a 子目錄同名檔仍 dirty 且不在 commit 內（不遞迴）",
              "extra/asset_diff_history.json" in dirty_after
              and "extra/asset_diff_history.json" not in _commit_files(d), str(dirty_after))
        check("R5b commit 內無任何子目錄路徑", not [f for f in _commit_files(d) if "/" in f],
              str(_commit_files(d)))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_no_change(mod) -> None:
    """R6：無變更不製造空 commit。"""
    print("=== R6 無變更 → 不製造空 commit ===")
    d = _sandbox("nochange", {"asset_diff_history.json": '{"v":1}'})
    try:
        h0, c0 = _head(d), _commit_count(d)
        rc, msg = mod.commit_artifacts(d)
        check("R6a rc=0 且明說無變更（非靜默、非假成功）", rc == 0 and "無變更" in msg, f"rc={rc} msg={msg}")
        check("R6b HEAD 未動、commit 數不變", _head(d) == h0 and _commit_count(d) == c0)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_fail_closed_preserves_staged(mod) -> None:
    """R7：index 混入非宣告檔 → 不提交，且不誤傷既有 staged。"""
    print("=== R7 fail-closed：不誤傷既有 staged 內容 ===")
    d = _sandbox("staged", {"asset_diff_history.json": '{"v":1}', "snapshot.json": '{"t":1}'})
    try:
        (d / "asset_diff_history.json").write_text('{"v":2}', encoding="utf-8", newline="\n")
        (d / "snapshot.json").write_text('{"t":2}', encoding="utf-8", newline="\n")
        git(d, "add", "--", "snapshot.json")          # 他班既有 staged（非宣告檔）
        h0, c0 = _head(d), _commit_count(d)
        rc, msg = mod.commit_artifacts(d)
        staged = {ln.strip() for ln in (git(d, "diff", "--cached", "--name-only").stdout or "").splitlines() if ln.strip()}
        check("R7a rc≠0（fail-closed）且訊息指出非宣告檔", rc != 0 and "非宣告" in msg, f"rc={rc} msg={msg}")
        check("R7b 零 commit、HEAD 不動", _head(d) == h0 and _commit_count(d) == c0)
        check("R7c 既有 staged 內容原樣保留（未被 reset 帶走）", staged == {"snapshot.json"}, str(staged))
        check("R7d 本檔自己的 stage 已撤回（宣告檔不在 index，內容留在工作區）",
              "asset_diff_history.json" not in staged
              and "asset_diff_history.json" in _porcelain(d), f"staged={staged}")
        check("R7e 未宣告檔內容未被修改（仍在工作區原樣）",
              (d / "snapshot.json").read_text(encoding="utf-8") == '{"t":2}')
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_not_a_repo(mod) -> None:
    """R8：非 git 目錄 → 拒絕執行且零寫入。"""
    print("=== R8 非 git 工作區 → fail-closed 零寫入 ===")
    d = Path(tempfile.mkdtemp(prefix="lj_p12_nogit_"))
    try:
        (d / "asset_diff_history.json").write_text('{"v":1}', encoding="utf-8", newline="\n")
        before = {p.name: p.read_text(encoding="utf-8") for p in d.iterdir() if p.is_file()}
        rc, msg = mod.commit_artifacts(d)
        after = {p.name: p.read_text(encoding="utf-8") for p in d.iterdir() if p.is_file()}
        check("R8a rc≠0 且說明非 git 工作區", rc != 0 and "不是 git 工作區" in msg, f"rc={rc} msg={msg}")
        check("R8b 目錄內容逐檔未變（零寫入）", before == after, f"{sorted(before)} vs {sorted(after)}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_push_path(mod) -> None:
    """R9／R10／R11：推送出口（auto_push.py）唯一且參數正確。"""
    print("=== R9/R10/R11 提交與發布分離（裁決 b：本檔不得推送）===")
    src = {"asset_diff_history.json": '{"v":1}'}
    # R9 靜態（AST；註解／docstring 不算）：本檔不得存在任何推送出口
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    _lit_calls, _flags, _imports = [], set(), set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            _imports |= {al.name.split(".")[0] for al in getattr(n, "names", [])}
            if isinstance(n, ast.ImportFrom) and n.module:
                _imports.add(n.module.split(".")[0])
        if isinstance(n, ast.Call):
            lit = [x.value for x in n.args if isinstance(x, ast.Constant) and isinstance(x.value, str)]
            _lit_calls.append(lit)
            if any("push" in x for x in lit):
                _flags.add(("push-literals", tuple(lit)))
            if (isinstance(n.func, ast.Attribute) and n.func.attr == "add_argument"
                    and lit and lit[0].startswith("--")):
                _flags.add(("cli-flag", lit[0]))
    _push_lits = [lit for lit in _lit_calls if any("push" in x or "auto_push" in x for x in lit)]
    check("R9a 無 auto_push 匯入（提交與發布分離）", "auto_push" not in _imports, str(_imports))
    check("R9b 任何呼叫實參皆不得含 push／auto_push 字面", not _push_lits, str(_push_lits))
    check("R9c CLI 不再註冊 --push（argparse 不得接受該旗標）",
          not any(k == "cli-flag" and v == "--push" for k, v in _flags), str(sorted(_flags)))
    check("R9d 函式簽名無 push 參數（呼叫端無法要求推送）",
          "push" not in inspect.signature(mod.commit_artifacts).parameters,
          str(list(inspect.signature(mod.commit_artifacts).parameters)))

    # R10 沙盒：所有提交路徑（有變更／無變更／fail-closed）皆不得觸及替身 auto_push.py
    d = _sandbox("nopush", src, fake_auto_push_rc=0)
    try:
        (d / "asset_diff_history.json").write_text('{"v":2}', encoding="utf-8", newline="\n")
        rc1, msg1 = mod.commit_artifacts(d)
        check("R10a 有變更 → rc=0、commit 成立、且替身 auto_push 未被觸發",
              rc1 == 0 and not (d / "PUSH_CALLED.txt").exists(), f"rc={rc1} msg={msg1}")
        rc2, msg2 = mod.commit_artifacts(d)
        check("R10b 無變更 → rc=0 且仍不觸及推送出口",
              rc2 == 0 and "無變更" in msg2 and not (d / "PUSH_CALLED.txt").exists(), f"msg={msg2}")
        # fail-closed 路徑（index 混入非宣告檔）也不得觸及推送出口
        (d / "snapshot.json").write_text('{"t":1}', encoding="utf-8", newline="\n")
        (d / "asset_diff_history.json").write_text('{"v":3}', encoding="utf-8", newline="\n")
        git(d, "add", "--", "snapshot.json")
        rc3, msg3 = mod.commit_artifacts(d)
        check("R10c fail-closed 路徑 → rc≠0 且不觸及推送出口",
              rc3 != 0 and not (d / "PUSH_CALLED.txt").exists(), f"rc={rc3} msg={msg3}")
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # R11 訊息語意：只能宣稱「提交完成、推送待獨立審查」，不得宣稱已推送
    d = _sandbox("msg", src, fake_auto_push_rc=0)
    try:
        (d / "asset_diff_history.json").write_text('{"v":2}', encoding="utf-8", newline="\n")
        rc, msg = mod.commit_artifacts(d)
        check("R11a rc=0 且訊息明示『已提交』", rc == 0 and "已提交" in msg, f"rc={rc} msg={msg}")
        check("R11b 訊息明示『推送待獨立審查』（提交 ≠ 發布）", "推送待獨立審查" in msg, msg)
        check("R11c 訊息不得宣稱已推送／已發布",
              "已推送" not in msg and "已發布" not in msg and "並推送" not in msg, msg)
        check("R11d commit 確實存在（rc=0 代表本機 commit 成立）",
              _commit_files(d) == {"asset_diff_history.json"})
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # R11e 已移除的旗標必須被拒（不得靜默吞掉 → 免得呼叫端誤以為推送成功）
    d = _sandbox("oldflag", src)
    try:
        p = subprocess.run([sys.executable, str(SRC), "--root", str(d), "--push"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=180)
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        check("R11e 舊呼叫 `--push` → 非零 rc 且明確拒絕（不靜默忽略）",
              p.returncode != 0 and "unrecognized arguments" in out, f"rc={p.returncode} out={out[:120]}")
        check("R11f 被拒時不得留下任何 commit",
              _commit_count(d) == 1, str(_commit_count(d)))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_commit_hook_failure(mod) -> None:
    """R12：commit 失敗（hook）→ 不誤傷：HEAD 不動、內容不遺失、不污染他班 index。"""
    print("=== R12 commit hook 失敗 → 零 commit、內容不遺失 ===")
    d = _sandbox("hook", {"asset_diff_history.json": '{"v":1}'})
    try:
        hook = d / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
        os.chmod(hook, 0o755)
        (d / "asset_diff_history.json").write_text('{"v":2}', encoding="utf-8", newline="\n")
        h0, c0 = _head(d), _commit_count(d)
        rc, msg = mod.commit_artifacts(d)
        staged = {ln.strip() for ln in (git(d, "diff", "--cached", "--name-only").stdout or "").splitlines() if ln.strip()}
        check("R12a hook 阻擋 → rc≠0 且訊息含『commit 失敗』", rc != 0 and "commit 失敗" in msg, f"rc={rc} msg={msg}")
        check("R12b HEAD 不動、零 commit", _head(d) == h0 and _commit_count(d) == c0)
        check("R12c 宣告檔內容未被修改（工作區內容不遺失）",
              (d / "asset_diff_history.json").read_text(encoding="utf-8") == '{"v":2}')
        check("R12d 失敗後 index 未混入非宣告檔（只殘留本檔自己的 stage，範圍未擴大）",
              staged <= {"asset_diff_history.json"}, str(staged))
    finally:
        shutil.rmtree(d, ignore_errors=True)



def _py_files() -> list[Path]:
    """產線／治理範圍的 .py —— **只掃版控中檔案**，並排除測試與證據目錄。

    2026-10-15：原本 rglob 整個工作區，會把未追蹤的證據腳本（_r2_evidence/，內含敘述
    「artifact_commit.py … --push」之類文字）誤判成產線呼叫者 → 假紅燈。本不變量要守的
    是「產線呼叫鏈」，故以版控為界（tools/、tests/、_r2_evidence/、.archive/ 一律不算）。
    """
    r = subprocess.run(["git", "ls-files", "*.py"], cwd=str(ROOT), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    out: list[Path] = []
    for rel in (r.stdout or "").split("\n"):
        rel = rel.strip()
        if not rel or rel.startswith(("tools/", "tests/", "_r2_evidence/", ".archive/", "_bak")):
            continue
        p = ROOT / rel
        if p.exists():
            out.append(p)
    return out


def _callers() -> set:
    """誰會執行 artifact_commit.py（以字面引用判斷；含 subprocess 呼叫與測試）。"""
    return {p.name for p in _py_files() if "artifact_commit.py" in p.read_text(encoding="utf-8", errors="replace")}


def _push_callers() -> set:
    """哪些**產線**檔以 --push 呼叫 artifact_commit（必須為空；排除 tools/、tests/ 的測試斷言）。"""
    out = set()
    for p in _py_files():
        rel = p.relative_to(ROOT)
        if rel.parts and rel.parts[0] in {"tools", "tests"}:
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if "artifact_commit.py" in line and "--push" in line:
                out.add(rel.as_posix())
    return out

def test_wiring(mod) -> None:
    """R13：責任鏈接線（evening_sync 認領、緊急應變不再兼任）。"""
    print("=== R13 責任鏈接線 ===")
    e = EVENING.read_text(encoding="utf-8") if EVENING.exists() else ""
    check("R13a evening_sync 已呼叫 artifact_commit.py", "artifact_commit.py" in e)
    check("R13b 呼叫**不帶** --push（裁決 b：晚報只提交、推送交獨立審查車道）",
          'run_capture("artifact_commit.py", 300)' in e
          and 'run_capture("artifact_commit.py", 300, ["--push"])' not in e)
    check("R13c evening_sync 專屬收尾步驟存在（單一責任邊界）",
          "資料產物收尾提交" in e and "P1-2 修復" in e)
    # 對照組（防止「改測試而不是改程式」的自我安慰）：責任邊界只能有一條
    check("R13d 接線唯一（恰一處呼叫，避免多頭提交）",
          e.count('run_capture("artifact_commit.py"') == 1,
          str(e.count('run_capture("artifact_commit.py"')))
    check("R13e 晚報明確揭露『推送待獨立審查』（提交 ≠ 發布，不得合併報告）",
          "推送待獨立審查" in e, "")
    check("R13f 晚報的『已推送並驗證』只依真正推送結果（不得被收尾提交拉成綠燈）",
          "if _pushed" in e and "(_pushed or _ok_art)" not in e, "")


def _exec_callers() -> set:
    """真正**執行** artifact_commit.py 的產線檔（排除 tools/、tests/ 的測試與驗證器）。"""
    pat = "artifact_commit.py"
    execish = ("run_capture(", "subprocess", "sys.executable", "Popen(")
    out = set()
    for p in _py_files():
        rel = p.relative_to(ROOT)
        if rel.parts and rel.parts[0] in {"tools", "tests"}:
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if pat in line and any(k in line for k in execish):
                out.add(rel.as_posix())
    return out


def test_release_gate_intact(mod) -> None:
    """R14：移除推送路徑後，推送仍受獨立審查／發布核准控制（不得因此失控）。"""
    print("=== R14 推送仍受獨立審查控制 ===")
    ap = (ROOT / "auto_push.py").read_text(encoding="utf-8")
    check("R14a 唯一推送出口仍在（auto_push.py 未被移除）", "def main()" in ap)
    check("R14b auto_push 仍以 publish_gate 判定 AUTO/CIO（未因本次修正被繞過）",
          "from publish_gate import decide" in ap)
    check("R14c 執行 artifact_commit.py 的產線檔只有 evening_sync.py（無其他呼叫鏈）",
          _exec_callers() == {"evening_sync.py"}, str(sorted(_exec_callers())))
    check("R14d 沒有任何檔案以 --push 呼叫 artifact_commit",
          not _push_callers(), str(sorted(_push_callers())))
    check("R14e 收尾提交不會自行宣稱已發布（evening_sync 的推送綠燈只看 _pushed）",
          "推送待獨立審查" in (ROOT / "evening_sync.py").read_text(encoding="utf-8"))


def main() -> int:
    if not SRC.exists():
        print(f"❌ 找不到受測檔：{SRC}")
        return 1
    mod = _load_module()
    print("=== P1-2 提交責任鏈驗收（真 git 沙盒）===")
    print(f"宣告清單 DECLARED = {mod.DECLARED}")
    test_declared_shape(mod)
    test_positive_commit(mod)
    test_undeclared_untouched(mod)
    test_no_change(mod)
    test_fail_closed_preserves_staged(mod)
    test_not_a_repo(mod)
    test_push_path(mod)
    test_commit_hook_failure(mod)
    test_wiring(mod)
    test_release_gate_intact(mod)
    print(f"\n測試結果：{PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
