"""Hunter 情報 — 純腳本版（0 Token）
只抓 Yahoo Finance 即時數據，格式推送 Telegram"""

import json, requests
from datetime import date, datetime
from pathlib import Path
from logging_config import get_logger
logger = get_logger("hunter_intel")

BASE = Path(__file__).resolve().parent
env_path = Path.home() / "AppData/Local/hermes/.env"

TG_TOKEN = ""
TG_CHAT_ID = ""
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.startswith("TG_TOKEN="): TG_TOKEN = line.split("=",1)[1].strip()
        if line.startswith("TG_CHAT_ID="): TG_CHAT_ID = line.split("=",1)[1].strip()

def get_yf_market():
    """抓 Yahoo Finance 即時數據（2026-09-22 INC-239：改走 market_price 單一入口取前收）

    舊版用 `range=1d&interval=1d` 的 meta.chartPreviousClose 當前收 → Yahoo 對 ^TWII 給的
    previousClose 落後一整個交易日（9/22 回 47,180.80＝9/18，真前收 47,718.84），
    台股漲跌 47,800.17 從 +0.17% 被寫成 +1.31%，且這串會流進
    hunter_cache → compile_intel → daily_condensed_intel → 日報「情報重點」段落。
    """
    from market_price import fetch_snapshot
    symbols = {
        "台股加權": "^TWII", "台積電": "2330.TW", "費半": "^SOX",
        "道瓊": "^DJI", "納指": "^IXIC", "S&P500": "^GSPC",
    }
    results = {}
    for name, sym in symbols.items():
        try:
            s = fetch_snapshot(sym, timeout=10)
            if s and s.get("price") is not None and s.get("prev"):
                results[name] = f"{s['price']:,.2f} ({s['change_pct']:+.2f}%)"
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
