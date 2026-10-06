# -*- coding: utf-8 -*-
"""tools/verify_scoped_commit.py — per-commit scope isolation 的合成沙箱驗收（A～E）

目的（使用者 2026-10-06 裁決）：
  先做 isolated sandbox / synthetic test，證明
  「別人的 dirty 不會阻擋我，但也絕對不會被我帶進 commit」，
  通過後才允許 21:30 emergency 重走完整產線。不得以當日報告當唯一正向測試。

受測對象：repo 根目錄的 dirty_gate.py（直接 import 本體，非複製品）。
測試環境：$LOCALAPPDATA/Temp 下每次新建的獨立 git repo（合成檔名，不碰真實 repo）。

測試項：
  A 本班 A 類 dirty ＋ B/C 類 dirty 同時存在，scope 正確 → A 可安全 stage/commit
  B 嘗試 stage 一個 B/C 類檔案 → 必須 STOP（不 commit）
  C heartbeat 類 runtime dirty 持續存在 → A 仍可 commit，且 heartbeat 絕不進 commit、內容原狀
  D manifest 故意少列本班應提交檔 → 必須 STOP
  E manifest 故意加入不屬於本班的檔案 → E1/E2 必須 STOP；E3 具名人工核可後才放行

另含：全程驗證 scope 外檔案 sha256 不變（不得被改動／刪除／覆寫）。
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import dirty_gate as G  # noqa: E402  受測本體

RESULTS: list = []


def sha(fp: Path) -> str:
    h = hashlib.sha256()
    with open(fp, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def sh(cwd: Path, *args):
    st = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    if st.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} rc={st.returncode}: {(st.stderr or st.stdout)[:200]}")
    return st.stdout


def new_sandbox(tag: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix=f"scopeiso_{tag}_",
                                 dir=os.environ.get("LOCALAPPDATA", tempfile.gettempdir()) + "/Temp"
                                 if os.path.isdir(os.environ.get("LOCALAPPDATA", "") + "/Temp") else None))
    sh(root, "init", "-q")
    sh(root, "config", "user.email", "sandbox@test")
    sh(root, "config", "user.name", "sandbox")
    sh(root, "config", "core.autocrlf", "false")
    (root / "data").mkdir(exist_ok=True)
    # A 類（本班產物）
    (root / "a_report.html").write_text("A v0\n", encoding="utf-8")
    (root / "a_data.json").write_text('{"v":0}\n', encoding="utf-8")
    # B 類（其他既有合法變更）
    (root / "b_other.html").write_text("B v0\n", encoding="utf-8")
    # C 類（runtime，非本班）
    (root / "data" / "heartbeat.json").write_text('{"hb":0}\n', encoding="utf-8")
    sh(root, "add", "--", ".")
    sh(root, "commit", "-q", "-m", "base")
    # 製造 dirty（A/B/C 全部 dirty，模擬今晚實況）
    (root / "a_report.html").write_text("A v1 — 本班產物\n", encoding="utf-8")
    (root / "a_data.json").write_text('{"v":1}\n', encoding="utf-8")
    (root / "b_other.html").write_text("B v1 — 別人的變更\n", encoding="utf-8")
    (root / "data" / "heartbeat.json").write_text('{"hb":1}\n', encoding="utf-8")
    return root


def head_files(root: Path) -> set:
    return {l.strip() for l in sh(root, "show", "--name-only", "--format=", "HEAD").splitlines() if l.strip()}


def staged(root: Path) -> set:
    return {l.strip() for l in sh(root, "diff", "--cached", "--name-only").splitlines() if l.strip()}


def record(name, ok, detail):
    RESULTS.append((name, ok, detail))
    print(f"  {'✅ PASS' if ok else '❌ FAIL'}  {name}：{detail}")


A = ["a_report.html", "a_data.json"]


def try_stop(fn):
    """回傳 (是否 STOP, detail)。STOP = SystemExit(EXIT_DIRTY)。"""
    try:
        fn()
        return False, "未 STOP"
    except SystemExit as e:
        return int(e.code or 0) == G.EXIT_DIRTY, f"STOP rc={e.code}"


# ── Test A ───────────────────────────────────────────────────────────────
def test_A():
    sb = new_sandbox("A")
    outside_before = {p: sha(sb / p) for p in ("b_other.html", "data/heartbeat.json")}
    m = G.build_manifest(label="sandboxA", produced=A, base=sb)
    stage_stop, d1 = try_stop(lambda: G.assert_scoped_commit(m, base=sb))
    sh(sb, "add", "--", *m["allow"])
    staged_stop, d2 = try_stop(lambda: G.assert_staged_in_scope(m, base=sb))
    if not (stage_stop or staged_stop):  # 未 STOP → 才繼續 commit
        sh(sb, "commit", "-q", "-m", "data: A only")
    committed = head_files(sb)
    outside_after = {p: sha(sb / p) for p in ("b_other.html", "data/heartbeat.json")}
    ok = (not stage_stop and not staged_stop and committed == set(A)
          and outside_after == outside_before)
    record("A 本班 scope 正確 → A 可安全提交（B/C dirty 同時存在）", ok,
           f"pre={'STOP' if stage_stop else 'OK'} post={'STOP' if staged_stop else 'OK'}｜"
           f"commit 內容={sorted(committed)}｜B/C 未被改動={outside_after == outside_before}｜sb={sb}")


# ── Test B ───────────────────────────────────────────────────────────────
def test_B():
    sb = new_sandbox("B")
    before = head_files(sb)
    m = G.build_manifest(label="sandboxB", produced=A, base=sb)
    G.assert_scoped_commit(m, base=sb)
    sh(sb, "add", "--", *m["allow"])
    sh(sb, "add", "--", "b_other.html")          # 故意 stage 一個 B 類
    stop, detail = try_stop(lambda: G.assert_staged_in_scope(m, base=sb))
    still_same = head_files(sb) == before
    ok = stop and still_same and "b_other.html" in "".join(staged(sb))
    record("B 嘗試 stage 一個 B/C 類檔案 → 必須 STOP 且不得 commit", ok,
           f"{detail}｜HEAD 未動={still_same}｜staged={sorted(staged(sb))}｜sb={sb}")
    sh(sb, "reset", "-q")                        # 沙箱還原 index（只動沙箱）


# ── Test C ───────────────────────────────────────────────────────────────
def test_C():
    sb = new_sandbox("C")
    hb = sb / "data/heartbeat.json"
    hb_sha_before = sha(hb)
    m = G.build_manifest(label="sandboxC", produced=A, base=sb)
    G.assert_scoped_commit(m, base=sb)
    sh(sb, "add", "--", *m["allow"])
    G.assert_staged_in_scope(m, base=sb)
    sh(sb, "commit", "-q", "-m", "data: A only")
    committed = head_files(sb)
    hb_sha_after = sha(hb)
    dirty = G.dirty_paths(sb)
    ok = (committed == set(A) and "data/heartbeat.json" not in committed
          and hb_sha_after == hb_sha_before and "data/heartbeat.json" in dirty)
    record("C heartbeat 持續 dirty → A 仍可 commit，heartbeat 絕不進 commit 且原狀", ok,
           f"commit={sorted(committed)}｜heartbeat 進 commit={'是' if 'data/heartbeat.json' in committed else '否'}"
           f"｜內容不變={hb_sha_after == hb_sha_before}｜仍 dirty={('data/heartbeat.json' in dirty)}｜sb={sb}")


# ── Test D ───────────────────────────────────────────────────────────────
def test_D():
    sb = new_sandbox("D")
    before = head_files(sb)
    # 本班應提交 2 檔，manifest 故意只允許 1 檔（少列）
    m = G.build_manifest(label="sandboxD", produced=A, allow=["a_report.html"], base=sb)
    viol = G.manifest_violations(m, base=sb)
    stop, detail = try_stop(lambda: G.assert_scoped_commit(m, base=sb))
    ok = stop and any("少列" in x for x in viol) and head_files(sb) == before and not staged(sb)
    record("D manifest 故意少列本班應提交檔 → 必須 STOP（不得偷偷提交）", ok,
           f"{detail}｜違規={viol[:1]}｜HEAD 未動={head_files(sb) == before}｜sb={sb}")


# ── Test E ───────────────────────────────────────────────────────────────
def test_E():
    sb = new_sandbox("E")
    before = head_files(sb)
    # E1：allow 混入 B 類、無人工核可
    m1 = G.build_manifest(label="sandboxE1", produced=["a_report.html"],
                          allow=["a_report.html", "b_other.html"], base=sb)
    s1, d1 = try_stop(lambda: G.assert_scoped_commit(m1, base=sb))
    # E2：列出 allow_extra 但缺具名理由
    m2 = G.build_manifest(label="sandboxE2", produced=["a_report.html"],
                          allow=["a_report.html", "b_other.html"],
                          allow_extra=[{"path": "b_other.html", "reason": "  "}], base=sb)
    s2, d2 = try_stop(lambda: G.assert_scoped_commit(m2, base=sb))
    # E3：具名人工核可 → 才放行
    m3 = G.build_manifest(label="sandboxE3", produced=["a_report.html"],
                          allow=["a_report.html", "b_other.html"],
                          allow_extra=[{"path": "b_other.html",
                                        "reason": "人工核可：本輪授權一併提交 b_other.html（測試）"}],
                          base=sb)
    s3, d3 = try_stop(lambda: G.assert_scoped_commit(m3, base=sb))
    ok = s1 and s2 and (not s3) and head_files(sb) == before and not staged(sb)
    record("E allow 混入非本班檔案 → E1/E2 必須 STOP；E3 具名人工核可後才放行", ok,
           f"E1[{d1}] E2[{d2}] E3[{d3}]｜HEAD 未動={head_files(sb) == before}｜sb={sb}")


def main() -> int:
    print("=" * 66)
    print("  per-commit scope isolation — 合成沙箱負向驗收（A～E）")
    print(f"  受測模組：{REPO / 'dirty_gate.py'}")
    print("=" * 66)
    for fn in (test_A, test_B, test_C, test_D, test_E):
        fn()
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("-" * 66)
    print(f"  結果：PASS {passed} / {len(RESULTS)}")
    for n, ok, _ in RESULTS:
        if not ok:
            print(f"    ❌ {n}")
    print("-" * 66)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
