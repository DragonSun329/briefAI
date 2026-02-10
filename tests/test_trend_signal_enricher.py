"""Tests for TrendSignalEnricher - Trend Radar Validation System."""

import json
import pytest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.trend_signal_enricher import (
    TrendSignalEnricher,
    TrendSignal,
    ValidatedTrendSignal,
)
from utils.entity_matcher import EntityMatcher
from utils.signal_validator import SignalValidator


def make_trend_signal(
    entity_name: str = "OpenAI",
    signal_type: str = "velocity_spike",
    momentum: float = 85.0,
) -> TrendSignal:
    """Helper to create TrendSignal objects."""
    return TrendSignal(
        entity_id=entity_name.lower().replace(" ", "_"),
        entity_name=entity_name,
        signal_type=signal_type,
        current_week="2026-W04",
        momentum_score=momentum,
        article_count=10,
        week_over_week_change=50.0,
        context="AI model company",
    )


class TestTrendSignalEnricherInit:
    """Tests for TrendSignalEnricher initialization."""

    def test_default_components(self):
        """Enricher initializes with default components."""
        enricher = TrendSignalEnricher()

        assert enricher.matcher is not None
        assert enricher.validator is not None
        assert enricher.snapshot_builder is not None

    def test_custom_components(self):
        """Enricher accepts custom matcher and validator."""
        matcher = EntityMatcher()
        validator = SignalValidator()

        enricher = TrendSignalEnricher(
            matcher=matcher,
            validator=validator,
        )

        assert enricher.matcher is matcher
        assert enricher.validator is validator


class TestTrendSignalDataclass:
    """Tests for TrendSignal dataclass."""

    def test_trend_signal_fields(self):
        """TrendSignal has expected fields."""
        signal = TrendSignal(
            entity_id="openai",
            entity_name="OpenAI",
            signal_type="velocity_spike",
            current_week="2026-W04",
            momentum_score=85.0,
        )

        assert signal.entity_id == "openai"
        assert signal.entity_name == "OpenAI"
        assert signal.signal_type == "velocity_spike"
        assert signal.momentum_score == 85.0

    def test_trend_signal_defaults(self):
        """TrendSignal has sensible defaults."""
        signal = TrendSignal(
            entity_id="openai",
            entity_name="OpenAI",
            signal_type="velocity_spike",
            current_week="2026-W04",
            momentum_score=85.0,
        )

        assert signal.article_count == 0
        assert signal.week_over_week_change == 0.0
        assert signal.context == ""


