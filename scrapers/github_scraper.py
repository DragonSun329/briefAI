"""
GitHub Scraper for AI Repository Trends

Scrapes trending AI repositories from GitHub to track
developer interest and open-source AI momentum.
"""

import requests
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional


class GitHubScraper:
    """Scraper for GitHub AI repositories."""

    BASE_URL = "https://api.github.com"

    # AI-related search queries
    AI_QUERIES = [
        "llm language:python",
        "machine learning",
        "deep learning",
        "transformer model",
        "chatgpt",
        "langchain",
        "llama",
        "stable diffusion",
        "neural network",
        "ai agent",
    ]

    # Known AI repositories to always track
    TRACKED_REPOS = [
        "openai/openai-python",
        "anthropics/anthropic-sdk-python",
        "huggingface/transformers",
        "langchain-ai/langchain",
        "run-llama/llama_index",
        "microsoft/autogen",
        "AUTOMATIC1111/stable-diffusion-webui",
        "oobabooga/text-generation-webui",
        "ggerganov/llama.cpp",
        "ollama/ollama",
        "meta-llama/llama",
        "lm-sys/FastChat",
    ]

    def __init__(self, token: Optional[str] = None, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "BriefAI/1.0",
        })
        if token:
            self.session.headers["Authorization"] = f"token {token}"

    def search_repositories(self, query: str, sort: str = "stars",
                           limit: int = 30) -> List[Dict[str, Any]]:
        """Search GitHub repositories."""
        url = f"{self.BASE_URL}/search/repositories"

        # Add date filter for recent activity
        date_filter = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        full_query = f"{query} pushed:>{date_filter}"

        params = {
            "q": full_query,
            "sort": sort,
            "order": "desc",
            "per_page": min(limit, 100),
        }

        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", [])
        except Exception as e:
            print(f"  Error searching for '{query}': {e}")
            return []

    def get_repository(self, full_name: str) -> Optional[Dict[str, Any]]:
        """Get repository details."""
        url = f"{self.BASE_URL}/repos/{full_name}"

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"  Error fetching {full_name}: {e}")
            return None

    def fetch_trending_ai_repos(self) -> List[Dict[str, Any]]:
        """Fetch trending AI repositories."""
        all_repos = []
        seen_ids = set()

        # Search with AI queries
        for query in self.AI_QUERIES:
            print(f"  Searching: {query}")
            repos = self.search_repositories(query, limit=20)
            for repo in repos:
                repo_id = repo.get("id")
                if repo_id and repo_id not in seen_ids:
                    seen_ids.add(repo_id)
                    all_repos.append(repo)

        # Also fetch tracked repos
        print("  Fetching tracked repositories...")
        for full_name in self.TRACKED_REPOS:
            repo = self.get_repository(full_name)
            if repo:
                repo_id = repo.get("id")
                if repo_id and repo_id not in seen_ids:
                    seen_ids.add(repo_id)
                    all_repos.append(repo)

        return all_repos

    def extract_repo_data(self, repo: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant fields from a repository."""
        return {
            "id": repo.get("id"),
            "full_name": repo.get("full_name"),
            "name": repo.get("name"),
            "owner": repo.get("owner", {}).get("login"),
            "description": repo.get("description", "")[:300] if repo.get("description") else "",
            "url": repo.get("html_url"),
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "watchers": repo.get("watchers_count", 0),
            "open_issues": repo.get("open_issues_count", 0),
            "language": repo.get("language"),
            "topics": repo.get("topics", []),
            "created_at": repo.get("created_at"),
            "updated_at": repo.get("updated_at"),
            "pushed_at": repo.get("pushed_at"),
            "license": repo.get("license", {}).get("spdx_id") if repo.get("license") else None,
        }

    def categorize_repo(self, repo: Dict[str, Any]) -> str:
        """Categorize a repository into AI trend buckets."""
        name = repo.get("full_name", "").lower()
        desc = repo.get("description", "").lower() if repo.get("description") else ""
        topics = [t.lower() for t in repo.get("topics", [])]
        combined = f"{name} {desc} {' '.join(topics)}"

        # Framework/library specific
        if any(x in combined for x in ['langchain', 'llama-index', 'llamaindex']):
            return "ai-agents"
        if any(x in combined for x in ['autogen', 'crew', 'agent']):
            return "ai-agents"

        # Company/model specific
        if any(x in combined for x in ['openai', 'gpt']):
            return "llm-foundation"
        if any(x in combined for x in ['anthropic', 'claude']):
            return "llm-foundation"
        if any(x in combined for x in ['huggingface', 'transformers']):
            return "llm-foundation"

        # Open source models
        if any(x in combined for x in ['llama', 'mistral', 'phi', 'qwen', 'gemma']):
            return "open-source-ai"
        if any(x in combined for x in ['ollama', 'llama.cpp', 'ggml', 'gguf']):
            return "open-source-ai"

        # Image generation
        if any(x in combined for x in ['stable-diffusion', 'diffusion', 'comfyui', 'automatic1111']):
            return "ai-image-generation"
        if any(x in combined for x in ['midjourney', 'dall-e', 'image generation']):
            return "ai-image-generation"

        # Other categories
        if any(x in combined for x in ['speech', 'whisper', 'tts', 'audio']):
            return "ai-audio"
        if any(x in combined for x in ['vision', 'yolo', 'detection', 'segmentation']):
            return "computer-vision"
        if any(x in combined for x in ['copilot', 'code', 'coding', 'cursor']):
            return "ai-coding"
        if any(x in combined for x in ['rag', 'retrieval', 'embedding', 'vector']):
            return "ai-infrastructure"

        return "ai-general"

    def compute_signals(self, repos: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute trend signals from GitHub repositories."""
        bucket_signals = {}

        for repo in repos:
            bucket = repo.get("bucket")
            if not bucket:
                continue

            stars = repo.get("stars", 0)
            forks = repo.get("forks", 0)

            # Momentum score: stars + forks*2
            momentum = stars + (forks * 2)

            if bucket not in bucket_signals:
                bucket_signals[bucket] = {
                    "repo_count": 0,
                    "total_stars": 0,
                    "total_forks": 0,
                    "total_momentum": 0,
                    "top_repos": [],
                }

            bucket_signals[bucket]["repo_count"] += 1
            bucket_signals[bucket]["total_stars"] += stars
            bucket_signals[bucket]["total_forks"] += forks
            bucket_signals[bucket]["total_momentum"] += momentum

            if len(bucket_signals[bucket]["top_repos"]) < 5:
                bucket_signals[bucket]["top_repos"].append({
                    "name": repo.get("full_name"),
                    "stars": stars,
                    "forks": forks,
                    "url": repo.get("url"),
                })

        # Add interpretations
        total_momentum = sum(d["total_momentum"] for d in bucket_signals.values())
        for bucket, data in bucket_signals.items():
            if total_momentum > 0:
                data["momentum_share"] = data["total_momentum"] / total_momentum
            else:
                data["momentum_share"] = 0

            # Interpret
            share = data["momentum_share"]
            if share > 0.25:
                data["signal_interpretation"] = "Dominant category - massive developer interest"
            elif share > 0.1:
                data["signal_interpretation"] = "Strong category - significant traction"
            elif share > 0.05:
                data["signal_interpretation"] = "Growing category - notable interest"
            else:
                data["signal_interpretation"] = "Niche category - specialized focus"

        return bucket_signals

    def run(self, save: bool = True) -> Dict[str, Any]:
        """Run the scraper and return results."""
        print("Fetching trending AI repositories from GitHub...")
        repos = self.fetch_trending_ai_repos()
        print(f"  Retrieved {len(repos)} repositories")

        # Process repos
        processed = []
        for repo in repos:
            data = self.extract_repo_data(repo)
            data["bucket"] = self.categorize_repo(repo)
            processed.append(data)

        # Sort by stars
        processed.sort(key=lambda x: x.get("stars", 0), reverse=True)

        # Compute signals
        signals = self.compute_signals(processed)

        result = {
            "source": "github",
            "scraped_at": datetime.now().isoformat(),
            "total_repos": len(processed),
            "repos": processed,
            "bucket_signals": signals,
        }

        if save:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.output_dir / f"github_{date_str}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Saved to {output_file}")

        return result


def main():
    """Main entry point."""
    scraper = GitHubScraper()
    result = scraper.run()

    print("\n" + "=" * 60)
    print("GITHUB AI TRENDS SUMMARY")
    print("=" * 60)
    print(f"Total repositories: {result['total_repos']}")

    print("\nTop 15 Repositories by Stars:")
    print("-" * 60)
    for i, repo in enumerate(result['repos'][:15], 1):
        print(f"{i}. {repo['full_name']}")
        print(f"   Stars: {repo['stars']:,} | Forks: {repo['forks']:,} | Bucket: {repo['bucket']}")
        print()

    print("\nSignals by Bucket:")
    print("-" * 60)
    for bucket, data in sorted(result['bucket_signals'].items(),
                               key=lambda x: -x[1]['total_momentum']):
        print(f"{bucket}:")
        print(f"   Repos: {data['repo_count']} | Stars: {data['total_stars']:,} | Forks: {data['total_forks']:,}")
        print(f"   Momentum share: {data['momentum_share']*100:.1f}%")
        print(f"   Signal: {data['signal_interpretation']}")
        print()


if __name__ == "__main__":
    main()