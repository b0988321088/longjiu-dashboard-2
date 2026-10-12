# -*- coding: utf-8 -*-
"""基金市值口徑單一來源（2026-10-12 總收尾，TD-20261012-26 根因修復）。

問題：鉅亨（Fund 口袋）＝一般申購（逐檔真值）＋自由Pay。當使用者尚未提供自由Pay 逐檔明細時，
`snapshot.fund_freepay`／`funds_breakdown["自由Pay"]` 會停在上一次真值日（實例：10/08 合計 497,695），
但平台帳戶總覽（使用者 App 畫面，權威）已是 10/12 的 896,219；自由Pay 差額法＝896,219 − 一般申購 401,048
＝ 495,171。舊寫法直接加總逐檔字典 → 鉅亨 898,743 ＋ 國泰 11,780,925 ＝ 12,679,668 ≠ funds 12,677,144
（差 2,524），日報那行與門檻檢查同時失準。

原則（不是把兩邊改成一樣、也不是用容差吃掉差異）：
  1. 權威值＝平台帳戶總覽欄位 `funds_heng_total_<yyyymmdd>`（取最新日期）；不存在才退回逐檔加總。
  2. 逐檔字典與權威值的差額**必須被點名**：只有在 snapshot 有 `funds_stale_notice` 記載該群組時才算
     「已解釋」；否則由呼叫端判為未記載的靜默漂移（fail-closed）。

消費者：run_daily.py（日報渲染行）、check_thresholds.py（④閉合＋日報行比對）。
"""
from __future__ import annotations

import re
from typing import Any

HENG_KEY_RE = re.compile(r"funds_heng_total_(\d{8})$")


def _grp(snap: dict, name: str) -> float:
    """funds_breakdown.<name> 逐檔加總（排除 note 等非金額鍵）。"""
    rows = ((snap.get("funds_breakdown") or {}).get(name) or {})
    return sum(float(v) for k, v in rows.items() if k != "note")


def heng_dict_sum(snap: dict) -> float:
    """鉅亨逐檔字典加總（一般申購＋自由Pay）＝「參考值」，可能停更。"""
    return _grp(snap, "一般申購") + _grp(snap, "自由Pay")


def heng_keys(snap: dict) -> list[str]:
    return sorted(k for k in snap if HENG_KEY_RE.fullmatch(str(k)))


def heng_total(snap: dict) -> float:
    """鉅亨權威市值：平台帳戶總覽（最新日期）優先，否則退回逐檔加總。"""
    keys = heng_keys(snap)
    if keys:
        return float(snap[keys[-1]])
    return heng_dict_sum(snap)


def heng_source(snap: dict) -> str:
    keys = heng_keys(snap)
    return keys[-1] if keys else "funds_breakdown 逐檔加總（無平台總覽欄位）"


def heng_explained(snap: dict) -> bool:
    """逐檔字典與權威值不一致時，是否已由 snapshot 記載原因（funds_stale_notice 指名自由Pay）。"""
    if abs(heng_dict_sum(snap) - heng_total(snap)) <= 1:
        return True
    return "自由Pay" in str(snap.get("funds_stale_notice") or "")


def heng_gap(snap: dict) -> float:
    return heng_dict_sum(snap) - heng_total(snap)
