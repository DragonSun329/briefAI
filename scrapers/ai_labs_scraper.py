"""
AI Labs News Scraper for Tech Trend Analysis

Scrapes news, blog posts, and research updates from major AI research labs
to track emerging technology trends and research directions.

Tracked Labs:
- DeepMind (Google)
- OpenAI
- Anthropic
- Meta AI (FAIR)
- Google AI / Google Research
- Microsoft Research
- NVIDIA Research
- Stability AI
- Mistral AI
- Cohere
- xAI
- Hugging Face
- Allen AI (AI2)
- EleutherAI

Data Sources:
1. Official blogs (RSS feeds where available)
2. News aggregation (Google News, Bing News)
3. Press releases
4. Research paper announcements

Output: data/alternative_signals/ai_labs_news_YYYY-MM-DD.json
"""

import requests
from bs4 import BeautifulSoup
import feedparser
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import defaultdict
from urllib.parse import quote, urljoin
import json
import time
import re
import random


@dataclass
class AILabArticle:
    """AI Lab news/blog article."""
    title: str
    url: str
    lab: str                              # Which AI lab
    source_type: str                      # blog, news, research, press
    published_date: Optional[str] = None
    summary: Optional[str] = None
    content_preview: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    research_areas: List[str] = field(default_factory=list)


@dataclass
class AILabSignal:
    """Signal format for trend radar integration."""
    name: str
    source_type: str = "ai_labs"
    signal_type: str = "research_news"
    entity_type: str = "ai_lab"
    description: Optional[str] = None
    url: str = ""
    category: str = ""
    lab: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    date_observed: str = field(default_factory=lambda: date.today().isoformat())


# AI Labs Configuration
AI_LABS = {
    "deepmind": {
        "name": "DeepMind",
        "parent": "Google",
        "blog_url": "https://deepmind.google/discover/blog/",
        "rss_url": "https://deepmind.google/blog/rss.xml",
        "news_query": "DeepMind AI",
        "focus_areas": ["reinforcement learning", "protein folding", "game AI", "neuroscience", "safety"],
    },
    "openai": {
        "name": "OpenAI",
        "parent": None,
        "blog_url": "https://openai.com/blog",
        "rss_url": None,  # No public RSS
        "news_query": "OpenAI",
        "focus_areas": ["GPT", "DALL-E", "ChatGPT", "safety", "alignment", "reasoning"],
    },
    "anthropic": {
        "name": "Anthropic",
        "parent": None,
        "blog_url": "https://www.anthropic.com/news",
        "rss_url": None,
        "news_query": "Anthropic AI Claude",
        "focus_areas": ["Claude", "constitutional AI", "safety", "interpretability", "alignment"],
    },
    "meta_ai": {
        "name": "Meta AI (FAIR)",
        "parent": "Meta",
        "blog_url": "https://ai.meta.com/blog/",
        "rss_url": None,
        "news_query": "Meta AI FAIR LLaMA",
        "focus_areas": ["LLaMA", "open source", "vision", "speech", "translation"],
    },
    "google_ai": {
        "name": "Google AI",
        "parent": "Google",
        "blog_url": "https://blog.google/technology/ai/",
        "rss_url": None,
        "news_query": "Google AI Gemini Bard",
        "focus_areas": ["Gemini", "Bard", "PaLM", "TPU", "multimodal"],
    },
    "microsoft_research": {
        "name": "Microsoft Research",
        "parent": "Microsoft",
        "blog_url": "https://www.microsoft.com/en-us/research/blog/",
        "rss_url": "https://www.microsoft.com/en-us/research/feed/",
        "news_query": "Microsoft AI Research Copilot",
        "focus_areas": ["Copilot", "Azure AI", "productivity", "coding", "enterprise"],
    },
    "nvidia_research": {
        "name": "NVIDIA Research",
        "parent": "NVIDIA",
        "blog_url": "https://blogs.nvidia.com/blog/category/deep-learning/",
        "rss_url": None,
        "news_query": "NVIDIA AI research GPU",
        "focus_areas": ["GPU", "CUDA", "inference", "training", "robotics", "automotive"],
    },
    "stability_ai": {
        "name": "Stability AI",
        "parent": None,
        "blog_url": "https://stability.ai/news",
        "rss_url": None,
        "news_query": "Stability AI Stable Diffusion",
        "focus_areas": ["Stable Diffusion", "image generation", "open source", "creative AI"],
    },
    "mistral_ai": {
        "name": "Mistral AI",
        "parent": None,
        "blog_url": "https://mistral.ai/news/",
        "rss_url": None,
        "news_query": "Mistral AI",
        "focus_areas": ["open weights", "efficiency", "European AI", "enterprise"],
    },
    "cohere": {
        "name": "Cohere",
        "parent": None,
        "blog_url": "https://cohere.com/blog",
        "rss_url": None,
        "news_query": "Cohere AI enterprise",
        "focus_areas": ["enterprise NLP", "RAG", "embeddings", "search"],
    },
    "xai": {
        "name": "xAI",
        "parent": None,
        "blog_url": "https://x.ai/",
        "rss_url": None,
        "news_query": "xAI Grok Elon Musk",
        "focus_areas": ["Grok", "reasoning", "real-time"],
    },
    "huggingface": {
        "name": "Hugging Face",
        "parent": None,
        "blog_url": "https://huggingface.co/blog",
        "rss_url": "https://huggingface.co/blog/feed.xml",
        "news_query": "Hugging Face AI",
        "focus_areas": ["open source", "transformers", "datasets", "community", "hub"],
    },
    "allen_ai": {
        "name": "Allen AI (AI2)",
        "parent": None,
        "blog_url": "https://allenai.org/blog",
        "rss_url": None,
        "news_query": "Allen AI AI2 research",
        "focus_areas": ["scientific AI", "NLP", "common sense", "open research"],
    },
    "eleuther_ai": {
        "name": "EleutherAI",
        "parent": None,
        "blog_url": "https://blog.eleuther.ai/",
        "rss_url": "https://blog.eleuther.ai/rss/",
        "news_query": "EleutherAI open source LLM",
        "focus_areas": ["open source", "GPT-NeoX", "evaluation", "interpretability"],
    },
}

