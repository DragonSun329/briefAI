#!/usr/bin/env python3
"""
Market-News Correlator for briefAI

Cross-references today's price moves (Yahoo Finance) with today's news articles
from all scrapers to produce matched signals: "CRWD -9.8% likely related to [article]"

Data flow:
  Yahoo Finance signals + All news sources -> Ticker extraction -> Matching -> Scored correlations

Usage:
  python scrapers/market_news_correlator.py [--date 2026-02-24]
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
MARKET_DIR = DATA_DIR / "market_signals"
NEWS_DIR = DATA_DIR / "news_signals"
ALT_DIR = DATA_DIR / "alternative_signals"
OUTPUT_DIR = DATA_DIR / "market_correlations"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Ticker -> company name mapping for fuzzy matching in article text
TICKER_ALIASES = {
    'NVDA': ['nvidia', 'nvda', 'jensen huang'],
    'MSFT': ['microsoft', 'msft', 'satya nadella'],
    'GOOGL': ['google', 'alphabet', 'googl', 'deepmind', 'gemini ai'],
    'META': ['meta', 'facebook', 'zuckerberg', 'llama model'],
    'AMZN': ['amazon', 'amzn', 'aws', 'alexa ai'],
    'AAPL': ['apple', 'aapl', 'siri ai'],
    'AMD': ['amd', 'advanced micro', 'lisa su'],
    'INTC': ['intel', 'intc', 'pat gelsinger'],
    'AI': ['c3.ai', 'c3 ai'],  # Don't add 'ai' - matches everything
    'PLTR': ['palantir', 'pltr', 'alex karp'],
    'PATH': ['uipath', 'ui path'],
    'SNOW': ['snowflake', 'snow'],
    'DDOG': ['datadog', 'ddog'],
    'MDB': ['mongodb', 'mongo'],
    'CRWD': ['crowdstrike', 'crwd'],
    'ZS': ['zscaler'],
    'AVGO': ['broadcom', 'avgo'],
    'QCOM': ['qualcomm', 'qcom'],
    'ARM': ['arm holdings', 'arm ltd', 'softbank arm'],
    'TSM': ['tsmc', 'taiwan semi'],
    'ASML': ['asml'],
    'MRVL': ['marvell', 'mrvl'],
    'CRM': ['salesforce', 'crm'],
    'ORCL': ['oracle corp', 'oracle cloud', 'orcl', 'larry ellison'],
    'IBM': ['ibm', 'watson ai'],
    'NOW': ['servicenow'],
    'ADBE': ['adobe', 'adbe'],
    'WDAY': ['workday', 'wday'],
    'UPST': ['upstart', 'upst'],
    'DOCS': ['doximity'],  # 'docs' is too generic
    'S': ['sentinelone', 'sentinel one'],  # Don't add 's' - too short
    'NET': ['cloudflare', 'net'],
    'U': ['unity software', 'unity technologies'],  # Don't add 'unity' alone - too generic
}

# Build reverse lookup: lowercase alias -> ticker
# Skip raw ticker symbols shorter than 3 chars (too many false positives: S, U, AI, NET)
ALIAS_TO_TICKER = {}
SHORT_TICKER_SKIP = {'s', 'u', 'ai', 'net', 'now'}  # these match common English words
for ticker, aliases in TICKER_ALIASES.items():
    for alias in aliases:
        ALIAS_TO_TICKER[alias.lower()] = ticker
    if ticker.lower() not in SHORT_TICKER_SKIP:
        ALIAS_TO_TICKER[ticker.lower()] = ticker


def load_market_data(date_str: str) -> Dict[str, Dict]:
    """Load market signals for the date. Prefers Finnhub, falls back to Yahoo Finance.
    Returns {ticker: signal_dict} with normalized keys."""
    
    # Try Finnhub first (more accurate from China)
    finnhub_path = MARKET_DIR / f"finnhub_{date_str}.json"
    yahoo_path = MARKET_DIR / f"yahoo_finance_{date_str}.json"
    
    path = finnhub_path if finnhub_path.exists() else yahoo_path
    if not path.exists():
        logger.warning(f"No market data for {date_str}")
        return {}
    
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    
    signals = {}
    for stock in data.get('stocks', []):
        ticker = stock.get('ticker')
        if not ticker:
            continue
        # Normalize Finnhub keys to match Yahoo format
        if 'change_pct' in stock and 'day_change_pct' not in stock:
            stock['day_change_pct'] = stock['change_pct']
        signals[ticker] = stock
    
    logger.info(f"Loaded {len(signals)} stock signals from {path.name}")
    return signals


def load_all_news(date_str: str) -> List[Dict]:
    """
    Load all news articles from every scraper for the given date.
    Normalizes them into a common format: {title, url, source, text, ticker_hint}.
    """
    articles = []
    
    # 1. news_search (Tavily/SearXNG)
    _load_news_search(date_str, articles)
    # 2. us_tech_news (already has ticker field!)
    _load_us_tech_news(date_str, articles)
    # 3. tech_news (TechMeme etc)
    _load_tech_news(date_str, articles)
    # 4. blog_signals
    _load_blog_signals(date_str, articles)
    # 5. earnings
    _load_earnings(date_str, articles)
    # 6. hackernews
    _load_hackernews(date_str, articles)
    # 7. podcasts
    _load_podcasts(date_str, articles)
    
    logger.info(f"Loaded {len(articles)} total articles from all sources")
    return articles


def _load_news_search(date_str: str, out: List[Dict]):
    path = ALT_DIR / f"news_search_{date_str}.json"
    if not path.exists():
        return
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    for a in data.get('articles', []):
        out.append({
            'title': a.get('title', ''),
            'url': a.get('url', ''),
            'source': a.get('source', 'news_search'),
            'text': f"{a.get('title', '')} {a.get('description', '')}",
            'ticker_hint': None,
            'relevance': a.get('ai_relevance_score', 0),
            'sentiment_keywords': a.get('sentiment_keywords', []),
        })


def _load_us_tech_news(date_str: str, out: List[Dict]):
    path = ALT_DIR / f"us_tech_news_{date_str}.json"
    if not path.exists():
        return
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    items = data if isinstance(data, list) else data.get('articles', [])
    for a in items:
        out.append({
            'title': a.get('title', ''),
            'url': a.get('url', ''),
            'source': a.get('source', 'us_tech_news'),
            'text': f"{a.get('title', '')} {a.get('summary', '')} {a.get('content_preview', '')}",
            'ticker_hint': a.get('ticker'),  # pre-tagged!
            'relevance': a.get('ai_relevance_score', 0),
            'sentiment_keywords': a.get('sentiment_keywords', []),
        })


def _load_tech_news(date_str: str, out: List[Dict]):
    path = NEWS_DIR / f"tech_news_{date_str}.json"
    if not path.exists():
        return
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    for a in data.get('stories', data.get('articles', [])):
        out.append({
            'title': a.get('title', ''),
            'url': a.get('url', ''),
            'source': 'techmeme',
            'text': f"{a.get('title', '')} {a.get('summary', '')}",
            'ticker_hint': None,
            'relevance': a.get('ai_relevance_score', 0.5),
            'sentiment_keywords': [],
        })


def _load_blog_signals(date_str: str, out: List[Dict]):
    path = ALT_DIR / f"blog_signals_{date_str}.json"
    if not path.exists():
        return
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    for a in data.get('posts', []):
        out.append({
            'title': a.get('title', ''),
            'url': a.get('url', ''),
            'source': a.get('blog', 'blog'),
            'text': f"{a.get('title', '')} {a.get('summary', '')}",
            'ticker_hint': None,
            'relevance': a.get('ai_relevance_score', 0),
            'sentiment_keywords': [],
        })


def _load_earnings(date_str: str, out: List[Dict]):
    path = ALT_DIR / f"earnings_{date_str}.json"
    if not path.exists():
        return
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    for a in data.get('earnings_news', []):
        # Earnings scraper ticker_hint is unreliable (assigns first ticker to all articles)
        # Only trust it if the ticker/company name actually appears in the title
        ticker_hint = a.get('ticker')
        title = a.get('title', '')
        if ticker_hint:
            aliases = TICKER_ALIASES.get(ticker_hint, [])
            title_lower = title.lower()
            if not any(al.lower() in title_lower for al in aliases + [ticker_hint]):
                ticker_hint = None  # Don't trust this tag
        out.append({
            'title': title,
            'url': a.get('url', ''),
            'source': 'earnings',
            'text': f"{title} {a.get('summary', '')}",
            'ticker_hint': ticker_hint,
            'relevance': 0.8,
            'sentiment_keywords': [],
        })


def _load_hackernews(date_str: str, out: List[Dict]):
    path = ALT_DIR / f"hackernews_{date_str}.json"
    if not path.exists():
        return
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    for a in data.get('stories', data.get('posts', [])):
        out.append({
            'title': a.get('title', ''),
            'url': a.get('url', ''),
            'source': 'hackernews',
            'text': f"{a.get('title', '')}",
            'ticker_hint': None,
            'relevance': 0.5,
            'sentiment_keywords': [],
        })


def _load_podcasts(date_str: str, out: List[Dict]):
    path = ALT_DIR / f"podcasts_{date_str}.json"
    if not path.exists():
        return
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    items = data if isinstance(data, list) else data.get('articles', [])
    for a in items:
        out.append({
            'title': a.get('title', ''),
            'url': a.get('url', ''),
            'source': f"podcast:{a.get('podcast_channel', 'unknown')}",
            'text': f"{a.get('title', '')} {a.get('summary', '')} {a.get('content', '')[:2000]}",
            'ticker_hint': None,
            'relevance': 0.9,  # Podcasts are high-signal
            'sentiment_keywords': [],
        })


def extract_tickers_from_text(text: str) -> List[Tuple[str, float]]:
    """
    Extract ticker mentions from text. Returns [(ticker, confidence), ...].
    Uses alias matching (company names, CEO names, etc).
    """
    if not text:
        return []
    
    text_lower = text.lower()
    found = {}
    
    for alias, ticker in ALIAS_TO_TICKER.items():
        if len(alias) <= 2:
            # Short aliases (like 'S', 'U', 'AI') need word boundary matching
            if re.search(r'\b' + re.escape(alias) + r'\b', text_lower):
                conf = 0.6  # lower confidence for short matches
                if ticker not in found or found[ticker] < conf:
                    found[ticker] = conf
        else:
            if alias in text_lower:
                # Longer aliases get higher confidence
                conf = 0.9 if len(alias) > 5 else 0.75
                if ticker not in found or found[ticker] < conf:
                    found[ticker] = conf
    
    return list(found.items())


def correlate(market: Dict[str, Dict], articles: List[Dict], min_move_pct: float = 1.5) -> Dict[str, Any]:
    """
    Core correlation engine. Matches price movers to relevant articles.
    
    For each stock with |change| >= min_move_pct:
      - Find articles mentioning that ticker (via alias matching or ticker_hint)
      - Score the match (article relevance * ticker confidence * move magnitude)
      - Infer sentiment from article keywords + price direction agreement
    
    Returns structured correlation output.
    """
    # Filter to significant movers
    movers = {t: s for t, s in market.items() if abs(s.get('day_change_pct', 0)) >= min_move_pct}
    logger.info(f"Significant movers (>={min_move_pct}%): {len(movers)}")
    
    if not movers:
        logger.info("No significant movers found")
        return {'correlations': [], 'summary': {'movers': 0, 'matched': 0}}
    
    # Pre-extract tickers from all articles
    article_tickers = []
    for art in articles:
        # Use pre-tagged ticker if available
        if art.get('ticker_hint'):
            tickers = [(art['ticker_hint'], 0.95)]
        else:
            tickers = extract_tickers_from_text(art['text'])
        article_tickers.append(tickers)
    
    # Match movers to articles
    correlations = []
    
    for ticker, signal in movers.items():
        change = signal['day_change_pct']
        direction = 'up' if change > 0 else 'down'
        
        matched_articles = []
        for i, art in enumerate(articles):
            art_tickers = article_tickers[i]
            for t, conf in art_tickers:
                if t == ticker:
                    # Score: combination of move magnitude, article relevance, match confidence
                    art_relevance = art.get('relevance', 0.5)
                    match_score = round(conf * min(1.0, abs(change) / 10) * max(0.3, art_relevance), 3)
                    
                    # Sentiment analysis from keywords
                    sentiment = _infer_sentiment(art.get('sentiment_keywords', []), art['text'])
                    
                    matched_articles.append({
                        'title': art['title'][:200],
                        'url': art['url'],
                        'source': art['source'],
                        'match_confidence': round(conf, 2),
                        'match_score': match_score,
                        'sentiment': sentiment,
                    })
                    break
        
        # Sort by match score, keep top articles
        matched_articles.sort(key=lambda x: x['match_score'], reverse=True)
        matched_articles = matched_articles[:10]  # cap at 10 per ticker
        
        # Determine if news explains the move
        explanation_strength = 'none'
        if matched_articles:
            top_score = matched_articles[0]['match_score']
            if top_score > 0.5:
                explanation_strength = 'strong'
            elif top_score > 0.3:
                explanation_strength = 'moderate'
            else:
                explanation_strength = 'weak'
        
        correlations.append({
            'ticker': ticker,
            'price_change_pct': change,
            'direction': direction,
            'signal': signal.get('signal', 'neutral'),
            'current_price': signal.get('current_price'),
            'article_matches': len(matched_articles),
            'explanation_strength': explanation_strength,
            'top_articles': matched_articles[:5],  # top 5 in output
            'all_match_count': len(matched_articles),
        })
    
    # Sort by absolute price change
    correlations.sort(key=lambda x: abs(x['price_change_pct']), reverse=True)
    
    # Summary stats
    matched_count = sum(1 for c in correlations if c['article_matches'] > 0)
    strong_count = sum(1 for c in correlations if c['explanation_strength'] == 'strong')
    
    return {
        'generated_at': datetime.now().isoformat(),
        'correlations': correlations,
        'summary': {
            'total_movers': len(correlations),
            'with_news_match': matched_count,
            'strong_explanations': strong_count,
            'weak_or_none': len(correlations) - matched_count,
            'total_articles_scanned': len(articles),
            'min_move_threshold': min_move_pct,
        }
    }


def _infer_sentiment(keywords: List[str], text: str) -> str:
    """Simple sentiment inference from keywords and text."""
    positive = {'launch', 'deal', 'growth', 'partnership', 'revenue', 'beat', 'upgrade',
                'expansion', 'record', 'innovation', 'breakthrough', 'surge', 'gain'}
    negative = {'crash', 'decline', 'layoff', 'breach', 'hack', 'fine', 'lawsuit',
                'downgrade', 'miss', 'warning', 'concern', 'risk', 'cut', 'loss', 'drop'}
    
    text_lower = text.lower()
    pos_count = sum(1 for w in positive if w in text_lower)
    neg_count = sum(1 for w in negative if w in text_lower)
    
    # Also check provided keywords
    for kw in keywords:
        if isinstance(kw, str):
            kw_l = kw.lower().lstrip('+-')
            if kw.startswith('+'):
                pos_count += 1
            elif kw.startswith('-'):
                neg_count += 1
    
    if pos_count > neg_count + 1:
        return 'positive'
    elif neg_count > pos_count + 1:
        return 'negative'
    elif pos_count > 0 or neg_count > 0:
        return 'mixed'
    return 'neutral'


def format_report(result: Dict) -> str:
    """Format correlations as a readable report."""
    lines = []
    lines.append("=" * 60)
    lines.append("MARKET-NEWS CORRELATION REPORT")
    lines.append(f"Generated: {result.get('generated_at', 'unknown')}")
    lines.append("=" * 60)
    
    s = result['summary']
    lines.append(f"Movers: {s['total_movers']} | Matched to news: {s['with_news_match']} | Strong: {s['strong_explanations']}")
    lines.append(f"Articles scanned: {s['total_articles_scanned']} | Threshold: >={s['min_move_threshold']}%")
    lines.append("")
    
    for c in result['correlations']:
        arrow = "[UP]" if c['direction'] == 'up' else "[DOWN]"
        sign = '+' if c['price_change_pct'] > 0 else ''
        lines.append(f"  {c['ticker']} {arrow} {sign}{c['price_change_pct']:.1f}% (${c.get('current_price', '?')})")
        lines.append(f"    Explanation: {c['explanation_strength']} ({c['article_matches']} articles)")
        
        for art in c['top_articles'][:3]:
            lines.append(f"    -> [{art['source']}] {art['title'][:100]}")
            lines.append(f"       score={art['match_score']} sentiment={art['sentiment']}")
        
        if not c['top_articles']:
            lines.append(f"    -> No matching articles found (unexplained move)")
        lines.append("")
    
    return "\n".join(lines)


def run_correlation(date_str: str = None, min_move_pct: float = 1.5) -> Dict[str, Any]:
    """Main entry point. Run full market-news correlation for a date."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    logger.info(f"Running market-news correlation for {date_str}")
    
    # Load data
    market = load_market_data(date_str)
    if not market:
        logger.error("No market data available - cannot correlate")
        return {'correlations': [], 'summary': {'error': 'no market data'}}
    
    articles = load_all_news(date_str)
    if not articles:
        logger.warning("No news articles available")
    
    # Correlate
    result = correlate(market, articles, min_move_pct=min_move_pct)
    
    # Save
    output_path = OUTPUT_DIR / f"market_news_{date_str}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"Saved correlations to {output_path}")
    
    # Print report (safe for Windows GBK console)
    report = format_report(result)
    try:
        print(report)
    except UnicodeEncodeError:
        print(report.encode('ascii', errors='replace').decode('ascii'))
    
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Market-News Correlator')
    parser.add_argument('--date', default=None, help='Date (YYYY-MM-DD)')
    parser.add_argument('--threshold', type=float, default=1.5, help='Min move %% to consider')
    args = parser.parse_args()
    
    run_correlation(date_str=args.date, min_move_pct=args.threshold)


if __name__ == '__main__':
    main()
