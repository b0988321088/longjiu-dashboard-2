#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_review_chain_binding_20261023.py — 綁定契約誤拒（R1–R3）的回歸測試

被驗行為（review_chain.py）：
  T1 漏綁定＋修復一次成功 ：APPROVE，meta.binding_repaired 記錄段號與次數。
  T2 漏綁定＋修復全失敗   ：REJECT，blocking 指名段號並附嘗試次數（fail-closed）。
  T3 只重試失敗的那一段   ：3 段中僅第 2 段漏綁定 → 修復呼叫 1 次、段審查仍 3 次。
  T4 tree 錯一碼          ：不得視為修復成功（逐字比對，不推定）。
  T5 首審 REJECT          ：補抄綁定成功仍 REJECT（修復不得改變判決）。
  T6 全層技術性失敗       ：丟 RuntimeError（呼叫端 fail-closed，不回歸成 APPROVE）。
  T7 無效審查段           ：仍列入 blocking，且不觸發綁定修復（不得被掩蓋）。
  T8 既有邊界回歸         ：coverage<100／無段 → REJECT；test_review_chain_20261013.py 全綠。
  T9 死碼回歸鎖           ：純綁定 JSON 會被 _valid_review 判 False（故修復必須走
                            review_text，不得改回 review）。

全程離線（打樁 review／review_text／_layers），不連外、不動 repo、不產生 API 成本。
執行：python -X utf8 tests/test_review_chain_binding_20261023.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import review_chain as rc  # noqa: E402

PASS = FAIL = 0
PAIR = ("4a41898ec213", "b8f6828e0d8b")
BAD_TREE = ("4a41898ec213", "b8f6828e0d8c")   # 故意錯一碼


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")


def _review_json(verdict: str = "APPROVE", pair=None, blocking=None) -> str:
    d = {"verdict": verdict, "blocking": blocking or [], "required_fixes": [],
         "note": "test"}
    if pair:
        d["reviewed_commits"] = [{"commit": pair[0], "tree": pair[1]}]
    return json.dumps(d, ensure_ascii=False)


def _binding_json(pair) -> str:
    return json.dumps({"reviewed_commits": [{"commit": pair[0], "tree": pair[1]}]},
                      ensure_ascii=False)


class Patch:
    """暫時取代 review_chain 的 review／review_text／_layers，結束後還原。"""

    def __enter__(self):
        self._orig = (rc.review, rc.review_text, rc._layers, rc._RETRY_BACKOFF)
        rc._RETRY_BACKOFF = 0          # 測試不真的等
        return self

    def __exit__(self, *exc):
        rc.review, rc.review_text, rc._layers, rc._RETRY_BACKOFF = self._orig
        return False


def _run_segmented(prompts, *, seg_replies, repair_replies):
    """seg_replies：每段回傳清單（可為 Exception）；repair_replies：修復回傳清單。"""
    calls = {"review": [], "repair": []}
    _seg = list(seg_replies)
    _rep = list(repair_replies)

    def _fake_review(prompt, **kw):
        calls["review"].append(prompt)
        item = _seg.pop(0) if _seg else RuntimeError("no seg reply")
        if isinstance(item, Exception):
            raise item
        return item, "FAKE-REVIEWER"

    def _fake_text(prompt, **kw):
        calls["repair"].append(prompt)
        item = _rep.pop(0) if _rep else RuntimeError("no repair reply")
        if isinstance(item, Exception):
            raise item
        return item, "FAKE-REVIEWER"

    rc.review = _fake_review
    rc.review_text = _fake_text
    rc._layers = lambda: [("FAKE-REVIEWER", lambda *a, **k: "")]
    txt, label, meta = rc.review_segmented(list(prompts), {"pct": 100.0},
                                           expect_pair=PAIR, retry_technical=2)
    return json.loads(txt), meta, calls


def t1() -> None:
    print("\nT1 漏綁定＋修復一次成功")
    with Patch():
        out, meta, calls = _run_segmented(["p1"], seg_replies=[_review_json()],
                                          repair_replies=[_binding_json(PAIR)])
    check("verdict=APPROVE", out["verdict"] == "APPROVE", out["verdict"])
    check("reviewed_commits 含正確綁定",
          {"commit": PAIR[0], "tree": PAIR[1]} in (out.get("reviewed_commits") or []), out)
    check("meta.binding_repaired 記錄 seg1:1", meta.get("binding_repaired") == ["seg1:1"],
          str(meta.get("binding_repaired")))
    check("meta.retried 記錄 binding-repair", "seg1:binding-repair" in meta.get("retried", []),
          str(meta.get("retried")))
    check("修復只呼叫 1 次", len(calls["repair"]) == 1, str(len(calls["repair"])))


def t2() -> None:
    print("\nT2 漏綁定＋修復全失敗（含例外）")
    with Patch():
        out, meta, calls = _run_segmented(
            ["p1"],
            seg_replies=[_review_json()],
            repair_replies=[RuntimeError("chain down"), RuntimeError("chain down"),
                            _binding_json(BAD_TREE)])
    check("verdict=REJECT", out["verdict"] == "REJECT", out["verdict"])
    _bl = " ".join(str(b) for b in out.get("blocking") or [])
    check("blocking 指名段號 1/1", "第 1/1 段未回報綁定" in _bl, _bl[:160])
    check("blocking 附嘗試次數", "綁定修復 3 次" in _bl, _bl[:160])
    check("修復嘗試 3 次（retry_technical=2）", len(calls["repair"]) == 3, str(len(calls["repair"])))
    check("meta.binding_repaired 為空", meta.get("binding_repaired") == [],
          str(meta.get("binding_repaired")))


