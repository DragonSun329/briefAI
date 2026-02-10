"""
X/Twitter Browser Scraper for AI Public Opinions

Uses Playwright to scrape public Twitter/X content without API keys.
Scrapes search results, trending topics, and AI influencer accounts.

Features:
- Search AI-related tweets
- Track AI influencer accounts
- Extract engagement metrics
- Sentiment analysis

Requirements:
- playwright installed: pip install playwright
- browsers installed: playwright install chromium

Output: data/alternative_signals/twitter_browser_YYYY-MM-DD.json
"""

import asyncio
import json
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from urllib.parse import quote

try:
    from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    raise


@dataclass
class Tweet:
    """Tweet data structure."""
    text: str
    author_name: str
    author_handle: str
    url: str = ""
    timestamp: Optional[str] = None
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    views: int = 0
    is_retweet: bool = False
    is_quote: bool = False
    hashtags: List[str] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)


@dataclass
class TwitterSignal:
    """Signal format for trend radar integration."""
    name: str
    source_type: str = "twitter_browser"
    signal_type: str = "social_sentiment"
    entity_type: str = "tweet"
    description: Optional[str] = None
    url: str = ""
    category: str = ""
    author: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    date_observed: str = field(default_factory=lambda: date.today().isoformat())


# AI-related search queries
AI_SEARCH_QUERIES = [
    "ChatGPT",
    "Claude AI",
    "GPT-4",
    "OpenAI",
    "Anthropic AI",
    "generative AI",
    "LLM",
    "AI agents",
    "Stable Diffusion",
    "Midjourney",
]

# AI influencer accounts to track
AI_ACCOUNTS = [
    "OpenAI",
    "AnthropicAI",
    "GoogleAI",
    "xaboratory",
    "sama",           # Sam Altman
    "ylecun",         # Yann LeCun
    "kaboratorypathy",      # Andrej Karpathy
    "emaboratoryhassab",    # Emad Mostaque
]

# Sentiment keywords
POSITIVE_KEYWORDS = [
    "amazing", "impressive", "breakthrough", "revolutionary", "game-changer",
    "love", "excellent", "incredible", "fantastic", "best", "awesome",
    "excited", "promising", "innovative", "powerful", "bullish",
]

NEGATIVE_KEYWORDS = [
    "terrible", "broken", "useless", "disappointing", "overhyped",
    "hate", "worst", "garbage", "scam", "dangerous", "concerning",
    "worried", "scary", "threat", "doom", "bearish", "job loss",
]


