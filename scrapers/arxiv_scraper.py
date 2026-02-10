"""
arXiv Scraper for AI Research Trends

Scrapes recent AI/ML papers from arXiv to track
research trends and emerging topics.
"""

import requests
import xml.etree.ElementTree as ET
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import re


class ArxivScraper:
    """Scraper for arXiv AI research papers."""

    BASE_URL = "http://export.arxiv.org/api/query"

    # AI-related arXiv categories
    AI_CATEGORIES = [
        "cs.AI",   # Artificial Intelligence
        "cs.LG",   # Machine Learning
        "cs.CL",   # Computation and Language (NLP)
        "cs.CV",   # Computer Vision
        "cs.NE",   # Neural and Evolutionary Computing
        "stat.ML", # Machine Learning (Statistics)
    ]

    # Keywords for filtering and categorization
    AI_KEYWORDS = {
        "llm": ['large language model', 'llm', 'language model', 'gpt', 'transformer'],
        "nlp": ['natural language', 'nlp', 'text', 'language understanding', 'translation'],
        "vision": ['computer vision', 'image', 'visual', 'object detection', 'segmentation'],
        "reinforcement": ['reinforcement learning', 'rl', 'reward', 'policy'],
        "generative": ['generative', 'diffusion', 'gan', 'vae', 'generation'],
        "safety": ['alignment', 'safety', 'interpretability', 'explainability', 'bias'],
    }

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def fetch_papers(self, query: str, max_results: int = 100,
                    sort_by: str = "submittedDate",
                    sort_order: str = "descending") -> List[Dict[str, Any]]:
        """Fetch papers from arXiv API."""
        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }

        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=60)
            resp.raise_for_status()
            return self.parse_arxiv_response(resp.text)
        except Exception as e:
            print(f"  Error fetching papers: {e}")
            return []

    def parse_arxiv_response(self, xml_text: str) -> List[Dict[str, Any]]:
        """Parse arXiv API XML response."""
        papers = []

        # Define namespace
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'arxiv': 'http://arxiv.org/schemas/atom',
        }

        root = ET.fromstring(xml_text)

        for entry in root.findall('atom:entry', ns):
            paper = {
                "id": entry.find('atom:id', ns).text if entry.find('atom:id', ns) is not None else "",
                "title": entry.find('atom:title', ns).text.strip().replace('\n', ' ') if entry.find('atom:title', ns) is not None else "",
                "summary": entry.find('atom:summary', ns).text.strip().replace('\n', ' ')[:500] if entry.find('atom:summary', ns) is not None else "",
                "published": entry.find('atom:published', ns).text if entry.find('atom:published', ns) is not None else "",
                "updated": entry.find('atom:updated', ns).text if entry.find('atom:updated', ns) is not None else "",
                "authors": [],
                "categories": [],
                "links": {},
            }

            # Extract authors
            for author in entry.findall('atom:author', ns):
                name = author.find('atom:name', ns)
                if name is not None:
                    paper["authors"].append(name.text)

            # Extract categories
            for category in entry.findall('atom:category', ns):
                term = category.get('term')
                if term:
                    paper["categories"].append(term)

            # Extract links
            for link in entry.findall('atom:link', ns):
                rel = link.get('rel', 'alternate')
                href = link.get('href')
                if href:
                    paper["links"][rel] = href

            # Extract arxiv ID from the URL
            if paper["id"]:
                arxiv_id = paper["id"].split("/abs/")[-1]
                paper["arxiv_id"] = arxiv_id
                paper["url"] = f"https://arxiv.org/abs/{arxiv_id}"
                paper["pdf_url"] = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

            papers.append(paper)

        return papers

    def fetch_recent_ai_papers(self, days: int = 7, max_per_category: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent AI papers from multiple categories."""
        all_papers = []
        seen_ids = set()

        for category in self.AI_CATEGORIES:
            print(f"  Fetching from {category}...")
            query = f"cat:{category}"
            papers = self.fetch_papers(query, max_results=max_per_category)

            for paper in papers:
                paper_id = paper.get("arxiv_id", paper.get("id"))
                if paper_id and paper_id not in seen_ids:
                    seen_ids.add(paper_id)
                    all_papers.append(paper)

        return all_papers

    def categorize_paper(self, paper: Dict[str, Any]) -> str:
        """Categorize a paper into AI trend buckets."""
        title = paper.get("title", "").lower()
        summary = paper.get("summary", "").lower()
        categories = paper.get("categories", [])
        combined = f"{title} {summary}"

        # Check for specific topics in title/abstract
        if any(kw in combined for kw in ['large language model', 'llm', 'gpt', 'chatgpt', 'instruction']):
            return "llm-foundation"
        if any(kw in combined for kw in ['llama', 'mistral', 'open-source', 'fine-tun']):
            return "open-source-ai"
        if any(kw in combined for kw in ['diffusion', 'stable diffusion', 'image generation', 'text-to-image']):
            return "ai-image-generation"
        if any(kw in combined for kw in ['alignment', 'safety', 'harmless', 'jailbreak', 'red team']):
            return "ai-safety"
        if any(kw in combined for kw in ['agent', 'tool use', 'planning', 'reasoning']):
            return "ai-agents"
        if any(kw in combined for kw in ['multimodal', 'vision-language', 'vlm']):
            return "multimodal-ai"
        if any(kw in combined for kw in ['robot', 'embodied', 'manipulation']):
            return "robotics-embodied"
        if any(kw in combined for kw in ['speech', 'audio', 'voice', 'tts', 'asr']):
            return "ai-audio"
        if any(kw in combined for kw in ['code', 'programming', 'software']):
            return "ai-coding"

        # Fall back to arXiv category
        if "cs.CL" in categories:
            return "llm-foundation"
        if "cs.CV" in categories:
            return "computer-vision"
        if "cs.LG" in categories or "stat.ML" in categories:
            return "ai-research"

        return "ai-general"

    def compute_signals(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute trend signals from papers."""
        bucket_signals = {}

        for paper in papers:
            bucket = paper.get("bucket")
            if not bucket:
                continue

            if bucket not in bucket_signals:
                bucket_signals[bucket] = {
                    "paper_count": 0,
                    "authors": set(),
                    "top_papers": [],
                    "categories": {},
                }

            bucket_signals[bucket]["paper_count"] += 1

            # Track unique authors
            for author in paper.get("authors", []):
                bucket_signals[bucket]["authors"].add(author)

            # Track arXiv categories
            for cat in paper.get("categories", []):
                bucket_signals[bucket]["categories"][cat] = (
                    bucket_signals[bucket]["categories"].get(cat, 0) + 1
                )

            if len(bucket_signals[bucket]["top_papers"]) < 5:
                bucket_signals[bucket]["top_papers"].append({
                    "title": paper.get("title"),
                    "url": paper.get("url"),
                    "published": paper.get("published"),
                })

        # Finalize
        total_papers = sum(d["paper_count"] for d in bucket_signals.values())
        for bucket, data in bucket_signals.items():
            data["unique_authors"] = len(data["authors"])
            del data["authors"]  # Don't serialize the set

            if total_papers > 0:
                data["share"] = data["paper_count"] / total_papers
            else:
                data["share"] = 0

            # Interpret research momentum
            share = data["share"]
            if share > 0.2:
                data["signal_interpretation"] = "Hot research area - very active"
            elif share > 0.1:
                data["signal_interpretation"] = "Active research area"
            elif share > 0.05:
                data["signal_interpretation"] = "Growing research interest"
            else:
                data["signal_interpretation"] = "Niche research area"

        return bucket_signals

    def run(self, save: bool = True) -> Dict[str, Any]:
        """Run the scraper and return results."""
        print("Fetching recent AI papers from arXiv...")
        papers = self.fetch_recent_ai_papers(max_per_category=50)
        print(f"  Retrieved {len(papers)} papers")

        # Process papers
        for paper in papers:
            paper["bucket"] = self.categorize_paper(paper)

        # Sort by date
        papers.sort(key=lambda x: x.get("published", ""), reverse=True)

        # Compute signals
        signals = self.compute_signals(papers)

        result = {
            "source": "arxiv",
            "scraped_at": datetime.now().isoformat(),
            "categories_scraped": self.AI_CATEGORIES,
            "total_papers": len(papers),
            "papers": papers,
            "bucket_signals": signals,
        }

        if save:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.output_dir / f"arxiv_{date_str}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Saved to {output_file}")

        return result


def main():
    """Main entry point."""
    scraper = ArxivScraper()
    result = scraper.run()

    print("\n" + "=" * 60)
    print("ARXIV AI RESEARCH SUMMARY")
    print("=" * 60)
    print(f"Categories scraped: {len(result['categories_scraped'])}")
    print(f"Total papers: {result['total_papers']}")

    print("\nMost Recent Papers:")
    print("-" * 60)
    for i, paper in enumerate(result['papers'][:10], 1):
        print(f"{i}. {paper['title'][:60]}...")
        print(f"   Categories: {', '.join(paper['categories'][:3])}")
        print(f"   Bucket: {paper['bucket']}")
        print()

    print("\nResearch Signals by Bucket:")
    print("-" * 60)
    for bucket, data in sorted(result['bucket_signals'].items(),
                               key=lambda x: -x[1]['paper_count']):
        print(f"{bucket}:")
        print(f"   Papers: {data['paper_count']} | Authors: {data['unique_authors']}")
        print(f"   Share: {data['share']*100:.1f}%")
        print(f"   Signal: {data['signal_interpretation']}")
        print()


if __name__ == "__main__":
    main()