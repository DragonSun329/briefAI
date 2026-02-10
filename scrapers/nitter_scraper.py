"""
Nitter/X Scraper for AI Public Opinions (No API Keys Required)

Scrapes Twitter/X content via Nitter instances (public Twitter frontends).
Nitter provides access to public tweets without requiring API authentication.

Features:
- Search AI-related tweets via Nitter instances
- Track AI influencer accounts
- Extract hashtag trends
- Sentiment analysis

Output: data/alternative_signals/twitter_sentiment_YYYY-MM-DD.json
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from collections import defaultdict
from urllib.parse import quote, urljoin
import json
import time
import re
import random


@dataclass
class Tweet:
    """Tweet data from Nitter."""
    text: str
    url: str
    author: str
    author_handle: str
    timestamp: Optional[str] = None
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    quotes: int = 0
    hashtags: List[str] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)
    is_retweet: bool = False
    is_quote: bool = False


@dataclass
class TwitterSentimentSignal:
    """Signal format for trend radar integration."""
    name: str
    source_type: str = "twitter"
    signal_type: str = "social_sentiment"
    entity_type: str = "tweet"
    description: Optional[str] = None
    url: str = ""
    category: str = ""
    author: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    date_observed: str = field(default_factory=lambda: date.today().isoformat())


# Nitter instances (public Twitter frontends)
# These change frequently - some may be down
NITTER_INSTANCES = [
    "nitter.privacydev.net",
    "nitter.poast.org",
    "nitter.1d4.us",
    "nitter.kavin.rocks",
    "nitter.unixfox.eu",
    "nitter.moomoo.me",
    "nitter.it",
    "nitter.namazso.eu",
]

# AI influencers and accounts to track
AI_TWITTER_ACCOUNTS = [
    # AI Companies
    "OpenAI",
    "AnthropicAI",
    "GoogleAI",
    "DeepMind",
    "xaboratory",  # xAI
    "MetaAI",
    "MistralAI",
    "CohereForAI",
    "StabilityAI",
    "midaboratory",  # Midaboratory

    # AI Researchers/Leaders
    "ylecun",       # Yann LeCun
    "kaboratorya",       # Andrew Ng
    "GaryMarcus",   # Gary Marcus
    "emaboratoryasberg",  # Emad Mostaque
    "sama",         # Sam Altman
    "demaboratoryhassabis",  # Demis Hassabis

    # AI/Tech News
    "TheAIGRID",
    "ai__pub",
    "ArtificialAnlys",

    # VCs focused on AI
    "a16z",
    "sequoia",
]

# AI-related search queries
AI_SEARCH_QUERIES = [
    "ChatGPT",
    "Claude AI",
    "GPT-4",
    "LLM",
    "generative AI",
    "AI agents",
    "Stable Diffusion",
    "machine learning",
    "OpenAI",
    "Anthropic",
]

# AI hashtags to track
AI_HASHTAGS = [
    "AI",
    "ArtificialIntelligence",
    "MachineLearning",
    "DeepLearning",
    "GenerativeAI",
    "ChatGPT",
    "LLM",
    "AIArt",
    "StableDiffusion",
    "OpenAI",
    "GPT4",
    "AIAgents",
]


class NitterScraper:
    """
    Scrapes Twitter content via Nitter instances.

    Nitter is a privacy-friendly Twitter frontend that allows
    scraping public content without API authentication.
    """

    def __init__(self, instances: Optional[List[str]] = None):
        """
        Initialize the scraper.

        Args:
            instances: List of Nitter instances to use
        """
        self.instances = instances or NITTER_INSTANCES
        self.working_instance = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
        self.last_request = 0
        self.min_delay = 2.0

    def _rate_limit(self):
        """Rate limiting between requests."""
        elapsed = time.time() - self.last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed + random.uniform(0.2, 0.8))
        self.last_request = time.time()

    def _find_working_instance(self) -> Optional[str]:
        """Find a working Nitter instance."""
        if self.working_instance:
            return self.working_instance

        print("  Finding working Nitter instance...")
        random.shuffle(self.instances)

        for instance in self.instances:
            try:
                url = f"https://{instance}"
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    print(f"    Using: {instance}")
                    self.working_instance = instance
                    return instance
            except Exception:
                continue

        print("    No working Nitter instances found!")
        return None

    def _get_base_url(self) -> Optional[str]:
        """Get base URL of working instance."""
        instance = self._find_working_instance()
        if instance:
            return f"https://{instance}"
        return None

    def get_user_tweets(self, username: str, limit: int = 20) -> List[Tweet]:
        """
        Fetch recent tweets from a user's timeline.

        Args:
            username: Twitter username (without @)
            limit: Max tweets to fetch
        """
        tweets = []
        base_url = self._get_base_url()

        if not base_url:
            return tweets

        self._rate_limit()

        try:
            url = f"{base_url}/{username}"
            print(f"    Fetching @{username}...")

            response = self.session.get(url, timeout=30)

            if response.status_code == 404:
                print(f"      User not found")
                return tweets

            if response.status_code != 200:
                print(f"      Error: {response.status_code}")
                # Try another instance
                self.working_instance = None
                return tweets

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find tweet containers
            tweet_items = soup.find_all('div', class_='timeline-item')

            for item in tweet_items[:limit]:
                try:
                    tweet = self._parse_tweet(item, username)
                    if tweet:
                        tweets.append(tweet)
                except Exception as e:
                    continue

            print(f"      Found {len(tweets)} tweets")

        except requests.RequestException as e:
            print(f"      Request error: {e}")
            self.working_instance = None

        return tweets

    def search_tweets(self, query: str, limit: int = 30) -> List[Tweet]:
        """
        Search for tweets matching a query.

        Args:
            query: Search query
            limit: Max tweets to return
        """
        tweets = []
        base_url = self._get_base_url()

        if not base_url:
            return tweets

        self._rate_limit()

        try:
            encoded_query = quote(query)
            url = f"{base_url}/search?f=tweets&q={encoded_query}"
            print(f"    Searching: {query}...")

            response = self.session.get(url, timeout=30)

            if response.status_code != 200:
                print(f"      Error: {response.status_code}")
                self.working_instance = None
                return tweets

            soup = BeautifulSoup(response.text, 'html.parser')
            tweet_items = soup.find_all('div', class_='timeline-item')

            for item in tweet_items[:limit]:
                try:
                    tweet = self._parse_tweet(item)
                    if tweet:
                        tweets.append(tweet)
                except Exception:
                    continue

            print(f"      Found {len(tweets)} tweets")

        except requests.RequestException as e:
            print(f"      Request error: {e}")
            self.working_instance = None

        return tweets

    def get_hashtag_tweets(self, hashtag: str, limit: int = 30) -> List[Tweet]:
        """
        Fetch tweets with a specific hashtag.

        Args:
            hashtag: Hashtag (without #)
            limit: Max tweets
        """
        # Search for the hashtag
        return self.search_tweets(f"#{hashtag}", limit)

    def _parse_tweet(self, item, default_user: str = "unknown") -> Optional[Tweet]:
        """Parse a tweet from Nitter HTML."""
        # Get tweet content
        content_elem = item.find('div', class_='tweet-content')
        if not content_elem:
            return None

        text = content_elem.get_text(strip=True)

        # Get author info
        author_elem = item.find('a', class_='fullname')
        author = author_elem.get_text(strip=True) if author_elem else default_user

        handle_elem = item.find('a', class_='username')
        handle = handle_elem.get_text(strip=True).replace('@', '') if handle_elem else default_user

        # Get tweet link
        link_elem = item.find('a', class_='tweet-link')
        tweet_url = ""
        if link_elem:
            href = link_elem.get('href', '')
            if href:
                # Convert Nitter URL to Twitter URL
                tweet_url = f"https://twitter.com{href}"

        # Get timestamp
        timestamp = None
        time_elem = item.find('span', class_='tweet-date')
        if time_elem:
            time_link = time_elem.find('a')
            if time_link:
                timestamp = time_link.get('title')

        # Get stats
        stats = self._parse_tweet_stats(item)

        # Extract hashtags
        hashtags = re.findall(r'#(\w+)', text)

        # Extract mentions
        mentions = re.findall(r'@(\w+)', text)

        # Check if retweet
        is_retweet = bool(item.find('div', class_='retweet-header'))

        # Check if quote tweet
        is_quote = bool(item.find('div', class_='quote'))

        return Tweet(
            text=text,
            url=tweet_url,
            author=author,
            author_handle=handle,
            timestamp=timestamp,
            likes=stats.get('likes', 0),
            retweets=stats.get('retweets', 0),
            replies=stats.get('replies', 0),
            quotes=stats.get('quotes', 0),
            hashtags=hashtags,
            mentions=mentions,
            is_retweet=is_retweet,
            is_quote=is_quote,
        )

    def _parse_tweet_stats(self, item) -> Dict[str, int]:
        """Parse tweet engagement stats."""
        stats = {'likes': 0, 'retweets': 0, 'replies': 0, 'quotes': 0}

        stat_container = item.find('div', class_='tweet-stats')
        if not stat_container:
            return stats

        # Parse each stat
        for stat_type in ['comment', 'retweet', 'quote', 'heart']:
            stat_elem = stat_container.find('div', class_=f'icon-{stat_type}')
            if stat_elem:
                parent = stat_elem.parent
                if parent:
                    text = parent.get_text(strip=True)
                    # Extract number
                    match = re.search(r'([\d,]+)', text)
                    if match:
                        value = int(match.group(1).replace(',', ''))
                        if stat_type == 'comment':
                            stats['replies'] = value
                        elif stat_type == 'retweet':
                            stats['retweets'] = value
                        elif stat_type == 'quote':
                            stats['quotes'] = value
                        elif stat_type == 'heart':
                            stats['likes'] = value

        return stats


class TwitterSentimentAggregator:
    """
    Aggregates AI-related Twitter sentiment from Nitter.
    """

    def __init__(self):
        self.scraper = NitterScraper()

    def collect_from_accounts(
        self,
        accounts: Optional[List[str]] = None,
        tweets_per_account: int = 10
    ) -> List[Tweet]:
        """
        Collect tweets from AI influencer accounts.
        """
        all_tweets = []
        accounts = accounts or AI_TWITTER_ACCOUNTS

        print("\n  Collecting from AI accounts...")

        for account in accounts:
            try:
                tweets = self.scraper.get_user_tweets(account, limit=tweets_per_account)
                all_tweets.extend(tweets)
                time.sleep(1)
            except Exception as e:
                print(f"    Error with @{account}: {e}")
                continue

        return all_tweets

    def collect_from_searches(
        self,
        queries: Optional[List[str]] = None,
        tweets_per_query: int = 20
    ) -> List[Tweet]:
        """
        Collect tweets from AI-related searches.
        """
        all_tweets = []
        queries = queries or AI_SEARCH_QUERIES

        print("\n  Searching AI topics...")

        for query in queries:
            try:
                tweets = self.scraper.search_tweets(query, limit=tweets_per_query)
                all_tweets.extend(tweets)
                time.sleep(1.5)
            except Exception as e:
                print(f"    Error searching '{query}': {e}")
                continue

        return all_tweets

    def collect_from_hashtags(
        self,
        hashtags: Optional[List[str]] = None,
        tweets_per_hashtag: int = 15
    ) -> List[Tweet]:
        """
        Collect tweets from AI hashtags.
        """
        all_tweets = []
        hashtags = hashtags or AI_HASHTAGS[:5]  # Limit to avoid rate limiting

        print("\n  Collecting from hashtags...")

        for tag in hashtags:
            try:
                tweets = self.scraper.get_hashtag_tweets(tag, limit=tweets_per_hashtag)
                all_tweets.extend(tweets)
                time.sleep(1.5)
            except Exception as e:
                print(f"    Error with #{tag}: {e}")
                continue

        return all_tweets

    def collect_all(self) -> List[Tweet]:
        """
        Collect from all sources.
        """
        all_tweets = []

        # From accounts (most reliable)
        all_tweets.extend(self.collect_from_accounts(tweets_per_account=5))

        # From searches
        all_tweets.extend(self.collect_from_searches(tweets_per_query=15))

        # From hashtags
        all_tweets.extend(self.collect_from_hashtags(tweets_per_hashtag=10))

        return all_tweets


# Sentiment keywords
POSITIVE_KEYWORDS = [
    "amazing", "impressive", "breakthrough", "revolutionary", "game-changer",
    "love", "excellent", "incredible", "fantastic", "best", "awesome",
    "excited", "promising", "innovative", "powerful", "efficient",
    "bullish", "optimistic", "great", "wonderful",
]

NEGATIVE_KEYWORDS = [
    "terrible", "broken", "useless", "disappointing", "overhyped",
    "hate", "worst", "garbage", "scam", "dangerous", "concerning",
    "worried", "scary", "threat", "replace", "layoffs", "job loss",
    "bearish", "pessimistic", "awful", "horrible", "doom",
]


def analyze_tweet_sentiment(tweet: Tweet) -> Dict[str, Any]:
    """Analyze sentiment of a single tweet."""
    text_lower = tweet.text.lower()

    positive = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
    negative = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)

    if positive + negative == 0:
        score = 0
        label = "neutral"
    else:
        score = (positive - negative) / (positive + negative)
        if score > 0.2:
            label = "positive"
        elif score < -0.2:
            label = "negative"
        else:
            label = "neutral"

    return {
        "score": round(score, 2),
        "label": label,
        "positive_count": positive,
        "negative_count": negative,
    }


def convert_to_signals(tweets: List[Tweet]) -> List[TwitterSentimentSignal]:
    """Convert tweets to signal format."""
    signals = []
    seen_urls = set()

    for tweet in tweets:
        # Deduplicate
        if tweet.url in seen_urls:
            continue
        seen_urls.add(tweet.url)

        sentiment = analyze_tweet_sentiment(tweet)
        engagement = tweet.likes + tweet.retweets * 2 + tweet.replies

        signal = TwitterSentimentSignal(
            name=tweet.text[:100] + "..." if len(tweet.text) > 100 else tweet.text,
            source_type="twitter",
            signal_type="social_sentiment",
            entity_type="tweet",
            description=tweet.text,
            url=tweet.url,
            category=f"twitter/{tweet.author_handle}",
            author=tweet.author_handle,
            metrics={
                "likes": tweet.likes,
                "retweets": tweet.retweets,
                "replies": tweet.replies,
                "quotes": tweet.quotes,
                "engagement": engagement,
                "hashtags": tweet.hashtags,
                "mentions": tweet.mentions,
                "sentiment_score": sentiment["score"],
                "sentiment_label": sentiment["label"],
                "is_retweet": tweet.is_retweet,
                "timestamp": tweet.timestamp,
            }
        )
        signals.append(signal)

    return signals


def analyze_overall_sentiment(tweets: List[Tweet]) -> Dict[str, Any]:
    """Analyze overall sentiment from all tweets."""
    sentiments = [analyze_tweet_sentiment(t) for t in tweets]

    positive = sum(1 for s in sentiments if s['label'] == 'positive')
    negative = sum(1 for s in sentiments if s['label'] == 'negative')
    neutral = sum(1 for s in sentiments if s['label'] == 'neutral')

    scores = [s['score'] for s in sentiments]
    avg_score = sum(scores) / len(scores) if scores else 0

    # Top hashtags
    all_hashtags = []
    for tweet in tweets:
        all_hashtags.extend(tweet.hashtags)

    hashtag_counts = defaultdict(int)
    for tag in all_hashtags:
        hashtag_counts[tag.lower()] += 1

    top_hashtags = sorted(hashtag_counts.items(), key=lambda x: -x[1])[:10]

    # Top mentioned accounts
    all_mentions = []
    for tweet in tweets:
        all_mentions.extend(tweet.mentions)

    mention_counts = defaultdict(int)
    for mention in all_mentions:
        mention_counts[mention.lower()] += 1

    top_mentions = sorted(mention_counts.items(), key=lambda x: -x[1])[:10]

    return {
        "total_tweets": len(tweets),
        "sentiment_distribution": {
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
        },
        "average_sentiment": round(avg_score, 3),
        "overall_label": "positive" if avg_score > 0.1 else "negative" if avg_score < -0.1 else "neutral",
        "top_hashtags": dict(top_hashtags),
        "top_mentions": dict(top_mentions),
        "total_engagement": sum(t.likes + t.retweets + t.replies for t in tweets),
    }


def save_signals(signals: List[TwitterSentimentSignal], output_dir: Path) -> Path:
    """Save signals to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    output_file = output_dir / f"twitter_sentiment_{today}.json"

    data = [asdict(s) for s in signals]

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return output_file


def main():
    """Main scraper workflow."""
    print("=" * 60)
    print("TWITTER/X SENTIMENT SCRAPER (via Nitter)")
    print("No API Keys Required")
    print("=" * 60)

    output_dir = Path(__file__).parent.parent / "data" / "alternative_signals"

    # Initialize aggregator
    aggregator = TwitterSentimentAggregator()

    # Collect tweets
    print("\nCollecting AI-related tweets...")
    all_tweets = aggregator.collect_all()

    if not all_tweets:
        print("\nNo tweets collected. Nitter instances may be down.")
        print("Try again later or check instance availability.")
        return

    print(f"\nTotal tweets collected: {len(all_tweets)}")

    # Convert to signals
    signals = convert_to_signals(all_tweets)
    print(f"Unique tweets: {len(signals)}")

    # Analyze sentiment
    print("\n" + "=" * 60)
    print("SENTIMENT ANALYSIS")
    print("=" * 60)

    analysis = analyze_overall_sentiment(all_tweets)

    print(f"\nOverall: {analysis['overall_label'].upper()} (score: {analysis['average_sentiment']:.3f})")
    print(f"\nDistribution:")
    print(f"  Positive: {analysis['sentiment_distribution']['positive']}")
    print(f"  Neutral:  {analysis['sentiment_distribution']['neutral']}")
    print(f"  Negative: {analysis['sentiment_distribution']['negative']}")

    print(f"\nTop Hashtags:")
    for tag, count in list(analysis['top_hashtags'].items())[:5]:
        print(f"  #{tag}: {count}")

    print(f"\nTop Mentions:")
    for mention, count in list(analysis['top_mentions'].items())[:5]:
        print(f"  @{mention}: {count}")

    print(f"\nTotal Engagement: {analysis['total_engagement']:,}")

    # Save
    output_file = save_signals(signals, output_dir)
    print(f"\nSaved to: {output_file}")

    # Top tweets by engagement
    print("\n" + "=" * 60)
    print("TOP TWEETS BY ENGAGEMENT")
    print("=" * 60)

    sorted_signals = sorted(signals, key=lambda s: s.metrics.get('engagement', 0), reverse=True)
    for i, s in enumerate(sorted_signals[:10], 1):
        print(f"\n{i}. @{s.author}")
        print(f"   {s.name}")
        print(f"   \u2764\ufe0f {s.metrics['likes']} | \ud83d\udd01 {s.metrics['retweets']} | \ud83d\udcac {s.metrics['replies']} | Sentiment: {s.metrics['sentiment_label']}")

    return signals


if __name__ == "__main__":
    main()
