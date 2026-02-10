"""Tests for SnapshotBuilder - Trend Radar Validation System."""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.snapshot_builder import SnapshotBuilder, DataHealth, SourceSnapshot


class TestSnapshotBuilderInit:
    """Tests for SnapshotBuilder initialization."""

    def test_default_directories(self):
        """SnapshotBuilder uses default data directories."""
        builder = SnapshotBuilder()
        assert builder.signals_dir.name == "alternative_signals"
        assert builder.snapshots_dir.name == "snapshots"

    def test_creates_directories(self):
        """SnapshotBuilder creates directories if needed."""
        with TemporaryDirectory() as tmpdir:
            signals_dir = Path(tmpdir) / "signals"
            snapshots_dir = Path(tmpdir) / "snapshots"

            builder = SnapshotBuilder(
                signals_dir=signals_dir,
                snapshots_dir=snapshots_dir,
            )

            assert signals_dir.exists()
            assert snapshots_dir.exists()

    def test_source_patterns_defined(self):
        """SnapshotBuilder has source file patterns."""
        assert len(SnapshotBuilder.SOURCE_PATTERNS) > 0
        assert "github" in SnapshotBuilder.SOURCE_PATTERNS

    def test_freshness_thresholds_defined(self):
        """SnapshotBuilder has freshness thresholds."""
        assert len(SnapshotBuilder.FRESHNESS_THRESHOLDS) > 0
        assert SnapshotBuilder.FRESHNESS_THRESHOLDS["twitter"] < SnapshotBuilder.FRESHNESS_THRESHOLDS["crunchbase"]


class TestSnapshotBuilding:
    """Tests for snapshot building."""

    def test_build_empty_snapshot(self):
        """Build snapshot with no source files."""
        with TemporaryDirectory() as tmpdir:
            signals_dir = Path(tmpdir) / "signals"
            snapshots_dir = Path(tmpdir) / "snapshots"
            signals_dir.mkdir(parents=True)

            builder = SnapshotBuilder(
                signals_dir=signals_dir,
                snapshots_dir=snapshots_dir,
            )

            snapshot = builder.build_snapshot(save=False)

            assert "snapshot_date" in snapshot
            assert "sources" in snapshot
            assert "data_health" in snapshot

    def test_build_with_source_file(self):
        """Build snapshot with source file present."""
        with TemporaryDirectory() as tmpdir:
            signals_dir = Path(tmpdir) / "signals"
            snapshots_dir = Path(tmpdir) / "snapshots"
            signals_dir.mkdir(parents=True)

            # Create a github signal file
            github_file = signals_dir / "github_2026-01-21.json"
            github_data = {
                "scraped_at": datetime.now().isoformat(),
                "trending_repos": [
                    {"name": "deepseek-ai/DeepSeek-V3", "stars": 1000}
                ],
            }
            github_file.write_text(json.dumps(github_data))

            builder = SnapshotBuilder(
                signals_dir=signals_dir,
                snapshots_dir=snapshots_dir,
            )

            snapshot = builder.build_snapshot(save=False)

            assert "github" in snapshot["sources"]
            assert "github" in snapshot["data_health"]["sources_available"]

    def test_save_snapshot(self):
        """Snapshot is saved to file."""
        with TemporaryDirectory() as tmpdir:
            signals_dir = Path(tmpdir) / "signals"
            snapshots_dir = Path(tmpdir) / "snapshots"
            signals_dir.mkdir(parents=True)

            builder = SnapshotBuilder(
                signals_dir=signals_dir,
                snapshots_dir=snapshots_dir,
            )

            snapshot = builder.build_snapshot(save=True)
            snapshot_date = snapshot["snapshot_date"]

            # Check file was created
            snapshot_file = snapshots_dir / f"source_snapshot_{snapshot_date}.json"
            assert snapshot_file.exists()


class TestStaleDetection:
    """Tests for stale data detection."""

    def test_fresh_data_not_stale(self):
        """Recent data is not marked stale."""
        with TemporaryDirectory() as tmpdir:
            signals_dir = Path(tmpdir) / "signals"
            snapshots_dir = Path(tmpdir) / "snapshots"
            signals_dir.mkdir(parents=True)

            # Create a fresh github file
            github_file = signals_dir / "github_2026-01-21.json"
            github_data = {
                "scraped_at": datetime.now().isoformat(),
                "data": [],
            }
            github_file.write_text(json.dumps(github_data))

            builder = SnapshotBuilder(
                signals_dir=signals_dir,
                snapshots_dir=snapshots_dir,
            )

            snapshot = builder.build_snapshot(save=False)

            assert "github" not in snapshot["data_health"].get("sources_stale", [])

    def test_old_data_marked_stale(self):
        """Old data is marked as stale."""
        with TemporaryDirectory() as tmpdir:
            signals_dir = Path(tmpdir) / "signals"
            snapshots_dir = Path(tmpdir) / "snapshots"
            signals_dir.mkdir(parents=True)

            # Create an old twitter file (twitter threshold is 1 day)
            twitter_file = signals_dir / "twitter_2026-01-21.json"
            old_date = datetime.now() - timedelta(days=5)
            twitter_data = {
                "scraped_at": old_date.isoformat(),
                "data": [],
            }
            twitter_file.write_text(json.dumps(twitter_data))

            builder = SnapshotBuilder(
                signals_dir=signals_dir,
                snapshots_dir=snapshots_dir,
            )

            snapshot = builder.build_snapshot(save=False)

            # Twitter data older than 1 day should be stale
            assert "twitter" in snapshot["data_health"].get("sources_stale", [])


