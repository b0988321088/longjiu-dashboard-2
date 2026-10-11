#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""label_mask.py — 保單標籤欄位正規化（受限、比對層專用）

為什麼有這支（事件 INC-2026-10-11）：
    Task 1+2 封版契約的 A/B 檢查是「封版基準（2d1b9ed2^）產出 vs 現行程式產出」逐位元比對。
    2026-10-10 的 no-hardcode 批次（1fd8ec42）把 `build_investment_performance.py` 的
    第一金列標籤由「數值代號」改成「遮罩形式」→ 逐位元不符 → Task 1+2 FAIL 2 項 →
    封版契約 F1 FAIL → 晨間產線整條被擋（10/11 07:00 rc=1）。

設計原則（使用者 2026-10-11 裁決「受限契約正規化」）：
    ① 只正規化**明確核准的標籤欄位**：政策標籤「第一金 FJ<2 碼>」與行內註記「vs FJ<2 碼>」。
       其餘任何字元、任何行、任何頁面差異一律不得被忽略。
    ② 只接受**兩種合法型態**：數值型 `FJ` + 兩位數字，或已遮罩 `FJXX`；兩者一律視為等價。
       政策方向＝標籤遮罩（公開輸出不宜出現代號），但**本模組不主張全站已遮罩**：現況仍有
       未遮罩字面存在於其他產物（見 has_unmasked_label 與 PEND 卡），本模組只負責「比對層
       把兩種型態視為等價」。其他形態（如 `FJAB`）**不**正規化 → 仍會被判為差異。
    ③ 純函式、不改寫任何檔案；正規化只發生在比對層（A/B 比較的兩側同時套用，語意對稱）。
    ④ 不得用於放寬其他斷言：本模組沒有任何「略過檔案／略過整段」的能力。

邊界（刻意可接受）：標籤代號本身不納入逐位元比對 —— 政策方向是公開輸出不宜出現代號，代號不應成為
    契約的比對對象。**但這不等於「全站已遮罩」**：現況 mtd_performance.html（來源 build_mtd_report.py）
    與已提交（尚未重產）的 investment_performance.html 仍含未遮罩字面，見 PEND-20261011-07；因此本模組
    的正規化缺口另由 tools/label_mask.has_unmasked_label() 的**正向斷言**補回（bip 頁），而非靠「已遮罩」
    這個假設。此界線由 tools/test_label_mask.py 的 T7/T17 明文釘住，避免日後被當成漏洞利用。
"""
from __future__ import annotations

import re

# 只認這兩個錨點；其後僅接「兩位數字」或「XX」→ 其餘不動
LABEL_RE = re.compile(r"(第一金 FJ|vs FJ)(?:[0-9]{2}|XX)")
MASKED = "XX"


def normalize(text: str) -> str:
    """把核准標籤欄位的代號一律正規化為遮罩形式（FJXX）。純函式、冪等。"""
    if not text:
        return text
    return LABEL_RE.sub(lambda m: m.group(1) + MASKED, text)


def normalize_bytes(data: bytes) -> bytes:
    """bytes 版：UTF-8 可解則解碼後正規化；不可解則原樣回傳（呼叫端會退回位元比對）。"""
    try:
        return normalize(data.decode("utf-8")).encode("utf-8")
    except UnicodeDecodeError:
        return data


# 反向斷言用：偵測「未遮罩」的核准標籤（＝遮罩回歸）
UNMASKED_LABEL_RE = re.compile(r"(第一金 FJ|vs FJ)[0-9]{2}")


def has_unmasked_label(text: str) -> bool:
    """正向遮罩斷言：True 表示文字中仍有『未遮罩』的核准標籤代號。

    為什麼需要（2026-10-11 獨立 CIO 審查 required_fix #1）：
        A/B 改為「正規化後相同」等於放棄比對這兩個欄位；若程式哪天又輸出未遮罩代號（re-leak），
        光靠 A/B 再也偵測不到。本函式把那個缺口用**另一條獨立斷言**補回來：
        出貨頁面必須是遮罩型（第一金 FJXX／vs FJXX），出現數值型即視為遮罩回歸。
        （兩側皆為數值型時 A/B 相同、但本斷言仍會 FAIL → 補回真錯攔截能力。）
    """
    return bool(text) and UNMASKED_LABEL_RE.search(text) is not None


def same_after_mask(a: bytes | str, b: bytes | str) -> bool:
    """A/B 比較入口：只有「正規化後完全相同」才算相同。

    - 傳入 bytes → 以 UTF-8 解碼後比對（解不開則退回原始位元比對，fail-closed）
    - 任何非標籤欄位的差異都會讓本函式回 False（由 test_label_mask.py T3/T4/T5 釘住）
    """
    if isinstance(a, bytes) and isinstance(b, bytes):
        try:
            a = a.decode("utf-8")
            b = b.decode("utf-8")
        except UnicodeDecodeError:
            return a == b
    elif isinstance(a, bytes):
        a = a.decode("utf-8", "replace")
    elif isinstance(b, bytes):
        b = b.decode("utf-8", "replace")
    return normalize(a) == normalize(b)
