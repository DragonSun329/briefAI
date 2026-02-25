# -*- coding: utf-8 -*-
"""
News Search Scraper v2 — Tavily + SearXNG + Legacy Fallback

Primary:  Tavily API (high-quality, AI-optimized search)
Fallback: SearXNG (self-hosted metasearch, no API key limits)
Legacy:   Original news_search_scraper (NewsAPI/GNews/MediaStack)

Output: data/alternative_signals/news_search_YYYY-MM-DD.json
"""

import os
import json
import hashlib
import requests
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


# Search queries — focused, not exhaustive (each costs API credits)
AI_SEARCH_QUERIES = [
    "AI artificial intelligence news this week",
    "OpenAI Anthropic Google AI latest",
    "large language model LLM breakthroughs",
    "AI startup funding investment 2026",
    "AI regulation policy government",
    "AI agents autonomous systems",
    "NVIDIA AMD AI chips semiconductor",
    "generative AI enterprise adoption",
    "AI safety alignment research",
    "China AI technology competition",
]


class TavilySearcher:
    """Tavily Search API — optimized for AI/LLM use cases."""

    BASE_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")
        if not self.api_key:
            raise ValueError("TAVILY_API_KEY not set")

    def search(self, query: str, max_results: int = 10, topic: str = "news",
               time_range: str = "week") -> List[Dict[str, Any]]:
        """Search via Tavily. Returns list of result dicts."""
        try:
            r = requests.post(self.BASE_URL, json={
                "api_key": self.api_key,
                "query": query,
                "topic": topic,
                "time_range": time_range,
                "max_results": max_results,
                "search_depth": "basic",
            }, timeout=20)
            r.raise_for_status()
            data = r.json()

            results = []
            for item in data.get("results", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", "")[:500],
                    "published_date": item.get("published_date"),
                    "source": self._extract_source(item.get("url", "")),
                    "score": item.get("score", 0),
                    "api_source": "tavily",
                })
            return results

        except Exception as e:
            print(f"    Tavily error for '{query[:40]}': {e}")
            return []

    @staticmethod
    def _extract_source(url: str) -> str:
        """Extract domain name as source."""
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc.replace("www.", "")
        except Exception:
            return ""


class SearXNGSearcher:
    """Self-hosted SearXNG metasearch engine."""

    def __init__(self, base_url: str = "http://localhost:8888"):
        self.base_url = base_url

    def is_available(self) -> bool:
        """Check if SearXNG is reachable."""
        try:
            r = requests.get(f"{self.base_url}/search", params={
                "q": "test", "format": "json"
            }, timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def search(self, query: str, max_results: int = 10,
               categories: str = "news") -> List[Dict[str, Any]]:
        """Search via SearXNG. Returns list of result dicts."""
        try:
            r = requests.get(f"{self.base_url}/search", params={
                "q": query,
                "format": "json",
                "categories": categories,
                "time_range": "week",
            }, timeout=20)
            r.raise_for_status()
            data = r.json()

            results = []
            for item in data.get("results", [])[:max_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", "")[:500],
                    "published_date": item.get("publishedDate"),
                    "source": item.get("engine", "searxng"),
                    "score": item.get("score", 0),
                    "api_source": "searxng",
                })
            return results

        except Exception as e:
            print(f"    SearXNG error for '{query[:40]}': {e}")
            return []


class NewsSearchScraperV2:
    """
    Unified news search with cascading fallback:
    Tavily (primary) → SearXNG (fallback) → skip
    """

    AI_KEYWORDS = {
        "high": [
            "artificial intelligence", "machine learning", "deep learning",
            "llm", "large language model", "gpt", "chatgpt", "claude",
            "anthropic", "openai", "deepmind", "gemini", "copilot",
            "neural network", "transformer", "diffusion", "generative ai",
            "ai agent", "reasoning model",
        ],
        "medium": [
            "ai", "ml", "automation", "model", "training", "inference",
            "gpu", "chip", "semiconductor", "nvidia", "data center",
        ],
    }

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize searchers
        self.tavily = None
        self.searxng = None

        try:
            self.tavily = TavilySearcher()
            print("  Tavily API: ready")
        except ValueError:
            print("  Tavily API: no key, skipping")

        self.searxng = SearXNGSearcher()
        if self.searxng.is_available():
            print("  SearXNG: ready")
        else:
            print("  SearXNG: not available")
            self.searxng = None

    def _calculate_relevance(self, text: str) -> float:
        """Calculate AI relevance score 0-1."""
        text_lower = text.lower()
        score = 0.0
        for kw in self.AI_KEYWORDS["high"]:
            if kw in text_lower:
                score += 0.3
        for kw in self.AI_KEYWORDS["medium"]:
            if kw in text_lower:
                score += 0.15
        return min(score, 1.0)

    def _dedup_results(self, results: List[Dict]) -> List[Dict]:
        """Deduplicate by URL."""
        seen = set()
        deduped = []
        for r in results:
            url_key = r["url"].rstrip("/").lower()
            if url_key not in seen:
                seen.add(url_key)
                deduped.append(r)
        return deduped

    def run(self) -> Dict[str, Any]:
        """Run the news search scraper."""
        all_results = []
        source_stats = {"tavily": 0, "searxng": 0}

        for query in AI_SEARCH_QUERIES:
            results = []

            # Try Tavily first
            if self.tavily:
                results = self.tavily.search(query, max_results=10)
                if results:
                    source_stats["tavily"] += len(results)
                    print(f"  [{query[:40]}] Tavily: {len(results)} results")

            # Fallback to SearXNG if Tavily returned nothing
            if not results and self.searxng:
                results = self.searxng.search(query, max_results=10)
                if results:
                    source_stats["searxng"] += len(results)
                    print(f"  [{query[:40]}] SearXNG: {len(results)} results")

            if not results:
                print(f"  [{query[:40]}] no results from any source")

            all_results.extend(results)

        # Dedup
        all_results = self._dedup_results(all_results)

        # Score AI relevance
        for r in all_results:
            text = f"{r['title']} {r.get('content', '')}"
            r["ai_relevance_score"] = round(self._calculate_relevance(text), 3)
            r["id"] = f"news_{hashlib.md5(r['url'].encode()).hexdigest()[:12]}"

        # Sort by relevance
        all_results.sort(key=lambda x: -x["ai_relevance_score"])

        # Save
        today = date.today().isoformat()
        output_path = self.output_dir / f"news_search_{today}.json"

        output = {
            "scraped_at": datetime.now().isoformat(),
            "source": "news_search_v2",
            "description": "AI news via Tavily + SearXNG cascade",
            "source_stats": source_stats,
            "article_count": len(all_results),
            "articles": all_results,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        total = source_stats["tavily"] + source_stats["searxng"]
        print(f"\n  Total: {len(all_results)} unique articles (Tavily: {source_stats['tavily']}, SearXNG: {source_stats['searxng']})")
        print(f"Saved to {output_path}")

        return output


if __name__ == "__main__":
    scraper = NewsSearchScraperV2()
    scraper.run()
