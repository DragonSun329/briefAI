"""Test getting stock data via Tavily as Yahoo Finance alternative."""
import requests, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

key = os.getenv('TAVILY_API_KEY')

# Try getting today's AI stock movers
queries = [
    'AI technology stocks biggest movers today percentage change February 24 2026',
    'NVDA CRWD NET AMD stock price change today',
]

for q in queries:
    print(f"\nQuery: {q[:60]}...")
    r = requests.post('https://api.tavily.com/search', json={
        'api_key': key,
        'query': q,
        'search_depth': 'basic',
        'max_results': 5,
        'include_answer': True,
    }, timeout=15)
    d = r.json()
    print(f"Answer: {d.get('answer','N/A')[:400]}")
    for res in d.get('results', [])[:3]:
        print(f"  - {res['title'][:100]}")
