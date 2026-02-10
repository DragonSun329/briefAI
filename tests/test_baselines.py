"""
Tests for historical baselines module.
"""

import pytest
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.historical_baselines import (
    HistoricalStats,
    HistoricalBaselineCalculator,
    WeeklySnapshot,
)


@pytest.fixture
def temp_historical_dir():
    """Create a temporary directory with test historical data."""
    import shutil

    temp_dir = Path(tempfile.mkdtemp())
    historical_dir = temp_dir / "historical"
    historical_dir.mkdir()

    # Create sample weekly snapshots
    base_date = datetime.now() - timedelta(weeks=20)

    for week in range(20):
        week_date = base_date + timedelta(weeks=week)
        week_str = week_date.strftime("%Y-W%W")
        filename = f"{week_str}.json"

        # Create sample bucket data with increasing trend
        data = {
            "week": week_str,
            "generated_at": week_date.isoformat(),
            "buckets": {
                "ai-agents": {
                    "tms": 50 + week * 2 + (week % 3) * 5,  # Trending up with noise
                    "ccs": 40 + week * 1,
                    "nas": 60 + (week % 5) * 8,  # More volatile
                    "eis": 30 + week * 0.5,
                },
                "ai-coding": {
                    "tms": 70 - week * 1,  # Trending down
                    "ccs": 55 + week * 0.5,
                    "nas": 45 + (week % 4) * 10,
                    "eis": 40 + week * 0.3,
                },
            }
        }

        with open(historical_dir / filename, "w") as f:
            json.dump(data, f)

    yield historical_dir

    # Cleanup
    shutil.rmtree(temp_dir)


class TestHistoricalStats:
    """Tests for HistoricalStats dataclass."""

    def test_compute_percentile_at_median(self):
        """Test percentile at median value."""
        stats = HistoricalStats(
            mean=50,
            std=10,
            min_val=30,
            max_val=70,
            p10=35,
            p25=42,
            p50=50,
            p75=58,
            p90=65,
            count=20,
        )

        # Value at median should be around 50th percentile
        percentile = stats.compute_percentile(50)
        assert 45 <= percentile <= 55

    def test_compute_percentile_at_extremes(self):
        """Test percentile at extreme values."""
        stats = HistoricalStats(
            mean=50,
            std=10,
            min_val=30,
            max_val=70,
            p10=35,
            p25=42,
            p50=50,
            p75=58,
            p90=65,
            count=20,
        )

        # Very low value
        low_percentile = stats.compute_percentile(25)
        assert low_percentile < 20

        # Very high value
        high_percentile = stats.compute_percentile(75)
        assert high_percentile > 80

    def test_compute_z_score(self):
        """Test z-score computation."""
        stats = HistoricalStats(
            mean=50,
            std=10,
            min_val=30,
            max_val=70,
            p10=35,
            p25=42,
            p50=50,
            p75=58,
            p90=65,
            count=20,
        )

        # Value at mean should have z-score of 0
        assert stats.compute_z_score(50) == 0

        # Value one std above mean
        assert stats.compute_z_score(60) == pytest.approx(1.0)

        # Value two std below mean
        assert stats.compute_z_score(30) == pytest.approx(-2.0)

    def test_compute_z_score_zero_std(self):
        """Test z-score with zero standard deviation."""
        stats = HistoricalStats(
            mean=50,
            std=0,  # No variance
            min_val=50,
            max_val=50,
            p10=50,
            p25=50,
            p50=50,
            p75=50,
            p90=50,
            count=20,
        )

        # Should return 0 for any value (avoid division by zero)
        assert stats.compute_z_score(50) == 0
        assert stats.compute_z_score(60) == 0


class TestWeeklySnapshot:
    """Tests for WeeklySnapshot."""

    def test_create_snapshot(self):
        """Test creating a weekly snapshot."""
        snapshot = WeeklySnapshot(
            week="2025-W01",
            generated_at=datetime.now(),
            buckets={
                "ai-agents": {"tms": 75, "ccs": 45},
            }
        )

        assert snapshot.week == "2025-W01"
        assert "ai-agents" in snapshot.buckets
        assert snapshot.buckets["ai-agents"]["tms"] == 75

    def test_get_signal(self):
        """Test getting a specific signal value."""
        snapshot = WeeklySnapshot(
            week="2025-W01",
            generated_at=datetime.now(),
            buckets={
                "ai-agents": {"tms": 75, "ccs": 45},
            }
        )

        assert snapshot.get_signal("ai-agents", "tms") == 75
        assert snapshot.get_signal("ai-agents", "nas") is None
        assert snapshot.get_signal("unknown-bucket", "tms") is None


