"""
Tests for signal smoothing module.
"""

import pytest
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.signal_smoothing import (
    SmoothingConfig,
    SignalSmoother,
    BatchSmoother,
    DEFAULT_SMOOTHING_CONFIGS,
)


class TestSmoothingConfig:
    """Tests for SmoothingConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SmoothingConfig(signal_name="test")
        assert config.signal_name == "test"
        assert config.ewma_alpha == 0.3
        assert config.enabled is True
        assert config.winsorize is False
        assert config.winsorize_lower == 5
        assert config.winsorize_upper == 95

    def test_custom_config(self):
        """Test custom configuration."""
        config = SmoothingConfig(
            signal_name="nas",
            ewma_alpha=0.5,
            enabled=True,
            winsorize=True,
        )
        assert config.ewma_alpha == 0.5
        assert config.winsorize is True


class TestSignalSmoother:
    """Tests for SignalSmoother."""

    def test_ewma_first_value(self):
        """Test EWMA with first value (no prior)."""
        config = SmoothingConfig(signal_name="test", ewma_alpha=0.3)
        smoother = SignalSmoother(config)

        result = smoother.smooth_ewma(50.0, prior_ewma=None)
        assert result == 50.0  # First value is returned as-is

    def test_ewma_smoothing(self):
        """Test EWMA smoothing calculation."""
        config = SmoothingConfig(signal_name="test", ewma_alpha=0.3)
        smoother = SignalSmoother(config)

        # EWMA = alpha * new_value + (1 - alpha) * prior
        # = 0.3 * 100 + 0.7 * 50 = 30 + 35 = 65
        result = smoother.smooth_ewma(100.0, prior_ewma=50.0)
        assert result == 65.0

    def test_ewma_series(self):
        """Test EWMA over a series of values."""
        config = SmoothingConfig(signal_name="test", ewma_alpha=0.3)
        smoother = SignalSmoother(config)

        values = [50, 60, 70, 80, 90]
        expected_ewmas = []

        ewma = None
        for v in values:
            if ewma is None:
                ewma = v
            else:
                ewma = 0.3 * v + 0.7 * ewma
            expected_ewmas.append(ewma)

        # Test using smooth method
        result_ewmas = []
        prior = None
        for v in values:
            result = smoother.smooth_ewma(v, prior_ewma=prior)
            result_ewmas.append(result)
            prior = result

        assert result_ewmas == pytest.approx(expected_ewmas)

    def test_winsorize_clip_high(self):
        """Test winsorization clips high outliers."""
        config = SmoothingConfig(
            signal_name="test",
            winsorize=True,
            winsorize_lower=10,
            winsorize_upper=90,
        )
        smoother = SignalSmoother(config)

        # Values above 90th percentile should be clipped
        result = smoother.winsorize([10, 20, 30, 40, 50, 60, 70, 80, 90, 1000])
        assert max(result) <= 90  # Should be clipped

    def test_winsorize_clip_low(self):
        """Test winsorization clips low outliers."""
        config = SmoothingConfig(
            signal_name="test",
            winsorize=True,
            winsorize_lower=10,
            winsorize_upper=90,
        )
        smoother = SignalSmoother(config)

        # Values below 10th percentile should be clipped
        result = smoother.winsorize([0, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        assert min(result) >= 10  # Should be clipped to at least p10

    def test_winsorize_single_value(self):
        """Test winsorization with single value."""
        config = SmoothingConfig(signal_name="test", winsorize=True)
        smoother = SignalSmoother(config)

        result = smoother.winsorize([50])
        assert result == [50]

    def test_disabled_smoothing(self):
        """Test that disabled smoothing returns original value."""
        config = SmoothingConfig(signal_name="test", enabled=False)
        smoother = SignalSmoother(config)

        result = smoother.smooth(100.0, prior_ewma=50.0)
        assert result == 100.0  # No smoothing applied


class TestBatchSmoother:
    """Tests for BatchSmoother."""

    def test_batch_smoothing(self):
        """Test batch smoothing multiple buckets."""
        configs = {
            "nas": SmoothingConfig(signal_name="nas", ewma_alpha=0.3, enabled=True),
            "tms": SmoothingConfig(signal_name="tms", ewma_alpha=0.5, enabled=False),
        }
        batch = BatchSmoother(configs)

        current_values = {
            "bucket1": {"nas": 80.0, "tms": 70.0},
            "bucket2": {"nas": 60.0, "tms": 50.0},
        }

        prior_ewmas = {
            "bucket1": {"nas": 50.0, "tms": 60.0},
            "bucket2": {"nas": 40.0, "tms": 40.0},
        }

        results = batch.smooth_batch(current_values, prior_ewmas)

        # NAS should be smoothed: 0.3 * 80 + 0.7 * 50 = 59
        assert results["bucket1"]["nas"] == pytest.approx(59.0)
        # TMS should not be smoothed (disabled)
        assert results["bucket1"]["tms"] == 70.0

    def test_default_configs_exist(self):
        """Test that default configs are defined for key signals."""
        assert "nas" in DEFAULT_SMOOTHING_CONFIGS
        assert "css" in DEFAULT_SMOOTHING_CONFIGS
        assert "tms" in DEFAULT_SMOOTHING_CONFIGS

        # NAS should have smoothing enabled
        assert DEFAULT_SMOOTHING_CONFIGS["nas"].enabled is True
        # TMS should have smoothing disabled by default
        assert DEFAULT_SMOOTHING_CONFIGS["tms"].enabled is False


class TestEWMAMath:
    """Mathematical property tests for EWMA."""

    def test_ewma_bounds(self):
        """EWMA should always be between min and max of values seen."""
        config = SmoothingConfig(signal_name="test", ewma_alpha=0.3)
        smoother = SignalSmoother(config)

        values = [10, 90, 20, 80, 50]
        ewma = None

        for v in values:
            ewma = smoother.smooth_ewma(v, prior_ewma=ewma)
            # EWMA should always be within range of values seen
            assert 10 <= ewma <= 90

    def test_ewma_alpha_1_equals_current(self):
        """With alpha=1, EWMA equals current value."""
        config = SmoothingConfig(signal_name="test", ewma_alpha=1.0)
        smoother = SignalSmoother(config)

        result = smoother.smooth_ewma(100.0, prior_ewma=50.0)
        assert result == 100.0

    def test_ewma_alpha_0_equals_prior(self):
        """With alpha=0, EWMA equals prior value."""
        config = SmoothingConfig(signal_name="test", ewma_alpha=0.0)
        smoother = SignalSmoother(config)

        result = smoother.smooth_ewma(100.0, prior_ewma=50.0)
        assert result == 50.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])