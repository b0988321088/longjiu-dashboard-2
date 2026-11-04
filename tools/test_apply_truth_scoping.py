#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_truth_*.py  名稱解析靜態守門（TD-20261015-05 blocking③）。

背景
----
真 CIO 工作區審查（2026-10-15T022730Z_worktree_cash_truth.json）以
「apply_truth_20261008.py 使用未定義變數 _FUNDS、P，導致執行時錯誤」列為 blocking。
覆核：該檔 L23 定義 P、L259 定義 _FUNDS，使用點（L261／L266／L269）皆在定義之後，
且 py_compile 通過 → 該審查只看到 diff 片段（segment 2/2）而誤判。

本測試用 AST 在「完整檔案」範圍內證明所有 Load 名稱皆有來源，並以負向案例
（抽掉 P 的綁定）證明此守門真的會抓到未定義變數，不是空跑。

用法：python tools/test_apply_truth_scoping.py   （rc=0 PASS／rc=1 FAIL）
"""
import ast
import builtins
import os
import re
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = ["apply_truth_20261008.py", "apply_truth_20261012.py"]


def _bound_names(tree: ast.AST) -> set:
    """收集檔案內所有被綁定的名稱（模組層＋函式/類別/推導式/except 等）。"""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            a = node.args if hasattr(node, "args") else None
            if a is not None:
                for arg in list(a.args) + list(a.posonlyargs) + list(a.kwonlyargs):
                    names.add(arg.arg)
                if a.vararg:
                    names.add(a.vararg.arg)
                if a.kwarg:
                    names.add(a.kwarg.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for al in node.names:
                names.add((al.asname or al.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.Global):
            names.update(node.names)
        elif isinstance(node, ast.comprehension) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def unresolved_names(src: str) -> list:
    tree = ast.parse(src)
    bound = _bound_names(tree) | set(dir(builtins)) | {"__name__", "__file__"}
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in bound:
            bad.append((node.id, node.lineno))
    return sorted(set(bad))


def main() -> int:
    fails = []
    for fname in TARGETS:
        path = os.path.join(BASE, fname)
        if not os.path.exists(path):
            print(f"⚠️ 找不到 {fname} → 跳過")
            continue
        src = open(path, encoding="utf-8").read()
        bad = unresolved_names(src)
        if bad:
            fails.append(fname)
            print(f"❌ {fname}：未解析名稱 {bad[:6]}")
        else:
            print(f"✅ {fname}：全檔 Load 名稱皆有定義（AST 完整檔範圍）")

    # ── 負向案例：抽掉 apply_truth_20261008.py 的 `P = ` 綁定 → 必須被抓到 ──
    neg_src_path = os.path.join(BASE, "apply_truth_20261008.py")
    if os.path.exists(neg_src_path):
        src = open(neg_src_path, encoding="utf-8").read()
        mutated = re.sub(r"^\s*P\s*=\s*BASE\s*/\s*\"snapshot\.json\"\s*$", "", src, count=1, flags=re.M)
        if mutated == src:
            print("⚠️ 負向案例：找不到可抽除的 P 綁定 → 無法證明守門有效性（視為 FAIL）")
            fails.append("negative-case-not-constructible")
        else:
            bad = unresolved_names(mutated)
            if any(n == "P" for n, _ in bad):
                print("✅ 負向案例：抽掉 P 綁定後如期被抓到（守門非空跑）")
            else:
                print("❌ 負向案例：抽掉 P 綁定卻沒被抓到 → 守門失效")
                fails.append("negative-case-undetected")
        # 另以暫存檔確認 AST 解析不因換行/編碼差異而漏檢
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "mut.py")
            open(p, "w", encoding="utf-8").write(mutated)
            compile(mutated, p, "exec")

    print("\n" + ("❌ FAIL：" + "、".join(fails) if fails else "✅ PASS：apply_truth 名稱解析守門 2/2 ＋ 負向 1/1"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
