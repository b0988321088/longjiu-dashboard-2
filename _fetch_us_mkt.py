# -*- coding: utf-8 -*-
"""Fetch live US market quotes (range=1d for correct prev close) + yields."""
import json, urllib.request, ssl, time, datetime

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

SYMS = ["^DJI", "^GSPC", "^IXIC", "^SOX", "^VIX", "^TNX", "^TYX",
        "TSM", "NVDA", "AAPL", "TSLA", "META", "AMZN", "MSFT", "GOOGL", "AVGO", "AMD",
        "ES=F", "NQ=F", "YM=F", "GC=F", "CL=F"]

def fetch(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?interval=1d&range=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            d = json.loads(r.read().decode())
        m = d["chart"]["result"][0]["meta"]
        prev = m.get("previousClose") or m.get("chartPreviousClose")
        price = m.get("regularMarketPrice")
        chg = (price - prev) if (price and prev) else None
        chgpct = (chg / prev * 100) if chg is not None and prev else None
        ts = m.get("regularMarketTime")
        tstr = datetime.datetime.utcfromtimestamp(ts).strftime("%m-%d %H:%M UTC") if ts else ""
        return {"sym": sym, "name": (m.get("shortName") or m.get("longName") or sym)[:28],
                "price": round(price, 2) if price else None, "prev": round(prev, 2) if prev else None,
                "chg": round(chg, 2) if chg is not None else None,
                "chg%": round(chgpct, 2) if chgpct is not None else None, "t": tstr}
    except Exception as e:
        return {"sym": sym, "error": str(e)[:100]}

out = []
for s in SYMS:
    out.append(fetch(s))
    time.sleep(0.35)

print(json.dumps(out, ensure_ascii=False, indent=0))
