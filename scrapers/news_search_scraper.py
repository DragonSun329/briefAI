"""
News Search Scraper for NAS (Narrative Attention Score)

Fetches AI-related news from multiple free/freemium APIs to improve NAS coverage.

Supported APIs:
1. NewsAPI.org (free tier: 100 requests/day)
2. GNews.io (free tier: 100 requests/day)
3. MediaStack (free tier: 500 requests/month)

These APIs search across thousands of news sources, providing much broader
coverage than RSS feeds alone.

Output: data/alternative_signals/news_search_YYYY-MM-DD.json
"""

import os
import json
import requests
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from pathlib import Path
from collections import defaultdict

# Load .env file
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


@dataclass
class NewsArticle:
    """News article data from search APIs."""
    title: str
    url: str
    source: str                          # e.g., "TechCrunch", "Wired"
    published_date: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    author: Optional[str] = None
    image_url: Optional[str] = None
    api_source: str = ""                 # Which API found this


@dataclass
class NewsSignal:
    """Unified signal format for bucket tagging."""
    name: str                            # Title as name
    source_type: str = "news_search"
    signal_type: str = "news_article"
    entity_type: str = "narrative"       # NAS = Narrative Attention Score
    description: Optional[str] = None
    url: str = ""
    category: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    source: str = ""                     # News source name
    date_observed: str = field(default_factory=lambda: date.today().isoformat())


# AI-related search queries for comprehensive coverage
AI_SEARCH_QUERIES = [
    # Core AI topics
    "artificial intelligence",
    "machine learning",
    "large language model",
    "generative AI",
    "ChatGPT OR Claude OR GPT-4",

    # Technical domains
    "AI chips semiconductor",
    "autonomous vehicles AI",
    "robotics AI automation",
    "computer vision AI",
    "natural language processing",

    # Industry applications
    "AI healthcare diagnosis",
    "AI finance trading",
    "AI enterprise automation",
    "AI cybersecurity",
    "AI education learning",

    # Companies and ecosystem
    "OpenAI Anthropic Google AI",
    "NVIDIA AI GPU",
    "Microsoft Copilot AI",
    "AI startup funding",

    # Trends
    "AI regulation policy",
    "AI safety alignment",
    "AI agents autonomous",
    "multimodal AI vision",
]


