"""
Signal Aggregator

Builds SignalProfiles by aggregating scores across all signal categories.
Calculates composite scores, momentum, and data freshness.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from .signal_models import (
    Entity, EntityType, SignalCategory, SignalScore, SignalProfile,
    CategoryWeights, normalize_entity_id, detect_entity_type
)
from .signal_scorers import (
    TechnicalScorer, CompanyScorer, FinancialScorer,
    ProductScorer, MediaScorer, get_scorer
)


class SignalAggregator:
    """
    Aggregates signal scores into unified SignalProfiles.

    Key responsibilities:
    - Collect latest scores per category for each entity
    - Calculate composite scores with configurable weights
    - Track momentum (score changes over time)
    - Manage data freshness indicators
    """

    def __init__(self, weights: Optional[CategoryWeights] = None):
        """
        Initialize aggregator with category weights.

        Args:
            weights: Custom category weights. Uses defaults if None.
        """
        self.weights = weights or CategoryWeights()
        self.scorers = {
            SignalCategory.TECHNICAL: TechnicalScorer(),
            SignalCategory.COMPANY_PRESENCE: CompanyScorer(),
            SignalCategory.FINANCIAL: FinancialScorer(),
            SignalCategory.PRODUCT_TRACTION: ProductScorer(),
            SignalCategory.MEDIA_SENTIMENT: MediaScorer(),
        }

    def build_profile(
        self,
        entity: Entity,
        scores: List[SignalScore],
        historical_scores: Optional[List[SignalScore]] = None
    ) -> SignalProfile:
        """
        Build a SignalProfile from entity and its scores.

        Args:
            entity: The entity to build profile for
            scores: Latest scores for this entity (all categories)
            historical_scores: Optional historical scores for momentum calc

        Returns:
            Complete SignalProfile
        """
        # Group scores by category
        scores_by_category: Dict[SignalCategory, List[SignalScore]] = defaultdict(list)
        for score in scores:
            scores_by_category[score.category].append(score)

        # Get latest score per category
        latest_scores: Dict[SignalCategory, SignalScore] = {}
        for category, cat_scores in scores_by_category.items():
            # Sort by created_at descending, take latest
            sorted_scores = sorted(cat_scores, key=lambda s: s.created_at, reverse=True)
            latest_scores[category] = sorted_scores[0]

        # Build profile
        profile = SignalProfile(
            entity_id=entity.id,
            entity_name=entity.name,
            entity_type=entity.entity_type,
            as_of=datetime.utcnow(),
        )

        # Set category scores
        for category, score_obj in latest_scores.items():
            setattr(profile, f"{self._category_to_attr(category)}_score", score_obj.score)

        # Set confidence values (from most recent observations)
        # For now, use a fixed confidence based on data availability
        for category in SignalCategory:
            attr = f"{self._category_to_attr(category)}_confidence"
            if category in latest_scores:
                setattr(profile, attr, 0.8)  # Have data
            else:
                setattr(profile, attr, 0.0)  # No data

        # Calculate composite score
        profile.composite_score = self._calculate_composite(latest_scores)

        # Calculate momentum if historical data available
        if historical_scores:
            profile.momentum_7d = self._calculate_momentum(
                latest_scores, historical_scores, days=7
            )
            profile.momentum_30d = self._calculate_momentum(
                latest_scores, historical_scores, days=30
            )

        # Track data freshness
        profile.data_freshness = {
            cat.value: score_obj.created_at.isoformat()
            for cat, score_obj in latest_scores.items()
        }

        # Top signals (IDs of contributing scores)
        profile.top_signals = [s.id for s in latest_scores.values()]

        return profile

    def build_profiles_batch(
        self,
        entities: List[Entity],
        all_scores: List[SignalScore],
        historical_scores: Optional[List[SignalScore]] = None
    ) -> List[SignalProfile]:
        """
        Build SignalProfiles for multiple entities efficiently.

        Args:
            entities: List of entities
            all_scores: All scores for these entities
            historical_scores: Optional historical scores

        Returns:
            List of SignalProfiles
        """
        # Group scores by entity_id
        scores_by_entity: Dict[str, List[SignalScore]] = defaultdict(list)
        for score in all_scores:
            scores_by_entity[score.entity_id].append(score)

        # Group historical by entity_id
        historical_by_entity: Dict[str, List[SignalScore]] = defaultdict(list)
        if historical_scores:
            for score in historical_scores:
                historical_by_entity[score.entity_id].append(score)

        # Build profiles
        profiles = []
        for entity in entities:
            entity_scores = scores_by_entity.get(entity.id, [])
            entity_historical = historical_by_entity.get(entity.id)

            if entity_scores:  # Only build if we have scores
                profile = self.build_profile(entity, entity_scores, entity_historical)
                profiles.append(profile)

        return profiles

    def _calculate_composite(
        self,
        latest_scores: Dict[SignalCategory, SignalScore]
    ) -> float:
        """
        Calculate weighted composite score from category scores.

        Applies a coverage penalty when entities have data for fewer signal types.
        This prevents entities with only one high score from dominating rankings.

        Coverage penalty formula:
        - 1 signal type: 50% penalty (multiply by 0.5)
        - 2 signal types: 25% penalty (multiply by 0.75)
        - 3 signal types: 10% penalty (multiply by 0.9)
        - 4+ signal types: no penalty (multiply by 1.0)
        """
        if not latest_scores:
            return 0.0

        weighted_sum = 0.0
        total_weight = 0.0

        for category, score_obj in latest_scores.items():
            weight = self.weights.get_weight(category)
            weighted_sum += score_obj.score * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        # Calculate raw composite (normalized by available weights)
        raw_composite = weighted_sum / total_weight

        # Apply coverage penalty based on number of signal types
        num_signals = len(latest_scores)
        coverage_multipliers = {
            1: 0.50,  # Single signal: 50% penalty
            2: 0.75,  # Two signals: 25% penalty
            3: 0.90,  # Three signals: 10% penalty
        }
        coverage_multiplier = coverage_multipliers.get(num_signals, 1.0)

        return round(raw_composite * coverage_multiplier, 2)

    def _calculate_momentum(
        self,
        latest_scores: Dict[SignalCategory, SignalScore],
        historical_scores: List[SignalScore],
        days: int = 7
    ) -> Optional[float]:
        """
        Calculate momentum as percentage change over time period.

        Args:
            latest_scores: Current scores by category
            historical_scores: Historical score data
            days: Lookback period in days

        Returns:
            Momentum as percentage (-100 to +100), or None if insufficient data
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Group historical by category and filter by date
        historical_by_cat: Dict[SignalCategory, List[SignalScore]] = defaultdict(list)
        for score in historical_scores:
            if score.created_at <= cutoff:
                historical_by_cat[score.category].append(score)

        # Get comparison scores (closest to cutoff)
        comparison_scores: Dict[SignalCategory, float] = {}
        for category, scores in historical_by_cat.items():
            if scores:
                # Get score closest to cutoff date
                closest = min(scores, key=lambda s: abs((s.created_at - cutoff).total_seconds()))
                comparison_scores[category] = closest.score

        # Calculate momentum
        if not comparison_scores:
            return None

        total_change = 0.0
        categories_counted = 0

        for category, current_score_obj in latest_scores.items():
            if category in comparison_scores:
                old_score = comparison_scores[category]
                current_score = current_score_obj.score

                if old_score > 0:
                    pct_change = ((current_score - old_score) / old_score) * 100
                    total_change += pct_change
                    categories_counted += 1

        if categories_counted == 0:
            return None

        return round(total_change / categories_counted, 2)

    def _category_to_attr(self, category: SignalCategory) -> str:
        """Convert SignalCategory to profile attribute prefix."""
        mapping = {
            SignalCategory.TECHNICAL: "technical",
            SignalCategory.COMPANY_PRESENCE: "company",
            SignalCategory.FINANCIAL: "financial",
            SignalCategory.PRODUCT_TRACTION: "product",
            SignalCategory.MEDIA_SENTIMENT: "media",
        }
        return mapping.get(category, category.value)

    def score_raw_data(
        self,
        entity_id: str,
        category: SignalCategory,
        raw_data: Dict[str, Any],
        source_id: str = "manual"
    ) -> SignalScore:
        """
        Score raw data and create a SignalScore.

        Convenience method that handles scorer selection.

        Args:
            entity_id: Entity ID
            category: Signal category
            raw_data: Raw metrics to score
            source_id: Source identifier

        Returns:
            SignalScore object
        """
        scorer = self.scorers[category]
        score_value = scorer.score(raw_data)
        confidence = scorer.get_confidence(raw_data)

        return SignalScore(
            entity_id=entity_id,
            source_id=source_id,
            category=category,
            score=score_value,
            created_at=datetime.utcnow(),
        )

    def get_category_breakdown(self, profile: SignalProfile) -> Dict[str, Dict[str, Any]]:
        """
        Get detailed breakdown of profile scores.

        Returns:
            Dict with score, confidence, and weight per category
        """
        breakdown = {}
        for category in SignalCategory:
            attr = self._category_to_attr(category)
            score = getattr(profile, f"{attr}_score", None)
            confidence = getattr(profile, f"{attr}_confidence", 0.0)
            weight = self.weights.get_weight(category)

            breakdown[category.value] = {
                "score": score,
                "confidence": confidence,
                "weight": weight,
                "weighted_contribution": (score or 0) * weight,
                "has_data": score is not None,
            }

        return breakdown


