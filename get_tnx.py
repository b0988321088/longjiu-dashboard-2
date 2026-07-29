import yfinance as yf

# US 10yr Treasury Yield
data = yf.download('^TNX', period='1mo')
if len(data) > 0:
    print(f'10yr Yield: {data["Close"].iloc[-1]:.2f}%')
    print(f'1mo High: {data["High"].max():.2f}%')
    print(f'1mo Low: {data["Low"].min():.2f}%')
    print(f'1mo Change: {(data["Close"].iloc[-1]-data["Close"].iloc[0]):.2f}%')
else:
    print('^TNX: no data - trying alternative')
    data = yf.download('TYX', period='1mo')
    if len(data) > 0:
        print(f'TYX: {data["Close"].iloc[-1]:.2f}')
        print(f'10yr ≈ {data["Close"].iloc[-1]/10:.2f}%')
