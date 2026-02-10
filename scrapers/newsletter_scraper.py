# -*- coding: utf-8 -*-
"""
AI Newsletter & Blog Scraper

Scrapes high-value AI newsletters and technical blogs.
Sources: Import AI, Simon Willison, The Batch, One Useful Thing
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


@dataclass 
class NewsletterPost:
    """Newsletter/blog post."""
    id: str
    title: str
    url: str
    source: str
    source_id: str
    published_at: Optional[datetime]
    summary: str
    author: str
    influence_score: float  # How influential is this source


class NewsletterScraper:
    """Scraper for AI newsletters and blogs."""
    
    # High-value newsletter/blog sources
    SOURCES = {
        "import_ai": {
            "name": "Import AI (Jack Clark)",
            "url": "https://importai.substack.com/feed",
            "author": "Jack Clark",
            "type": "rss",
            "influence": 10,  # Former OpenAI policy director
            "focus": ["research", "policy", "insider"],
        },
        "simon_willison": {
            "name": "Simon Willison's Weblog",
            "url": "https://simonwillison.net/atom/everything/",
            "author": "Simon Willison",
            "type": "atom",
            "influence": 9,  # Django co-creator, LLM tooling expert
            "focus": ["technical", "llm", "tools"],
        },
        "one_useful_thing": {
            "name": "One Useful Thing",
            "url": "https://www.oneusefulthing.org/feed",
            "author": "Ethan Mollick",
            "type": "rss",
            "influence": 8,  # Wharton professor, AI adoption research
            "focus": ["applications", "productivity", "education"],
        },
        "ai_supremacy": {
            "name": "AI Supremacy",
            "url": "https://aisupremacy.substack.com/feed",
            "author": "Michael Spencer",
            "type": "rss",
            "influence": 7,
            "focus": ["analysis", "trends"],
        },
        "thezvi": {
            "name": "Don't Worry About the Vase",
            "url": "https://thezvi.substack.com/feed",
            "author": "Zvi Mowshowitz",
            "type": "rss",
            "influence": 8,  # Deep AI analysis
            "focus": ["analysis", "safety", "prediction"],
        },
        "lesswrong": {
            "name": "LessWrong AI",
            "url": "https://www.lesswrong.com/feed.xml?view=community-rss&karmaThreshold=30",
            "author": "Community",
            "type": "rss",
            "influence": 8,  # AI safety community
            "focus": ["safety", "alignment", "technical"],
        },
        "alignment_forum": {
            "name": "Alignment Forum",
            "url": "https://www.alignmentforum.org/feed.xml",
            "author": "Community",
            "type": "rss",
            "influence": 9,  # Core AI safety research
            "focus": ["alignment", "safety", "research"],
        },
        # Added Jan 28, 2026
        "interconnects": {
            "name": "Interconnects",
            "url": "https://www.interconnects.ai/feed",
            "author": "Nathan Lambert",
            "type": "rss",
            "influence": 9,  # Ex-HuggingFace, RLHF expert
            "focus": ["rlhf", "training", "technical"],
        },
        "semianalysis": {
            "name": "SemiAnalysis",
            "url": "https://semianalysis.substack.com/feed",
            "author": "Dylan Patel",
            "type": "rss",
            "influence": 10,  # Top chip/hardware analysis
            "focus": ["chips", "hardware", "infrastructure"],
        },
        "chinatalk": {
            "name": "ChinaTalk",
            "url": "https://chinatalk.substack.com/feed",
            "author": "Jordan Schneider",
            "type": "rss",
            "influence": 9,  # China tech policy
            "focus": ["china", "policy", "geopolitics"],
        },
        "ai_snake_oil": {
            "name": "AI Snake Oil",
            "url": "https://aisnakeoil.substack.com/feed",
            "author": "Arvind Narayanan",
            "type": "rss",
            "influence": 9,  # Princeton prof, AI criticism
            "focus": ["criticism", "analysis", "debunking"],
        },
        "stratechery": {
            "name": "Stratechery",
            "url": "https://stratechery.com/feed/",
            "author": "Ben Thompson",
            "type": "rss",
            "influence": 10,  # Top tech strategy analyst
            "focus": ["business", "strategy", "analysis"],
        },
        "the_gradient": {
            "name": "The Gradient",
            "url": "https://thegradient.pub/rss/",
            "author": "Community",
            "type": "rss",
            "influence": 9,  # ML research interviews
            "focus": ["research", "interviews", "analysis"],
        },
    }
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "newsletter_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def fetch_source(self, source_id: str) -> List[Dict[str, Any]]:
        """Fetch posts from a newsletter/blog source."""
        if source_id not in self.SOURCES:
            return []
        
        config = self.SOURCES[source_id]
        print(f"  Fetching {config['name']}...")
        
        try:
            feed = feedparser.parse(config["url"])
            
            entries = []
            for entry in feed.entries[:20]:
                # Get published date
                pub_date = entry.get("published", entry.get("updated", ""))
                
                entries.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", entry.get("content", [{}])[0].get("value", ""))[:1000],
                    "published": pub_date,
                })
            
            print(f"    Got {len(entries)} posts")
            return entries
            
        except Exception as e:
            print(f"    Error: {e}")
            return []
    
    def process_entry(self, entry: Dict[str, Any], source_id: str) -> NewsletterPost:
        """Process an entry into NewsletterPost."""
        config = self.SOURCES[source_id]
        
        import hashlib
        url_hash = hashlib.md5(entry["link"].encode()).hexdigest()[:12]
        
        # Parse date
        pub_date = None
        if entry["published"]:
            try:
                for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"]:
                    try:
                        pub_date = datetime.strptime(entry["published"], fmt)
                        break
                    except:
                        continue
            except:
                pass
        
        return NewsletterPost(
            id=f"{source_id}_{url_hash}",
            title=entry["title"],
            url=entry["link"],
            source=config["name"],
            source_id=source_id,
            published_at=pub_date,
            summary=entry["summary"][:500],
            author=config["author"],
            influence_score=config["influence"] / 10.0,
        )
    
    def scrape_all(self, days_back: int = 7) -> List[NewsletterPost]:
        """Scrape all newsletter sources."""
        all_posts = []
        cutoff = datetime.now() - timedelta(days=days_back)
        
        print(f"Scraping {len(self.SOURCES)} newsletter sources...")
        
        for source_id in self.SOURCES:
            entries = self.fetch_source(source_id)
            
            for entry in entries:
                post = self.process_entry(entry, source_id)
                
                # Filter by date if we have one
                if post.published_at:
                    if post.published_at.replace(tzinfo=None) < cutoff:
                        continue
                
                all_posts.append(post)
            
            time.sleep(0.5)
        
        # Sort by influence
        all_posts.sort(key=lambda p: p.influence_score, reverse=True)
        
        print(f"\nTotal: {len(all_posts)} recent posts")
        return all_posts
    
    def to_signal_observations(self, posts: List[NewsletterPost]) -> List[Dict[str, Any]]:
        """Convert posts to signal observations."""
        observations = []
        
        for post in posts:
            # The newsletter author themselves is the entity
            obs = {
                "entity_name": post.author if post.author != "Community" else post.source,
                "source_id": f"newsletter_{post.source_id}",
                "category": "media",
                "raw_value": 5.0 + (post.influence_score * 4),  # 5-9 based on influence
                "raw_data": {
                    "source": post.source,
                    "headline": post.title,
                    "url": post.url,
                    "summary": post.summary[:200],
                    "published_at": post.published_at.isoformat() if post.published_at else None,
                    "author": post.author,
                    "influence_score": post.influence_score,
                    "signal_type": "thought_leadership",
                },
                "confidence": 0.7 + (post.influence_score * 0.2),
            }
            observations.append(obs)
        
        return observations
    
    def save_results(self, posts: List[NewsletterPost]):
        """Save results to JSON."""
        filename = f"newsletters_{datetime.now().strftime('%Y-%m-%d')}.json"
        output_path = self.output_dir / filename
        
        data = {
            "scraped_at": datetime.now().isoformat(),
            "post_count": len(posts),
            "posts": [asdict(p) for p in posts],
        }
        
        for post in data["posts"]:
            if post["published_at"]:
                post["published_at"] = post["published_at"].isoformat()
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"Saved to {output_path}")


def run_scraper():
    """Run newsletter scraper."""
    scraper = NewsletterScraper()
    
    print("=" * 60)
    print("NEWSLETTER & BLOG SCRAPER")
    print("=" * 60)
    
    posts = scraper.scrape_all(days_back=7)
    
    if posts:
        scraper.save_results(posts)
        
        print("\n" + "=" * 60)
        print("TOP 10 POSTS BY INFLUENCE")
        print("=" * 60)
        
        for i, post in enumerate(posts[:10], 1):
            title = post.title[:50].encode('ascii', 'ignore').decode()
            print(f"{i}. [{post.author}] {title}...")
    
    return posts


if __name__ == "__main__":
    run_scraper()
