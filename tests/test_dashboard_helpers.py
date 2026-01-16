"""Tests for dashboard UI helpers."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.dashboard_helpers import (
    get_confidence_style,
    generate_sparkline_data,
    format_persistence_text,
    get_severity_config,
)


class TestConfidenceStyle:
    """Tests for confidence visual encoding."""

    def test_high_confidence(self):
        """High confidence (>0.8) returns solid style."""
        style = get_confidence_style(0.85)
        assert style["opacity"] == 1.0
        assert style["border_style"] == "solid"
        assert style["badge"] is None

    def test_medium_confidence(self):
        """Medium confidence (0.5-0.8) returns reduced opacity."""
        style = get_confidence_style(0.65)
        assert style["opacity"] == 0.7
        assert style["border_style"] == "solid"

    def test_low_confidence(self):
        """Low confidence (<0.5) returns dashed style."""
        style = get_confidence_style(0.35)
        assert style["opacity"] == 0.5
        assert style["border_style"] == "dashed"

    def test_missing_data(self):
        """Missing data (None) returns gray with badge."""
        style = get_confidence_style(None)
        assert style["color"] == "#9e9e9e"
        assert style["badge"] == "?"


class TestSparklineData:
    """Tests for sparkline generation."""

    def test_generate_sparkline_8_weeks(self):
        """Generate 8-week sparkline data."""
        history = [50, 55, 60, 65, 70, 72, 75, 78]
        result = generate_sparkline_data(history)
        assert len(result["values"]) == 8
        assert result["trend"] == "rising"
        assert result["delta"] == 28  # 78 - 50

    def test_empty_history(self):
        """Handle empty history gracefully."""
        result = generate_sparkline_data([])
        assert result["values"] == []
        assert result["trend"] == "stable"


class TestPersistenceText:
    """Tests for persistence duration formatting."""

    def test_one_week(self):
        """One week persistence."""
        assert format_persistence_text(1) == "1 week"

    def test_multiple_weeks(self):
        """Multiple weeks persistence."""
        assert format_persistence_text(3) == "3 weeks"

    def test_zero_weeks(self):
        """Zero weeks (new alert)."""
        assert format_persistence_text(0) == "New"


class TestSeverityConfig:
    """Tests for severity configuration."""

    def test_info_severity(self):
        """INFO severity config."""
        config = get_severity_config("INFO")
        assert config["icon"] == "info"
        assert config["cooldown_days"] == 3

    def test_warn_severity(self):
        """WARN severity config."""
        config = get_severity_config("WARN")
        assert config["icon"] == "warning"
        assert config["cooldown_days"] == 7

    def test_crit_severity(self):
        """CRIT severity config."""
        config = get_severity_config("CRIT")
        assert config["icon"] == "error"
        assert config["cooldown_days"] == 14


class TestSparklineChart:
    """Tests for Plotly sparkline generation."""

    def test_create_sparkline_figure(self):
        """Create a Plotly sparkline figure."""
        from utils.dashboard_helpers import create_sparkline_figure

        history = [50, 55, 60, 65, 70, 72, 75, 78]
        fig = create_sparkline_figure(history, "TMS")

        assert fig is not None
        assert len(fig.data) == 1  # One trace

    def test_sparkline_with_coverage(self):
        """Sparkline with coverage percentage."""
        from utils.dashboard_helpers import create_sparkline_figure

        history = [50, 55, 60, 65, 70, 72, 75, 78]
        fig = create_sparkline_figure(history, "TMS", coverage=0.92)

        # Should have coverage annotation
        assert fig is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])