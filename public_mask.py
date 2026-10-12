# -*- coding: utf-8 -*-
"""public_mask.py — 公開面（Pages／radar）敏感資訊遮蔽：唯一實作

2026-10-12 使用者裁決（資安處置方向）：**保留憑證、不撤銷**；優先清理公開資料。
本模組只做「輸出（渲染）時遮蔽」，不動任何真值、不改 snapshot/DB：
  ① 帳號標識：002***75、007-0099804310022717 之類 → 一律 •••
  ② 行庫餘額／安全線：屬 4 類敏感項（帳號、餘額、資產分母）→ 由呼叫端對應 key 遮蔽為 ●●●
  ③ 資產分母（radar fed.total_assets）→ 不落地、不輸出
設計原則：遮蔽規則**集中一處**、有正反例測試；真值層與內部報告不受影響。
"""
from __future__ import annotations

import re

MASK = "•••"
AMOUNT_MASK = "●●●"

# 行庫水位相關的 data-k 鍵（公開頁不得顯示絕對金額；狀態色與門檻比較仍保留）
BANK_KEYS = frozenset({
    "yushan", "fubon", "cathay", "cathay_d1", "cathay_d2", "taiwan", "sinopac", "dawho", "shizheng",
    "richart_sub", "wenxin", "richart_gen", "card_sum", "other_sum",
    "safe_line", "safe_line_cathay", "safe_line_sinopac", "cathay_loan", "sinopac_loan",
})

# 帳號樣式（僅遮罩識別碼本身，不碰金額）
_ACC = (
    re.compile(r"\b\d{3}\*{2,}\d{2,4}\b"),                 # 002***75
    re.compile(r"\b\d{3}-\d{6,20}\b"),                          # 007-0099804310022717
    re.compile(r"\b\d{10,16}\b(?=\s*(?:帳戶|帳號|acct))"),      # 純數字帳號（需上下文）
)
_SAFE = re.compile(r"安全線：\s*[\d,]+")
_INTERNAL_LINE = "內部門檻（不公開）"


def mask_accounts(text: str) -> str:
    if not text:
        return text
    out = text
    for rx in _ACC:
        out = rx.sub(MASK, out)
    return out


def mask_safety_lines(text: str) -> str:
    """『安全線：40,000』→『安全線：內部門檻（不公開）』（門檻值本身亦屬敏感）。"""
    if not text:
        return text
    return _SAFE.sub(f"安全線：{_INTERNAL_LINE}", text)


def is_bank_key(key: str) -> bool:
    return key in BANK_KEYS


def display_value(key: str, value) -> str:
    """公開頁顯示值：行庫類一律 ●●●；其餘交回呼叫端格式化。"""
    return AMOUNT_MASK if is_bank_key(key) else None


def scrub(text: str) -> str:
    """最終輸出前的最後一道：遮罩帳號與安全線門檻。"""
    return mask_safety_lines(mask_accounts(text))
