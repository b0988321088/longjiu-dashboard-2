#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schedule_events_weekly_clean.py — 週日 08:00 cron 的入口（2026-09-16 收尾後僅剩入口）

為什麼留著這個檔名：Hermes cron 的 script 欄位只吃「HERMES_HOME/scripts/ 內的單一檔名」，
不吃參數（cron/scheduler_script.py::_script_argv 只傳 path），所以改檔名就得動 cron 設定。
→ 保留檔名當入口、實作全部集中到 scripts/components/cleanup_utils.py（單一來源）。

實作：cleanup_utils.weekly_calendar_main()（分類規則／state／commit+push 契約都在那裡）
用法：python schedule_events_weekly_clean.py [--dry-run]
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

from cleanup_utils import weekly_calendar_main  # noqa: E402

if __name__ == "__main__":
    weekly_calendar_main()