class NewsAPIClient:
    """
    Client for NewsAPI.org

    Free tier: 100 requests/day, articles up to 1 month old
    Docs: https://newsapi.org/docs
    """

    BASE_URL = "https://newsapi.org/v2"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("NEWSAPI_KEY")
        self.session = requests.Session()

    def search(
        self,
        query: str,
        days_back: int = 7,
        page_size: int = 50,
        language: str = "en"
    ) -> List[NewsArticle]:
        """
        Search for news articles.

        Args:
            query: Search query
            days_back: How far back to search
            page_size: Max results (100 max for free tier)
            language: Language code
        """
        if not self.api_key:
            return []

        articles = []
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        try:
            response = self.session.get(
                f"{self.BASE_URL}/everything",
                params={
                    "q": query,
                    "from": from_date,
                    "sortBy": "relevancy",
                    "pageSize": min(page_size, 100),
                    "language": language,
                    "apiKey": self.api_key,
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                for item in data.get("articles", []):
                    article = NewsArticle(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        source=item.get("source", {}).get("name", "Unknown"),
                        published_date=item.get("publishedAt"),
                        description=item.get("description"),
                        content=item.get("content"),
                        author=item.get("author"),
                        image_url=item.get("urlToImage"),
                        api_source="newsapi"
                    )
                    if article.title and article.url:
                        articles.append(article)
            elif response.status_code == 401:
                print("  NewsAPI: Invalid API key")
            elif response.status_code == 429:
                print("  NewsAPI: Rate limit exceeded")
            else:
                print(f"  NewsAPI error: {response.status_code}")

        except Exception as e:
            print(f"  NewsAPI error: {e}")

        return articles


class GNewsClient:
    """
    Client for GNews.io

    Free tier: 100 requests/day, articles up to 7 days old
    Docs: https://gnews.io/docs
    """

    BASE_URL = "https://gnews.io/api/v4"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GNEWS_KEY")
        self.session = requests.Session()

    def search(
        self,
        query: str,
        max_results: int = 50,
        language: str = "en"
    ) -> List[NewsArticle]:
        """
        Search for news articles.

        Args:
            query: Search query
            max_results: Max results (10 max for free tier per request)
            language: Language code
        """
        if not self.api_key:
            return []

        articles = []

        try:
            response = self.session.get(
                f"{self.BASE_URL}/search",
                params={
                    "q": query,
                    "max": min(max_results, 10),  # Free tier limit
                    "lang": language,
                    "token": self.api_key,
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                for item in data.get("articles", []):
                    article = NewsArticle(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        source=item.get("source", {}).get("name", "Unknown"),
                        published_date=item.get("publishedAt"),
                        description=item.get("description"),
                        content=item.get("content"),
                        image_url=item.get("image"),
                        api_source="gnews"
                    )
                    if article.title and article.url:
                        articles.append(article)
            elif response.status_code == 403:
                print("  GNews: Invalid API key or quota exceeded")
            else:
                print(f"  GNews error: {response.status_code}")

        except Exception as e:
            print(f"  GNews error: {e}")

        return articles


class MediaStackClient:
    """
    Client for MediaStack.com

    Free tier: 500 requests/month, no historical data
    Docs: https://mediastack.com/documentation
    """

    BASE_URL = "http://api.mediastack.com/v1"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("MEDIASTACK_KEY")
        self.session = requests.Session()

    def search(
        self,
        keywords: str,
        limit: int = 50,
        languages: str = "en"
    ) -> List[NewsArticle]:
        """
        Search for news articles.

        Args:
            keywords: Search keywords
            limit: Max results (25 for free tier)
            languages: Comma-separated language codes
        """
        if not self.api_key:
            return []

        articles = []

        try:
            response = self.session.get(
                f"{self.BASE_URL}/news",
                params={
                    "access_key": self.api_key,
                    "keywords": keywords,
                    "limit": min(limit, 25),
                    "languages": languages,
                    "sort": "published_desc",
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                for item in data.get("data", []):
                    article = NewsArticle(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        source=item.get("source", "Unknown"),
                        published_date=item.get("published_at"),
                        description=item.get("description"),
                        author=item.get("author"),
                        image_url=item.get("image"),
                        api_source="mediastack"
                    )
                    if article.title and article.url:
                        articles.append(article)
            else:
                error = response.json().get("error", {})
                print(f"  MediaStack error: {error.get('message', response.status_code)}")

        except Exception as e:
            print(f"  MediaStack error: {e}")

        return articles


class NewsSearchScraper:
    """
    Unified news search scraper using multiple APIs.

    Aggregates results from all available APIs for maximum coverage.
    """

    def __init__(
        self,
        newsapi_key: Optional[str] = None,
        gnews_key: Optional[str] = None,
        mediastack_key: Optional[str] = None
    ):
        self.newsapi = NewsAPIClient(newsapi_key)
        self.gnews = GNewsClient(gnews_key)
        self.mediastack = MediaStackClient(mediastack_key)

        # Track which APIs are available
        self.available_apis = []
        if self.newsapi.api_key:
            self.available_apis.append("newsapi")
        if self.gnews.api_key:
            self.available_apis.append("gnews")
        if self.mediastack.api_key:
            self.available_apis.append("mediastack")

    def search_all_queries(
        self,
        queries: Optional[List[str]] = None,
        max_per_query: int = 20
    ) -> List[NewsArticle]:
        """
        Search all AI-related queries across all available APIs.

        Args:
            queries: Custom queries (defaults to AI_SEARCH_QUERIES)
            max_per_query: Max articles per query per API

        Returns:
            Deduplicated list of news articles
        """
        if not self.available_apis:
            print("WARNING: No news API keys configured!")
            print("Set one or more environment variables:")
            print("  - NEWSAPI_KEY (from newsapi.org)")
            print("  - GNEWS_KEY (from gnews.io)")
            print("  - MEDIASTACK_KEY (from mediastack.com)")
            return []

        queries = queries or AI_SEARCH_QUERIES
        all_articles = []
        seen_urls = set()

        print(f"Available APIs: {', '.join(self.available_apis)}")
        print(f"Searching {len(queries)} queries...")

        for i, query in enumerate(queries, 1):
            print(f"\n[{i}/{len(queries)}] Query: {query[:50]}...")

            query_articles = []

            # NewsAPI
            if "newsapi" in self.available_apis:
                articles = self.newsapi.search(query, page_size=max_per_query)
                query_articles.extend(articles)
                print(f"  NewsAPI: {len(articles)} articles")

            # GNews
            if "gnews" in self.available_apis:
                articles = self.gnews.search(query, max_results=max_per_query)
                query_articles.extend(articles)
                print(f"  GNews: {len(articles)} articles")

            # MediaStack
            if "mediastack" in self.available_apis:
                articles = self.mediastack.search(query, limit=max_per_query)
                query_articles.extend(articles)
                print(f"  MediaStack: {len(articles)} articles")

            # Dedupe by URL
            for article in query_articles:
                if article.url not in seen_urls:
                    seen_urls.add(article.url)
                    all_articles.append(article)

        print(f"\nTotal unique articles: {len(all_articles)}")
        return all_articles

    def search_topic(self, topic: str, max_results: int = 50) -> List[NewsArticle]:
        """
        Search for a specific topic across all APIs.

        Args:
            topic: Search topic
            max_results: Max results per API
        """
        all_articles = []
        seen_urls = set()

        if "newsapi" in self.available_apis:
            articles = self.newsapi.search(topic, page_size=max_results)
            for a in articles:
                if a.url not in seen_urls:
                    seen_urls.add(a.url)
                    all_articles.append(a)

        if "gnews" in self.available_apis:
            articles = self.gnews.search(topic, max_results=min(max_results, 10))
            for a in articles:
                if a.url not in seen_urls:
                    seen_urls.add(a.url)
                    all_articles.append(a)

        if "mediastack" in self.available_apis:
            articles = self.mediastack.search(topic, limit=min(max_results, 25))
            for a in articles:
                if a.url not in seen_urls:
                    seen_urls.add(a.url)
                    all_articles.append(a)

        return all_articles


def convert_to_signals(articles: List[NewsArticle]) -> List[NewsSignal]:
    """Convert news articles to unified signal format for bucket tagging."""
    signals = []

    for article in articles:
        signal = NewsSignal(
            name=article.title,
            source_type="news_search",
            signal_type="news_article",
            entity_type="narrative",
            description=article.description,
            url=article.url,
            category=f"news/{article.source}",
            source=article.source,
            metrics={
                "published_date": article.published_date,
                "api_source": article.api_source,
                "has_content": bool(article.content),
            }
        )
        signals.append(signal)

    return signals


def save_signals(articles: List[NewsArticle], output_dir: Path) -> Path:
    """Save articles to JSON file in signal format."""
    output_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    output_file = output_dir / f"news_search_{today}.json"

    # Convert to signal format
    signals = convert_to_signals(articles)
    data = [asdict(s) for s in signals]

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return output_file


def analyze_coverage(articles: List[NewsArticle]) -> Dict[str, Any]:
    """Analyze source and topic coverage."""
    sources = defaultdict(int)
    apis = defaultdict(int)

    for article in articles:
        sources[article.source] += 1
        apis[article.api_source] += 1

    return {
        "total_articles": len(articles),
        "unique_sources": len(sources),
        "top_sources": dict(sorted(sources.items(), key=lambda x: -x[1])[:20]),
        "by_api": dict(apis),
    }


def main():
    """Main scraper workflow."""
    print("=" * 60)
    print("NEWS SEARCH SCRAPER")
    print("Fetching AI news from multiple APIs for NAS improvement")
    print("=" * 60)
    print()

    output_dir = Path(__file__).parent.parent / "data" / "alternative_signals"

    # Initialize scraper
    scraper = NewsSearchScraper()

    if not scraper.available_apis:
        print("\nTo enable news search, set API keys in environment:")
        print()
        print("  # NewsAPI.org (100 free requests/day)")
        print("  set NEWSAPI_KEY=your_key_here")
        print()
        print("  # GNews.io (100 free requests/day)")
        print("  set GNEWS_KEY=your_key_here")
        print()
        print("  # MediaStack.com (500 free requests/month)")
        print("  set MEDIASTACK_KEY=your_key_here")
        print()
        print("Get free API keys from:")
        print("  - https://newsapi.org/register")
        print("  - https://gnews.io/")
        print("  - https://mediastack.com/signup/free")
        return

    # Search all AI queries
    print()
    articles = scraper.search_all_queries(max_per_query=20)

    if not articles:
        print("No articles found!")
        return

    # Analyze coverage
    print("\n" + "=" * 60)
    print("COVERAGE ANALYSIS")
    print("=" * 60)
    coverage = analyze_coverage(articles)
    print(f"Total articles: {coverage['total_articles']}")
    print(f"Unique sources: {coverage['unique_sources']}")
    print(f"\nBy API:")
    for api, count in coverage["by_api"].items():
        print(f"  {api}: {count}")
    print(f"\nTop 10 sources:")
    for source, count in list(coverage["top_sources"].items())[:10]:
        print(f"  {source}: {count}")

    # Save
    output_file = save_signals(articles, output_dir)
    print(f"\nSaved to: {output_file}")

    # Sample articles
    print("\n" + "=" * 60)
    print("SAMPLE ARTICLES")
    print("=" * 60)
    for article in articles[:10]:
        print(f"\n{article.title[:80]}...")
        print(f"  Source: {article.source} ({article.api_source})")
        print(f"  URL: {article.url[:60]}...")


if __name__ == "__main__":
    main()