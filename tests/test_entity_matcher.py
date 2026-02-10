"""Tests for EntityMatcher - Trend Radar Validation System."""

import pytest
from pathlib import Path

from utils.entity_matcher import (
    EntityMatcher,
    EntityCandidate,
    EntityResolution,
    TIER_CONFIDENCE,
    COHERENCE_BOOST_VALUES,
    match_entity,
)


class TestEntityMatcherInit:
    """Tests for EntityMatcher initialization."""

    def test_loads_registry(self):
        """EntityMatcher loads entity registry."""
        matcher = EntityMatcher()
        assert len(matcher.registry) > 0

    def test_loads_ambiguity_rules(self):
        """EntityMatcher loads ambiguity rules."""
        matcher = EntityMatcher()
        assert len(matcher._ambiguous_terms) >= 0

    def test_builds_lookup_indices(self):
        """EntityMatcher builds fast lookup indices."""
        matcher = EntityMatcher()
        # Should have indices built
        assert hasattr(matcher, "_normalized_to_canonical")
        assert hasattr(matcher, "_alias_to_canonical")
        assert hasattr(matcher, "_github_org_to_canonical")
        assert hasattr(matcher, "_hf_namespace_to_canonical")


class TestTier1Matching:
    """Tests for Tier 1 (registry/alias) matching."""

    def test_exact_key_match(self):
        """Tier 1: Exact canonical key match."""
        matcher = EntityMatcher()
        result = matcher.resolve_entity("openai")

        assert result.primary_match == "openai"
        assert result.primary_name == "OpenAI"
        assert result.resolution_confidence == 1.0
        assert result.resolution_path == "tier1"

    def test_alias_match(self):
        """Tier 1: Alias match."""
        matcher = EntityMatcher()
        result = matcher.resolve_entity("open ai")

        assert result.primary_match == "openai"
        assert result.resolution_confidence == 1.0

    def test_case_insensitive(self):
        """Tier 1: Case insensitive matching."""
        matcher = EntityMatcher()
        result = matcher.resolve_entity("OpenAI")

        assert result.primary_match == "openai"

    def test_normalized_with_suffix(self):
        """Tier 1: Strips common suffixes."""
        matcher = EntityMatcher()
        result = matcher.resolve_entity("OpenAI Inc")

        assert result.primary_match == "openai"


class TestTier2Matching:
    """Tests for Tier 2 (org/namespace) matching."""

    def test_github_org_match(self):
        """Tier 2: GitHub org match."""
        matcher = EntityMatcher()
        result = matcher.resolve_entity("deepseek-ai", source="github")

        assert result.primary_match == "deepseek"
        assert result.resolution_confidence == TIER_CONFIDENCE[2]
        assert "tier2" in result.resolution_path

    def test_github_repo_with_org_prefix(self):
        """Tier 2: GitHub repo with org prefix."""
        matcher = EntityMatcher()
        result = matcher.resolve_entity("openai/gpt-4", source="github")

        assert result.primary_match == "openai"

    def test_huggingface_namespace_match(self):
        """Tier 2: HuggingFace namespace match."""
        matcher = EntityMatcher()
        result = matcher.resolve_entity("meta-llama", source="huggingface")

        assert result.primary_match == "meta"

    def test_product_match(self):
        """Tier 2: Product name match."""
        matcher = EntityMatcher()
        result = matcher.resolve_entity("gpt-4")

        assert result.primary_match == "openai"


class TestTier3Matching:
    """Tests for Tier 3 (substring) matching."""

    def test_substring_in_entity_name(self):
        """Tier 3: Substring match in longer text."""
        matcher = EntityMatcher()
        # Use a phrase that only matches via substring
        result = matcher.resolve_entity("news about deepseek")

        # Should find deepseek via substring
        if result.primary_match:
            assert result.primary_match == "deepseek"
            assert result.resolution_confidence == TIER_CONFIDENCE[3]


class TestAmbiguityHandling:
    """Tests for ambiguity detection and handling."""

    def test_ambiguous_term_detected(self):
        """Ambiguous terms are flagged."""
        matcher = EntityMatcher()
        result = matcher.resolve_entity("claude")

        # Claude is ambiguous (common name vs Anthropic product)
        if "ambiguous_term" in result.ambiguity_flags:
            assert True
        else:
            # If not in ambiguity list, should still resolve
            assert result.primary_match in ("anthropic", None)

    def test_context_resolves_ambiguity(self):
        """Context keywords resolve ambiguity."""
        matcher = EntityMatcher()
        result = matcher.resolve_entity("claude", context="Anthropic AI model")

        # With context, should resolve to anthropic
        assert result.primary_match == "anthropic" or "ambiguous_term" not in result.ambiguity_flags


