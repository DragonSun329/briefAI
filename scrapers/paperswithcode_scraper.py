"""
Papers With Code Scraper for AI Benchmark Trends

Scrapes trending papers and SOTA benchmarks from Papers With Code
to track research breakthroughs and competitive landscape.
"""

import requests
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class PapersWithCodeScraper:
    """Scraper for Papers With Code trends and benchmarks.
    
    NOTE (Feb 2026): The paperswithcode.com API v1 now redirects to HuggingFace.
    We use HuggingFace's daily papers API as a fallback when PwC returns non-JSON.
    """

    BASE_URL = "https://paperswithcode.com/api/v1"
    HF_PAPERS_API = "https://huggingface.co/api/daily_papers"

    # Key benchmarks to track
    KEY_BENCHMARKS = [
        "imagenet",
        "coco",
        "squad",
        "glue",
        "superglue",
        "mmlu",
        "humaneval",
        "gsm8k",
        "hellaswag",
    ]

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BriefAI/1.0",
        })

    def fetch_trending_papers(self, page: int = 1, items_per_page: int = 50) -> List[Dict[str, Any]]:
        """Fetch trending papers. Tries PapersWithCode first, falls back to HuggingFace."""
        # Try PapersWithCode API first
        url = f"{self.BASE_URL}/papers/"
        params = {
            "page": page,
            "items_per_page": items_per_page,
            "ordering": "-github_stars",
        }

        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "json" not in content_type and "application" not in content_type:
                raise ValueError(f"Non-JSON response (content-type: {content_type})")
            data = resp.json()
            results = data.get("results", [])
            if results:
                return results
        except Exception as e:
            print(f"  PapersWithCode API failed ({e}), falling back to HuggingFace...")

        # Fallback: HuggingFace Daily Papers API
        return self._fetch_hf_papers(items_per_page)

    def _fetch_hf_papers(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch trending papers from HuggingFace Daily Papers API."""
        try:
            resp = self.session.get(self.HF_PAPERS_API, timeout=30)
            resp.raise_for_status()
            hf_papers = resp.json()

            # Convert HuggingFace format to PapersWithCode-compatible format
            papers = []
            for item in hf_papers[:limit]:
                paper_data = item.get("paper", {})
                papers.append({
                    "id": paper_data.get("id", ""),
                    "title": paper_data.get("title", ""),
                    "abstract": paper_data.get("summary", ""),
                    "url_abs": f"https://arxiv.org/abs/{paper_data.get('id', '')}",
                    "url_pdf": f"https://arxiv.org/pdf/{paper_data.get('id', '')}",
                    "arxiv_id": paper_data.get("id"),
                    "github_stars": paper_data.get("upvotes", 0),
                    "published": paper_data.get("publishedAt"),
                    "authors": [a.get("name", "") for a in paper_data.get("authors", [])],
                    "tasks": [],
                })
            print(f"  Fetched {len(papers)} papers from HuggingFace Daily Papers")
            return papers
        except Exception as e:
            print(f"  Error fetching HuggingFace papers: {e}")
            return []

    def fetch_paper_details(self, paper_id: str) -> Optional[Dict[str, Any]]:
        """Fetch detailed information about a paper."""
        url = f"{self.BASE_URL}/papers/{paper_id}/"

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"  Error fetching paper {paper_id}: {e}")
            return None

    def fetch_sota_results(self, task: str = None, dataset: str = None,
                           limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch state-of-the-art results."""
        url = f"{self.BASE_URL}/results/"
        params = {"items_per_page": limit}

        if task:
            params["task"] = task
        if dataset:
            params["dataset"] = dataset

        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
        except Exception as e:
            print(f"  Error fetching SOTA results: {e}")
            return []

    def fetch_tasks(self, area: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch ML tasks/benchmarks."""
        url = f"{self.BASE_URL}/tasks/"
        params = {"items_per_page": limit}

        if area:
            params["area"] = area

        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "json" not in content_type and "application" not in content_type:
                print(f"  Tasks API returned non-JSON (content-type: {content_type}), skipping")
                return []
            data = resp.json()
            return data.get("results", [])
        except Exception as e:
            print(f"  Error fetching tasks: {e}")
            return []

    def extract_paper_data(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant fields from a paper."""
        return {
            "id": paper.get("id"),
            "title": paper.get("title"),
            "abstract": paper.get("abstract", "")[:500] if paper.get("abstract") else "",
            "url_abs": paper.get("url_abs"),
            "url_pdf": paper.get("url_pdf"),
            "arxiv_id": paper.get("arxiv_id"),
            "github_stars": paper.get("github_stars", 0),
            "published": paper.get("published"),
            "authors": paper.get("authors", []),
            "tasks": paper.get("tasks", []),
        }

    def categorize_paper(self, paper: Dict[str, Any]) -> str:
        """Categorize a paper into AI trend buckets."""
        title = paper.get("title", "").lower()
        abstract = paper.get("abstract", "").lower() if paper.get("abstract") else ""
        tasks = [t.lower() if isinstance(t, str) else t.get("name", "").lower()
                 for t in paper.get("tasks", [])]
        combined = f"{title} {abstract} {' '.join(str(t) for t in tasks)}"

        # Categorize based on content
        if any(kw in combined for kw in ['language model', 'llm', 'gpt', 'transformer', 'bert']):
            return "llm-foundation"
        if any(kw in combined for kw in ['llama', 'mistral', 'open source', 'fine-tun']):
            return "open-source-ai"
        if any(kw in combined for kw in ['diffusion', 'image generation', 'text-to-image', 'stable']):
            return "ai-image-generation"
        if any(kw in combined for kw in ['object detection', 'segmentation', 'image classification']):
            return "computer-vision"
        if any(kw in combined for kw in ['speech', 'audio', 'voice', 'asr', 'tts']):
            return "ai-audio"
        if any(kw in combined for kw in ['reinforcement', 'reward', 'policy']):
            return "ai-research"
        if any(kw in combined for kw in ['agent', 'reasoning', 'planning', 'tool']):
            return "ai-agents"
        if any(kw in combined for kw in ['code', 'programming', 'software']):
            return "ai-coding"

        return "ai-general"

    def compute_signals(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute trend signals from papers."""
        bucket_signals = {}

        for paper in papers:
            bucket = paper.get("bucket")
            if not bucket:
                continue

            stars = paper.get("github_stars", 0)

            if bucket not in bucket_signals:
                bucket_signals[bucket] = {
                    "paper_count": 0,
                    "total_stars": 0,
                    "top_papers": [],
                }

            bucket_signals[bucket]["paper_count"] += 1
            bucket_signals[bucket]["total_stars"] += stars

            if len(bucket_signals[bucket]["top_papers"]) < 5:
                bucket_signals[bucket]["top_papers"].append({
                    "title": paper.get("title"),
                    "stars": stars,
                    "url": paper.get("url_abs"),
                })

        # Add interpretations
        total_stars = sum(d["total_stars"] for d in bucket_signals.values())
        for bucket, data in bucket_signals.items():
            if total_stars > 0:
                data["star_share"] = data["total_stars"] / total_stars
            else:
                data["star_share"] = 0

            if data["paper_count"] > 0:
                data["avg_stars"] = data["total_stars"] / data["paper_count"]
            else:
                data["avg_stars"] = 0

            # Interpret
            share = data["star_share"]
            if share > 0.2:
                data["signal_interpretation"] = "Hot research area with high implementation interest"
            elif share > 0.1:
                data["signal_interpretation"] = "Active area with significant code adoption"
            elif share > 0.05:
                data["signal_interpretation"] = "Growing interest in implementations"
            else:
                data["signal_interpretation"] = "Research-focused with limited code adoption"

        return bucket_signals

    def run(self, save: bool = True) -> Dict[str, Any]:
        """Run the scraper and return results."""
        print("Fetching trending papers from Papers With Code...")
        papers = self.fetch_trending_papers(items_per_page=100)
        print(f"  Retrieved {len(papers)} papers")

        # Process papers
        processed = []
        for paper in papers:
            data = self.extract_paper_data(paper)
            data["bucket"] = self.categorize_paper(paper)
            processed.append(data)

        # Sort by stars
        processed.sort(key=lambda x: x.get("github_stars", 0), reverse=True)

        # Compute signals
        signals = self.compute_signals(processed)

        # Fetch some tasks/benchmarks info
        print("  Fetching ML tasks...")
        tasks = self.fetch_tasks(limit=30)

        result = {
            "source": "paperswithcode",
            "scraped_at": datetime.now().isoformat(),
            "total_papers": len(processed),
            "papers": processed,
            "bucket_signals": signals,
            "tasks_count": len(tasks),
        }

        if save:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.output_dir / f"paperswithcode_{date_str}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Saved to {output_file}")

        return result


def main():
    """Main entry point."""
    scraper = PapersWithCodeScraper()
    result = scraper.run()

    print("\n" + "=" * 60)
    print("PAPERS WITH CODE AI TRENDS")
    print("=" * 60)
    print(f"Total papers analyzed: {result['total_papers']}")

    print("\nTop 10 Papers by GitHub Stars:")
    print("-" * 60)
    for i, paper in enumerate(result['papers'][:10], 1):
        stars = paper.get('github_stars', 0)
        print(f"{i}. {paper['title'][:55]}...")
        print(f"   Stars: {stars:,} | Bucket: {paper['bucket']}")
        print()

    print("\nSignals by Bucket:")
    print("-" * 60)
    for bucket, data in sorted(result['bucket_signals'].items(),
                               key=lambda x: -x[1]['total_stars']):
        print(f"{bucket}:")
        print(f"   Papers: {data['paper_count']} | Total stars: {data['total_stars']:,}")
        print(f"   Star share: {data['star_share']*100:.1f}%")
        print(f"   Signal: {data['signal_interpretation']}")
        print()


if __name__ == "__main__":
    main()