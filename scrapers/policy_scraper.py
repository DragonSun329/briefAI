# -*- coding: utf-8 -*-
"""
Government Policy Scraper

Scrapes AI-related government regulations and policies.
Tracks Federal Register, EU regulations, and policy announcements.
"""

import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import time
import feedparser


class PolicyScraper:
    """Scraper for AI government policy and regulations."""
    
    # Federal Register API
    FED_REG_API = "https://www.federalregister.gov/api/v1/documents.json"
    
    # AI-related search terms for Federal Register
    AI_SEARCH_TERMS = [
        "artificial intelligence",
        "machine learning",
        "automated decision",
        "algorithmic",
        "AI governance",
        "facial recognition",
        "deepfake",
        "autonomous vehicle",
        "generative AI",
    ]
    
    # Government agencies relevant to AI
    AGENCIES = [
        "Commerce Department",
        "Federal Trade Commission",
        "National Institute of Standards and Technology",
        "Office of Science and Technology Policy",
        "Defense Department",
        "Homeland Security Department",
        "Securities and Exchange Commission",
    ]
    
    # Policy RSS feeds
    POLICY_FEEDS = {
        "nist_ai": "https://www.nist.gov/topics/artificial-intelligence/rss.xml",
        "whitehouse_ostp": "https://www.whitehouse.gov/ostp/feed/",
        "ftc_tech": "https://www.ftc.gov/feeds/press-release-consumer-protection.xml",
        "eu_ai_act": "https://digital-strategy.ec.europa.eu/en/policies/european-approach-artificial-intelligence/rss",
    }
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "policy_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def fetch_federal_register(self, term: str, days: int = 30) -> List[Dict[str, Any]]:
        """Fetch AI-related documents from Federal Register."""
        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)
            
            params = {
                "conditions[term]": term,
                "conditions[publication_date][gte]": start_date.strftime("%Y-%m-%d"),
                "per_page": 20,
                "order": "newest",
            }
            
            resp = requests.get(self.FED_REG_API, params=params, timeout=15)
            
            if resp.status_code != 200:
                return []
            
            data = resp.json()
            docs = data.get("results", [])
            
            results = []
            for doc in docs:
                results.append({
                    "id": doc.get("document_number", ""),
                    "title": doc.get("title", ""),
                    "type": doc.get("type", ""),
                    "agency": ", ".join(doc.get("agencies", [{}])[0].get("name", "") for a in doc.get("agencies", [])),
                    "abstract": doc.get("abstract", "")[:500] if doc.get("abstract") else "",
                    "publication_date": doc.get("publication_date", ""),
                    "url": doc.get("html_url", ""),
                    "pdf_url": doc.get("pdf_url", ""),
                    "search_term": term,
                    "source": "federal_register",
                })
            
            return results
            
        except Exception as e:
            print(f"    Error fetching '{term}': {e}")
            return []
    
    def fetch_policy_feed(self, feed_id: str) -> List[Dict[str, Any]]:
        """Fetch from policy RSS feed."""
        if feed_id not in self.POLICY_FEEDS:
            return []
        
        try:
            feed = feedparser.parse(self.POLICY_FEEDS[feed_id])
            
            results = []
            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                
                # Check AI relevance
                text = f"{title} {summary}".lower()
                ai_relevant = any(term.lower() in text for term in self.AI_SEARCH_TERMS)
                
                results.append({
                    "id": entry.get("id", entry.get("link", "")),
                    "title": title,
                    "summary": summary[:500] if summary else "",
                    "url": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "source": feed_id,
                    "ai_relevant": ai_relevant,
                })
            
            return results
            
        except Exception as e:
            print(f"    Error fetching {feed_id}: {e}")
            return []
    
    def run(self) -> Dict[str, Any]:
        """Run policy scraper."""
        print("=" * 60)
        print("GOVERNMENT POLICY SCRAPER")
        print("=" * 60)
        
        results = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "federal_register": [],
            "policy_feeds": {},
            "ai_relevant": [],
        }
        
        # Fetch from Federal Register
        print("\nSearching Federal Register...")
        all_fed_docs = []
        for term in self.AI_SEARCH_TERMS[:5]:  # Top 5 terms
            print(f"  '{term}'...")
            docs = self.fetch_federal_register(term, days=60)
            if docs:
                print(f"    Found {len(docs)} documents")
                all_fed_docs.extend(docs)
            time.sleep(0.5)
        
        # Dedupe
        seen = set()
        unique_fed = []
        for doc in all_fed_docs:
            if doc["id"] not in seen:
                seen.add(doc["id"])
                unique_fed.append(doc)
        results["federal_register"] = unique_fed
        
        # Fetch policy feeds
        print("\nFetching policy feeds...")
        all_ai_relevant = []
        for feed_id in self.POLICY_FEEDS:
            print(f"  {feed_id}...")
            items = self.fetch_policy_feed(feed_id)
            results["policy_feeds"][feed_id] = items
            ai_items = [i for i in items if i.get("ai_relevant")]
            all_ai_relevant.extend(ai_items)
            print(f"    Got {len(items)} items ({len(ai_items)} AI-relevant)")
            time.sleep(0.5)
        
        results["ai_relevant"] = all_ai_relevant
        
        # Save
        output_file = self.output_dir / f"policy_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nSaved to {output_file}")
        
        # Summary
        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")
        print(f"Federal Register documents: {len(results['federal_register'])}")
        print(f"Policy feed items: {sum(len(v) for v in results['policy_feeds'].values())}")
        print(f"AI-relevant items: {len(results['ai_relevant'])}")
        
        if results["federal_register"]:
            print(f"\n{'=' * 60}")
            print("RECENT FEDERAL REGISTER (AI-related)")
            print(f"{'=' * 60}")
            for doc in results["federal_register"][:10]:
                print(f"  [{doc['publication_date']}] {doc['title'][:60]}...")
                print(f"       Type: {doc['type']} | {doc['url']}")
        
        return results


if __name__ == "__main__":
    scraper = PolicyScraper()
    scraper.run()
