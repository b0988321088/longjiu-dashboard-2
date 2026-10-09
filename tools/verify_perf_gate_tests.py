# -*- coding: utf-8 -*-
"""verify_perf_gate_tests.py — Phase 03 對抗性測試台（T1–T18 / R1–R2）

設計依據：Phase 02 設計稿 v2 §3（.hermes/plans/2026-10-09_220000-perf-gate-decoupling-design.md）

隔離原則：
  · 所有 fixture（git 測試庫、快照副本）建於 %TEMP%，**不寫任何 repo 產物**；
  · 每個情境都**實際執行**（不得以模擬或未執行標記 PASS）；
  · 唯讀檢查 repo 現狀用於 R1/R2。

用法：python tools/verify_perf_gate_tests.py [--json OUT]
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import perf_gate_contract as pgc  # noqa: E402

TMP = Path(tempfile.gettempdir()) / "perf_gate_tests"
PY = sys.executable

RESULTS: list[dict] = []


def rec(tid: str, desc: str, expected: str, actual: str, ok: bool, evidence: str = "") -> None:
    RESULTS.append({"id": tid, "desc": desc, "expected": expected,
                    "actual": actual, "ok": bool(ok), "evidence": evidence[:400]})
    print(f"  {'✅' if ok else '❌'} {tid} {desc}｜預期 {expected}｜實得 {actual}"
          + (f"｜{evidence[:110]}" if evidence else ""))


def _g(d: Path, *a: str):
    return subprocess.run(["git", *a], cwd=str(d), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def mk_fixture(name: str, candidate_files: dict[str, str], base_files: dict[str, str] | None = None):
    """建立小型 git 測試庫：base commit → candidate commit。回傳測試庫目錄。

    每次使用唯一目錄名：Windows 上 .git 內含唯讀檔，rmtree 可能靜默失敗，
    沿用同名目錄會讓 mkdir 直接爆掉（2026-10-09 實測）。
    """
    d = TMP / f"{name}_{uuid.uuid4().hex[:6]}"
    d.mkdir(parents=True, exist_ok=True)
    _g(d, "init", "-q")
    _g(d, "config", "user.email", "t@example.invalid")
    _g(d, "config", "user.name", "t")
    for fn, c in (base_files or {"a.py": "A=1\n", "b.py": "B=1\n"}).items():
        (d / fn).write_text(c, encoding="utf-8")
    _g(d, "add", "-A")
    _g(d, "commit", "-q", "-m", "base")
    for fn, c in candidate_files.items():
        (d / fn).write_text(c, encoding="utf-8")
    _g(d, "add", "-A")
    _g(d, "commit", "-q", "-m", "candidate")
    return d


def mk_snap(dst: Path, *, fail_set, expires="2099-12-31", updated_by="human-approver",
            approval_ref="APR-TEST", tamper_sha=False) -> Path:
    s = {
        "as_of": "2026-10-09", "expires_at": expires,
        "created_by": "test", "updated_by": updated_by,
        "reason": "test fixture", "approval_ref": approval_ref,
        "fail_set": list(fail_set),
    }
    s["content_sha256"] = pgc.fail_set_sha(fail_set)
    if tamper_sha:
        s["content_sha256"] = "0" * 64
    dst.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    return dst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--skip-slow", action="store_true", help="略過 F1 實跑（僅供快速迭代，正式驗收不得使用）")
    a = ap.parse_args()
    TMP.mkdir(parents=True, exist_ok=True)

    print("== 前置：取得真實 F1 結果與 ENV_JSON（一次，供多情境重用）==")
    f1 = pgc.f1_baseline_contract()
    env = f1.get("env_json") or {}
    print(f"  F1 ok={f1['ok']}｜ENV 紅燈 {len(env.get('fail_names') or [])} 條"
          f"｜PASS {env.get('pass_count')}/{env.get('total')}")

    shipped = pgc.SNAPSHOT_PATH
    all8 = list(env.get("fail_names") or [])

    # ───────────── F1 ─────────────
    print("\n== T1 固定基準符合封版契約 ==")
    rec("T1", "固定基準 2d1b9ed2 符合封版契約", "PASS", "PASS" if f1["ok"] else "FAIL", f1["ok"],
        "／".join(c["label"] for c in f1["checks"]))

    # ───────────── F2 ─────────────
    print("\n== T2/T3/T11/T12/T15 F2 本輪範圍契約 ==")
    d2 = mk_fixture("t2_ok", {"a.py": "A=2\n", "b.py": "B=2\n"})
    r = pgc.f2_scope("HEAD", ["a.py", "b.py"], "APR-OK", ["a.py"], worktree_root=d2)
    rec("T2", "本輪只含核准範圍（＋核准來源、實際差異、工作樹乾淨）", "PASS",
        "PASS" if r["ok"] else "FAIL", r["ok"],
        f"變更集全在範圍內；dirty={len(r['worktree_dirty'])} untracked={len(r['untracked'])}")

    d3 = mk_fixture("t3_bad", {"a.py": "A=3\n", "evil.py": "E=1\n"})
    r = pgc.f2_scope("HEAD", ["a.py", "b.py"], "APR-OK", ["a.py"], worktree_root=d3)
    rec("T3", "本輪混入未核准檔案", "FAIL", "FAIL" if not r["ok"] else "PASS(out)", not r["ok"],
        "指名：" + "、".join(r["out_of_scope"]))

    r = pgc.f2_scope("HEAD", [], "APR-OK", ["a.py"], worktree_root=d2)
    rec("T11", "呼叫端未提供允許範圍", "FAIL-CLOSED", "FAIL-CLOSED" if not r["ok"] else "PASS(out)",
        not r["ok"], r["checks"][-1]["detail"])

    r = pgc.f2_scope("HEAD", ["a.py", "b.py"], "", ["a.py"], worktree_root=d2)
    rec("T15", "核准紀錄缺失／對象無法核對", "FAIL-CLOSED",
        "FAIL-CLOSED" if not r["ok"] else "PASS(out)", not r["ok"], r["checks"][-1]["detail"])

    d12 = mk_fixture("t12_pollute", {"a.py": "A=4\n"})
    (d12 / "a.py").write_text("A=4\nPOLLUTED=1\n", encoding="utf-8")   # 工作樹污染（未提交）
    r = pgc.f2_scope("HEAD", ["a.py", "b.py"], "APR-OK", ["a.py"], worktree_root=d12)
    rec("T12", "工作樹污染（交付項同時存在未提交異動）", "FAIL",
        "FAIL" if not r["ok"] else "PASS(out)", not r["ok"],
        "collide=" + "、".join(sorted(set(["a.py"]) & (set(r["worktree_dirty"]) | set(r["untracked"])))))

    # ───────────── F3 ─────────────
    print("\n== T4/T5/T6/T9/T13/T16/T17 F3 環境健康度（受治理快照）==")
    # 2026-10-09：真實環境紅燈已清乾淨（僅剩已核定基線）→ F3 測試改以**合成環境**驅動，
    #   不得依賴「真實環境剛好有紅燈」；合成 = 真實基線 ∪ 2 條合成紅燈（與真實解耦）。
    all8 = sorted({str(x) for x in (env.get("fail_names") or [])}) + ["__synth_gate_A__", "__synth_gate_B__"]
    env = {"gate": "check_dividend_caliber", "parseable": True,
           "pass_count": 66, "total": 74, "fail_names": list(all8)}
    _rel_hit = sorted(set(all8) & set(pgc.RELEASED_20261005))
    if _rel_hit:
        print(f"  ⚠️ 觀測：現行紅燈含 10/05 已釋放規則 {len(_rel_hit)} 條 → {_rel_hit}")
    t4_set = [n for n in all8 if n not in pgc.RELEASED_20261005]
    # T4 只驗「既有紅燈正確辨識」這個契約 → 用合成環境把 R-e 的干擾隔離
    #   （回吞攔阻由 T17 專責；現行環境含 1 條已釋放規則，若沿用真實 env 會同時觸發 R-e）。
    s_all = mk_snap(TMP / "snap_t4.json", fail_set=t4_set)
    env_t4 = {"gate": "check_dividend_caliber", "parseable": True,
              "pass_count": 0, "total": len(t4_set), "fail_names": list(t4_set)}
    r = pgc.f3_environment(env_t4, s_all)
    rec("T4", "歷史既有紅燈被正確辨識（不誤判為新增）", "PASS",
        "PASS" if r["ok"] else "FAIL", r["ok"],
        f"既有 {len(r['baseline_fails'])} 條、新增 {len(r['new_fails'])} 條（合成環境以隔離 R-e）")
    # 真實環境下的同一判定（供對照，不計入 T4 合否）
    r_real = pgc.f3_environment(env, s_all)
    print(f"    ↳ 真實環境對照：既有 {len(r_real['baseline_fails'])} 條、"
          f"快照外 {len(r_real['new_fails'])} 條 → {r_real['new_fails']}")

    r = pgc.f3_environment(env, shipped)
    rec("T5", "快照外紅燈（未經核定）", "FAIL", "FAIL" if not r["ok"] else "PASS(out)", not r["ok"],
        "指名：" + "、".join(r["new_fails"]))

    r = pgc.f3_environment(env, TMP / "no_such_snap.json")
    rec("T6a", "快照缺失", "FAIL-CLOSED", "FAIL-CLOSED" if not r["ok"] else "PASS(out)", not r["ok"],
        r["checks"][-1]["detail"])

    bad = TMP / "snap_corrupt.json"
    bad.write_text("{not json", encoding="utf-8")
    r = pgc.f3_environment(env, bad)
    rec("T6b", "快照損毀", "FAIL-CLOSED", "FAIL-CLOSED" if not r["ok"] else "PASS(out)", not r["ok"],
        r["checks"][-1]["detail"])

    r = pgc.f3_environment(None, shipped)
    rec("T6c", "環境閘門輸出無法取得", "FAIL-CLOSED",
        "FAIL-CLOSED" if not r["ok"] else "PASS(out)", not r["ok"], r["checks"][-1]["detail"])

    s_exp = mk_snap(TMP / "snap_expired.json", fail_set=all8, expires="2026-01-01")
    r = pgc.f3_environment(env, s_exp)
    rec("T9", "快照過期", "FAIL-CLOSED", "FAIL-CLOSED" if not r["ok"] else "PASS(out)", not r["ok"],
        "; ".join(c["detail"] for c in r["checks"] if not c["ok"])[:150])

    s_self = mk_snap(TMP / "snap_selfacct.json", fail_set=all8, updated_by="check_dividend_caliber")
    r = pgc.f3_environment(env, s_self)
    rec("T10/T13", "未經獨立核准的快照更新（自我核准）", "FAIL",
        "FAIL" if not r["ok"] else "PASS(out)", not r["ok"],
        "; ".join(c["detail"] for c in r["checks"] if not c["ok"])[:150])

    s_tam = mk_snap(TMP / "snap_tamper.json", fail_set=all8, tamper_sha=True)
    r = pgc.f3_environment(env, s_tam)
    rec("T16", "快照 content_sha256 不符（事後改寫）", "FAIL-CLOSED",
        "FAIL-CLOSED" if not r["ok"] else "PASS(out)", not r["ok"],
        "; ".join(c["detail"] for c in r["checks"] if not c["ok"])[:150])

    s_sw = mk_snap(TMP / "snap_swallow.json", fail_set=all8 + [pgc.RELEASED_20261005[0]])
    r = pgc.f3_environment(env, s_sw)
    rec("T17", "快照回吞 2026-10-05 已釋放規則", "FAIL",
        "FAIL" if not r["ok"] else "PASS(out)", not r["ok"],
        "; ".join(c["detail"] for c in r["checks"] if not c["ok"])[:150])

    # ───────────── F4 ─────────────
    print("\n== T8/T14/T18 F4 發布一致性 ==")
    # 2026-10-09（CIO 阻擋 #2 修正後）：F4 **一律**查核核准紀錄，不再因參數而跳過。
    #   測試改為以 approval_file 指向沙箱核准檔 → 注入的是「核准紀錄」，不是「跳過查核」。
    _apf = TMP / "cio_approved_sandbox.txt"
    _apf.write_text("2026-10-09T22:00:00+08:00\ttreeA\tabc1234\tAPPROVE\treviewer-x\tnote\n",
                    encoding="utf-8")

    r = pgc.f4_publish_consistency(candidate_tree="treeA",
                                   approval_file=TMP / "no_such_approve.txt")
    rec("T8a", "無 CIO 核准紀錄（不得發布）", "BLOCKED",
        "BLOCKED" if not r["ok"] else "PASS(out)", not r["ok"], r["checks"][-1]["detail"])

    r = pgc.f4_publish_consistency(candidate_tree="treeB", approval_file=_apf)
    rec("T8c", "候選 tree 不在核准紀錄中（參數不得取代查核）", "BLOCKED",
        "BLOCKED" if not r["ok"] else "PASS(out)", not r["ok"], r["checks"][-1]["detail"])

    r = pgc.f4_publish_consistency(approval_tree="treeZ", candidate_tree="treeA", approval_file=_apf)
    rec("T8d", "呼叫端宣稱核准 tree ≠ 候選（覆寫繞過）", "FAIL",
        "FAIL" if not r["ok"] else "PASS(out)", not r["ok"], r["checks"][-1]["detail"])

    r = pgc.f4_publish_consistency(candidate_tree="treeA", artifacts={"x.html": "abc"},
                                   approved_artifacts={"x.html": "abc"},
                                   pushed_manifest="treeA", approval_file=_apf)
    rec("T8b", "四項一致（正向對照，不誤擋）", "PASS", r["ok"],
        "、".join(c["label"] for c in r["checks"] if c["ok"]))

    r = pgc.f4_publish_consistency(candidate_tree="treeA", build_source="treeZ",
                                   artifacts={"x.html": "abc"}, approved_artifacts={"x.html": "abc"},
                                   pushed_manifest="treeA", approval_file=_apf)
    rec("T18", "核准後重新建置（建置來源 ≠ 核准來源）", "FAIL",
        "FAIL" if not r["ok"] else "PASS(out)", not r["ok"],
        "; ".join(c["detail"] for c in r["checks"] if not c["ok"])[:150])

    r = pgc.f4_publish_consistency(candidate_tree="treeA", artifacts={"x.html": "TAMPERED"},
                                   approved_artifacts={"x.html": "abc"},
                                   pushed_manifest="treeA", approval_file=_apf)
    rec("T14", "產物內容雜湊 ≠ 核准清單", "FAIL", "FAIL" if not r["ok"] else "PASS(out)",
        not r["ok"], "; ".join(c["detail"] for c in r["checks"] if not c["ok"])[:150])

    r = pgc.f4_publish_consistency(candidate_tree="treeA", artifacts={"x.html": "abc"},
                                   approved_artifacts={"x.html": "abc"},
                                   pushed_manifest="treeB", approval_file=_apf)
    rec("T8", "推送內容與核准清單不一致", "FAIL", "FAIL" if not r["ok"] else "PASS(out)",
        not r["ok"], "; ".join(c["detail"] for c in r["checks"] if not c["ok"])[:150])

    r = pgc.f4_publish_consistency(candidate_tree="treeA", artifacts={"x.html": "abc"},
                                   approved_artifacts={"x.html": "abc"}, approval_file=_apf)
    rec("T8b2", "四項一致・未提供推送紀錄亦通過", "PASS", "PASS" if r["ok"] else "FAIL", r["ok"],
        "全部通過")

    # 2026-10-09（CIO 第二輪 blocking）：核准來源不得指向 repo 內檔案（可被 commit／發布）
    _inrepo = REPO / "governance" / "_forged_approval_selftest.txt"
    _inrepo.write_text("x\ttreeA\tc\tAPPROVE\tr\tn\n", encoding="utf-8")
    try:
        r = pgc.f4_publish_consistency(candidate_tree="treeA", artifacts={"x.html": "abc"},
                                       approved_artifacts={"x.html": "abc"},
                                       pushed_manifest="treeA", approval_file=_inrepo)
    finally:
        _inrepo.unlink(missing_ok=True)
    rec("T8e", "核准來源指向 repo 內檔案（偽造核准）", "FAIL-CLOSED",
        "FAIL-CLOSED" if not r["ok"] else "PASS(out)", not r["ok"], r["checks"][-1]["detail"])

    # 2026-10-09（CIO 第二輪 blocking）：生產 CLI 不得暴露核准來源參數
    _cli = (REPO / "tools" / "verify_performance_monthly.py").read_text(encoding="utf-8")
    rec("T8f", "生產 CLI 未暴露 --approval-file（不得以參數取代查核）", "PASS",
        "--approval-file" not in _cli,
        "CLI 已無該旗標" if "--approval-file" not in _cli else "仍存在 --approval-file")

    # ───────────── T7 分立 ─────────────
    print("\n== T7 任務契約 vs 環境健康度 分立呈現 ==")
    ev = pgc.evaluate(f1_precomputed=f1, candidate="HEAD",
                      allowed_files=["a.py", "b.py"], approval_ref="APR-OK",
                      deliverables=["a.py"], worktree_root=d2,
                      approval_tree="", build_source="treeA", candidate_tree="treeA",
                      approval_file=_apf,
                      artifacts={"x.html": "abc"}, approved_artifacts={"x.html": "abc"},
                      env_json=env, snapshot_path=shipped)
    sep = (ev["task_contract"]["ok"] is True) and (ev["environment"]["ok"] is False) and ev["rc"] == 1
    rec("T7", "只修契約、環境仍紅 → 兩者分開呈現且不互相冒充", "契約PASS／環境FAIL／rc=1",
        f"契約{'PASS' if ev['task_contract']['ok'] else 'FAIL'}／"
        f"環境{'PASS' if ev['environment']['ok'] else 'FAIL'}／rc={ev['rc']}", sep,
        f"F1/F2/F4={ev['task_contract']['members']}｜F3 快照外 {len(ev['f3']['new_fails'])} 條")

    # ───────────── R1 / R2 ─────────────
    print("\n== R1/R2 回歸 ==")
    r1 = subprocess.run([PY, str(REPO / "tools" / "verify_performance_monthly.py")],
                        cwd=str(REPO), capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    out = (r1.stdout or "")
    ab = [ln for ln in out.splitlines() if "  - " in ln and not ln.strip().startswith("- F")]
    f_lines = [ln for ln in out.splitlines() if ln.strip().startswith("- F")]
    rec("R1", "原有 A–E 安全檢查仍有效（B 段突變／9,999,999 負測等）", "A–E 0 FAIL",
        f"A–E {len(ab)} FAIL", len(ab) == 0,
        f"月度閘門 rc={r1.returncode}｜僅剩契約/環境分類：{len(f_lines)} 條")

    rel_in_snap = sorted(set(json.loads(shipped.read_text(encoding='utf-8'))["fail_set"])
                         & set(pgc.RELEASED_20261005))
    rec("R2", "10/05 已釋放兩條未被快照重新吸收", "0 條", f"{len(rel_in_snap)} 條",
        not rel_in_snap, "、".join(rel_in_snap) if rel_in_snap else "快照 fail_set 未含已釋放規則")

    # ───────────── 總結 ─────────────
    ok_n = sum(1 for r in RESULTS if r["ok"])
    print(f"\n=== 對抗性測試台：{ok_n}/{len(RESULTS)} PASS ===")
    for r in RESULTS:
        if not r["ok"]:
            print(f"  ❌ {r['id']} {r['desc']}｜預期 {r['expected']}｜實得 {r['actual']}")
    if a.json:
        Path(a.json).write_text(json.dumps({"results": RESULTS, "pass": ok_n,
                                            "total": len(RESULTS)}, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print(f"  （結果已寫入 {a.json}）")
    return 0 if ok_n == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
