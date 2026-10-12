#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_evening_scope_gate.py — 唯讀自測：evening_sync 的 commit scope 判定（_scope_verdict）。

背景（2026-10-12 實踩）：原判定式 `sorted(_st) == sorted(_keep)` 要求「staged 與本輪產物完全相等」，
遇到「產物內容經 git 正規化後與 HEAD 相同（autocrlf／clean filter）→ git add 不產生 staged 變更」
就整批 fail-closed；當晚訊息＝「多出 []」（沒有任何多餘檔卻判定不符）→ 22:00 晚報連續不上線。
修正＝安全性質只保留「staged ⊄ produced → 不推」，反向只列 ℹ️ 不阻擋。

本檔同時驗「舊式判定在此情境會誤擋」→ 證明修正不是為了讓紅燈變綠，而是修誤擋。
"""
import sys
from pathlib import Path

REPO = Path(r"C:/Users/bot/Desktop/longjiu_system")
sys.path.insert(0, str(REPO))
from evening_sync import _scope_verdict       # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   | " + detail) if detail else ""))


def old_predicate(staged, keep):
    """2026-10-12 修正前的判定式（保留在測試裡，作為回歸證明）。"""
    return sorted(staged or []) == sorted(keep or [])


# ── 正向：staged == produced（常態）─────────────────────────────────────────
v, extra, missing = _scope_verdict(["a.json", "b.html"], ["b.html", "a.json"])
check("正向：完全相等 → ok", v == "ok" and not extra and not missing, f"{v} {extra} {missing}")

# ── 修復主案例：staged ⊂ produced（git 正規化造成無 staged 變更）────────────
staged = ["index.html", "snapshot.json"]
keep = ["index.html", "snapshot.json", "asset_diff_history.json"]
check("主案例：舊式判定會誤擋（回歸證明）", old_predicate(staged, keep) is False)
v, extra, missing = _scope_verdict(staged, keep)
check("主案例：新版放行且多餘為空", v == "ok" and extra == [], f"{v} extra={extra}")
check("主案例：缺漏以 ℹ️ 回報（missing）", missing == ["asset_diff_history.json"], str(missing))

# ── 安全性質：staged 有 produced 以外的檔 → 必擋（不得帶走他班／他輪檔）──────
v, extra, missing = _scope_verdict(["a.json", "他班的檔.md"], ["a.json"])
check("負向：多出他班檔 → extra_blocked", v == "extra_blocked" and extra == ["他班的檔.md"], f"{v} {extra}")

# ── 同時多出又缺漏 → 仍以 extra 優先擋 ─────────────────────────────────────
v, extra, missing = _scope_verdict(["a.json", "x.md"], ["a.json", "y.md"])
check("負向：多出＋缺漏並存 → 擋（extra 優先）",
      v == "extra_blocked" and extra == ["x.md"] and missing == ["y.md"], f"{v} {extra} {missing}")

# ── 邊界：空集合 ───────────────────────────────────────────────────────────
v, extra, missing = _scope_verdict([], [])
check("邊界：兩邊皆空 → ok", v == "ok", v)
v, extra, missing = _scope_verdict([], ["a.json"])
check("邊界：staged 空、produced 有 → ok（無 staged 變更）", v == "ok" and missing == ["a.json"])
v, extra, missing = _scope_verdict(["a.json"], [])
check("邊界：staged 有、produced 空 → 擋（幽靈提交）", v == "extra_blocked" and extra == ["a.json"])

# ── 重複項不得影響判定 ────────────────────────────────────────────────────
v, extra, missing = _scope_verdict(["a.json", "a.json"], ["a.json"])
check("重複 staged 項 → ok（集合語意）", v == "ok" and not extra and not missing, f"{v} {extra} {missing}")

print(f"\n結果：{'✅ 全部通過' if not FAILS else '❌ 失敗 ' + str(FAILS)}")
sys.exit(1 if FAILS else 0)
