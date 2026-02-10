"""
Tests for alert store module.
"""

import pytest
from datetime import datetime, date, timedelta
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.alert_store import (
    AlertStore,
    StoredAlert,
    AlertSeverity,
    DEFAULT_COOLDOWNS,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def alert_store(temp_db):
    """Create an AlertStore with temporary database."""
    store = AlertStore(db_path=temp_db)
    yield store
    store.close()


def create_test_alert(**kwargs):
    """Helper to create a test alert with required fields."""
    defaults = {
        "alert_id": f"test-alert-{datetime.now().timestamp()}",
        "bucket_id": "ai-agents",
        "bucket_name": "AI Agents",
        "alert_type": "alpha_zone",
        "severity": AlertSeverity.WARN.value,
        "interpretation": "High TMS, low CCS",
        "first_detected": date.today().isoformat(),
        "last_updated": datetime.now().isoformat(),
    }
    defaults.update(kwargs)
    return StoredAlert(**defaults)


class TestStoredAlert:
    """Tests for StoredAlert dataclass."""

    def test_create_alert(self):
        """Test creating a basic alert."""
        alert = create_test_alert()

        assert alert.bucket_id == "ai-agents"
        assert alert.alert_type == "alpha_zone"
        assert alert.severity == AlertSeverity.WARN.value
        assert alert.alert_id is not None
        assert alert.first_detected == date.today().isoformat()

    def test_is_expired_false(self):
        """Test alert is not expired when no expiration set."""
        alert = create_test_alert(interpretation="Test")
        assert alert.is_active() is True

    def test_is_expired_true(self):
        """Test alert is expired when expired_at is set."""
        alert = create_test_alert(
            interpretation="Test",
            expired_at=date.today().isoformat(),
        )
        assert alert.is_active() is False

    def test_cooldown_active(self):
        """Test cooldown is active when cooldown_expires is in future."""
        future = (datetime.now() + timedelta(days=5)).isoformat()
        alert = create_test_alert(
            interpretation="Test",
            cooldown_expires=future,
        )
        assert alert.is_in_cooldown() is True

    def test_cooldown_not_active(self):
        """Test cooldown is not active when cooldown_expires is in past."""
        past = (datetime.now() - timedelta(days=1)).isoformat()
        alert = create_test_alert(
            interpretation="Test",
            cooldown_expires=past,
        )
        assert alert.is_in_cooldown() is False


class TestAlertStore:
    """Tests for AlertStore."""

    def test_save_and_get_alert(self, alert_store):
        """Test saving and retrieving an alert."""
        alert = create_test_alert(
            interpretation="High technical momentum",
            trigger_scores={"tms": 92, "ccs": 25},
        )

        alert_id = alert_store.save_alert(alert)
        assert alert_id is not None

        retrieved = alert_store.get_alert(alert_id)
        assert retrieved is not None
        assert retrieved.bucket_id == "ai-agents"
        assert retrieved.alert_type == "alpha_zone"
        assert retrieved.severity == AlertSeverity.WARN.value

    def test_get_active_alerts(self, alert_store):
        """Test getting active (non-expired) alerts."""
        # Save an active alert
        active = create_test_alert(interpretation="Active alert")
        alert_store.save_alert(active)

        # Save and then expire an alert
        expired = create_test_alert(
            bucket_id="ai-coding",
            bucket_name="AI Coding",
            alert_type="hype_zone",
            severity=AlertSeverity.INFO.value,
            interpretation="Expired alert",
        )
        expired_id = alert_store.save_alert(expired)
        alert_store.expire_alert(expired_id, reason="Test expiration")

        # Get active alerts (filter to only non-expired)
        alerts = alert_store.get_active_alerts()
        active_alerts = [a for a in alerts if a.is_active()]
        assert len(active_alerts) == 1
        assert active_alerts[0].bucket_id == "ai-agents"

    def test_get_alerts_by_bucket(self, alert_store):
        """Test filtering alerts by bucket."""
        alert1 = create_test_alert(interpretation="Alert 1")
        alert2 = create_test_alert(
            bucket_id="ai-coding",
            bucket_name="AI Coding",
            alert_type="hype_zone",
            severity=AlertSeverity.INFO.value,
            interpretation="Alert 2",
        )

        alert_store.save_alert(alert1)
        alert_store.save_alert(alert2)

        alerts = alert_store.get_active_alerts(bucket_id="ai-agents")
        assert len(alerts) == 1
        assert alerts[0].alert_type == "alpha_zone"

    def test_check_cooldown_no_prior(self, alert_store):
        """Test cooldown check when no prior alert exists."""
        result = alert_store.check_cooldown("new-bucket", "alpha_zone")
        assert result is False  # No cooldown for new alerts

    def test_check_cooldown_active(self, alert_store):
        """Test cooldown check when cooldown is active."""
        alert = create_test_alert(interpretation="Test")
        alert_id = alert_store.save_alert(alert)
        
        # Mark as shown to start cooldown
        alert_store.mark_shown(alert_id, cooldown_days=7)

        result = alert_store.check_cooldown("ai-agents", "alpha_zone")
        assert result is True

    def test_mark_shown(self, alert_store):
        """Test marking an alert as shown."""
        alert = create_test_alert(interpretation="Test")
        alert_id = alert_store.save_alert(alert)

        alert_store.mark_shown(alert_id)

        retrieved = alert_store.get_alert(alert_id)
        assert retrieved.last_shown is not None

    def test_expire_alert(self, alert_store):
        """Test expiring an alert."""
        alert = create_test_alert(interpretation="Test")
        alert_id = alert_store.save_alert(alert)

        alert_store.expire_alert(alert_id, reason="Conditions no longer met")

        retrieved = alert_store.get_alert(alert_id)
        assert retrieved.is_active() is False
        assert retrieved.expired_reason == "Conditions no longer met"

    def test_update_existing_alert(self, alert_store):
        """Test updating an existing alert increments persistence."""
        # Create initial alert
        alert1 = create_test_alert(
            interpretation="Week 1",
            weeks_persistent=1,
        )
        alert_store.save_alert(alert1)

        # Create updated alert (same bucket + type)
        alert2 = create_test_alert(
            interpretation="Week 2",
            weeks_persistent=2,
        )
        alert_store.save_alert(alert2)

        # Should only have one alert
        alerts = alert_store.get_active_alerts(bucket_id="ai-agents")
        assert len(alerts) == 1
        assert alerts[0].weeks_persistent == 2

    def test_severity_escalation_overrides_cooldown(self, alert_store):
        """Test that severity escalation can override cooldown."""
        # Create WARN alert with active cooldown
        future = (datetime.now() + timedelta(days=5)).isoformat()
        alert = create_test_alert(
            interpretation="Warning level",
            cooldown_expires=future,
        )
        alert_store.save_alert(alert)

        # Escalate to CRIT
        escalated = create_test_alert(
            severity=AlertSeverity.CRIT.value,
            interpretation="Critical level",
        )
        alert_store.save_alert(escalated)

        # Should now show the escalated alert
        alerts = alert_store.get_active_alerts(bucket_id="ai-agents")
        assert len(alerts) == 1
        assert alerts[0].severity == AlertSeverity.CRIT.value


class TestDefaultCooldowns:
    """Tests for default cooldown values."""

    def test_info_cooldown(self):
        """Test INFO severity has 3-day cooldown."""
        assert DEFAULT_COOLDOWNS[AlertSeverity.INFO] == 3

    def test_warn_cooldown(self):
        """Test WARN severity has 7-day cooldown."""
        assert DEFAULT_COOLDOWNS[AlertSeverity.WARN] == 7

    def test_crit_cooldown(self):
        """Test CRIT severity has 14-day cooldown."""
        assert DEFAULT_COOLDOWNS[AlertSeverity.CRIT] == 14


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
