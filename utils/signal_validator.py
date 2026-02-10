"""
Signal Validator for Trend Radar Validation System.

Computes validation scores by analyzing cross-source corroboration.
Splits validation into Coverage (did we check?) and Strength (how strong is evidence?).
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from utils.entity_matcher import EntityCandidate, EntityResolution


@dataclass
class SourceMatch:
    """A match found in a specific source."""
    source: str
    category: str  # technical, social, financial, predictive, media
    match_tier: int
    confidence: float
    matched_item: str  # e.g., repo name, model ID, post title
    matched_at: str  # ISO timestamp
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Complete validation result with coverage and strength metrics."""

    # Coverage: did we have data to check?
    validation_coverage: float  # 0-1
    sources_checked: List[str]
    sources_missing: List[str]  # No snapshot available
    sources_no_data: List[str]  # Checked but empty

    # Strength: how strong is the evidence?
    validation_strength: float  # 0-1

    # Combined score
    validation_score: float  # coverage * strength

    # Category diversity
    diversity_bonus: float

    # Temporal alignment
    temporal_alignment: float  # 0-1

    # Fields with defaults must come after non-default fields
    sources_stale: List[str] = field(default_factory=list)  # Data too old (doesn't count)
    corroborating_sources: Dict[str, SourceMatch] = field(default_factory=dict)
    tier_distribution: Dict[int, int] = field(default_factory=dict)  # {1: 2, 2: 1, 3: 0}
    categories_found: List[str] = field(default_factory=list)

    # Debug/explainability
    validation_fail_reasons: Dict[str, str] = field(default_factory=dict)
    scoring_breakdown: Dict[str, float] = field(default_factory=dict)


# Source category mappings (loaded from config)
DEFAULT_SOURCE_CATEGORIES = {
    "technical": ["github", "huggingface", "arxiv", "paperswithcode"],
    "social": ["reddit", "hackernews", "twitter"],
    "financial": ["sec", "crunchbase", "openbook_vc"],
    "predictive": ["polymarket", "manifold", "metaculus"],
    "media": ["news", "ai_labs_news"],
}

# Diversity bonuses for cross-category validation
DEFAULT_DIVERSITY_BONUSES = {
    "technical_financial": 0.15,
    "technical_predictive": 0.10,
    "financial_predictive": 0.12,
    "social_financial": 0.08,
    "any_three_categories": 0.20,
    "all_four_categories": 0.30,
}

# Validation thresholds
DEFAULT_THRESHOLDS = {
    "high_confidence": 0.7,
    "validated": 0.5,
    "min_sources_for_validated": 2,
    "min_tier_for_count": 2,  # Tier 3 alone NEVER counts toward validated
    "diversity_bonus_cap": 0.25,  # Max diversity bonus to prevent inflation
    "tier3_max_contribution": 0.1,  # Tier 3 contributes at most 10% to strength
}


