"""配息入帳提醒 — 比對 relay_calendar.md 檢查今明後天有無配息/T+4"""
import re
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
CAL = BASE / "relay_calendar.md"

if not CAL.exists():
    print("⚠️ relay_calendar.md 不存在")
    exit(0)

text = CAL.read_text(encoding="utf-8")
today = date.today()
today_md = f"{today.month}/{today.day}"
tomorrow_md = f"{(today+timedelta(1)).month}/{(today+timedelta(1)).day}"
day3_md = f"{(today+timedelta(2)).month}/{(today+timedelta(2)).day}"

alerts = []
for line in text.splitlines():
    if "|" not in line or line.startswith("| 基金") or line.startswith("|---"):
        continue
    cells = [c.strip() for c in line.split("|") if c.strip()]
    if len(cells) >= 3:
        name = cells[0]
        ex = re.sub(r'\(.*?\)', '', cells[1]).strip()
        t4 = re.sub(r'\(.*?\)', '', cells[2]).strip()
        for label, date_str in [("除息日", ex), ("T+4截止", t4)]:
            if date_str in (today_md, tomorrow_md, day3_md):
                day_label = "今天" if date_str == today_md else ("明天" if date_str == tomorrow_md else "後天")
                alerts.append(f"🔔 {name} {label}: {date_str}（{day_label}）")

if alerts:
    print("📌 近3日配息提醒：")
    for a in alerts:
        print(f"  {a}")
else:
    print("✅ 近3日無配息行程")
