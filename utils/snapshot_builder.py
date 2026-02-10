"""
Snapshot Builder for Trend Radar Validation System.

Consolidates scraper outputs into unified daily snapshots for offline validation.
This enables reproducible validation: same snapshot → same results.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import glob as glob_module


@dataclass
class DataHealth:
    """Health status of snapshot data sources."""
    sources_available: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    sources_stale: List[str] = field(default_factory=list)
    stale_threshold_days: int = 7


@dataclass
class SourceSnapshot:
    """Snapshot data from a single source."""
    source: str
    scraped_at: str
    record_count: int
    data: Dict[str, Any]
    file_path: str
    is_stale: bool = False


class SnapshotBuilder:
    """
    Consolidates scraper outputs into unified daily snapshots.

    Reads from data/alternative_signals/ and produces
    data/snapshots/source_snapshot_YYYY-MM-DD.json
    """

    # Expected source files and their patterns
    SOURCE_PATTERNS = {
        "github": "github_*.json",
        "huggingface": "huggingface_*.json",
        "reddit": "reddit_*.json",
        "hackernews": "hackernews_*.json",
        "twitter": "twitter_*.json",
        "arxiv": "arxiv_*.json",
        "paperswithcode": "paperswithcode_*.json",
        "polymarket": "polymarket_*.json",
        "manifold": "manifold_*.json",
        "metaculus": "metaculus_*.json",
        "crunchbase": "crunchbase_*.json",
        "openbook_vc": "openbook_vc_*.json",
        "sec": "sec_*.json",
        "news": "news_*.json",
        "ai_labs_news": "ai_labs_*.json",
        "podcast": "podcasts_*.json",  # Note: stored in cache directory
    }

    # Sources stored in cache directory instead of alternative_signals
    CACHE_SOURCES = {"podcast"}

    # Freshness thresholds by source (days)
    FRESHNESS_THRESHOLDS = {
        "github": 7,
        "huggingface": 7,
        "reddit": 3,
        "hackernews": 3,
        "twitter": 1,
        "arxiv": 14,
        "paperswithcode": 14,
        "polymarket": 7,
        "manifold": 7,
        "metaculus": 7,
        "crunchbase": 30,
        "openbook_vc": 30,
        "sec": 30,
        "news": 7,
        "ai_labs_news": 7,
        "podcast": 7,  # Weekly podcast freshness
    }

    def __init__(
        self,
        signals_dir: Optional[Path] = None,
        snapshots_dir: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
    ):
        data_dir = Path(__file__).parent.parent / "data"
        self.signals_dir = signals_dir or data_dir / "alternative_signals"
        self.snapshots_dir = snapshots_dir or data_dir / "snapshots"
        self.cache_dir = cache_dir or data_dir / "cache"

        # Create directories if needed
        self.signals_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def build_snapshot(
        self,
        snapshot_date: Optional[str] = None,
        save: bool = True,
    ) -> Dict[str, Any]:
        """
        Build a consolidated snapshot from all available sources.

        Args:
            snapshot_date: Date string YYYY-MM-DD (defaults to today)
            save: Whether to save the snapshot to disk

        Returns:
            Consolidated snapshot dictionary
        """
        if snapshot_date is None:
            snapshot_date = datetime.now().strftime("%Y-%m-%d")

        reference_date = datetime.strptime(snapshot_date, "%Y-%m-%d")

        # Collect data from all sources
        sources_data: Dict[str, SourceSnapshot] = {}
        data_health = DataHealth(stale_threshold_days=7)

        for source, pattern in self.SOURCE_PATTERNS.items():
            source_snapshot = self._find_latest_source_file(
                source, pattern, reference_date
            )

            if source_snapshot is None:
                data_health.sources_missing.append(source)
            elif source_snapshot.is_stale:
                data_health.sources_stale.append(source)
                sources_data[source] = source_snapshot
                data_health.sources_available.append(source)
            else:
                sources_data[source] = source_snapshot
                data_health.sources_available.append(source)

        # Build consolidated snapshot
        snapshot = {
            "snapshot_date": snapshot_date,
            "generated_at": datetime.now().isoformat(),
            "sources": {},
            "data_health": {
                "sources_available": data_health.sources_available,
                "sources_missing": data_health.sources_missing,
                "sources_stale": data_health.sources_stale,
                "total_sources": len(self.SOURCE_PATTERNS),
                "coverage_pct": len(data_health.sources_available) / len(self.SOURCE_PATTERNS) * 100,
            },
        }

        # Add source data
        for source, source_snapshot in sources_data.items():
            snapshot["sources"][source] = {
                "scraped_at": source_snapshot.scraped_at,
                "record_count": source_snapshot.record_count,
                "is_stale": source_snapshot.is_stale,
                "file_path": source_snapshot.file_path,
                "data": source_snapshot.data,
            }

        # Save if requested
        if save:
            snapshot_path = self.snapshots_dir / f"source_snapshot_{snapshot_date}.json"
            with open(snapshot_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)

        return snapshot

    def _find_latest_source_file(
        self,
        source: str,
        pattern: str,
        reference_date: datetime,
    ) -> Optional[SourceSnapshot]:
        """Find the most recent file for a source."""
        # Determine which directory to search
        search_dir = self.cache_dir if source in self.CACHE_SOURCES else self.signals_dir
        search_pattern = str(search_dir / pattern)
        files = glob_module.glob(search_pattern)

        if not files:
            return None

        # Sort by modification time (most recent first)
        files.sort(key=os.path.getmtime, reverse=True)

        # Try to load the most recent file
        for file_path in files:
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)

                # Handle case where data is a list instead of dict
                if isinstance(data, list):
                    # Wrap list in a dict with reasonable key
                    data = {"items": data}

                # Extract scraped_at timestamp
                scraped_at = data.get("scraped_at", "") if isinstance(data, dict) else ""
                if not scraped_at:
                    # Try to get from file modification time
                    mtime = os.path.getmtime(file_path)
                    scraped_at = datetime.fromtimestamp(mtime).isoformat()

                # Check staleness
                threshold_days = self.FRESHNESS_THRESHOLDS.get(source, 7)
                is_stale = self._is_stale(scraped_at, reference_date, threshold_days)

                # Count records
                record_count = self._count_records(source, data)

                # Extract relevant data
                extracted_data = self._extract_source_data(source, data)

                return SourceSnapshot(
                    source=source,
                    scraped_at=scraped_at,
                    record_count=record_count,
                    data=extracted_data,
                    file_path=str(file_path),
                    is_stale=is_stale,
                )

            except (json.JSONDecodeError, KeyError) as e:
                # Try next file
                continue

        return None

    def _is_stale(
        self,
        scraped_at: str,
        reference_date: datetime,
        threshold_days: int,
    ) -> bool:
        """Check if data is stale based on threshold."""
        try:
            # Parse ISO timestamp
            if "T" in scraped_at:
                scraped_date = datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
            else:
                scraped_date = datetime.strptime(scraped_at[:10], "%Y-%m-%d")

            # Make both naive for comparison
            if scraped_date.tzinfo:
                scraped_date = scraped_date.replace(tzinfo=None)

            age_days = (reference_date - scraped_date).days
            return age_days > threshold_days

        except (ValueError, TypeError):
            return True  # Assume stale if can't parse

    def _count_records(self, source: str, data: Dict[str, Any]) -> int:
        """Count records in source data."""
        # Source-specific counting logic
        if source == "github":
            return len(data.get("trending_repos", [])) + len(data.get("orgs", []))
        elif source == "huggingface":
            return len(data.get("models", [])) + len(data.get("spaces", []))
        elif source in ("reddit", "hackernews"):
            return len(data.get("posts", []))
        elif source == "arxiv":
            return len(data.get("papers", []))
        elif source in ("polymarket", "manifold", "metaculus"):
            return len(data.get("markets", [])) + len(data.get("questions", []))
        elif source == "crunchbase":
            return len(data.get("companies", []))
        elif source == "openbook_vc":
            return len(data.get("vc_firms", []))
        elif source == "news":
            return len(data.get("articles", []))
        elif source == "podcast":
            # Podcast data is stored as a list directly or under "episodes"
            if isinstance(data, list):
                return len(data)
            return len(data.get("episodes", data.get("items", [])))
        else:
            # Generic: count list values or return 1
            for key, value in data.items():
                if isinstance(value, list):
                    return len(value)
            return 1

    def _extract_source_data(self, source: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant data from source file."""
        # Remove metadata fields, keep actual data
        excluded_keys = {"source", "scraped_at", "generated_at", "total_count", "errors"}

        # Special handling for podcast: rename "items" to "episodes"
        if source == "podcast" and "items" in data and "episodes" not in data:
            data["episodes"] = data.pop("items")

        return {
            k: v for k, v in data.items()
            if k not in excluded_keys and not k.startswith("_")
        }

    def load_snapshot(self, snapshot_date: str) -> Optional[Dict[str, Any]]:
        """Load a saved snapshot by date."""
        snapshot_path = self.snapshots_dir / f"source_snapshot_{snapshot_date}.json"

        if not snapshot_path.exists():
            return None

        with open(snapshot_path, encoding="utf-8") as f:
            return json.load(f)

    def load_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """Load the most recent snapshot."""
        snapshots = list(self.snapshots_dir.glob("source_snapshot_*.json"))

        if not snapshots:
            return None

        # Sort by date in filename (descending)
        snapshots.sort(reverse=True)

        with open(snapshots[0], encoding="utf-8") as f:
            return json.load(f)

    def list_snapshots(self) -> List[str]:
        """List all available snapshot dates."""
        snapshots = list(self.snapshots_dir.glob("source_snapshot_*.json"))
        dates = []

        for path in snapshots:
            # Extract date from filename
            name = path.stem  # source_snapshot_YYYY-MM-DD
            parts = name.split("_")
            if len(parts) >= 3:
                dates.append(parts[2])

        dates.sort(reverse=True)
        return dates

    def get_source_data(
        self,
        snapshot: Dict[str, Any],
        source: str,
    ) -> Optional[Dict[str, Any]]:
        """Get data for a specific source from a snapshot."""
        sources = snapshot.get("sources", {})
        source_info = sources.get(source)

        if source_info:
            return source_info.get("data")
        return None

    def get_data_health(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Get data health summary from a snapshot."""
        return snapshot.get("data_health", {})


# Convenience function for quick snapshot building
def build_daily_snapshot(save: bool = True) -> Dict[str, Any]:
    """Build today's snapshot using default paths."""
    builder = SnapshotBuilder()
    return builder.build_snapshot(save=save)
