#!/usr/bin/env python3
"""mb_income_tracker.py — MB 入帳自動追蹤（配息＋薪資）協調器

cron 07:10（no_agent，stdout 逐字送出）用。依序執行兩條互不相干的追蹤：
  ① `dividend_tracker.main()`  → 配息（ETF／基金實收；既有邏輯與輸出**完全不動**）
  ② `salary_tracker.run(apply=True)` → 台電薪資實收事實層（2026-10-11 新增）

輸出契約（避免每日噪音）：
  - 配息段：一律沿用 dividend_tracker 的原始 stdout（行為與改版前逐字相同）
  - 薪資段：**只有**「新寫入／WARN／契約失敗」才輸出；no-op 時完全靜默
  - 兩段皆無事 → stdout 為空（no_agent＝不發訊息）

界線：本檔只做順序與輸出彙整，不改任何口徑、不寫入模型層欄位
（monthly_salary／monthly_income／working_surplus 全程不動，見 salary_tracker 檔頭⑥）。
"""
from __future__ import annotations

import contextlib
import io
import sys

import dividend_tracker
import salary_tracker

# 薪資段「值得打擾使用者」的行（其餘如 ℹ️ no-op 一律靜默）
_INTERESTING = ("  ＋ ", "WARN", "[FAIL]", "已寫入")


def main() -> int:
    rc = 0
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            dividend_tracker.main()
        except SystemExit as e:                     # dividend_tracker 既有行為：直接結束
            rc = int(e.code or 0)
        except Exception as e:                      # 配息段失敗不得靜默
            print(f"[FAIL] 配息追蹤失敗：{type(e).__name__}: {e}")
            rc = 1
    div_text = out.getvalue().strip()

    sal = io.StringIO()
    with contextlib.redirect_stdout(sal):
        try:
            sal_rc = salary_tracker.run(apply=True)
        except Exception as e:
            print(f"[FAIL] 薪資追蹤失敗：{type(e).__name__}: {e}")
            sal_rc = 1
    sal_lines = [l for l in sal.getvalue().splitlines() if any(k in l for k in _INTERESTING)]

    if div_text:
        print(div_text)
    if sal_lines:
        print("💰 薪資自動帶入（MB 明細 → salary_records）")
        print("\n".join(sal_lines))
    if sal_rc:
        rc = sal_rc
    return rc


if __name__ == "__main__":
    sys.exit(main())
