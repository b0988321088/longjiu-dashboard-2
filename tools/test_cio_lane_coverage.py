#!/usr/bin/env python3
"""cio_lane 送審覆蓋率基建修復的測試（2026-10-15 建立）

背景（實測 0da98b37）：cio_lane 自己做字元切片後，把「本段所屬檔案」脈絡串進
`build_review_prompt(..., patch=...)` 的 patch 參數 → 該段長度 = DIFF_CAP + 脈絡長度
（12000 + 43 = 12043）→ build_review_prompt 內 `patch[:diff_cap]` **二次截斷** →
`_coverage_note` 明示「涵蓋率 99.6%」→ 當日 B1／R1 守門（涵蓋率 <100% 不得 APPROVE）
必然 REJECT（審查者自述「內容本身未見可指名之阻塞缺陷」）。修法＝分段與 prompt 走
review_chain 單一真值，脈絡改加在 prompt 開頭（diff fence 之外）。

測項（離線，不呼叫模型）：
  U1 分段覆蓋：切片無遺漏／無重複，段數與 prompt 數一致，coverage = 100%
  U2 無二次截斷：每個 prompt 的 diff fence 內容 ≤ cap，且不得出現「diff 未完整」警告
  U3 負向：模擬舊行為（脈絡串進 patch）→ 必須仍出現截斷警告（守門未被削弱）
  U4 負向：涵蓋率 <100% → review_segmented 直接 REJECT（coverage guard，不呼叫模型）
  U5 真實 commit：對 0da98b37 的實際 patch 驗證 100% 覆蓋（長檔 daily_report_v2 含在內）
  U6 邊界：單段（≤cap）情形不誤報截斷

跑法：python tools/test_cio_lane_coverage.py（全過 exit 0）
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import review_chain as _rc          # noqa: E402
import cio_lane as _lc              # noqa: E402

PASS = FAIL = 0
_DIFF_BLOCK = re.compile(r"```diff\n(.*?)\n```", re.S)
_WARN = "diff 未完整"


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")


def _fake_patch(n_files: int = 4, body: int = 9000) -> str:
    out = []
    for i in range(n_files):
        out.append(f"diff --git a/file_{i}.py b/file_{i}.py\n--- a/file_{i}.py\n"
                   f"+++ b/file_{i}.py\n@@ -1 +1 @@\n" + ("+x" * 0 + "+" + "a" * body + "\n"))
    return "".join(out)


def main() -> int:
    cap = _lc.DIFF_CAP
    print(f"=== cio_lane 送審覆蓋率基建修復（DIFF_CAP={cap}） ===")
    patch = _fake_patch(4, 9000)
    check("U0 前提：合成 patch 長度 > cap（需觸發分段）", len(patch) > cap, f"len={len(patch)}")

    prompts, cov, segs = _lc.build_segments("a" * 40, "b" * 40, "s", "f.py", "stat", patch)
    check("U1a 切片無遺漏／無重複（join(segs) == patch）", "".join(segs) == patch)
    check("U1b 段數與 prompt 數一致", len(prompts) == len(segs) == int(cov.get("segments", -1)),
          f"prompts={len(prompts)} segs={len(segs)} cov={cov.get('segments')}")
    check("U1c coverage 回報 100%（修復前為 99.6% 級別的假截斷）",
          float(cov.get("pct", 0)) == 100.0 and cov.get("provided_chars") == len(patch),
          json.dumps(cov, ensure_ascii=False))

    _blocks = [_DIFF_BLOCK.search(p) for p in prompts]
    check("U2a 每個 prompt 都含 diff 區塊（脈絡不得吃掉預算而擠掉 diff）",
          all(_blocks), f"{[bool(b) for b in _blocks]}")
    check("U2b 每個 prompt 的 diff 內容 ≤ cap（無二次截斷）",
          all(len(b.group(1)) <= cap for b in _blocks if b),
          f"lens={[len(b.group(1)) for b in _blocks if b]}")
    check("U2c 每個 prompt 皆無『diff 未完整／涵蓋率』警告",
          all(_WARN not in p and "涵蓋率" not in p for p in prompts))
    check("U2d 脈絡加在 prompt 開頭（diff fence 之外）",
          all(p.startswith("# ⓘ 本段所屬檔案：") for p in prompts), prompts[0][:40])

    # U3 負向：重現舊行為（脈絡串進 patch，且總長超過 cap）→ 截斷警告必須仍出現。
    #   2026-10-16（cap 12,000 → 32,000）：舊寫法用 segs[0]（≤cap）已不再觸發截斷，
    #   故此處以「刻意超長」的內容重建同一情境 —— 判準本身不放寬（仍必須出現警告）。
    _old = _rc.build_review_prompt("a" * 40, "b" * 40, "s", "f.py", "stat", cap,
                                  patch="# ⓘ 本段所屬檔案：file_0.py\n" + "z" * (cap + 43),
                                  segment=(1, 2))
    check("U3 負向：脈絡串進 patch 且超長（舊版行為）→ 截斷警告仍必須出現（守門未削弱）",
          _WARN in _old and "涵蓋率 99" in _old,
          _old[-160:])

    # U4 負向：涵蓋率 <100% 直接 REJECT（coverage guard，不呼叫模型 → 離線可跑）
    _txt, _lab, _meta = _rc.review_segmented(["x"], {"total_chars": 12043, "provided_chars": 12000,
                                                     "pct": 99.6, "segments": 1})
    _j = json.loads(_txt)
    check("U4 負向：涵蓋率 99.6% → REJECT 且標記 coverage-guard（不呼叫模型）",
          _lab == "coverage-guard" and _j.get("verdict") == "REJECT" and _meta.get("segments") == 0,
          f"label={_lab} verdict={_j.get('verdict')}")

    # U5 真實 commit（0da98b37）：實際 patch 必須 100% 覆蓋
    _c = "0da98b37"
    _has = subprocess.run(["git", "cat-file", "-e", f"{_c}^{{commit}}"], cwd=str(BASE),
                          capture_output=True).returncode == 0
    if _has:
        _real = subprocess.run(["git", "show", "--format=", _c], cwd=str(BASE),
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace").stdout
        _files = subprocess.run(["git", "show", "--name-only", "--format=", _c], cwd=str(BASE),
                                capture_output=True, text=True, encoding="utf-8").stdout.strip()
        _tree = subprocess.run(["git", "rev-parse", f"{_c}^{{tree}}"], cwd=str(BASE),
                               capture_output=True, text=True).stdout.strip()
        _rp, _rcov, _rsegs = _lc.build_segments(_c, _tree, "s", _files, "stat", _real)
        _rb = [_DIFF_BLOCK.search(p) for p in _rp]
        check(f"U5a 真實 {_c}：涵蓋率 100%、無警告（{len(_rp)} 段）",
              float(_rcov.get("pct", 0)) == 100.0 and all(_WARN not in p for p in _rp),
              json.dumps(_rcov, ensure_ascii=False))
        check(f"U5b 真實 {_c}：每段 diff ≤ cap 且完整落在 prompt 內",
              all(b and len(b.group(1)) <= cap for b in _rb),
              f"lens={[len(b.group(1)) if b else None for b in _rb]}")
        check(f"U5c 真實 {_c}：daily_report_v2 的 diff 有進入審查內容（長檔不得被擠掉）",
              any("daily_report_v2_2026-10-15.html" in p for p in _rp))
    else:
        check(f"U5 真實 commit {_c} 存在於本機（可驗證）", False, "找不到 commit")

    # U6 邊界：單段（≤cap）不誤報
    _small = "diff --git a/x b/x\n@@ -1 +1 @@\n-a\n+b\n"
    _sp, _scov, _ssegs = _lc.build_segments("a" * 40, "b" * 40, "s", "x", "stat", _small)
    check("U6 邊界：單段（≤cap）1 個 prompt、涵蓋率 100%、無警告",
          len(_sp) == 1 and float(_scov.get("pct", 0)) == 100.0 and _WARN not in _sp[0])

    print(f"\n測試結果：{PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
