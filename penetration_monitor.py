"""穿透異常偵測 — 純腳本版（0 Token）
比對 assets 表近2天數據，單項變動 > 5% 推送警報"""

import sqlite3, json, os
from datetime import date
from pathlib import Path
from logging_config import get_logger
logger = get_logger("penetration_monitor")

BASE = Path(r"C:\Users\bot\Desktop\longjiu_system")  # 2026-08-17 修正：固定指向 repo 真值 DB（原 __file__ parent → cron 讀 scripts 舊副本 8/10 → 重複發假警報）
db_path = BASE / "dragon_assets.db"
env_path = Path.home() / "AppData/Local/hermes/.env"

TG_TOKEN = ""
TG_CHAT_ID = ""
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.startswith("TG_TOKEN="): TG_TOKEN = line.split("=",1)[1].strip()
        if line.startswith("TG_CHAT_ID="): TG_CHAT_ID = line.split("=",1)[1].strip()

if not db_path.exists():
    logger.error("❌ db 不存在")
    exit(1)

db = sqlite3.connect(str(db_path))
db.row_factory = sqlite3.Row

# 取最近2天
rows = db.execute("SELECT * FROM assets ORDER BY date DESC LIMIT 2").fetchall()
if len(rows) < 2:
    logger.warning("⚠️ 數據不足2天，無法比對")
    db.close()
    exit(0)

today, yesterday = rows[0], rows[1]
alerts = []
fields = ["securities", "funds", "insurance", "bonds", "cash_total", "total_assets"]
labels = {"securities":"證券", "funds":"基金", "insurance":"保單", "bonds":"債券", "cash_total":"現金",
          "total_assets":"總資產"}

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
    # 2026-09-03 修正：cron 環境無 requests → 改 stdlib urllib，任何直譯器可跑
    try:
        import urllib.request
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data=json.dumps({"chat_id": TG_CHAT_ID, "text": msg}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass
