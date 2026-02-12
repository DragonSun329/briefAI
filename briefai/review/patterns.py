"""
Pattern Discovery Engine

Analyzes correlations between prediction attributes and outcomes
to identify what the system is good and bad at predicting.

This is the learning engine - the most important part.

v1.1: Added sample-size protection (insight_strength) and reliability ranking.
"""

from collections import defaultdict
from typing import Optional

from .models import (
    ExpiredPrediction,
    ResolvedOutcome,
    LearningInsight,
    OutcomeStatus,
    Direction,
)


# v1.1: Minimum sample sizes for insight strength levels
MIN_SAMPLE_WEAK = 2  # Minimum to emit any insight
MIN_SAMPLE_MODERATE = 5  # Moderate confidence
MIN_SAMPLE_STRONG = 10  # Strong confidence


def safe_divide(num: float, denom: float, default: float = 0.0) -> float:
    return num / denom if denom > 0 else default


class PatternAnalyzer:
    """
    Analyzes prediction outcomes to discover patterns.
    
    Identifies correlations between:
    - Signal sources and correctness
    - Mechanisms and correctness
    - Entity types and correctness
    - Categories and correctness
    - Confidence levels and actual outcomes
    """
    
    def __init__(
        self,
        predictions: list[ExpiredPrediction],
        outcomes: list[ResolvedOutcome],
    ):
        self.predictions = predictions
        self.outcomes = outcomes
        self.outcome_map = {o.prediction_id: o for o in outcomes}
        
        # Pre-compute correctness for each prediction
        self.correctness = {}
        for pred in predictions:
            outcome = self.outcome_map.get(pred.prediction_id)
            if outcome and outcome.outcome != OutcomeStatus.UNCLEAR:
                self.correctness[pred.prediction_id] = (
                    outcome.outcome == OutcomeStatus.CORRECT
                )
    
    def analyze_mechanism_performance(self) -> list[LearningInsight]:
        """
        Analyze which prediction mechanisms work best.
        
        Mechanisms: product_launch, research_translation, hiring_expansion,
                   pricing_shift, partnership, media_attention_spike, etc.
        """
        insights = []
        mechanism_stats = defaultdict(lambda: {"correct": 0, "total": 0})
        
        for pred in self.predictions:
            if pred.prediction_id not in self.correctness:
                continue
            
            mechanism = pred.mechanism or "unknown"
            mechanism_stats[mechanism]["total"] += 1
            if self.correctness[pred.prediction_id]:
                mechanism_stats[mechanism]["correct"] += 1
        
        for mechanism, stats in mechanism_stats.items():
            if stats["total"] < 2:  # Need at least 2 samples
                continue
            
            success_rate = safe_divide(stats["correct"], stats["total"])
            
            # Generate interpretation
            if success_rate >= 0.7:
                interpretation = f"Mechanism '{mechanism}' is reliable - predictions are frequently correct"
            elif success_rate >= 0.5:
                interpretation = f"Mechanism '{mechanism}' has moderate reliability"
            elif success_rate >= 0.3:
                interpretation = f"Mechanism '{mechanism}' underperforms - predictions often incorrect"
            else:
                interpretation = f"Mechanism '{mechanism}' is unreliable - consider reducing confidence"
            
            insights.append(LearningInsight(
                category="mechanism",
                pattern=mechanism,
                success_rate=success_rate,
                sample_size=stats["total"],
                interpretation=interpretation,
            ))
        
        return sorted(insights, key=lambda x: (-x.success_rate, -x.sample_size))
    
    def analyze_category_performance(self) -> list[LearningInsight]:
        """
        Analyze which prediction categories work best.
        
        Categories: media, social, financial, technical, etc.
        """
        insights = []
        category_stats = defaultdict(lambda: {"correct": 0, "total": 0})
        
        for pred in self.predictions:
            if pred.prediction_id not in self.correctness:
                continue
            
            category = pred.category or "unknown"
            category_stats[category]["total"] += 1
            if self.correctness[pred.prediction_id]:
                category_stats[category]["correct"] += 1
        
        for category, stats in category_stats.items():
            if stats["total"] < 2:
                continue
            
            success_rate = safe_divide(stats["correct"], stats["total"])
            
            if success_rate >= 0.7:
                interpretation = f"Category '{category}' predictions are reliable"
            elif success_rate >= 0.5:
                interpretation = f"Category '{category}' has moderate accuracy"
            else:
                interpretation = f"Category '{category}' predictions often miss - needs improvement"
            
            insights.append(LearningInsight(
                category="signal_category",
                pattern=category,
                success_rate=success_rate,
                sample_size=stats["total"],
                interpretation=interpretation,
            ))
        
        return sorted(insights, key=lambda x: (-x.success_rate, -x.sample_size))
    
    def analyze_entity_type_performance(self) -> list[LearningInsight]:
        """
        Analyze accuracy by entity type.
        
        Infers entity type from entity name patterns:
        - Hyperscalers: Google, Microsoft, Amazon, Meta, etc.
        - Startups: Generally smaller, specific product names
        - Chip companies: NVIDIA, AMD, Intel, etc.
        - Enterprise: Salesforce, Oracle, SAP, etc.
        """
        insights = []
        
        # Entity type classification rules
        hyperscalers = {"google", "microsoft", "amazon", "meta", "apple", "anthropic", "openai"}
        chip_companies = {"nvidia", "amd", "intel", "qualcomm", "arm", "tsmc", "broadcom"}
        enterprise = {"salesforce", "oracle", "sap", "ibm", "workday", "servicenow"}
        
        type_stats = defaultdict(lambda: {"correct": 0, "total": 0})
        
        for pred in self.predictions:
            if pred.prediction_id not in self.correctness:
                continue
            
            entity_lower = pred.entity.lower()
            
            # Classify entity
            if any(h in entity_lower for h in hyperscalers):
                entity_type = "hyperscaler"
            elif any(c in entity_lower for c in chip_companies):
                entity_type = "chip_company"
            elif any(e in entity_lower for e in enterprise):
                entity_type = "enterprise_saas"
            else:
                entity_type = "other"
            
            type_stats[entity_type]["total"] += 1
            if self.correctness[pred.prediction_id]:
                type_stats[entity_type]["correct"] += 1
        
        for entity_type, stats in type_stats.items():
            if stats["total"] < 2:
                continue
            
            success_rate = safe_divide(stats["correct"], stats["total"])
            
            if success_rate >= 0.7:
                interpretation = f"Predictions about {entity_type} entities are reliable"
            elif success_rate >= 0.5:
                interpretation = f"Moderate accuracy for {entity_type} predictions"
            else:
                interpretation = f"Weak accuracy for {entity_type} - may need different approach"
            
            insights.append(LearningInsight(
                category="entity_type",
                pattern=entity_type,
                success_rate=success_rate,
                sample_size=stats["total"],
                interpretation=interpretation,
            ))
        
        return sorted(insights, key=lambda x: (-x.success_rate, -x.sample_size))
    
    def analyze_confidence_calibration(self) -> list[LearningInsight]:
        """
        Analyze how well confidence scores predict actual outcomes.
        
        Identifies if we're overconfident or underconfident.
        """
        insights = []
        
        # Group by confidence buckets
        buckets = {
            "very_high": {"threshold": 0.9, "correct": 0, "total": 0},
            "high": {"threshold": 0.7, "correct": 0, "total": 0},
            "medium": {"threshold": 0.5, "correct": 0, "total": 0},
            "low": {"threshold": 0.0, "correct": 0, "total": 0},
        }
        
        for pred in self.predictions:
            if pred.prediction_id not in self.correctness:
                continue
            
            # Find bucket
            if pred.confidence >= 0.9:
                bucket = "very_high"
            elif pred.confidence >= 0.7:
                bucket = "high"
            elif pred.confidence >= 0.5:
                bucket = "medium"
            else:
                bucket = "low"
            
            buckets[bucket]["total"] += 1
            if self.correctness[pred.prediction_id]:
                buckets[bucket]["correct"] += 1
        
        for bucket_name, stats in buckets.items():
            if stats["total"] < 2:
                continue
            
            actual_rate = safe_divide(stats["correct"], stats["total"])
            expected_rate = stats["threshold"]
            
            # Determine if overconfident or underconfident
            if actual_rate < expected_rate - 0.15:
                interpretation = f"Overconfident at {bucket_name} level - actual accuracy ({actual_rate:.0%}) below expected"
            elif actual_rate > expected_rate + 0.15:
                interpretation = f"Underconfident at {bucket_name} level - actual accuracy ({actual_rate:.0%}) exceeds expectation"
            else:
                interpretation = f"Well-calibrated at {bucket_name} level"
            
            insights.append(LearningInsight(
                category="calibration",
                pattern=bucket_name,
                success_rate=actual_rate,
                sample_size=stats["total"],
                interpretation=interpretation,
            ))
        
        return insights
    
    def analyze_direction_performance(self) -> list[LearningInsight]:
        """
        Analyze accuracy by prediction direction.
        
        Identifies if we're better at bullish vs bearish predictions.
        """
        insights = []
        direction_stats = defaultdict(lambda: {"correct": 0, "total": 0})
        
        for pred in self.predictions:
            if pred.prediction_id not in self.correctness:
                continue
            
            direction = pred.direction.value if hasattr(pred.direction, 'value') else str(pred.direction)
            direction_stats[direction]["total"] += 1
            if self.correctness[pred.prediction_id]:
                direction_stats[direction]["correct"] += 1
        
        for direction, stats in direction_stats.items():
            if stats["total"] < 2:
                continue
            
            success_rate = safe_divide(stats["correct"], stats["total"])
            
            if direction == "up":
                if success_rate >= 0.6:
                    interpretation = "Strong at predicting bullish trends"
                else:
                    interpretation = "Bullish predictions underperform - may be too optimistic"
            elif direction == "down":
                if success_rate >= 0.6:
                    interpretation = "Strong at predicting bearish trends"
                else:
                    interpretation = "Bearish predictions underperform - may miss declines"
            else:
                interpretation = f"Direction '{direction}' has moderate reliability"
            
            insights.append(LearningInsight(
                category="direction",
                pattern=direction,
                success_rate=success_rate,
                sample_size=stats["total"],
                interpretation=interpretation,
            ))
        
        return sorted(insights, key=lambda x: -x.success_rate)
    
    def analyze_timeframe_performance(self) -> list[LearningInsight]:
        """
        Analyze accuracy by prediction timeframe.
        
        Identifies if short-term vs long-term predictions differ in accuracy.
        """
        insights = []
        timeframe_stats = defaultdict(lambda: {"correct": 0, "total": 0})
        
        for pred in self.predictions:
            if pred.prediction_id not in self.correctness:
                continue
            
            if pred.date_made and pred.check_date:
                days = (pred.check_date - pred.date_made).days
                if days <= 7:
                    timeframe = "short_term"
                elif days <= 14:
                    timeframe = "medium_term"
                else:
                    timeframe = "long_term"
            else:
                timeframe = "unknown"
            
            timeframe_stats[timeframe]["total"] += 1
            if self.correctness[pred.prediction_id]:
                timeframe_stats[timeframe]["correct"] += 1
        
        for timeframe, stats in timeframe_stats.items():
            if stats["total"] < 2:
                continue
            
            success_rate = safe_divide(stats["correct"], stats["total"])
            
            if timeframe == "short_term":
                interpretation = f"Short-term predictions ({success_rate:.0%} accurate)"
            elif timeframe == "medium_term":
                interpretation = f"Medium-term predictions ({success_rate:.0%} accurate)"
            else:
                interpretation = f"Long-term predictions ({success_rate:.0%} accurate)"
            
            insights.append(LearningInsight(
                category="timeframe",
                pattern=timeframe,
                success_rate=success_rate,
                sample_size=stats["total"],
                interpretation=interpretation,
            ))
        
        return sorted(insights, key=lambda x: -x.success_rate)


