#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_review_chain_packaging_20261016.py — 送審分段包裝的假截斷修復（2026-10-16 使用者裁決）

背景（實測 2026-10-16 07:00 產線全停）：
    d28b889d（晨間四源同步）patch 共 640,240 字元，舊版以 12,000 字元**純字元切片**成 54 段。
    切片不認檔案邊界，於是把 cost.html 的 `<script id="seed">` JSON（合法、5,263 字元）切半
    → 審查者看到半截 JSON，判「truncated and malformed」→ REJECT → 不落 RECORD → 不推送 → rc=1。

修復（review_chain 送審包裝層）：
    ① 分段改以**檔案邊界**優先（`split_patch`），禁止切穿檔案；單檔超限才續切，且標示第 j/m 段。
    ② 單段目標上限 12,000 → 32,000 字元；覆蓋率仍 100%（不改成摘要審查、不降覆蓋）。
    ③ 僅**技術性失敗**（全層不可用／無有效結果）每段最多重試 2 次；有效 REJECT 不重試、不換層。
    ④ 段級完整性：任一段無可解析的有效結果 → 列入 blocking（缺段／漏審不得視為通過）。

測項（全部離線，除註明者不打模型）：
    P1 跨檔案：段界只落在檔案之間，不切穿任何檔案（合成 patch）
    P2 大型單檔：只有超限的那一檔被續切；每段 ≤ cap；join == 原檔；prompt 標示第 j/m 段與⑥條款
    P3 JSON 完整性：檔案 ≤ cap 時，其超長單行 JSON 必須完整落在同一段（合成＋真實 d28b889d cost.html）
    P4 覆蓋率與守門：pct 恆 100%；負向（99%）仍直接 REJECT（守門未放寬）
    P5 重試行為：技術性失敗重試 ≤2 次；用盡即 fail-closed；有效 REJECT 不重試；無效結果不得通過
    P6 真實回歸：d28b889d 的段界、段數、覆蓋率、切點性質（有 commit 才跑）

跑法：python -X utf8 tools/test_review_chain_packaging_20261016.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import review_chain as _rc          # noqa: E402

PASS = FAIL = 0
_BLK = re.compile(r"(?m)^(?=diff --git )")
_REAL = "d28b889d1229fae4ef7233bdda318cd5bec30092"


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")


def _blk(name: str, body: str) -> str:
    return (f"diff --git a/{name} b/{name}\n--- a/{name}\n+++ b/{name}\n"
            f"@@ -1 +1 @@\n{body}\n")


def _line_at(text: str, pos: int) -> str:
    """回傳 pos 所落的整行（用於判斷切點是否落在行中間）。"""
    s = text.rfind("\n", 0, pos) + 1
    e = text.find("\n", pos)
    return text[s:e if e != -1 else len(text)]


def _boundary_aligned(patch: str, seg: str) -> bool:
    """段界是否落在檔案邊界（段首／段尾都必須是 `diff --git` 的起點或字串端點）。"""
    i = patch.find(seg)
    if i < 0:
        return False
    head_ok = i == 0 or patch.startswith("diff --git ", i)
    tail_ok = (i + len(seg) == len(patch)) or patch.startswith("diff --git ", i + len(seg))
    return head_ok and tail_ok


