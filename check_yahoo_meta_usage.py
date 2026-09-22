#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_yahoo_meta_usage.py — 防止「前收欄位」地雷復發（2026-09-22，INC-239 家族）

為什麼要有這支：
  Yahoo chart API 的 `meta.previousClose` / `meta.chartPreviousClose` **不是真值** ——
  - INC-171（2026-09-13）：range=5d/1mo 的 chartPreviousClose 是「區間起點前」的收盤
    （≈5 日／1 月前）→ 漲跌% 被算成「一週漲跌」。
  - INC-239（2026-09-22）：改讀 previousClose 後仍然錯 —— ^TWII 回 47,180.80（＝9/18 收盤），
    真前收 47,718.84 → 台股 +0.17% 被寫成 +1.31%，並流進日報第 3/4 章與情報重點。
  同一個欄位 9 天內修兩次都還是錯 → 用「機械檢查」擋，不靠記憶。

判準：**前收一律由日線 (timestamp, close) 對齊推得**（`market_price.fetch_snapshot` / `fetch_bars`），
      任何檔案（除 market_price.py 本身）只要「真的在取值」即違規。

實作：用 `ast` 掃「屬性存取／下標／.get() 字串鍵」，**不看說明文字**（docstring/註解提到不會誤報）。

用法：
    python check_yahoo_meta_usage.py            # 檢查版控中的 .py（git ls-files）
    python check_yahoo_meta_usage.py --all      # 連未版控的 .py 也掃
離開碼：0 = 乾淨；1 = 有違規（交付閘門可據此擋下）
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ALLOW = {"market_price.py"}                      # 唯一允許解析 meta 的地方（已用日線對齊）
FORBIDDEN = {"previousClose", "chartPreviousClose"}
HINT = ("改用 market_price.fetch_snapshot()（今值/前收/漲跌%）"
        "或 market_price.fetch_bars()（動能/相對強弱序列）")


def _tracked() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "*.py"], cwd=BASE, capture_output=True,
                             text=True, encoding="utf-8", timeout=60).stdout
        return [BASE / f for f in out.splitlines() if f.endswith(".py") and (BASE / f).exists()]
    except Exception:  # noqa: BLE001
        return sorted(BASE.glob("*.py"))


def _scan(path: Path) -> list[tuple[int, str]]:
    """回傳 [(行號, 命中摘要)]；只認真的取值（attribute / subscript / .get()）。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN:
            hits.append((node.lineno, f".{node.attr}"))
        elif isinstance(node, ast.Subscript):
            sl = node.slice
            if isinstance(sl, ast.Constant) and sl.value in FORBIDDEN:
                hits.append((node.lineno, f'["{sl.value}"]'))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get" and node.args:
            a0 = node.args[0]
            if isinstance(a0, ast.Constant) and a0.value in FORBIDDEN:
                hits.append((node.lineno, f'.get("{a0.value}")'))
    return hits


def main() -> int:
    files = sorted(BASE.rglob("*.py")) if "--all" in sys.argv else _tracked()
    bad: list[tuple[str, int, str]] = []
    for f in files:
        if f.name in ALLOW:
            continue
        for ln, what in _scan(f):
            bad.append((str(f.relative_to(BASE)), ln, what))
    if bad:
        print(f"❌ 發現 {len(bad)} 處使用 Yahoo meta 前收欄位（唯一真值來源＝日線 timestamp 對齊）：")
        for f, ln, what in bad:
            print(f"   {f}:{ln}  {what}")
        print(f"   修法：{HINT}")
        print("   例外：market_price.py（單一入口，已用日線對齊）。")
        return 1
    print(f"✅ 無 meta 前收欄位使用（掃 {len(files)} 支 .py；唯一入口 market_price.py）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