class TwitterBrowserScraper:
    """
    Scrapes Twitter/X using Playwright browser automation.

    Works without API keys by simulating browser behavior.
    """

    def __init__(self, headless: bool = True):
        """
        Initialize the scraper.

        Args:
            headless: Run browser in headless mode (no visible window)
        """
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.tweets_collected: List[Tweet] = []

    async def start(self):
        """Start the browser."""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )

        # Create context with realistic settings
        context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
        )

        self.page = await context.new_page()

        # Block unnecessary resources for speed
        await self.page.route("**/*.{png,jpg,jpeg,gif,svg,ico}", lambda route: route.abort())
        await self.page.route("**/analytics/**", lambda route: route.abort())

    async def close(self):
        """Close the browser."""
        if self.browser:
            await self.browser.close()

    async def search_tweets(self, query: str, max_tweets: int = 30, scroll_count: int = 3) -> List[Tweet]:
        """
        Search for tweets matching a query.

        Args:
            query: Search query
            max_tweets: Maximum tweets to collect
            scroll_count: Number of times to scroll for more tweets
        """
        if not self.page:
            await self.start()

        tweets = []
        encoded_query = quote(query)
        url = f"https://x.com/search?q={encoded_query}&src=typed_query&f=live"

        print(f"  Searching: {query}")

        try:
            await self.page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)  # Wait for dynamic content

            # Check for login wall
            if await self._check_login_wall():
                print("    Login wall detected - skipping")
                return tweets

            # Scroll and collect tweets
            for i in range(scroll_count):
                new_tweets = await self._extract_tweets_from_page()
                for tweet in new_tweets:
                    if tweet.text not in [t.text for t in tweets]:
                        tweets.append(tweet)
                        if len(tweets) >= max_tweets:
                            break

                if len(tweets) >= max_tweets:
                    break

                # Scroll down
                await self.page.evaluate('window.scrollBy(0, 1000)')
                await asyncio.sleep(1.5)

            print(f"    Found {len(tweets)} tweets")

        except PlaywrightTimeout:
            print(f"    Timeout loading search results")
        except Exception as e:
            print(f"    Error: {e}")

        return tweets

    async def get_user_tweets(self, username: str, max_tweets: int = 20) -> List[Tweet]:
        """
        Get recent tweets from a user's profile.

        Args:
            username: Twitter username (without @)
            max_tweets: Maximum tweets to collect
        """
        if not self.page:
            await self.start()

        tweets = []
        url = f"https://x.com/{username}"

        print(f"  Fetching @{username}...")

        try:
            await self.page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)

            # Check for login wall or protected account
            if await self._check_login_wall():
                print("    Login wall detected - skipping")
                return tweets

            # Check if account exists
            page_content = await self.page.content()
            if "This account doesn't exist" in page_content:
                print(f"    Account @{username} not found")
                return tweets

            # Scroll and collect
            for i in range(2):
                new_tweets = await self._extract_tweets_from_page()
                for tweet in new_tweets:
                    if tweet.author_handle.lower() == username.lower():
                        if tweet.text not in [t.text for t in tweets]:
                            tweets.append(tweet)

                if len(tweets) >= max_tweets:
                    break

                await self.page.evaluate('window.scrollBy(0, 800)')
                await asyncio.sleep(1)

            print(f"    Found {len(tweets)} tweets")

        except PlaywrightTimeout:
            print(f"    Timeout loading @{username}")
        except Exception as e:
            print(f"    Error: {e}")

        return tweets

    async def _check_login_wall(self) -> bool:
        """Check if Twitter is showing a login wall."""
        try:
            # Common login wall indicators
            login_indicators = [
                'text="Sign in"',
                'text="Log in"',
                '[data-testid="loginButton"]',
                'text="Sign up"',
            ]

            for indicator in login_indicators:
                try:
                    element = await self.page.query_selector(indicator)
                    if element:
                        # Check if it's prominently displayed (login wall)
                        box = await element.bounding_box()
                        if box and box['y'] < 300:  # Near top of page
                            return True
                except:
                    continue

            return False
        except:
            return False

    async def _extract_tweets_from_page(self) -> List[Tweet]:
        """Extract tweets from current page content."""
        tweets = []

        try:
            # Find tweet articles
            tweet_elements = await self.page.query_selector_all('article[data-testid="tweet"]')

            for element in tweet_elements:
                try:
                    tweet = await self._parse_tweet_element(element)
                    if tweet:
                        tweets.append(tweet)
                except Exception as e:
                    continue

        except Exception as e:
            print(f"    Error extracting tweets: {e}")

        return tweets

    async def _parse_tweet_element(self, element) -> Optional[Tweet]:
        """Parse a tweet from a DOM element."""
        try:
            # Get tweet text
            text_elem = await element.query_selector('[data-testid="tweetText"]')
            text = await text_elem.inner_text() if text_elem else ""

            if not text:
                return None

            # Get author info
            author_elem = await element.query_selector('[data-testid="User-Name"]')
            author_text = await author_elem.inner_text() if author_elem else ""

            # Parse author name and handle
            author_parts = author_text.split('\n') if author_text else []
            author_name = author_parts[0] if len(author_parts) > 0 else "Unknown"
            author_handle = ""
            for part in author_parts:
                if part.startswith('@'):
                    author_handle = part[1:]  # Remove @
                    break

            # Get engagement metrics
            likes = await self._get_metric(element, 'like')
            retweets = await self._get_metric(element, 'retweet')
            replies = await self._get_metric(element, 'reply')

            # Get tweet URL
            url = ""
            link_elem = await element.query_selector('a[href*="/status/"]')
            if link_elem:
                href = await link_elem.get_attribute('href')
                if href:
                    url = f"https://x.com{href}" if href.startswith('/') else href

            # Get timestamp
            timestamp = None
            time_elem = await element.query_selector('time')
            if time_elem:
                timestamp = await time_elem.get_attribute('datetime')

            # Extract hashtags and mentions
            hashtags = re.findall(r'#(\w+)', text)
            mentions = re.findall(r'@(\w+)', text)

            # Check if retweet
            is_retweet = 'reposted' in author_text.lower() if author_text else False

            return Tweet(
                text=text,
                author_name=author_name,
                author_handle=author_handle,
                url=url,
                timestamp=timestamp,
                likes=likes,
                retweets=retweets,
                replies=replies,
                hashtags=hashtags,
                mentions=mentions,
                is_retweet=is_retweet,
            )

        except Exception as e:
            return None

    async def _get_metric(self, element, metric_type: str) -> int:
        """Extract engagement metric from tweet element."""
        try:
            selector = f'[data-testid="{metric_type}"] span'
            metric_elem = await element.query_selector(selector)
            if metric_elem:
                text = await metric_elem.inner_text()
                return self._parse_count(text)
        except:
            pass
        return 0

    def _parse_count(self, text: str) -> int:
        """Parse count from text (handles K, M suffixes)."""
        if not text:
            return 0
        text = text.strip().upper()
        try:
            if 'K' in text:
                return int(float(text.replace('K', '')) * 1000)
            elif 'M' in text:
                return int(float(text.replace('M', '')) * 1000000)
            else:
                return int(text.replace(',', ''))
        except:
            return 0