# Research area keywords for tagging
RESEARCH_AREAS = {
    "llm": ["large language model", "llm", "gpt", "transformer", "language model"],
    "multimodal": ["multimodal", "vision-language", "image-text", "audio", "video"],
    "reinforcement_learning": ["reinforcement learning", "rl", "reward", "agent", "policy"],
    "safety": ["safety", "alignment", "harm", "bias", "fairness", "responsible"],
    "reasoning": ["reasoning", "chain of thought", "cot", "logic", "math"],
    "code": ["code", "programming", "coding", "developer", "software"],
    "robotics": ["robotics", "robot", "embodied", "manipulation", "navigation"],
    "efficiency": ["efficiency", "quantization", "distillation", "compression", "inference"],
    "open_source": ["open source", "open weights", "release", "available", "community"],
    "enterprise": ["enterprise", "business", "commercial", "deployment", "production"],
    "image_gen": ["image generation", "diffusion", "stable diffusion", "dall-e", "midjourney"],
    "speech": ["speech", "audio", "voice", "tts", "asr", "transcription"],
    "science": ["science", "protein", "drug", "medical", "biology", "chemistry"],
}


class AILabsBlogScraper:
    """Scrapes official AI lab blogs."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
        self.last_request = 0
        self.min_delay = 2.0

    def _rate_limit(self):
        elapsed = time.time() - self.last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed + random.uniform(0.1, 0.5))
        self.last_request = time.time()

    def scrape_rss_feed(self, lab_id: str, rss_url: str, limit: int = 20) -> List[AILabArticle]:
        """Scrape articles from RSS feed."""
        articles = []
        lab_config = AI_LABS.get(lab_id, {})
        lab_name = lab_config.get("name", lab_id)

        print(f"  Fetching RSS: {lab_name}...")

        try:
            feed = feedparser.parse(rss_url)

            for entry in feed.entries[:limit]:
                # Extract date
                pub_date = None
                if hasattr(entry, 'published'):
                    pub_date = entry.published
                elif hasattr(entry, 'updated'):
                    pub_date = entry.updated

                # Extract summary/content
                summary = ""
                if hasattr(entry, 'summary'):
                    summary = BeautifulSoup(entry.summary, 'html.parser').get_text()[:500]
                elif hasattr(entry, 'description'):
                    summary = BeautifulSoup(entry.description, 'html.parser').get_text()[:500]

                # Extract tags
                tags = []
                if hasattr(entry, 'tags'):
                    tags = [t.term for t in entry.tags if hasattr(t, 'term')]

                # Detect research areas
                text_to_analyze = f"{entry.title} {summary}".lower()
                research_areas = self._detect_research_areas(text_to_analyze)

                article = AILabArticle(
                    title=entry.title,
                    url=entry.link,
                    lab=lab_name,
                    source_type="blog",
                    published_date=pub_date,
                    summary=summary,
                    tags=tags,
                    research_areas=research_areas,
                )
                articles.append(article)

            print(f"    Found {len(articles)} articles")

        except Exception as e:
            print(f"    Error: {e}")

        return articles

    def scrape_blog_page(self, lab_id: str, blog_url: str, limit: int = 15) -> List[AILabArticle]:
        """Scrape articles from blog page HTML."""
        articles = []
        lab_config = AI_LABS.get(lab_id, {})
        lab_name = lab_config.get("name", lab_id)

        print(f"  Scraping blog: {lab_name}...")
        self._rate_limit()

        try:
            response = self.session.get(blog_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Generic article extraction - look for common patterns
            article_selectors = [
                'article',
                'div[class*="post"]',
                'div[class*="article"]',
                'div[class*="blog"]',
                'div[class*="card"]',
                'a[href*="/blog/"]',
                'a[href*="/news/"]',
            ]

            found_articles = []
            for selector in article_selectors:
                elements = soup.select(selector)
                if elements:
                    found_articles = elements[:limit]
                    break

            for elem in found_articles:
                try:
                    # Extract title
                    title = ""
                    title_elem = elem.find(['h1', 'h2', 'h3', 'h4'])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                    elif elem.name == 'a':
                        title = elem.get_text(strip=True)

                    if not title or len(title) < 10:
                        continue

                    # Extract URL
                    url = ""
                    if elem.name == 'a':
                        url = elem.get('href', '')
                    else:
                        link = elem.find('a')
                        if link:
                            url = link.get('href', '')

                    if url and not url.startswith('http'):
                        url = urljoin(blog_url, url)

                    if not url:
                        continue

                    # Extract summary
                    summary = ""
                    desc_elem = elem.find(['p', 'div[class*="excerpt"]', 'div[class*="summary"]'])
                    if desc_elem:
                        summary = desc_elem.get_text(strip=True)[:300]

                    # Extract date
                    pub_date = None
                    date_elem = elem.find(['time', 'span[class*="date"]', 'div[class*="date"]'])
                    if date_elem:
                        pub_date = date_elem.get_text(strip=True)

                    # Detect research areas
                    text_to_analyze = f"{title} {summary}".lower()
                    research_areas = self._detect_research_areas(text_to_analyze)

                    article = AILabArticle(
                        title=title,
                        url=url,
                        lab=lab_name,
                        source_type="blog",
                        published_date=pub_date,
                        summary=summary,
                        research_areas=research_areas,
                    )
                    articles.append(article)

                except Exception:
                    continue

            print(f"    Found {len(articles)} articles")

        except Exception as e:
            print(f"    Error: {e}")

        return articles

    def _detect_research_areas(self, text: str) -> List[str]:
        """Detect research areas from text."""
        areas = []
        text_lower = text.lower()

        for area, keywords in RESEARCH_AREAS.items():
            if any(kw in text_lower for kw in keywords):
                areas.append(area)

        return areas


class AILabsNewsScraper:
    """Scrapes news about AI labs from news sources."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self.last_request = 0
        self.min_delay = 2.0

    def _rate_limit(self):
        elapsed = time.time() - self.last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed + random.uniform(0.1, 0.5))
        self.last_request = time.time()

    def search_google_news(self, query: str, lab_name: str, limit: int = 10) -> List[AILabArticle]:
        """Search Google News for AI lab coverage."""
        articles = []
        self._rate_limit()

        print(f"  Searching news: {lab_name}...")

        try:
            # Use Google News RSS feed
            encoded_query = quote(query)
            rss_url = f"https://news.google.com/rss/search?q={encoded_query}+when:7d&hl=en-US&gl=US&ceid=US:en"

            feed = feedparser.parse(rss_url)

            for entry in feed.entries[:limit]:
                # Clean title (Google News adds source)
                title = entry.title
                source = ""
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0]
                    source = parts[1] if len(parts) > 1 else ""

                # Extract date
                pub_date = entry.get('published', None)

                # Detect research areas
                text_to_analyze = f"{title}".lower()
                research_areas = self._detect_research_areas(text_to_analyze)

                article = AILabArticle(
                    title=title,
                    url=entry.link,
                    lab=lab_name,
                    source_type="news",
                    published_date=pub_date,
                    summary=f"Source: {source}" if source else None,
                    research_areas=research_areas,
                )
                articles.append(article)

            print(f"    Found {len(articles)} news articles")

        except Exception as e:
            print(f"    Error: {e}")

        return articles

    def _detect_research_areas(self, text: str) -> List[str]:
        """Detect research areas from text."""
        areas = []
        text_lower = text.lower()

        for area, keywords in RESEARCH_AREAS.items():
            if any(kw in text_lower for kw in keywords):
                areas.append(area)

        return areas