class TestValidatedTrendSignalDataclass:
    """Tests for ValidatedTrendSignal dataclass."""

    def test_validated_signal_fields(self):
        """ValidatedTrendSignal has all expected fields."""
        signal = ValidatedTrendSignal(
            entity_id="openai",
            entity_name="OpenAI",
            entity_type="company",
            signal_type="velocity_spike",
            current_week="2026-W04",
            momentum_score=85.0,
            article_count=10,
            week_over_week_change=50.0,
            canonical_key="openai",
            canonical_name="OpenAI",
            resolution_confidence=1.0,
            resolution_path="tier1",
            ambiguity_flags=[],
            validation_score=0.8,
            validation_coverage=1.0,
            validation_strength=0.8,
            validation_status="validated",
            categories_found=["technical"],
            tier_distribution={1: 2, 2: 0, 3: 0},
            corroborating_sources=["github", "huggingface"],
            validation_fail_reasons={},
        )

        assert signal.entity_id == "openai"
        assert signal.canonical_key == "openai"
        assert signal.validation_score == 0.8

    def test_to_dict(self):
        """ValidatedTrendSignal can be serialized to dict."""
        signal = ValidatedTrendSignal(
            entity_id="openai",
            entity_name="OpenAI",
            entity_type="company",
            signal_type="velocity_spike",
            current_week="2026-W04",
            momentum_score=85.0,
            article_count=10,
            week_over_week_change=50.0,
            canonical_key="openai",
            canonical_name="OpenAI",
            resolution_confidence=1.0,
            resolution_path="tier1",
            ambiguity_flags=[],
            validation_score=0.8,
            validation_coverage=1.0,
            validation_strength=0.8,
            validation_status="validated",
            categories_found=["technical"],
            tier_distribution={1: 2, 2: 0, 3: 0},
            corroborating_sources=["github"],
            validation_fail_reasons={},
        )

        d = signal.to_dict()

        assert isinstance(d, dict)
        assert d["entity_id"] == "openai"
        assert d["validation_score"] == 0.8

    def test_is_validated_property(self):
        """is_validated property works correctly."""
        validated_signal = ValidatedTrendSignal(
            entity_id="openai",
            entity_name="OpenAI",
            entity_type="company",
            signal_type="velocity_spike",
            current_week="2026-W04",
            momentum_score=85.0,
            article_count=10,
            week_over_week_change=50.0,
            canonical_key="openai",
            canonical_name="OpenAI",
            resolution_confidence=1.0,
            resolution_path="tier1",
            ambiguity_flags=[],
            validation_score=0.8,
            validation_coverage=1.0,
            validation_strength=0.8,
            validation_status="validated",
            categories_found=["technical"],
            tier_distribution={1: 2, 2: 0, 3: 0},
            corroborating_sources=["github"],
            validation_fail_reasons={},
        )

        unvalidated_signal = ValidatedTrendSignal(
            entity_id="unknown",
            entity_name="Unknown",
            entity_type="unknown",
            signal_type="new_entity",
            current_week="2026-W04",
            momentum_score=50.0,
            article_count=5,
            week_over_week_change=10.0,
            canonical_key=None,
            canonical_name=None,
            resolution_confidence=0.0,
            resolution_path="rejected",
            ambiguity_flags=[],
            validation_score=0.2,
            validation_coverage=0.3,
            validation_strength=0.2,
            validation_status="unvalidated",
            categories_found=[],
            tier_distribution={1: 0, 2: 0, 3: 0},
            corroborating_sources=[],
            validation_fail_reasons={"github": "no_match"},
        )

        assert validated_signal.is_validated is True
        assert unvalidated_signal.is_validated is False


class TestSnapshotLoading:
    """Tests for snapshot loading in enricher."""

    def test_load_snapshot(self):
        """Enricher can load a snapshot."""
        with TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshots"
            snapshot_dir.mkdir(parents=True)

            # Create a test snapshot
            snapshot_date = "2026-01-21"
            snapshot_file = snapshot_dir / f"source_snapshot_{snapshot_date}.json"
            snapshot_data = {
                "snapshot_date": snapshot_date,
                "sources": {
                    "github": {
                        "trending_repos": [
                            {"name": "openai/gpt-4", "stars": 50000},
                        ],
                    },
                },
                "data_health": {
                    "sources_available": ["github"],
                    "sources_missing": [],
                    "sources_stale": [],
                },
            }
            snapshot_file.write_text(json.dumps(snapshot_data))

            enricher = TrendSignalEnricher(snapshot_dir=snapshot_dir)
            loaded = enricher.load_snapshot(snapshot_date)

            assert loaded is True
            assert enricher._snapshot is not None

    def test_build_and_load_snapshot(self):
        """Enricher can build and load a fresh snapshot."""
        with TemporaryDirectory() as tmpdir:
            signals_dir = Path(tmpdir) / "signals"
            snapshot_dir = Path(tmpdir) / "snapshots"
            signals_dir.mkdir(parents=True)

            # Create a signals file
            github_file = signals_dir / "github_2026-01-21.json"
            github_data = {
                "scraped_at": datetime.now().isoformat(),
                "trending_repos": [],
            }
            github_file.write_text(json.dumps(github_data))

            enricher = TrendSignalEnricher(snapshot_dir=snapshot_dir)
            enricher.snapshot_builder.signals_dir = signals_dir

            loaded = enricher.build_and_load_snapshot()

            assert loaded is True
            assert enricher._snapshot is not None


