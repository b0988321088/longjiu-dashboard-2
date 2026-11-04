#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""account_floors.py — 帳戶安全線的「外部資格門檻」單一來源（2026-11-04 使用者裁示）

口徑沿革
--------
2026-09-28：房貸扣款行安全線＝「自身房貸月繳×3」（國泰＝大義街、永豐＝洲際W）。
2026-11-04：使用者裁示 **永豐需維持「大戶」資格，帳戶底線 300,000** →
            永豐安全線改為 max(房貸月繳×3, 大戶門檻)。

為什麼門檻放常數、不放 snapshot
------------------------------
大戶門檻是銀行方案的**外部資格條件**，不是資產／現金流真值；snapshot 每個欄位都必須
能被真值來源（截圖／MoneyBook）驗證，門檻沒有這種來源，硬塞進 snapshot 反而製造
「看起來是真值、實際無法驗證」的假欄位。故獨立成常數模組，由所有顯示／告警層共用。

同值副本（無法 import 的位置）
-----------------------------
`index_template.html` 的 JS（瀏覽器端即時渲染）無法 import Python，該處以同名常數
`YF_DAWHO_FLOOR = 300000` 對齊；**改門檻時兩處必須同步**，並重跑 build_dashboard.py。
"""
from __future__ import annotations

# 永豐「大戶」資格帳戶底線（外部資格條件常數；不隨房貸月繳變動）
YONG_FENG_DAWHO_FLOOR = 300_000


def yongfeng_safe_line(monthly_x3) -> float:
    """永豐安全線＝max(房貸月繳×3, 大戶資格門檻)。

    monthly_x3 不可解析／非數值 → 以 0 計，此時安全線＝門檻（絕不退成 0，
    否則「餘額 < 門檻」會誤判成達標）。
    """
    try:
        base = float(monthly_x3)
    except (TypeError, ValueError):
        base = 0.0
    if base != base or base in (float("inf"), float("-inf")):   # NaN / Inf
        base = 0.0
    return max(base, float(YONG_FENG_DAWHO_FLOOR))