class AILabsAggregator:
    """Aggregates news from all AI labs."""

    def __init__(self):
        self.blog_scraper = AILabsBlogScraper()
        self.news_scraper = AILabsNewsScraper()

    def collect_all(
        self,
        labs: Optional[List[str]] = None,
        include_blogs: bool = True,
        include_news: bool = True,
    ) -> List[AILabArticle]:
        """Collect articles from all AI labs."""
        all_articles = []

        # Default to all labs if not specified
        labs_to_scrape = labs or list(AI_LABS.keys())

        for lab_id in labs_to_scrape:
            lab_config = AI_LABS.get(lab_id)
            if not lab_config:
                continue

            lab_name = lab_config["name"]
            print(f"\n{'='*50}")
            print(f"{lab_name}")
            print('='*50)

            # Scrape blog
            if include_blogs:
                if lab_config.get("rss_url"):
                    articles = self.blog_scraper.scrape_rss_feed(
                        lab_id, lab_config["rss_url"], limit=15
                    )
                    all_articles.extend(articles)
                elif lab_config.get("blog_url"):
                    articles = self.blog_scraper.scrape_blog_page(
                        lab_id, lab_config["blog_url"], limit=10
                    )
                    all_articles.extend(articles)

            # Search news
            if include_news and lab_config.get("news_query"):
                articles = self.news_scraper.search_google_news(
                    lab_config["news_query"], lab_name, limit=10
                )
                all_articles.extend(articles)

            time.sleep(1)

        return all_articles