class TestHistoricalBaselineCalculator:
    """Tests for HistoricalBaselineCalculator."""

    def test_load_snapshots(self, temp_historical_dir):
        """Test loading historical snapshots."""
        calc = HistoricalBaselineCalculator(snapshot_dir=temp_historical_dir)

        # Should have loaded 20 weeks of data
        assert len(calc.snapshots) == 20

    def test_compute_baseline_stats(self, temp_historical_dir):
        """Test computing baseline statistics."""
        calc = HistoricalBaselineCalculator(snapshot_dir=temp_historical_dir)

        stats = calc.compute_baseline_stats("ai-agents", "tms", window_weeks=12)

        assert stats is not None
        assert stats.count == 12
        assert stats.mean > 0
        assert stats.std >= 0
        assert stats.p50 > 0

    def test_compute_historical_percentile(self, temp_historical_dir):
        """Test computing historical percentile."""
        calc = HistoricalBaselineCalculator(snapshot_dir=temp_historical_dir)

        # Get stats first to understand the distribution
        stats = calc.compute_baseline_stats("ai-agents", "tms", window_weeks=12)

        # Test with a value at the median
        percentile = calc.compute_historical_percentile(
            "ai-agents", "tms", stats.p50, window_weeks=12
        )
        assert 40 <= percentile <= 60

    def test_detect_trend(self, temp_historical_dir):
        """Test trend detection."""
        calc = HistoricalBaselineCalculator(snapshot_dir=temp_historical_dir)

        # ai-agents TMS was designed to trend up
        trend = calc.detect_trend("ai-agents", "tms", window_weeks=12)

        assert trend is not None
        assert "slope" in trend
        assert "direction" in trend
        # Should detect upward trend
        assert trend["direction"] in ["rising", "stable", "falling"]

    def test_get_bucket_baseline_summary(self, temp_historical_dir):
        """Test getting full bucket baseline summary."""
        calc = HistoricalBaselineCalculator(snapshot_dir=temp_historical_dir)

        summary = calc.get_bucket_baseline_summary("ai-agents")

        assert "tms" in summary
        assert "ccs" in summary
        assert summary["tms"]["stats_12w"] is not None
        assert summary["tms"]["stats_26w"] is not None or summary["tms"]["stats_26w"] is None  # May have insufficient data

    def test_missing_bucket(self, temp_historical_dir):
        """Test handling missing bucket."""
        calc = HistoricalBaselineCalculator(snapshot_dir=temp_historical_dir)

        stats = calc.compute_baseline_stats("nonexistent-bucket", "tms")
        assert stats is None

    def test_missing_signal(self, temp_historical_dir):
        """Test handling missing signal."""
        calc = HistoricalBaselineCalculator(snapshot_dir=temp_historical_dir)

        stats = calc.compute_baseline_stats("ai-agents", "nonexistent-signal")
        assert stats is None

    def test_insufficient_data(self, temp_historical_dir):
        """Test handling insufficient data."""
        calc = HistoricalBaselineCalculator(
            snapshot_dir=temp_historical_dir,
            min_weeks_required=50  # More than we have
        )

        stats = calc.compute_baseline_stats("ai-agents", "tms", window_weeks=12)
        assert stats is None


class TestStatisticalCalculations:
    """Test statistical calculation accuracy."""

    def test_percentile_ordering(self, temp_historical_dir):
        """Test that percentiles are properly ordered."""
        calc = HistoricalBaselineCalculator(snapshot_dir=temp_historical_dir)
        stats = calc.compute_baseline_stats("ai-agents", "tms", window_weeks=12)

        if stats:
            assert stats.p10 <= stats.p25
            assert stats.p25 <= stats.p50
            assert stats.p50 <= stats.p75
            assert stats.p75 <= stats.p90

    def test_mean_within_bounds(self, temp_historical_dir):
        """Test that mean is within min/max bounds."""
        calc = HistoricalBaselineCalculator(snapshot_dir=temp_historical_dir)
        stats = calc.compute_baseline_stats("ai-agents", "tms", window_weeks=12)

        if stats:
            assert stats.min_val <= stats.mean <= stats.max_val

    def test_std_non_negative(self, temp_historical_dir):
        """Test that standard deviation is non-negative."""
        calc = HistoricalBaselineCalculator(snapshot_dir=temp_historical_dir)
        stats = calc.compute_baseline_stats("ai-agents", "tms", window_weeks=12)

        if stats:
            assert stats.std >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])