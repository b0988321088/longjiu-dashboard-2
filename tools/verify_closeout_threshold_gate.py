#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/verify_closeout_threshold_gate.py — 驗證「收工閘門＝15 類稽核 ＋ check_thresholds 不變式」

背景（2026-10-04）：closeout_check.py 的 15 類稽核「不含」check_thresholds 的 blocking 不變式
（含「未閉環 pending 卡狀態不得含隱藏關鍵字」）→ 實踩：一張完成卡狀態含「已完成」使
build_dashboard 整卡靜默隱藏數日，收工稽核卻仍報「全部通過」。本驗證器證明新接線**具鑑別力**，
而不是只證明「程式跑得起來」。

要求的四態（＋延伸）：
  S1 正常 pending                → 檢查器 rc=0、step 回傳空清單（PASS）
  S2 pending 含隱藏關鍵字        → 檢查器 rc≠0、step 回傳問題（FAIL）
  S3 檢查器本身異常退出          → step 回傳問題（fail-closed）
  S4 非 blocking 的資訊性輸出    → step 不阻塞（rc=0 → 空清單）
  S5 檢查器不存在                → step 回傳問題（fail-closed）
  S6 MUTATION：拿掉那條不變式後，同一個 S2 夾具必須「不再 FAIL」
     → 證明 S2 的 FAIL 確實由該不變式造成（非空洞通過／不是被別的錯誤順便擋下）
  S7 無遞迴：check_thresholds 不得反向引用 closeout_check
  S8 無副作用：跑 step 前後 snapshot／pending／index.html 位元不變
  S9 反恆真：本檔與被驗程式不得出現恆真斷言字面
  S10 wiring：closeout_check 確實呼叫並把結果併入 problems

用法：python tools/verify_closeout_threshold_gate.py      # 全 PASS → exit 0
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

_RESULTS: list[tuple[str, bool, str]] = []


def chk(name: str, ok: bool, detail: str = "") -> None:
    _RESULTS.append((name, bool(ok), detail))
    print(("✅ " if ok else "❌ ") + name + (f"｜{detail}" if detail else ""))


