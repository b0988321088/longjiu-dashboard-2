# -*- coding: utf-8 -*-
"""cash_need_90d_guard.py — 90 天現金需求（A 區）產物守門（純函式，可獨立測試）

背景（2026-10-09 使用者裁決：押標金未得標→不列入 90 天已確認需求、不預先辦理保證函）：
  原守門以「否定句附近出現 2,400,000」的正則判定，無法辨識否定語意，
  把**明示排除**的句子誤判為違規
  （實測 daily_report_v2_2026-10-09.html ⑥：「…未得標不屬 90 天已確認需求…」）。

  第一版修法曾加「語境」檢查（押標金附近需有排除詞），**實測同樣脆弱**：
  產物在多處合法語境提及押標金（決策卡清單、本週投資計劃、條件式事件），
  固定字元窗無法區分「提及」與「列為需求」→ 又製造假紅燈。
  依使用者裁定「使用數值與實際計算結果判斷，不再單靠否定句附近的 regex」，
  **移除所有散文式判定**，只保留可證偽的數值判定。

保留的判定（數值）：產物渲染出的 90 天需求分母（÷ 已確認 N）必須等於 A 區計算值。
  產物若把押標金併入需求，分母會變成 A+2,400,000 → 立即不符。
  這比原散文式更強：原式只在「碰巧鄰近」時觸發，且無法區分否定；本式直接比對計算結果，
  且「找不到渲染式」一律 FAIL（不得因找不到而默認通過）。
  搭配 check_dividend_caliber 既有的數值檢查（A 區＝固定月支出×3、不建立 B 區）形成完整覆蓋。
"""
from __future__ import annotations

import re

# 覆蓋率渲染式：「可動用 639,661 ÷ 已確認 477,630」
RENDERED_RE = re.compile(r"可動用\s*([\d,]+)\s*÷\s*已確認\s*([\d,]+)")


def to_amount(s: str) -> float:
    return float(str(s).replace(",", "").strip())


def parse_rendered_need(text: str) -> list[tuple[float, float]]:
    """取出 (可動用, 已確認需求) 數對。"""
    return [(to_amount(a), to_amount(b)) for a, b in RENDERED_RE.findall(text or "")]


def check_rendered_denominator(text: str, a_amount: float) -> tuple[bool, str]:
    """產物渲染的需求分母必須等於 A 區計算值（＝押標金未併入）。

    回傳 (ok, detail)。找不到任何渲染式視為 FAIL（無法以數值驗證 ≠ 通過）。
    """
    pairs = parse_rendered_need(text)
    if not pairs:
        return False, "找不到『可動用 X ÷ 已確認 Y』渲染式（無法以數值驗證）"
    dens = sorted({d for _, d in pairs})
    bad = [d for d in dens if abs(d - float(a_amount)) >= 1.0]
    return (not bad), f"分母={dens}｜A 區={a_amount:,.0f}" + ("（不符）" if bad else "")
