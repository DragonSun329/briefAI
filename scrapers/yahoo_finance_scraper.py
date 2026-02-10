#!/usr/bin/env python3
"""
Yahoo Finance Scraper for briefAI
Fetches stock prices, fundamentals, and earnings for AI companies.
Uses yfinance library - no API key required.

Uses yf.download() for reliability + individual Ticker for fundamentals.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import time
import random

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Missing dependencies. Run: pip install yfinance pandas")
    sys.exit(1)

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


def download_prices(tickers: List[str], period: str = "5d") -> Optional[pd.DataFrame]:
    """
    Download price data for multiple tickers at once (more reliable).
    
    Returns:
        DataFrame with OHLCV data for all tickers
    """
    try:
        logger.info(f"Downloading prices for {len(tickers)} tickers...")
        data = yf.download(
            tickers=tickers,
            period=period,
            group_by='ticker',
            auto_adjust=True,
            progress=False,
            threads=True
        )
        return data
    except Exception as e:
        logger.error(f"Failed to download prices: {e}")
        return None


def calculate_signals(prices_df: pd.DataFrame, tickers: List[str]) -> List[Dict]:
    """
    Calculate price signals from downloaded data.
    """
    signals = []
    
    for ticker in tickers:
        try:
            # Handle multi-ticker vs single-ticker DataFrame structure
            if len(tickers) > 1:
                if ticker not in prices_df.columns.get_level_values(0):
                    continue
                ticker_data = prices_df[ticker]
            else:
                ticker_data = prices_df
            
            if ticker_data.empty or 'Close' not in ticker_data.columns:
                continue
            
            close = ticker_data['Close'].dropna()
            if len(close) < 2:
                continue
            
            current = close.iloc[-1]
            prev = close.iloc[-2]
            day_change = ((current - prev) / prev) * 100
            
            # Calculate range position (using available data)
            low_5d = close.min()
            high_5d = close.max()
            if high_5d > low_5d:
                range_pos = ((current - low_5d) / (high_5d - low_5d)) * 100
            else:
                range_pos = 50
            
            # Determine signal
            signal = 'neutral'
            score = 0
            
            if day_change > 5:
                signal = 'bullish'
                score = min(0.8, day_change / 10)
            elif day_change < -5:
                signal = 'bearish'
                score = max(-0.8, day_change / 10)
            
            signals.append({
                'ticker': ticker,
                'current_price': round(current, 2),
                'previous_close': round(prev, 2),
                'day_change_pct': round(day_change, 2),
                'range_5d_position': round(range_pos, 1),
                'signal': signal,
                'score': round(score, 2),
                'signal_type': 'stock_price',
                'source': 'yahoo_finance',
                'scraped_at': datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.debug(f"  Error processing {ticker}: {e}")
            continue
    
    return signals


def get_fundamentals(ticker: str) -> Optional[Dict]:
    """
    Fetch fundamental data for a single ticker.
    More prone to rate limiting, so use sparingly.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.fast_info  # Use fast_info instead of info (more reliable)
        
        return {
            'ticker': ticker,
            'market_cap': getattr(info, 'market_cap', None),
            'pe_ratio': getattr(info, 'pe_ratio', None),
            'fifty_two_week_low': getattr(info, 'fifty_two_week_low', None),
            'fifty_two_week_high': getattr(info, 'fifty_two_week_high', None),
        }
    except Exception as e:
        logger.debug(f"  No fundamentals for {ticker}: {e}")
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
    
    # 4. Get fundamentals for top movers only (to avoid rate limits)
    if result['movers']:
        logger.info(f"Fetching fundamentals for {min(5, len(result['movers']))} top movers...")
        for mover in result['movers'][:5]:
            time.sleep(random.uniform(0.5, 1))
            fund = get_fundamentals(mover['ticker'])
            if fund:
                result['fundamentals'].append(fund)
    
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
