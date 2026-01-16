"""Tests for coverage-aware UI helpers."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.dashboard_helpers import get_signal_display_info, CoverageWarning


class TestSignalDisplayInfo:
    """Tests for signal display with coverage context."""

    def test_high_coverage_signal(self):
        """High coverage signal displays normally."""
        info = get_signal_display_info(
            value=85,
            confidence=0.9,
            coverage=0.8,
        )
        assert info.display_value == "85"
        assert info.warning is None
        assert info.is_reliable is True

    def test_low_coverage_low_value(self):
        """Low coverage with low value shows warning."""
        info = get_signal_display_info(
            value=25,
            confidence=0.3,
            coverage=0.2,
        )
        assert info.display_value == "25"
        assert info.warning == CoverageWarning.INSUFFICIENT_COVERAGE
        assert info.warning_text == "Low due to insufficient data (20% coverage)"
        assert info.is_reliable is False

    def test_missing_signal(self):
        """Missing signal shows N/A with reason."""
        info = get_signal_display_info(
            value=None,
            confidence=0.0,
            coverage=0.0,
            missing_reason="scraper_failure",
        )
        assert info.display_value == "N/A"
        assert info.warning == CoverageWarning.SCRAPER_FAILURE
        assert "data source error" in info.warning_text.lower()


class TestCoverageBadge:
    """Tests for coverage badge display."""

    def test_full_coverage_badge(self):
        """Full coverage gets green badge."""
        from utils.dashboard_helpers import get_coverage_badge
        badge = get_coverage_badge(0.9)
        assert badge["label"] == "GOOD"
        assert badge["color"] == "#27ae60"

    def test_low_coverage_badge(self):
        """Low coverage gets red badge with warning."""
        from utils.dashboard_helpers import get_coverage_badge
        badge = get_coverage_badge(0.2)
        assert badge["label"] == "LOW"
        assert badge["color"] == "#e74c3c"
        assert badge["show_warning"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])