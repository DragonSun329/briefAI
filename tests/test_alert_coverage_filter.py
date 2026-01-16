"""Tests for alert coverage filtering."""

import pytest
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.bucket_models import BucketProfile, SignalMetadata, AlertType


class TestAlertCoverageFiltering:
    """Tests for filtering alerts by coverage."""

    def test_low_coverage_low_value_not_alert(self):
        """Low value with low coverage should NOT trigger alpha_zone alert."""
        profile = BucketProfile(
            bucket_id="test-bucket",
            bucket_name="Test Bucket",
            week_start=date(2026, 1, 13),
            tms=92,  # High TMS
            ccs=15,  # Low CCS - but...
            signal_metadata={
                "tms": SignalMetadata(
                    value=92,
                    confidence=0.9,
                    coverage=0.8,  # Good coverage
                ).model_dump(),
                "ccs": SignalMetadata(
                    value=15,
                    confidence=0.2,
                    coverage=0.15,  # LOW coverage - not reliable!
                ).model_dump(),
            },
        )

        from utils.bucket_alerts import should_trigger_alert, COVERAGE_THRESHOLD

        should_alert, reason = should_trigger_alert(
            profile,
            AlertType.ALPHA_ZONE,
            coverage_threshold=COVERAGE_THRESHOLD,
        )

        assert should_alert is False
        assert "insufficient coverage" in reason.lower()

    def test_good_coverage_triggers_alert(self):
        """Proper coverage should allow alert to trigger."""
        profile = BucketProfile(
            bucket_id="test-bucket",
            bucket_name="Test Bucket",
            week_start=date(2026, 1, 13),
            tms=92,
            ccs=25,
            signal_metadata={
                "tms": SignalMetadata(value=92, confidence=0.9, coverage=0.85).model_dump(),
                "ccs": SignalMetadata(value=25, confidence=0.7, coverage=0.7).model_dump(),
            },
        )

        from utils.bucket_alerts import should_trigger_alert

        should_alert, reason = should_trigger_alert(profile, AlertType.ALPHA_ZONE)

        assert should_alert is True
        assert "alpha zone" in reason.lower()

    def test_data_health_alert_on_coverage_drop(self):
        """Coverage drop should trigger DATA_HEALTH alert."""
        profile = BucketProfile(
            bucket_id="test-bucket",
            bucket_name="Test Bucket",
            week_start=date(2026, 1, 13),
            tms=None,  # Missing
            ccs=50,
            signal_metadata={
                "tms": SignalMetadata(
                    value=None,
                    coverage=0.1,
                    missing_reason="scraper_failure",
                ).model_dump(),
            },
        )

        from utils.bucket_alerts import check_data_health_alert

        alert = check_data_health_alert(profile, previous_coverage={"tms": 0.9})

        assert alert is not None
        assert alert.alert_type == AlertType.DATA_HEALTH
        assert "coverage" in alert.why_now.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])