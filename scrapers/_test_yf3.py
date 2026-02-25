"""Test: Yahoo Finance v8 API directly (no yfinance library)."""
import requests
import json

tickers = ['NVDA', 'MSFT', 'GOOGL', 'META', 'AMD', 'AAPL', 'AMZN', 'TSM', 'AVGO', 'CRM']
symbols = ','.join(tickers)

# Yahoo Finance v8 quote API
url = f'https://query1.finance.yahoo.com/v8/finance/chart/{tickers[0]}'
headers = {'User-Agent': 'Mozilla/5.0'}

# Try v7 quote endpoint (returns multiple tickers)
url2 = f'https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols}'
try:
    r = requests.get(url2, headers=headers, timeout=15)
    print(f'v7 status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        for q in data.get('quoteResponse', {}).get('result', []):
            sym = q.get('symbol', '?')
            price = q.get('regularMarketPrice', 0)
            chg = q.get('regularMarketChangePercent', 0)
            prev = q.get('regularMarketPreviousClose', 0)
            mcap = q.get('marketCap', 0)
            print(f'  {sym}: ${price:.2f} ({chg:+.2f}%) prev=${prev:.2f} mcap=${mcap/1e9:.0f}B')
    else:
        print(f'  Body: {r.text[:200]}')
except Exception as e:
    print(f'v7 failed: {e}')

# Try v6 as fallback
url3 = f'https://query2.finance.yahoo.com/v6/finance/quote?symbols={symbols}'
try:
    r = requests.get(url3, headers=headers, timeout=15)
    print(f'\nv6 status: {r.status_code}')
    if r.status_code == 200:
        print('  v6 works too')
except Exception as e:
    print(f'v6 failed: {e}')
