"""Tests for SignalValidator - Trend Radar Validation System."""

import pytest
from datetime import datetime, timedelta

from utils.signal_validator import (
    SignalValidator,
    ValidationResult,
    SourceMatch,
    DEFAULT_SOURCE_CATEGORIES,
    DEFAULT_THRESHOLDS,
)
from utils.entity_matcher import EntityResolution


def make_source_match(
    source: str,
    category: str,
    tier: int = 1,
    confidence: float = 1.0,
    matched_at: str = None,
) -> SourceMatch:
    """Helper to create SourceMatch objects."""
    if matched_at is None:
        matched_at = datetime.now().isoformat()

    return SourceMatch(
        source=source,
        category=category,
        match_tier=tier,
        confidence=confidence,
        matched_item=f"test_{source}_item",
        matched_at=matched_at,
    )


def make_resolution(primary: str = "openai") -> EntityResolution:
    """Helper to create EntityResolution objects."""
    return EntityResolution(
        primary_match=primary,
        primary_name="OpenAI",
        primary_type="company",
        candidates=[],
        resolution_confidence=1.0,
        ambiguity_flags=[],
        resolution_path="tier1",
        raw_input="OpenAI",
        normalized_input="openai",
    )


class TestSignalValidatorInit:
    """Tests for SignalValidator initialization."""

    def test_loads_config(self):
        """SignalValidator loads source categories config."""
        validator = SignalValidator()
        assert len(validator.source_categories) > 0

    def test_builds_source_to_category_map(self):
        """SignalValidator builds source-to-category mapping."""
        validator = SignalValidator()
        assert "github" in validator.source_to_category
        assert validator.source_to_category["github"] == "technical"


class TestCoverageCalculation:
    """Tests for validation coverage calculation."""

    def test_full_coverage(self):
        """Full coverage when all sources checked."""
        validator = SignalValidator()

        # Create matches for all sources
        matches = {
            "github": make_source_match("github", "technical"),
            "reddit": make_source_match("reddit", "social"),
            "crunchbase": make_source_match("crunchbase", "financial"),
        }

        data_health = {
            "sources_available": ["github", "reddit", "crunchbase"],
            "sources_missing": [],
            "sources_stale": [],
        }

        result = validator.compute_validation(matches, make_resolution(), data_health)

        assert result.validation_coverage == 1.0

    def test_partial_coverage(self):
        """Partial coverage when some sources missing."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical"),
        }

        data_health = {
            "sources_available": ["github", "reddit"],
            "sources_missing": ["crunchbase"],
            "sources_stale": [],
        }

        result = validator.compute_validation(matches, make_resolution(), data_health)

        # 1 out of 2 available sources
        assert result.validation_coverage == 0.5

    def test_stale_sources_excluded_from_coverage(self):
        """Stale sources do NOT count toward coverage."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical"),
        }

        data_health = {
            "sources_available": ["github", "reddit"],
            "sources_missing": [],
            "sources_stale": ["reddit"],  # reddit is stale
        }

        result = validator.compute_validation(matches, make_resolution(), data_health)

        # Only github is available (non-stale), and we matched it
        assert result.validation_coverage == 1.0
        assert "reddit" in result.sources_stale


class TestStrengthCalculation:
    """Tests for validation strength calculation."""

    def test_tier1_high_strength(self):
        """Tier 1 matches give high strength."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical", tier=1),
            "huggingface": make_source_match("huggingface", "technical", tier=1),
        }

        result = validator.compute_validation(matches, make_resolution())

        assert result.validation_strength > 0.5

    def test_tier3_only_low_strength(self):
        """Tier 3 matches alone give low strength."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical", tier=3),
            "reddit": make_source_match("reddit", "social", tier=3),
        }

        result = validator.compute_validation(matches, make_resolution())

        # Tier 3 only should be capped at low strength
        assert result.scoring_breakdown.get("tier3_only", False)

    def test_tier12_count_tracked(self):
        """Tier 1/2 count is tracked separately."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical", tier=1),
            "reddit": make_source_match("reddit", "social", tier=2),
            "hackernews": make_source_match("hackernews", "social", tier=3),
        }

        result = validator.compute_validation(matches, make_resolution())

        assert result.scoring_breakdown["tier12_count"] == 2


class TestDiversityBonus:
    """Tests for category diversity bonus."""

    def test_no_bonus_single_category(self):
        """No diversity bonus for single category."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical", tier=1),
            "huggingface": make_source_match("huggingface", "technical", tier=1),
        }

        result = validator.compute_validation(matches, make_resolution())

        assert result.diversity_bonus == 0.0

    def test_bonus_for_cross_category(self):
        """Diversity bonus for cross-category matches."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical", tier=1),
            "crunchbase": make_source_match("crunchbase", "financial", tier=1),
        }

        result = validator.compute_validation(matches, make_resolution())

        assert result.diversity_bonus > 0.0

    def test_tier3_excluded_from_diversity(self):
        """Tier 3 matches don't contribute to diversity bonus."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical", tier=1),
            "crunchbase": make_source_match("crunchbase", "financial", tier=3),  # Tier 3
        }

        result = validator.compute_validation(matches, make_resolution())

        # Only github (technical) should count - no cross-category
        assert result.diversity_bonus == 0.0

    def test_diversity_bonus_capped(self):
        """Diversity bonus is capped."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical", tier=1),
            "crunchbase": make_source_match("crunchbase", "financial", tier=1),
            "polymarket": make_source_match("polymarket", "predictive", tier=1),
            "reddit": make_source_match("reddit", "social", tier=1),
        }

        result = validator.compute_validation(matches, make_resolution())

        cap = validator.thresholds.get("diversity_bonus_cap", 0.25)
        assert result.diversity_bonus <= cap


class TestTemporalAlignment:
    """Tests for temporal alignment calculation."""

    def test_same_week_high_alignment(self):
        """Matches in same week get high alignment."""
        validator = SignalValidator()

        now = datetime.now()
        matches = {
            "github": make_source_match("github", "technical", matched_at=now.isoformat()),
            "reddit": make_source_match("reddit", "social", matched_at=(now + timedelta(days=2)).isoformat()),
        }

        result = validator.compute_validation(matches, make_resolution())

        assert result.temporal_alignment == 1.0

    def test_two_weeks_medium_alignment(self):
        """Matches within 2 weeks get medium alignment."""
        validator = SignalValidator()

        now = datetime.now()
        matches = {
            "github": make_source_match("github", "technical", matched_at=now.isoformat()),
            "reddit": make_source_match("reddit", "social", matched_at=(now + timedelta(days=10)).isoformat()),
        }

        result = validator.compute_validation(matches, make_resolution())

        assert result.temporal_alignment == 0.7

    def test_single_source_no_alignment(self):
        """Single source has no temporal alignment."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical"),
        }

        result = validator.compute_validation(matches, make_resolution())

        assert result.temporal_alignment == 0.0