def _load_closeout():
    """以檔案路徑載入受測模組（不經 package 匯入，避免汙染）。"""
    spec = importlib.util.spec_from_file_location("_lj_closeout_under_test", BASE / "closeout_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_checker(checker: Path) -> subprocess.CompletedProcess:
    """以 checker 所在目錄為 BASE 執行（check_thresholds 的 BASE 取自 __file__ 的 parent）。"""
    return subprocess.run([sys.executable, str(checker), "--sot-only"],
                          cwd=str(checker.parent), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)


def make_sandbox(pending_text: str) -> Path:
    """建立可獨立執行的沙盒：根目錄 *.py ＋ snapshot.json ＋ 指定內容的 pending_decisions.json。"""
    d = Path(tempfile.mkdtemp(prefix="lj_thr_sbx_"))
    for p in BASE.glob("*.py"):
        shutil.copy2(p, d / p.name)
    shutil.copy2(BASE / "snapshot.json", d / "snapshot.json")
    (d / "pending_decisions.json").write_text(pending_text, encoding="utf-8")
    return d


def inject_hidden(text: str) -> str:
    """在 pending 夾具裡注入一張「狀態含隱藏關鍵字」的卡（模擬實踩的那張完成卡）。"""
    items = json.loads(text)
    items.append({
        "id": "SBX-HIDDEN-1",
        "date": "2026-10-04",
        "title": "沙盒夾具：狀態含隱藏關鍵字的完成卡",
        "desc": "測試用夾具，不得寫回真值檔。",
        "priority": "P9",
        "status": "已完成",
        "source": "sandbox",
    })
    return json.dumps(items, ensure_ascii=False, indent=2) + "\n"


def strip_pending_visibility_invariant(src: str) -> str:
    """MUTATION：把 pending 隱藏關鍵字那一段整體拿掉（回傳改後原始碼；找不到則回空字串）。"""
    lines = src.splitlines(keepends=True)
    start = None
    for i, ln in enumerate(lines):
        if "未閉環 pending 卡狀態不得含" in ln:
            start = i
            break
    if start is None:
        return ""
    end = None
    for j in range(start, len(lines)):
        if lines[j].strip() == "break":
            end = j
            break
    if end is None:
        return ""
    del lines[start:end + 1]
    return "".join(lines)


def main() -> int:
    co = _load_closeout()
    real_checker = BASE / "check_thresholds.py"
    if not real_checker.exists():
        chk("前置：check_thresholds.py 存在", False, str(real_checker))
        return 1

    real_pending_text = (BASE / "pending_decisions.json").read_text(encoding="utf-8")

    # ── S1 正常 pending → 檢查器 rc=0、step 無問題 ────────────────────────────
    p1 = run_checker(real_checker)
    got1 = co.step_threshold_invariants(True)
    chk("S1 正常 pending → 檢查器 rc=0 且 step 回傳空清單",
        p1.returncode == 0 and got1 == [],
        f"rc={p1.returncode}；step problems={len(got1)}")

    # ── S2 pending 含隱藏關鍵字 → 檢查器 rc≠0、step 回傳問題 ──────────────────
    hidden_text = inject_hidden(real_pending_text)
    sbx_hidden = make_sandbox(hidden_text)
    p2 = run_checker(sbx_hidden)
    got2 = co.step_threshold_invariants(True, checker=sbx_hidden / "check_thresholds.py")
    _msg2 = " ".join(got2)
    stays_hidden = ("hidden" in _msg2.lower()) or ("pending" in _msg2.lower()) or ("隱藏" in _msg2)
    chk("S2 pending 含隱藏關鍵字 → 檢查器 rc≠0 且 step 回傳問題",
        p2.returncode != 0 and len(got2) >= 1 and stays_hidden,
        f"rc={p2.returncode}；step problems={len(got2)}")
    chk("S2b 失敗訊息保留原始 stdout（不只是「檢查失敗」四個字）",
        "❌" in _msg2 and "pending" in _msg2,
        _msg2[:110])

    # ── S3 檢查器異常退出 → fail-closed ──────────────────────────────────────
    d_stub = Path(tempfile.mkdtemp(prefix="lj_thr_stub_"))
    (d_stub / "stub_crash.py").write_text(
        "import sys\n"
        "print('stub: 模擬檢查器內部錯誤')\n"
        "sys.exit(3)\n", encoding="utf-8")
    got3 = co.step_threshold_invariants(True, checker=d_stub / "stub_crash.py")
    chk("S3 檢查器異常退出（rc=3）→ step 回傳問題（fail-closed）",
        len(got3) >= 1 and "rc=3" in " ".join(got3),
        " ".join(got3)[:110])

    # ── S4 資訊性輸出（rc=0）→ 不阻塞 ────────────────────────────────────────
    (d_stub / "stub_info.py").write_text(
        "print('✅ 資訊性輸出 A')\n"
        "print('⏭️  日報檔不存在 → 未驗渲染行')\n"
        "print('⚠️ 找不到基金部位行（格式變了？未驗）')\n"
        "raise SystemExit(0)\n", encoding="utf-8")
    got4 = co.step_threshold_invariants(True, checker=d_stub / "stub_info.py")
    chk("S4 非 blocking 的資訊性輸出 → step 不阻塞",
        got4 == [], f"problems={len(got4)}")

    # ── S5 檢查器不存在 → fail-closed ───────────────────────────────────────
    got5 = co.step_threshold_invariants(True, checker=d_stub / "no_such_checker.py")
    chk("S5 檢查器不存在 → step 回傳問題（fail-closed）",
        len(got5) >= 1 and "不存在" in " ".join(got5),
        " ".join(got5)[:110])

    # ── S6 MUTATION：拿掉不變式後，同一夾具必須不再 FAIL ──────────────────────
    sbx_mut = make_sandbox(hidden_text)          # 同一個夾具（只差不變式）
    src = (sbx_mut / "check_thresholds.py").read_text(encoding="utf-8")
    mutated = strip_pending_visibility_invariant(src)
    ok_mutate = bool(mutated) and ("_closed_kw" not in mutated)
    if ok_mutate:
        (sbx_mut / "check_thresholds.py").write_text(mutated, encoding="utf-8")
    p6 = run_checker(sbx_mut / "check_thresholds.py") if ok_mutate else None
    got6 = co.step_threshold_invariants(True, checker=sbx_mut / "check_thresholds.py") if ok_mutate else ["(mutant 未建立)"]
    chk("S6 MUTATION 拿掉該不變式 → 同一夾具不再 FAIL（證明 S2 非空洞）",
        ok_mutate and p6 is not None and p6.returncode == 0 and got6 == [],
        f"mutant 建立={ok_mutate}；rc={(p6.returncode if p6 else 'n/a')}；step problems={len(got6)}")

    # ── S7 無遞迴：checker 不得反向引用 closeout ─────────────────────────────
    ct_src = real_checker.read_text(encoding="utf-8", errors="replace")
    chk("S7 無遞迴（check_thresholds 不引用 closeout_check）",
        "closeout_check" not in ct_src, "反向依賴=0")

    # ── S8 無副作用：真值檔位元不變 ─────────────────────────────────────────
    watch = [BASE / "snapshot.json", BASE / "pending_decisions.json", BASE / "index.html"]
    before = {str(p): _sha(p) for p in watch if p.exists()}
    co.step_threshold_invariants(True)
    after = {str(p): _sha(p) for p in watch if p.exists()}
    chk("S8 無副作用（snapshot／pending／index.html 位元不變）",
        before == after, f"監看 {len(before)} 檔")

    # ── S9 反恆真：本檔與被驗程式不得出現恆真斷言字面 ────────────────────────
    banned = ["or" + " True", "assert" + " True", "or" + " 1"]
    self_src = Path(__file__).read_text(encoding="utf-8")
    co_src = (BASE / "closeout_check.py").read_text(encoding="utf-8", errors="replace")
    hits = [t for t in banned if t in self_src or t in co_src]
    chk("S9 反恆真（本檔＋closeout_check 無恆真斷言字面）",
        not hits, f"命中={hits}" if hits else "clean")

    # ── S10 wiring：呼叫與併入 problems ─────────────────────────────────────
    wired_call = "thr_problems = step_threshold_invariants(" in co_src
    wired_ext = "problems.extend(thr_problems)" in co_src
    chk("S10 wiring（呼叫 step_threshold_invariants 並併入 problems）",
        wired_call and wired_ext, f"call={wired_call} extend={wired_ext}")

    # ── S11 端到端穿透：真正跑 main()，依賴失效必須讓 rc≠0 ────────────────────
    # 只換掉「依賴」（THRESHOLD_CHECKER → 會崩的 stub），其餘走真實 main() 與真實鏈路。
    _argv_backup = sys.argv[:]
    _checker_backup = co.THRESHOLD_CHECKER
    try:
        sys.argv = ["closeout_check.py"]
        co.THRESHOLD_CHECKER = d_stub / "stub_crash.py"
        import contextlib as _cl
        import io as _io
        _buf = _io.StringIO()
        with _cl.redirect_stdout(_buf):
            rc_main = co.main()
        _txt = _buf.getvalue()
        _in_summary = "門檻不變式檢查 FAIL" in _txt.rsplit("收工檢查", 1)[-1]
    finally:
        co.THRESHOLD_CHECKER = _checker_backup
        sys.argv = _argv_backup
    chk("S11 端到端：依賴失效 → main() rc≠0 且問題列在收工摘要",
        rc_main != 0 and _in_summary,
        f"main rc={rc_main}；摘要含該問題={_in_summary}")

    # ── 清理沙盒 ────────────────────────────────────────────────────────────
    for d in (sbx_hidden, sbx_mut, d_stub):
        shutil.rmtree(d, ignore_errors=True)

    n_pass = sum(1 for _, ok, _ in _RESULTS if ok)
    n_fail = len(_RESULTS) - n_pass
    print("=" * 58)
    print(f"收工閘門驗證｜合計 {len(_RESULTS)} 項｜PASS {n_pass}｜FAIL {n_fail}")
    print("=" * 58)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
