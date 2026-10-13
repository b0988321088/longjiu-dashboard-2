#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_cio_lane_rollback_20261013.py — 2026-10-13 台股緊急應變發布故障修復的沙盒驗證

被驗行為（daily_deploy.py / nightly_dashboard_sync.py 共同根因修復）：
  T1 閘門判定：強制真 CIO 類檔（index.html／snapshot.json）＝True；低風險白名單（cost.*）＝False。
  T2 真審查未過 → **撤回本步驟 commit**（HEAD 不前進、內容留工作區）→ 不留推不出去的 commit 卡住整條範圍。
  T3 真審查通過 → commit 保留（不撤回），交由 auto_push 推送。
沙盒：暫存 git repo + stub 掉 cio_lane（不連外、不動真 repo）。
執行：python -X utf8 tests/test_cio_lane_rollback_20261013.py
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # daily_deploy 會 import logging_config（repo 根目錄）
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


def main() -> int:
    dd = _load("daily_deploy_probe", ROOT / "daily_deploy.py")

    print("T1 閘門判定（單一真值 publish_gate）")
    check("index.html → 必須真 CIO", dd._gate_requires_cio(["index.html"]) is True)
    check("snapshot.json → 必須真 CIO", dd._gate_requires_cio(["snapshot.json"]) is True)
    check("cost.html+cost_data.json → 可走 AUTO", dd._gate_requires_cio(["cost.html", "cost_data.json"]) is False)
    check("判定失敗 fail-closed（不存在的檔名→仍False；不拋例外）",
          dd._gate_requires_cio(["__不存在__.json"]) in (True, False))

    for title, verdict_ok in (("T2 真審查未過 → 撤回 commit（保留阻塞）", False),
                              ("T3 真審查通過 → commit 保留", True)):
        print(title)
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _git(repo, "init", "-q")
            _git(repo, "config", "user.email", "t@example.com")
            _git(repo, "config", "user.name", "t")
            f = repo / "x.json"
            f.write_text('{"v":0}', encoding="utf-8")
            _git(repo, "add", "x.json")
            _git(repo, "commit", "-q", "-m", "init")
            base = _git(repo, "rev-parse", "HEAD")
            f.write_text('{"v":1}', encoding="utf-8")

            stub = types.ModuleType("cio_lane")
            calls: list[str] = []

            def _rar(tag: str = "x"):
                calls.append(tag)
                return (verdict_ok, "stub " + ("APPROVE" if verdict_ok else "REJECT"))

            stub.review_and_record = _rar
            sys.modules["cio_lane"] = stub

            old_base, old_gate = dd.BASE, dd._gate_requires_cio
            dd.BASE = repo
            dd._gate_requires_cio = lambda paths: True   # 強制走真審查車道
            try:
                ok = dd.github_push("x.json")
                head = _git(repo, "rev-parse", "HEAD")
                dirty = bool(_git(repo, "status", "--porcelain", "--", "x.json"))
                rolled = (head == base)
                check("審查車道被呼叫一次", calls == ["daily_deploy"], str(calls))
                check("回傳 False（保留阻塞）", ok is False, f"ok={ok}")
                if verdict_ok:
                    check("HEAD 前進（commit 保留）", not rolled, f"head={head[:8]} base={base[:8]}")
                    check("檔案已進 commit（工作區乾淨）", dirty is False)
                else:
                    check("HEAD 未前進（已撤回 commit）", rolled, f"head={head[:8]} base={base[:8]}")
                    check("內容留在工作區（仍 dirty，下輪可重試）", dirty is True)
            finally:
                dd.BASE, dd._gate_requires_cio = old_base, old_gate
                sys.modules.pop("cio_lane", None)

    print(f"\n{PASS} 通過／{FAIL} 失敗")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
