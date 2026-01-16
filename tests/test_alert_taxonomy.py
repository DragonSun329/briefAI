"""Tests for alert cause taxonomy."""

import pytest
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.bucket_models import (
    BucketAlert,
    AlertType,
    AlertCause,
    AlertInterpretation,
    AlertSeverity,
)


class TestAlertCause:
    """Tests for alert cause enum."""

    def test_cause_values(self):
        """All cause types exist."""
        assert AlertCause.DIVERGENCE.value == "divergence"
        assert AlertCause.INFLECTION.value == "inflection"
        assert AlertCause.REGIME_SHIFT.value == "regime_shift"
        assert AlertCause.DATA_HEALTH.value == "data_health"


class TestAlertWithCause:
    """Tests for alerts with cause tracking."""

    def test_alert_with_cause(self):
        """Alert stores cause and features used."""
        alert = BucketAlert(
            bucket_id="ai-agents",
            bucket_name="Agent Frameworks",
            week_start=date(2026, 1, 13),
            alert_type=AlertType.ALPHA_ZONE,
            interpretation=AlertInterpretation.OPPORTUNITY,
            cause=AlertCause.DIVERGENCE,
            trigger_rule_id="alpha_zone_v1",
            features_used=["tms_percentile", "ccs_percentile", "tms_coverage"],
            why_now="TMS crossed p90 AND CCS < p30 AND coverage > 0.7",
            trigger_scores={"tms": 92, "ccs": 28},
            threshold_used="TMS >= 90, CCS <= 30",
            divergence_magnitude=64,
            rationale="High technical momentum with low capital conviction",
            first_detected=date(2026, 1, 6),
        )

        assert alert.cause == AlertCause.DIVERGENCE
        assert alert.trigger_rule_id == "alpha_zone_v1"
        assert "tms_percentile" in alert.features_used
        assert "p90" in alert.why_now

    def test_data_health_alert(self):
        """Data health alerts track source failures."""
        alert = BucketAlert(
            bucket_id="ai-agents",
            bucket_name="Agent Frameworks",
            week_start=date(2026, 1, 13),
            alert_type=AlertType.DATA_HEALTH,
            interpretation=AlertInterpretation.SIGNAL,
            cause=AlertCause.DATA_HEALTH,
            trigger_rule_id="coverage_drop",
            features_used=["tms_coverage", "github_api_status"],
            why_now="TMS coverage dropped from 0.9 to 0.3 due to GitHub API failure",
            trigger_scores={"tms_coverage": 0.3, "tms_coverage_prev": 0.9},
            threshold_used="coverage_delta > 0.5",
            divergence_magnitude=0,
            rationale="GitHub API returning 503 errors",
            first_detected=date(2026, 1, 13),
        )

        assert alert.cause == AlertCause.DATA_HEALTH
        assert "coverage dropped" in alert.why_now

    def test_inflection_alert(self):
        """Inflection alerts track velocity changes."""
        alert = BucketAlert(
            bucket_id="ai-coding",
            bucket_name="AI Coding Tools",
            week_start=date(2026, 1, 13),
            alert_type=AlertType.ROTATION,
            interpretation=AlertInterpretation.SIGNAL,
            cause=AlertCause.INFLECTION,
            trigger_rule_id="velocity_flip",
            features_used=["tms_velocity_4w", "tms_acceleration"],
            why_now="TMS 4-week velocity flipped from +12 to -8 (deceleration)",
            trigger_scores={"tms_velocity_4w": -8, "tms_velocity_prev": 12},
            threshold_used="velocity_sign_change AND magnitude > 5",
            divergence_magnitude=20,
            rationale="Technical momentum decelerating after rapid growth",
            first_detected=date(2026, 1, 13),
        )

        assert alert.cause == AlertCause.INFLECTION
        assert "velocity flipped" in alert.why_now


if __name__ == "__main__":
    pytest.main([__file__, "-v"])