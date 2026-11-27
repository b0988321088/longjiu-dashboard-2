#!/usr/bin/env python
"""核准鏈故障注入測試（2026-11-27 核准鏈修復專案的驗收工具）。

在**獨立沙盒 repo** 內跑，不動真實 repo 的 commit 與核准紀錄。
沙盒會複製 approval_ledger.py 與 cio_approve.py，因此測的是「即將上線的版本」。

案例（對應使用者要求的七條防呆）：
  T1 正常 APPROVE → 查核通過
  T2 --expect-tree 不符 → 拒寫（內容已變必須重審）
  T3 tree 相同但 commit 不同（reset／合併後）→ 查核失敗，且訊息指出需重新綁定
  T4 用 --expect-tree 綁到新 commit → 通過（內容未變可沿用審查結論）
  T5 內容變更後仍拿舊 expect-tree → 拒寫
  T6 verdict=REJECT → 不落紀錄
  T7 重複寫入 → 去重，紀錄行數不增加
  T8 對非 HEAD 的 commit 落紀錄 → 綁在該 commit 上（不再一律綁 HEAD）
  T9 帳本含損壞行 → 忽略損壞行、有效紀錄仍可查核；空帳本 → fail-closed
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable
RESULTS: list[tuple[str, bool, str]] = []


def sh(*args, cwd=None, expect=None):
    p = subprocess.run(list(args), cwd=str(cwd) if cwd else None,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if expect is not None and p.returncode != expect:
        raise AssertionError(f"{' '.join(args)} → rc={p.returncode}\n{p.stdout}\n{p.stderr}")
    return p


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'✅' if ok else '❌'} {name}" + (f"｜{detail}" if detail and not ok else ""))


def new_sandbox() -> Path:
    d = Path(tempfile.mkdtemp(prefix="lj_approval_"))
    shutil.copy2(REPO / "approval_ledger.py", d / "approval_ledger.py")
    shutil.copy2(REPO / "cio_approve.py", d / "cio_approve.py")
    sh("git", "init", "-q", cwd=d)
    sh("git", "config", "user.email", "t@example.com", cwd=d)
    sh("git", "config", "user.name", "T", cwd=d)
    return d


def commit_file(d: Path, name: str, content: str, msg: str) -> tuple[str, str]:
    (d / name).write_text(content, encoding="utf-8")
    sh("git", "add", name, cwd=d)
    sh("git", "commit", "-q", "-m", msg, cwd=d)
    c = sh("git", "rev-parse", "HEAD", cwd=d).stdout.strip()
    t = sh("git", "rev-parse", "HEAD^{tree}", cwd=d).stdout.strip()
    return c, t


def write_json(d: Path, verdict: str = "APPROVE", blocking=None) -> Path:
    f = d / f"_review_{verdict}.json"
    f.write_text(json.dumps({"verdict": verdict, "blocking": blocking or [],
                             "required_fixes": [], "summary": "test"}, ensure_ascii=False),
                 encoding="utf-8")
    return f


def approve(d: Path, *extra: str):
    return sh(PY, "cio_approve.py", "--reviewer", "CIO-Gemini", *extra, cwd=d)


def verify(d: Path, commit: str, tree: str):
    code = ("import sys,json;sys.path.insert(0,'.');import approval_ledger as L;"
            f"ok,r,h=L.verify_commit({commit!r},{tree!r},'.');"
            "print(json.dumps({'ok':ok,'reason':r},ensure_ascii=False))")
    p = sh(PY, "-c", code, cwd=d)
    return json.loads(p.stdout.strip().splitlines()[-1])


def ledger_lines(d: Path) -> int:
    f = d / ".git" / "CIO_APPROVED"
    return len(f.read_text(encoding="utf-8").splitlines()) if f.exists() else 0


def main() -> int:
    d = new_sandbox()
    try:
        j = write_json(d)
        c1, t1 = commit_file(d, "a.txt", "one", "c1")

        # T1 正常
        r = approve(d, "--verdict", "APPROVE", "--result", str(j))
        v = verify(d, c1, t1)
        check("T1 正常 APPROVE 落紀錄並可查核", r.returncode == 0 and v["ok"], v.get("reason", ""))

        # T3 tree 相同、commit 不同（amend／reset 後改寫訊息）→ 必須判失敗並提示重新綁定
        sh("git", "commit", "-q", "--amend", "-m", "c1-rewritten", cwd=d)
        c3 = sh("git", "rev-parse", "HEAD", cwd=d).stdout.strip()
        t3 = sh("git", "rev-parse", "HEAD^{tree}", cwd=d).stdout.strip()
        v = verify(d, c3, t3)
        check("T3 commit 改寫後不自動沿用舊憑證", (not v["ok"]) and "重新綁定" in v["reason"],
              v.get("reason", ""))
        check("T3b 改寫後 tree 確實不變（內容相同）", t3 == t1, f"{t3[:12]} vs {t1[:12]}")

        # T2 --expect-tree 不符（拿 c1 的 tree 套在 c2 上）
        n0 = ledger_lines(d)
        c2, t2 = commit_file(d, "b.txt", "two", "c2")
        r = approve(d, "--verdict", "APPROVE", "--result", str(j), "--commit", c2,
                    "--expect-tree", t1)
        check("T2 --expect-tree 不符 → 拒寫", r.returncode != 0 and ledger_lines(d) == n0,
              f"rc={r.returncode} lines={ledger_lines(d)}")

        # T4 用 expect-tree 重新綁定 → 通過
        r = approve(d, "--verdict", "APPROVE", "--result", str(j), "--commit", c3,
                    "--expect-tree", t3)
        v = verify(d, c3, t3)
        check("T4 --expect-tree 正確 → 重新綁定成功", r.returncode == 0 and v["ok"], v.get("reason", ""))

        # T5 內容變更後拿舊 tree → 拒寫
        n1 = ledger_lines(d)
        c4, t4 = commit_file(d, "a.txt", "changed", "c4")
        r = approve(d, "--verdict", "APPROVE", "--result", str(j), "--commit", c4,
                    "--expect-tree", t3)
        check("T5 內容已變仍拿舊 expect-tree → 拒寫",
              r.returncode != 0 and ledger_lines(d) == n1 and t4 != t3,
              f"rc={r.returncode}")

        # T6 REJECT → 不落
        n2 = ledger_lines(d)
        jr = write_json(d, "REJECT", ["內容不符"])
        r = approve(d, "--verdict", "APPROVE", "--result", str(jr), "--commit", c4,
                    "--expect-tree", t4)
        check("T6 審查結論非 APPROVE → 不落紀錄",
              r.returncode != 0 and ledger_lines(d) == n2, f"rc={r.returncode}")

        # T7 重複寫入去重
        approve(d, "--verdict", "APPROVE", "--result", str(j), "--commit", c4,
                "--expect-tree", t4)
        n3 = ledger_lines(d)
        r = approve(d, "--verdict", "APPROVE", "--result", str(j), "--commit", c4,
                    "--expect-tree", t4)
        check("T7 重複寫入 → 去重不產生重複授權",
              r.returncode == 0 and ledger_lines(d) == n3, f"{n2}→{n3}→{ledger_lines(d)}")

        # T8 對非 HEAD commit 落紀錄
        c5, t5 = commit_file(d, "e.txt", "five", "c5")
        r = approve(d, "--verdict", "APPROVE", "--result", str(j), "--commit", c1,
                    "--expect-tree", t1)
        lines = (d / ".git" / "CIO_APPROVED").read_text(encoding="utf-8").splitlines()
        bound = [ln for ln in lines if ln.split("\t")[2] == c1 and ln.split("\t")[1] == t1]
        v_head = verify(d, c5, t5)
        check("T8 指定非 HEAD commit → 綁在該 commit（非 HEAD）",
              r.returncode == 0 and bound and not v_head["ok"],
              f"bound={len(bound)} head_ok={v_head['ok']}")

        # T9 損壞行容錯 + 空帳本 fail-closed
        with open(d / ".git" / "CIO_APPROVED", "a", encoding="utf-8") as f:
            f.write("broken-line-without-tabs\n")
        v = verify(d, c1, t1)
        ok_corrupt = v["ok"]
        e = new_sandbox()
        try:
            ce, te = commit_file(e, "z.txt", "z", "cz")
            ve = verify(e, ce, te)
        finally:
            shutil.rmtree(e, ignore_errors=True)
        check("T9 帳本含損壞行仍可查核有效紀錄／空帳本 fail-closed",
              ok_corrupt and (not ve["ok"]), f"corrupt_ok={ok_corrupt} empty_ok={ve['ok']}")
    finally:
        shutil.rmtree(d, ignore_errors=True)

    bad = [r for r in RESULTS if not r[1]]
    print("\n" + "=" * 56)
    print(f"核准鏈測試：{len(RESULTS) - len(bad)} PASS / {len(bad)} FAIL")
    print("=" * 56)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
