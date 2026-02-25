#!/usr/bin/env python3
"""
Yahoo Finance Scraper for briefAI
Fetches stock prices, fundamentals, and earnings for AI companies.

Strategy (China/GFW-resilient):
  1. Try yf.download() bulk (fast when it works)
  2. Fallback: concurrent per-ticker fast_info (15s timeout each)
  3. Fallback: Tavily API search for remaining tickers (1-2 credits)
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Missing dependencies. Run: pip install yfinance pandas")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass

from loguru import logger

# Output paths
DATA_DIR = Path(__file__).parent.parent / "data" / "market_signals"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# AI/Tech companies to track
AI_TICKERS = [
    # Big Tech / AI Leaders
    'NVDA', 'MSFT', 'GOOGL', 'META', 'AMZN', 'AAPL', 'AMD', 'INTC',
    # AI-focused companies
    'AI', 'PLTR', 'PATH', 'SNOW', 'DDOG', 'MDB', 'CRWD', 'ZS',
    # Semiconductors
    'AVGO', 'QCOM', 'ARM', 'TSM', 'ASML', 'MRVL',
    # Cloud / Enterprise
    'CRM', 'ORCL', 'IBM', 'NOW', 'ADBE', 'WDAY',
    # AI Pure-plays
    'UPST', 'DOCS', 'S', 'NET', 'U'
]


def _fetch_single_ticker(ticker: str, timeout: int = 15) -> Optional[Dict]:
    """Fetch a single ticker via fast_info in a thread with timeout."""
    row_holder = [None]
    def _get():
        try:
            info = yf.Ticker(ticker).fast_info
            row_holder[0] = {
                'Ticker': ticker,
                'Close': getattr(info, 'last_price', None),
                'PreviousClose': getattr(info, 'previous_close', None),
                'Open': getattr(info, 'open', None),
                'DayHigh': getattr(info, 'day_high', None),
                'DayLow': getattr(info, 'day_low', None),
                'Volume': getattr(info, 'last_volume', None),
                'FiftyDayAvg': getattr(info, 'fifty_day_average', None),
                'TwoHundredDayAvg': getattr(info, 'two_hundred_day_average', None),
                'MarketCap': getattr(info, 'market_cap', None),
                'YearHigh': getattr(info, 'year_high', None),
                'YearLow': getattr(info, 'year_low', None),
            }
        except Exception:
            pass
    th = threading.Thread(target=_get, daemon=True)
    th.start()
    th.join(timeout=timeout)
    if th.is_alive() or row_holder[0] is None:
        return None
    return row_holder[0]


def _fetch_via_tavily(tickers: List[str]) -> List[Dict]:
    """
    Fallback: use Tavily API to get stock prices for tickers.
    Costs 1-2 API credits. Parses prices from the answer text.
    """
    api_key = os.getenv('TAVILY_API_KEY')
    if not api_key:
        logger.warning("No TAVILY_API_KEY, skipping Tavily fallback")
        return []
    
    try:
        import requests
    except ImportError:
        return []
    
    # Batch tickers into groups of ~10 for focused queries
    rows = []
    got = set()
    for batch_start in range(0, len(tickers), 10):
        batch = [t for t in tickers[batch_start:batch_start + 10] if t not in got]
        if not batch:
            continue
        ticker_str = ' '.join(batch)
        query = f"current stock price today close {ticker_str} percentage change"
        
        try:
            logger.info(f"Tavily fallback for {len(batch)} tickers...")
            r = requests.post('https://api.tavily.com/search', json={
                'api_key': api_key,
                'query': query,
                'search_depth': 'basic',
                'max_results': 8,
                'include_answer': True,
            }, timeout=20)
            data = r.json()
            answer = data.get('answer', '')
            
            # Combine answer + all result snippets for parsing
            all_text = answer + '\n'
            for res in data.get('results', []):
                all_text += res.get('content', '') + '\n' + res.get('title', '') + '\n'
            
            if not all_text.strip():
                continue
            
            # Parse ticker data from combined text
            for ticker in batch:
                if ticker in got:
                    continue
                
                # Strategy: find the FIRST price mention near the ticker
                # Use a narrow window to avoid picking up wrong prices
                patterns = [
                    # "NVDA is $188.11, down 0.92%" / "fell 0.92%"
                    rf'{ticker}\b.{{0,60}}\$(\d+\.?\d*).{{0,40}}?(up|down|fell|rose|gained|lost|dropped|increased|decreased|higher|lower)\s*(\d+\.?\d*)%',
                    # "NVDA ... $188.11 ... -0.92%"
                    rf'{ticker}\b.{{0,60}}\$(\d+\.?\d*).{{0,30}}?([+-]\d+\.?\d*)%',
                    # Just "NVDA ... $188.11" (no change data)
                    rf'{ticker}\b.{{0,40}}\$(\d+\.?\d*)',
                ]
                
                for pi, pat in enumerate(patterns):
                    m = re.search(pat, all_text, re.IGNORECASE | re.DOTALL)
                    if m:
                        price = float(m.group(1))
                        change_pct = None
                        
                        if pi == 0:
                            direction = m.group(2).lower()
                            pct = float(m.group(3))
                            change_pct = -pct if direction in ('down', 'fell', 'lost', 'dropped', 'decreased', 'lower') else pct
                        elif pi == 1:
                            change_pct = float(m.group(2))
                        
                        prev_close = None
                        if change_pct is not None and change_pct != 0:
                            prev_close = price / (1 + change_pct / 100)
                        
                        rows.append({
                            'Ticker': ticker,
                            'Close': price,
                            'PreviousClose': round(prev_close, 2) if prev_close else None,
                            'Open': None, 'DayHigh': None, 'DayLow': None,
                            'Volume': None, 'FiftyDayAvg': None, 'TwoHundredDayAvg': None,
                            'MarketCap': None, 'YearHigh': None, 'YearLow': None,
                            '_source': 'tavily',
                        })
                        got.add(ticker)
                        logger.debug(f"  {ticker}: ${price} ({change_pct}%) [tavily]")
                        break
                        
        except Exception as e:
            logger.warning(f"Tavily request failed: {e}")
    
    logger.info(f"Tavily fallback got {len(rows)} tickers")
    return rows


def download_prices(tickers: List[str], period: str = "5d") -> Optional[pd.DataFrame]:
    """
    Download price data with 3-tier fallback:
      1. yf.download() bulk (30s timeout)
      2. Concurrent per-ticker fast_info (15s each, 5 workers)
      3. Tavily API for remaining tickers
    """
    got_tickers = set()
    all_rows = []
    
    # === Tier 1: Bulk download ===
    try:
        result_holder = [None]
        def _bulk():
            result_holder[0] = yf.download(
                tickers=tickers, period=period,
                group_by='ticker', auto_adjust=True,
                progress=False, threads=True,
            )
        
        logger.info(f"[Tier 1] Bulk download for {len(tickers)} tickers...")
        t = threading.Thread(target=_bulk, daemon=True)
        t.start()
        t.join(timeout=30)
        
        if not t.is_alive() and result_holder[0] is not None and not result_holder[0].empty:
            logger.info(f"Bulk download succeeded!")
            return result_holder[0]
        else:
            logger.warning("Bulk download timed out or empty")
    except Exception as e:
        logger.warning(f"Bulk download failed: {e}")
    
    # === Tier 2: Finnhub API (reliable from China, structured data) ===
    remaining = [t for t in tickers if t not in got_tickers]
    finnhub_key = os.getenv('FINNHUB_API_KEY')
    if remaining and finnhub_key:
        logger.info(f"[Tier 2] Finnhub API for {len(remaining)} tickers...")
        try:
            import requests as _req
            for i, ticker in enumerate(remaining):
                try:
                    r = _req.get('https://finnhub.io/api/v1/quote',
                                 params={'symbol': ticker, 'token': finnhub_key},
                                 timeout=10)
                    q = r.json()
                    if q and q.get('c', 0) > 0:
                        all_rows.append({
                            'Ticker': ticker,
                            'Close': q['c'],
                            'PreviousClose': q.get('pc'),
                            'Open': q.get('o'),
                            'DayHigh': q.get('h'),
                            'DayLow': q.get('l'),
                            'Volume': None,
                            'FiftyDayAvg': None,
                            'TwoHundredDayAvg': None,
                            'MarketCap': None,
                            'YearHigh': None,
                            'YearLow': None,
                            '_source': 'finnhub',
                        })
                        got_tickers.add(ticker)
                        logger.debug(f"  {ticker}: ${q['c']} ({q.get('dp', 0):+.2f}%) [finnhub]")
                    else:
                        logger.debug(f"  {ticker}: no data [finnhub]")
                except Exception as e:
                    logger.debug(f"  {ticker}: error {e} [finnhub]")
                # Rate limit: 60/min free tier
                if (i + 1) % 55 == 0:
                    time.sleep(1)
                else:
                    time.sleep(0.15)
            logger.info(f"Tier 2 (Finnhub) result: {len(got_tickers)}/{len(tickers)} tickers")
        except Exception as e:
            logger.warning(f"Finnhub tier failed: {e}")
    elif remaining:
        logger.info("[Tier 2] No FINNHUB_API_KEY, skipping Finnhub")
    
    # === Tier 3: yfinance per-ticker (backup when Finnhub unavailable) ===
    remaining = [t for t in tickers if t not in got_tickers]
    if remaining and len(remaining) <= 10:
        logger.info(f"[Tier 3] yfinance fast_info for {len(remaining)} remaining tickers...")
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(_fetch_single_ticker, t, 12): t for t in remaining}
            for future in as_completed(futures, timeout=90):
                ticker = futures[future]
                try:
                    row = future.result()
                    if row and row.get('Close') is not None:
                        all_rows.append(row)
                        got_tickers.add(ticker)
                except Exception:
                    pass
        logger.info(f"After yfinance: {len(got_tickers)}/{len(tickers)} tickers")
    elif remaining:
        logger.info(f"Skipping yfinance tier ({len(remaining)} missing, too many to fetch individually)")
    
    if not all_rows:
        return None
    
    return pd.DataFrame(all_rows).set_index('Ticker')


def calculate_signals(prices_df: pd.DataFrame, tickers: List[str]) -> List[Dict]:
    """
    Calculate price signals from downloaded data.
    Handles both bulk download (MultiIndex) and per-ticker (flat) DataFrames.
    """
    signals = []
    is_flat = 'Close' in prices_df.columns  # per-ticker fallback format
    
    for ticker in tickers:
        try:
            if is_flat:
                # Per-ticker fast_info format
                if ticker not in prices_df.index:
                    continue
                row = prices_df.loc[ticker]
                current = row.get('Close')
                prev = row.get('PreviousClose')
                volume = row.get('Volume')
                fifty_day = row.get('FiftyDayAvg')
                two_hundred_day = row.get('TwoHundredDayAvg')
                year_high = row.get('YearHigh')
                year_low = row.get('YearLow')
                market_cap = row.get('MarketCap')
                
                if current is None:
                    continue
                
                if prev is None or prev == 0:
                    day_change = 0  # No change data available
                else:
                    day_change = ((current - prev) / prev) * 100
                
                # Range position: where is price in 52-week range
                if year_high and year_low and year_high > year_low:
                    range_pos = ((current - year_low) / (year_high - year_low)) * 100
                else:
                    range_pos = 50
                
                # Volume signal (vs avg) - not available in fast_info fallback
                volume_ratio = None
                
                # Trend: price vs moving averages
                trend_50d = round(((current - fifty_day) / fifty_day) * 100, 2) if fifty_day else None
                trend_200d = round(((current - two_hundred_day) / two_hundred_day) * 100, 2) if two_hundred_day else None
                
            else:
                # Bulk download MultiIndex format
                if ticker not in prices_df.columns.get_level_values(0):
                    continue
                ticker_data = prices_df[ticker]
                
                if ticker_data.empty or 'Close' not in ticker_data.columns:
                    continue
                
                close = ticker_data['Close'].dropna()
                if len(close) < 2:
                    continue
                
                current = close.iloc[-1]
                prev = close.iloc[-2]
                day_change = ((current - prev) / prev) * 100
                
                low_5d = close.min()
                high_5d = close.max()
                range_pos = ((current - low_5d) / (high_5d - low_5d)) * 100 if high_5d > low_5d else 50
                
                volume_ratio = None
                trend_50d = None
                trend_200d = None
                market_cap = None
            
            # Determine signal strength
            signal = 'neutral'
            score = 0
            
            if day_change > 5:
                signal = 'bullish'
                score = min(0.8, day_change / 10)
            elif day_change > 2:
                signal = 'slightly_bullish'
                score = day_change / 20
            elif day_change < -5:
                signal = 'bearish'
                score = max(-0.8, day_change / 10)
            elif day_change < -2:
                signal = 'slightly_bearish'
                score = day_change / 20
            
            # Track data source
            data_source = 'yahoo_finance'
            if is_flat and ticker in prices_df.index:
                src = prices_df.loc[ticker].get('_source')
                if src:
                    data_source = str(src)
            
            entry = {
                'ticker': ticker,
                'current_price': round(float(current), 2),
                'previous_close': round(float(prev), 2) if prev else None,
                'day_change_pct': round(float(day_change), 2),
                'range_52w_position': round(float(range_pos), 1),
                'signal': signal,
                'score': round(float(score), 3),
                'signal_type': 'stock_price',
                'source': data_source,
                'scraped_at': datetime.now().isoformat(),
            }
            
            # Add enrichment fields when available
            if trend_50d is not None:
                entry['trend_vs_50d'] = trend_50d
            if trend_200d is not None:
                entry['trend_vs_200d'] = trend_200d
            if market_cap is not None:
                entry['market_cap'] = round(float(market_cap))
            
            signals.append(entry)
            
        except Exception as e:
            logger.debug(f"  Error processing {ticker}: {e}")
            continue
    
    return signals


def get_fundamentals(ticker: str) -> Optional[Dict]:
    """
    Fetch fundamental data for a single ticker (with timeout).
    """
    row = _fetch_single_ticker(ticker, timeout=10)
    if row:
        return {
            'ticker': ticker,
            'market_cap': row.get('MarketCap'),
            'fifty_two_week_low': row.get('YearLow'),
            'fifty_two_week_high': row.get('YearHigh'),
        }
    return None


def scrape_market_signals(tickers: List[str] = None) -> Dict[str, Any]:
    """
    Main scraper function: collects market data for AI stocks.
    
    Uses bulk download for prices (reliable) + optional fundamentals.
    """
    logger.info("=" * 50)
    logger.info("Yahoo Finance Scraper")
    logger.info("=" * 50)
    
    if tickers is None:
        tickers = AI_TICKERS
    
    result = {
        'scraped_at': datetime.now().isoformat(),
        'stocks': [],
        'movers': [],
        'fundamentals': []
    }
    
    # 1. Bulk download prices (most reliable method)
    prices_df = download_prices(tickers)
    
    if prices_df is None or prices_df.empty:
        logger.error("Failed to download any price data")
        return result
    
    # 2. Calculate signals from prices
    result['stocks'] = calculate_signals(prices_df, tickers)
    logger.info(f"Got prices for {len(result['stocks'])} tickers")
    
    # 3. Find big movers
    for stock in result['stocks']:
        if abs(stock.get('day_change_pct', 0)) > 3:
            result['movers'].append({
                'ticker': stock['ticker'],
                'change_pct': stock['day_change_pct'],
                'signal': stock['signal']
            })
    
    result['movers'].sort(key=lambda x: abs(x.get('change_pct', 0)), reverse=True)
    
    # 4. Get fundamentals for top movers (skip if yfinance is blocked)
    # Check if any stock came from tavily (means yfinance is down)
    has_yf_data = any(s.get('source') != 'tavily' for s in result['stocks'])
    if result['movers'] and has_yf_data:
        logger.info(f"Fetching fundamentals for {min(5, len(result['movers']))} top movers...")
        for mover in result['movers'][:5]:
            fund = get_fundamentals(mover['ticker'])
            if fund:
                result['fundamentals'].append(fund)
    elif result['movers']:
        logger.info("Skipping fundamentals (yfinance unavailable, data from Tavily)")
    
    # Summary
    logger.info("-" * 50)
    logger.info(f"Stocks with prices: {len(result['stocks'])}")
    logger.info(f"Big movers (>3%): {len(result['movers'])}")
    logger.info(f"Fundamentals fetched: {len(result['fundamentals'])}")
    
    return result


def save_signals(signals: Dict[str, Any]) -> Path:
    """Save signals to JSON file."""
    today = datetime.now().strftime("%Y-%m-%d")
    output_path = DATA_DIR / f"yahoo_finance_{today}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(signals, f, indent=2, ensure_ascii=False, default=str)
    
    logger.info(f"Saved to: {output_path}")
    return output_path


def main():
    """Run the Yahoo Finance scraper."""
    signals = scrape_market_signals()
    save_signals(signals)
    
    # Print top movers
    if signals['movers']:
        logger.info("\nTop Movers Today:")
        for m in signals['movers'][:5]:
            direction = "↑" if m['change_pct'] > 0 else "↓"
            logger.info(f"  {m['ticker']}: {direction} {abs(m['change_pct']):.1f}%")
    
    return signals


if __name__ == "__main__":
    main()
