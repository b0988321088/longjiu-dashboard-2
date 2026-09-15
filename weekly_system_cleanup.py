#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""weekly_system_cleanup.py — 每週一 03:00 cron 的入口：龍九系統全量深度清理

2026-09-16 建立：原 cron（weekly-system-cleanup）的 script 欄位寫成
「components/cleanup_utils.py --apply」——但 Hermes cron 只吃 HERMES_HOME/scripts/ 內的單一
檔名、不傳參數 → 該 job 每次都會以 "Script not found" 失敗（從未跑過）。改為本入口檔（檔名
落在 scripts 目錄、鏡像自動同步），參數改由這裡寫死。

實作：cleanup_utils.run_full_cleanup(apply_changes=True)
用法：python weekly_system_cleanup.py [--dry-run]   # --dry-run 只印不動檔
⚠️ 這支會真的刪/搬檔案（備份只留最新 2、淘汰腳本搬進 .archive、舊日誌歸檔）——乾跑先看。
"""
import pathlib
import sys

_REPO_FALLBACK = pathlib.Path(r"C:/Users/bot/Desktop/longjiu_system")


def _repo_root() -> pathlib.Path:
    for cand in (pathlib.Path.cwd(), pathlib.Path(__file__).resolve().parent, _REPO_FALLBACK):
        if (cand / "scripts" / "components" / "cleanup_utils.py").exists():
            return cand
    raise SystemExit("❌ 找不到龍九系統 repo（scripts/components/cleanup_utils.py）")


sys.path.insert(0, str(_repo_root() / "scripts" / "components"))

from cleanup_utils import run_full_cleanup  # noqa: E402

if __name__ == "__main__":
    run_full_cleanup(apply_changes=("--dry-run" not in sys.argv))
