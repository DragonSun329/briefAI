# -*- coding: utf-8 -*-
"""
Conference Papers Scraper

Scrapes AI research papers from ArXiv and major conferences.
Tracks research breakthroughs and trends.
"""

import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import time
import re
import feedparser
import xml.etree.ElementTree as ET


class ConferencePapersScraper:
    """Scraper for AI research papers."""
    
    # ArXiv categories
    ARXIV_CATEGORIES = {
        "cs.LG": "Machine Learning",
        "cs.CL": "Computation and Language (NLP)",
        "cs.CV": "Computer Vision",
        "cs.AI": "Artificial Intelligence",
        "cs.NE": "Neural and Evolutionary Computing",
        "cs.RO": "Robotics",
        "stat.ML": "Statistics - Machine Learning",
    }
    
    # ArXiv API
    ARXIV_API = "http://export.arxiv.org/api/query"
    
    # Known institutions/labs
    TOP_LABS = [
        "google", "deepmind", "openai", "anthropic", "meta", "facebook",
        "microsoft", "nvidia", "stanford", "berkeley", "mit", "cmu",
        "oxford", "cambridge", "tsinghua", "peking",
    ]
    
    # High-impact keywords
    TRENDING_KEYWORDS = [
        "large language model", "LLM", "GPT", "transformer",
        "diffusion", "RLHF", "instruction tuning", "alignment",
        "multimodal", "vision-language", "chain-of-thought",
        "in-context learning", "emergent", "scaling law",
        "retrieval augmented", "RAG", "agent", "reasoning",
    ]
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "paper_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def fetch_arxiv_papers(self, category: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent papers from ArXiv category."""
        try:
            params = {
                "search_query": f"cat:{category}",
                "start": 0,
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            
            resp = requests.get(self.ARXIV_API, params=params, timeout=30)
            
            if resp.status_code != 200:
                return []
            
            # Parse XML response
            root = ET.fromstring(resp.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            
            papers = []
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                summary = entry.find("atom:summary", ns).text.strip()[:500]
                
                authors = []
                for author in entry.findall("atom:author", ns):
                    name = author.find("atom:name", ns).text
                    authors.append(name)
                
                published = entry.find("atom:published", ns).text
                arxiv_id = entry.find("atom:id", ns).text.split("/")[-1]
                
                # Calculate relevance
                text = f"{title} {summary}".lower()
                keyword_hits = sum(1 for kw in self.TRENDING_KEYWORDS if kw.lower() in text)
                lab_hits = sum(1 for lab in self.TOP_LABS if lab in " ".join(authors).lower())
                
                papers.append({
                    "id": arxiv_id,
                    "title": title,
                    "authors": authors[:5],  # First 5 authors
                    "abstract": summary,
                    "category": category,
                    "category_name": self.ARXIV_CATEGORIES.get(category, category),
                    "published": published[:10],
                    "url": f"https://arxiv.org/abs/{arxiv_id}",
                    "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                    "keyword_relevance": keyword_hits,
                    "lab_relevance": lab_hits,
                    "total_relevance": keyword_hits + lab_hits * 2,
                })
            
            return papers
            
        except Exception as e:
            print(f"    Error fetching {category}: {e}")
            return []
    
    def search_arxiv(self, query: str, max_results: int = 30) -> List[Dict[str, Any]]:
        """Search ArXiv for specific query."""
        try:
            params = {
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            
            resp = requests.get(self.ARXIV_API, params=params, timeout=30)
            
            if resp.status_code != 200:
                return []
            
            root = ET.fromstring(resp.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            
            papers = []
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                arxiv_id = entry.find("atom:id", ns).text.split("/")[-1]
                published = entry.find("atom:published", ns).text
                
                papers.append({
                    "id": arxiv_id,
                    "title": title,
                    "published": published[:10],
                    "url": f"https://arxiv.org/abs/{arxiv_id}",
                    "search_query": query,
                })
            
            return papers
            
        except Exception as e:
            print(f"    Error searching '{query}': {e}")
            return []
    
    def run(self) -> Dict[str, Any]:
        """Run conference papers scraper."""
        print("=" * 60)
        print("CONFERENCE PAPERS SCRAPER (ArXiv)")
        print("=" * 60)
        
        results = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "papers_by_category": {},
            "trending_papers": [],
            "search_results": [],
        }
        
        # Fetch by category
        print("\nFetching papers by category...")
        all_papers = []
        for cat_id, cat_name in self.ARXIV_CATEGORIES.items():
            print(f"  {cat_name} ({cat_id})...")
            papers = self.fetch_arxiv_papers(cat_id, max_results=30)
            results["papers_by_category"][cat_id] = papers
            all_papers.extend(papers)
            print(f"    Got {len(papers)} papers")
            time.sleep(1)  # ArXiv rate limit
        
        # Find trending papers (high relevance)
        trending = sorted(all_papers, key=lambda x: -x.get("total_relevance", 0))[:20]
        results["trending_papers"] = trending
        
        # Search for hot topics
        print("\nSearching hot topics...")
        hot_topics = ["GPT-4", "Claude", "Gemini", "Llama 3", "mixture of experts"]
        for topic in hot_topics:
            print(f"  '{topic}'...")
            papers = self.search_arxiv(topic, max_results=10)
            results["search_results"].extend(papers)
            time.sleep(1)
        
        # Save
        output_file = self.output_dir / f"papers_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nSaved to {output_file}")
        
        # Summary
        total_papers = sum(len(p) for p in results["papers_by_category"].values())
        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")
        print(f"Total papers: {total_papers}")
        print(f"Trending papers: {len(results['trending_papers'])}")
        
        print(f"\n{'=' * 60}")
        print("TOP TRENDING PAPERS")
        print(f"{'=' * 60}")
        for p in results["trending_papers"][:10]:
            rel = p.get("total_relevance", 0)
            print(f"  [{rel}] {p['title'][:70]}...")
            print(f"       {p['url']}")
        
        return results


if __name__ == "__main__":
    scraper = ConferencePapersScraper()
    scraper.run()
