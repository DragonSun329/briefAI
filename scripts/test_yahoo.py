#!/usr/bin/env python3
"""Quick e2e test for Yahoo Finance scraper."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.yahoo_finance_scraper import scrape_market_signals, save_signals

r = scrape_market_signals()
path = save_signals(r)

print(f"\nStocks: {len(r['stocks'])}")
print(f"Movers: {len(r['movers'])}")
print(f"Saved to: {path}")

if r['movers']:
    print("\nTop movers:")
    for m in r['movers'][:10]:
        d = '+' if m['change_pct'] > 0 else ''
        print(f"  {m['ticker']}: {d}{m['change_pct']:.1f}%")

if r['stocks']:
    s = r['stocks'][0]
    print(f"\nSample: {s['ticker']} = ${s['current_price']} ({s['signal']})")
