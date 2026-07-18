"""
決策日期解析工具（Calendar-Aware）
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional


def _next_monday(d: date) -> date:
    days_ahead = 7 - d.weekday()  # Monday=0, Sunday=6
    if days_ahead == 7:
        days_ahead = 0
    return d + timedelta(days=days_ahead)


def _first_of_next_month(d: date) -> date:
    y = d.year + (1 if d.month == 12 else 0)
    m = (d.month % 12) + 1
    return date(y, m, 1)


def parse_defer_days(text: str) -> int:
    text = text.strip()
    if "下個月" in text or "下个月" in text:
        return (_first_of_next_month(date.today()) - date.today()).days
    if "下週" in text or "下星期" in text or "下周" in text:
        return (_next_monday(date.today()) - date.today()).days
    if "明天" in text:
        return 1
    m = re.search(r"(\d+)\s*天", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*day", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 1


def defer_until(text: str) -> str:
    return (date.today() + timedelta(days=parse_defer_days(text))).isoformat()


# self-test
if __name__ == "__main__":
    tests = [
        ("延后", "default +1"),
        ("延后 3天", "3 days"),
        ("延后 明天", "tomorrow"),
        ("延后 下週", "next Monday"),
        ("延后 下個月", "next month"),
        ("延后0050下週賣出", "0050 next week"),
        ("延后 7 天", "7 days"),
    ]
    for t, label in tests:
        print(f"{label:20s} | input={t:20s} | remind_at={defer_until(t)}")
