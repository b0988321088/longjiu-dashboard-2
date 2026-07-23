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
                prev = meta.get("chartPreviousClose", 0)
                cur = meta.get("regularMarketPrice", 0) or meta.get("chartPreviousClose", 0)
                if prev and cur:
                    chg = (cur - prev) / prev * 100
                    results[name] = f"{cur:,.2f} ({chg:+.2f}%)"
        except Exception:
            pass
    return results

market = get_yf_market()
intel_data = {
    "date": date.today().isoformat(),
    "timestamp": datetime.now().strftime("%H:%M"),
    "market_data": market
}
# Save to hunter_cache as JSON
cache_dir = BASE / "hunter_cache"
cache_dir.mkdir(exist_ok=True)
cache_file = cache_dir / f"market_intel_{date.today().isoformat()}.json"
cache_file.write_text(json.dumps(intel_data, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"Hunter intelligence data saved to {cache_file}")