class SignalValidator:
    """
    Computes validation scores for trend signals.

    Uses cross-source corroboration with diversity and temporal alignment factors.
    """

    def __init__(self, source_categories_path: Optional[Path] = None):
        config_dir = Path(__file__).parent.parent / "config"
        self.config_path = source_categories_path or config_dir / "source_categories.json"

        self._load_config()

    def _load_config(self):
        """Load source category configuration."""
        try:
            with open(self.config_path, encoding="utf-8") as f:
                config = json.load(f)

            # Extract categories
            categories = config.get("categories", {})
            self.source_categories: Dict[str, List[str]] = {}
            self.category_weights: Dict[str, float] = {}

            for cat_name, cat_info in categories.items():
                self.source_categories[cat_name] = cat_info.get("sources", [])
                self.category_weights[cat_name] = cat_info.get("weight", 1.0)

            # Build reverse mapping: source → category
            self.source_to_category: Dict[str, str] = {}
            for category, sources in self.source_categories.items():
                for source in sources:
                    self.source_to_category[source] = category

            # Load diversity bonuses
            self.diversity_bonuses = config.get("diversity_bonuses", DEFAULT_DIVERSITY_BONUSES)

            # Load thresholds
            self.thresholds = config.get("validation_thresholds", DEFAULT_THRESHOLDS)

            # Load source metadata
            self.source_metadata = config.get("source_metadata", {})

        except (FileNotFoundError, json.JSONDecodeError):
            # Use defaults
            self.source_categories = DEFAULT_SOURCE_CATEGORIES
            self.source_to_category = {}
            for category, sources in self.source_categories.items():
                for source in sources:
                    self.source_to_category[source] = category
            self.diversity_bonuses = DEFAULT_DIVERSITY_BONUSES
            self.thresholds = DEFAULT_THRESHOLDS
            self.source_metadata = {}
            self.category_weights = {cat: 1.0 for cat in self.source_categories}

    def compute_validation(
        self,
        matches: Dict[str, SourceMatch],
        resolution: EntityResolution,
        data_health: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """
        Compute validation result from source matches.

        Args:
            matches: Dict of source → SourceMatch
            resolution: Entity resolution result
            data_health: Optional data health info from snapshot

        Returns:
            ValidationResult with coverage, strength, and combined score
        """
        # Initialize tracking
        sources_checked: List[str] = []
        sources_missing: List[str] = []
        sources_no_data: List[str] = []
        validation_fail_reasons: Dict[str, str] = {}

        # Get available sources from data health
        # CRITICAL: Stale sources should NOT count toward coverage
        if data_health:
            all_available = set(data_health.get("sources_available", []))
            stale_sources = set(data_health.get("sources_stale", []))
            missing_sources = set(data_health.get("sources_missing", []))
            # Only count non-stale sources as truly available
            available_sources = all_available - stale_sources
        else:
            available_sources = set(self.source_to_category.keys())
            missing_sources = set()
            stale_sources = set()

        # Track which sources we checked
        sources_stale_list: List[str] = []
        for source in self.source_to_category.keys():
            if source in missing_sources:
                sources_missing.append(source)
                validation_fail_reasons[source] = "no_snapshot"
            elif source in stale_sources:
                # Stale sources are tracked separately and don't count toward coverage
                sources_stale_list.append(source)
                validation_fail_reasons[source] = "stale_data"
            elif source in matches:
                sources_checked.append(source)
            elif source in available_sources:
                sources_no_data.append(source)
                validation_fail_reasons[source] = "no_match"

        # Compute coverage (what fraction of available sources did we check?)
        total_possible = len(available_sources)
        if total_possible > 0:
            validation_coverage = len(sources_checked) / total_possible
        else:
            validation_coverage = 0.0

        # Compute strength metrics
        strength_result = self._compute_strength(matches, resolution)

        # Compute temporal alignment
        temporal_alignment = self._compute_temporal_alignment(matches)

        # Compute diversity bonus (pass matches to filter by tier)
        categories_found = list(set(
            self.source_to_category.get(source, "unknown")
            for source in matches.keys()
        ))
        diversity_bonus = self._compute_diversity_bonus(categories_found, matches)

        # Compute tier distribution
        tier_distribution = {1: 0, 2: 0, 3: 0}
        for match in matches.values():
            tier = match.match_tier
            if tier in tier_distribution:
                tier_distribution[tier] += 1

        # Compute combined validation score
        # Formula: coverage * strength * (1 + diversity_bonus) * temporal_factor
        raw_strength = strength_result["raw_strength"]
        temporal_factor = 0.7 + (0.3 * temporal_alignment)  # Range: 0.7 - 1.0

        validation_strength = raw_strength * temporal_factor
        validation_score = validation_coverage * validation_strength * (1 + diversity_bonus)

        # Cap at 1.0
        validation_score = min(1.0, validation_score)

        # Build scoring breakdown for explainability
        scoring_breakdown = {
            "source_count_factor": strength_result["source_count_factor"],
            "tier_quality_factor": strength_result["tier_quality_factor"],
            "temporal_alignment": temporal_alignment,
            "diversity_bonus": diversity_bonus,
            "coverage": validation_coverage,
            "raw_strength": raw_strength,
            "final_strength": validation_strength,
            "tier12_count": strength_result.get("tier12_count", 0),
            "tier3_only": strength_result.get("tier3_only", False),
        }

        return ValidationResult(
            validation_coverage=validation_coverage,
            sources_checked=sources_checked,
            sources_missing=sources_missing,
            sources_no_data=sources_no_data,
            sources_stale=sources_stale_list,
            validation_strength=validation_strength,
            corroborating_sources=matches,
            tier_distribution=tier_distribution,
            validation_score=validation_score,
            categories_found=categories_found,
            diversity_bonus=diversity_bonus,
            temporal_alignment=temporal_alignment,
            validation_fail_reasons=validation_fail_reasons,
            scoring_breakdown=scoring_breakdown,
        )

    def _compute_strength(
        self,
        matches: Dict[str, SourceMatch],
        resolution: EntityResolution,
    ) -> Dict[str, float]:
        """
        Compute validation strength from matches.

        Strength = Source count factor (40%) + Tier quality factor (60%)

        CRITICAL: Tier 3 matches alone CANNOT produce "validated" status.
        Tier 3 only contributes weak evidence and is capped.
        """
        if not matches:
            return {
                "raw_strength": 0.0,
                "source_count_factor": 0.0,
                "tier_quality_factor": 0.0,
                "tier12_count": 0,
                "tier3_only": True,
            }

        # Separate Tier 1/2 from Tier 3
        tier12_matches = {s: m for s, m in matches.items() if m.match_tier <= 2}
        tier3_matches = {s: m for s, m in matches.items() if m.match_tier == 3}

        tier3_only = len(tier12_matches) == 0

        # Source count factor (40%)
        # ONLY count unique categories with Tier 1/2 matches (Tier 3 doesn't count here)
        categories_with_signal: Set[str] = set()
        for source, match in tier12_matches.items():
            category = self.source_to_category.get(source, "unknown")
            categories_with_signal.add(category)

        num_categories = len(categories_with_signal)

        # Score based on category count (Tier 1/2 only)
        if num_categories >= 4:
            source_count_factor = 1.0
        elif num_categories == 3:
            source_count_factor = 0.75
        elif num_categories == 2:
            source_count_factor = 0.5
        elif num_categories == 1:
            source_count_factor = 0.2
        else:
            source_count_factor = 0.0

        # Tier quality factor (60%)
        # Compute separately for Tier 1/2 and Tier 3
        tier_weights = {1: 1.0, 2: 0.6, 3: 0.2}

        # Tier 1/2 contribution
        tier12_weight = 0.0
        tier12_count = 0
        for match in tier12_matches.values():
            weight = tier_weights.get(match.match_tier, 0.1)
            tier12_weight += weight * match.confidence
            tier12_count += 1

        # Tier 3 contribution (CAPPED)
        tier3_max = self.thresholds.get("tier3_max_contribution", 0.1)
        tier3_weight = 0.0
        for match in tier3_matches.values():
            tier3_weight += tier_weights[3] * match.confidence

        # Cap Tier 3 contribution
        tier3_contribution = min(tier3_weight, tier3_max)

        # Combined tier quality
        total_count = len(matches)
        if total_count > 0:
            # Tier 1/2 gets full weight, Tier 3 is capped
            if tier12_count > 0:
                tier_quality_factor = (tier12_weight / tier12_count) * 0.9 + tier3_contribution * 0.1
            else:
                # Only Tier 3 matches - very weak signal
                tier_quality_factor = tier3_contribution
        else:
            tier_quality_factor = 0.0

        # Combined strength
        raw_strength = (0.4 * source_count_factor) + (0.6 * tier_quality_factor)

        return {
            "raw_strength": raw_strength,
            "source_count_factor": source_count_factor,
            "tier_quality_factor": tier_quality_factor,
            "tier12_count": tier12_count,
            "tier3_only": tier3_only,
        }

    def _compute_temporal_alignment(
        self,
        matches: Dict[str, SourceMatch],
    ) -> float:
        """
        Compute temporal alignment of matches.

        Score based on how close together the matches occurred.
        """
        if len(matches) < 2:
            return 0.0  # Need at least 2 sources for alignment

        # Parse timestamps
        timestamps: List[datetime] = []
        for match in matches.values():
            try:
                ts = match.matched_at
                if "T" in ts:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                else:
                    dt = datetime.strptime(ts[:10], "%Y-%m-%d")

                # Make naive for comparison
                if dt.tzinfo:
                    dt = dt.replace(tzinfo=None)

                timestamps.append(dt)
            except (ValueError, TypeError):
                continue

        if len(timestamps) < 2:
            return 0.0

        # Calculate time span
        timestamps.sort()
        span_days = (timestamps[-1] - timestamps[0]).days

        # Score based on span
        if span_days <= 7:
            return 1.0  # All within a week
        elif span_days <= 14:
            return 0.7  # Within 2 weeks
        else:
            return 0.4  # More than 2 weeks apart

    def _compute_diversity_bonus(
        self,
        categories_found: List[str],
        matches: Optional[Dict[str, SourceMatch]] = None,
    ) -> float:
        """
        Compute diversity bonus based on category spread.

        Rewards cross-category validation (e.g., technical + financial).
        CAPPED to prevent inflation from same-category sources.

        Each category contributes at most ONCE (strongest match only).
        """
        if len(categories_found) < 2:
            return 0.0

        # Get unique categories with Tier 1/2 matches only
        # (Tier 3 doesn't contribute to diversity bonus)
        if matches:
            valid_categories: Set[str] = set()
            for source, match in matches.items():
                if match.match_tier <= 2:
                    category = self.source_to_category.get(source, "unknown")
                    valid_categories.add(category)
            categories_set = valid_categories
        else:
            categories_set = set(categories_found)

        if len(categories_set) < 2:
            return 0.0

        bonus = 0.0

        # Check specific category pairs (only count once per pair)
        if "technical" in categories_set and "financial" in categories_set:
            bonus += self.diversity_bonuses.get("technical_financial", 0.15)

        if "technical" in categories_set and "predictive" in categories_set:
            bonus += self.diversity_bonuses.get("technical_predictive", 0.10)

        if "financial" in categories_set and "predictive" in categories_set:
            bonus += self.diversity_bonuses.get("financial_predictive", 0.12)

        if "social" in categories_set and "financial" in categories_set:
            bonus += self.diversity_bonuses.get("social_financial", 0.08)

        # Category count bonuses (mutually exclusive - take higher)
        if len(categories_set) >= 4:
            bonus += self.diversity_bonuses.get("all_four_categories", 0.30)
        elif len(categories_set) >= 3:
            bonus += self.diversity_bonuses.get("any_three_categories", 0.20)

        # CAP the bonus to prevent inflation
        cap = self.thresholds.get("diversity_bonus_cap", 0.25)
        return min(bonus, cap)

    def get_validation_status(self, result: ValidationResult) -> str:
        """
        Get human-readable validation status.

        Returns: "high_confidence", "validated", "insufficient_data", or "unvalidated"
        """
        if result.validation_score >= self.thresholds.get("high_confidence", 0.7):
            return "high_confidence"
        elif result.validation_score >= self.thresholds.get("validated", 0.5):
            return "validated"
        elif result.validation_coverage < 0.5:
            return "insufficient_data"
        else:
            return "unvalidated"

    def is_validated(self, result: ValidationResult) -> bool:
        """
        Check if signal meets minimum validation threshold.

        CRITICAL: Tier 3 matches alone CANNOT produce "validated" status.
        Must have at least one Tier 1 or Tier 2 match.
        """
        # Check if we only have Tier 3 matches - NEVER validated
        if result.scoring_breakdown.get("tier3_only", False):
            return False

        # Need at least 2 sources with Tier 1/2 matches
        min_sources = self.thresholds.get("min_sources_for_validated", 2)
        min_tier = self.thresholds.get("min_tier_for_count", 2)

        valid_source_count = sum(
            1 for match in result.corroborating_sources.values()
            if match.match_tier <= min_tier
        )

        if valid_source_count >= min_sources:
            return True

        # Alternative: 1 Tier 1 + 2 Tier 3 (Tier 3 as supporting evidence only)
        tier1_count = result.tier_distribution.get(1, 0)
        tier3_count = result.tier_distribution.get(3, 0)

        if tier1_count >= 1 and tier3_count >= 2:
            return True

        return False

    def format_validation_summary(self, result: ValidationResult) -> str:
        """Format validation result as human-readable summary."""
        status = self.get_validation_status(result)
        score_pct = int(result.validation_score * 100)

        lines = [
            f"Validation: {score_pct}% ({status})",
            f"└─ Coverage: {len(result.sources_checked)}/{len(result.sources_checked) + len(result.sources_missing)} sources",
        ]

        # Show tier distribution
        tier_strs = []
        for tier, count in sorted(result.tier_distribution.items()):
            if count > 0:
                tier_strs.append(f"Tier {tier}: {count}")

        if tier_strs:
            lines.append(f"└─ Strength: {', '.join(tier_strs)}")

        # Show categories
        if result.categories_found:
            lines.append(f"└─ Categories: {', '.join(result.categories_found)}")

        # Show fail reasons if any
        if result.validation_fail_reasons and status in ("unvalidated", "insufficient_data"):
            fail_summary = ", ".join(
                f"{k}={v}" for k, v in list(result.validation_fail_reasons.items())[:3]
            )
            lines.append(f"└─ Fail: {fail_summary}")

        return "\n".join(lines)
