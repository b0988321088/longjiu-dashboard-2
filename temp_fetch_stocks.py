import json, subprocess

symbols = {
    'TSM': 'TSM (台積電ADR)',
    'NVDA': 'NVIDIA',
    'TSLA': '特斯拉',
    'AMZN': 'Amazon',
    'AAPL': 'Apple',
    'QQQ': 'QQQ (納斯達克ETF)',
    'SPY': 'SPY (標普500ETF)',
    'GC=F': '黃金期貨',
    'CL=F': '原油期貨',
}

results = {}
for sym, name in symbols.items():
    try:
        r = subprocess.run(
            ['curl', '-s', f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d',
             '-H', 'User-Agent: Mozilla/5.0'],
            capture_output=True, text=True, timeout=15
        )
        d = json.loads(r.stdout)
        if d.get('chart') and d['chart'].get('result') and d['chart']['result'][0]:
            m = d['chart']['result'][0]['meta']
            q = d['chart']['result'][0]['indicators']['quote'][0]
            prev = m.get('chartPreviousClose', 0)
            price = m.get('regularMarketPrice', 0)
            change = price - prev
            change_pct = (change / prev * 100) if prev else 0
            results[sym] = {
                'name': name,
                'price': round(price, 2),
                'open': round(q['open'][0], 2) if q.get('open') and q['open'][0] else None,
                'high': round(q['high'][0], 2) if q.get('high') and q['high'][0] else None,
                'low': round(q['low'][0], 2) if q.get('low') and q['low'][0] else None,
                'close': round(q['close'][0], 2) if q.get('close') and q['close'][0] else None,
                'volume': int(q['volume'][0]) if q.get('volume') and q['volume'][0] else None,
                'prev_close': round(prev, 2),
                'change': round(change, 2),
                'change_pct': round(change_pct, 2),
                '52w_high': round(m.get('fiftyTwoWeekHigh', 0), 2) if m.get('fiftyTwoWeekHigh') else None,
                '52w_low': round(m.get('fiftyTwoWeekLow', 0), 2) if m.get('fiftyTwoWeekLow') else None,
            }
        else:
            results[sym] = {'name': name, 'error': 'No data from API'}
    except Exception as e:
        results[sym] = {'name': name, 'error': str(e)}

# Also fetch the index data we already got for completeness
indexes = {
    '^GSPC': 'S&P 500',
    '^DJI': '道瓊',
    '^IXIC': '納斯達克',
}
for sym, name in indexes.items():
    r = subprocess.run(
        ['curl', '-s', f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d',
         '-H', 'User-Agent: Mozilla/5.0'],
        capture_output=True, text=True, timeout=15
    )
    d = json.loads(r.stdout)
    if d.get('chart') and d['chart'].get('result') and d['chart']['result'][0]:
        m = d['chart']['result'][0]['meta']
        q = d['chart']['result'][0]['indicators']['quote'][0]
        prev = m.get('chartPreviousClose', 0)
        price = m.get('regularMarketPrice', 0)
        change = price - prev
        change_pct = (change / prev * 100) if prev else 0
        results[sym] = {
            'name': name,
            'price': round(price, 2),
            'open': round(q['open'][0], 2) if q.get('open') and q['open'][0] else None,
            'high': round(q['high'][0], 2) if q.get('high') and q['high'][0] else None,
            'low': round(q['low'][0], 2) if q.get('low') and q['low'][0] else None,
            'volume': int(q['volume'][0]) if q.get('volume') and q['volume'][0] else None,
            'prev_close': round(prev, 2),
            'change': round(change, 2),
            'change_pct': round(change_pct, 2),
        }

print(json.dumps(results, ensure_ascii=False, indent=2))