def _real_patch(sha: str) -> str | None:
    r = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=str(BASE),
                       capture_output=True)
    if r.returncode != 0:
        return None
    return subprocess.run(["git", "show", "--format=", sha], cwd=str(BASE), capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


def _valid_text(verdict: str = "APPROVE", pair=("a" * 12, "b" * 12)) -> str:
    return json.dumps({"verdict": verdict, "reviewed_commits": [{"commit": pair[0], "tree": pair[1]}],
                       "blocking": ([] if verdict == "APPROVE" else ["cost.html: 數值矛盾"]),
                       "required_fixes": [], "note": "stub"}, ensure_ascii=False)


def main() -> int:  # noqa: C901
    cap = _rc.DEFAULT_DIFF_CAP
    print(f"=== review_chain 送審分段包裝修復（DEFAULT_DIFF_CAP={cap}） ===")
    check("P0 前提：預設上限已是 32,000（裁決②）", cap == 32000, f"cap={cap}")
    check("P0b 前提：技術性重試預設 2 次（裁決③）", _rc._RETRY_TECHNICAL == 2,
          f"retry={_rc._RETRY_TECHNICAL}")

    # ── P1 跨檔案不切穿 ────────────────────────────────────────────────
    blocks = [_blk(f"f{i}.py", "+" + "a" * 9000) for i in range(4)]      # 4 檔 × ~9.1KB > 32KB
    patch = "".join(blocks)
    segs = _rc.split_patch(patch, cap)
    check("P1a 覆蓋率：join(段) == patch 且為完整分段",
          "".join(s["text"] for s in segs) == patch and len(segs) > 1, f"段數={len(segs)}")
    check("P1b 段界只落在檔案之間（不切穿檔案）",
          all(s["split"] == {} and _boundary_aligned(patch, s["text"]) for s in segs),
          f"段界={[len(s['text']) for s in segs]}")
    check("P1c 每段皆 ≤ cap", all(len(s["text"]) <= cap for s in segs))
    check("P1d 段內檔案清單與實際 diff 標頭一致",
          all(set(s["files"]) == {m.group(1) for m in
                                  re.finditer(r"(?m)^diff --git a/(\S+)", s["text"])}
              for s in segs))

    # ── P2 大型單檔（只有它被續切）────────────────────────────────────
    big = _blk("daily_report_v2_2026-10-16.html",
               "".join(f"+line{j}\n" for j in range(12000)))            # > cap
    p2 = _blk("small.py", "+x\n") + big + _blk("tail.py", "+y\n")
    segs2 = _rc.split_patch(p2, cap)
    split_segs = [s for s in segs2 if s["split"]]
    check("P2a 只有超限的那一檔被標為續切（其他檔完整）",
          {f for s in split_segs for f in s["split"]} == {"daily_report_v2_2026-10-16.html"},
          str([s["split"] for s in split_segs]))
    check("P2b 續切段數 = 標示的 m，且每段 ≤ cap",
          len(split_segs) == split_segs[0]["split"]["daily_report_v2_2026-10-16.html"][1]
          == max(j for s in split_segs for _, (j, _m) in s["split"].items())
          and all(len(s["text"]) <= cap for s in split_segs),
          f"n={len(split_segs)}")
    check("P2c 續切片段還原後等於原檔區塊（無遺漏、無重複）",
          "".join(s["text"] for s in split_segs) == big)
    check("P2d 合成 patch 整體覆蓋 100%", "".join(s["text"] for s in segs2) == p2)
    # 行邊界：除「單行本身超限」外，切點必須落在換行處
    pos, ok_line = 0, True
    for s in segs2[:-1]:
        pos += len(s["text"])
        if p2[pos - 1] != "\n":                       # 切在行中間
            ok_line = ok_line and len(_line_at(p2, pos)) > cap   # 僅允許「單行超限」造成
    check("P2e 切點落在行邊界（唯一例外：單行本身超限）", ok_line)

    prompts2, cov2 = _rc.build_review_prompts("c" * 40, "d" * 40, "s", "f", "stat", cap, patch=p2)
    check("P2f 段數與 coverage 一致", len(prompts2) == int(cov2.get("segments", -1)) == len(segs2),
          f"prompts={len(prompts2)} cov={cov2.get('segments')} segs={len(segs2)}")
    _sp = [p for p in prompts2 if "本段為該檔第" in p]
    check("P2g 續切段的 prompt 明示「本檔第 j/m 段」與上下文限制",
          len(_sp) == len(split_segs) and all("刻意分段，不是資料截斷" in p for p in _sp),
          f"n={len(_sp)}")
    check("P2h 續切段的 prompt 含「⑥分段切點不是缺陷」判準",
          all("⑥**分段切點不是缺陷**" in p for p in _sp))
    check("P2i 段界落在檔案之間的段，prompt 仍明示該性質（不誤導為截斷）",
          all("段界落在檔案之間" in p for p in prompts2 if "本段為該檔第" not in p))

    # ── P3 JSON 完整性 ───────────────────────────────────────────────
    js = json.dumps({"generated_at": "2026-10-16 07:00", "series": [{"d": i} for i in range(400)]},
                    ensure_ascii=False)
    cost = _blk("cost.html", f'+<script type="application/json" id="seed">{js}</script>\n')
    p3 = _blk("a.py", "+a\n") + cost + _blk("b.py", "+b\n")
    segs3 = _rc.split_patch(p3, cap)
    holder = [s["text"] for s in segs3 if 'id="seed"' in s["text"]]
    got = re.search(r'<script type="application/json" id="seed">(.*?)</script>',
                    holder[0] if holder else "", re.S)
    check("P3a 合成：檔內超長 JSON 完整落在同一段（未被切半）",
          len(holder) == 1 and got is not None and json.loads(got.group(1)) == json.loads(js),
          f"holder={len(holder)}")

    real = _real_patch(_REAL)
    if real:
        segsr = _rc.split_patch(real, cap)
        cost_segs = [s for s in segsr if "cost.html" in s["files"]]
        _m = re.search(r'<script type="application/json" id="seed">(.*?)</script>',
                       cost_segs[0]["text"] if cost_segs else "", re.S)
        check("P3b 真實 d28b889d：cost.html 完整落在同一段（舊版被切半＝本次事故根因）",
              len(cost_segs) == 1 and cost_segs[0]["split"] == {} and _m is not None
              and isinstance(json.loads(_m.group(1)), dict),
              f"cost 段數={len(cost_segs)}")
        check("P3c 真實 d28b889d：seed JSON 可解析且非空（＝內容本就合法，舊判為假 REJECT）",
              _m is not None and len(json.loads(_m.group(1)).get("series") or []) > 0)
    else:
        check(f"P3b 真實 {_REAL[:12]} 存在於本機（可驗真）", False, "找不到 commit")

    # ── P4 覆蓋率守門未放寬 ─────────────────────────────────────────
    _txt, _lab, _meta = _rc.review_segmented(["x"], {"total_chars": 32043, "provided_chars": 32000,
                                                     "pct": 99.9, "segments": 1})
    _j = json.loads(_txt)
    check("P4a 負向：涵蓋率 <100% → 直接 REJECT（coverage guard，未放寬、不打模型）",
          _lab == "coverage-guard" and _j.get("verdict") == "REJECT" and _meta.get("segments") == 0)
    _t2, _l2, _m2 = _rc.review_segmented([], {"total_chars": 0, "provided_chars": 0, "pct": 100.0,
                                             "segments": 0})
    check("P4b 負向：無任何送審段（缺段／漏審）→ REJECT，不得通過",
          _l2 == "no-segments" and json.loads(_t2).get("verdict") == "REJECT")
    check("P4c coverage 回報檔案邊界分段資訊（可稽核）",
          "file_aligned" in cov2 and "split_files" in cov2 and cov2.get("pct") == 100.0,
          json.dumps(cov2.get("split_files", {}), ensure_ascii=False)[:120])

    # ── P5 重試行為（打樁 review，不打真模型）────────────────────────
    orig_review, orig_backoff = _rc.review, _rc._RETRY_BACKOFF
    _rc._RETRY_BACKOFF = 0                     # 測試不睡
    _cov1 = {"total_chars": 10, "provided_chars": 10, "pct": 100.0, "segments": 1}
    pair = ("a" * 12, "b" * 12)
    try:
        calls = {"n": 0}

        def _flaky(prompt, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("CIO-Pollinations(openai): HTTP 402")
            return _valid_text("APPROVE", pair), "CIO-stub"

        _rc.review = _flaky
        _t, _l, _m = _rc.review_segmented(["p"], _cov1, expect_pair=pair)
        check("P5a 技術性失敗（402）→ 重試後成功：通過且記錄重試次數",
              json.loads(_t)["verdict"] == "APPROVE" and _m.get("retried") == ["seg1:2"]
              and calls["n"] == 2, f"calls={calls['n']} meta={_m.get('retried')}")

        calls["n"] = 0

        def _dead(prompt, **k):
            calls["n"] += 1
            raise RuntimeError("審查鏈全數失敗 → fail-closed")

        _rc.review = _dead
        _raised = ""
        try:
            _rc.review_segmented(["p"], _cov1, expect_pair=pair)
        except RuntimeError as e:
            _raised = str(e)
        check("P5b 技術性失敗重試用盡 → 丟例外（fail-closed，不得視為通過）",
              "重試 2 次後仍失敗" in _raised, _raised[:120])
        check("P5c 重試次數上限：1 次首呼 + 2 次重試 = 3", calls["n"] == 3, f"calls={calls['n']}")

        calls["n"] = 0

        def _reject(prompt, **k):
            calls["n"] += 1
            return _valid_text("REJECT", pair), "CIO-stub"

        _rc.review = _reject
        _t, _l, _m = _rc.review_segmented(["p"], _cov1, expect_pair=pair)
        _j = json.loads(_t)
        check("P5d 有效 REJECT → **不重試**（1 次呼叫）、整體 REJECT、blocking 保留",
              calls["n"] == 1 and _j["verdict"] == "REJECT" and _j["blocking"]
              and _m.get("retried") == [], f"calls={calls['n']} retried={_m.get('retried')}")

        calls["n"] = 0

        def _invalid(prompt, **k):
            calls["n"] += 1
            return json.dumps({"verdict": "MAYBE", "reviewed_commits": [], "blocking": []}), "CIO-stub"

        _rc.review = _invalid
        _t, _l, _m = _rc.review_segmented(["p"], _cov1, expect_pair=pair)
        _j = json.loads(_t)
        check("P5e 段級無效結果（verdict 不可判定）→ 列入 blocking，不得通過",
              _j["verdict"] == "REJECT" and any("無效審查結果" in str(b) for b in _j["blocking"])
              and _m.get("invalid_segments"), f"invalid={_m.get('invalid_segments')}")

        calls["n"] = 0

        def _badpair(prompt, **k):
            calls["n"] += 1
            return _valid_text("APPROVE", ("f" * 12, "e" * 12)), "CIO-stub"

        _rc.review = _badpair
        _t, _l, _m = _rc.review_segmented(["p"], _cov1, expect_pair=pair)
        check("P5f 綁定不符 → 整體 REJECT（不得以未綁定的審查放行）",
              json.loads(_t)["verdict"] == "REJECT" and _m.get("binding_bad"))
    finally:
        _rc.review, _rc._RETRY_BACKOFF = orig_review, orig_backoff

    # ── P6 真實回歸（不打模型）──────────────────────────────────────
    if real:
        segsr = _rc.split_patch(real, cap)
        promptsr, covr = _rc.build_review_prompts(_REAL[:12], "e" * 40, "四源同步 2026-10-16",
                                                  "f", "stat", cap, patch=real)
        check(f"P6a 真實 {_REAL[:12]}：覆蓋率 100%、provided==total",
              covr.get("pct") == 100.0 and covr.get("provided_chars") == covr.get("total_chars") == len(real),
              json.dumps(covr, ensure_ascii=False)[:160])
        check("P6b 真實：段數遠低於舊版 54 段（裁決②的實效）",
              len(segsr) < 54, f"段數={len(segsr)}")
        check("P6c 真實：每個非續切段的段界都在檔案邊界（不切穿檔案）",
              all(_boundary_aligned(real, s["text"]) for s in segsr if not s["split"]),
              str([len(s["text"]) for s in segsr if not s["split"]]))
        check("P6d 真實：每段 ≤ cap", all(len(s["text"]) <= cap for s in segsr),
              f"max={max(len(s['text']) for s in segsr)}")
        check("P6e 真實：prompt 數 == 段數 == coverage.segments",
              len(promptsr) == len(segsr) == int(covr.get("segments", -1)))
        check("P6f 真實：被續切的檔僅限「本身 > cap」者",
              all(any(len(b) > cap for b in _BLK.split(real) if b.startswith(f"diff --git a/{f} "))
                  for s in segsr for f in s["split"]),
              str(sorted({f for s in segsr for f in s["split"]})))
    else:
        check(f"P6 真實 {_REAL[:12]} 存在於本機（可驗真）", False, "找不到 commit")

    print(f"\n測試結果：{PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
