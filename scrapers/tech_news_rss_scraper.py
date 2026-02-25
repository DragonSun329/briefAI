# -*- coding: utf-8 -*-
"""
Tech News RSS Scraper

Scrapes AI news from major tech publications via RSS feeds.
Sources: TechCrunch, VentureBeat, The Verge, Ars Technica, MIT Tech Review
"""

import feedparser
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import json
import time
import re
import hashlib


@dataclass
class NewsArticle:
    """Scraped news article."""
    id: str
    title: str
    url: str
    source: str
    source_id: str
    published_at: Optional[datetime]
    summary: str
    author: Optional[str]
    categories: List[str]
    ai_relevance_score: float  # 0-1, how relevant to AI
    sentiment_keywords: List[str]


class TechNewsRSSScraper:
    """Scraper for tech news RSS feeds."""
    
    # RSS Feed configurations
    RSS_FEEDS = {
        "techcrunch_ai": {
            "name": "TechCrunch AI",
            "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
            "credibility": 8,
            "focus": ["funding", "product", "startup"],
        },
        "venturebeat_ai": {
            "name": "VentureBeat AI",
            "url": "https://venturebeat.com/category/ai/feed/",
            "credibility": 8,
            "focus": ["enterprise", "research", "product"],
        },
        "theverge_ai": {
            "name": "The Verge AI",
            "url": "https://www.theverge.com/rss/ai/index.xml",
            "credibility": 8,
            "focus": ["consumer", "product", "policy"],
        },
        "arstechnica": {
            "name": "Ars Technica",
            "url": "https://feeds.arstechnica.com/arstechnica/technology-lab",
            "credibility": 9,
            "focus": ["technical", "analysis"],
        },
        "mit_tech_review": {
            "name": "MIT Technology Review",
            "url": "https://www.technologyreview.com/feed/",
            "credibility": 10,
            "focus": ["research", "analysis", "policy"],
        },
        "wired": {
            "name": "Wired",
            "url": "https://www.wired.com/feed/category/business/latest/rss",
            "credibility": 8,
            "focus": ["analysis", "culture"],
        },
        "google_ai_blog": {
            "name": "Google AI Blog",
            "url": "https://blog.google/technology/ai/rss/",
            "credibility": 10,
            "focus": ["research", "product"],
        },
        "nvidia_blog": {
            "name": "NVIDIA Blog",
            "url": "https://blogs.nvidia.com/feed/",
            "credibility": 9,
            "focus": ["product", "technical"],
        },
        # Added Jan 28, 2026
        "cnbc_tech": {
            "name": "CNBC Tech",
            "url": "https://www.cnbc.com/id/19854910/device/rss/rss.html",
            "credibility": 8,
            "focus": ["financial", "market"],
        },
        "zdnet_ai": {
            "name": "ZDNet AI",
            "url": "https://www.zdnet.com/topic/artificial-intelligence/rss.xml",
            "credibility": 7,
            "focus": ["enterprise", "product"],
        },
        "ieee_spectrum": {
            "name": "IEEE Spectrum AI",
            "url": "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss",
            "credibility": 9,
            "focus": ["engineering", "research"],
        },
        "the_register": {
            "name": "The Register AI/ML",
            "url": "https://www.theregister.com/software/ai_ml/headlines.atom",
            "credibility": 7,
            "focus": ["technical", "news"],
        },
        "technode": {
            "name": "TechNode (China Tech)",
            "url": "https://technode.com/feed/",
            "credibility": 8,
            "focus": ["china", "startup"],
        },
        "arxiv_cs_lg": {
            "name": "ArXiv Machine Learning",
            "url": "http://arxiv.org/rss/cs.LG",
            "credibility": 10,
            "focus": ["research", "papers"],
        },
        # Latent Space disabled - feed URL changed
        # "latent_space": {
        #     "name": "Latent Space Podcast",
        #     "url": "https://api.substack.com/feed/podcast/1084089.rss",
        #     "credibility": 9,
        #     "focus": ["engineering", "insider"],
        # },
    }
    
    # AI-related keywords for relevance scoring
    AI_KEYWORDS = {
        "high": [
            "artificial intelligence", "machine learning", "deep learning",
            "llm", "large language model", "gpt", "chatgpt", "claude",
            "anthropic", "openai", "deepmind", "gemini", "copilot",
            "neural network", "transformer", "diffusion", "generative ai",
        ],
        "medium": [
            "ai", "ml", "automation", "algorithm", "model", "training",
            "inference", "gpu", "chip", "semiconductor", "nvidia", "amd",
            "data center", "cloud computing", "autonomous",
        ],
        "low": [
            "technology", "tech", "software", "startup", "funding",
            "robot", "computer", "digital",
        ],
    }
    
    SENTIMENT_KEYWORDS = {
        "positive": [
            "breakthrough", "revolutionary", "launch", "release", "announces",
            "partnership", "funding", "raises", "growth", "record", "success",
        ],
        "negative": [
            "layoff", "cuts", "decline", "concern", "risk", "lawsuit",
            "investigation", "delay", "fail", "struggle", "warning",
        ],
    }
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "news_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BriefAI/2.0 (News Aggregator; contact@briefai.dev)"
        })
    
    def fetch_feed(self, feed_id: str) -> List[Dict[str, Any]]:
        """Fetch and parse an RSS feed."""
        if feed_id not in self.RSS_FEEDS:
            print(f"Unknown feed: {feed_id}")
            return []
        
        config = self.RSS_FEEDS[feed_id]
        print(f"  Fetching {config['name']}...")
        
        try:
            feed = feedparser.parse(config["url"])
            
            if feed.bozo and feed.bozo_exception:
                print(f"    Warning: Feed parsing issue - {feed.bozo_exception}")
            
            entries = []
            for entry in feed.entries[:50]:  # Limit to 50 per feed
                entries.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", entry.get("description", "")),
                    "published": entry.get("published", entry.get("updated", "")),
                    "author": entry.get("author", ""),
                    "tags": [t.get("term", "") for t in entry.get("tags", [])],
                })
            
            print(f"    Got {len(entries)} entries")
            return entries
            
        except Exception as e:
            print(f"    Error fetching {feed_id}: {e}")
            return []
    
    def calculate_ai_relevance(self, text: str) -> float:
        """Calculate AI relevance score (0-1) based on keywords.

        Uses diminishing returns to avoid score inflation:
        - First high match: +0.35, extras: +0.10 each (max 3 extra)
        - Medium matches: +0.10 each (max 2)
        - Low matches: +0.05 each (max 2)
        Max possible: 0.35 + 0.30 + 0.20 + 0.10 = 0.95
        """
        text_lower = text.lower()

        high_hits = sum(1 for kw in self.AI_KEYWORDS["high"] if kw in text_lower)
        med_hits = sum(1 for kw in self.AI_KEYWORDS["medium"] if kw in text_lower)
        low_hits = sum(1 for kw in self.AI_KEYWORDS["low"] if kw in text_lower)

        score = 0.0
        if high_hits >= 1:
            score += 0.35 + min(3, high_hits - 1) * 0.10
        score += min(2, med_hits) * 0.10
        score += min(2, low_hits) * 0.05

        return min(round(score, 2), 1.0)
    
    def extract_sentiment_keywords(self, text: str) -> List[str]:
        """Extract sentiment-indicating keywords."""
        text_lower = text.lower()
        found = []
        
        for kw in self.SENTIMENT_KEYWORDS["positive"]:
            if kw in text_lower:
                found.append(f"+{kw}")
        
        for kw in self.SENTIMENT_KEYWORDS["negative"]:
            if kw in text_lower:
                found.append(f"-{kw}")
        
        return found
    
    def parse_published_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats from RSS feeds."""
        if not date_str:
            return None
        
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        return None
    
    def process_entry(self, entry: Dict[str, Any], feed_id: str) -> NewsArticle:
        """Process a feed entry into a NewsArticle."""
        config = self.RSS_FEEDS[feed_id]
        
        # Generate unique ID from URL
        url_hash = hashlib.md5(entry["link"].encode()).hexdigest()[:12]
        article_id = f"{feed_id}_{url_hash}"
        
        # Combine title and summary for analysis
        full_text = f"{entry['title']} {entry['summary']}"
        
        return NewsArticle(
            id=article_id,
            title=entry["title"],
            url=entry["link"],
            source=config["name"],
            source_id=feed_id,
            published_at=self.parse_published_date(entry["published"]),
            summary=entry["summary"][:500] if entry["summary"] else "",
            author=entry["author"],
            categories=entry["tags"] + config["focus"],
            ai_relevance_score=self.calculate_ai_relevance(full_text),
            sentiment_keywords=self.extract_sentiment_keywords(full_text),
        )
    
    def scrape_all_feeds(self, min_relevance: float = 0.2) -> List[NewsArticle]:
        """Scrape all configured RSS feeds."""
        all_articles = []
        
        print(f"Scraping {len(self.RSS_FEEDS)} RSS feeds...")
        
        for feed_id in self.RSS_FEEDS:
            entries = self.fetch_feed(feed_id)
            
            for entry in entries:
                article = self.process_entry(entry, feed_id)
                
                # Filter by AI relevance
                if article.ai_relevance_score >= min_relevance:
                    all_articles.append(article)
            
            time.sleep(1)  # Rate limiting
        
        # Sort by relevance
        all_articles.sort(key=lambda a: a.ai_relevance_score, reverse=True)
        
        print(f"\nTotal: {len(all_articles)} AI-relevant articles")
        return all_articles
    
    def save_results(self, articles: List[NewsArticle], filename: Optional[str] = None):
        """Save scraped articles to JSON."""
        if filename is None:
            filename = f"tech_news_{datetime.now().strftime('%Y-%m-%d')}.json"
        
        output_path = self.output_dir / filename
        
        data = {
            "scraped_at": datetime.now().isoformat(),
            "source": "tech_news_rss",
            "article_count": len(articles),
            "articles": [asdict(a) for a in articles],
        }
        
        # Convert datetime objects to strings
        for article in data["articles"]:
            if article["published_at"]:
                article["published_at"] = article["published_at"].isoformat()
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"Saved to {output_path}")
        return output_path
    
    def to_signal_observations(self, articles: List[NewsArticle]) -> List[Dict[str, Any]]:
        """Convert articles to signal observation format for briefAI."""
        observations = []
        
        for article in articles:
            # Extract entities from title (simple approach)
            entities = self._extract_entities(article.title)
            
            for entity in entities:
                obs = {
                    "entity_name": entity,
                    "source_id": f"news_{article.source_id}",
                    "category": "media",
                    "raw_value": 5.0 + (article.ai_relevance_score * 4),  # 5-9 scale
                    "raw_data": {
                        "source": article.source,
                        "headline": article.title,
                        "url": article.url,
                        "summary": article.summary[:200],
                        "published_at": article.published_at.isoformat() if article.published_at else None,
                        "ai_relevance": article.ai_relevance_score,
                        "sentiment_keywords": article.sentiment_keywords,
                        "signal_type": "news_coverage",
                    },
                    "confidence": min(0.6 + article.ai_relevance_score * 0.3, 0.95),
                }
                observations.append(obs)
        
        return observations
    
    def _extract_entities(self, title: str) -> List[str]:
        """Extract company/product entities from title."""
        # Known entities to look for
        known_entities = [
            "OpenAI", "Anthropic", "Google", "Meta", "Microsoft", "NVIDIA",
            "AMD", "Apple", "Amazon", "Tesla", "Palantir", "Snowflake",
            "DeepMind", "Stability AI", "Midjourney", "Hugging Face",
            "Databricks", "Scale AI", "Cohere", "AI21", "Inflection",
            "xAI", "Mistral", "Perplexity", "Character.AI",
            "ChatGPT", "Claude", "Gemini", "GPT-4", "GPT-5", "Llama",
            "Copilot", "Bard", "Grok",
        ]
        
        found = []
        title_lower = title.lower()
        
        for entity in known_entities:
            if entity.lower() in title_lower:
                found.append(entity)
        
        return found if found else ["AI Industry"]  # Default entity


def run_scraper():
    """Run the tech news RSS scraper."""
    scraper = TechNewsRSSScraper()
    
    print("=" * 60)
    print("TECH NEWS RSS SCRAPER")
    print("=" * 60)
    
    articles = scraper.scrape_all_feeds(min_relevance=0.2)
    
    if articles:
        # Save raw results
        scraper.save_results(articles)
        
        # Show top articles
        print("\n" + "=" * 60)
        print("TOP 10 AI-RELEVANT ARTICLES")
        print("=" * 60)
        
        for i, article in enumerate(articles[:10], 1):
            print(f"\n{i}. [{article.source}] {article.title[:70]}...")
            print(f"   Relevance: {article.ai_relevance_score:.2f} | {article.url[:50]}...")
        
        # Convert to signals
        signals = scraper.to_signal_observations(articles[:30])  # Top 30
        print(f"\n{len(signals)} signal observations ready for briefAI")
        
        return articles
    
    return []


if __name__ == "__main__":
    run_scraper()
