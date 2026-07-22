"""龍九情報彙整"""
import sqlite3, json, re, glob
from datetime import date, datetime
from pathlib import Path
BASE = Path(__file__).resolve().parent
today = date.today().isoformat()
def compile_intel(force_refresh=False):
    db = sqlite3.connect(str(BASE / "dragon_assets.db"))
    txts = sorted(glob.glob(str(BASE / "hunter_logs" / f"intel_{today.replace(chr(45),chr(45))}_*.txt")))
    sig = {"sell":[],"buy":[]}
    for f in txts:
        try:
            for line in Path(f).read_text("utf-8",errors="ignore").splitlines():
                for k in ["賣出","賣超","大跌","跌破"]:
                    if k in line: sig["sell"].append(line.strip()); break
                for k in ["買進","買超","大漲"]:
                    if k in line: sig["buy"].append(line.strip()); break
        except: pass
    p = db.execute("SELECT tw_index,tsmc,sox,tw_change FROM market_intel WHERE date=? AND source='daily_intel' ORDER BY id DESC LIMIT 1",(today,)).fetchone()
    if p: ti,ts,so,tc=p
    else: ti=ts=so=0; tc=0.0
    c={"date":today,"timestamp":datetime.now().strftime("%H%M"),"source":"compiled","tw_index":ti,"tsmc":ts,"sox":so,"tw_change":tc,"dow":0,"nasdaq":0,"sp500":0,"nikkei":0,"summary":f"hunter_logs {len(txts)}筆","signals":json.dumps(sig,ensure_ascii=False),"raw_data":"{}","hunter_count":len(txts),"buy_count":len(sig["buy"]),"sell_count":len(sig["sell"])}
    if force_refresh: db.execute("DELETE FROM market_intel WHERE date=? AND source='compiled'",(today,))
    db.execute("INSERT OR REPLACE INTO market_intel(date,timestamp,source,tw_index,tsmc,sox,tw_change,dow,nasdaq,sp500,nikkei,summary,signals,raw_data,hunter_count,buy_count,sell_count) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(c["date"],c["timestamp"],c["source"],c["tw_index"],c["tsmc"],c["sox"],c["tw_change"],c["dow"],c["nasdaq"],c["sp500"],c["nikkei"],c["summary"],c["signals"],c["raw_data"],c["hunter_count"],c["buy_count"],c["sell_count"]))
    db.commit(); db.close()
    print(f"加權:{c[chr(116)+chr(119)+chr(95)+chr(105)+chr(110)+chr(100)+chr(101)+chr(120)]:,.0f}" if c[chr(116)+chr(119)+chr(95)+chr(105)+chr(110)+chr(100)+chr(101)+chr(120)] else "無資料")
    return c
if __name__=="__main__": compile_intel()
