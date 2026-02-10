"""
Enhanced GitHub Scraper for Trend Radar TMS

Improves TMS coverage by:
1. Fetching GitHub trending repos (daily/weekly)
2. Fetching specific AI-related repos by topic
3. Using GitHub API for star history (velocity)
4. Better topic extraction for bucket matching

Output: data/alternative_signals/github_trending_YYYY-MM-DD.json
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
import json
import time
import os
import re


@dataclass
class GitHubRepo:
    """GitHub repository data."""
    name: str                        # repo name (short)
    full_name: str                   # owner/repo
    description: str = ""
    url: str = ""
    stars: int = 0
    stars_today: int = 0             # Stars gained today (from trending)
    stars_week: int = 0              # Stars gained this week
    forks: int = 0
    language: str = ""
    topics: List[str] = field(default_factory=list)
    owner: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class TrendingSignal:
    """Unified signal format for storage."""
    name: str
    source_type: str = "github"
    signal_type: str = "trending"
    description: str = ""
    url: str = ""
    category: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    date_observed: str = field(default_factory=lambda: date.today().isoformat())


# AI-related topics to search for better bucket coverage
AI_TOPICS = [
    # Core AI/ML
    "llm", "large-language-model", "machine-learning", "deep-learning",
    "artificial-intelligence", "neural-network", "transformer",

    # RAG & Retrieval
    "rag", "retrieval-augmented-generation", "vector-database",
    "embedding", "semantic-search",

    # Agents & Orchestration
    "ai-agent", "langchain", "llm-agent", "autonomous-agent",
    "multi-agent", "agent-framework",

    # Computer Vision
    "computer-vision", "image-generation", "diffusion-model",
    "stable-diffusion", "image-classification", "object-detection",

    # NLP
    "nlp", "natural-language-processing", "text-generation",
    "chatbot", "conversational-ai",

    # Speech & Audio
    "speech-recognition", "text-to-speech", "audio-processing",
    "whisper", "voice-assistant",

    # MLOps & Infrastructure
    "mlops", "model-serving", "inference", "fine-tuning",
    "model-optimization", "quantization",

    # Specific frameworks
    "pytorch", "tensorflow", "huggingface", "transformers",
    "openai", "anthropic", "ollama", "vllm",
]


class GitHubTrendingScraper:
    """
    Scrapes GitHub trending page.

    This uses the github.com/trending page which doesn't require authentication.
    """

    TRENDING_URL = "https://github.com/trending"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def get_trending(
        self,
        language: Optional[str] = None,
        since: str = "daily"  # daily, weekly, monthly
    ) -> List[GitHubRepo]:
        """
        Fetch trending repos from GitHub.

        Args:
            language: Filter by language (e.g., "python", "javascript")
            since: Time range ("daily", "weekly", "monthly")
        """
        repos = []

        # Build URL
        url = self.TRENDING_URL
        if language:
            url = f"{url}/{language}"
        url = f"{url}?since={since}"

        try:
            print(f"Fetching: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find repo articles
            articles = soup.find_all('article', class_='Box-row')

            for article in articles:
                try:
                    repo = self._parse_repo_article(article, since)
                    if repo:
                        repos.append(repo)
                except Exception as e:
                    print(f"  Error parsing repo: {e}")
                    continue

            print(f"  Found {len(repos)} trending repos")

        except requests.RequestException as e:
            print(f"  Error fetching trending: {e}")

        return repos

    def _parse_repo_article(self, article, since: str) -> Optional[GitHubRepo]:
        """Parse a single repo article from trending page."""
        # Get repo link
        h2 = article.find('h2')
        if not h2:
            return None

        link = h2.find('a')
        if not link:
            return None

        href = link.get('href', '').strip('/')
        if not href or '/' not in href:
            return None

        parts = href.split('/')
        owner = parts[0]
        name = parts[1] if len(parts) > 1 else href

        # Get description
        desc_p = article.find('p', class_='col-9')
        description = desc_p.get_text(strip=True) if desc_p else ""

        # Get language
        lang_span = article.find('span', itemprop='programmingLanguage')
        language = lang_span.get_text(strip=True) if lang_span else ""

        # Get stars
        stars = 0
        stars_link = article.find('a', href=re.compile(r'/stargazers$'))
        if stars_link:
            stars_text = stars_link.get_text(strip=True).replace(',', '')
            try:
                stars = int(stars_text)
            except ValueError:
                pass

        # Get stars today/week/month
        stars_today = 0
        stars_span = article.find('span', class_='d-inline-block float-sm-right')
        if stars_span:
            stars_text = stars_span.get_text(strip=True)
            # Extract number from "1,234 stars today"
            match = re.search(r'([\d,]+)\s*stars', stars_text)
            if match:
                try:
                    stars_today = int(match.group(1).replace(',', ''))
                except ValueError:
                    pass

        # Get forks
        forks = 0
        forks_link = article.find('a', href=re.compile(r'/forks$'))
        if forks_link:
            forks_text = forks_link.get_text(strip=True).replace(',', '')
            try:
                forks = int(forks_text)
            except ValueError:
                pass

        return GitHubRepo(
            name=name,
            full_name=href,
            description=description,
            url=f"https://github.com/{href}",
            stars=stars,
            stars_today=stars_today if since == "daily" else 0,
            stars_week=stars_today if since == "weekly" else 0,
            forks=forks,
            language=language,
            owner=owner,
        )


class GitHubAPIClient:
    """
    GitHub API client for detailed repo info.

    Uses GitHub API (with optional token for higher rate limits).
    """

    API_BASE = "https://api.github.com"

    def __init__(self, token: Optional[str] = None):
        """
        Initialize client.

        Args:
            token: GitHub personal access token (optional, for higher rate limits)
        """
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "BriefAI-TrendRadar/1.0",
        })
        if token:
            self.session.headers["Authorization"] = f"token {token}"

        self.rate_limit_remaining = 60  # Default for unauthenticated

    def search_repos_by_topic(
        self,
        topic: str,
        sort: str = "stars",
        limit: int = 30
    ) -> List[GitHubRepo]:
        """
        Search repos by topic.

        Args:
            topic: Topic to search (e.g., "llm", "ai-agent")
            sort: Sort by "stars", "forks", "updated"
            limit: Max repos to return
        """
        repos = []

        # Search query with topic
        query = f"topic:{topic}"

        try:
            url = f"{self.API_BASE}/search/repositories"
            params = {
                "q": query,
                "sort": sort,
                "order": "desc",
                "per_page": min(limit, 100),
            }

            response = self.session.get(url, params=params, timeout=30)

            # Update rate limit tracking
            self.rate_limit_remaining = int(
                response.headers.get('X-RateLimit-Remaining', 0)
            )

            if response.status_code == 403:
                print(f"  Rate limited! Remaining: {self.rate_limit_remaining}")
                return repos

            response.raise_for_status()
            data = response.json()

            for item in data.get("items", [])[:limit]:
                repo = GitHubRepo(
                    name=item.get("name", ""),
                    full_name=item.get("full_name", ""),
                    description=item.get("description") or "",
                    url=item.get("html_url", ""),
                    stars=item.get("stargazers_count", 0),
                    forks=item.get("forks_count", 0),
                    language=item.get("language") or "",
                    topics=item.get("topics", []),
                    owner=item.get("owner", {}).get("login", ""),
                    created_at=item.get("created_at"),
                    updated_at=item.get("updated_at"),
                )
                repos.append(repo)

        except requests.RequestException as e:
            print(f"  Error searching topic {topic}: {e}")

        return repos

    def get_repo_details(self, owner: str, repo: str) -> Optional[GitHubRepo]:
        """Get detailed info for a specific repo."""
        try:
            url = f"{self.API_BASE}/repos/{owner}/{repo}"
            response = self.session.get(url, timeout=30)

            self.rate_limit_remaining = int(
                response.headers.get('X-RateLimit-Remaining', 0)
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            item = response.json()

            return GitHubRepo(
                name=item.get("name", ""),
                full_name=item.get("full_name", ""),
                description=item.get("description") or "",
                url=item.get("html_url", ""),
                stars=item.get("stargazers_count", 0),
                forks=item.get("forks_count", 0),
                language=item.get("language") or "",
                topics=item.get("topics", []),
                owner=item.get("owner", {}).get("login", ""),
                created_at=item.get("created_at"),
                updated_at=item.get("updated_at"),
            )

        except requests.RequestException as e:
            print(f"  Error fetching {owner}/{repo}: {e}")
            return None


def convert_to_signals(repos: List[GitHubRepo]) -> List[TrendingSignal]:
    """Convert GitHubRepo objects to TrendingSignal format."""
    signals = []
    seen = set()

    for repo in repos:
        # Deduplicate
        if repo.full_name in seen:
            continue
        seen.add(repo.full_name)

        signal = TrendingSignal(
            name=repo.name,
            source_type="github",
            signal_type="trending",
            description=repo.description,
            url=repo.url,
            category=f"GitHub/{repo.language.lower() if repo.language else 'other'}",
            metrics={
                "stars": repo.stars,
                "stars_today": repo.stars_today,
                "stars_week": repo.stars_week,
                "forks": repo.forks,
                "language": repo.language,
                "topics": repo.topics,
                "owner": repo.owner,
                "timeframe": "daily" if repo.stars_today > 0 else "weekly",
            }
        )
        signals.append(signal)

    return signals


def save_signals(signals: List[TrendingSignal], output_dir: Path) -> Path:
    """Save signals to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    output_file = output_dir / f"github_trending_{today}.json"

    data = [asdict(s) for s in signals]

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return output_file