class TestEnrichment:
    """Tests for signal enrichment."""

    def test_enrich_known_entity(self):
        """Enricher resolves known entities."""
        enricher = TrendSignalEnricher()

        signals = [make_trend_signal("OpenAI")]
        enriched = enricher.enrich(signals)

        assert len(enriched) == 1
        assert enriched[0].canonical_key == "openai"
        assert enriched[0].canonical_name == "OpenAI"

    def test_enrich_unknown_entity(self):
        """Enricher handles unknown entities gracefully."""
        enricher = TrendSignalEnricher()

        signals = [make_trend_signal("TotallyUnknownCompany12345")]
        enriched = enricher.enrich(signals)

        assert len(enriched) == 1
        # Unknown entity should have low/no resolution
        assert enriched[0].resolution_confidence < 0.5 or enriched[0].canonical_key is None

    def test_enrich_multiple_signals(self):
        """Enricher processes multiple signals."""
        enricher = TrendSignalEnricher()

        signals = [
            make_trend_signal("OpenAI"),
            make_trend_signal("DeepSeek"),
            make_trend_signal("Anthropic"),
        ]
        enriched = enricher.enrich(signals)

        assert len(enriched) == 3

        # All known entities should be resolved
        canonical_keys = [s.canonical_key for s in enriched]
        assert "openai" in canonical_keys
        assert "deepseek" in canonical_keys
        assert "anthropic" in canonical_keys

    def test_enrich_preserves_original_data(self):
        """Enrichment preserves original signal data."""
        enricher = TrendSignalEnricher()

        signal = make_trend_signal("OpenAI", signal_type="velocity_spike", momentum=85.0)
        enriched = enricher.enrich([signal])

        assert enriched[0].signal_type == "velocity_spike"
        assert enriched[0].momentum_score == 85.0
        assert enriched[0].article_count == 10


class TestValidationIntegration:
    """Tests for validation integration."""

    def test_validation_score_populated(self):
        """Enriched signals have validation scores."""
        enricher = TrendSignalEnricher()

        signals = [make_trend_signal("OpenAI")]
        enriched = enricher.enrich(signals)

        # Should have validation fields populated
        assert hasattr(enriched[0], "validation_score")
        assert hasattr(enriched[0], "validation_coverage")
        assert hasattr(enriched[0], "validation_status")

    def test_validation_status_set(self):
        """Validation status is set correctly."""
        enricher = TrendSignalEnricher()

        signals = [make_trend_signal("OpenAI")]
        enriched = enricher.enrich(signals)

        # Should have a valid status
        assert enriched[0].validation_status in (
            "high_confidence",
            "validated",
            "insufficient_data",
            "unvalidated",
        )

    def test_categories_found_populated(self):
        """Categories found are populated from validation."""
        enricher = TrendSignalEnricher()

        signals = [make_trend_signal("OpenAI")]
        enriched = enricher.enrich(signals)

        # categories_found should be a list
        assert isinstance(enriched[0].categories_found, list)


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_signal_list(self):
        """Enricher handles empty signal list."""
        enricher = TrendSignalEnricher()

        enriched = enricher.enrich([])

        assert len(enriched) == 0

    def test_signal_with_empty_name(self):
        """Enricher handles signals with empty names."""
        enricher = TrendSignalEnricher()

        signal = TrendSignal(
            entity_id="",
            entity_name="",
            signal_type="velocity_spike",
            current_week="2026-W04",
            momentum_score=50.0,
        )
        enriched = enricher.enrich([signal])

        assert len(enriched) == 1
        # Should not crash, just have no resolution
        assert enriched[0].canonical_key is None or enriched[0].resolution_confidence == 0.0

    def test_signal_with_special_characters(self):
        """Enricher handles names with special characters without crashing."""
        enricher = TrendSignalEnricher()

        signal = make_trend_signal("OpenAI's GPT-4 (2024)")
        enriched = enricher.enrich([signal])

        assert len(enriched) == 1
        # Should handle without crashing (may or may not resolve)
        assert enriched[0] is not None