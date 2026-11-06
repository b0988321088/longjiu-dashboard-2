"""tools/test_date_wiring.py — 接線驗收（INC-20261106-01 第二／三階段）

**刻意不 import run_daily / regenerate_report**：
2026-10-13 曾因 import regenerate_report 誤觸正式產線（TD-20261013-13）。
故本檔一律用「靜態原始碼檢查 + 純函式呼叫」驗證接線。

執行：python tools/test_date_wiring.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import date_integrity as di  # noqa: E402

RESULTS = []


def check(case_id, desc, ok, detail=""):
    RESULTS.append((case_id, desc, bool(ok)))
    print(f"{'✅' if ok else '❌'} {case_id} {desc}" + (f" — {detail}" if detail else ""))


def read(p):
    return (BASE / p).read_text(encoding="utf-8", errors="replace")


def main():
    # ── W1：regenerate_report 已接入仲裁器 ────────────────────────
    reg = read("regenerate_report.py")
    check("W1", "regenerate_report 匯入 pipeline_gate", "from date_integrity import pipeline_gate" in reg)

    # ── W2：發布條件含 _date_ok ─────────────────────────────────
    check("W2", "發布條件改為 ok and _cio_ok and _date_ok",
          "elif ok and _cio_ok and _date_ok:" in reg)

    # ── W3：--no-push 語義未受影響（NO_PUSH 分支仍在 elif 之前）──
    i_np = reg.find("if _NO_PUSH:")
    i_elif = reg.find("elif ok and _cio_ok and _date_ok:")
    check("W3", "--no-push 分支順序未被改變（仍先於發布分支）", 0 <= i_np < i_elif,
          f"NO_PUSH@{i_np} < elif@{i_elif}")

    # ── W4：仲裁器故障 → fail-closed ────────────────────────────
    check("W4", "仲裁器例外時 _date_ok=False（fail-closed）",
          "_date_ok = False" in reg and "[DATE-GATE][ERROR]" in reg)

    # ── W5：run_daily 已接入（只算狀態，不阻斷既有產物）──────────
    rd = read("run_daily.py")
    check("W5", "run_daily 已呼叫 pipeline_gate", "pipeline_gate(BASE)" in rd and "tv['dis_status']" in rd)

    # ── W6：同型 wrapper 已無 commit / auto_push（B 案）──────────
    for f in ("wrappers/cost_watch_digest.py", "wrappers/cost_watch_close.py"):
        src = read(f)
        has_commit_call = bool(re.search(r'_git\(\s*"commit"', src))
        has_push_call = "auto_push.py" in src and "--script" in src
        check(f"W6-{Path(f).stem}", f"{Path(f).name} 不再 commit／不呼叫 auto_push",
              not has_commit_call and not has_push_call,
              f"commit={has_commit_call} push={has_push_call}")

    # ── W7：cost_watch_eod 僅委派、無 git 路徑（第三支同型）──────
    # 注意：docstring 會提到 auto_push，故檢查「呼叫形式」而非字樣
    eod = read("wrappers/cost_watch_eod.py")
    delegates = "cost_watch_digest.py" in eod
    no_git_call = "_git(" not in eod and "git\", \"commit" not in eod
    no_push_call = 'subprocess.run([sys.executable, "auto_push.py"' not in eod
    check("W7", "cost_watch_eod 純委派 digest、無 git／auto_push 呼叫",
          delegates and no_git_call and no_push_call,
          f"delegate={delegates} git_call={not no_git_call} push_call={not no_push_call}")

    # ── W8：pipeline_gate 對 11/06 現況：落後可發、冒充才停 ───────
    verdict = di.pipeline_gate(BASE)
    _dec = di.publish_decision(verdict, snapshot=json.loads((BASE / "snapshot.json").read_text(encoding="utf-8")))
    disp = BASE / "data" / f"dis_status_{verdict['report_base_date']}.json"
    check("W8", "pipeline_gate 11/06 現況 → 可發布（落後標示、非停發）", _dec["publish"] is True,
          json.dumps(verdict["layers"], ensure_ascii=False))
    check("W8b", "DIS 狀態檔已落檔且狀態一致", disp.exists() and
          json.loads(disp.read_text(encoding="utf-8"))["status"] == verdict["status"], str(disp.name))

    # ── W9：發布決策傳遞到輸出（可被 log 看見）───────────────────
    lines = di.format_gate_lines(verdict)
    _die_src = read("regenerate_report.py")
    check("W9", "發布決策與阻擋原因會寫入產線日誌",
          "可發布=" in _die_src and "阻擋發布" in _die_src and any("DATE-GATE" in l for l in lines))

    # ── W10：發布阻擋布林模擬（不執行產線）───────────────────────
    def would_publish(ok, cio_ok, date_ok):
        return bool(ok and cio_ok and date_ok)
    check("W10", "ok/CIO 皆過但日期 BLOCKED → 不發布",
          would_publish(True, True, False) is False)
    check("W10b", "三者皆過 → 可發布", would_publish(True, True, True) is True)

    # ── W11：原始 20 項仲裁測試仍應通過（回歸）──────────────────
    import subprocess
    r = subprocess.run([sys.executable, str(BASE / "tools" / "test_date_integrity.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("W11", "原 T1–T13（20 項）回歸仍全綠", r.returncode == 0,
          (r.stdout or "").strip().splitlines()[-2] if r.stdout else "")

    passed = sum(1 for _, _, ok in RESULTS if ok)
    total = len(RESULTS)
    print("\n" + "=" * 52)
    print(f"  接線驗收：{passed}/{total} PASS")
    print("=" * 52)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
