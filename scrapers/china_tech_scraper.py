# -*- coding: utf-8 -*-
"""
China Tech Scraper

Scrapes AI news from Chinese tech sources.
Tracks 36Kr, China AI companies, and regulatory news.
"""

import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import time
import feedparser


class ChinaTechScraper:
    """Scraper for Chinese AI/tech news."""
    
    # Chinese tech RSS feeds (English versions where available)
    FEEDS = {
        "technode": {
            "name": "TechNode",
            "url": "https://technode.com/feed/",
            "language": "en",
        },
        "pandaily": {
            "name": "Pandaily",
            "url": "https://pandaily.com/feed/",
            "language": "en",
        },
        "kr_asia": {
            "name": "KrASIA",
            "url": "https://kr-asia.com/feed",
            "language": "en",
        },
        "scmp_tech": {
            "name": "SCMP Tech",
            "url": "https://www.scmp.com/rss/5/feed",
            "language": "en",
        },
        "caixin_tech": {
            "name": "Caixin Tech",
            "url": "https://www.caixinglobal.com/rss/tech.rss",
            "language": "en",
        },
    }
    
    # Chinese AI companies to track
    CHINA_AI_COMPANIES = [
        "Baidu", "Alibaba", "Tencent", "ByteDance", "Huawei",
        "SenseTime", "Megvii", "iFlytek", "Cambricon", "Horizon Robotics",
        "Zhipu AI", "MiniMax", "Moonshot AI", "DeepSeek", "01.AI",
        "Baichuan", "SenseNova", "Xiaomi", "OPPO", "Vivo",
        "DJI", "BYD", "NIO", "XPeng", "Li Auto",
    ]
    
    # AI-related Chinese keywords (for filtering)
    AI_KEYWORDS = [
        "AI", "artificial intelligence", "人工智能",
        "machine learning", "机器学习",
        "large language model", "LLM", "大模型", "大语言模型",
        "GPT", "ChatGPT", "文心一言", "通义千问",
        "autonomous", "自动驾驶",
        "chip", "芯片", "semiconductor", "半导体",
        "Huawei", "华为", "Baidu", "百度", "Alibaba", "阿里",
        "Tencent", "腾讯", "ByteDance", "字节",
    ]
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "china_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def fetch_feed(self, feed_id: str) -> List[Dict[str, Any]]:
        """Fetch from RSS feed."""
        if feed_id not in self.FEEDS:
            return []
        
        config = self.FEEDS[feed_id]
        
        try:
            feed = feedparser.parse(config["url"])
            
            results = []
            for entry in feed.entries[:30]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                
                # Check AI relevance
                text = f"{title} {summary}".lower()
                ai_relevant = any(kw.lower() in text for kw in self.AI_KEYWORDS)
                
                # Check company mentions
                companies_mentioned = [c for c in self.CHINA_AI_COMPANIES if c.lower() in text]
                
                results.append({
                    "id": entry.get("id", entry.get("link", "")),
                    "title": title,
                    "summary": summary[:400] if summary else "",
                    "url": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "source": config["name"],
                    "source_id": feed_id,
                    "language": config["language"],
                    "ai_relevant": ai_relevant,
                    "companies_mentioned": companies_mentioned,
                })
            
            return results
            
        except Exception as e:
            print(f"    Error fetching {config['name']}: {e}")
            return []
    
    def run(self) -> Dict[str, Any]:
        """Run China tech scraper."""
        print("=" * 60)
        print("CHINA TECH SCRAPER")
        print("=" * 60)
        
        results = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "articles": [],
            "ai_articles": [],
            "by_company": {},
        }
        
        # Fetch all feeds
        print("\nFetching Chinese tech feeds...")
        all_articles = []
        for feed_id, config in self.FEEDS.items():
            print(f"  {config['name']}...")
            articles = self.fetch_feed(feed_id)
            if articles:
                ai_count = sum(1 for a in articles if a.get("ai_relevant"))
                print(f"    Got {len(articles)} articles ({ai_count} AI-relevant)")
                all_articles.extend(articles)
            time.sleep(0.5)
        
        # Dedupe by URL
        seen = set()
        unique = []
        for a in all_articles:
            if a["url"] not in seen:
                seen.add(a["url"])
                unique.append(a)
        
        results["articles"] = unique
        results["ai_articles"] = [a for a in unique if a.get("ai_relevant")]
        
        # Group by company
        for article in results["ai_articles"]:
            for company in article.get("companies_mentioned", []):
                if company not in results["by_company"]:
                    results["by_company"][company] = []
                results["by_company"][company].append({
                    "title": article["title"],
                    "url": article["url"],
                    "source": article["source"],
                })
        
        # Save
        output_file = self.output_dir / f"china_tech_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nSaved to {output_file}")
        
        # Summary
        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")
        print(f"Total articles: {len(results['articles'])}")
        print(f"AI-relevant: {len(results['ai_articles'])}")
        print(f"Companies with coverage: {len(results['by_company'])}")
        
        if results["by_company"]:
            print(f"\n{'=' * 60}")
            print("COMPANY MENTIONS")
            print(f"{'=' * 60}")
            sorted_companies = sorted(results["by_company"].items(), key=lambda x: -len(x[1]))
            for company, articles in sorted_companies[:10]:
                print(f"  {company}: {len(articles)} articles")
        
        if results["ai_articles"]:
            print(f"\n{'=' * 60}")
            print("RECENT AI HEADLINES")
            print(f"{'=' * 60}")
            for a in results["ai_articles"][:10]:
                print(f"  [{a['source']}] {a['title'][:60]}...")
        
        return results


if __name__ == "__main__":
    scraper = ChinaTechScraper()
    scraper.run()
