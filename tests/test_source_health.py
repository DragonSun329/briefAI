"""
Tests for source health monitoring module.
"""

import pytest
from datetime import datetime, timedelta
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.source_health import (
    SourceHealthConfig,
    SourceStatus,
    SourceHealthRecord,
    SourceHealthMonitor,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def health_monitor(temp_db):
    """Create a SourceHealthMonitor with temporary database."""
    monitor = SourceHealthMonitor(db_path=temp_db)
    yield monitor
    monitor.close()


class TestSourceHealthConfig:
    """Tests for SourceHealthConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SourceHealthConfig()

        assert config.circuit_breaker_threshold == 3
        assert config.circuit_breaker_reset_hours == 1
        assert config.max_retries == 3
        assert config.base_delay_seconds == 1.0
        assert config.max_delay_seconds == 60.0

    def test_custom_config(self):
        """Test custom configuration."""
        config = SourceHealthConfig(
            circuit_breaker_threshold=5,
            max_retries=5,
        )

        assert config.circuit_breaker_threshold == 5
        assert config.max_retries == 5


class TestSourceStatus:
    """Tests for SourceStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert SourceStatus.HEALTHY.value == "healthy"
        assert SourceStatus.DEGRADED.value == "degraded"
        assert SourceStatus.UNHEALTHY.value == "unhealthy"
        assert SourceStatus.CIRCUIT_OPEN.value == "circuit_open"


class TestSourceHealthRecord:
    """Tests for SourceHealthRecord dataclass."""

    def test_create_record(self):
        """Test creating a health record."""
        record = SourceHealthRecord(
            source_name="hackernews",
            status=SourceStatus.HEALTHY,
        )

        assert record.source_name == "hackernews"
        assert record.status == SourceStatus.HEALTHY
        assert record.consecutive_failures == 0
        assert record.total_requests == 0

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        record = SourceHealthRecord(
            source_name="test",
            status=SourceStatus.HEALTHY,
            total_requests=100,
            successful_requests=80,
        )

        assert record.success_rate == 0.8

    def test_success_rate_zero_requests(self):
        """Test success rate with zero requests."""
        record = SourceHealthRecord(
            source_name="test",
            status=SourceStatus.HEALTHY,
            total_requests=0,
        )

        assert record.success_rate == 0.0


class TestSourceHealthMonitor:
    """Tests for SourceHealthMonitor."""

    def test_record_success(self, health_monitor):
        """Test recording a successful request."""
        health_monitor.record_success("hackernews", response_time_ms=150)

        record = health_monitor.get_source_health("hackernews")
        assert record is not None
        assert record.status == SourceStatus.HEALTHY
        assert record.successful_requests == 1
        assert record.total_requests == 1
        assert record.consecutive_failures == 0

    def test_record_failure(self, health_monitor):
        """Test recording a failed request."""
        health_monitor.record_failure("hackernews", error="Timeout")

        record = health_monitor.get_source_health("hackernews")
        assert record is not None
        assert record.failed_requests == 1
        assert record.consecutive_failures == 1
        assert record.last_error == "Timeout"

    def test_consecutive_failures_trigger_unhealthy(self, health_monitor):
        """Test that consecutive failures trigger unhealthy status."""
        for i in range(3):
            health_monitor.record_failure("hackernews", error=f"Error {i}")

        record = health_monitor.get_source_health("hackernews")
        assert record.status in [SourceStatus.UNHEALTHY, SourceStatus.CIRCUIT_OPEN]
        assert record.consecutive_failures == 3

    def test_success_resets_consecutive_failures(self, health_monitor):
        """Test that success resets consecutive failure count."""
        # Record some failures
        health_monitor.record_failure("hackernews", error="Error 1")
        health_monitor.record_failure("hackernews", error="Error 2")

        record = health_monitor.get_source_health("hackernews")
        assert record.consecutive_failures == 2

        # Record success
        health_monitor.record_success("hackernews")

        record = health_monitor.get_source_health("hackernews")
        assert record.consecutive_failures == 0

    def test_circuit_breaker_opens(self, health_monitor):
        """Test that circuit breaker opens after threshold failures."""
        config = health_monitor.config

        # Record failures up to threshold
        for i in range(config.circuit_breaker_threshold):
            health_monitor.record_failure("hackernews", error="Error")

        record = health_monitor.get_source_health("hackernews")
        assert record.status == SourceStatus.CIRCUIT_OPEN
        assert record.circuit_open_until is not None

    def test_is_source_available_healthy(self, health_monitor):
        """Test is_source_available for healthy source."""
        health_monitor.record_success("hackernews")

        assert health_monitor.is_source_available("hackernews") is True

    def test_is_source_available_circuit_open(self, health_monitor):
        """Test is_source_available when circuit is open."""
        # Trigger circuit breaker
        for _ in range(3):
            health_monitor.record_failure("hackernews", error="Error")

        assert health_monitor.is_source_available("hackernews") is False

    def test_is_source_available_unknown(self, health_monitor):
        """Test is_source_available for unknown source."""
        # Unknown sources should be available by default
        assert health_monitor.is_source_available("unknown_source") is True

    def test_get_all_source_health(self, health_monitor):
        """Test getting health for all sources."""
        health_monitor.record_success("hackernews")
        health_monitor.record_success("reddit")
        health_monitor.record_failure("github", error="Rate limit")

        all_health = health_monitor.get_all_source_health()

        assert len(all_health) == 3
        source_names = [r.source_name for r in all_health]
        assert "hackernews" in source_names
        assert "reddit" in source_names
        assert "github" in source_names

    def test_get_healthy_sources(self, health_monitor):
        """Test getting only healthy sources."""
        health_monitor.record_success("hackernews")
        health_monitor.record_success("reddit")

        # Make github unhealthy
        for _ in range(3):
            health_monitor.record_failure("github", error="Error")

        healthy = health_monitor.get_healthy_sources()

        healthy_names = [r.source_name for r in healthy]
        assert "hackernews" in healthy_names
        assert "reddit" in healthy_names
        assert "github" not in healthy_names

    def test_degraded_status(self, health_monitor):
        """Test degraded status based on success rate."""
        # Record mix of successes and failures
        for _ in range(7):
            health_monitor.record_success("hackernews")
        for _ in range(3):
            health_monitor.record_failure("hackernews", error="Error")

        record = health_monitor.get_source_health("hackernews")
        # With 70% success rate, should be degraded
        assert record.status in [SourceStatus.HEALTHY, SourceStatus.DEGRADED]

    def test_average_response_time(self, health_monitor):
        """Test average response time tracking."""
        health_monitor.record_success("hackernews", response_time_ms=100)
        health_monitor.record_success("hackernews", response_time_ms=200)
        health_monitor.record_success("hackernews", response_time_ms=300)

        record = health_monitor.get_source_health("hackernews")
        assert record.avg_response_time_ms == pytest.approx(200, rel=0.1)


class TestCircuitBreaker:
    """Tests for circuit breaker behavior."""

    def test_circuit_resets_after_timeout(self, health_monitor):
        """Test that circuit resets after the timeout period."""
        # Open the circuit
        for _ in range(3):
            health_monitor.record_failure("hackernews", error="Error")

        record = health_monitor.get_source_health("hackernews")
        assert record.status == SourceStatus.CIRCUIT_OPEN

        # Manually set circuit_open_until to past
        health_monitor._update_circuit_open_until(
            "hackernews",
            datetime.now() - timedelta(hours=2)
        )

        # Should now be available
        assert health_monitor.is_source_available("hackernews") is True

    def test_half_open_state(self, health_monitor):
        """Test circuit breaker half-open state behavior."""
        # Open circuit
        for _ in range(3):
            health_monitor.record_failure("hackernews", error="Error")

        # Set circuit to recently expired
        health_monitor._update_circuit_open_until(
            "hackernews",
            datetime.now() - timedelta(minutes=1)
        )

        # Source should be available for testing
        assert health_monitor.is_source_available("hackernews") is True

        # Success should close circuit
        health_monitor.record_success("hackernews")
        record = health_monitor.get_source_health("hackernews")
        assert record.status != SourceStatus.CIRCUIT_OPEN


class TestHealthDashboard:
    """Tests for health dashboard/summary features."""

    def test_get_health_summary(self, health_monitor):
        """Test getting overall health summary."""
        health_monitor.record_success("hackernews")
        health_monitor.record_success("reddit")
        health_monitor.record_success("github")

        # Make one source unhealthy
        for _ in range(3):
            health_monitor.record_failure("arxiv", error="Error")

        summary = health_monitor.get_health_summary()

        assert summary["total_sources"] == 4
        assert summary["healthy_sources"] >= 2
        assert summary["unhealthy_sources"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])