#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/test_emergency_no_commit.py — B1／§4 緊急應變「只產出、不提交」離線驗收測試（2026-10-15）

對應使用者 2026-10-15 B1 授權（§4）：
  「緊急應變：預設關閉提交功能。驗收時確認不產生新 commit，且既有產出與告警正常。」

驗證行為：
  E1 預設（LJ_EMERGENCY_COMMIT 未設）→ _commit_own() 不呼叫任何 git 寫入（add／commit／push）
  E2 負向自測：旗標開啟（=1）→ 同一支函式**確實**會 add＋commit（證明 E1 的斷言有鑑別力）
  E3 產物不存在時仍安全回 0、不呼叫 git
  E4 產出（generate_emergency_report）仍寫出兩份 HTML，且不觸發任何 git 動作
  E5 負向自測：缺 snapshot.json → 產出不得假成功（無檔案寫出）
  E6 rc 語意不變：呼叫端彙總（_rcs／_ok_own）仍把 rc=0 視為成功
  E7 全檔唯一 git 寫入點＝_commit_own()（證明「不提交」是可完全關閉的閘門）
  E8–E10 發布計畫層（publish_plan／_plan_violations）：未授權時不含 daily_deploy.py、
        regenerate_report 一律帶 --no-push、計畫自檢 fail-closed；並以負向自測證明有鑑別力
  E11 未授權 ＋ **真 git ＋ 真 bare 遠端**：零 commit、index 無 staged、遠端 ref 不變、推送出口未觸及
  E12 負向自測：授權時確實產生 1 顆 commit（內容恰為自家兩檔）且確實觸及推送出口