def analyze_sentiment(tweet: Tweet) -> Dict[str, Any]:
    """Analyze sentiment of a tweet."""
    text_lower = tweet.text.lower()

    positive = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
    negative = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)

    if positive + negative == 0:
        score = 0
        label = "neutral"
    else:
        score = (positive - negative) / (positive + negative)
        label = "positive" if score > 0.2 else "negative" if score < -0.2 else "neutral"

    return {"score": round(score, 2), "label": label}


def convert_to_signals(tweets: List[Tweet]) -> List[TwitterSignal]:
    """Convert tweets to signal format."""
    signals = []
    seen_texts = set()

    for tweet in tweets:
        # Deduplicate by text
        if tweet.text in seen_texts:
            continue
        seen_texts.add(tweet.text)

        sentiment = analyze_sentiment(tweet)
        engagement = tweet.likes + tweet.retweets * 2 + tweet.replies

        signal = TwitterSignal(
            name=tweet.text[:100] + "..." if len(tweet.text) > 100 else tweet.text,
            source_type="twitter_browser",
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
                "engagement": engagement,
                "hashtags": tweet.hashtags,
                "mentions": tweet.mentions,
                "sentiment_score": sentiment["score"],
                "sentiment_label": sentiment["label"],
                "timestamp": tweet.timestamp,
            }
        )
        signals.append(signal)

    return signals


def save_signals(signals: List[TwitterSignal], output_dir: Path) -> Path:
    """Save signals to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    output_file = output_dir / f"twitter_browser_{today}.json"

    data = [asdict(s) for s in signals]

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return output_file


async def main():
    """Main scraper workflow."""
    print("=" * 60)
    print("X/TWITTER BROWSER SCRAPER")
    print("Using Playwright - No API Keys Required")
    print("=" * 60)

    output_dir = Path(__file__).parent.parent / "data" / "alternative_signals"

    scraper = TwitterBrowserScraper(headless=True)
    all_tweets = []

    try:
        await scraper.start()

        # Search AI topics
        print("\n[1/2] Searching AI topics...")
        print("-" * 40)

        for query in AI_SEARCH_QUERIES[:5]:  # Limit to avoid detection
            tweets = await scraper.search_tweets(query, max_tweets=20, scroll_count=2)
            all_tweets.extend(tweets)
            await asyncio.sleep(2)  # Rate limiting

        # Get tweets from AI accounts
        print("\n[2/2] Fetching AI influencer accounts...")
        print("-" * 40)

        for account in AI_ACCOUNTS[:5]:  # Limit to avoid detection
            tweets = await scraper.get_user_tweets(account, max_tweets=10)
            all_tweets.extend(tweets)
            await asyncio.sleep(2)

    finally:
        await scraper.close()

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    if not all_tweets:
        print("No tweets collected. Twitter may be blocking access.")
        print("Try running with headless=False to see what's happening.")
        return

    # Convert and save
    signals = convert_to_signals(all_tweets)
    print(f"Total tweets: {len(all_tweets)}")
    print(f"Unique signals: {len(signals)}")

    # Sentiment analysis
    sentiments = [analyze_sentiment(t) for t in all_tweets]
    positive = sum(1 for s in sentiments if s['label'] == 'positive')
    negative = sum(1 for s in sentiments if s['label'] == 'negative')
    neutral = len(sentiments) - positive - negative

    avg_score = sum(s['score'] for s in sentiments) / len(sentiments) if sentiments else 0

    print(f"\nSentiment: {'POSITIVE' if avg_score > 0.1 else 'NEGATIVE' if avg_score < -0.1 else 'NEUTRAL'} ({avg_score:.3f})")
    print(f"  Positive: {positive} | Neutral: {neutral} | Negative: {negative}")

    # Save
    output_file = save_signals(signals, output_dir)
    print(f"\nSaved to: {output_file}")

    # Top tweets
    print("\n" + "-" * 40)
    print("TOP TWEETS BY ENGAGEMENT")
    print("-" * 40)

    sorted_signals = sorted(signals, key=lambda s: s.metrics.get('engagement', 0), reverse=True)
    for i, s in enumerate(sorted_signals[:5], 1):
        print(f"\n{i}. @{s.author}")
        print(f"   {s.name}")
        print(f"   ❤️ {s.metrics['likes']} | 🔁 {s.metrics['retweets']} | 💬 {s.metrics['replies']}")


if __name__ == "__main__":
    asyncio.run(main())
