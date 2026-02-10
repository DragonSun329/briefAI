"""
Threads (Meta) Browser Scraper for AI Public Opinions

Uses Playwright to scrape public Threads content without API keys.
Scrapes search results and AI influencer accounts.

Features:
- Search AI-related posts
- Track AI influencer accounts
- Extract engagement metrics
- Sentiment analysis

Requirements:
- playwright installed: pip install playwright
- browsers installed: playwright install chromium

Output: data/alternative_signals/threads_browser_YYYY-MM-DD.json
"""

import asyncio
import json
import re
from datetime import date
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from urllib.parse import quote

try:
    from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    raise


@dataclass
class ThreadPost:
    """Thread post data structure."""
    text: str
    author_name: str
    author_handle: str
    url: str = ""
    timestamp: Optional[str] = None
    likes: int = 0
    replies: int = 0
    reposts: int = 0
    is_repost: bool = False
    hashtags: List[str] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)


@dataclass
class ThreadsSignal:
    """Signal format for trend radar integration."""
    name: str
    source_type: str = "threads_browser"
    signal_type: str = "social_sentiment"
    entity_type: str = "thread"
    description: Optional[str] = None
    url: str = ""
    category: str = ""
    author: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    date_observed: str = field(default_factory=lambda: date.today().isoformat())


# AI-related search queries
AI_SEARCH_QUERIES = [
    "artificial intelligence",
    "ChatGPT",
    "AI",
    "machine learning",
    "OpenAI",
    "Claude AI",
    "generative AI",
    "AI tools",
    "LLM",
    "GPT",
]