def t3() -> None:
    print("\nT3 3 段中僅第 2 段漏綁定 → 只重試第 2 段")
    with Patch():
        out, meta, calls = _run_segmented(
            ["p1", "p2", "p3"],
            seg_replies=[_review_json(pair=PAIR), _review_json(), _review_json(pair=PAIR)],
            repair_replies=[_binding_json(PAIR)])
    check("verdict=APPROVE", out["verdict"] == "APPROVE", out["verdict"])
    check("段審查 3 次（已通過段落不重跑）", len(calls["review"]) == 3, str(len(calls["review"])))
    check("綁定修復只 1 次（僅第 2 段）", len(calls["repair"]) == 1, str(len(calls["repair"])))
    check("修復紀錄指向 seg2", meta.get("binding_repaired") == ["seg2:1"],
          str(meta.get("binding_repaired")))


def t4() -> None:
    print("\nT4 tree 錯一碼不得算修復成功")
    with Patch():
        out, meta, _ = _run_segmented(["p1"], seg_replies=[_review_json()],
                                      repair_replies=[_binding_json(BAD_TREE)] * 3)
    check("verdict=REJECT", out["verdict"] == "REJECT", out["verdict"])
    check("未記錄修復成功", meta.get("binding_repaired") == [], str(meta.get("binding_repaired")))
    check("不得回報錯誤綁定",
          {"commit": BAD_TREE[0], "tree": BAD_TREE[1]} not in (out.get("reviewed_commits") or []),
          out.get("reviewed_commits"))


def t5() -> None:
    print("\nT5 首審 REJECT，補抄綁定成功仍 REJECT")
    _block = "daily_report_v2_2026-10-23.html 行 12 數字與 snapshot 不一致"
    with Patch():
        out, meta, _ = _run_segmented(["p1"],
                                      seg_replies=[_review_json("REJECT", blocking=[_block])],
                                      repair_replies=[_binding_json(PAIR)])
    check("verdict 仍為 REJECT（不得因補抄翻成 APPROVE）", out["verdict"] == "REJECT",
          out["verdict"])
    check("首審 blocking 原樣保留", any(_block in str(b) for b in out.get("blocking") or []),
          str(out.get("blocking"))[:160])
    check("綁定確實有補上（修復生效但不改判決）", meta.get("binding_bad") == [],
          str(meta.get("binding_bad")))


def t6() -> None:
    print("\nT6 全層技術性失敗 → RuntimeError")
    with Patch():
        raised = ""
        try:
            _run_segmented(["p1"], seg_replies=[RuntimeError("layer1 down")] * 3,
                           repair_replies=[])
        except RuntimeError as e:
            raised = str(e)
        except Exception as e:  # noqa: BLE001
            raised = f"WRONG:{type(e).__name__}"
    check("丟 RuntimeError（呼叫端 fail-closed）", raised.startswith("第 1/1 段技術性失敗"), raised[:160])


def t7() -> None:
    print("\nT7 無效審查段不得被綁定修復掩蓋")
    with Patch():
        out, meta, calls = _run_segmented(["p1"], seg_replies=['{"foo": 1}'],
                                          repair_replies=[_binding_json(PAIR)])
    check("verdict=REJECT", out["verdict"] == "REJECT", out["verdict"])
    check("blocking 含無效審查", any("無效審查" in str(b) for b in out.get("blocking") or []),
          str(out.get("blocking"))[:160])
    check("無效段不觸發綁定修復", len(calls["repair"]) == 0, str(len(calls["repair"])))


def t8() -> None:
    print("\nT8 既有邊界回歸")
    _txt, _lbl, meta = rc.review_segmented(["p"], {"pct": 99.9}, expect_pair=PAIR)
    check("coverage<100 → REJECT", meta.get("verdict") == "REJECT", str(meta.get("verdict")))
    _txt2, _lbl2, meta2 = rc.review_segmented([], {"pct": 100.0}, expect_pair=PAIR)
    check("無段 → REJECT", meta2.get("verdict") == "REJECT", str(meta2.get("verdict")))
    old = ROOT / "tests" / "test_review_chain_20261013.py"
    r = subprocess.run([sys.executable, "-X", "utf8", str(old)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))
    tail = (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else ""
    check("既有 20261013 測試全綠", r.returncode == 0 and "失敗" in tail and "／0 失敗" in tail,
          f"rc={r.returncode} tail={tail}")


def t9() -> None:
    print("\nT9 死碼回歸鎖（純綁定 JSON 不是有效審查）")
    pure = _binding_json(PAIR)
    check("_valid_review(純綁定JSON) is False", rc._valid_review(pure) is False,
          str(rc._valid_review(pure)))
    check("contract_violation 指出 verdict 不可判定",
          "verdict 不可判定" in (rc.contract_violation(rc.parse_review(pure)) or ""),
          str(rc.contract_violation(rc.parse_review(pure))))
    # review() 必須拒收；review_text() 必須接受 —— 這正是 R1 的分工
    with Patch():
        rc._layers = lambda: [("FAKE", lambda *a, **k: pure)]
        _t, _l = rc.review_text("x")
        check("review_text 可取純綁定文字", _t == pure, _t[:60])
        _raised = ""
        try:
            rc.review("x")
        except RuntimeError as e:
            _raised = str(e)
        check("review() 對純綁定仍 fail-closed", "無可判定 verdict" in _raised, _raised[:160])


def main() -> int:
    print("=" * 60)
    print("review_chain 綁定契約誤拒 — T1~T9")
    print("=" * 60)
    for fn in (t1, t2, t3, t4, t5, t6, t7, t8, t9):
        fn()
    print(f"\n{PASS} 通過／{FAIL} 失敗")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
