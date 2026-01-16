"""Tests for signal contract enforcement."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.bucket_models import SignalMetadata, MissingReason, SignalQuality


class TestSignalMetadata:
    """Tests for SignalMetadata contract."""

    def test_complete_signal(self):
        """Complete signal with all fields."""
        meta = SignalMetadata(
            value=75.0,
            confidence=0.85,
            coverage=0.9,
            freshness_hours=24,
            sources=["github", "huggingface"],
        )
        assert meta.value == 75.0
        assert meta.is_valid is True
        assert meta.missing_reason is None
        assert meta.quality == SignalQuality.HIGH

    def test_low_coverage_signal(self):
        """Low coverage signal should be marked as insufficient."""
        meta = SignalMetadata(
            value=25.0,
            confidence=0.3,
            coverage=0.2,
            freshness_hours=48,
        )
        assert meta.is_valid is True
        assert meta.quality == SignalQuality.LOW
        assert meta.coverage < 0.6

    def test_missing_signal(self):
        """Missing signal should have missing_reason."""
        meta = SignalMetadata(
            value=None,
            missing_reason=MissingReason.NO_DATA,
        )
        assert meta.is_valid is False
        assert meta.missing_reason == MissingReason.NO_DATA

    def test_stale_signal(self):
        """Stale signal should be marked."""
        meta = SignalMetadata(
            value=50.0,
            confidence=0.7,
            coverage=0.8,
            freshness_hours=200,
        )
        assert meta.is_stale is True
        assert meta.quality == SignalQuality.MEDIUM

    def test_contributors_tracked(self):
        """Contributors should be stored."""
        meta = SignalMetadata(
            value=80.0,
            confidence=0.9,
            coverage=0.95,
            freshness_hours=12,
            contributors=[
                {"entity": "langchain/langchain", "contribution": 0.3},
                {"entity": "vllm-project/vllm", "contribution": 0.25},
            ],
        )
        assert len(meta.contributors) == 2
        assert meta.contributors[0]["entity"] == "langchain/langchain"


class TestSignalQuality:
    """Tests for signal quality classification."""

    def test_high_quality(self):
        """High quality: confidence >= 0.8 AND coverage >= 0.6."""
        meta = SignalMetadata(value=50.0, confidence=0.85, coverage=0.75)
        assert meta.quality == SignalQuality.HIGH

    def test_medium_quality(self):
        """Medium quality: confidence >= 0.5 OR coverage >= 0.4."""
        meta = SignalMetadata(value=50.0, confidence=0.6, coverage=0.5)
        assert meta.quality == SignalQuality.MEDIUM

    def test_low_quality(self):
        """Low quality: confidence < 0.5 AND coverage < 0.4."""
        meta = SignalMetadata(value=50.0, confidence=0.3, coverage=0.2)
        assert meta.quality == SignalQuality.LOW

    def test_insufficient_coverage(self):
        """Insufficient coverage should flag as unreliable."""
        meta = SignalMetadata(value=15.0, confidence=0.3, coverage=0.15)
        assert meta.is_coverage_insufficient is True
        assert meta.get_display_reason() == "low coverage (15%)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])