# AI influencer accounts on Threads
AI_ACCOUNTS = [
    "zuck",              # Mark Zuckerberg
    "satlonapatel",      # Satya Nadella
    "sundarpichai",      # Sundar Pichai
    "elonmusk",          # Elon Musk
    "sama",              # Sam Altman
    "lexfridman",        # Lex Fridman
    "garaboratoryrytan",         # Gary Tan (YC)
    "timurban",          # Tim Urban (Wait But Why)
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


class ThreadsBrowserScraper:
    """
    Scrapes Threads using Playwright browser automation.

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
        await self.page.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2}", lambda route: route.abort())
        await self.page.route("**/logging/**", lambda route: route.abort())

    async def close(self):
        """Close the browser."""
        if self.browser:
            await self.browser.close()

    async def search_posts(self, query: str, max_posts: int = 30, scroll_count: int = 3) -> List[ThreadPost]:
        """
        Search for posts matching a query.

        Args:
            query: Search query
            max_posts: Maximum posts to collect
            scroll_count: Number of times to scroll for more posts
        """
        if not self.page:
            await self.start()

        posts = []
        encoded_query = quote(query)
        url = f"https://www.threads.net/search?q={encoded_query}&serp_type=default"

        print(f"  Searching: {query}")

        try:
            await self.page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)  # Wait for dynamic content

            # Check for login wall
            if await self._check_login_required():
                print("    Login required - skipping")
                return posts

            # Scroll and collect posts
            for i in range(scroll_count):
                new_posts = await self._extract_posts_from_page()
                for post in new_posts:
                    if post.text not in [p.text for p in posts]:
                        posts.append(post)
                        if len(posts) >= max_posts:
                            break

                if len(posts) >= max_posts:
                    break

                # Scroll down
                await self.page.evaluate('window.scrollBy(0, 1000)')
                await asyncio.sleep(2)

            print(f"    Found {len(posts)} posts")

        except PlaywrightTimeout:
            print(f"    Timeout loading search results")
        except Exception as e:
            print(f"    Error: {e}")

        return posts

    async def get_user_posts(self, username: str, max_posts: int = 20) -> List[ThreadPost]:
        """
        Get recent posts from a user's profile.

        Args:
            username: Threads username (without @)
            max_posts: Maximum posts to collect
        """
        if not self.page:
            await self.start()

        posts = []
        url = f"https://www.threads.net/@{username}"

        print(f"  Fetching @{username}...")

        try:
            await self.page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)

            # Check for login wall or private account
            if await self._check_login_required():
                print("    Login required - skipping")
                return posts

            page_content = await self.page.content()
            if "Sorry, this page isn't available" in page_content:
                print(f"    Account @{username} not found")
                return posts

            # Scroll and collect
            for i in range(2):
                new_posts = await self._extract_posts_from_page()
                for post in new_posts:
                    if post.text not in [p.text for p in posts]:
                        posts.append(post)

                if len(posts) >= max_posts:
                    break

                await self.page.evaluate('window.scrollBy(0, 800)')
                await asyncio.sleep(1.5)

            print(f"    Found {len(posts)} posts")

        except PlaywrightTimeout:
            print(f"    Timeout loading @{username}")
        except Exception as e:
            print(f"    Error: {e}")

        return posts

    async def _check_login_required(self) -> bool:
        """Check if Threads is requiring login."""
        try:
            page_content = await self.page.content()
            login_indicators = [
                "Log in to see this",
                "Sign up to see",
                "Log in with Instagram",
                "Create an account",
            ]
            return any(indicator in page_content for indicator in login_indicators)
        except:
            return False

    async def _extract_posts_from_page(self) -> List[ThreadPost]:
        """Extract posts from current page content."""
        posts = []

        try:
            # Threads uses various selectors - try multiple approaches
            # Method 1: Look for post containers
            post_containers = await self.page.query_selector_all('[data-pressable-container="true"]')

            if not post_containers:
                # Method 2: Look for article-like elements
                post_containers = await self.page.query_selector_all('div[role="article"]')

            for container in post_containers:
                try:
                    post = await self._parse_post_element(container)
                    if post and len(post.text) > 10:
                        posts.append(post)
                except Exception as e:
                    continue

            # Method 3: Try extracting from raw HTML if above didn't work
            if not posts:
                posts = await self._extract_posts_from_html()

        except Exception as e:
            print(f"    Error extracting posts: {e}")

        return posts

    async def _parse_post_element(self, element) -> Optional[ThreadPost]:
        """Parse a post from a DOM element."""
        try:
            # Get all text content
            text_content = await element.inner_text()

            if not text_content or len(text_content) < 10:
                return None

            # Parse the text content to extract components
            lines = text_content.split('\n')
            lines = [l.strip() for l in lines if l.strip()]

            if len(lines) < 2:
                return None

            # First line is usually author info
            author_info = lines[0]
            author_name = author_info.split('@')[0].strip() if '@' in author_info else author_info
            author_handle = ""

            # Find handle
            for line in lines[:3]:
                if '@' in line:
                    match = re.search(r'@(\w+)', line)
                    if match:
                        author_handle = match.group(1)
                        break

            # Find the main text (usually the longest non-metadata line)
            text = ""
            for line in lines[1:]:
                # Skip lines that look like metadata
                if any(x in line.lower() for x in ['like', 'reply', 'repost', 'share', 'ago', 'hour', 'minute', 'day']):
                    continue
                if len(line) > len(text):
                    text = line

            if not text or len(text) < 10:
                return None

            # Extract metrics (look for numbers followed by likes/replies)
            likes = 0
            replies = 0
            reposts = 0

            for line in lines:
                line_lower = line.lower()
                if 'like' in line_lower:
                    match = re.search(r'(\d+[KkMm]?)\s*like', line_lower)
                    if match:
                        likes = self._parse_count(match.group(1))
                if 'repl' in line_lower:
                    match = re.search(r'(\d+[KkMm]?)\s*repl', line_lower)
                    if match:
                        replies = self._parse_count(match.group(1))
                if 'repost' in line_lower:
                    match = re.search(r'(\d+[KkMm]?)\s*repost', line_lower)
                    if match:
                        reposts = self._parse_count(match.group(1))

            # Get URL if available
            url = ""
            link_elem = await element.query_selector('a[href*="/post/"]')
            if link_elem:
                href = await link_elem.get_attribute('href')
                if href:
                    url = f"https://www.threads.net{href}" if href.startswith('/') else href

            # Extract hashtags and mentions
            hashtags = re.findall(r'#(\w+)', text)
            mentions = re.findall(r'@(\w+)', text)

            return ThreadPost(
                text=text,
                author_name=author_name,
                author_handle=author_handle,
                url=url,
                likes=likes,
                replies=replies,
                reposts=reposts,
                hashtags=hashtags,
                mentions=mentions,
            )

        except Exception as e:
            return None

    async def _extract_posts_from_html(self) -> List[ThreadPost]:
        """Fallback method: extract posts directly from HTML."""
        posts = []

        try:
            html = await self.page.content()

            # Look for text content patterns
            # This is a fallback and may need adjustment based on Threads' actual structure

            # Pattern for post content
            text_pattern = r'<span[^>]*>([^<]{50,500})</span>'
            matches = re.findall(text_pattern, html)

            for text in matches[:10]:
                # Clean up HTML entities
                text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                text = re.sub(r'<[^>]+>', '', text)  # Remove any remaining tags

                if len(text) > 30:
                    posts.append(ThreadPost(
                        text=text,
                        author_name="Unknown",
                        author_handle="",
                    ))

        except Exception as e:
            pass

        return posts

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


def analyze_sentiment(post: ThreadPost) -> Dict[str, Any]:
    """Analyze sentiment of a post."""
    text_lower = post.text.lower()

    positive = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
    negative = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)

    if positive + negative == 0:
        score = 0
        label = "neutral"
    else:
        score = (positive - negative) / (positive + negative)
        label = "positive" if score > 0.2 else "negative" if score < -0.2 else "neutral"

    return {"score": round(score, 2), "label": label}


def convert_to_signals(posts: List[ThreadPost]) -> List[ThreadsSignal]:
    """Convert posts to signal format."""
    signals = []
    seen_texts = set()

    for post in posts:
        # Deduplicate by text
        if post.text in seen_texts:
            continue
        seen_texts.add(post.text)

        sentiment = analyze_sentiment(post)
        engagement = post.likes + post.reposts * 2 + post.replies

        signal = ThreadsSignal(
            name=post.text[:100] + "..." if len(post.text) > 100 else post.text,
            source_type="threads_browser",
            signal_type="social_sentiment",
            entity_type="thread",
            description=post.text,
            url=post.url,
            category=f"threads/{post.author_handle}" if post.author_handle else "threads/unknown",
            author=post.author_handle,
            metrics={
                "likes": post.likes,
                "reposts": post.reposts,
                "replies": post.replies,
                "engagement": engagement,
                "hashtags": post.hashtags,
                "mentions": post.mentions,
                "sentiment_score": sentiment["score"],
                "sentiment_label": sentiment["label"],
                "timestamp": post.timestamp,
            }
        )
        signals.append(signal)

    return signals


def save_signals(signals: List[ThreadsSignal], output_dir: Path) -> Path:
    """Save signals to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    output_file = output_dir / f"threads_browser_{today}.json"

    data = [asdict(s) for s in signals]

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return output_file


async def main():
    """Main scraper workflow."""
    print("=" * 60)
    print("THREADS (META) BROWSER SCRAPER")
    print("Using Playwright - No API Keys Required")
    print("=" * 60)

    output_dir = Path(__file__).parent.parent / "data" / "alternative_signals"

    scraper = ThreadsBrowserScraper(headless=True)
    all_posts = []

    try:
        await scraper.start()

        # Search AI topics
        print("\n[1/2] Searching AI topics on Threads...")
        print("-" * 40)

        for query in AI_SEARCH_QUERIES[:5]:  # Limit to avoid detection
            posts = await scraper.search_posts(query, max_posts=15, scroll_count=2)
            all_posts.extend(posts)
            await asyncio.sleep(3)  # Rate limiting

        # Get posts from AI-related accounts
        print("\n[2/2] Fetching posts from tech leaders...")
        print("-" * 40)

        for account in AI_ACCOUNTS[:5]:  # Limit to avoid detection
            posts = await scraper.get_user_posts(account, max_posts=10)
            all_posts.extend(posts)
            await asyncio.sleep(3)

    finally:
        await scraper.close()

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    if not all_posts:
        print("No posts collected. Threads may require login or be blocking access.")
        print("Try running with headless=False to see what's happening.")
        return

    # Convert and save
    signals = convert_to_signals(all_posts)
    print(f"Total posts: {len(all_posts)}")
    print(f"Unique signals: {len(signals)}")

    # Sentiment analysis
    sentiments = [analyze_sentiment(p) for p in all_posts]
    positive = sum(1 for s in sentiments if s['label'] == 'positive')
    negative = sum(1 for s in sentiments if s['label'] == 'negative')
    neutral = len(sentiments) - positive - negative

    avg_score = sum(s['score'] for s in sentiments) / len(sentiments) if sentiments else 0

    print(f"\nSentiment: {'POSITIVE' if avg_score > 0.1 else 'NEGATIVE' if avg_score < -0.1 else 'NEUTRAL'} ({avg_score:.3f})")
    print(f"  Positive: {positive} | Neutral: {neutral} | Negative: {negative}")

    # Save
    output_file = save_signals(signals, output_dir)
    print(f"\nSaved to: {output_file}")

    # Top posts
    print("\n" + "-" * 40)
    print("TOP POSTS BY ENGAGEMENT")
    print("-" * 40)

    sorted_signals = sorted(signals, key=lambda s: s.metrics.get('engagement', 0), reverse=True)
    for i, s in enumerate(sorted_signals[:5], 1):
        print(f"\n{i}. @{s.author if s.author else 'unknown'}")
        print(f"   {s.name}")
        print(f"   ❤️ {s.metrics['likes']} | 🔄 {s.metrics['reposts']} | 💬 {s.metrics['replies']}")


if __name__ == "__main__":
    asyncio.run(main())
