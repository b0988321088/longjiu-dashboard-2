#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/test_review_chain_stability.py — B1／R1 審查鏈發布安全回歸測試（2026-10-15）

驗證行為（對應使用者 B1 四項強制要求）：
  S1 契約違規必須被拒（本檔做端到端整合；純函式在 tests/test_review_chain_20261013.py）
  S2 分段 diff 必須有完整涵蓋證據；涵蓋率 <100% 不得 APPROVE
  S3 不得靜默截斷：超量 diff 必須出現涵蓋率提示，且改走**完整分段**
  S4 一致性：同一輸入重複送審結論矛盾 → UNSTABLE（不得作為核准依據）

負向自測：每個正向斷言都附「舊行為／被停用時的樣本」，證明斷言確有鑑別力。

全程離線：以打樁 `_layers` 取代真網路，不連外、不動真 repo。
執行：python -X utf8 tools/test_review_chain_stability.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PASS = FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    rc = _load("review_chain_probe2", ROOT / "review_chain.py")
    real_layers = rc._layers

    def stub(actions: list[str]):
        """actions：依序回覆的行為（approve / reject_ok / reject_empty）。"""
        calls: list[int] = []

        def mk(i: int):
            def fn(prompt, max_tokens, timeout, json_mode):
                calls.append(i)
                a = actions[min(i, len(actions) - 1)]
                if a == "reject_ok":
                    return json.dumps({"verdict": "REJECT",
                                       "blocking": ["buffett_cto_report_2026-10-15.md：X（行 1）"]},
                                      ensure_ascii=False)
                if a == "reject_empty":
                    return '{"verdict":"REJECT","blocking":[],"note":"n"}'
                return '{"verdict":"APPROVE","blocking":[],"note":"ok"}'
            return fn
        return [(f"L{i}", mk(i)) for i in range(len(actions))], calls

    def stub_by_prompt(mapping: dict):
        """依 prompt 內容決定回覆（分段彙總用：每段各由同一層回應）。"""
        calls: list[str] = []

        def mk(label: str):
            def fn(prompt, max_tokens, timeout, json_mode, _l=label):
                calls.append(_l)
                a = mapping.get(prompt, "approve")
                if a == "reject_ok":
                    return json.dumps({"verdict": "REJECT",
                                       "blocking": ["buffett_cto_report_2026-10-15.md：X（行 1）"]},
                                      ensure_ascii=False)
                if a == "reject_empty":
                    return '{"verdict":"REJECT","blocking":[],"note":"n"}'
                if a == "approve_bound":
                    return ('{"verdict":"APPROVE","blocking":[],'
                            '"reviewed_commits":[{"commit":"abc123abc123","tree":"tree123tree1"}],'
                            '"note":"ok"}')
                return '{"verdict":"APPROVE","blocking":[],"note":"ok"}'
            return fn
        return [("L0", mk("L0"))], calls

    try:
        # ---- S3：不得靜默截斷 -------------------------------------------------
        print("S3 超量 diff 不得靜默截斷（須標示涵蓋率並改走分段）")
        big = "".join(f"+line {i}\n" for i in range(4000))     # ~44k 字元 > 12000
        prompts, cov = rc.build_review_prompts("abc123abc123", "tree123tree1", "s",
                                              "a.py", "1 file", diff_cap=12000, patch=big)
        check("分段數 > 1（完整切段）", cov["segments"] > 1, str(cov))
        check("涵蓋率 = 100%（所有字元都送審）", cov["pct"] == 100.0, str(cov))
        check("provided == total", cov["provided_chars"] == cov["total_chars"], str(cov))
        check("單段 prompt 亦含段落標示（第 k/n 段）", all("第 " in p for p in prompts))
        # 舊行為樣本（截斷且無提示）→ 必須被偵測為「缺涵蓋率證據」
        legacy = "變更內容（實際 patch）：\n```diff\n" + big[:12000] + "\n```\n"
        check("負向：未改前的樣本須被判為缺涵蓋率提示（證明斷言有鑑別力）",
              "涵蓋率" not in legacy)
        check("正向：單段版 prompt 於超量時出現涵蓋率提示",
              "涵蓋率" in rc.build_review_prompt("abc123abc123", "tree123tree1", "s",
                                                "a.py", "1 file", 12000, big))

        # ---- S2：涵蓋率不足 → 不得 APPROVE -----------------------------------
        print("S2 涵蓋率 <100% → 直接拒絕核准（不呼叫模型）")
        layers, calls = stub(["approve", "approve"])
        rc._layers = lambda: layers
        txt, label, meta = rc.review_segmented(["p1", "p2"],
                                               {"total_chars": 100, "provided_chars": 90,
                                                "pct": 90.0, "segments": 1})
        j = json.loads(txt)
        check("verdict=REJECT", j["verdict"] == "REJECT", txt[:120])
        check("blocking 指名涵蓋率不足", any("涵蓋率" in str(b) for b in j["blocking"]), str(j["blocking"]))
        check("未呼叫任何模型層", calls == [], str(calls))
        check("label=coverage-guard", label == "coverage-guard", label)
        # 負向自測：同一打樁在涵蓋率 100% 時應放行 → 證明上一個 REJECT 來自守門而非打樁
        layer2, calls2 = stub(["approve"])
        rc._layers = lambda: layer2
        txt2, _, _ = rc.review_segmented(["p"], {"total_chars": 10, "provided_chars": 10,
                                                 "pct": 100.0, "segments": 1})
        check("負向對照：涵蓋率 100% 時同打樁可放行（證明守門有牙）",
              json.loads(txt2)["verdict"] == "APPROVE" and calls2 == [0], txt2[:120])

        # ---- 分段彙總：任一段有 blocking → 整體 REJECT -------------------------
        print("S2b 分段彙總：任一段 blocking → 整體 REJECT（blocking 取聯集）")
        layers, calls = stub_by_prompt({"p1": "approve", "p2": "reject_ok"})
        rc._layers = lambda: layers
        txt, _, meta = rc.review_segmented(["p1", "p2"],
                                           {"total_chars": 20, "provided_chars": 20,
                                            "pct": 100.0, "segments": 2})
        j = json.loads(txt)
        check("全段皆呼叫", len(calls) == 2, str(calls))
        check("整體 REJECT", j["verdict"] == "REJECT", txt[:120])
        check("blocking 聯集非空", len(j["blocking"]) == 1, str(j["blocking"]))

        # ---- 分段綁定：每段都須回報 commit/tree 綁定 ---------------------------
        print("S2c 分段綁定：任一段未回報 commit/tree 綁定 → 不得放行")
        layers, _c = stub_by_prompt({"p1": "approve", "p2": "approve"})   # 回覆不含 reviewed_commits
        rc._layers = lambda: layers
        txt, _, meta = rc.review_segmented(["p1", "p2"],
                                           {"total_chars": 20, "provided_chars": 20,
                                            "pct": 100.0, "segments": 2},
                                           expect_pair=("abc123abc123", "tree123tree1"))
        check("未回報綁定 → REJECT", json.loads(txt)["verdict"] == "REJECT", txt[:140])
        check("blocking 指名未回報綁定",
              any("綁定" in str(b) for b in json.loads(txt)["blocking"]), str(json.loads(txt)["blocking"]))
        layers, _c = stub_by_prompt({"p1": "approve_bound", "p2": "approve_bound"})
        rc._layers = lambda: layers
        txt, _, meta = rc.review_segmented(["p1", "p2"],
                                           {"total_chars": 20, "provided_chars": 20,
                                            "pct": 100.0, "segments": 2},
                                           expect_pair=("abc123abc123", "tree123tree1"))
        j = json.loads(txt)
        check("負向對照：正確回報綁定 → APPROVE", j["verdict"] == "APPROVE", txt[:140])
        check("彙總保留 reviewed_commits 供上游比對",
              len(j.get("reviewed_commits") or []) == 1, str(j.get("reviewed_commits")))

        # ---- S4：一致性（UNSTABLE）-------------------------------------------
        print("S4 重複送審一致性：矛盾即 UNSTABLE")
        st_ok = rc.stability_check(["APPROVE", "APPROVE"])
        st_bad = rc.stability_check(["APPROVE", "REJECT"])
        check("一致 → STABLE", st_ok["status"] == "STABLE", str(st_ok))
        check("矛盾 → UNSTABLE", st_bad["status"] == "UNSTABLE", str(st_bad))
        check("UNSTABLE 明確標示不得作為核准依據", "不得作為核准依據" in st_bad["note"], st_bad["note"])
        check("負向對照：單一取樣不得算 STABLE（無法證明一致性）",
              rc.stability_check(["APPROVE"])["status"] == "UNSTABLE")

        # ---- 契約守門（端到端）-------------------------------------------------
        print("S1 契約守門：違規回覆視為無效 → 續下一層；全層違規 → fail-closed")
        layers, calls = stub(["reject_empty", "approve"])
        rc._layers = lambda: layers
        txt, label = rc.review("p", max_tokens=32, timeout=5)
        check("違規層被跳過（呼叫 2 層）", len(calls) == 2, str(calls))
        check("採用第二層", label == "L1", label)
        layers, calls = stub(["reject_empty"])
        rc._layers = lambda: layers
        try:
            rc.review("p", max_tokens=32, timeout=5)
            check("全層違規應丟例外", False, "未丟例外")
        except Exception as exc:  # noqa: BLE001
            check("全層違規 → fail-closed 例外", "契約違規" in str(exc), str(exc)[:160])
    finally:
        rc._layers = real_layers

    print("\n" + "=" * 54)
    print(f"測試結果：{PASS} PASS / {FAIL} FAIL")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
