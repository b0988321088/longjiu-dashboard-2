#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mirror_guard.py — repo ↔ hermes/scripts 鏡像守門（2026-10-05 新建）

為什麼需要它
------------
`_audit_closeout.py` 第 5 類原本只比對 **5 支硬編碼檔**（asset_sync／buffett_cto_analyzer／
closing_log／update_data／budget_daily_check）。2026-10-05 實測：真正漂移的是 **10 支**
（另含 asset_diff_monitor、build_dashboard、build_penetration_report、build_rebalance_dashboard、
fire_progress、morning_briefing、report_components、run_daily），且已排除換行碼假陽性
→ 不是掃描器太敏感，而是 **coverage 不足**（固定清單式守門擋不住清單外的成員，
與第 14 類「新增 no_agent 腳本沒部署」同一個病灶）。

本檔 = 全量掃描的**單一實作**：稽核（`_audit_closeout.py` 第 5 類）與獨立守門（CLI／cron）
共用同一份邏輯，避免「兩份掃描各自演化再互相漂移」。

判定規則
--------
1. repo 根目錄 `*.py` ∩ 鏡像同名檔，**逐位元**比對（排除薄轉發器：cron 端刻意保留的轉發層）。
2. repo/wrappers/*.py 是 fail-closed 不變式：遺失或內容不符一律 FAIL
   （轉發器缺失＝cron 集體 Script not found）。
3. 鏡像端沒有的檔不算漂移（全量鏡像只對齊「已存在的同名檔」；新增檔是否要鏡像由部署流程決定）。

退出碼語義（fail-closed）
------------------------
  0 = 一致
  1 = 漂移（內容不一致／wrapper 不符）→ 列出清單
  2 = **無法判定**（解析不到 Hermes 目錄、鏡像目錄不存在、讀檔失敗）
      → 一律視為 FAIL。讀不到不等於沒問題，不得當 PASS。

用法
----
    python mirror_guard.py            # 人類可讀報告
    python mirror_guard.py --json     # 機器可讀（cron／下游守門取用）
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_DEFAULT = Path(__file__).resolve().parent
FORWARDER_MARKS = ("薄轉發器", "REPO_SCRIPT")


def hermes_dir() -> Path | None:
    """解析 Hermes 資料目錄；解析序與 `.githooks/post-commit.py` 的 `_hermes_dir()` 一致。

    （hook 是 git 執行的腳本、匯入會連帶執行模組層程式碼，故不 import，改為同序重寫；
      任一邊改動解析序時必須同步另一邊。）
    """
    cands: list[Path] = []
    env = os.environ.get("HERMES_HOME")
    if env:
        cands.append(Path(env))
    for key in ("USERPROFILE", "HOME"):
        h = os.environ.get(key)
        if h:
            cands.append(Path(h) / "AppData/Local/hermes")
    cands.append(Path(r"C:\Users\bot\AppData\Local\hermes"))
    cands.append(Path.home() / "AppData/Local/hermes")
    for c in cands:
        try:
            if c.is_dir():
                return c
        except OSError:
            continue
    return None


def is_forwarder(p: Path) -> bool:
    """薄轉發器：cron 端保留的轉發層，內容本來就與 repo 真身不同 → 不列入比對。"""
    try:
        t = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return any(m in t for m in FORWARDER_MARKS)


def scan(repo: Path = REPO_DEFAULT, mirror: Path | None = None) -> dict:
    """全量比對；失敗（無法判定）以 RuntimeError 往外丟，由呼叫端當 FAIL 處理。"""
    repo = Path(repo)
    if mirror is None:
        h = hermes_dir()
        if h is None:
            raise RuntimeError(
                "找不到 Hermes 資料目錄（HERMES_HOME/USERPROFILE/HOME 皆無效）→ 無法判定"
            )
        mirror = h / "scripts"
    mirror = Path(mirror)
    if not mirror.is_dir():
        raise RuntimeError(f"鏡像目錄不存在：{mirror} → 無法判定")

    same, forwarders, not_mirrored = 0, 0, 0
    drift: list[str] = []
    for src in sorted(repo.glob("*.py")):
        dst = mirror / src.name
        if not dst.exists():
            not_mirrored += 1
            continue
        if is_forwarder(dst):
            forwarders += 1
            continue
        try:
            if src.read_bytes() == dst.read_bytes():
                same += 1
            else:
                drift.append(src.name)
        except OSError as e:
            drift.append(f"{src.name}(讀取失敗:{e})")

    wrapper_bad: list[str] = []
    wsrc = repo / "wrappers"
    if wsrc.is_dir():
        for s in sorted(wsrc.glob("*.py")):
            d = mirror / s.name
            try:
                if (not d.exists()) or d.read_bytes() != s.read_bytes():
                    wrapper_bad.append(s.name)
            except OSError as e:
                wrapper_bad.append(f"{s.name}({e})")

    return {
        "repo": str(repo),
        "mirror": str(mirror),
        "same": same,
        "drift": drift,
        "forwarders": forwarders,
        "not_mirrored": not_mirrored,
        "wrapper_bad": wrapper_bad,
        "ok": (not drift) and (not wrapper_bad),
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    try:
        r = scan()
    except Exception as e:
        if as_json:
            print(json.dumps({"ok": False, "undecidable": str(e)}, ensure_ascii=False))
        else:
            print(f"❌ 鏡像守門無法判定（fail-closed，視為 FAIL）：{e}")
        return 2

    if as_json:
        print(json.dumps(r, ensure_ascii=False))
    else:
        print(
            f"鏡像守門：一致 {r['same']} 支｜轉發器 {r['forwarders']}｜"
            f"鏡像無此檔 {r['not_mirrored']}｜目標 {r['mirror']}"
        )
        if r["drift"]:
            print(f"❌ 漂移 {len(r['drift'])} 支：{', '.join(r['drift'])}")
        if r["wrapper_bad"]:
            print(f"❌ wrapper 不變式不符 {len(r['wrapper_bad'])} 支：{', '.join(r['wrapper_bad'])}")
        if r["ok"]:
            print("✅ repo ∩ 鏡像（全量、排除轉發器）＋ wrapper 不變式 逐位元一致")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
