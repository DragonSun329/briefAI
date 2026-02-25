# -*- coding: utf-8 -*-
"""
News Search Scraper — Tavily (primary) + SearXNG (fallback)

Replaces the old NewsAPI/GNews/MediaStack scraper with:
  1. Tavily Search API — purpose-built for AI agents, news topic, date filtering
  2. SearXNG (local) — self-hosted metasearch aggregating Google/Bing/DDG news

The old API-key-dependent approach is gone. Tavily gives better relevance;
SearXNG gives breadth and zero rate limits as fallback.

Output: data/alternative_signals/news_search_YYYY-MM-DD.json
"""

import os
import json
import requests
import hashlib
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


# ── Search queries for AI news coverage ──────────────────────────────────
AI_QUERIES = [
    "artificial intelligence news",
    "OpenAI Anthropic Google AI",
    "AI funding startup investment",
    "large language model LLM",
    "AI regulation policy",
    "AI chip GPU semiconductor",
    "generative AI enterprise",
    "AI agent autonomous",
    "open source AI model",
    "AI China DeepSeek Baidu",
]

# Company-specific queries for deeper signal
COMPANY_QUERIES = [
    "OpenAI",
    "Anthropic Claude",
    "Google DeepMind Gemini",
    "Meta AI Llama",
    "NVIDIA AI",
    "Microsoft Copilot AI",
    "DeepSeek",
    "Mistral AI",
]


class TavilySearcher:
    """Primary: Tavily Search API (news topic, high relevance)."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.tavily.com/search"

    def search(self, query: str, max_results: int = 10, days_back: int = 7) -> List[Dict]:
        """Search Tavily for news articles."""
        try:
            resp = requests.post(self.base_url, json={
                "api_key": self.api_key,
                "query": query,
                "topic": "news",
                "time_range": "week",
                "max_results": max_results,
                "search_depth": "basic",
            }, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for r in data.get("results", []):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "source": self._extract_source(r.get("url", "")),
                    "description": r.get("content", "")[:500],
                    "published_date": r.get("published_date"),
                    "score": r.get("score", 0),
                    "api_source": "tavily",
                })
            return results

        except requests.exceptions.RequestException as e:
            print(f"    Tavily error for '{query[:30]}': {e}")
            return []

    def _extract_source(self, url: str) -> str:
        """Extract publication name from URL."""
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.replace("www.", "")
            return domain.split(".")[0].title()
        except Exception:
            return "Unknown"


class SearXNGSearcher:
    """Fallback: Local SearXNG instance (metasearch, no API keys)."""

    def __init__(self, base_url: str = "http://localhost:8888"):
        self.base_url = base_url

    def is_available(self) -> bool:
        """Check if SearXNG is running."""
        try:
            r = requests.get(f"{self.base_url}/healthz", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search SearXNG for news articles."""
        try:
            resp = requests.get(f"{self.base_url}/search", params={
                "q": f"{query} news",
                "format": "json",
                "categories": "general",
            }, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for r in data.get("results", [])[:max_results]:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "source": r.get("engine", "searxng"),
                    "description": r.get("content", "")[:500],
                    "published_date": r.get("publishedDate"),
                    "score": r.get("score", 0),
                    "api_source": "searxng",
                })
            return results

        except requests.exceptions.RequestException as e:
            print(f"    SearXNG error for '{query[:30]}': {e}")
            return []


