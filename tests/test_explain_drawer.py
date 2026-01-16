"""Tests for explain drawer component."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.components.explain_drawer import (
    SparklineData,
    ExplainDrawerData,
    build_explain_drawer_data,
    ExplainDrawerRenderer,
    SIGNAL_DISPLAY_NAMES,
)


class TestExplainDrawerData:
    """Tests for explain drawer data building."""

    def test_build_drawer_data(self):
        """Build drawer data from bucket profile."""
        profile = {
            "bucket_id": "ai-agents",
            "bucket_name": "Agent Frameworks",
            "tms": 85,
            "ccs": 42,
            "nas": 72,
            "eis_offensive": 61,
            "signal_confidence": 0.85,
            "top_technical_entities": ["langchain/langchain", "vllm-project/vllm"],
            "top_capital_entities": ["Pinecone"],
            "entity_count": 15,
        }

        signal_history = {
            "tms": [75, 78, 80, 82, 83, 84, 85, 85],
            "ccs": [35, 36, 38, 39, 40, 41, 42, 42],
        }

        drawer_data = build_explain_drawer_data(profile, signal_history)

        assert drawer_data.bucket_name == "Agent Frameworks"
        assert len(drawer_data.sparklines) >= 2
        assert drawer_data.data_quality_pct > 0

    def test_all_six_signals_processed(self):
        """Test that all 6 signals are processed when present."""
        profile = {
            "bucket_id": "test",
            "bucket_name": "Test Bucket",
            "tms": 80,
            "ccs": 70,
            "nas": 60,
            "eis": 50,
            "pms": 40,
            "css": 30,
        }
        signal_history = {}

        drawer_data = build_explain_drawer_data(profile, signal_history)

        assert drawer_data.signals_available == 6
        assert drawer_data.data_quality_pct == 1.0
        assert len(drawer_data.sparklines) == 6

    def test_partial_signals_correct_quality(self):
        """Test data quality calculation with partial signals."""
        profile = {
            "bucket_id": "test",
            "bucket_name": "Test",
            "tms": 80,
            "ccs": 70,
            "nas": 60,
        }
        signal_history = {}

        drawer_data = build_explain_drawer_data(profile, signal_history)

        assert drawer_data.signals_available == 3
        assert drawer_data.data_quality_pct == 0.5

    def test_missing_signals_handled(self):
        """Test handling of missing signals."""
        profile = {
            "bucket_id": "test",
            "bucket_name": "Test",
        }
        signal_history = {}

        drawer_data = build_explain_drawer_data(profile, signal_history)

        assert drawer_data.signals_available == 0
        assert drawer_data.data_quality_pct == 0.0
        assert len(drawer_data.sparklines) == 0

    def test_alert_info_extraction(self):
        """Test alert info is properly extracted."""
        profile = {
            "bucket_id": "test",
            "bucket_name": "Test",
            "tms": 85,
        }
        alert_info = {
            "alert_type": "alpha_zone",
            "rationale": "High TMS with low CCS indicates hidden gem",
        }

        drawer_data = build_explain_drawer_data(profile, {}, alert_info)

        assert drawer_data.active_alert_type == "alpha_zone"
        assert drawer_data.alert_rationale == "High TMS with low CCS indicates hidden gem"

    def test_entity_string_normalization(self):
        """Test that string entities are normalized to dicts."""
        profile = {
            "bucket_id": "test",
            "bucket_name": "Test",
            "top_technical_entities": ["repo1", "repo2"],
            "top_capital_entities": ["company1"],
        }

        drawer_data = build_explain_drawer_data(profile, {})

        assert len(drawer_data.top_repos) == 2
        assert drawer_data.top_repos[0] == {"name": "repo1", "stars_delta": 0}
        assert len(drawer_data.top_companies) == 1
        assert drawer_data.top_companies[0] == {"name": "company1"}

    def test_entity_dict_passthrough(self):
        """Test that dict entities are passed through unchanged."""
        profile = {
            "bucket_id": "test",
            "bucket_name": "Test",
            "top_technical_entities": [{"name": "repo1", "stars_delta": 100}],
            "top_capital_entities": [{"name": "company1", "funding": "$10M"}],
        }

        drawer_data = build_explain_drawer_data(profile, {})

        assert drawer_data.top_repos[0]["stars_delta"] == 100
        assert drawer_data.top_companies[0]["funding"] == "$10M"

    def test_sparkline_data_populated(self):
        """Test sparkline data is populated correctly."""
        profile = {
            "bucket_id": "test",
            "bucket_name": "Test",
            "tms": 85,
        }
        signal_history = {
            "tms": [70, 72, 75, 78, 80, 82, 84, 85],
        }

        drawer_data = build_explain_drawer_data(profile, signal_history)

        assert len(drawer_data.sparklines) == 1
        spark = drawer_data.sparklines[0]
        assert spark.signal_name == "tms"
        assert spark.display_name == "TMS (Technical)"
        assert spark.current_value == 85
        assert spark.history == [70, 72, 75, 78, 80, 82, 84, 85]
        assert len(spark.sparkline_chars) > 0
        assert spark.trend in ["rising", "falling", "stable"]

    def test_zero_signal_values_processed(self):
        """Test that zero signal values are processed correctly."""
        profile = {
            "bucket_id": "test",
            "bucket_name": "Test",
            "tms": 0,
            "ccs": 50,
        }
        drawer_data = build_explain_drawer_data(profile, {})

        assert drawer_data.signals_available == 2
        tms_spark = next((s for s in drawer_data.sparklines if s.signal_name == "tms"), None)
        assert tms_spark is not None
        assert tms_spark.current_value == 0


class TestExplainDrawerRenderer:
    """Tests for the renderer class."""

    def test_renderer_instantiation(self):
        """Test renderer can be instantiated."""
        renderer = ExplainDrawerRenderer()
        assert renderer is not None

    def test_renderer_has_render_method(self):
        """Test renderer has render method with correct signature."""
        renderer = ExplainDrawerRenderer()
        assert hasattr(renderer, "render")
        assert callable(renderer.render)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])