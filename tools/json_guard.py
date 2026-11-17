#!/usr/bin/env python3
"""JSON 安全寫入（沿用原格式）＋ staged 整檔重排守門。

為什麼要這支（2026-11-17 實踩兩次）：
    snapshot.json 的原格式是 indent=1、檔尾無換行。被人用 json.dump(indent=2) 寫回，
    結果 9,749/9,746 行整檔重排 —— 真正的改動只有 3 個值，審查看不出來，13 段審查白花，
    diff 噪音也讓「有沒有改錯」無法人工複核。

用法：
    from json_guard import safe_json_write
    safe_json_write("snapshot.json", data)      # 自動偵測 indent／尾換行／中文轉義

    python tools/json_guard.py --check-staged    # pre-commit 用：偵測 staged 的整檔重排
    python tools/json_guard.py --probe <file>    # 印出偵測到的格式

守門規則（保守，避免誤擋產線）：
    1. 只看 *.json（含 .jsonl 不看，逐行 append 型）
    2. 只看「已存在於 HEAD」的檔案（新檔 removed=0 → 跳過）
    3. 只在 added+removed > 檔案行數 × 0.8 且檔案行數 ≥ 200 時才判違規
    4. commit message 含 [json-reflow-ok] 時放行（明確例外，留痕）
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def detect_format(text: str) -> dict:
    """從既有 JSON 文字推回寫入格式。找不到就退回 indent=1、無尾換行、不轉義中文。"""
    indent = None
    m = re.search(r"\n( +)\S", text)
    if m:
        indent = len(m.group(1))
    elif re.search(r"\n\t\S", text):
        indent = "\t"
    ascii_escaped = "\\u" in text and not re.search(r"[\u4e00-\u9fff]", text)
    return {
        "indent": indent if indent is not None else 1,
        "trailing_newline": text.endswith("\n"),
        "ensure_ascii": ascii_escaped,
    }


def safe_json_write(path: str | Path, obj, *, create_format: dict | None = None) -> dict:
    """以原檔格式寫回；檔案不存在時用 create_format（預設 indent=1、無尾換行）。

    回傳實際使用的格式，方便呼叫端回報「格式沿用/新建」。
    """
    p = Path(path)
    if not p.is_absolute():
        p = REPO / p
    if p.exists():
        fmt = detect_format(p.read_text(encoding="utf-8", errors="replace"))
    else:
        fmt = dict(create_format or {"indent": 1, "trailing_newline": False, "ensure_ascii": False})

    text = json.dumps(obj, ensure_ascii=fmt["ensure_ascii"], indent=fmt["indent"])
    if fmt["trailing_newline"]:
        text += "\n"
    p.write_text(text, encoding="utf-8", newline="\n")
    return fmt


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(REPO), capture_output=True)
    return r.stdout.decode("utf-8", errors="replace")


def check_staged(threshold: float = 0.8, min_lines: int = 200) -> tuple[int, list[str]]:
    """回傳 (rc, 違規清單)。rc=1 代表疑似整檔重排。"""
    numstat = _git("diff", "--cached", "--numstat", "--", "*.json")
    msg = _git("log", "-1", "--format=%B")
    allow = "[json-reflow-ok]" in msg

    bad: list[str] = []
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, removed, path = parts[0], parts[1], parts[2]
        if added == "-" or removed == "-":      # 二進位
            continue
        if removed == "0":                      # 新檔
            continue
        total_txt = _git("show", f":{path}")
        total = max(1, total_txt.count("\n"))
        if total < min_lines:
            continue
        churn = int(added) + int(removed)
        if churn > total * threshold:
            bad.append(f"{path}: +{added}/-{removed} 行（檔案僅 {total} 行）→ 疑似整檔重排")

    if bad:
        print("❌ 偵測到 JSON 整檔重排（真正的改動會被 diff 噪音淹沒）：", file=sys.stderr)
        for b in bad:
            print(f"   · {b}", file=sys.stderr)
        print("   修正：改用 tools/json_guard.py 的 safe_json_write() 重寫，"
              "或確認整檔重排是刻意的（commit message 加 [json-reflow-ok]）。", file=sys.stderr)
        if allow:
            print("   ⚠️ 已偵測 [json-reflow-ok] → 放行（留痕於 commit message）", file=sys.stderr)
            return 0, bad
        return 1, bad
    return 0, bad


def main() -> int:
    ap = argparse.ArgumentParser(description="JSON 安全寫入與整檔重排守門")
    ap.add_argument("--check-staged", action="store_true", help="pre-commit 用：檢查 staged 的 *.json")
    ap.add_argument("--probe", metavar="FILE", help="印出該檔偵測到的格式（不寫入）")
    ap.add_argument("--threshold", type=float, default=0.8, help="改動行數占比門檻（預設 0.8）")
    ap.add_argument("--min-lines", type=int, default=200, help="小於此行數的檔不判（預設 200）")
    a = ap.parse_args()

    if a.probe:
        p = Path(a.probe)
        if not p.is_absolute():
            p = REPO / p
        print(f"{p.name}: {detect_format(p.read_text(encoding='utf-8', errors='replace'))}")
        return 0

    if a.check_staged:
        rc, bad = check_staged(a.threshold, a.min_lines)
        if rc == 0 and not bad:
            pass  # 靜默：pre-commit 無事不打字
        return rc

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