離線：不連網。E1–E10 以打樁（不呼叫真 git）；E11／E12 在 $TEMP 的獨立 repo ＋ 本地 bare 遠端
以**真 git** 實跑（不觸碰產線 repo 的 HEAD／index／remote，遠端為本機暫存，全程無網路）。
執行：python -X utf8 tools/test_emergency_no_commit.py
"""
from __future__ import annotations

import ast
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "emergency_1330.py"
PASS = FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")


# ── 從真檔以 AST 抽出「資料 + 函式」，不執行整支腳本（腳本有網路／git 副作用） ──
_TREE = ast.parse(SRC.read_text(encoding="utf-8"))
_WANT_ASSIGN = {"_OWN_FILES", "_COMMIT_ENABLED", "_PUBLISH_CAPABLE", "_NO_PUSH_CAPABLE"}
_WANT_FUNC = {"_commit_own", "generate_emergency_report", "publish_plan", "_plan_violations"}


def _extract(*names: str) -> str:
    picked = []
    for node in _TREE.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in names:
            picked.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in names:
            picked.append(node)
    mod = ast.Module(body=picked, type_ignores=[])
    ast.fix_missing_locations(mod)
    return ast.unparse(ast.fix_missing_locations(mod))


class _StubRun:
    """假的 subprocess.run：記錄呼叫、永不真的執行（離線、無副作用）。"""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, cmd, *a, **kw):  # noqa: ANN001
        self.calls.append([str(x) for x in cmd])
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    def run(self, cmd, *a, **kw):  # noqa: ANN001
        """讓受測碼以 subprocess.run(...) 呼叫時也走同一支打樁。"""
        return self(cmd, *a, **kw)

    def git_verbs(self) -> list[str]:
        out = []
        for c in self.calls:
            if len(c) >= 2 and Path(c[0]).name.startswith("git"):
                out.append(c[1])
        return out

    def touched_auto_push(self) -> bool:
        return any("auto_push.py" in " ".join(c) for c in self.calls)


def _ns(tmp: Path, flag: str | None, stub: _StubRun, extra_src: str = "") -> dict:
    """組出受測命名空間：只放被抽出的節點，LJ 指向沙盒。"""
    env_backup = os.environ.get("LJ_EMERGENCY_COMMIT")
    if flag is None:
        os.environ.pop("LJ_EMERGENCY_COMMIT", None)
    else:
        os.environ["LJ_EMERGENCY_COMMIT"] = flag
    src = _extract(*sorted(_WANT_ASSIGN)) + "\n" + _extract(*sorted(_WANT_FUNC)) + "\n" + extra_src
    ns: dict = {
        "LJ": tmp,
        "today": "2026-10-15",
        "subprocess": stub,
        "sys": sys,
        "json": __import__("json"),
        "re": __import__("re"),
        "datetime": __import__("datetime").datetime,
        "Path": Path,
        "os": os,
    }
    exec(compile(src, "<emergency_1330:extract>", "exec"), ns)   # noqa: S102
    if env_backup is None:
        os.environ.pop("LJ_EMERGENCY_COMMIT", None)
    else:
        os.environ["LJ_EMERGENCY_COMMIT"] = env_backup
    return ns


def _sandbox(files: list[str]) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="lj_s4_"))
    for f in files:
        src = ROOT / f
        dst = tmp / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copyfile(src, dst)
    return tmp


def _real_git_sandbox(today: str) -> dict:
    """真 git 沙盒：真 repo ＋ 真 bare 遠端 ＋（替身）auto_push.py。

    E1–E10 以打樁驗證「不會呼叫 git」；此處改用**真 git 執行同一支 _commit_own()**，
    以 HEAD／index／工作區／遠端 ref 四個實體狀態證明「不提交、不推送」不是打樁假象。
    替身 auto_push.py 只寫出 marker（不真的推送）→ 可精確判定「推送出口有沒有被觸及」。
    """
    tmp = Path(tempfile.mkdtemp(prefix="lj_s4real_"))
    repo, bare = tmp / "repo", tmp / "remote.git"
    repo.mkdir()
    g = lambda *a, **kw: subprocess.run(["git", *a], cwd=str(repo), capture_output=True,
                                        text=True, encoding="utf-8", errors="replace", **kw)
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], capture_output=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(repo), capture_output=True)
    g("config", "user.email", "t@example.invalid")
    g("config", "user.name", "t")
    g("config", "core.autocrlf", "false")
    (repo / "asset_diff_history.json").write_text('{"v":1}', encoding="utf-8", newline="\n")
    (repo / f"buffett_cto_report_{today}.md").write_text("v1", encoding="utf-8", newline="\n")
    (repo / "auto_push.py").write_text(
        "import sys, pathlib\n"
        "pathlib.Path('PUSH_CALLED.txt').write_text(' '.join(sys.argv[1:]), encoding='utf-8')\n"
        "sys.exit(0)\n", encoding="utf-8", newline="\n")
    g("add", "--", "asset_diff_history.json", f"buffett_cto_report_{today}.md", "auto_push.py")
    g("commit", "-q", "-m", "base")
    g("remote", "add", "origin", str(bare))
    g("push", "-q", "-u", "origin", "main")
    # 製造 dirty（＝13:00 產線寫入後的實況：自家兩檔有未提交變更）
    (repo / "asset_diff_history.json").write_text('{"v":2}', encoding="utf-8", newline="\n")
    (repo / f"buffett_cto_report_{today}.md").write_text("v2", encoding="utf-8", newline="\n")
    return {"repo": repo, "bare": bare, "g": g}


def _state(sb: dict) -> dict:
    g, repo = sb["g"], sb["repo"]
    return {
        "head": (g("rev-parse", "HEAD").stdout or "").strip(),
        "n": len([x for x in (g("rev-list", "HEAD").stdout or "").split() if x]),
        "staged": [x for x in (g("diff", "--cached", "--name-only").stdout or "").split() if x],
        "dirty": {ln[3:].strip() for ln in (g("status", "--porcelain").stdout or "").splitlines() if ln.strip()},
        "remote": (g("rev-parse", "origin/main").stdout or "").strip(),
        "marker": (repo / "PUSH_CALLED.txt").exists(),
    }


def _commit_files(repo: Path) -> set[str]:
    out = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=str(repo),
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout or ""
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


def main() -> int:
    print("=== §4 緊急應變預設不提交 ===")
    today = "2026-10-15"
    own = [f"buffett_cto_report_{today}.md"]

    # E1 預設：不提交
    tmp = _sandbox(["asset_diff_history.json", *own])
    stub = _StubRun()
    ns = _ns(tmp, None, stub)
    _buf = io.StringIO()
    with contextlib.redirect_stdout(_buf):
        rc = ns["_commit_own"]()
    _out = _buf.getvalue()
    check("E1a 旗標未設 → 回 0", rc == 0, f"rc={rc}")
    check("E1b 旗標未設 → 零 git 寫入", stub.git_verbs() == [] and not stub.calls,
          f"calls={stub.calls[:3]}")
    check("E1c 旗標未設 → 不觸及 auto_push.py", not stub.touched_auto_push())
    check("E1d 明確列出待提交清單（非靜默、非假成功）",
          "待提交" in _out and f"buffett_cto_report_{today}.md" in _out, f"out={_out[:120]!r}")

    # E2 負向自測：規則停用（旗標開啟）→ 斷言必須變紅
    stub2 = _StubRun()
    ns2 = _ns(tmp, "1", stub2)
    rc2 = ns2["_commit_own"]()
    check("E2 負向自測：旗標=1 → 確實 add＋commit（E1 有鑑別力）",
          "add" in stub2.git_verbs() and "commit" in stub2.git_verbs(),
          f"verbs={stub2.git_verbs()}")
    check("E2b 旗標=1 → 觸及 auto_push.py（推送出口）", stub2.touched_auto_push())
    check("E2c 旗標=1 → 回傳值為 int", isinstance(rc2, int))

    # E3 產物不存在 → 安全略過
    tmp3 = _sandbox([])
    stub3 = _StubRun()
    rc3 = _ns(tmp3, None, stub3)["_commit_own"]()
    check("E3 產物不存在 → 回 0 且零呼叫", rc3 == 0 and not stub3.calls, f"rc={rc3}")

    # E4 產出仍正常（離線；update_all 以打樁取代，避免副作用）
    tmp4 = _sandbox(["snapshot.json"])
    stub4 = _StubRun()
    fake = types.ModuleType("update_all")
    fake.calc_penetration = lambda *a, **kw: {          # noqa: ARG005
        "台股市值型成長": 100.0, "美股市值型成長": 200.0, "防守型配息": 300.0,
        "債券": 400.0, "現金/安全網": 500.0, "_meta": {}}
    sys.modules["update_all"] = fake
    try:
        ns4 = _ns(tmp4, None, stub4)
        ns4["generate_emergency_report"](None, None, None)
    finally:
        sys.modules.pop("update_all", None)
    f_rail = tmp4 / f"emergency_report_{today}.html"
    f_tx = tmp4 / f"emergency_taiex_report_{today}.html"
    check("E4a 產出 emergency_report（Railway 版）", f_rail.exists())
    check("E4b 產出 emergency_taiex_report（GitHub 版）", f_tx.exists())
    _html = f_rail.read_text(encoding="utf-8") if f_rail.exists() else ""
    check("E4c 內容含資產穿透卡＋合計列",
          "資產穿透" in _html and "合計" in _html, f"len={len(_html)}")
    check("E4d 產出過程零 git 動作", not stub4.calls, f"calls={stub4.calls[:2]}")

    # E5 負向自測：缺 snapshot → 不得假成功
    tmp5 = _sandbox([])
    ok5 = False
    try:
        _ns(tmp5, None, _StubRun())["generate_emergency_report"](None, None, None)
    except Exception:  # noqa: BLE001
        ok5 = True
    check("E5 負向自測：缺 snapshot.json → 直接失敗（不寫出空報告）",
          ok5 and not (tmp5 / f"emergency_report_{today}.html").exists())

    # E6 rc 語意不變（呼叫端彙總）
    _src = SRC.read_text(encoding="utf-8")
    check("E6a 呼叫點仍是 _ok_own = _commit_own()", "_ok_own = _commit_own()" in _src)
    check("E6b 失敗判定仍為 rc not in (0, 3)", "rc not in (0, 3)" in _src)
    check("E6c rc 彙總仍含『產物補提交』", '_rcs["產物補提交"] = _ok_own' in _src)

    # E7 全檔唯一 git 寫入點＝_commit_own
    _git_sites = []
    for node in ast.walk(_TREE):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "run":
            seg = ast.get_source_segment(_src, node) or ""
            if "git" in seg or "auto_push" in seg:
                _git_sites.append((node.lineno, seg.splitlines()[0][:70]))
    _in_commit = [n for n in _TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_commit_own"]
    _c_lo, _c_hi = _in_commit[0].lineno, _in_commit[0].end_lineno
    _outside = [s for s in _git_sites if not (_c_lo <= s[0] <= _c_hi)]
    check("E7 沒有任何 _commit_own() 之外的 git／auto_push 呼叫點",
          _outside == [], f"outside={_outside}")

    # ── E8/E9/E10（2026-10-15 P0-3 修復）：發布路徑改由「計畫層」攔截並驗證 ──────────
    #   舊版 E7 只掃本檔字面 → 看不到 daily_deploy.py 子程序內部的 commit／push（實際漏放）。
    #   修法：發布步驟由 publish_plan() 單一決定，測試直接驗「計畫內容」＋負向自測。
    _ns8 = _ns(_sandbox([]), None, _StubRun())
    _plan_off = _ns8["publish_plan"](False, _sandbox([]), sys.executable)
    _cmds_off = [" ".join(str(x) for x in _c) for _l, _c, _t in _plan_off]
    check("E8a 未授權 → 計畫不含 daily_deploy.py（推送步驟整步不列入）",
          not any("daily_deploy.py" in _c for _c in _cmds_off), str(_cmds_off))
    check("E8b 未授權 → regenerate_report.py 一律帶 --no-push（只產出、不提交）",
          any("regenerate_report.py" in _c and "--no-push" in _c for _c in _cmds_off), str(_cmds_off))
    check("E8c 未授權 → fail-closed 自檢判定計畫無違規",
          _ns8["_plan_violations"](_plan_off) == [], str(_ns8["_plan_violations"](_plan_off)))
    check("E8d 未授權 → 仍保留產出步驟（只產出、不發布）",
          any("asset_diff_monitor.py" in _c for _c in _cmds_off) and len(_plan_off) == 2, str(_cmds_off))
    # 負向自測：授權 → 推送步驟必須出現（證明 E8 有鑑別力）
    _plan_on = _ns8["publish_plan"](True, _sandbox([]), sys.executable)
    _cmds_on = [" ".join(str(x) for x in _c) for _l, _c, _t in _plan_on]
    check("E9a 負向自測：授權 → 計畫含 daily_deploy.py",
          any("daily_deploy.py" in _c for _c in _cmds_on), str(_cmds_on))
    check("E9b 負向自測：授權 → regenerate_report 不再帶 --no-push",
          any("regenerate_report.py" in _c and "--no-push" not in _c for _c in _cmds_on), str(_cmds_on))
    # fail-closed 自檢本身要有鑑別力：人工塞入未降級發布步驟必須被判違規
    _tampered = [("推送", [sys.executable, str(Path("x") / "daily_deploy.py")], 600),
                 ("日報", [sys.executable, str(Path("x") / "regenerate_report.py")], 600)]
    check("E10a 負向自測：未降級發布步驟 → 被判違規（2 項）",
          len(_ns8["_plan_violations"](_tampered)) == 2,
          str(_ns8["_plan_violations"](_tampered)))
    check("E10b 違規時中止不執行任何步驟（執行前守門存在）",
          "if _viol:" in _src and "sys.exit(1)" in _src)
    check("E10c 略過推送時明確揭露（略過 ≠ 失敗）",
          "推送步驟已略過" in _src and '_rcs["推送"] = 0' in _src)

    # ── E11/E12（2026-10-15 P0-3 驗收補強）：真 git ＋ 真遠端下，未授權路徑零 commit／零推送 ──
    #   E1–E10 以打樁證明「不會呼叫 git」；打樁證明不了「真的跑下去也不會」。本節以**真 git**、
    #   真 bare 遠端重跑同一支 _commit_own()，逐一比對 HEAD／commit 數／index／工作區／遠端 ref。
    sb11 = _real_git_sandbox(today)
    s11_before = _state(sb11)
    buf11 = io.StringIO()
    with contextlib.redirect_stdout(buf11):
        rc11 = _ns(sb11["repo"], None, subprocess)["_commit_own"]()
    out11 = buf11.getvalue()
    s11_after = _state(sb11)
    check("E11a 未授權（真 git）→ 回 0 並列出待提交清單",
          rc11 == 0 and "待提交" in out11, f"rc={rc11} out={out11[:120]!r}")
    check("E11b HEAD 未動、commit 數不變（零 commit）",
          s11_after["head"] == s11_before["head"] and s11_after["n"] == s11_before["n"],
          f"{s11_before['head'][:8]}→{s11_after['head'][:8]}")
    check("E11c index 無任何 staged 變更（不污染既有 index）", s11_after["staged"] == [],
          str(s11_after["staged"]))
    check("E11d 自家兩檔仍為未提交 dirty（內容留在工作區）",
          {"asset_diff_history.json", f"buffett_cto_report_{today}.md"} <= s11_after["dirty"],
          str(sorted(s11_after["dirty"])))
    check("E11e 遠端 ref 未動（零 push）", s11_after["remote"] == s11_before["remote"],
          s11_after["remote"][:8])
    check("E11f 推送出口（auto_push.py）未被觸及", not s11_after["marker"])
    # 負向自測：授權 → 確實 commit 且確實觸及推送出口（證明 E11 的斷言有鑑別力）
    sb12 = _real_git_sandbox(today)
    s12_before = _state(sb12)
    buf12 = io.StringIO()
    with contextlib.redirect_stdout(buf12):
        rc12 = _ns(sb12["repo"], "1", subprocess)["_commit_own"]()
    s12_after = _state(sb12)
    _cf12 = _commit_files(sb12["repo"])
    check("E12a 負向自測：授權 → HEAD 前進 1 顆、commit 內容恰為自家兩檔",
          rc12 == 0 and s12_after["n"] == s12_before["n"] + 1
          and _cf12 == {"asset_diff_history.json", f"buffett_cto_report_{today}.md"},
          f"rc={rc12} files={_cf12}")
    check("E12b 負向自測：授權 → 推送出口確實被觸及（marker 生成）", s12_after["marker"])
    check("E12c 負向自測：授權才提交，且 index 無殘留 staged（不吞半成品）",
          s12_after["staged"] == [], str(s12_after["staged"]))
    shutil.rmtree(sb11["repo"].parent, ignore_errors=True)
    shutil.rmtree(sb12["repo"].parent, ignore_errors=True)

    print(f"\n測試結果：{PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
