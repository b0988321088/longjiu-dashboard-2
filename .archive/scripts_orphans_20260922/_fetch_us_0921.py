# -*- coding: utf-8 -*-
import json, urllib.request, ssl

TICKERS = ["^DJI","^GSPC","^IXIC","^SOX","TSM","NVDA","AAPL","MSFT","AMZN","GOOGL","META","AVGO","QQQ","TLT","BIL","0050.TW","^TWII","^VIX","DX-Y.NYB","GC=F","CL=F"]
HDR = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

out = {}
for t in TICKERS:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=1d&range=5d" % urllib.parse.quote(t)
    try:
        req = urllib.request.Request(url, headers=HDR)
        raw = urllib.request.urlopen(req, timeout=20, context=ctx).read()
        d = json.loads(raw)["chart"]["result"][0]
        meta = d["meta"]
        closes = [c for c in d["indicators"]["quote"][0]["close"] if c is not None]
        if len(closes) >= 2:
            chg = (closes[-1]-closes[-2])/closes[-2]*100
        else:
            chg = meta.get("regularMarketChangePercent", 0.0)
        out[t] = {"price": round(meta.get("regularMarketPrice", closes[-1] if closes else 0), 2),
                  "pct": round(chg, 2),
                  "prev": round(closes[-2], 2) if len(closes) >= 2 else None,
                  "closes": [round(c,2) for c in closes]}
    except Exception as e:
        out[t] = {"error": str(e)}

print(json.dumps(out, ensure_ascii=False, indent=1))
open("_us_market_0921.json","w",encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
