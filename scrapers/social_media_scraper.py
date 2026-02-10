"""
Social Media Scraper for AI Public Opinions (No API Keys Required)

Scrapes AI-related discussions from multiple public social platforms:
1. Reddit (via old.reddit.com - no API needed)
2. Hacker News (public JSON API - no auth)
3. Lemmy instances (federated Reddit alternative)
4. Lobsters (tech community)

These platforms provide valuable public sentiment signals for CSS (Community Sentiment Score).

Output: data/alternative_signals/social_sentiment_YYYY-MM-DD.json
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import defaultdict
from urllib.parse import urljoin, quote
import json
import time
import re
import random


@dataclass
class SocialPost:
    """Unified social media post data."""
    title: str
    url: str
    platform: str                        # reddit, hackernews, lemmy, lobsters
    subreddit: Optional[str] = None      # For Reddit/Lemmy
    author: Optional[str] = None
    score: int = 0                       # Upvotes/points
    num_comments: int = 0
    content: Optional[str] = None        # Self-text or description
    created_utc: Optional[float] = None
    permalink: str = ""
    flair: Optional[str] = None
    sentiment_keywords: List[str] = field(default_factory=list)


@dataclass
class SocialSentimentSignal:
    """Signal format for trend radar integration."""
    name: str
    source_type: str = "social_media"
    signal_type: str = "public_sentiment"
    entity_type: str = "community"
    description: Optional[str] = None
    url: str = ""
    category: str = ""
    platform: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    date_observed: str = field(default_factory=lambda: date.today().isoformat())


# AI-related subreddits to scrape
AI_SUBREDDITS = [
    # Core AI/ML
    "MachineLearning",
    "artificial",
    "deeplearning",
    "learnmachinelearning",

    # LLMs and ChatGPT
    "LocalLLaMA",
    "ChatGPT",
    "ClaudeAI",
    "OpenAI",
    "Bard",

    # AI Applications
    "StableDiffusion",
    "midjourney",
    "singularity",
    "agi",

    # Tech/Programming with AI focus
    "programming",
    "technology",
    "compsci",

    # AI Ethics & Impact
    "ControlProblem",
    "AIethics",
]

# Lemmy AI communities
LEMMY_COMMUNITIES = [
    ("lemmy.ml", "artificial_intelligence"),
    ("lemmy.ml", "machinelearning"),
    ("lemmy.world", "technology"),
    ("programming.dev", "programming"),
]

# AI keywords for filtering and sentiment
AI_KEYWORDS = [
    "llm", "gpt", "claude", "chatgpt", "openai", "anthropic", "gemini", "bard",
    "machine learning", "deep learning", "neural network", "transformer",
    "stable diffusion", "midjourney", "dall-e", "ai art", "generative ai",
    "ai agent", "autonomous", "agi", "artificial general intelligence",
    "fine-tuning", "rag", "retrieval", "embeddings", "vector database",
    "nvidia", "cuda", "gpu", "inference", "quantization",
    "ai safety", "alignment", "ai ethics", "regulation",
]

# Sentiment indicators
POSITIVE_KEYWORDS = [
    "amazing", "impressive", "breakthrough", "revolutionary", "game-changer",
    "love", "excellent", "incredible", "fantastic", "best", "awesome",
    "excited", "promising", "innovative", "powerful", "efficient",
]

NEGATIVE_KEYWORDS = [
    "terrible", "broken", "useless", "disappointing", "overhyped",
    "hate", "worst", "garbage", "scam", "dangerous", "concerning",
    "worried", "scary", "threat", "replace", "layoffs", "job loss",
]


class RedditScraper:
    """
    Scrapes Reddit via JSON API (no authentication required).

    Uses Reddit's public JSON endpoints which don't require API keys.
    Rate limited to be respectful (follows Reddit guidelines).
    """

    BASE_URL = "https://www.reddit.com"

    def __init__(self):
        self.session = requests.Session()
        # Use browser-like headers for better compatibility
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
        })
        self.last_request = 0
        self.min_delay = 2.5  # Slightly longer delay to be safe

    def _rate_limit(self):
        """Ensure we don't hit Reddit too fast."""
        elapsed = time.time() - self.last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed + random.uniform(0.1, 0.5))
        self.last_request = time.time()

    def get_subreddit_posts(
        self,
        subreddit: str,
        sort: str = "hot",  # hot, new, top, rising
        time_filter: str = "week",  # hour, day, week, month, year, all
        limit: int = 25
    ) -> List[SocialPost]:
        """
        Fetch posts from a subreddit using Reddit's JSON API.

        Args:
            subreddit: Subreddit name (without r/)
            sort: Sort method
            time_filter: Time filter for "top" sort
            limit: Max posts to fetch
        """
        posts = []
        self._rate_limit()

        # Build JSON API URL
        if sort == "top":
            url = f"{self.BASE_URL}/r/{subreddit}/top.json?t={time_filter}&limit={limit}"
        else:
            url = f"{self.BASE_URL}/r/{subreddit}/{sort}.json?limit={limit}"

        try:
            print(f"  Fetching r/{subreddit}/{sort}...")
            response = self.session.get(url, timeout=30)

            if response.status_code == 403:
                print(f"    Access denied to r/{subreddit}")
                return posts
            elif response.status_code == 404:
                print(f"    r/{subreddit} not found")
                return posts
            elif response.status_code == 429:
                print(f"    Rate limited, waiting...")
                time.sleep(60)
                return posts

            response.raise_for_status()
            data = response.json()

            # Parse JSON response
            children = data.get('data', {}).get('children', [])

            for child in children[:limit]:
                try:
                    post = self._parse_reddit_json(child.get('data', {}), subreddit)
                    if post:
                        posts.append(post)
                except Exception as e:
                    continue

            print(f"    Found {len(posts)} posts")

        except requests.RequestException as e:
            print(f"    Error fetching r/{subreddit}: {e}")

        return posts

    def _parse_reddit_json(self, post_data: Dict, subreddit: str) -> Optional[SocialPost]:
        """Parse a Reddit post from JSON API response."""
        title = post_data.get('title', '')
        if not title:
            return None

        # Get URL (external link or self post)
        url = post_data.get('url', '')
        if not url or url.startswith('/r/'):
            url = f"https://reddit.com{post_data.get('permalink', '')}"

        permalink = f"https://reddit.com{post_data.get('permalink', '')}"
        score = post_data.get('score', 0)
        num_comments = post_data.get('num_comments', 0)
        author = post_data.get('author', '[deleted]')

        # Get flair
        flair = post_data.get('link_flair_text')

        # Get self-text content
        content = post_data.get('selftext', '')[:500] if post_data.get('selftext') else None

        # Get creation time
        created_utc = post_data.get('created_utc')

        # Extract sentiment keywords
        text_to_analyze = f"{title} {content or ''}"
        sentiment_keywords = self._extract_sentiment(text_to_analyze)

        return SocialPost(
            title=title,
            url=url,
            platform="reddit",
            subreddit=subreddit,
            author=author,
            score=score,
            num_comments=num_comments,
            content=content,
            created_utc=created_utc,
            permalink=permalink,
            flair=flair,
            sentiment_keywords=sentiment_keywords,
        )

    def _extract_sentiment(self, text: str) -> List[str]:
        """Extract sentiment-related keywords from text."""
        text_lower = text.lower()
        found = []

        for kw in POSITIVE_KEYWORDS:
            if kw in text_lower:
                found.append(f"+{kw}")

        for kw in NEGATIVE_KEYWORDS:
            if kw in text_lower:
                found.append(f"-{kw}")

        return found

    def search_reddit(self, query: str, subreddit: Optional[str] = None, limit: int = 25) -> List[SocialPost]:
        """
        Search Reddit for posts matching a query using JSON API.

        Args:
            query: Search query
            subreddit: Optional subreddit to search within
            limit: Max results
        """
        posts = []
        self._rate_limit()

        # Build JSON search URL
        encoded_query = quote(query)
        if subreddit:
            url = f"{self.BASE_URL}/r/{subreddit}/search.json?q={encoded_query}&restrict_sr=on&sort=relevance&t=week&limit={limit}"
        else:
            url = f"{self.BASE_URL}/search.json?q={encoded_query}&sort=relevance&t=week&limit={limit}"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            children = data.get('data', {}).get('children', [])

            for child in children[:limit]:
                try:
                    post_data = child.get('data', {})
                    sub = post_data.get('subreddit', 'unknown')
                    post = self._parse_reddit_json(post_data, sub)
                    if post:
                        posts.append(post)
                except Exception:
                    continue

        except requests.RequestException as e:
            print(f"  Search error: {e}")

        return posts


