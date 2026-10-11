# -*- coding: utf-8 -*-
"""verify_postpush_guard.py — 推送後線上驗證的「未推送不驗」守門回歸測試（唯讀）

背景（2026-10-11 實踩）：
  07:00 晨間產線因 F1 封版契約 FAIL 而阻擋推送（fail-closed 正確），但收尾的
  `check_dashboard_sync.py --post-push` **無條件執行** → 本輪新檔必然還沒上線 → 必然 404，
  日誌噴出 3 條「線上 XXX → 404」，把真正的真因（閘門 FAIL）蓋掉。

本測試**不複製邏輯**，而是直接從 regenerate_report.py 抽出該段原始碼執行（單一真值來源），
並用 pre-fix 版本（`git show <PRE_FIX_SHA>:regenerate_report.py`）證明缺陷原本存在。
唯讀：不寫任何 repo 產物、不呼叫真的 subprocess／網路。

用法：python tools/verify_postpush_guard.py
失敗 exit 1。
"""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "regenerate_report.py"
PRE_FIX_SHA = "2ea2c894"          # 修復前最後一個 commit（缺陷重現基準）
START_ANCHOR = "_push_pending = bool(_push_files)"
END_ANCHOR = "⛔ 產出檢查="          # 外層 else: 之後的第一行（用來界定區塊尾端）
EXIT_EXPR = "sys.exit(0 if (ok and _pages_ok and _gate_ok) else 1)"

FAIL = []


def rec(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + (f" — {detail}" if detail else ""))
    if not ok:
        FAIL.append(name)


def extract_block(src: str) -> str:
    """抽出 `_push_pending = ...` 到外層 `else:` 之前的那一段（保持原縮排）。"""
    lines = src.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip().startswith(START_ANCHOR)), None)
    if start is None:
        raise SystemExit("❌ 找不到區塊起點（START_ANCHOR）→ regenerate_report.py 結構已變，請同步本測試")
    end = next((i for i in range(start, len(lines)) if END_ANCHOR in lines[i]), None)
    if end is None:
        raise SystemExit("❌ 找不到區塊終點（END_ANCHOR）")
    block = []
    for l in lines[start:end]:
        if l.strip() and not l[:1].isspace():
            break                     # 外層 else: / 註解 → 區塊結束
        block.append(l)
    return "\n".join(block).rstrip()


class _R:
    def __init__(self, rc, out="[stub stdout]"):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


def run_case(block: str, *, recorded, push_files, gate_ok, post_rc=0):
    """執行真實區塊；回傳 (subprocess 呼叫次數, 區塊執行後的 _pages_ok, 訊息, exit 碼)。"""
    ns = {"_recorded": recorded, "_push_files": push_files, "_gate_ok": gate_ok,
          "_pages_ok": True, "ok": True, "BASE": REPO, "sys": sys, "print": print}
    calls = []

    def fake_run(*a, **k):
        calls.append(a[0] if a else k)
        return _R(post_rc)

    ns["subprocess"] = type("S", (), {"run": staticmethod(fake_run)})
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile("if True:\n" + block, "<block>", "exec"), ns)
    rc = 0 if (ns["ok"] and ns["_pages_ok"] and ns["_gate_ok"]) else 1   # = 真實 exit 表達式
    return len(calls), ns["_pages_ok"], buf.getvalue(), rc


def main() -> int:
    src = TARGET.read_text(encoding="utf-8")
    print("== 0. 原始碼與 exit 表達式 ==")
    rec("exit 表達式未變（本測試的 rc 判準與程式一致）", EXIT_EXPR in src.replace("\r\n", "\n"),
        EXIT_EXPR)
    block = extract_block(src)
    print(f"  抽出區塊 {len(block.splitlines())} 行")

    print("\n== 1. 修後行為（真值＝本次要交付的 regenerate_report.py）==")
    # E1 推成功 → 驗線上（維持原安全網）
    n, pages, out, rc = run_case(block, recorded=True, push_files=["a.html"], gate_ok=True)
    rec("E1 推成功 → 執行 --post-push 且 rc 隨線上結果",
        n == 1 and pages is True and rc == 0, f"呼叫 {n} 次、rc={rc}")
    # E2 推成功但線上 404 → 仍判失敗（不放寬 fail-loud）
    n, pages, out, rc = run_case(block, recorded=True, push_files=["a.html"], gate_ok=True, post_rc=1)
    rec("E2 推成功但線上 404 → _pages_ok=False、rc=1",
        n == 1 and pages is False and rc == 1 and "線上連結驗證未過" in out, f"rc={rc}")
    # E3 閘門 FAIL（本次 07:00 實況）→ 不驗線上、不噴 404
    n, pages, out, rc = run_case(block, recorded=False, push_files=["a.html"], gate_ok=False)
    rec("E3 閘門 FAIL → 不呼叫 --post-push（假 404 消失）",
        n == 0 and "⏭ 本次未推送" in out and "404" in out, f"呼叫 {n} 次")
    rec("E3 仍 fail-loud（rc=1，不因略過驗證而變綠）", rc == 1, f"rc={rc}")
    # E4 有產物、閘門 PASS、卻沒推成功 → 明確標記失敗（不靠 404 巧合）
    n, pages, out, rc = run_case(block, recorded=False, push_files=["a.html"], gate_ok=True)
    rec("E4 推送未成功 → _pages_ok=False、rc=1、訊息指名 auto_push",
        n == 0 and pages is False and rc == 1 and "推送未成功" in out, f"rc={rc}")
    # E5 無待推產物（線上狀態未被本次改動）→ 保留線上驗證
    n, pages, out, rc = run_case(block, recorded=False, push_files=[], gate_ok=True)
    rec("E5 無待推產物 → 仍驗線上（既有安全網不退讓）",
        n == 1 and pages is True and rc == 0, f"呼叫 {n} 次")

    print(f"\n== 2. 缺陷重現（pre-fix {PRE_FIX_SHA}）==")
    old = subprocess.run(["git", "show", f"{PRE_FIX_SHA}:regenerate_report.py"],
                         cwd=str(REPO), capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if old.returncode != 0:
        rec("可取回 pre-fix 版本", False, old.stderr.strip()[:120])
    else:
        ols = old.stdout.replace("\r\n", "\n").splitlines()
        s = next((i for i, l in enumerate(ols)
                  if "推送與遠端 sha 驗證已在 auto_push.py 內完成" in l), None)
        e = next((i for i, l in enumerate(ols) if l.startswith("else:") and i > (s or 0)), None)
        rec("取回 pre-fix 區塊", s is not None and e is not None, f"lines {s}..{e}")
        if s is not None and e is not None:
            oblock = "\n".join(ols[s:e]).rstrip()
            for label, kw in (("閘門 FAIL", dict(recorded=False, push_files=["a.html"], gate_ok=False)),
                              ("無待推產物", dict(recorded=False, push_files=[], gate_ok=True))):
                n, pages, out, rc = run_case(oblock, **kw)
                rec(f"pre-fix：{label} 也會無條件呼叫 --post-push（故必然噴假 404）",
                    n == 1, f"呼叫 {n} 次（修後為 0 或 1，見上）")

    print(f"\n=== 結果：{'PASS' if not FAIL else 'FAIL'}（FAIL {len(FAIL)}）===")
    for f in FAIL:
        print("  - " + f)
    print("  註：本測試為靜態抽出＋stub 執行；未呼叫真 subprocess／網路，未寫任何產物。")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
