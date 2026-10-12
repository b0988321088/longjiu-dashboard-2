# -*- coding: utf-8 -*-
"""tests/test_perf_gate_f4.py — TD-20261009-13（P0）：F4 核准查核必須 fail-closed。

驗收條件（TD-20261009-13）：
 ①改為 fail-closed（例外一律視為不可信、拒絕採信）
 ②負向測試涵蓋三類：模擬例外（路徑解析失敗）／讀取失敗／格式錯誤 → 全部必須阻擋
 ③不得藉此放寬其餘既有檢查
驗收條件（本檔加驗）：**repo 內偽造核准檔一律不得放行**（含相對跳脫、大小寫／分隔符變體、
Windows 長路徑前綴等非常規路徑）。
"""
import json
import sys
import tempfile
import unittest.mock as mock
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "tools"))
sys.path.insert(0, str(BASE))
import perf_gate_contract as pgc  # noqa: E402

REPO = pgc.REPO
_ok = _fail = 0
FAILS = []


def ck(name, cond, detail=""):
    global _ok, _fail
    if cond:
        _ok += 1; print(f"  ✅ {name}")
    else:
        _fail += 1; FAILS.append(name); print(f"  ❌ {name} {detail}")


def _approved_tree():
    """取一個確實有 APPROVE 紀錄的 tree（用真實紀錄，不用偽造）。"""
    f = REPO / ".git" / "CIO_APPROVED"
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) >= 5 and parts[3].strip() == "APPROVE":
            return parts[1].strip()      # 核准紀錄以第 2 欄（tree）為鍵
    raise SystemExit("找不到可用 APPROVE tree")


def _row(tree, verdict="APPROVE"):
    return f"2026-10-12T00:00:00Z\t{tree}\t{tree}\t{verdict}\tCIO-FORGED-TEST\t偽造測試列\n"


def _f4(**kw):
    return pgc.f4_publish_consistency(**kw)


def main() -> int:
    tree = _approved_tree()
    print(f"=== F4 fail-closed 負向測試（候選 tree {tree[:12]}）===")

    # ── 類別①：路徑解析失敗（模擬例外）→ 必須阻擋 ──
    print("① 路徑解析失敗（Path.resolve 拋例外）")
    with mock.patch.object(Path, "resolve", side_effect=OSError("simulated resolve failure")):
        out = _f4(candidate_tree=tree, approval_file=str(REPO / ".git" / "CIO_APPROVED"))
    ck("① 例外時 ok=False（不得 fail-open）", out.get("ok") is False, str(out.get("checks"))[:160])
    ck("① 明示 FAIL-CLOSED", any("FAIL-CLOSED" in c["detail"] for c in out["checks"]), str(out["checks"])[:160])

    # ── 類別②：讀取失敗（權限／存取異常）→ 必須阻擋 ──
    print("② 讀取失敗（權限／存取異常）→ 必須明確阻擋（ok=False ＋ FAIL-CLOSED）")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "approval"
        p.write_text(_row(tree), encoding="utf-8")
        _real = Path.read_text
        def _boom(self, *a, **k):                      # 只讓目標核准檔讀取失敗（精準注入）
            if Path(self) == p:
                raise PermissionError("simulated permission denied")
            return _real(self, *a, **k)
        with mock.patch.object(Path, "read_text", _boom):
            out2 = _f4(candidate_tree=tree, approval_file=str(p))
    ck("② 讀取失敗 → ok=False", out2.get("ok") is False, str(out2.get("checks"))[:160])
    ck("② 明示 FAIL-CLOSED（不得當成「無紀錄」帶過）",
       any("FAIL-CLOSED" in c["detail"] for c in out2["checks"]), str(out2["checks"])[:200])
    with tempfile.TemporaryDirectory() as d:
        out2b = _f4(candidate_tree=tree, approval_file=d)   # 指向目錄 → 讀取必然失敗
    ck("② 指向目錄（IsADirectoryError）→ ok=False", out2b.get("ok") is False, str(out2b.get("checks"))[:160])

    # ── 類別③：格式錯誤 → 必須阻擋 ──
    print("③ 格式錯誤（非四欄 tab 格式／內容不可解析）")
    for label, content in (("空白檔", ""), ("任意文字", "not a cio approval file\n"),
                           ("欄位不足", "x\ty\tAPPROVE\n"), ("非 tab 分隔", "a b c d e f\n")):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "approval"; p.write_text(content, encoding="utf-8")
            o = _f4(candidate_tree=tree, approval_file=str(p))
        ck(f"③ {label} → ok=False", o.get("ok") is False, str(o.get("checks"))[:140])

    # ── repo 內偽造核准檔：一律不得放行（含非常規路徑變體） ──
    print("④ repo 內偽造核准檔（含非常規路徑）")
    forged = [("repo 內 .git 偽造檔", REPO / ".git" / "_forged_approval_test"),
              ("repo 根目錄偽造檔", REPO / "_forged_approval_test.txt")]
    for name, fp in forged:
        fp.write_text(_row(tree), encoding="utf-8")     # 偽造「對 candidate tree APPROVE」
        try:
            o = _f4(candidate_tree=tree, approval_file=str(fp))
            ck(f"④ {name} → 拒絕採信", o.get("ok") is False and any("repo 內" in c["detail"] for c in o["checks"]),
               str(o.get("checks"))[:180])
        finally:
            fp.unlink(missing_ok=True)
    variants = {
        "相對跳脫（..）": str(REPO / ".git" / ".." / ".git" / "CIO_APPROVED"),
        "大小寫／正斜線變體": str(REPO).lower().replace("\\", "/") + "/.git/CIO_APPROVED",
        "Windows 長路徑前綴": "\\\\?\\" + str(REPO / ".git" / "CIO_APPROVED"),
        "混合分隔符": str(REPO).replace("\\", "/") + "\\\\.git\\\\CIO_APPROVED",
    }
    for name, v in variants.items():
        try:
            o = _f4(candidate_tree=tree, approval_file=v)
            ck(f"④ {name} → 拒絕採信", o.get("ok") is False, f"ok={o.get('ok')} {(o.get('checks') or [{}])[0].get('detail','')[:120]}")
        except Exception as e:
            ck(f"④ {name} → 拒絕採信", False, f"拋例外 {type(e).__name__}: {e}")

    # ── 正向對照＋③不放寬其餘檢查 ──
    print("⑤ 正向對照（repo 外、格式正確、對 candidate APPROVE）與不放寬")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "approval"; p.write_text(_row(tree), encoding="utf-8")
        o = _f4(candidate_tree=tree, approval_file=str(p), artifacts={}, approved_artifacts={})
        first = o["checks"][0]
        ck("⑤ repo 外正常紀錄 → 通過核准綁定查核", first["ok"] is True, str(first)[:160])
        ck("⑤ 但仍因缺產物清單而阻擋（未放寬其餘檢查）", o.get("ok") is False and
           any("核准產物清單" in c["label"] for c in o["checks"]), str(o["checks"])[-200:])
        o2 = _f4(candidate_tree=tree, approval_file=str(p), approval_tree="0" * 40)
        ck("⑤ 呼叫端宣稱核准 tree ≠ 候選 → 阻擋（不得覆寫）", o2.get("ok") is False, str(o2["checks"])[:160])

    print(f"\n== 結果：{_ok} PASS / {_fail} FAIL ==")
    if FAILS:
        print("FAIL 清單:", FAILS)
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