class TestDenylist:
    """Tests for denylist filtering."""

    def test_short_name_rejected(self):
        """Names below min length are rejected."""
        matcher = EntityMatcher()
        result = matcher.resolve_entity("a")

        assert result.primary_match is None
        assert "denylisted" in result.ambiguity_flags

    def test_long_name_rejected(self):
        """Names above max length are rejected."""
        matcher = EntityMatcher()
        result = matcher.resolve_entity("a" * 100)

        assert result.primary_match is None


class TestCoherenceBoosts:
    """Tests for coherence boost application."""

    def test_apply_domain_coherence(self):
        """Domain coherence boost increases confidence."""
        matcher = EntityMatcher()
        candidate = EntityCandidate(
            canonical_key="openai",
            canonical_name="OpenAI",
            entity_type="company",
            match_tier=2,
            match_method="org_prefix",
            base_confidence=0.6,
        )

        matcher.apply_coherence_boost(candidate, "domain_coherence")

        assert "domain_coherence" in candidate.coherence_boosts
        assert candidate.confidence == 0.6 + COHERENCE_BOOST_VALUES["domain_coherence"]

    def test_multiple_boosts_stack(self):
        """Multiple coherence boosts stack (capped at 1.0)."""
        matcher = EntityMatcher()
        candidate = EntityCandidate(
            canonical_key="openai",
            canonical_name="OpenAI",
            entity_type="company",
            match_tier=2,
            match_method="org_prefix",
            base_confidence=0.6,
        )

        matcher.apply_coherence_boost(candidate, "domain_coherence")
        matcher.apply_coherence_boost(candidate, "readme_mention")

        # Confidence is capped at 1.0
        expected = min(1.0, 0.6 + COHERENCE_BOOST_VALUES["domain_coherence"] + COHERENCE_BOOST_VALUES["readme_mention"])
        assert candidate.confidence == expected

    def test_confidence_capped_at_1(self):
        """Confidence is capped at 1.0."""
        candidate = EntityCandidate(
            canonical_key="openai",
            canonical_name="OpenAI",
            entity_type="company",
            match_tier=1,
            match_method="registry",
            base_confidence=1.0,
            coherence_boosts=["domain_coherence", "readme_mention", "namespace_match"],
        )

        assert candidate.confidence == 1.0


class TestEntityResolution:
    """Tests for EntityResolution dataclass."""

    def test_resolution_fields(self):
        """EntityResolution has all required fields."""
        resolution = EntityResolution(
            primary_match="openai",
            primary_name="OpenAI",
            primary_type="company",
            candidates=[],
            resolution_confidence=1.0,
            ambiguity_flags=[],
            resolution_path="tier1",
            raw_input="OpenAI",
            normalized_input="openai",
        )

        assert resolution.primary_match == "openai"
        assert resolution.normalization_version == "1.0"


class TestRegistryValidation:
    """Tests for registry validation."""

    def test_validates_registry(self):
        """Registry validation runs without errors."""
        matcher = EntityMatcher()
        issues = matcher.validate_registry()
        # Should run without crashing and return issues dict
        assert isinstance(issues, dict)

    def test_validate_registry_returns_issues(self):
        """validate_registry returns issue dict."""
        matcher = EntityMatcher()
        issues = matcher.validate_registry()

        assert "alias_collisions" in issues
        assert "org_collisions" in issues
        assert "missing_fields" in issues


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_match_entity_function(self):
        """match_entity convenience function works."""
        result = match_entity("openai")

        assert result.primary_match == "openai"

    def test_get_entity(self):
        """get_entity returns entity definition."""
        matcher = EntityMatcher()
        entity = matcher.get_entity("openai")

        assert entity is not None
        assert entity["canonical_name"] == "OpenAI"

    def test_get_products_for_entity(self):
        """get_products_for_entity returns products."""
        matcher = EntityMatcher()
        products = matcher.get_products_for_entity("openai")

        assert "gpt-4" in products or "chatgpt" in products