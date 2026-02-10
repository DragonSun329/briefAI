#!/usr/bin/env python3
"""
Insider Trading Scraper for briefAI
Fetches SEC Form 4 data from OpenInsider and stores as signals.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pandas as pd
    import requests
    from lxml import html
except ImportError:
    print("Missing dependencies. Run: pip install pandas requests lxml")
    sys.exit(1)

from loguru import logger

# Output paths
DATA_DIR = Path(__file__).parent.parent / "data" / "insider_signals"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def fetch_insider_trades(tickers: List[str] = None, limit_per_ticker: int = 10, days: int = 14) -> List[Dict]:
    """
    Fetch insider trading data for specified tickers.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # Default AI/tech tickers to track
    if not tickers:
        tickers = [
            'NVDA', 'MSFT', 'GOOGL', 'META', 'AMZN', 'AAPL', 'AMD', 'INTC',
            'CRM', 'ORCL', 'IBM', 'PLTR', 'SNOW', 'AI', 'PATH', 'DDOG',
            'MDB', 'NET', 'CRWD', 'ZS', 'PANW', 'FTNT'
        ]
    
    all_trades = []
    
    for ticker in tickers:
        logger.info(f"  Fetching insider trades for {ticker}...")
        url = f"http://openinsider.com/screener?s={ticker.upper()}&o=&pl=&ph=&ll=&lh=&fd=0&fdr=&td=0&tdr=&fdlyl=&fdlyh=&dtefrom=&dteto=&xp=1&vl=&vh=&ocl=&och=&session=1,2&v=1"
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"    Error fetching {ticker}: {e}")
            continue
        
        tree = html.fromstring(response.content)
        tables = tree.xpath('//table[contains(@class, "tinytable")]')
        
        ticker_trades = []
        
        for table in tables:
            rows = table.xpath('.//tbody//tr')
            
            for row in rows[:limit_per_ticker]:
                cells = row.xpath('.//td')
                if len(cells) < 12:
                    continue
                
                try:
                    # OpenInsider table structure
                    filing_date = cells[1].text_content().strip()
                    trade_date = cells[2].text_content().strip()
                    ticker_val = cells[3].text_content().strip()
                    insider_name = cells[4].text_content().strip()
                    title = cells[5].text_content().strip()
                    trade_type = cells[6].text_content().strip()
                    price = cells[7].text_content().strip().replace('$', '').replace(',', '')
                    qty = cells[8].text_content().strip().replace(',', '').replace('+', '').replace('-', '')
                    owned = cells[9].text_content().strip().replace(',', '')
                    delta_own = cells[10].text_content().strip()
                    value = cells[11].text_content().strip().replace('$', '').replace(',', '').replace('+', '').replace('-', '')
                    
                    # Parse values
                    try:
                        price_val = float(price) if price else 0
                        qty_val = int(qty) if qty else 0
                        value_val = int(value) if value else 0
                    except ValueError:
                        continue
                    
                    # Skip small trades (< $10k)
                    if value_val < 10000:
                        continue
                    
                    # Determine signal strength
                    is_purchase = 'P' in trade_type.upper()
                    
                    # C-suite trades are stronger signals
                    is_executive = any(t in title.upper() for t in ['CEO', 'CFO', 'COO', 'CTO', 'PRESIDENT', 'CHAIRMAN'])
                    
                    if is_purchase:
                        if is_executive and value_val > 100000:
                            signal = 'strong_bullish'
                            score = 0.8
                        elif value_val > 500000:
                            signal = 'strong_bullish'
                            score = 0.7
                        else:
                            signal = 'bullish'
                            score = 0.5
                    else:
                        if is_executive and value_val > 500000:
                            signal = 'strong_bearish'
                            score = -0.7
                        else:
                            signal = 'bearish'
                            score = -0.3
                    
                    trade = {
                        'entity': ticker.upper(),
                        'signal_type': 'insider_trade',
                        'filing_date': filing_date,
                        'trade_date': trade_date,
                        'insider_name': insider_name,
                        'title': title,
                        'trade_type': 'Purchase' if is_purchase else 'Sale',
                        'price': price_val,
                        'qty': qty_val,
                        'value': value_val,
                        'is_executive': is_executive,
                        'signal': signal,
                        'score': score,
                        'source': 'openinsider',
                        'headline': f"{insider_name} ({title}) {'bought' if is_purchase else 'sold'} ${value_val:,} of {ticker}",
                        'scraped_at': datetime.now().isoformat()
                    }
                    
                    ticker_trades.append(trade)
                    
                except Exception as e:
                    continue
        
        if ticker_trades:
            logger.info(f"    Found {len(ticker_trades)} trades for {ticker}")
            all_trades.extend(ticker_trades)
    
    return all_trades


