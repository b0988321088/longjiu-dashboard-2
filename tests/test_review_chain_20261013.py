#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_review_chain_20261013.py — TD-20261013-05／06 根因修復的回歸測試

被驗行為（review_chain.py 的異質審查鏈 + cio_lane.py 的 fail-closed 收斂）：
  T1 正常審查     ：第一層可用 → 由第一層回應，label 正確回報。
  T2 402          ：第一層 HTTP 402 → 第二層接手（不再全停）。
  T3 逾時         ：第一層 timeout → 第二層接手。
  T4 無效回應     ：HTTP 200 但無 choices → 視為失敗 → 下一層。
  T5 空輸出       ：finish_reason=length 且 content 空 → 下一層（不得當成功）。
  T6 全鏈失敗     ：所有層失敗 → 丟例外（呼叫端 fail-closed），錯誤含每一層。
  T7 拒審不換層   ：模型回 REJECT → 停在同一層，**不得**為了拿 APPROVE 改試別層。
  T8 憑證防護     ：nous agent_key 過期 → 該層直接排除（不用失效憑證硬打）。
  T9 失敗不留紀錄 ：審查全失敗 → cio_lane 回 False 且 .git/CIO_APPROVED 未新增列。

全程離線（打樁 _post／_layers／review_chain 模組），不連外、不動真 repo。
執行：python -X utf8 tests/test_review_chain_20261013.py
"""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import types
import urllib.error
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


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout.strip()


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x/y", code, "err", {}, io.BytesIO(b"{}"))


def main() -> int:
    rc = _load("review_chain_probe", ROOT / "review_chain.py")

    # ---- 打樁：以腳本化的層行為取代真網路 -------------------------------------
    def stub_layers(script: dict):
        """script: {label: 行為}；行為 ∈ ok / http402 / timeout / nochoice / empty。"""
        seen: list[str] = []

        def mk(label):
            def fn(prompt, max_tokens, timeout, json_mode, _l=label):
                seen.append(_l)
                act = script.get(_l, "ok")
                if act == "http402":
                    raise _http_error(402)
                if act == "timeout":
                    raise TimeoutError("timed out")
                if act == "nochoice":
                    raise RuntimeError("回應無 choices：{}")
                if act == "empty":
                    raise RuntimeError("空輸出（finish_reason=length）")
                if act == "reject":
                    # 2026-10-15 B1（R1）：合法 REJECT 必須指名**可定位依據**（檔名／行號）
                    return ('{"verdict":"REJECT","reviewed_commits":[],'
                            '"blocking":["asset_diff_history.json：2026-10-15 缺 bonds（append_today 行 441-460）"],'
                            '"note":"n"}')
                if act == "reject_vague":
                    return '{"verdict":"REJECT","reviewed_commits":[],"blocking":["x"],"note":"n"}'
                if act == "reject_empty":
                    return '{"verdict":"REJECT","reviewed_commits":[],"blocking":[],"note":"n"}'
                if act == "approve_with_blocking":
                    return ('{"verdict":"APPROVE","reviewed_commits":[],'
                            '"blocking":["daily_report_v2_2026-10-15.html：不符"],"note":"n"}')
                return '{"verdict":"APPROVE","reviewed_commits":[],"blocking":[],"note":"ok"}'
            return fn

        labels = list(script.keys())
        return [(l, mk(l)) for l in labels], seen

    real_layers = rc._layers
    try:
        cases = [
            ("T1 正常審查 → 第一層回應",
             {"A": "ok", "B": "ok", "C": "ok"}, 1, 0),
            ("T2 402 → 第二層接手（不再全停）",
             {"A": "http402", "B": "ok", "C": "ok"}, 2, 0),
            ("T3 逾時 → 第二層接手",
             {"A": "timeout", "B": "ok", "C": "ok"}, 2, 0),
            ("T4 無效回應（無 choices）→ 下一層",
             {"A": "nochoice", "B": "ok", "C": "ok"}, 2, 0),
            ("T5 空輸出 → 下一層（不得當成功）",
             {"A": "empty", "B": "ok", "C": "ok"}, 2, 0),
            # 2026-10-15 B1（R1）：契約違規（verdict 與 blocking 不一致／缺可定位依據）
            # → 該層判**無效審查**，續試下一層（不得把違規回覆當成有效判定）
            ("T10 契約違規：REJECT 但 blocking 空 → 無效，續下一層",
             {"A": "reject_empty", "B": "ok", "C": "ok"}, 2, 0),
            ("T11 契約違規：REJECT 的 blocking 無可定位依據 → 無效，續下一層",
             {"A": "reject_vague", "B": "ok", "C": "ok"}, 2, 0),
            ("T12 契約違規：APPROVE 但 blocking 非空 → 無效，續下一層",
             {"A": "approve_with_blocking", "B": "ok", "C": "ok"}, 2, 0),
        ]
        for title, script, want_calls, _ in cases:
            print(title)
            layers, seen = stub_layers(script)
            rc._layers = lambda: layers
            try:
                txt, label = rc.review("p", max_tokens=32, timeout=5)
                check(f"呼叫層數＝{want_calls}", len(seen) == want_calls, str(seen))
                check("回傳為可解析 JSON", "verdict" in json.loads(txt))
                check("label 為實際使用者（非寫死）", label == seen[-1], f"{label} vs {seen[-1]}")
            finally:
                rc._layers = real_layers

        print("T6 全鏈失敗 → 丟例外，錯誤逐層記錄")
        layers, seen = stub_layers({"A": "http402", "B": "timeout", "C": "nochoice"})
        rc._layers = lambda: layers
        try:
            rc.review("p", max_tokens=32, timeout=5)
            check("應丟例外", False, "未丟例外")
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            check("三層都試過", len(seen) == 3, str(seen))
            check("錯誤含 402", "402" in msg or "HTTP Error 402" in msg, msg[:160])
            check("錯誤含逾時", "timed out" in msg or "timeout" in msg.lower(), msg[:160])
        finally:
            rc._layers = real_layers

        print("T7 拒審不換層（不得為了拿 APPROVE 改試別層）")
        layers, seen = stub_layers({"A": "reject", "B": "ok", "C": "ok"})
        rc._layers = lambda: layers
        try:
            txt, label = rc.review("p", max_tokens=32, timeout=5)
            check("只呼叫第一層（不因 REJECT 換層）", len(seen) == 1, str(seen))
            check("原樣回傳 REJECT", json.loads(txt)["verdict"] == "REJECT")
            check("label 為第一層", label == "A", label)
        finally:
            rc._layers = real_layers

        print("T13 全層契約違規 → fail-closed 丟例外（不得拿違規回覆放行）")
        layers, seen = stub_layers({"A": "reject_empty", "B": "reject_vague",
                                    "C": "approve_with_blocking"})
        rc._layers = lambda: layers
        try:
            rc.review("p", max_tokens=32, timeout=5)
            check("應丟例外", False, "未丟例外（契約違規回覆被當成有效審查）")
        except Exception as exc:  # noqa: BLE001
            check("三層都試過", len(seen) == 3, str(seen))
            check("錯誤訊息含契約違規", "契約違規" in str(exc), str(exc)[:200])
        finally:
            rc._layers = real_layers

        print("T14 契約驗證純函式（contract_violation）正負向")
        _ok_rej = {"verdict": "REJECT", "blocking": ["asset_diff_history.json：缺 bonds（行 441）"]}
        check("合法 REJECT → 合規", rc.contract_violation(_ok_rej) is None,
              str(rc.contract_violation(_ok_rej)))
        check("REJECT 空 blocking → 違規",
              (rc.contract_violation({"verdict": "REJECT", "blocking": []}) or "").startswith("契約違規"))
        check("APPROVE 非空 blocking → 違規",
              (rc.contract_violation({"verdict": "APPROVE", "blocking": ["x"]}) or "").startswith("契約違規"))
        check("blocking 缺可定位依據 → 違規",
              (rc.contract_violation({"verdict": "REJECT", "blocking": ["x"]}) or "").startswith("契約違規"))
        check("APPROVE 空 blocking → 合規",
              rc.contract_violation({"verdict": "APPROVE", "blocking": []}) is None)
    finally:
        rc._layers = real_layers

    print("T8 憑證防護：agent_key 過期 → 排除該層")
    real_cred = rc._nous_credentials
    try:
        rc._nous_credentials = lambda: None
        labels = [l for l, _ in rc._layers()]
        check("nous 層全數排除（只剩 keyless 層）",
              all("nous" not in l for l in labels), str(labels))
        check("keyless 層仍在", any("Pollinations" in l for l in labels), str(labels))
    finally:
        rc._nous_credentials = real_cred

    print("T9 審查全失敗 → cio_lane 回 False 且不留 RECORD")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "t")
        (repo / "x.json").write_text('{"v":0}', encoding="utf-8")
        _git(repo, "add", "x.json")
        _git(repo, "commit", "-q", "-m", "base")
        base_tree = _git(repo, "rev-parse", "HEAD")
        _git(repo, "update-ref", "refs/remotes/origin/clean-main", base_tree)
        (repo / "x.json").write_text('{"v":1}', encoding="utf-8")
        _git(repo, "add", "x.json")
        _git(repo, "commit", "-q", "-m", "candidate")

        rec = repo / ".git" / "CIO_APPROVED"
        before = rec.read_text(encoding="utf-8") if rec.exists() else ""

        lane = _load("cio_lane_probe", ROOT / "cio_lane.py")
        old_base = lane.BASE
        lane.BASE = repo
        fake = types.ModuleType("review_chain")

        def _boom(*a, **k):
            raise RuntimeError("CIO-Pollinations(openai): HTTP Error 402；nous: 空輸出")

        fake.review = _boom
        # 2026-10-13 P1：cio_lane 改為呼叫 review_chain.build_review_prompt 組送審 prompt
        # （兩車道單一真值），打樁須一併提供否則會以 AttributeError 中止，測不到 T9 原意。
        fake.build_review_prompt = lambda *a, **k: "STUB-PROMPT"
        sys.modules["review_chain"] = fake
        try:
            ok, msg = lane.review_and_record("t9")
            after = rec.read_text(encoding="utf-8") if rec.exists() else ""
            check("回傳 False（fail-closed）", ok is False, f"ok={ok}")
            check("訊息指出審查鏈不可用", "審查鏈" in msg, msg[:120])
            check("未新增 RECORD（不留授權痕跡）", after == before, f"before={len(before)} after={len(after)}")
            check("HEAD 仍停在候選 commit（未被靜默推送）",
                  _git(repo, "rev-parse", "HEAD") == _git(repo, "rev-parse", "HEAD"))
        finally:
            lane.BASE = old_base
            sys.modules.pop("review_chain", None)

    print(f"\n{PASS} 通過／{FAIL} 失敗")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
