"""
決策日期解析工具
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, date
from typing import Optional


def parse_defer_days(text: str) -> int:
    text = text.strip()
    # 明天下週下個月
    if "下個月" in text or "下個月" in text:
        today = date.today()
        first_next = date(today.year + (1 if today.month == 12 else 0), (today.month % 12) + 1, 1)
        return (first_next - today).days
    if "下週" in text or "下星期" in text:
        return 7
    if "明天" in text:
        return 1
    # 數字 + 天
    m = re.search(r"(\d+)\s*天", text)
    if m:
        return int(m.group(1))
    # 數字 + day
    m = re.search(r"(\d+)\s*day", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 1  # 預設


def defer_until(text: str) -> Optional[str]:
    days = parse_defer_days(text)
    return (date.today() + timedelta(days=days)).isoformat()
