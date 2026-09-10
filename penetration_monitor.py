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

# 已知事件（預期變動）登錄檔 — 命中者不視為異常（2026-09-10 加，避免 MMF 在途/回補誤報）
KNOWN_FILE = BASE / "asset_event_exclusions.json"
_known_events = []
if KNOWN_FILE.exists():
    try:
        _known_events = json.loads(KNOWN_FILE.read_text(encoding="utf-8"))
    except Exception as _e:
        logger.warning(f"known events load failed: {_e}")


def _matched_event(_d, _field, _delta):
    """回傳命中的已知事件（同日期+同欄位+delta 誤差 <5% 或 <1000）"""
    for _ev in _known_events:
        if str(_ev.get("date")) != str(_d) or _ev.get("field") != _field:
            continue
        _exp = float(_ev.get("delta", 0) or 0)
        if _exp == 0:
            continue
        if abs(_delta - _exp) <= max(abs(_exp) * 0.05, 1000):
            return _ev
    return None


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
_filtered = []
fields = ["securities", "funds", "insurance", "bonds", "cash_total", "total_assets"]
labels = {"securities":"證券", "funds":"基金", "insurance":"保單", "bonds":"債券", "cash_total":"現金",
          "total_assets":"總資產"}

for f in fields:
    old_v = float(yesterday[f] or 0)
    new_v = float(today[f] or 0)
    if old_v == 0: continue
    delta = new_v - old_v
    change_pct = delta / old_v * 100
    if abs(change_pct) > 5:
        _ev = _matched_event(today["date"], f, delta)
        if _ev:
            _filtered.append(f"  ℹ️ {labels.get(f,f)}: {old_v:,.0f} → {new_v:,.0f}（已知事件：{_ev.get('note','')}）")
            continue
        emoji = "🔴" if change_pct < 0 else "🟢"
        alerts.append(f"  {emoji} {labels.get(f,f)}: {old_v:,.0f} → {new_v:,.0f} ({change_pct:+.1f}%)")

db.close()

if alerts:
    msg = f"⚠️ 穿透異常警報（{today['date']}）\n" + "\n".join(alerts)
    if _filtered:
        msg += "\n（另已排除已知事件：" + str(len(_filtered)) + " 項）"
    print(msg)
elif _filtered:
    # 全部變動皆為已登錄的預期事件 → 完全靜默（僅寫本機 log 檔，不進 stdout/不推播）
    try:
        with open(BASE / "penetration_monitor.log", "a", encoding="utf-8") as _lf:
            _lf.write(f"[{date.today().isoformat()}] 已知事件變動已排除：" +
                      " | ".join(x.strip() for x in _filtered) + "\n")
    except Exception:
        pass
else:
    print(f"✅ 穿透正常（{today['date']}）— 各項變動 < 5%")

# 移除 TG_TOKEN and TG_CHAT_ID 區塊，讓 cronjob 處理投遞
