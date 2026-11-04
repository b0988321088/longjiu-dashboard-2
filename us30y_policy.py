#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""us30y_policy.py — US30Y 門檻政策的單一來源（B 案；**尚未生效**）

為什麼要有這一支
----------------
2026-11-04 使用者提問「30Y 定在 5.20 是不是不再適合、是否放寬到 5.30」。實測（Yahoo ^TYX 日線）：

- 近 6 個月 30Y 中位數 5.206、均值 5.204 → 「警戒線 5.20」正好落在資料中位數，
  近 47 個交易日 100% 在其上方（最長連續 48 日）＝已變常態，失去鑑別力。
- 5.30 反而被頻繁穿越：近 3 個月 ≥5.30 的連續段為 1／5／1／22／6／1 日
  → 「連續 2 日」的判定對單日來回穿越過度敏感。
- 因此「把 5.20 直接抬到 5.30」不會更寬鬆（10 月有 22 個交易日全在 5.30 上方），
  只會把假警報換位置。

B 案（使用者 2026-11-04 選定，待 12/01 前一句話核准上線）
------------------------------------------------------
① `WARN_DISPLAY_ONLY = 5.20`：純顯示，不再綁任何行動（不凍結美股、不凍結債券）。
② 行動門檻只綁 `ACTION_THRESHOLD = 5.30`。
③ 行動觸發平滑為「連續 `ACTION_CONSECUTIVE_DAYS = 5` 個交易日」。

開關語意
--------
`APPROVED = False`（預設）＝與 2026-11-04 前的行為逐位元相同。
使用者核准後把 `APPROVED` 改 True 且日期已達 `EFFECTIVE_FROM` 才生效 —— 這是刻意的
人工閘門：門檻放寬屬決策層變更，不得由時間自動生效（避免凍結期內變相放行）。
"""
from __future__ import annotations

from datetime import date as _date, datetime

APPROVED = True                  # 2026-11-04 使用者裁決「上線」；生效日仍受 EFFECTIVE_FROM 約束
EFFECTIVE_FROM = "2026-12-01"    # 核准後仍不得早於此日生效

WARN_DISPLAY_ONLY = 5.20         # 純顯示（不綁行動）
ACTION_THRESHOLD = 5.30          # 唯一行動門檻
ACTION_CONSECUTIVE_DAYS = 5      # 平滑單日穿越

LEGACY_CONSECUTIVE_DAYS = 2      # 舊制（未生效時）


def is_active(today=None) -> bool:
    """B 案是否生效：需 APPROVED 且已達生效日。任何解析失敗一律視為未生效（fail-closed）。"""
    if not APPROVED:
        return False
    try:
        _t = today or _date.today()
        if isinstance(_t, datetime):
            _t = _t.date()
        elif isinstance(_t, str):
            _t = _date.fromisoformat(_t[:10])
        return _t >= _date.fromisoformat(EFFECTIVE_FROM)
    except Exception:
        return False


def action_consecutive_days(today=None) -> int:
    """行動判定所需的連續交易日數（生效＝5；未生效＝舊制 2）。"""
    return ACTION_CONSECUTIVE_DAYS if is_active(today) else LEGACY_CONSECUTIVE_DAYS


def describe() -> str:
    """一行口徑說明（給 log／報表用，避免各處自行拼字）。"""
    if is_active():
        return (f"B 案生效：{WARN_DISPLAY_ONLY:.2f}% 純顯示；行動門檻 ≥{ACTION_THRESHOLD:.2f}% "
                f"連續 {ACTION_CONSECUTIVE_DAYS} 交易日")
    return (f"舊制（B 案未生效）：模式A ≥5.20% 連 {LEGACY_CONSECUTIVE_DAYS} 日即防禦；"
            f"紅線 ≥{ACTION_THRESHOLD:.2f}% 連 {LEGACY_CONSECUTIVE_DAYS} 日")