class HackerNewsScraper:
    """
    Scrapes Hacker News using their public API (no auth needed).

    API docs: https://github.com/HackerNews/API
    """

    API_BASE = "https://hacker-news.firebaseio.com/v0"
    SITE_URL = "https://news.ycombinator.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BriefAI-TrendRadar/1.0",
        })

    def get_top_stories(self, limit: int = 100) -> List[int]:
        """Get IDs of top stories."""
        try:
            response = self.session.get(f"{self.API_BASE}/topstories.json", timeout=30)
            response.raise_for_status()
            return response.json()[:limit]
        except Exception as e:
            print(f"  Error fetching top stories: {e}")
            return []

    def get_new_stories(self, limit: int = 100) -> List[int]:
        """Get IDs of new stories."""
        try:
            response = self.session.get(f"{self.API_BASE}/newstories.json", timeout=30)
            response.raise_for_status()
            return response.json()[:limit]
        except Exception as e:
            print(f"  Error fetching new stories: {e}")
            return []

    def get_best_stories(self, limit: int = 100) -> List[int]:
        """Get IDs of best stories."""
        try:
            response = self.session.get(f"{self.API_BASE}/beststories.json", timeout=30)
            response.raise_for_status()
            return response.json()[:limit]
        except Exception as e:
            print(f"  Error fetching best stories: {e}")
            return []

    def get_item(self, item_id: int) -> Optional[Dict]:
        """Get details of a specific item."""
        try:
            response = self.session.get(f"{self.API_BASE}/item/{item_id}.json", timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def get_ai_stories(self, max_stories: int = 200, ai_limit: int = 50) -> List[SocialPost]:
        """
        Fetch AI-related stories from HN.

        Checks top/new/best stories and filters for AI keywords.
        """
        posts = []
        seen_ids = set()

        print("  Fetching Hacker News stories...")

        # Get story IDs from different feeds
        all_ids = []
        all_ids.extend(self.get_top_stories(max_stories))
        all_ids.extend(self.get_new_stories(max_stories // 2))
        all_ids.extend(self.get_best_stories(max_stories // 2))

        # Deduplicate
        unique_ids = []
        for id in all_ids:
            if id not in seen_ids:
                seen_ids.add(id)
                unique_ids.append(id)

        print(f"    Checking {len(unique_ids)} unique stories...")

        ai_count = 0
        for item_id in unique_ids:
            if ai_count >= ai_limit:
                break

            item = self.get_item(item_id)
            if not item or item.get('type') != 'story':
                continue

            title = item.get('title', '')
            url = item.get('url', '')
            text = item.get('text', '')

            # Check if AI-related
            search_text = f"{title} {url} {text}".lower()
            is_ai_related = any(kw.lower() in search_text for kw in AI_KEYWORDS)

            if not is_ai_related:
                continue

            # Extract sentiment
            sentiment_keywords = []
            for kw in POSITIVE_KEYWORDS:
                if kw in search_text:
                    sentiment_keywords.append(f"+{kw}")
            for kw in NEGATIVE_KEYWORDS:
                if kw in search_text:
                    sentiment_keywords.append(f"-{kw}")

            post = SocialPost(
                title=title,
                url=url if url else f"{self.SITE_URL}/item?id={item_id}",
                platform="hackernews",
                author=item.get('by'),
                score=item.get('score', 0),
                num_comments=len(item.get('kids', [])),
                content=text[:500] if text else None,
                created_utc=item.get('time'),
                permalink=f"{self.SITE_URL}/item?id={item_id}",
                sentiment_keywords=sentiment_keywords,
            )
            posts.append(post)
            ai_count += 1

            time.sleep(0.1)  # Small delay to be nice to the API

        print(f"    Found {len(posts)} AI-related stories")
        return posts


class LemmyScraper:
    """
    Scrapes Lemmy instances (federated Reddit alternative).

    Uses the public Lemmy API which doesn't require authentication for reading.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BriefAI-TrendRadar/1.0",
            "Accept": "application/json",
        })

    def get_community_posts(
        self,
        instance: str,
        community: str,
        sort: str = "Hot",  # Hot, New, Top, Active
        limit: int = 25
    ) -> List[SocialPost]:
        """
        Fetch posts from a Lemmy community.

        Args:
            instance: Lemmy instance domain (e.g., "lemmy.ml")
            community: Community name
            sort: Sort method
            limit: Max posts
        """
        posts = []

        try:
            # Lemmy API endpoint
            url = f"https://{instance}/api/v3/post/list"
            params = {
                "community_name": community,
                "sort": sort,
                "limit": limit,
            }

            print(f"  Fetching {community}@{instance}...")
            response = self.session.get(url, params=params, timeout=30)

            if response.status_code != 200:
                print(f"    Error: {response.status_code}")
                return posts

            data = response.json()

            for item in data.get('posts', []):
                post_data = item.get('post', {})
                counts = item.get('counts', {})
                creator = item.get('creator', {})

                title = post_data.get('name', '')
                url = post_data.get('url', '')
                body = post_data.get('body', '')

                # Extract sentiment
                search_text = f"{title} {body}".lower()
                sentiment_keywords = []
                for kw in POSITIVE_KEYWORDS:
                    if kw in search_text:
                        sentiment_keywords.append(f"+{kw}")
                for kw in NEGATIVE_KEYWORDS:
                    if kw in search_text:
                        sentiment_keywords.append(f"-{kw}")

                post = SocialPost(
                    title=title,
                    url=url if url else post_data.get('ap_id', ''),
                    platform="lemmy",
                    subreddit=f"{community}@{instance}",
                    author=creator.get('name'),
                    score=counts.get('score', 0),
                    num_comments=counts.get('comments', 0),
                    content=body[:500] if body else None,
                    permalink=post_data.get('ap_id', ''),
                    sentiment_keywords=sentiment_keywords,
                )
                posts.append(post)

            print(f"    Found {len(posts)} posts")

        except Exception as e:
            print(f"    Error: {e}")

        return posts


class LobstersScraper:
    """
    Scrapes Lobste.rs (tech-focused community).

    Uses their public JSON feeds.
    """

    BASE_URL = "https://lobste.rs"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BriefAI-TrendRadar/1.0",
            "Accept": "application/json",
        })

    def get_stories(self, page: str = "hottest", limit: int = 50) -> List[SocialPost]:
        """
        Fetch stories from Lobsters.

        Args:
            page: Feed type - "hottest", "newest", "active"
            limit: Max stories to return
        """
        posts = []

        try:
            url = f"{self.BASE_URL}/{page}.json"
            print(f"  Fetching Lobsters {page}...")

            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            stories = response.json()

            for story in stories[:limit]:
                title = story.get('title', '')
                url = story.get('url', '')
                description = story.get('description', '')
                tags = story.get('tags', [])

                # Check if AI-related
                search_text = f"{title} {description} {' '.join(tags)}".lower()
                is_ai_related = any(kw.lower() in search_text for kw in AI_KEYWORDS)

                if not is_ai_related:
                    continue

                # Extract sentiment
                sentiment_keywords = []
                for kw in POSITIVE_KEYWORDS:
                    if kw in search_text:
                        sentiment_keywords.append(f"+{kw}")
                for kw in NEGATIVE_KEYWORDS:
                    if kw in search_text:
                        sentiment_keywords.append(f"-{kw}")

                post = SocialPost(
                    title=title,
                    url=url if url else story.get('short_id_url', ''),
                    platform="lobsters",
                    author=story.get('submitter_user', {}).get('username'),
                    score=story.get('score', 0),
                    num_comments=story.get('comment_count', 0),
                    content=description[:500] if description else None,
                    permalink=story.get('short_id_url', ''),
                    flair=', '.join(tags) if tags else None,
                    sentiment_keywords=sentiment_keywords,
                )
                posts.append(post)

            print(f"    Found {len(posts)} AI-related stories")

        except Exception as e:
            print(f"    Error: {e}")

        return posts


class SocialMediaAggregator:
    """
    Aggregates AI sentiment from multiple social platforms.

    Combines Reddit, HN, Lemmy, and Lobsters into unified signal format.
    """

    def __init__(self):
        self.reddit = RedditScraper()
        self.hn = HackerNewsScraper()
        self.lemmy = LemmyScraper()
        self.lobsters = LobstersScraper()

    def collect_all(
        self,
        reddit_subs: Optional[List[str]] = None,
        lemmy_communities: Optional[List[Tuple[str, str]]] = None,
        include_hn: bool = True,
        include_lobsters: bool = True,
    ) -> List[SocialPost]:
        """
        Collect AI-related posts from all platforms.

        Returns:
            Aggregated list of SocialPost objects
        """
        all_posts = []

        # ============================================================
        # Reddit
        # ============================================================
        print("\n" + "=" * 60)
        print("REDDIT")
        print("=" * 60)

        subs = reddit_subs or AI_SUBREDDITS
        for sub in subs:
            try:
                # Get hot posts
                posts = self.reddit.get_subreddit_posts(sub, sort="hot", limit=15)
                all_posts.extend(posts)

                # Small delay between subreddits
                time.sleep(1)

                # Get top weekly posts
                posts = self.reddit.get_subreddit_posts(sub, sort="top", time_filter="week", limit=10)
                all_posts.extend(posts)

                time.sleep(1)
            except Exception as e:
                print(f"  Error with r/{sub}: {e}")
                continue

        # ============================================================
        # Hacker News
        # ============================================================
        if include_hn:
            print("\n" + "=" * 60)
            print("HACKER NEWS")
            print("=" * 60)

            try:
                hn_posts = self.hn.get_ai_stories(max_stories=200, ai_limit=50)
                all_posts.extend(hn_posts)
            except Exception as e:
                print(f"  Error: {e}")

        # ============================================================
        # Lemmy
        # ============================================================
        print("\n" + "=" * 60)
        print("LEMMY")
        print("=" * 60)

        communities = lemmy_communities or LEMMY_COMMUNITIES
        for instance, community in communities:
            try:
                posts = self.lemmy.get_community_posts(instance, community, limit=20)
                # Filter for AI content
                ai_posts = [p for p in posts if self._is_ai_related(p)]
                all_posts.extend(ai_posts)
                time.sleep(1)
            except Exception as e:
                print(f"  Error with {community}@{instance}: {e}")
                continue

        # ============================================================
        # Lobsters
        # ============================================================
        if include_lobsters:
            print("\n" + "=" * 60)
            print("LOBSTERS")
            print("=" * 60)

            try:
                lobster_posts = self.lobsters.get_stories(limit=100)
                all_posts.extend(lobster_posts)
            except Exception as e:
                print(f"  Error: {e}")

        return all_posts

    def _is_ai_related(self, post: SocialPost) -> bool:
        """Check if a post is AI-related."""
        search_text = f"{post.title} {post.content or ''}".lower()
        return any(kw.lower() in search_text for kw in AI_KEYWORDS)


def convert_to_signals(posts: List[SocialPost]) -> List[SocialSentimentSignal]:
    """Convert posts to unified signal format."""
    signals = []
    seen_urls = set()

    for post in posts:
        # Deduplicate by URL
        if post.url in seen_urls:
            continue
        seen_urls.add(post.url)

        # Calculate basic sentiment score
        positive = len([k for k in post.sentiment_keywords if k.startswith('+')])
        negative = len([k for k in post.sentiment_keywords if k.startswith('-')])
        sentiment_score = (positive - negative) / max(positive + negative, 1)

        signal = SocialSentimentSignal(
            name=post.title,
            source_type="social_media",
            signal_type="public_sentiment",
            entity_type="community",
            description=post.content,
            url=post.url,
            category=f"social/{post.platform}",
            platform=post.platform,
            metrics={
                "score": post.score,
                "num_comments": post.num_comments,
                "subreddit": post.subreddit,
                "author": post.author,
                "flair": post.flair,
                "sentiment_keywords": post.sentiment_keywords,
                "sentiment_score": round(sentiment_score, 2),
                "engagement": post.score + post.num_comments * 2,  # Weighted engagement
            }
        )
        signals.append(signal)

    return signals


def analyze_sentiment(posts: List[SocialPost]) -> Dict[str, Any]:
    """Analyze overall sentiment from collected posts."""
    platforms = defaultdict(list)
    all_sentiments = []

    for post in posts:
        platforms[post.platform].append(post)

        positive = len([k for k in post.sentiment_keywords if k.startswith('+')])
        negative = len([k for k in post.sentiment_keywords if k.startswith('-')])
        if positive + negative > 0:
            score = (positive - negative) / (positive + negative)
            all_sentiments.append(score)

    # Calculate per-platform stats
    platform_stats = {}
    for platform, platform_posts in platforms.items():
        scores = [p.score for p in platform_posts]
        comments = [p.num_comments for p in platform_posts]

        platform_stats[platform] = {
            "count": len(platform_posts),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "total_comments": sum(comments),
            "top_post": max(platform_posts, key=lambda p: p.score).title[:60] if platform_posts else None,
        }

    # Overall sentiment
    avg_sentiment = sum(all_sentiments) / len(all_sentiments) if all_sentiments else 0

    return {
        "total_posts": len(posts),
        "platforms": platform_stats,
        "overall_sentiment": round(avg_sentiment, 3),
        "sentiment_label": "positive" if avg_sentiment > 0.1 else "negative" if avg_sentiment < -0.1 else "neutral",
    }


def save_signals(signals: List[SocialSentimentSignal], output_dir: Path) -> Path:
    """Save signals to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    output_file = output_dir / f"social_sentiment_{today}.json"

    data = [asdict(s) for s in signals]

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return output_file


def main():
    """Main scraper workflow."""
    print("=" * 60)
    print("SOCIAL MEDIA SENTIMENT SCRAPER")
    print("AI Public Opinion Aggregator (No API Keys Required)")
    print("=" * 60)

    output_dir = Path(__file__).parent.parent / "data" / "alternative_signals"

    # Initialize aggregator
    aggregator = SocialMediaAggregator()

    # Collect from all platforms
    print("\nCollecting AI discussions from social platforms...")
    all_posts = aggregator.collect_all()

    print("\n" + "=" * 60)
    print("PROCESSING")
    print("=" * 60)

    # Convert to signals
    signals = convert_to_signals(all_posts)
    print(f"Total unique posts: {len(signals)}")

    # Analyze sentiment
    print("\n" + "=" * 60)
    print("SENTIMENT ANALYSIS")
    print("=" * 60)

    analysis = analyze_sentiment(all_posts)

    print(f"\nOverall sentiment: {analysis['sentiment_label'].upper()} ({analysis['overall_sentiment']:.3f})")
    print(f"\nBy Platform:")
    for platform, stats in analysis['platforms'].items():
        print(f"  {platform}:")
        print(f"    Posts: {stats['count']}")
        print(f"    Avg Score: {stats['avg_score']}")
        print(f"    Total Comments: {stats['total_comments']}")
        if stats['top_post']:
            print(f"    Top: {stats['top_post']}...")

    # Save
    output_file = save_signals(signals, output_dir)
    print(f"\nSaved to: {output_file}")

    # Top posts by engagement
    print("\n" + "=" * 60)
    print("TOP POSTS BY ENGAGEMENT")
    print("=" * 60)

    sorted_signals = sorted(signals, key=lambda s: s.metrics.get('engagement', 0), reverse=True)
    for i, s in enumerate(sorted_signals[:15], 1):
        print(f"\n{i}. [{s.platform}] {s.name[:70]}...")
        print(f"   Score: {s.metrics['score']} | Comments: {s.metrics['num_comments']} | Sentiment: {s.metrics['sentiment_score']}")

    return signals


if __name__ == "__main__":
    main()