class TestSnapshotLoading:
    """Tests for snapshot loading."""

    def test_load_snapshot_by_date(self):
        """Load specific snapshot by date."""
        with TemporaryDirectory() as tmpdir:
            signals_dir = Path(tmpdir) / "signals"
            snapshots_dir = Path(tmpdir) / "snapshots"
            signals_dir.mkdir(parents=True)
            snapshots_dir.mkdir(parents=True)

            # Create a snapshot file
            snapshot_date = "2026-01-20"
            snapshot_file = snapshots_dir / f"source_snapshot_{snapshot_date}.json"
            snapshot_data = {
                "snapshot_date": snapshot_date,
                "sources": {},
                "data_health": {"sources_available": [], "sources_missing": [], "sources_stale": []},
            }
            snapshot_file.write_text(json.dumps(snapshot_data))

            builder = SnapshotBuilder(
                signals_dir=signals_dir,
                snapshots_dir=snapshots_dir,
            )

            loaded = builder.load_snapshot(snapshot_date)

            assert loaded is not None
            assert loaded["snapshot_date"] == snapshot_date

    def test_load_latest_snapshot(self):
        """Load most recent snapshot."""
        with TemporaryDirectory() as tmpdir:
            signals_dir = Path(tmpdir) / "signals"
            snapshots_dir = Path(tmpdir) / "snapshots"
            signals_dir.mkdir(parents=True)
            snapshots_dir.mkdir(parents=True)

            # Create multiple snapshot files
            for date in ["2026-01-18", "2026-01-19", "2026-01-20"]:
                snapshot_file = snapshots_dir / f"source_snapshot_{date}.json"
                snapshot_data = {"snapshot_date": date, "sources": {}, "data_health": {}}
                snapshot_file.write_text(json.dumps(snapshot_data))

            builder = SnapshotBuilder(
                signals_dir=signals_dir,
                snapshots_dir=snapshots_dir,
            )

            loaded = builder.load_latest_snapshot()

            assert loaded is not None
            assert loaded["snapshot_date"] == "2026-01-20"

    def test_load_missing_snapshot_returns_none(self):
        """Loading non-existent snapshot returns None."""
        with TemporaryDirectory() as tmpdir:
            builder = SnapshotBuilder(
                signals_dir=Path(tmpdir) / "signals",
                snapshots_dir=Path(tmpdir) / "snapshots",
            )

            loaded = builder.load_snapshot("2020-01-01")

            assert loaded is None


class TestDataHealth:
    """Tests for DataHealth tracking."""

    def test_data_health_dataclass(self):
        """DataHealth dataclass has expected fields."""
        health = DataHealth()

        assert hasattr(health, "sources_available")
        assert hasattr(health, "sources_missing")
        assert hasattr(health, "sources_stale")

    def test_missing_sources_tracked(self):
        """Missing sources are tracked in data health."""
        with TemporaryDirectory() as tmpdir:
            signals_dir = Path(tmpdir) / "signals"
            snapshots_dir = Path(tmpdir) / "snapshots"
            signals_dir.mkdir(parents=True)

            builder = SnapshotBuilder(
                signals_dir=signals_dir,
                snapshots_dir=snapshots_dir,
            )

            snapshot = builder.build_snapshot(save=False)

            # All sources should be missing
            assert len(snapshot["data_health"]["sources_missing"]) > 0


class TestSourceSnapshot:
    """Tests for SourceSnapshot dataclass."""

    def test_source_snapshot_fields(self):
        """SourceSnapshot has expected fields."""
        snapshot = SourceSnapshot(
            source="github",
            scraped_at="2026-01-21T12:00:00",
            record_count=10,
            data={"repos": []},
            file_path="/path/to/file.json",
        )

        assert snapshot.source == "github"
        assert snapshot.record_count == 10
        assert snapshot.is_stale is False


class TestMultipleSourceTypes:
    """Tests for handling multiple source types."""

    def test_github_source_parsing(self):
        """GitHub source files are parsed correctly."""
        with TemporaryDirectory() as tmpdir:
            signals_dir = Path(tmpdir) / "signals"
            snapshots_dir = Path(tmpdir) / "snapshots"
            signals_dir.mkdir(parents=True)

            # Create github file with trending repos
            github_file = signals_dir / "github_2026-01-21.json"
            github_data = {
                "scraped_at": datetime.now().isoformat(),
                "trending_repos": [
                    {"name": "openai/gpt-4", "stars": 50000},
                    {"name": "deepseek-ai/DeepSeek-V3", "stars": 30000},
                ],
                "orgs": [
                    {"name": "openai", "repos": 100},
                ],
            }
            github_file.write_text(json.dumps(github_data))

            builder = SnapshotBuilder(
                signals_dir=signals_dir,
                snapshots_dir=snapshots_dir,
            )

            snapshot = builder.build_snapshot(save=False)

            assert "github" in snapshot["sources"]
            github_snapshot = snapshot["sources"]["github"]
            assert "trending_repos" in github_snapshot or "data" in github_snapshot

    def test_huggingface_source_parsing(self):
        """HuggingFace source files are parsed correctly."""
        with TemporaryDirectory() as tmpdir:
            signals_dir = Path(tmpdir) / "signals"
            snapshots_dir = Path(tmpdir) / "snapshots"
            signals_dir.mkdir(parents=True)

            # Create huggingface file
            hf_file = signals_dir / "huggingface_2026-01-21.json"
            hf_data = {
                "scraped_at": datetime.now().isoformat(),
                "models": [
                    {"model_id": "deepseek-ai/deepseek-v3", "downloads": 100000},
                ],
                "spaces": [],
            }
            hf_file.write_text(json.dumps(hf_data))

            builder = SnapshotBuilder(
                signals_dir=signals_dir,
                snapshots_dir=snapshots_dir,
            )

            snapshot = builder.build_snapshot(save=False)

            assert "huggingface" in snapshot["sources"]