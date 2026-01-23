"""Fetch historical snapshots from Wayback Machine for backtesting."""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import time

try:
    import waybackpy
    WAYBACK_AVAILABLE = True
except ImportError:
    WAYBACK_AVAILABLE = False

import requests


@dataclass
class WaybackSnapshot:
    """A historical snapshot from Wayback Machine."""
    url: str
    original_url: str
    timestamp: str
    status_code: int
    content_type: str
    content: Optional[str] = None
    fetched_at: str = ""


class WaybackScraper:
    """Fetch historical web snapshots for backtesting."""

    # Sources we can fetch from Wayback
    SUPPORTED_SOURCES = {
        "jiqizhixin": "https://www.jiqizhixin.com",
        "qbitai": "https://www.qbitai.com",
        "github_trending": "https://github.com/trending",
        "huggingface_models": "https://huggingface.co/models",
        "hackernews": "https://news.ycombinator.com",
        "techcrunch_ai": "https://techcrunch.com/category/artificial-intelligence/",
    }

    def __init__(self, cache_dir: Optional[Path] = None):
        if not WAYBACK_AVAILABLE:
            raise ImportError("waybackpy is required. Install with: pip install waybackpy")

        self.cache_dir = cache_dir or Path("data/wayback_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_snapshot(
        self,
        url: str,
        target_date: date,
        fetch_content: bool = True,
    ) -> Optional[WaybackSnapshot]:
        """
        Get closest snapshot to target date.

        Args:
            url: URL to fetch historical version of
            target_date: Date to find closest snapshot to
            fetch_content: Whether to fetch full HTML content

        Returns:
            WaybackSnapshot or None if not found
        """
        # Check cache first
        cache_key = f"{url.replace('/', '_').replace(':', '')}_{target_date.isoformat()}"
        cache_file = self.cache_dir / f"{cache_key}.json"

        if cache_file.exists():
            with open(cache_file, encoding="utf-8") as f:
                data = json.load(f)
                return WaybackSnapshot(**data)

        try:
            # Use waybackpy to find nearest snapshot
            user_agent = "BriefAI Backtest Bot (research purposes)"
            availability = waybackpy.Url(url, user_agent).near(
                year=target_date.year,
                month=target_date.month,
                day=target_date.day,
            )

            snapshot = WaybackSnapshot(
                url=availability.archive_url,
                original_url=url,
                timestamp=availability.timestamp.isoformat() if availability.timestamp else "",
                status_code=200,
                content_type="text/html",
                fetched_at=datetime.now().isoformat(),
            )

            # Optionally fetch content
            if fetch_content:
                try:
                    resp = requests.get(availability.archive_url, timeout=30)
                    snapshot.content = resp.text[:100000]  # Limit size
                except Exception:
                    pass

            # Cache the result
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(asdict(snapshot), f, ensure_ascii=False, indent=2)

            # Rate limit
            time.sleep(1)

            return snapshot

        except Exception as e:
            print(f"Wayback fetch failed for {url} @ {target_date}: {e}")
            return None

    def get_source_snapshot(
        self,
        source_id: str,
        target_date: date,
    ) -> Optional[WaybackSnapshot]:
        """Get snapshot for a known source ID."""
        url = self.SUPPORTED_SOURCES.get(source_id)
        if not url:
            raise ValueError(f"Unknown source: {source_id}")

        return self.get_snapshot(url, target_date)

    def build_historical_snapshot(
        self,
        target_date: date,
        sources: Optional[List[str]] = None,
    ) -> Dict[str, WaybackSnapshot]:
        """
        Build a multi-source snapshot for a historical date.

        Returns dict of source_id -> WaybackSnapshot
        """
        if sources is None:
            sources = list(self.SUPPORTED_SOURCES.keys())

        snapshots = {}
        for source_id in sources:
            print(f"Fetching {source_id} @ {target_date}...")
            snapshot = self.get_source_snapshot(source_id, target_date)
            if snapshot:
                snapshots[source_id] = snapshot
            time.sleep(0.5)  # Rate limit between sources

        return snapshots


if __name__ == "__main__":
    # Example usage
    if not WAYBACK_AVAILABLE:
        print("waybackpy not installed. Run: pip install waybackpy")
    else:
        scraper = WaybackScraper()
        print(f"Supported sources: {list(scraper.SUPPORTED_SOURCES.keys())}")