# -*- coding: utf-8 -*-
"""
Product Hunt Scraper

Scrapes AI product launches from Product Hunt.
Tracks new AI products and developer tools.
"""

import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import time
import feedparser


class ProductHuntScraper:
    """Scraper for Product Hunt AI launches."""
    
    # Product Hunt RSS feeds
    RSS_FEEDS = {
        "featured": "https://www.producthunt.com/feed",
        "ai_topic": "https://www.producthunt.com/topics/artificial-intelligence/feed",
    }
    
    # AI-related keywords
    AI_KEYWORDS = [
        "ai", "artificial intelligence", "machine learning", "ml",
        "gpt", "llm", "chatbot", "copilot", "assistant",
        "generative", "neural", "deep learning",
        "nlp", "computer vision", "automation",
        "openai", "claude", "gemini", "llama",
    ]
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "product_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def fetch_feed(self, feed_id: str) -> List[Dict[str, Any]]:
        """Fetch products from RSS feed."""
        if feed_id not in self.RSS_FEEDS:
            return []
        
        try:
            feed = feedparser.parse(self.RSS_FEEDS[feed_id])
            
            products = []
            for entry in feed.entries[:50]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                text = f"{title} {summary}".lower()
                
                # Calculate AI relevance
                relevance = sum(1 for kw in self.AI_KEYWORDS if kw in text)
                
                products.append({
                    "id": entry.get("id", entry.get("link", "")),
                    "name": title,
                    "tagline": summary[:200] if summary else "",
                    "url": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "ai_relevance": min(relevance / 3, 1.0),
                    "source": f"producthunt_{feed_id}",
                })
            
            return products
            
        except Exception as e:
            print(f"    Error fetching {feed_id}: {e}")
            return []
    
    def run(self) -> Dict[str, Any]:
        """Run Product Hunt scraper."""
        print("=" * 60)
        print("PRODUCT HUNT SCRAPER")
        print("=" * 60)
        
        results = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "products": [],
            "ai_products": [],
        }
        
        # Fetch all feeds
        all_products = []
        for feed_id in self.RSS_FEEDS:
            print(f"  Fetching {feed_id}...")
            products = self.fetch_feed(feed_id)
            print(f"    Got {len(products)} products")
            all_products.extend(products)
            time.sleep(0.5)
        
        # Dedupe by URL
        seen = set()
        unique = []
        for p in all_products:
            if p["url"] not in seen:
                seen.add(p["url"])
                unique.append(p)
        
        results["products"] = unique
        results["ai_products"] = [p for p in unique if p["ai_relevance"] > 0]
        
        # Save
        output_file = self.output_dir / f"producthunt_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nSaved to {output_file}")
        
        # Summary
        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")
        print(f"Total products: {len(results['products'])}")
        print(f"AI-related: {len(results['ai_products'])}")
        
        if results["ai_products"]:
            print("\nTop AI products:")
            for p in sorted(results["ai_products"], key=lambda x: -x["ai_relevance"])[:10]:
                print(f"  [{p['ai_relevance']:.1f}] {p['name'][:50]}")
        
        return results


if __name__ == "__main__":
    scraper = ProductHuntScraper()
    scraper.run()
