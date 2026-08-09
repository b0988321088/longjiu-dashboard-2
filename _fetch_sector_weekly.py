#!/usr/bin/env python3
"""Fetch weekly performance for proxy tickers + holdings via Yahoo Finance."""
import urllib.request, json, datetime, sys, os

BASE = os.path.dirname(os.path.abspath(__file__))
TICKERS = ["0050.TW","006208.TW","0056.TW","00878.TW","00919.TW","00713.TW",
           "2330.TW","2317.TW","2891.TW","2881.TW",
           "00924.TW","00888.TW","00981A.TW","00984A.TW","00918.TW","009816.TW",
           "00983D.TW","00646.TW","009823.TW","^TNX"]

def fetch(t):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=1mo&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=25))
    r = d["chart"]["result"][0]
    ts = r["timestamp"]; q = r["indicators"]["quote"][0]
    closes = []
    tz = datetime.timezone(datetime.timedelta(hours=8))
    for i in range(len(ts)):
        c = q["close"][i]
        if c is None: continue
        closes.append((datetime.datetime.fromtimestamp(ts[i], tz).strftime("%Y-%m-%d"), c))
    return closes

out = {}
for t in TICKERS:
    try:
        closes = fetch(t)
        if len(closes) < 3:
            out[t] = {"error": "insufficient data", "n": len(closes)}
            continue
        # last 5 trading days (this week) + prior week close
        week = closes[-5:]
        prev_close = closes[-6][1] if len(closes) >= 6 else week[0][1]
        w_chg = (week[-1][1] / prev_close - 1) * 100
        # week-internal: first day of week vs last
        first = week[0][1]
        week_internal = (week[-1][1] / first - 1) * 100
        out[t] = {
            "rows": [[d, round(c, 2)] for d, c in week],
            "prev_close": round(prev_close, 2),
            "w_chg_pct": round(w_chg, 2),
            "week_internal_pct": round(week_internal, 2),
            "last_close": round(week[-1][1], 2),
        }
    except Exception as e:
        out[t] = {"error": str(e)}

with open(os.path.join(BASE, "_sector_weekly.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

for t, v in out.items():
    if "error" in v:
        print(f"{t}: ERROR {v['error']}")
    else:
        print(f"{t}: w_chg={v['w_chg_pct']}% (vs prev Fri {v['prev_close']} -> {v['last_close']})")
