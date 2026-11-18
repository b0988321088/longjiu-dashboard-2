#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""四頁期末總資產一致性檢查（fail-closed）

血淚 2026-11-18
    MTD 頁停在 11/17 口徑（26,434,546），與儀表板 25,970,345 差 464,201，
    而 sync_all 顯示全綠 —— 因為它的步驟清單根本沒有 build_mtd_report.py。
    使用者自己打開本月績效頁才發現。此後每次 sync_all 收尾都驗這四頁。

檢查對象（使用者會直接打開的頁面）
    1. index.html                    儀表板首頁
    2. daily_report_v2_<date>.html   當日日報
    3. mtd_data.json                 本月績效頁資料源
    4. performance_monthly.html      月報

基準：snapshot.total_assets（真值）；容差 1 元（浮點四捨五入）
任一頁找不到數字或超差 → exit 1（sync_all 失敗即停，不會帶著舊值上線）。

用法
    python tools/check_total_consistency.py                # 驗今天
    python tools/check_total_consistency.py --date 2026-11-18
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TOL = 1.0


def _num(s):
    return float(str(s).replace(",", "").strip())


def check(day: str):
    snap = json.load((BASE / "snapshot.json").open(encoding="utf-8"))
    truth = float(snap["total_assets"])
    rows = []

    # 1) 儀表板：文案「總資產 25,970,345 = 66.2% ...」
    p = BASE / "index.html"
    if p.exists():
        h = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"總資產\s*([\d,]+)\s*=", h)
        rows.append(("index.html", _num(m.group(1)) if m else None))
    else:
        rows.append(("index.html", None))

    # 2) 日報：表格列「<td>總資產</td><td>25,970,345.0 TWD</td>」
    p = BASE / f"daily_report_v2_{day}.html"
    if p.exists():
        h = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"<td>總資產</td><td>([\d,.]+)\s*TWD", h)
        rows.append((p.name, _num(m.group(1)) if m else None))
    else:
        rows.append((p.name, None))

    # 3) 本月績效資料源：total_assets.end
    p = BASE / "mtd_data.json"
    if p.exists():
        j = json.load(p.open(encoding="utf-8"))
        ta = j.get("total_assets") or {}
        rows.append((p.name, float(ta["end"]) if ta.get("end") is not None else None))
    else:
        rows.append((p.name, None))

    # 4) 月報：內嵌 JSON "balance":{"total_assets":25970345.0
    p = BASE / "performance_monthly.html"
    if p.exists():
        h = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'"balance"\s*:\s*\{\s*"total_assets"\s*:\s*([\d.]+)', h)
        rows.append((p.name, float(m.group(1)) if m else None))
    else:
        rows.append((p.name, None))

    bad = []
    print(f"基準 snapshot.total_assets = {truth:,.0f}（{day}）")
    for name, v in rows:
        if v is None:
            print(f"  ⚠️ {name}：找不到總資產（缺檔或格式改變）")
            bad.append(name)
        elif abs(v - truth) > TOL:
            print(f"  ❌ {name}：{v:,.0f}（差 {v - truth:+,.0f}）")
            bad.append(name)
        else:
            print(f"  ✅ {name}：{v:,.0f}")

    if bad:
        print(f"\n❌ 四頁總資產不一致（{len(bad)} 頁）：{'、'.join(bad)}")
        print("   → 重產這些頁後再交付；勿帶著舊值 push")
        return 1
    print(f"\n✅ 四頁總資產一致（{len(rows)}/{len(rows)}）")
    return 0


def main():
    day = date.today().isoformat()
    if "--date" in sys.argv:
        i = sys.argv.index("--date")
        if i + 1 < len(sys.argv):
            day = sys.argv[i + 1]
    return check(day)


if __name__ == "__main__":
    sys.exit(main())