class NewsSearchScraper:
    """
    Unified news search: Tavily primary, SearXNG fallback.
    
    Follows the same pattern as other briefAI scrapers:
    - run() method returns result dict
    - Saves to data/alternative_signals/
    - Deduplicates by URL
    """

    # AI relevance keywords (same as tech_news_rss_scraper)
    AI_KEYWORDS_HIGH = [
        "artificial intelligence", "machine learning", "deep learning",
        "llm", "large language model", "gpt", "chatgpt", "claude",
        "anthropic", "openai", "deepmind", "gemini", "copilot",
        "neural network", "transformer", "diffusion", "generative ai",
        "ai agent", "rag", "fine-tuning", "reasoning model",
    ]
    AI_KEYWORDS_MED = [
        "ai", "ml", "automation", "model", "training", "inference",
        "gpu", "chip", "semiconductor", "nvidia", "data center",
        "embedding", "token", "context window",
    ]

    SENTIMENT_POSITIVE = [
        "breakthrough", "launch", "release", "partnership", "funding",
        "raises", "growth", "record", "success", "game-changer",
    ]
    SENTIMENT_NEGATIVE = [
        "layoff", "cuts", "decline", "concern", "risk", "lawsuit",
        "investigation", "delay", "fail", "warning", "ban", "restrict",
    ]

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize searchers
        tavily_key = os.getenv("TAVILY_API_KEY", "")
        self.tavily = TavilySearcher(tavily_key) if tavily_key else None
        self.searxng = SearXNGSearcher()

        self._seen_urls = set()

    def _dedup(self, articles: List[Dict]) -> List[Dict]:
        """Deduplicate articles by URL."""
        unique = []
        for a in articles:
            url = a.get("url", "").rstrip("/").lower()
            if url and url not in self._seen_urls:
                self._seen_urls.add(url)
                unique.append(a)
        return unique

    def _calculate_ai_relevance(self, text: str) -> float:
        """Score AI relevance 0-1."""
        text_lower = text.lower()
        score = 0.0
        for kw in self.AI_KEYWORDS_HIGH:
            if kw in text_lower:
                score += 0.3
        for kw in self.AI_KEYWORDS_MED:
            if kw in text_lower:
                score += 0.15
        return min(score, 1.0)

    def _extract_sentiment(self, text: str) -> List[str]:
        text_lower = text.lower()
        found = []
        for kw in self.SENTIMENT_POSITIVE:
            if kw in text_lower:
                found.append(f"+{kw}")
        for kw in self.SENTIMENT_NEGATIVE:
            if kw in text_lower:
                found.append(f"-{kw}")
        return found

    def _enrich(self, article: Dict) -> Dict:
        """Add AI relevance score and sentiment to article."""
        text = f"{article.get('title', '')} {article.get('description', '')}"
        article["ai_relevance_score"] = round(self._calculate_ai_relevance(text), 3)
        article["sentiment_keywords"] = self._extract_sentiment(text)
        article["id"] = f"news_{hashlib.md5(article['url'].encode()).hexdigest()[:12]}"
        return article

    def run(self) -> Dict[str, Any]:
        """Run the news search scraper."""
        all_queries = AI_QUERIES + COMPANY_QUERIES
        all_articles = []
        tavily_count = 0
        searxng_count = 0
        tavily_available = self.tavily is not None
        searxng_available = self.searxng.is_available()

        print(f"\nNews search: Tavily={'yes' if tavily_available else 'NO KEY'}, "
              f"SearXNG={'yes' if searxng_available else 'DOWN'}")
        print(f"Running {len(all_queries)} queries...")

        for query in all_queries:
            results = []

            # Primary: Tavily
            if tavily_available:
                tavily_results = self.tavily.search(query, max_results=10)
                results.extend(tavily_results)
                tavily_count += len(tavily_results)

            # Fallback: SearXNG (always run for breadth, or if Tavily missing)
            if searxng_available:
                searxng_results = self.searxng.search(query, max_results=10)
                results.extend(searxng_results)
                searxng_count += len(searxng_results)

            # Deduplicate within this batch
            unique = self._dedup(results)
            for a in unique:
                self._enrich(a)
            all_articles.extend(unique)

            # Rate limiting
            import time
            time.sleep(0.3)

        # Filter: only AI-relevant articles
        ai_articles = [a for a in all_articles if a.get("ai_relevance_score", 0) >= 0.15]

        # Sort by relevance
        ai_articles.sort(key=lambda a: -a.get("ai_relevance_score", 0))

        # Save
        today = date.today().isoformat()
        output_path = self.output_dir / f"news_search_{today}.json"

        result = {
            "scraped_at": datetime.now().isoformat(),
            "source": "news_search",
            "description": "AI news via Tavily (primary) + SearXNG (fallback)",
            "stats": {
                "queries_run": len(all_queries),
                "tavily_results": tavily_count,
                "searxng_results": searxng_count,
                "total_unique": len(all_articles),
                "ai_relevant": len(ai_articles),
            },
            "article_count": len(ai_articles),
            "articles": ai_articles,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"  Tavily: {tavily_count} results, SearXNG: {searxng_count} results")
        print(f"  Unique: {len(all_articles)}, AI-relevant: {len(ai_articles)}")
        print(f"Saved to {output_path}")

        return result


if __name__ == "__main__":
    scraper = NewsSearchScraper()
    scraper.run()