def main():
    """Main scraper workflow."""
    print("=" * 60)
    print("ENHANCED GITHUB SCRAPER FOR TMS")
    print("=" * 60)
    print()

    output_dir = Path(__file__).parent.parent / "data" / "alternative_signals"

    # Get GitHub token from environment (optional)
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        print("Using authenticated GitHub API (higher rate limits)")
    else:
        print("Using unauthenticated API (60 requests/hour limit)")
    print()

    all_repos = []

    # =========================================================================
    # 1. FETCH TRENDING REPOS (Scraping - no auth needed)
    # =========================================================================
    print("=" * 60)
    print("PHASE 1: GitHub Trending Page")
    print("=" * 60)

    scraper = GitHubTrendingScraper()

    # Daily trending - all languages
    print("\nFetching daily trending (all languages)...")
    daily_all = scraper.get_trending(since="daily")
    all_repos.extend(daily_all)
    time.sleep(1)

    # Daily trending - Python (most AI projects)
    print("\nFetching daily trending (Python)...")
    daily_python = scraper.get_trending(language="python", since="daily")
    all_repos.extend(daily_python)
    time.sleep(1)

    # Weekly trending for more coverage
    print("\nFetching weekly trending (all languages)...")
    weekly_all = scraper.get_trending(since="weekly")
    all_repos.extend(weekly_all)

    print(f"\nTotal from trending pages: {len(all_repos)} repos")

    # =========================================================================
    # 2. FETCH BY AI TOPICS (API - uses rate limit)
    # =========================================================================
    print()
    print("=" * 60)
    print("PHASE 2: Topic-Based Search (API)")
    print("=" * 60)

    api_client = GitHubAPIClient(token=github_token)

    # Prioritized topics for better bucket coverage
    priority_topics = [
        "llm", "rag", "ai-agent", "langchain",
        "computer-vision", "speech-recognition",
        "mlops", "fine-tuning", "stable-diffusion",
    ]

    for topic in priority_topics:
        if api_client.rate_limit_remaining < 5:
            print(f"\nRate limit low ({api_client.rate_limit_remaining}), stopping topic search")
            break

        print(f"\nSearching topic: {topic}")
        topic_repos = api_client.search_repos_by_topic(topic, limit=20)
        all_repos.extend(topic_repos)
        print(f"  Rate limit remaining: {api_client.rate_limit_remaining}")
        time.sleep(0.5)

    print(f"\nTotal repos collected: {len(all_repos)}")

    # =========================================================================
    # 3. DEDUPLICATE AND CONVERT
    # =========================================================================
    print()
    print("=" * 60)
    print("PHASE 3: Processing")
    print("=" * 60)

    signals = convert_to_signals(all_repos)
    print(f"Unique repos after deduplication: {len(signals)}")

    # =========================================================================
    # 4. SAVE
    # =========================================================================
    output_file = save_signals(signals, output_dir)
    print(f"\nSaved to: {output_file}")

    # =========================================================================
    # 5. SUMMARY
    # =========================================================================
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    # By language
    languages = {}
    for s in signals:
        lang = s.metrics.get("language") or "Unknown"
        languages[lang] = languages.get(lang, 0) + 1

    print("\nBy Language:")
    for lang, count in sorted(languages.items(), key=lambda x: -x[1])[:10]:
        print(f"  {lang}: {count}")

    # Top by stars today
    print("\nTop 10 by Stars Today:")
    sorted_signals = sorted(signals, key=lambda s: s.metrics.get("stars_today", 0), reverse=True)
    for i, s in enumerate(sorted_signals[:10], 1):
        stars_today = s.metrics.get("stars_today", 0)
        total_stars = s.metrics.get("stars", 0)
        print(f"  {i}. {s.name} (+{stars_today} today, {total_stars:,} total)")

    # Topics coverage
    all_topics = set()
    for s in signals:
        all_topics.update(s.metrics.get("topics", []))

    print(f"\nUnique topics found: {len(all_topics)}")
    ai_topics_found = [t for t in all_topics if any(
        ai in t.lower() for ai in ['ai', 'llm', 'ml', 'deep', 'neural', 'rag', 'agent']
    )]
    print(f"AI-related topics: {len(ai_topics_found)}")

    return signals


if __name__ == "__main__":
    main()