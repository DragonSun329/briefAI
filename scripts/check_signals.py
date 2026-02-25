import json, os, sys
sys.path.insert(0, 'C:\\Users\\admin\\briefAI')
os.chdir('C:\\Users\\admin\\briefAI')
from trading.paper_trader import load_finnhub_data, load_correlations, generate_signals

finnhub = load_finnhub_data('2026-02-24')
corr = load_correlations('2026-02-24')

# Check structure
stocks = finnhub.get("stocks", finnhub.get("data", []))
if isinstance(stocks, dict):
    stocks = list(stocks.values())
print(f"Stocks: {len(stocks)}")
if stocks:
    s = stocks[0]
    print(f"Sample keys: {list(s.keys())}")
    print(f"Sample: ticker={s.get('ticker','?')}, price={s.get('current_price', s.get('price','?'))}")
    ta = s.get('technical_analysis', {})
    print(f"TA keys: {list(ta.keys())}")
    print(f"TA: {ta}")

# Check correlations structure
corrs = corr.get("correlations", [])
print(f"\nCorrelations: {len(corrs)}")
if corrs:
    c = corrs[0]
    print(f"Corr keys: {list(c.keys())}")

signals = generate_signals(finnhub, corr)
print(f"\nSignals generated: {len(signals)}")
for s in signals:
    print(f"  {s['action']} {s['ticker']}: {s['reason']} conf={s['confidence']:.2f}")
