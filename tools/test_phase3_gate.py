# -*- coding: utf-8 -*-
"""F1 第三階段測試：07:00 呼叫端的四態分流（gate）與接線存在性。

驗收邊界（2026-10-21 使用者授權）：
  - 只在 %TEMP% 沙箱驗證；正式 repo 零寫入（T00 以 git status 前後比對）。
  - 不執行 regenerate_report.py（會寫正式報表）；接線以原始碼標記＋AST 解析證明。
  - 只驗「呼叫端能不能用錯」：rc=0 不等於通過、非 inject 不得複製／注入／發布。

用法：python tools/test_phase3_gate.py
"""
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

TMP = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Temp" / "f1_phase3"
SANDBOX = TMP / "staging"
DATE = "2026-10-20"
GEN_OK = f"{DATE}T21:34:00+08:00"

import staging_handoff as sh  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("  PASS " if ok else "  FAIL ") + name + ("｜" + str(detail) if detail else ""))


def repo_status():
    r = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def reset(tag, flag=None):
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX, ignore_errors=True)
    os.environ["LJ_HANDOFF_ROOT"] = str(SANDBOX)
    if flag is None:
        os.environ.pop("LJ_EMERGENCY_HANDOFF", None)
    else:
        os.environ["LJ_EMERGENCY_HANDOFF"] = flag
    return sh.day_dir(DATE, SANDBOX)


def seed(d: Path, tamper=False):
    d.mkdir(parents=True, exist_ok=True)
    (d / "analysis.json").write_bytes(json.dumps(
        {"generated_at": GEN_OK, "full_report": "x" * 800, "source": "美股開盤"},
        ensure_ascii=False).encode("utf-8"))
    (d / f"emergency_report_{DATE}.html").write_bytes(b"<html>rail</html>")
    (d / f"emergency_taiex_report_{DATE}.html").write_bytes(b"<html>gh</html>")
    r = sh.seal(DATE, root_dir=SANDBOX)
    assert r.state == sh.VALID, r.codes
    if tamper:
        p = d / "analysis.json"
        b = p.read_bytes()
        i = b.find(b"x")
        p.write_bytes(b[:i] + b"y" + b[i + 1:])
    return d


def t_legacy_no_dir():
    print("\n[G1] 未設旗標 + 無當日資料 → legacy（舊行為不變）")
    reset("g1")
    g = sh.gate(DATE, SANDBOX)
    check("mode=legacy", g.mode == sh.MODE_LEGACY, g.mode)
    check("rc=0", g.rc == 0, g.rc)
    check("may_copy=False", g.may_copy() is False, g.may_copy())


def t_legacy_explicit_off():
    print("\n[G2] 顯式 off + 無當日資料 → legacy")
    reset("g2", flag="off")
    g = sh.gate(DATE, SANDBOX)
    check("mode=legacy", g.mode == sh.MODE_LEGACY, g.mode)


def t_disabled_with_data():
    print("\n[G3] 旗標關閉但有當日資料 → blank + rc13（禁止回退舊 JSON）")
    reset("g3", flag="off")
    seed(sh.day_dir(DATE, SANDBOX))
    g = sh.gate(DATE, SANDBOX)
    check("mode=blank", g.mode == sh.MODE_BLANK, g.mode)
    check("rc=13", g.rc == 13, g.rc)
    check("public=H90 對照文字", g.public == sh.PUBLIC_TEXT["H90"], g.public)
    check("may_copy=False（不得注入）", g.may_copy() is False, g.may_copy())


def t_inject():
    print("\n[G4] 旗標 on + 驗證通過 → inject（唯一可複製／發布）")
    reset("g4", flag="on")
    seed(sh.day_dir(DATE, SANDBOX))
    g = sh.gate(DATE, SANDBOX)
    check("mode=inject", g.mode == sh.MODE_INJECT, g.mode)
    check("rc=0", g.rc == 0, g.rc)
    check("may_copy=True", g.may_copy() is True, g.may_copy())
    check("analysis 為 dict（可注入）", isinstance(g.result.analysis, dict), type(g.result.analysis))


