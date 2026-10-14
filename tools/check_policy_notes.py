#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""TD-20261014-01 回歸檢查：政策文字不得殘留「未經核實的具體市場數值」。

背景：radar_state.json 的 policy_notes 是人工維護文字；2026-10-14 曾因內含過期市場數值
（10Y 月動能 +6.2%、USD/TWD 31.76、COT 淨多單舊值）與當日 signals 矛盾，導致 CIO 審查 REJECT。
市場數值一律改由 institutional_flow.render_policy_live() 當日注入；政策文字只保留
「政策事件」與「解讀」。

判準：只抓「市場真值類」數值。政策事件本身的事實數值（FOMC 升息碼數、利率區間、日期、
基金成分結構比例如 48-55%、標的代號）不在此列，避免誤判。

用法：python tools/check_policy_notes.py [--state radar_state.json]
      退出碼 0 = PASS；1 = 發現殘留；2 = 檔案／結構錯誤
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MARKET_PATTERNS = [
    (r"10Y[^\n]{0,10}月動能[^\n]{0,4}[-+]?\d", "10Y 月動能具體值"),
    (r"美債10年[^\n]{0,8}殖利率?\s*[-+]?\d+\.?\d*\s*%", "10Y 殖利率具體值"),
    (r"USD\s*/\s*TW[A-Za-z]*\s*[-+]?\d+\.?\d*", "USD/TWD 具體匯率"),
    (r"美元\s*[/／]\s*台幣\s*\d+\.?\d*", "USD/TWD 具體匯率（中文）"),
    (r"淨多單\s*[-+]?\d{2,}", "COT 淨多單具體值"),
    (r"債券桶[^\n]{0,8}\d+\.?\d*\s*%", "債券桶具體比重"),
    (r"週[變減增]化?[^\n]{0,4}[-+]?\d+\.?\d*\s*%", "週變化具體值"),
]

# 不列入檢查（避免誤判）：
#   - 政策事件事實：升息碼數、利率區間（3.75-4.00%）、日期、標的代號、基金成分結構比例（48-55%）。
#   - **已發生且附日期的歷史市場事件**（例：「9/18 台股開 46,449.56、站上 47,000」）：
#     這是歷史事實、不會過期，不屬於「應反映當日的市場真值」，故不視為違規。
#     反之，「10Y 月動能 +6.2%」「USD/TWD 31.76」「COT 淨多單 230,338」這類
#     **有當日真值可對照**的指標才是本檢查的標的。


def iter_texts(pn: dict):
    for k, v in (pn or {}).items():
        if isinstance(v, str):
            yield k, v
        elif isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, str):
                    yield f"{k}.{kk}", vv


def scan(pn: dict):
    hits = []
    for where, text in iter_texts(pn):
        for pat, label in MARKET_PATTERNS:
            for m in re.finditer(pat, text):
                hits.append((where, label, m.group(0)))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="radar_state.json")
    a = ap.parse_args()
    p = Path(a.state)
    if not p.exists():
        print(f"❌ 找不到 {p}")
        return 2
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ {p} 解析失敗：{e}")
        return 2

    pn = d.get("policy_notes")
    if not isinstance(pn, dict) or not pn:
        print("⚠️ 無 policy_notes（視為無此風險）→ PASS")
        return 0

    hits = scan(pn)
    if hits:
        print(f"❌ 政策文字殘留具體市場數值（{len(hits)} 處）— 應改由 render_policy_live() 當日注入：")
        for where, label, got in hits:
            print(f"   - [{where}] {label}：{got!r}")
        return 1

    print("✅ PASS：政策文字無具體市場數值殘留（市場數值一律由程式當日注入）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