def create_profile_from_raw(
    entity_name: str,
    raw_data_by_category: Dict[str, Dict[str, Any]],
    entity_type: Optional[EntityType] = None
) -> SignalProfile:
    """
    Convenience function to create a profile directly from raw data.

    Args:
        entity_name: Name of the entity
        raw_data_by_category: Dict of category -> raw_data
            e.g., {"technical": {"stars": 1000}, "company": {"cb_rank": 150}}
        entity_type: Optional entity type (auto-detected if None)

    Returns:
        SignalProfile with all available scores
    """
    # Create entity
    canonical_id = normalize_entity_id(entity_name)
    entity_type = entity_type or detect_entity_type(entity_name)

    entity = Entity(
        canonical_id=canonical_id,
        name=entity_name,
        entity_type=entity_type,
    )

    # Score each category
    aggregator = SignalAggregator()
    scores = []

    category_map = {
        "technical": SignalCategory.TECHNICAL,
        "company": SignalCategory.COMPANY_PRESENCE,
        "financial": SignalCategory.FINANCIAL,
        "product": SignalCategory.PRODUCT_TRACTION,
        "media": SignalCategory.MEDIA_SENTIMENT,
    }

    for cat_name, raw_data in raw_data_by_category.items():
        category = category_map.get(cat_name.lower())
        if category and raw_data:
            score = aggregator.score_raw_data(
                entity_id=entity.id,
                category=category,
                raw_data=raw_data,
            )
            scores.append(score)

    # Build profile
    return aggregator.build_profile(entity, scores)


