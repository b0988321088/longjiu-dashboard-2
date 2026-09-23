#!/usr/bin/env python3
"""報告「空值」守門：金額欄與佔比不得一為 0、一為正。

2026-09-23 INC-244 新增。背景：日報穿透表「└ 科技股／└ 非科技」金額欄印 **0 TWD**，
但同一列的佔比正常（15.3%／24.2%）—— 因為 `update_data.py` 重建 penetration 時只把
子維度補回 `actual_pct`，`actual_twd` 被丟掉，renderer 用 `.get(key, 0)` 靜默印 0。

第 1 類稽核（舊值殘留）掃不到這種「**空值**」症狀：舊值掃描是找「已知的舊數字」，
而被丟掉的鍵根本沒有數字可掃。故另立不變式：

> 佔比 = 金額 ÷ 總額 → 金額為 0 時，佔比不可能 > 0。

反向（金額 > 0 但佔比 0.0%）刻意**不列問題**：小額部位的損益 rounding 就會這樣（假陽性）。

用法：
    python check_report_zero_values.py            # 掃今日報告（機讀輸出，供稽核引用）
    python check_report_zero_values.py --date 2026-09-23
"""
from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

BASE = Path.home() / "Desktop" / "longjiu_system"

# 金額為 0：必須是獨立數字（前一字元不得是數字/逗號/小數點），否則 "80,100 TWD" 會被誤判（實測）
_MONEY_ZERO = re.compile(r"(?:(?:NT\$|\$)\s*0(?:\.0+)?|(?<![\d.,])0(?:\.0+)?\s*(?:TWD|元|台幣))")
# 儲存格開頭就是正的佔比：0% / 0.0% 不算（與金額 0 一致，放行）
_PCT_CELL = re.compile(r"^\s*([1-9]\d*(?:\.\d+)?)\s*%")
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)


def _cells(row_html: str) -> list[str]:
    out = []
    for c in _CELL.findall(row_html):
        txt = re.sub(r"<[^>]+>", " ", c).replace("&nbsp;", " ")
        out.append(re.sub(r"\s+", " ", txt).strip())
    return out


def scan_file(path: Path) -> list[str]:
    """回傳該檔的違規列描述（空 list = 乾淨）。

    判定：**「金額 0」儲存格的下一格就是正的佔比**。用相鄰格而非整列，是因為穿透表
    同一列有「金額／佔比／目標」多個百分比欄 —— 整列比對會把「0 TWD＋目標 3%」誤判成違規
    （2026-09-23 自測案例抓到）。已知限制：若表格欄序不是「金額,佔比」相鄰則不適用。
    """
    try:
        txt = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    out: list[str] = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", txt, re.S):
        cs = _cells(row)
        for i, c in enumerate(cs[:-1]):
            if _MONEY_ZERO.search(c) and _PCT_CELL.match(cs[i + 1]):
                out.append(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", row)).strip()[:110])
                break
    return out


def report_files(date: str | None = None, base: Path = BASE) -> list[Path]:
    t = date or datetime.date.today().isoformat()
    names = [
        f"daily_report_v2_{t}.html",
        "index.html",
        f"penetration_report_{t}.html",
        f"asset_diff_{t}.html",
        f"rebalance_dashboard_{t}.html",
        "mtd_performance.html",
    ]
    return [base / n for n in names if (base / n).exists()]


def scan(date: str | None = None, base: Path = BASE) -> list[str]:
    """回傳 ['<檔名>：<列片段>', ...]；空 list = 全部乾淨。"""
    hits: list[str] = []
    for p in report_files(date, base):
        for row in scan_file(p):
            hits.append(f"{p.name}：{row}")
    return hits


def main() -> int:
    date = None
    if "--date" in sys.argv:
        date = sys.argv[sys.argv.index("--date") + 1]
    hits = scan(date)
    if hits:
        for h in hits:
            print(f"❌ {h}")
        print(f"\n❌ 報告金額欄 0 但佔比 > 0：{len(hits)} 列（穿透/口徑子維度鍵疑似被重建流程丟掉）")
        return 1
    print("✅ 報告無『金額 0 ＋ 佔比 > 0』矛盾列")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
