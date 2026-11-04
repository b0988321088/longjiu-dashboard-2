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


# ── 顯示層共用文案（2026-11-04：8 個報表原本各自寫死 5.20，改由這裡單一出字）──
#   原則：顯示層只負責「把口徑說對」，不得自行判定；判定一律在 us30y_monitor／sot_targets。

def band_text() -> str:
    """警戒帶的文字敘述（舊制 5.20-5.30／B 案 ≥5.30 連續N日）。"""
    if is_active():
        return f"≥{ACTION_THRESHOLD:.2f}%（連續{ACTION_CONSECUTIVE_DAYS}日）"
    return f"{WARN_DISPLAY_ONLY:.2f}-{ACTION_THRESHOLD:.2f}%"


def band_action() -> str:
    """警戒帶對應的動作（B 案下 5.20 不再凍結任何東西）。"""
    if is_active():
        return (f"顯示用、不凍結（行動門檻 ≥{ACTION_THRESHOLD:.2f}% 連續{ACTION_CONSECUTIVE_DAYS}日："
                f"長債新增凍結、科技上限維持）")
    return "台股≤50萬/週、美股停購、長債凍結"


def red_text() -> str:
    """紅線敘述（含連續天數）。"""
    need = action_consecutive_days()
    return f"≥{ACTION_THRESHOLD:.2f}%（連續{need}日）"


def entry_text() -> str:
    """市值型大額進場的解凍條件敘述。"""
    need = action_consecutive_days()
    return f"連續{need}日 <{ACTION_THRESHOLD:.2f}%"


def bond_freeze_text() -> str:
    """長債新增凍結的門檻敘述（舊制 >5.20 即凍結；B 案 ≥5.30 連續N日才凍結）。"""
    if is_active():
        return f"≥{ACTION_THRESHOLD:.2f}%（連續{ACTION_CONSECUTIVE_DAYS}日）"
    return f">{WARN_DISPLAY_ONLY:.2f}%"


def us30y_state_text(rate) -> str:
    """給簡報／卡片用的單行狀態（rate 為百分數，例如 5.29）。"""
    try:
        r = float(rate)
    except Exception:
        return "US30Y 無讀值"
    if is_active():
        if r >= ACTION_THRESHOLD:
            return f"{r:.2f}% 高於行動門檻 {ACTION_THRESHOLD:.2f}%（連續{ACTION_CONSECUTIVE_DAYS}日才凍結）"
        return f"{r:.2f}% 行動門檻以下（{WARN_DISPLAY_ONLY:.2f}% 僅顯示）"
    if r >= ACTION_THRESHOLD:
        return f"{r:.2f}% 已達 {ACTION_THRESHOLD:.2f}% 凍結線"
    if r >= WARN_DISPLAY_ONLY:
        return f"{r:.2f}% 警戒區（{WARN_DISPLAY_ONLY:.2f}-{ACTION_THRESHOLD:.2f}），未觸發凍結"
    return "警戒線下"


def gate_rows() -> list:
    """三層閘門表（週報用）：[(燈號, 範圍, 規則), ...]。"""
    if is_active():
        return [
            ("🟢", f"<{ACTION_THRESHOLD:.2f}%", "不凍結；可分批建倉（解凍另看 sot_targets.unfreeze_conditions）"),
            ("🟡", f"{WARN_DISPLAY_ONLY:.2f}-{ACTION_THRESHOLD:.2f}%",
             "顯示用、不觸發任何凍結（B 案）"),
            ("🔴", f"≥{ACTION_THRESHOLD:.2f}%（連續{ACTION_CONSECUTIVE_DAYS}日）",
             "長債新增凍結；科技上限維持或收緊；不否決台股分批"),
        ]
    return [
        ("🟢", f"<{WARN_DISPLAY_ONLY:.2f}%", "解凍；可分批建倉"),
        ("🟡", f"{WARN_DISPLAY_ONLY:.2f}-{ACTION_THRESHOLD:.2f}%", "警戒：台股≤50萬/週、美股停購、長債凍結、LTV≤30%"),
        ("🔴", f"≥{ACTION_THRESHOLD:.2f}%", "長債凍結；五因子綜合判斷（非直接凍結）"),
    ]
