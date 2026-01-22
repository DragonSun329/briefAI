"""
GitHub Tools

Active operations for fetching live GitHub repository data.
"""

import os
import json
import requests
from pathlib import Path
from typing import TYPE_CHECKING
from loguru import logger

from mcp_server.errors import MCPToolError, RateLimitedError

if TYPE_CHECKING:
    from fastmcp import FastMCP


def get_headers() -> dict:
    """Get GitHub API headers with optional authentication."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_cached_github_data(owner: str, repo: str) -> dict | None:
    """Try to get repo data from cached scraper output."""
    cache_dir = Path(__file__).parent.parent.parent / "data" / "alternative_signals"
    if not cache_dir.exists():
        return None

    github_files = sorted(cache_dir.glob("github_*.json"), reverse=True)
    if not github_files:
        return None

    try:
        with open(github_files[0], 'r') as f:
            data = json.load(f)
            full_name = f"{owner}/{repo}".lower()
            for repo_data in data.get("repositories", []):
                if repo_data.get("full_name", "").lower() == full_name:
                    return {
                        "stars": repo_data.get("stars", 0),
                        "forks": repo_data.get("forks", 0),
                        "open_issues": repo_data.get("open_issues", 0),
                        "last_push": repo_data.get("pushed_at"),
                        "language": repo_data.get("language"),
                        "license": repo_data.get("license"),
                    }
    except Exception as e:
        logger.debug(f"Could not read cached GitHub data: {e}")

    return None


def register(mcp: "FastMCP"):
    """Register GitHub tools with MCP server."""

    @mcp.tool()
    def get_repo_health(owner: str, repo: str) -> dict:
        """Get live GitHub repository health metrics.

        Fetches current stats from GitHub API with fallback to cached data.

        Args:
            owner: GitHub username or organization
            repo: Repository name

        Returns:
            Dict with stars, forks, issues, last_push, language, license
        """
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}"
            resp = requests.get(url, headers=get_headers(), timeout=10)

            if resp.status_code == 403:
                # Rate limited - try cache first
                cached = _get_cached_github_data(owner, repo)
                if cached:
                    logger.info(f"GitHub rate limited, using cached data for {owner}/{repo}")
                    return {**cached, "_source": "cache"}
                raise RateLimitedError("github", retry_after=60)

            if resp.status_code == 404:
                raise MCPToolError("github", f"Repository not found: {owner}/{repo}")

            resp.raise_for_status()
            data = resp.json()

            return {
                "stars": data.get("stargazers_count"),
                "forks": data.get("forks_count"),
                "open_issues": data.get("open_issues_count"),
                "last_push": data.get("pushed_at"),
                "language": data.get("language"),
                "license": data.get("license", {}).get("spdx_id") if data.get("license") else None,
                "description": data.get("description"),
                "topics": data.get("topics", []),
                "_source": "live"
            }

        except requests.RequestException as e:
            # Network error - try cache
            cached = _get_cached_github_data(owner, repo)
            if cached:
                logger.warning(f"GitHub API error, using cached data: {e}")
                return {**cached, "_source": "cache"}
            raise MCPToolError("github", str(e))

    @mcp.tool()
    def get_repo_activity(owner: str, repo: str, days: int = 30) -> dict:
        """Get recent commit activity for a repository.

        Args:
            owner: GitHub username or organization
            repo: Repository name
            days: Number of days to look back (default 30)

        Returns:
            Dict with commit counts, contributors, and activity patterns
        """
        try:
            # Get commit activity
            url = f"https://api.github.com/repos/{owner}/{repo}/stats/commit_activity"
            resp = requests.get(url, headers=get_headers(), timeout=10)

            if resp.status_code == 403:
                raise RateLimitedError("github", retry_after=60)
            if resp.status_code == 404:
                raise MCPToolError("github", f"Repository not found: {owner}/{repo}")

            # GitHub returns 202 if stats are being computed
            if resp.status_code == 202:
                return {
                    "status": "computing",
                    "message": "GitHub is computing stats, try again in a few seconds"
                }

            resp.raise_for_status()
            data = resp.json()

            # data is list of weekly commit counts
            weeks_to_check = min(days // 7, len(data))
            recent_weeks = data[-weeks_to_check:] if weeks_to_check > 0 else data

            total_commits = sum(week.get("total", 0) for week in recent_weeks)

            return {
                "total_commits": total_commits,
                "weeks_analyzed": len(recent_weeks),
                "avg_commits_per_week": total_commits / len(recent_weeks) if recent_weeks else 0,
                "recent_activity": [
                    {"week": week.get("week"), "commits": week.get("total", 0)}
                    for week in recent_weeks[-4:]  # Last 4 weeks
                ]
            }

        except requests.RequestException as e:
            raise MCPToolError("github", str(e))

    @mcp.tool()
    def search_repos(query: str, sort: str = "stars", limit: int = 10) -> dict:
        """Search GitHub repositories.

        Args:
            query: Search query (e.g., "llm agent python")
            sort: Sort by 'stars', 'forks', or 'updated'
            limit: Maximum results (1-100)

        Returns:
            Dict with list of matching repositories
        """
        try:
            url = "https://api.github.com/search/repositories"
            params = {
                "q": query,
                "sort": sort,
                "order": "desc",
                "per_page": min(limit, 100)
            }
            resp = requests.get(url, headers=get_headers(), params=params, timeout=15)

            if resp.status_code == 403:
                raise RateLimitedError("github", retry_after=60)

            resp.raise_for_status()
            data = resp.json()

            return {
                "total_count": data.get("total_count", 0),
                "repositories": [
                    {
                        "full_name": repo.get("full_name"),
                        "description": repo.get("description"),
                        "stars": repo.get("stargazers_count"),
                        "forks": repo.get("forks_count"),
                        "language": repo.get("language"),
                        "updated_at": repo.get("updated_at"),
                        "topics": repo.get("topics", [])
                    }
                    for repo in data.get("items", [])
                ]
            }

        except requests.RequestException as e:
            raise MCPToolError("github", str(e))
