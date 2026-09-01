#!/usr/bin/env python3
"""儀表板同步檢查（2026-09-01 建立）：產出 index.html 後驗證無舊值/佔位符/月份寫死。
整合進 regenerate_report.py（產出後自動跑）；也可獨立執行：python check_dashboard_sync.py
失敗 exit 1（regenerate 會印警告），全過 exit 0。"""
import datetime
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
html = (BASE / "index.html").read_text(encoding="utf-8")
fails = []

# 1. 佔位符殘留（build_dashboard 未注入）
phs = sorted(set(re.findall(r"__[A-Z_]+__", html)))
if phs:
    fails.append(f"佔位符殘留: {phs}")

# 2. JS 月份寫死（讀 dividend_records/rent_received 的 key 寫死某月）
if re.search(r"\['2026-0\d'\]", html):
    fails.append("JS 月份寫死 (['2026-0X'] 殘留)")

# 3. 已知舊值殘留（非 data-k fallback 的裸舊值 = build 沒跑或 rep 漏）
OLD = [
    "753,388", "138,627", "102,469", "123,607", "243,434",
    "225,918", "799,612", "20260829", "20260821_1", "772,607",
    "08月現金流入", "系統時間：2026-08",
]
for v in OLD:
    for m in re.finditer(re.escape(v), html):
        ctx = html[max(0, m.start() - 80):m.start() + 80]
        if "data-k=" in ctx or "/*" in ctx or "--" in ctx:
            continue  # data-k fallback / 註解可接受
        fails.append(f"舊值殘留: {v} @ {m.start()}")
        break

# 4. 月度流入標題 = 當月
_ym = datetime.date.today().strftime("%Y-%m")
if f"{int(_ym[5:])}月現金流入檢對核實" not in html:
    fails.append("月度流入標題非當月")

# 5. 戰略區塊已注入（健康度/雷達/交易計畫/P0）
for kw in ["龍九健康度", "雷達更新", "本週交易計畫（動態）", "P0 戰略任務"]:
    if kw not in html:
        fails.append(f"戰略區塊缺失: {kw}")

# 6. 系統時間 JS 動態（非寫死日期）
if "sys-date" not in html:
    fails.append("系統時間非 JS 動態")

if fails:
    print("❌ 儀表板同步檢查失敗:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("✅ 儀表板同步檢查全過（無佔位符 / 月份寫死 / 舊值，戰略區塊已注入）")