def fetch_cluster_buys(limit: int = 30) -> List[Dict]:
    """
    Fetch cluster buys - multiple insiders buying same stock.
    This is a strong bullish signal.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    logger.info("  Fetching cluster buys...")
    
    url = "http://openinsider.com/latest-cluster-buys"
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"    Error fetching cluster buys: {e}")
        return []
    
    tree = html.fromstring(response.content)
    
    # Find the cluster buys table
    tables = tree.xpath('//table[contains(@class, "tinytable")]')
    
    clusters = []
    
    for table in tables:
        rows = table.xpath('.//tbody//tr')
        
        for row in rows[:limit]:
            cells = row.xpath('.//td')
            if len(cells) < 6:
                continue
            
            try:
                ticker = cells[1].text_content().strip()
                company = cells[2].text_content().strip()
                industry = cells[3].text_content().strip() if len(cells) > 3 else ''
                
                # Skip if not a valid ticker
                if not ticker or len(ticker) > 5:
                    continue
                
                cluster = {
                    'entity': ticker,
                    'signal_type': 'cluster_buy',
                    'company': company,
                    'industry': industry,
                    'signal': 'strong_bullish',
                    'score': 0.85,
                    'source': 'openinsider',
                    'headline': f"Multiple insiders buying {ticker} ({company})",
                    'scraped_at': datetime.now().isoformat()
                }
                
                clusters.append(cluster)
                
            except Exception:
                continue
    
    logger.info(f"    Found {len(clusters)} cluster buy signals")
    return clusters


def run() -> Dict[str, Any]:
    """
    Main scraper entry point.
    """
    print("=" * 60)
    print("INSIDER TRADING SCRAPER (OpenInsider)")
    print("=" * 60)
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Fetch individual trades
    logger.info("Fetching insider trades...")
    trades = fetch_insider_trades()
    
    # Fetch cluster buys
    logger.info("Fetching cluster buys...")
    clusters = fetch_cluster_buys()
    
    # Combine signals
    all_signals = trades + clusters
    
    # Summary stats
    purchases = sum(1 for t in trades if t.get('trade_type') == 'Purchase')
    sales = sum(1 for t in trades if t.get('trade_type') == 'Sale')
    
    summary = {
        'date': today,
        'total_trades': len(trades),
        'purchases': purchases,
        'sales': sales,
        'cluster_buys': len(clusters),
        'buy_sell_ratio': round(purchases / max(sales, 1), 2),
        'total_signals': len(all_signals)
    }
    
    # Save to file
    output_file = DATA_DIR / f"insider_trades_{today}.json"
    with open(output_file, 'w') as f:
        json.dump({
            'summary': summary,
            'signals': all_signals
        }, f, indent=2)
    
    print(f"\nSaved to: {output_file}")
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"  Individual trades: {len(trades)}")
    print(f"    Purchases: {purchases}")
    print(f"    Sales: {sales}")
    print(f"    Buy/Sell Ratio: {summary['buy_sell_ratio']}")
    print(f"  Cluster buys: {len(clusters)}")
    print(f"\n  Total signals: {len(all_signals)}")
    
    # Show top signals
    print(f"\n{'=' * 60}")
    print("TOP BULLISH SIGNALS")
    print("=" * 60)
    
    bullish = sorted([s for s in all_signals if s['score'] > 0], key=lambda x: -x['score'])[:10]
    for s in bullish:
        print(f"  [{s['entity']}] {s['headline'][:60]}")
        print(f"       Score: {s['score']}, Type: {s['signal_type']}")
    
    return summary


if __name__ == '__main__':
    run()