def discover_patterns(
    predictions: list[ExpiredPrediction],
    outcomes: list[ResolvedOutcome],
) -> list[LearningInsight]:
    """
    Discover all patterns from prediction outcomes.
    
    Main entry point for pattern discovery.
    
    Args:
        predictions: List of expired predictions
        outcomes: List of resolved outcomes
    
    Returns:
        List of LearningInsight objects with discovered patterns
    
    v1.1: Insights are now ranked by reliability_score (n * |success_rate - 0.5|)
    """
    analyzer = PatternAnalyzer(predictions, outcomes)
    
    all_insights = []
    
    # Run all analyses
    all_insights.extend(analyzer.analyze_mechanism_performance())
    all_insights.extend(analyzer.analyze_category_performance())
    all_insights.extend(analyzer.analyze_entity_type_performance())
    all_insights.extend(analyzer.analyze_confidence_calibration())
    all_insights.extend(analyzer.analyze_direction_performance())
    all_insights.extend(analyzer.analyze_timeframe_performance())
    
    # v1.1: Sort by reliability_score (prioritize reliable learnings)
    all_insights.sort(key=lambda x: -x.reliability_score)
    
    return all_insights


def get_reliable_insights(
    insights: list[LearningInsight],
    min_strength: str = "moderate",
) -> list[LearningInsight]:
    """
    v1.1: Filter insights by minimum strength level.
    
    Args:
        insights: All discovered insights
        min_strength: Minimum strength ("weak", "moderate", "strong")
    
    Returns:
        Filtered list of insights meeting the strength threshold
    """
    strength_order = {"weak": 0, "moderate": 1, "strong": 2}
    min_level = strength_order.get(min_strength, 0)
    
    return [
        i for i in insights
        if strength_order.get(i.insight_strength, 0) >= min_level
    ]


def get_top_performers(insights: list[LearningInsight], n: int = 5) -> list[LearningInsight]:
    """Get the top N performing patterns."""
    # Filter for high confidence (enough samples)
    high_conf = [i for i in insights if i.confidence_level in ("medium", "high")]
    return sorted(high_conf, key=lambda x: (-x.success_rate, -x.sample_size))[:n]


def get_worst_performers(insights: list[LearningInsight], n: int = 5) -> list[LearningInsight]:
    """Get the worst N performing patterns."""
    high_conf = [i for i in insights if i.confidence_level in ("medium", "high")]
    return sorted(high_conf, key=lambda x: (x.success_rate, -x.sample_size))[:n]


def get_overconfident_areas(insights: list[LearningInsight]) -> list[LearningInsight]:
    """Get areas where we're overconfident."""
    return [
        i for i in insights 
        if i.category == "calibration" and "overconfident" in i.interpretation.lower()
    ]


def get_underconfident_areas(insights: list[LearningInsight]) -> list[LearningInsight]:
    """Get areas where we're underconfident."""
    return [
        i for i in insights 
        if i.category == "calibration" and "underconfident" in i.interpretation.lower()
    ]
