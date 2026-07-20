"""Hunter 情報 — 純腳本版（0 Token）
只抓 Yahoo Finance 即時數據，格式推送 Telegram"""

import json, os, requests, re
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
env_path = BASE / ".env"

TG_TOKEN = ""
TG_CHAT_ID = ""
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.startswith("TG_TOKEN="): TG_TOKEN = line.split("=",1)[1].strip()
        if line.startswith("TG_CHAT_ID="): TG_CHAT_ID = line.split("=",1)[1].strip()

def get_yf_market():
    """抓 Yahoo Finance 即時數據"""
    symbols = {
        "台股加權": "^TWII", "台積電": "2330.TW", "費半": "^SOX",
        "道瓊": "^DJI", "納指": "^IXIC", "S&P500": "^GSPC",
    }
    results = {}
    for name, sym in symbols.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1d"
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
                prev = meta.get("previousClose", 0)
                cur = meta.get("regularMarketPrice", 0) or meta.get("chartPreviousClose", 0)
                if prev and cur:
                    chg = (cur - prev) / prev * 100
                    results[name] = f"{cur:,.2f} ({chg:+.2f}%)"
        except Exception:
            pass
    return results

market = get_yf_market()
now = datetime.now().strftime("%H:%M")
lines = [f"📈 Hunter 情報 {date.today().isoformat()} {now}", ""]

if market:
    for k, v in market.items():
        lines.append(f"  {k}: {v}")
else:
    lines.append("  ⚠️ 無法取得市場數據")

msg = "\n".join(lines)
print(msg)

if TG_TOKEN and TG_CHAT_ID:
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      json={"chat_id": TG_CHAT_ID, "text": msg}, timeout=10)
    except Exception:
        pass