def t_block():
    print("\n[G5] 旗標 on + 驗證失敗 → block + rc12（應變段硬擋）")
    reset("g5", flag="on")
    seed(sh.day_dir(DATE, SANDBOX), tamper=True)
    g = sh.gate(DATE, SANDBOX)
    check("mode=block", g.mode == sh.MODE_BLOCK, g.mode)
    check("rc=12", g.rc == 12, g.rc)
    check("public=H06 對照文字", g.public == sh.PUBLIC_TEXT["H06"], g.public)
    check("不得注入（may_copy=False）", g.may_copy() is False, g.may_copy())
    check("analysis 為 None", g.result.analysis is None, g.result.analysis)


def t_dryrun_ok():
    print("\n[G6] dry-run + 驗證通過 → blank + rc0（rc0 不代表通過）")
    reset("g6", flag="dry-run")
    seed(sh.day_dir(DATE, SANDBOX))
    g = sh.gate(DATE, SANDBOX)
    check("mode=blank（不注入也不發布）", g.mode == sh.MODE_BLANK, g.mode)
    check("rc=0", g.rc == 0, g.rc)
    check("may_copy=False", g.may_copy() is False, g.may_copy())
    check("state 仍為 VALID_DRYRUN（狀態可追溯）", g.state == sh.VALID_DRYRUN, g.state)


def t_dryrun_fail():
    print("\n[G7] dry-run + 驗證失敗 → blank + rc0，但狀態紀錄為失敗")
    reset("g7", flag="dry-run")
    seed(sh.day_dir(DATE, SANDBOX), tamper=True)
    g = sh.gate(DATE, SANDBOX)
    check("mode=blank", g.mode == sh.MODE_BLANK, g.mode)
    check("rc=0（不阻擋，但非通過）", g.rc == 0, g.rc)
    check("state=INVALID_DRYRUN", g.state == sh.INVALID_DRYRUN, g.state)
    check("may_copy=False", g.may_copy() is False, g.may_copy())
    log = sh.status_log(DATE, SANDBOX)
    check("狀態留痕 invalid_dry_run", any(r.get("action") == "invalid_dry_run" for r in log),
          [r.get("action") for r in log])


def t_unknown_flag():
    print("\n[G8/G9] 未知旗標值 → 視為 off（fail-safe）；不憑空建立當日目錄")
    reset("g8", flag="ONNN")
    g = sh.gate(DATE, SANDBOX)
    check("無資料時 mode=legacy（不是 rc13 假警報）", g.mode == sh.MODE_LEGACY, g.mode)
    check("未憑空建立當日目錄", not sh.day_dir(DATE, SANDBOX).exists(), sh.day_dir(DATE, SANDBOX))
    reset("g9", flag="ONNN")
    seed(sh.day_dir(DATE, SANDBOX))
    g2 = sh.gate(DATE, SANDBOX)
    log = sh.status_log(DATE, SANDBOX)
    check("有資料時 mode=blank + rc13", (g2.mode == sh.MODE_BLANK and g2.rc == 13), (g2.mode, g2.rc))
    check("留痕 flag_unknown", any(r.get("action") == "flag_unknown" for r in log),
          [r.get("action") for r in log])


def t_public_safe():
    print("\n[G10] 全部模式的公開文字不含檔名／路徑／sha")
    reset("g10", flag="on")
    seed(sh.day_dir(DATE, SANDBOX), tamper=True)
    g = sh.gate(DATE, SANDBOX)
    bad = ["analysis.json", "staging", "handoff.json", "C:", "/", "\\", "status.jsonl"]
    check("block 公開文字不含內部細節", not any(b in g.public for b in bad), g.public)
    reset("g10b", flag="off")
    seed(sh.day_dir(DATE, SANDBOX))
    g2 = sh.gate(DATE, SANDBOX)
    check("disabled 公開文字不含內部細節", not any(b in g2.public for b in bad), g2.public)


