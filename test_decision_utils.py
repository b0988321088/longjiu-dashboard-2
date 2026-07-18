import argparse, json, os, re, sys, time
from datetime import datetime, timedelta, date
from pathlib import Path
def parse_defer_days(text):
    text = text.strip()
    # 中文
    if "下個月" in text or "下个月" in text:
        today = date.today()
        first_next = date(today.year + (1 if today.month == 12 else 0), (today.month % 12) + 1, 1)
        return (first_next - today).days
    if "下週" in text or "下星期" in text or "下周" in text:
        return 7
    if "明天" in text:
        return 1
    # 數字 + 天
    m = re.search(r"(\d+)\s*天", text)
    if m:
        return int(m.group(1))
    return 1
def defer_until(text):
    return (date.today() + timedelta(days=parse_defer_days(text))).isoformat()
print(f"Tomorrow: {defer_until('延后')}")
print(f"Next week: {defer_until('延后 下週')}")
print(f"Next month: {defer_until('延后 下個月')}")
sys.exit(0)