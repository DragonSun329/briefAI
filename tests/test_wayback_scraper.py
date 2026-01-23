"""Tests for Wayback Machine scraper."""

import json
import pytest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.wayback_scraper import WaybackSnapshot, WAYBACK_AVAILABLE

# Conditionally import WaybackScraper only if waybackpy is available
if WAYBACK_AVAILABLE:
    from scrapers.wayback_scraper import WaybackScraper


class TestWaybackSnapshot:
    """Tests for WaybackSnapshot dataclass."""

    def test_snapshot_fields(self):
        """Snapshot has expected fields."""
        snapshot = WaybackSnapshot(
            url="https://web.archive.org/web/20241215/https://github.com/trending",
            original_url="https://github.com/trending",
            timestamp="2024-12-15T12:00:00",
            status_code=200,
            content_type="text/html",
        )

        assert snapshot.url.startswith("https://web.archive.org")
        assert snapshot.original_url == "https://github.com/trending"
        assert snapshot.status_code == 200

    def test_snapshot_with_content(self):
        """Snapshot can include content."""
        snapshot = WaybackSnapshot(
            url="https://web.archive.org/web/20241215/https://example.com",
            original_url="https://example.com",
            timestamp="2024-12-15T12:00:00",
            status_code=200,
            content_type="text/html",
            content="<html><body>Test</body></html>",
            fetched_at="2026-01-22T12:00:00",
        )

        assert snapshot.content is not None
        assert "Test" in snapshot.content
        assert snapshot.fetched_at != ""

    def test_snapshot_defaults(self):
        """Snapshot has correct defaults."""
        snapshot = WaybackSnapshot(
            url="https://web.archive.org/test",
            original_url="https://test.com",
            timestamp="2024-12-15",
            status_code=200,
            content_type="text/html",
        )

        assert snapshot.content is None
        assert snapshot.fetched_at == ""


@pytest.mark.skipif(not WAYBACK_AVAILABLE, reason="waybackpy not installed")
class TestWaybackScraper:
    """Tests for Wayback Machine scraper."""

    def test_supported_sources_defined(self):
        """Scraper has supported sources."""
        assert len(WaybackScraper.SUPPORTED_SOURCES) > 0
        assert "github_trending" in WaybackScraper.SUPPORTED_SOURCES
        assert "hackernews" in WaybackScraper.SUPPORTED_SOURCES

    def test_cache_directory_created(self):
        """Scraper creates cache directory."""
        with TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "wayback_cache"
            scraper = WaybackScraper(cache_dir=cache_dir)
            assert cache_dir.exists()

    def test_unknown_source_raises(self):
        """Unknown source ID raises ValueError."""
        with TemporaryDirectory() as tmpdir:
            scraper = WaybackScraper(cache_dir=Path(tmpdir) / "cache")
            with pytest.raises(ValueError, match="Unknown source"):
                scraper.get_source_snapshot("unknown_source_xyz", date(2024, 12, 15))

    def test_cache_hit(self):
        """Cached snapshots are returned from cache."""
        with TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache_dir.mkdir(parents=True)

            # Pre-populate cache
            cache_key = "https__github.com_trending_2024-12-15"
            cache_file = cache_dir / f"{cache_key}.json"
            cached_data = {
                "url": "https://web.archive.org/web/20241215/https://github.com/trending",
                "original_url": "https://github.com/trending",
                "timestamp": "2024-12-15T00:00:00",
                "status_code": 200,
                "content_type": "text/html",
                "content": "<html>Cached</html>",
                "fetched_at": "2026-01-20T12:00:00",
            }
            cache_file.write_text(json.dumps(cached_data))

            scraper = WaybackScraper(cache_dir=cache_dir)
            snapshot = scraper.get_snapshot(
                "https://github.com/trending",
                date(2024, 12, 15),
            )

            assert snapshot is not None
            assert "Cached" in snapshot.content


@pytest.mark.skipif(not WAYBACK_AVAILABLE, reason="waybackpy not installed")
@pytest.mark.integration
class TestWaybackScraperIntegration:
    """Integration tests that hit the real Wayback Machine API.

    These tests are marked with @pytest.mark.integration and are
    skipped by default. Run with: pytest -m integration
    """

    def test_fetch_github_trending_historical(self):
        """Fetch historical GitHub trending page."""
        scraper = WaybackScraper()
        snapshot = scraper.get_source_snapshot(
            "github_trending",
            date(2024, 12, 15),
        )

        # May or may not find a snapshot depending on Wayback availability
        if snapshot:
            assert snapshot.original_url == "https://github.com/trending"
            assert "2024" in snapshot.timestamp

    def test_fetch_hackernews_historical(self):
        """Fetch historical Hacker News page."""
        scraper = WaybackScraper()
        snapshot = scraper.get_source_snapshot(
            "hackernews",
            date(2024, 11, 1),
        )

        if snapshot:
            assert snapshot.original_url == "https://news.ycombinator.com"


class TestWaybackAvailabilityFlag:
    """Tests for WAYBACK_AVAILABLE flag."""

    def test_flag_is_boolean(self):
        """WAYBACK_AVAILABLE is a boolean."""
        assert isinstance(WAYBACK_AVAILABLE, bool)

    @pytest.mark.skipif(WAYBACK_AVAILABLE, reason="Test for when waybackpy is NOT installed")
    def test_import_fails_gracefully(self):
        """When waybackpy is not installed, WAYBACK_AVAILABLE is False."""
        assert WAYBACK_AVAILABLE is False