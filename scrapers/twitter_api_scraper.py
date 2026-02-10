#!/usr/bin/env python3
"""
Twitter/X API Scraper for briefAI
Uses AIsa API for fast, reliable Twitter data access.
Replaces the slow browser-based scraper.

Requires: AISA_API_KEY in environment or .env file
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
except ImportError:
    print("Missing requests. Run: pip install requests")
    sys.exit(1)

from loguru import logger

# Output paths
DATA_DIR = Path(__file__).parent.parent / "data" / "social_signals"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# AIsa API base
AISA_BASE_URL = "https://api.aisa.one/apis/v1/twitter"


def get_api_key() -> Optional[str]:
    """Get AIsa API key from environment or .env file."""
    api_key = os.environ.get('AISA_API_KEY')
    
    if not api_key:
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith('AISA_API_KEY='):
                        api_key = line.split('=', 1)[1].strip().strip('"\'')
                        break
    
    return api_key


def _request(endpoint: str, params: Dict = None) -> Optional[Dict]:
    """Make authenticated request to AIsa API."""
    api_key = get_api_key()
    if not api_key:
        logger.error("AISA_API_KEY not found")
        return None
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    url = f"{AISA_BASE_URL}{endpoint}"
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"AIsa API error: {e}")
        return None


def get_trending_topics(woeid: int = 1) -> List[Dict]:
    """
    Get trending topics from Twitter.
    
    Args:
        woeid: Where On Earth ID (1 = worldwide, 23424977 = USA)
    
    Returns:
        List of trending topics with metadata
    """
    logger.info(f"Fetching Twitter trends (woeid={woeid})...")
    
    data = _request("/trends", {"woeid": woeid})
    
    if not data:
        return []
    
    trends = []
    for item in data.get('trends', data if isinstance(data, list) else []):
        if isinstance(item, dict):
            trend = {
                'name': item.get('name', ''),
                'tweet_volume': item.get('tweet_volume'),
                'url': item.get('url', ''),
                'signal_type': 'twitter_trend',
                'source': 'twitter_aisa',
                'scraped_at': datetime.now().isoformat()
            }
            trends.append(trend)
    
    logger.info(f"  Found {len(trends)} trending topics")
    return trends


def search_tweets(query: str, query_type: str = "Latest", limit: int = 50) -> List[Dict]:
    """
    Search for tweets matching a query.
    
    Args:
        query: Search query
        query_type: "Latest" or "Top"
        limit: Max tweets to return
    
    Returns:
        List of tweet objects
    """
    logger.info(f"Searching Twitter for: {query}")
    
    data = _request("/tweet/advanced_search", {
        "query": query,
        "queryType": query_type
    })
    
    if not data:
        return []
    
    tweets = []
    results = data.get('tweets', data.get('data', data if isinstance(data, list) else []))
    
    for item in results[:limit]:
        if isinstance(item, dict):
            tweet = {
                'id': item.get('id_str', item.get('id', '')),
                'text': item.get('full_text', item.get('text', '')),
                'user': item.get('user', {}).get('screen_name', ''),
                'user_name': item.get('user', {}).get('name', ''),
                'user_followers': item.get('user', {}).get('followers_count', 0),
                'retweets': item.get('retweet_count', 0),
                'likes': item.get('favorite_count', 0),
                'created_at': item.get('created_at', ''),
                'url': f"https://twitter.com/{item.get('user', {}).get('screen_name', '')}/status/{item.get('id_str', item.get('id', ''))}",
                'signal_type': 'twitter_mention',
                'query': query,
                'source': 'twitter_aisa',
                'scraped_at': datetime.now().isoformat()
            }
            tweets.append(tweet)
    
    logger.info(f"  Found {len(tweets)} tweets")
    return tweets


def get_user_tweets(username: str, limit: int = 20) -> List[Dict]:
    """
    Get recent tweets from a specific user.
    
    Args:
        username: Twitter username (without @)
        limit: Max tweets to return
    """
    logger.info(f"Fetching tweets from @{username}...")
    
    data = _request("/user/user_last_tweet", {"userName": username})
    
    if not data:
        return []
    
    tweets = []
    results = data.get('tweets', data if isinstance(data, list) else [])
    
    for item in results[:limit]:
        if isinstance(item, dict):
            tweet = {
                'id': item.get('id_str', item.get('id', '')),
                'text': item.get('full_text', item.get('text', '')),
                'user': username,
                'retweets': item.get('retweet_count', 0),
                'likes': item.get('favorite_count', 0),
                'created_at': item.get('created_at', ''),
                'url': f"https://twitter.com/{username}/status/{item.get('id_str', item.get('id', ''))}",
                'signal_type': 'influencer_tweet',
                'source': 'twitter_aisa',
                'scraped_at': datetime.now().isoformat()
            }
            tweets.append(tweet)
    
    logger.info(f"  Found {len(tweets)} tweets from @{username}")
    return tweets


def scrape_ai_twitter_signals() -> Dict[str, Any]:
    """
    Main scraper function: collects AI-related Twitter signals.
    
    Returns:
        Dict with trends, mentions, and influencer tweets
    """
    logger.info("=" * 50)
    logger.info("Twitter API Scraper (AIsa)")
    logger.info("=" * 50)
    
    signals = {
        'scraped_at': datetime.now().isoformat(),
        'trends': [],
        'ai_mentions': [],
        'influencer_tweets': []
    }
    
    # 1. Get trending topics
    signals['trends'] = get_trending_topics(woeid=1)  # Worldwide
    
    # 2. Search for AI-related tweets
    ai_queries = [
        "AI agents",
        "GPT-5 OR GPT5",
        "Claude AI",
        "LLM production",
        "AI startup funding"
    ]
    
    for query in ai_queries:
        tweets = search_tweets(query, "Top", limit=10)
        signals['ai_mentions'].extend(tweets)
    
    # 3. Get tweets from AI influencers
    influencers = [
        "sama",       # Sam Altman
        "kaboraito",  # Kaito
        "AndrewYNg",  # Andrew Ng
        "ylecun",     # Yann LeCun
        "emaborito",  # Emad
    ]
    
    for user in influencers:
        try:
            tweets = get_user_tweets(user, limit=5)
            signals['influencer_tweets'].extend(tweets)
        except Exception as e:
            logger.warning(f"Failed to fetch @{user}: {e}")
    
    # Summary
    logger.info("-" * 50)
    logger.info(f"Trends: {len(signals['trends'])}")
    logger.info(f"AI Mentions: {len(signals['ai_mentions'])}")
    logger.info(f"Influencer Tweets: {len(signals['influencer_tweets'])}")
    
    return signals


def save_signals(signals: Dict[str, Any]) -> Path:
    """Save signals to JSON file."""
    today = datetime.now().strftime("%Y-%m-%d")
    output_path = DATA_DIR / f"twitter_api_{today}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(signals, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved to: {output_path}")
    return output_path


def main():
    """Run the Twitter API scraper."""
    if not get_api_key():
        logger.error("AISA_API_KEY not found in environment or .env")
        logger.info("Get your key at: https://aisa.one")
        sys.exit(1)
    
    signals = scrape_ai_twitter_signals()
    save_signals(signals)
    
    return signals


if __name__ == "__main__":
    main()
