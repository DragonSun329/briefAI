# -*- coding: utf-8 -*-
"""
Patent Scraper

Scrapes USPTO and Google Patents for AI-related patent filings.
Tracks R&D direction and competitive intelligence.
"""

import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import json
import time
import re


@dataclass
class PatentSignal:
    """A patent filing signal."""
    id: str
    title: str
    assignee: str  # Company
    inventors: List[str]
    filing_date: str
    publication_date: str
    patent_number: str
    abstract: str
    url: str
    source: str
    ai_relevance: float


class PatentScraper:
    """Scraper for AI-related patents."""
    
    # AI companies to track patents for
    AI_ASSIGNEES = [
        "Google", "Alphabet", "DeepMind",
        "Microsoft", "OpenAI",
        "Meta", "Facebook",
        "Amazon", "AWS",
        "Apple",
        "NVIDIA",
        "IBM",
        "Intel",
        "Anthropic",
        "Baidu",
        "Alibaba",
        "Tencent",
        "ByteDance",
        "Samsung",
        "Huawei",
    ]
    
    # AI-related search terms
    AI_TERMS = [
        "machine learning",
        "neural network",
        "deep learning",
        "artificial intelligence",
        "natural language processing",
        "transformer model",
        "large language model",
        "generative AI",
        "computer vision",
        "reinforcement learning",
    ]
    
    # USPTO PatentsView API v1 (new endpoint as of 2024; old endpoint discontinued)
    USPTO_API = "https://search.patentsview.org/api/v1/patent/"
    # Legacy fallback (returns 410 Gone)
    USPTO_API_LEGACY = "https://api.patentsview.org/patents/query"
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "patent_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def search_uspto(self, assignee: str, days: int = 30) -> List[Dict[str, Any]]:
        """Search USPTO for recent patents by assignee.
        
        Uses the new PatentsView API v1 (search.patentsview.org).
        Falls back to Google Patents RSS if the API is unavailable.
        """
        try:
            # Calculate date range
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)
            
            # Try new PatentsView API v1 (different query format)
            params = {
                "q": json.dumps({
                    "_and": [
                        {"_contains": {"assignees.assignee_organization": assignee}},
                        {"_gte": {"patent_date": start_date.strftime("%Y-%m-%d")}},
                    ]
                }),
                "f": json.dumps([
                    "patent_id", "patent_title", "patent_date",
                    "patent_abstract", "assignees.assignee_organization"
                ]),
                "o": json.dumps({"size": 25}),
            }
            
            headers = {
                "User-Agent": "BriefAI/2.0 Patent Scraper",
                "Accept": "application/json",
            }
            
            resp = requests.get(self.USPTO_API, params=params, headers=headers, timeout=30)
            
            if resp.status_code == 410:
                # Old API discontinued, try new format
                return self._search_google_patents_rss(assignee, days)
            
            if resp.status_code == 403:
                # New API may require API key - fallback to Google Patents
                return self._search_google_patents_rss(assignee, days)
            
            if resp.status_code != 200:
                return self._search_google_patents_rss(assignee, days)
            
            data = resp.json()
            patents = data.get("patents", data.get("results", [])) or []
            
            # Filter for AI relevance
            ai_patents = []
            for p in patents:
                title = (p.get("patent_title") or "").lower()
                abstract = (p.get("patent_abstract") or "").lower()
                text = f"{title} {abstract}"
                
                # Check AI relevance
                relevance = 0
                for term in self.AI_TERMS:
                    if term in text:
                        relevance += 1
                
                if relevance > 0:
                    ai_patents.append({
                        "patent_number": p.get("patent_number") or p.get("patent_id"),
                        "title": p.get("patent_title"),
                        "date": p.get("patent_date"),
                        "abstract": (p.get("patent_abstract") or "")[:500],
                        "assignee": assignee,
                        "ai_relevance": min(relevance / 3, 1.0),
                    })
            
            return ai_patents
            
        except Exception as e:
            print(f"    Error searching USPTO for {assignee}: {e}")
            return self._search_google_patents_rss(assignee, days)

    def _search_google_patents_rss(self, assignee: str, days: int = 30) -> List[Dict[str, Any]]:
        """Fallback: Search Google Patents via RSS feed."""
        try:
            import feedparser
            from urllib.parse import quote
            
            query = f'assignee:"{assignee}" AND (artificial intelligence OR machine learning OR neural network)'
            url = f"https://patents.google.com/rss/search?q={quote(query)}&num=25"
            
            feed = feedparser.parse(url)
            ai_patents = []
            
            for entry in feed.entries[:25]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                text = f"{title} {summary}".lower()
                
                relevance = sum(1 for term in self.AI_TERMS if term in text)
                if relevance > 0:
                    ai_patents.append({
                        "patent_number": entry.get("id", ""),
                        "title": title,
                        "date": entry.get("published", ""),
                        "abstract": summary[:500],
                        "assignee": assignee,
                        "ai_relevance": min(relevance / 3, 1.0),
                        "url": entry.get("link", ""),
                    })
            
            return ai_patents
        except Exception as e:
            print(f"    Google Patents fallback failed for {assignee}: {e}")
            return []
    
    def search_by_terms(self, days: int = 14) -> List[Dict[str, Any]]:
        """Search for AI-related patents by keyword. Uses Google Patents RSS as fallback."""
        all_patents = []
        
        for term in self.AI_TERMS[:5]:  # Top 5 terms
            try:
                patents = self._search_google_patents_rss(term, days)
                for p in patents:
                    p["search_term"] = term
                    all_patents.extend([p])
                
                time.sleep(0.5)  # Rate limit
                
            except Exception as e:
                print(f"    Error searching term '{term}': {e}")
        
        # Dedupe by patent number
        seen = set()
        unique = []
        for p in all_patents:
            pn = p.get("patent_number", "")
            if pn and pn not in seen:
                seen.add(pn)
                unique.append(p)
        
        return unique
    
    def run(self, days: int = 30, save: bool = True) -> Dict[str, Any]:
        """Run patent scraper."""
        print("=" * 60)
        print("PATENT SCRAPER (USPTO)")
        print("=" * 60)
        
        results = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "patents_by_company": [],
            "patents_by_term": [],
        }
        
        # Search by company
        print(f"\nSearching patents by company (last {days} days)...")
        for assignee in self.AI_ASSIGNEES[:10]:  # Top 10
            print(f"  {assignee}...")
            patents = self.search_uspto(assignee, days)
            if patents:
                print(f"    Found {len(patents)} AI patents")
                results["patents_by_company"].extend(patents)
            time.sleep(0.3)
        
        # Search by AI terms
        print(f"\nSearching patents by AI terms...")
        term_patents = self.search_by_terms(days=14)
        results["patents_by_term"] = term_patents
        print(f"  Found {len(term_patents)} patents")
        
        # Save
        if save:
            output_file = self.output_dir / f"patents_{datetime.now().strftime('%Y-%m-%d')}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\nSaved to {output_file}")
        
        # Summary
        total = len(results["patents_by_company"]) + len(results["patents_by_term"])
        print(f"\n{'=' * 60}")
        print(f"Total patents found: {total}")
        print(f"  By company: {len(results['patents_by_company'])}")
        print(f"  By AI term: {len(results['patents_by_term'])}")
        
        return results


if __name__ == "__main__":
    scraper = PatentScraper()
    scraper.run()