if __name__ == "__main__":
    # Test the aggregator
    print("Testing Signal Aggregator")
    print("=" * 50)

    # Create a test profile
    profile = create_profile_from_raw(
        entity_name="OpenAI",
        raw_data_by_category={
            "technical": {
                "source": "github",
                "stars": 150000,
                "forks": 25000,
            },
            "company": {
                "cb_rank": 4,
                "employee_count": 1500,
            },
            "financial": {
                "total_funding_usd": 10000000000,  # $10B
                "investors": ["Microsoft", "Sequoia", "Thrive"],
            },
            "media": {
                "weighted_score": 9.2,
                "mention_count": 500,
                "article_count": 150,
            },
        }
    )

    print(f"Entity: {profile.entity_name}")
    print(f"Type: {profile.entity_type}")
    print()
    print("Scores:")
    print(f"  Technical:  {profile.technical_score or 'N/A'}")
    print(f"  Company:    {profile.company_score or 'N/A'}")
    print(f"  Financial:  {profile.financial_score or 'N/A'}")
    print(f"  Product:    {profile.product_score or 'N/A'}")
    print(f"  Media:      {profile.media_score or 'N/A'}")
    print()
    print(f"Composite Score: {profile.composite_score}")
    print()

    # Show radar data
    print("Radar Data:")
    for item in profile.get_radar_data():
        print(f"  {item['axis']}: {item['value']}")