def convert_to_signals(articles: List[AILabArticle]) -> List[AILabSignal]:
    """Convert articles to signal format."""
    signals = []
    seen_urls = set()

    for article in articles:
        # Deduplicate
        if article.url in seen_urls:
            continue
        seen_urls.add(article.url)

        signal = AILabSignal(
            name=article.title,
            source_type="ai_labs",
            signal_type="research_news",
            entity_type="ai_lab",
            description=article.summary,
            url=article.url,
            category=f"ai_labs/{article.lab.lower().replace(' ', '_')}",
            lab=article.lab,
            metrics={
                "source_type": article.source_type,
                "published_date": article.published_date,
                "research_areas": article.research_areas,
                "tags": article.tags,
                "authors": article.authors,
            }
        )
        signals.append(signal)

    return signals


def analyze_coverage(articles: List[AILabArticle]) -> Dict[str, Any]:
    """Analyze lab and research area coverage."""
    labs = defaultdict(int)
    source_types = defaultdict(int)
    research_areas = defaultdict(int)

    for article in articles:
        labs[article.lab] += 1
        source_types[article.source_type] += 1
        for area in article.research_areas:
            research_areas[area] += 1

    return {
        "total_articles": len(articles),
        "by_lab": dict(sorted(labs.items(), key=lambda x: -x[1])),
        "by_source": dict(source_types),
        "by_research_area": dict(sorted(research_areas.items(), key=lambda x: -x[1])),
    }


def save_signals(signals: List[AILabSignal], output_dir: Path) -> Path:
    """Save signals to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    output_file = output_dir / f"ai_labs_news_{today}.json"

    data = [asdict(s) for s in signals]

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return output_file


def main():
    """Main scraper workflow."""
    print("=" * 60)
    print("AI LABS NEWS SCRAPER")
    print("Tracking Tech Trends from Major Research Labs")
    print("=" * 60)

    output_dir = Path(__file__).parent.parent / "data" / "alternative_signals"

    # Initialize aggregator
    aggregator = AILabsAggregator()

    # Collect from all labs
    print("\nCollecting news from AI research labs...")
    all_articles = aggregator.collect_all()

    print("\n" + "=" * 60)
    print("PROCESSING")
    print("=" * 60)

    # Convert to signals
    signals = convert_to_signals(all_articles)
    print(f"Total articles: {len(all_articles)}")
    print(f"Unique signals: {len(signals)}")

    # Analyze coverage
    print("\n" + "=" * 60)
    print("COVERAGE ANALYSIS")
    print("=" * 60)

    analysis = analyze_coverage(all_articles)

    print(f"\nBy AI Lab:")
    for lab, count in list(analysis["by_lab"].items())[:10]:
        print(f"  {lab}: {count}")

    print(f"\nBy Source Type:")
    for source, count in analysis["by_source"].items():
        print(f"  {source}: {count}")

    print(f"\nTop Research Areas:")
    for area, count in list(analysis["by_research_area"].items())[:10]:
        print(f"  {area}: {count}")

    # Save
    output_file = save_signals(signals, output_dir)
    print(f"\nSaved to: {output_file}")

    # Sample articles
    print("\n" + "=" * 60)
    print("RECENT ARTICLES")
    print("=" * 60)

    for article in all_articles[:15]:
        print(f"\n[{article.lab}] {article.title[:70]}...")
        if article.research_areas:
            print(f"  Areas: {', '.join(article.research_areas[:3])}")
        print(f"  URL: {article.url[:60]}...")

    return signals


if __name__ == "__main__":
    main()
