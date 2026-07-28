"""配息入帳提醒 — 從 schedule_events.json 檢查今明後天有無配息/T+4事件"""
import json
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
EVENTS = BASE / "schedule_events.json"

if not EVENTS.exists():
    print("⚠️ schedule_events.json 不存在")
    exit(0)

events = json.loads(EVENTS.read_text(encoding="utf-8"))
today = date.today()
window = [today, today + timedelta(1), today + timedelta(2)]

alerts = []
for e in events:
    try:
        d = e["date"]
        if d == "待處理":
            continue
        ed = date.fromisoformat(d)
        if ed in window and ("配息" in e.get("item", "") or "T+4" in e.get("item", "") or "股息" in e.get("item", "")):
            alerts.append(f"  {d} — {e['item']} ({e.get('status','')})")
    except:
        continue

if alerts:
    print(f"📅 今明後天配息/事件提醒 ({today}):")
    print("\n".join(alerts))
else:
    print(f"✅ 今明後天無配息/事件 ({today})")
