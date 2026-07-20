"""穿透異常偵測 — 純腳本版（0 Token）
比對 assets 表近2天數據，單項變動 > 5% 推送警報"""

import sqlite3, json, os
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
db_path = BASE / "dragon_assets.db"
env_path = BASE / ".env"

TG_TOKEN = ""
TG_CHAT_ID = ""
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.startswith("TG_TOKEN="): TG_TOKEN = line.split("=",1)[1].strip()
        if line.startswith("TG_CHAT_ID="): TG_CHAT_ID = line.split("=",1)[1].strip()

if not db_path.exists():
    print("❌ db 不存在")
    exit(1)

db = sqlite3.connect(str(db_path))
db.row_factory = sqlite3.Row

# 取最近2天
rows = db.execute("SELECT * FROM assets ORDER BY date DESC LIMIT 2").fetchall()
if len(rows) < 2:
    print("⚠️ 數據不足2天，無法比對")
    db.close()
    exit(0)

today, yesterday = rows[0], rows[1]
alerts = []
fields = ["securities", "fund_market_value", "insurance", "bonds", "cash", "total_assets", "total_liabilities", "net_worth"]
labels = {"securities":"證券", "fund_market_value":"基金", "insurance":"保單", "bonds":"債券", "cash":"現金",
          "total_assets":"總資產", "total_liabilities":"總負債", "net_worth":"淨值"}

for f in fields:
    old_v = float(yesterday[f] or 0)
    new_v = float(today[f] or 0)
    if old_v == 0: continue
    change_pct = (new_v - old_v) / old_v * 100
    if abs(change_pct) > 5:
        emoji = "🔴" if change_pct < 0 else "🟢"
        alerts.append(f"  {emoji} {labels.get(f,f)}: {old_v:,.0f} → {new_v:,.0f} ({change_pct:+.1f}%)")

db.close()

if not alerts:
    msg = f"✅ 穿透正常（{today['date']}）— 各項變動 < 5%"
else:
    msg = f"⚠️ 穿透異常警報（{today['date']}）\n" + "\n".join(alerts)

print(msg)

if TG_TOKEN and TG_CHAT_ID:
    import requests
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      json={"chat_id": TG_CHAT_ID, "text": msg}, timeout=10)
    except Exception:
        pass