def t_wiring():
    print("\n[G11] 07:00 呼叫端接線存在且語法可解析")
    src_path = REPO / "regenerate_report.py"
    src = src_path.read_text(encoding="utf-8")
    try:
        ast.parse(src)
        check("regenerate_report.py AST 可解析", True, "")
    except SyntaxError as e:
        check("regenerate_report.py AST 可解析", False, str(e))
    markers = {
        "呼叫 gate()": "_sh_h.gate(TODAY)",
        "分流 inject": 'if _em_mode == "inject":',
        "非 inject 排除應變頁": "不納入本輪發布",
        "published 紀錄": "_sh_h.mark_published(TODAY)",
        "退出碼傳遞": "elif _hgate is not None and _hgate.rc:",
        "rc 收斂": "sys.exit(_rc_final)",
    }
    for label, m in markers.items():
        check(f"接線標記：{label}", m in src, m)
    check("仍以 legacy 為預設（_em_mode 初始值）",
          '_em_mode = _hgate.mode if _hgate is not None else "legacy"' in src, "")


def t00_repo_untouched(before):
    print("\n[T00] 正式 repo 零寫入")
    after = repo_status()
    check("git status 前後一致", before == after, "diff" if before != after else "identical")


def t_morning_rc_split():
    print("\n[G12] morning_deploy：12/13 不得報成「產線失敗」，退出碼仍保留")
    import contextlib
    import importlib
    import io
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    md = importlib.import_module("morning_deploy")
    text = (
        "📰 日報:      https://example.test/daily_report_v2_2026-10-20.html\n"
        "📈 差異分析:  https://example.test/asset_diff_2026-10-20.html\n"
        "🏠 儀表板:    https://example.test/\n"
        "❌ 應變段驗證失敗 H06\n"
    )

    def run(rc):
        _orig_read, _orig_log = md.read_stdout, md.write_full_log
        md.read_stdout = lambda: (text, rc)
        md.write_full_log = lambda t: None          # 不寫 repo/logs
        buf, code = io.StringIO(), None
        try:
            with contextlib.redirect_stdout(buf):
                md.main()
        except SystemExit as e:
            code = e.code
        finally:
            md.read_stdout, md.write_full_log = _orig_read, _orig_log
        return buf.getvalue(), code

    out12, code12 = run(12)
    check("rc=12 文案為「已上線」而非「產線失敗」",
          ("已上線" in out12) and ("產線失敗" not in out12), out12.splitlines()[0] if out12 else "")
    check("rc=12 退出碼保留 12", code12 == 12, code12)
    check("rc=12 仍附上線連結", "daily_report_v2_2026-10-20.html" in out12, "")

    out13, code13 = run(13)
    check("rc=13 文案為「已上線」", ("已上線" in out13) and ("產線失敗" not in out13),
          out13.splitlines()[0] if out13 else "")
    check("rc=13 退出碼保留 13", code13 == 13, code13)

    out1, code1 = run(1)
    check("rc=1 仍為「產線失敗」（未放寬真失敗）",
          "產線失敗" in out1 and code1 == 1, (out1.splitlines()[0] if out1 else "", code1))

    out0, code0 = run(0)
    check("rc=0 正常成功文案", ("已產出並上線" in out0) and code0 is None,
          (out0.splitlines()[0] if out0 else "", code0))


def main():
    print("沙箱：%s" % SANDBOX)
    print("模組：%s" % sh.__file__)
    before = repo_status()
    for fn in (t_legacy_no_dir, t_legacy_explicit_off, t_disabled_with_data, t_inject, t_block,
               t_dryrun_ok, t_dryrun_fail, t_unknown_flag, t_public_safe, t_wiring,
               t_morning_rc_split):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            check(fn.__name__ + " 例外", False, repr(e)[:200])
    os.environ.pop("LJ_EMERGENCY_HANDOFF", None)
    t00_repo_untouched(before)
    ok = sum(1 for _, b, _ in RESULTS if b)
    bad = [r for r in RESULTS if not r[1]]
    print("\n================ 合計 %d PASS / %d FAIL ================" % (ok, len(RESULTS) - ok))
    for n, _, d in bad:
        print("  ✗ " + n + "｜" + str(d))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