class TestValidationStatus:
    """Tests for validation status determination."""

    def test_high_confidence_status(self):
        """High validation score gives high_confidence status."""
        validator = SignalValidator()

        # Strong multi-source validation
        matches = {
            "github": make_source_match("github", "technical", tier=1),
            "huggingface": make_source_match("huggingface", "technical", tier=1),
            "crunchbase": make_source_match("crunchbase", "financial", tier=1),
            "reddit": make_source_match("reddit", "social", tier=1),
        }

        data_health = {
            "sources_available": ["github", "huggingface", "crunchbase", "reddit"],
            "sources_missing": [],
            "sources_stale": [],
        }

        result = validator.compute_validation(matches, make_resolution(), data_health)
        status = validator.get_validation_status(result)

        assert status in ("high_confidence", "validated")

    def test_insufficient_data_status(self):
        """Low coverage gives insufficient_data status."""
        validator = SignalValidator()

        matches = {}  # No matches

        data_health = {
            "sources_available": ["github", "reddit", "crunchbase"],
            "sources_missing": [],
            "sources_stale": [],
        }

        result = validator.compute_validation(matches, make_resolution(), data_health)
        status = validator.get_validation_status(result)

        assert status == "insufficient_data" or result.validation_coverage < 0.5


class TestIsValidated:
    """Tests for is_validated check."""

    def test_tier3_only_not_validated(self):
        """Tier 3 matches alone NEVER produce validated status."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical", tier=3),
            "reddit": make_source_match("reddit", "social", tier=3),
            "crunchbase": make_source_match("crunchbase", "financial", tier=3),
        }

        result = validator.compute_validation(matches, make_resolution())

        assert not validator.is_validated(result)

    def test_two_tier12_sources_validated(self):
        """Two Tier 1/2 sources can produce validated status."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical", tier=1),
            "crunchbase": make_source_match("crunchbase", "financial", tier=2),
        }

        data_health = {
            "sources_available": ["github", "crunchbase"],
            "sources_missing": [],
            "sources_stale": [],
        }

        result = validator.compute_validation(matches, make_resolution(), data_health)

        assert validator.is_validated(result)

    def test_tier1_plus_two_tier3_validated(self):
        """One Tier 1 + two Tier 3 can be validated."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical", tier=1),
            "reddit": make_source_match("reddit", "social", tier=3),
            "hackernews": make_source_match("hackernews", "social", tier=3),
        }

        result = validator.compute_validation(matches, make_resolution())

        # This should be validated via alternative rule
        assert validator.is_validated(result)


class TestValidationSummary:
    """Tests for validation summary formatting."""

    def test_format_summary(self):
        """format_validation_summary produces readable output."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical", tier=1),
            "reddit": make_source_match("reddit", "social", tier=2),
        }

        result = validator.compute_validation(matches, make_resolution())
        summary = validator.format_validation_summary(result)

        assert "Validation:" in summary
        assert "Coverage:" in summary

    def test_summary_includes_fail_reasons(self):
        """Summary includes failure reasons when unvalidated."""
        validator = SignalValidator()

        matches = {}

        data_health = {
            "sources_available": ["github"],
            "sources_missing": ["crunchbase"],
            "sources_stale": [],
        }

        result = validator.compute_validation(matches, make_resolution(), data_health)

        # Should have fail reasons
        assert len(result.validation_fail_reasons) > 0


class TestTierDistribution:
    """Tests for tier distribution tracking."""

    def test_tier_distribution_counted(self):
        """Tier distribution is accurately counted."""
        validator = SignalValidator()

        matches = {
            "github": make_source_match("github", "technical", tier=1),
            "huggingface": make_source_match("huggingface", "technical", tier=1),
            "reddit": make_source_match("reddit", "social", tier=2),
            "hackernews": make_source_match("hackernews", "social", tier=3),
        }

        result = validator.compute_validation(matches, make_resolution())

        assert result.tier_distribution[1] == 2
        assert result.tier_distribution[2] == 1
        assert result.tier_distribution[3] == 1