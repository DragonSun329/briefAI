import requests, json, os
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(r'C:\Users\admin\briefAI\.env'))
key = os.getenv('TAVILY_API_KEY')

tickers = ['NVDA', 'MSFT', 'GOOGL', 'META', 'AMD', 'AAPL']
for t in tickers:
    r = requests.post('https://api.tavily.com/search', json={
        'api_key': key,
        'query': f'{t} stock price',
        'topic': 'finance',
        'time_range': 'week',
        'max_results': 2,
    }, timeout=15)
    d = r.json()
    results = d.get('results', [])
    if results:
        print(f"{t}: {results[0].get('title','')[:80]}")
        print(f"  {results[0].get('content','')[:150]}")
    else:
        print(f"{t}: no results")
    print()
