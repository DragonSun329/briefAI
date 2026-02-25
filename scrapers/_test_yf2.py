"""Test: fetch prices for a few tickers one at a time with individual timeout."""
import yfinance as yf
import threading
import time

tickers = ['NVDA', 'MSFT', 'GOOGL', 'META', 'AMD', 'AAPL']

for ticker in tickers:
    result = [None]
    def _get(t=ticker):
        try:
            result[0] = yf.Ticker(t).fast_info
        except:
            pass
    
    th = threading.Thread(target=_get, daemon=True)
    th.start()
    th.join(timeout=15)
    
    if th.is_alive() or result[0] is None:
        print(f"{ticker}: TIMEOUT/FAIL")
    else:
        info = result[0]
        lp = getattr(info, 'last_price', None)
        pc = getattr(info, 'previous_close', None)
        if lp and pc:
            chg = ((lp - pc) / pc) * 100
            print(f"{ticker}: ${lp:.2f} ({chg:+.2f}%) prev=${pc:.2f}")
        else:
            print(f"{ticker}: no price data")
    time.sleep(0.5)
