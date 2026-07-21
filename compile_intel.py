"""龍九情報彙整 — 將所有 intel 來源壓進 market_intel 表"""
import sqlite3, json, re, glob
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
today = date.today().isoformat()

def compile_intel(force_refresh: bool = False) -> dict:
    """彙整所有情報來源 → market_intel 表，回傳今日彙總 dict"""
    db = sqlite3.connect(str(BASE / "dragon_assets.db"))
    
    # 掃 hunter_logs
    txts = sorted(glob.glob(str(BASE / "hunter_logs" / f"intel_{today.replace('-','')}_*.txt")))
    signals = {"sell": [], "buy": []}
    for f in txts:
        try:
            text = Path(f).read_text("utf-8", errors="ignore")
            for line in text.splitlines():
                if any(k in line for k in ["賣出","賣超","大跌","跌破"]): signals["sell"].append(line.strip())
                if any(k in line for k in ["買進","買超","大漲"]): signals["buy"].append(line.strip())
        except: pass
    
    # 從 snapshot 取市場數據
    snap = json.loads((BASE / "snapshot.json").read_text("utf-8"))
    mkt = snap.get("market", {})
    
    # 從 daily_analysis.json 取補充
    analysis = {}
    da_path = BASE / "daily_analysis.json"
    if da_path.exists():
        try: analysis = json.loads(da_path.read_text("utf-8"))
        except: pass
    
    # 清理當日舊資料
    if force_refresh:
        db.execute("DELETE FROM market_intel WHERE date=?", (today,))
    
    compiled = {
        "date": today,
        "timestamp": datetime.now().strftime("%H%M"),
        "source": "compiled",
        "tw_index": _parse_num(mkt.get("twii", "")),
        "tsmc": _parse_num(mkt.get("tsmc", "")),
        "sox": _parse_num(mkt.get("sox", "")),
        "tw_change": _parse_pct(mkt.get("twii", "")),
        "dow": _parse_num(mkt.get("dow", "")),
        "nasdaq": _parse_num(mkt.get("nasdaq", "")),
        "sp500": _parse_num(mkt.get("sp500", "")),
        "nikkei": _parse_num(mkt.get("nikkei", "")),
        "summary": f"hunter_logs {len(txts)}筆，買{len(signals['buy'])}賣{len(signals['sell'])}訊號",
        "signals": json.dumps(signals, ensure_ascii=False),
        "raw_data": json.dumps(mkt, ensure_ascii=False),
        "hunter_count": len(txts),
        "buy_count": len(signals["buy"]),
        "sell_count": len(signals["sell"]),
    }
    
    db.execute("""INSERT OR REPLACE INTO market_intel
        (date, timestamp, source, tw_index, tsmc, sox, tw_change, dow, nasdaq, sp500, nikkei, summary, signals, raw_data)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (compiled["date"], compiled["timestamp"], compiled["source"],
         compiled["tw_index"], compiled["tsmc"], compiled["sox"], compiled["tw_change"],
         compiled["dow"], compiled["nasdaq"], compiled["sp500"], compiled["nikkei"],
         compiled["summary"], compiled["signals"], compiled["raw_data"]))
    db.commit()
    db.close()
    return compiled

def get_today_intel(db=None) -> dict:
    """讀取今日情報彙總"""
    if db is None:
        db = sqlite3.connect(str(BASE / "dragon_assets.db"))
        db.row_factory = sqlite3.Row
        _close = True
    else: _close = False
    row = db.execute("SELECT * FROM market_intel WHERE date=? ORDER BY timestamp DESC LIMIT 1", (today,)).fetchone()
    if _close: db.close()
    return dict(row) if row else {}

def _parse_num(s):
    if not s: return 0.0
    s = s.split("(")[0].strip().replace(",","")
    try: return float(re.sub(r'[^0-9.]', '', s))
    except: return 0.0

def _parse_pct(s):
    if not s or "(" not in s: return 0.0
    try: return float(s.split("(")[1].replace(")", "").replace("%", "").replace("+", ""))
    except: return 0.0

if __name__ == "__main__":
    c = compile_intel(force_refresh=True)
    print(f"✅ 情報彙整完成：{c['hunter_count']}筆hunter / 買{c['buy_count']}賣{c['sell_count']}訊號")
    print(f"   加權：{c['tw_index']:,.0f} ({c['tw_change']:+.2f}%)")
