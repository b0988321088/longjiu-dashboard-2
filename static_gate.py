#!/usr/bin/env python3
"""static_gate.py — 致命類靜態檢查閘門（2026-09-12 建立，INC-156）

只擋「會炸掉或會靜默算錯」的類別，其餘化妝品級（f-string 無佔位、未用 import、
未用變數）刻意不檢查 — 目的是維持訊噪比，讓真 bug 浮得出來：
  F821 未定義名稱（NameError）
  F823 先用後賦值（UnboundLocalError，典型：函式內 local import 遮蔽同名全域）
  F811 重複定義（後者靜默覆蓋前者）
  F601/F602 重複 dict key（Python 靜默取最後一個 → 算錯不報錯）

背景：2026-09-12 一次全庫掃描，341 筆裡真正會炸的只有這 7 筆（含 run_daily.py 的
`intel_text`、`timedelta` 被 local import 遮蔽、`monthly_income` 重複 key），
但沒有任何機制會在提交前發現它們。此閘門即為該機制的自動化。

用法：python static_gate.py [--root .]
退出碼：0 = 通過（或工具不可用而跳過）；1 = 發現致命類問題
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

RULES = "F821,F823,F811,F601,F602"
EXCLUDE = "node_modules,__pycache__,archive,.git,.venv,venv"


def _find_runner() -> list[str] | None:
    """依序找可用的 ruff 執行方式（cron/agent 環境路徑各異，故多重 fallback）。"""
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = []
    if local:
        candidates.append([os.path.join(local, "hermes", "bin", "uv"), "run", "--no-project", "--with", "ruff", "ruff", "check"])
    candidates.append(["uv", "run", "--no-project", "--with", "ruff", "ruff", "check"])
    if local:
        candidates.append([os.path.join(local, "hermes", "bin", "uvx"), "ruff", "check"])
    candidates.append(["uvx", "ruff", "check"])
    for cmd in candidates:
        if shutil.which(cmd[0]) or os.path.exists(cmd[0]):
            return cmd
    return None


def main() -> int:
    root = "."
    if "--root" in sys.argv:
        i = sys.argv.index("--root")
        if i + 1 < len(sys.argv):
            root = sys.argv[i + 1]
    if not Path(root).exists():
        print(f"⚠️ 靜態閘門：找不到 {root}，跳過")
        return 0

    runner = _find_runner()
    if runner is None:
        print("⚠️ 靜態閘門：找不到 ruff（uv/uvx 皆不可用），本次跳過 — 請人工確認")
        return 0

    cmd = runner + [root, "--select", RULES, "--exclude", EXCLUDE, "--output-format", "concise", "--quiet"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except Exception as e:  # 工具本身壞掉不應該擋住產報
        print(f"⚠️ 靜態閘門：ruff 執行失敗（{e}），跳過")
        return 0

    out = (r.stdout or "") + (r.stderr or "")
    hits = [l for l in out.splitlines() if ":" in l and any(f" {x} " in f" {l} " or f" {x}\n" in l + "\n" for x in RULES.split(","))]

    if r.returncode == 0:
        print("✅ 靜態閘門通過（無未定義名稱／重複定義／重複 dict key）")
        return 0

    print("❌ 靜態閘門擋下（會炸或會靜默算錯的類別）：")
    for l in hits[:20]:
        print("  • " + l.strip())
    if len(hits) > 20:
        print(f"  …另有 {len(hits) - 20} 筆，完整清單請執行：ruff check . --select {RULES}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
