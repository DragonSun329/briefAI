"""
Data models for the prediction review system.

All models are dataclasses for determinism and testability.

v1.1: Added explainability fields (debug_features, decision_trace, unclear_reason)
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class OutcomeStatus(Enum):
    """Possible prediction outcomes."""
    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNCLEAR = "unclear"


class Direction(Enum):
    """Prediction direction."""
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


class UnclearReason(Enum):
    """
    Reasons why an outcome was marked unclear.
    
    v1.1: Provides actionable explanation for unclear outcomes.
    """
    DATA_MISSING = "data_missing"  # No signal data available for the entity/period
    MIXED_EVIDENCE = "mixed_evidence"  # Conflicting signals, can't determine direction
    LOW_SIGNAL = "low_signal"  # Signals exist but too weak to make determination
    NONE = "none"  # Not unclear (outcome was resolved)


@dataclass
class ExpiredPrediction:
    """
    A prediction whose check_date has passed and needs review.
    """
    prediction_id: str
    entity: str
    direction: Direction
    confidence: float
    check_date: date
    hypothesis_text: str
    evidence_refs: list[str] = field(default_factory=list)
    
    # Original prediction context
    mechanism: str = ""
    category: str = ""
    concept_name: str = ""
    canonical_metric: str = ""
    date_made: date = None
    hypothesis_id: str = ""
    
    def __post_init__(self):
        if isinstance(self.direction, str):
            self.direction = Direction(self.direction) if self.direction in [d.value for d in Direction] else Direction.UNKNOWN


@dataclass
class SupportingEvidence:
    """Evidence that supports an outcome determination."""
    source: str
    signal_type: str
    date: str
    description: str
    relevance_score: float = 0.0


@dataclass
class ResolvedOutcome:
    """
    The determined outcome of a prediction.
    
    v1.1: Added explainability fields for debugging and transparency.
    """
    prediction_id: str
    outcome: OutcomeStatus
    confidence_score: float
    supporting_evidence: list[SupportingEvidence] = field(default_factory=list)
    resolution_method: str = ""
    
    # v1.1 Explainability fields
    debug_features: dict = field(default_factory=dict)  # feature -> normalized score
    decision_trace: list[str] = field(default_factory=list)  # human-readable steps
    unclear_reason: UnclearReason = UnclearReason.NONE
    
    def __post_init__(self):
        if isinstance(self.outcome, str):
            self.outcome = OutcomeStatus(self.outcome)
        if isinstance(self.unclear_reason, str):
            self.unclear_reason = UnclearReason(self.unclear_reason) if self.unclear_reason in [r.value for r in UnclearReason] else UnclearReason.NONE
    
    @property
    def is_correct(self) -> bool:
        return self.outcome == OutcomeStatus.CORRECT
    
    @property
    def is_incorrect(self) -> bool:
        return self.outcome == OutcomeStatus.INCORRECT
    
    @property
    def is_unclear(self) -> bool:
        return self.outcome == OutcomeStatus.UNCLEAR


@dataclass
class ReviewMetrics:
    """
    Aggregate accuracy metrics for a review period.
    
    v1.1: Added unclear_rate and unclear_breakdown for actionable diagnostics.
    """
    total_predictions: int = 0
    total_resolved: int = 0
    total_unclear: int = 0
    
    # Core accuracy
    overall_accuracy: float = 0.0
    overall_correct: int = 0
    overall_incorrect: int = 0
    
    # v1.1: Unclear analysis
    unclear_rate: float = 0.0  # unclear / total
    unclear_breakdown: dict = field(default_factory=dict)  # UnclearReason -> count
    accuracy_excluding_unclear: float = 0.0  # same as overall_accuracy but explicit
    
    # Direction breakdown
    bullish_accuracy: float = 0.0
    bullish_count: int = 0
    bearish_accuracy: float = 0.0
    bearish_count: int = 0
    
    # Confidence breakdown
    high_confidence_accuracy: float = 0.0  # >0.8
    high_confidence_count: int = 0
    medium_confidence_accuracy: float = 0.0  # 0.5-0.8
    medium_confidence_count: int = 0
    low_confidence_accuracy: float = 0.0  # <0.5
    low_confidence_count: int = 0
    
    # Calibration
    calibration_error: float = 0.0  # Mean |confidence - actual|
    calibration_buckets: dict = field(default_factory=dict)
    
    # Time analysis
    avg_time_to_resolution_days: float = 0.0


@dataclass
class LearningInsight:
    """
    A discovered pattern from prediction analysis.
    
    v1.1: Added insight_strength and reliability_score for sample-size protection.
    """
    category: str  # e.g., "source", "mechanism", "entity_type"
    pattern: str  # e.g., "arxiv", "product_launch", "hyperscaler"
    success_rate: float
    sample_size: int
    interpretation: str
    confidence_level: str = "low"  # low, medium, high based on sample_size
    
    # v1.1: Sample-size protection
    insight_strength: str = "weak"  # weak (<5), moderate (5-9), strong (>=10)
    reliability_score: float = 0.0  # n * |success_rate - 0.5| for ranking
    
    def __post_init__(self):
        # Determine confidence level based on sample size
        if self.sample_size >= 20:
            self.confidence_level = "high"
        elif self.sample_size >= 10:
            self.confidence_level = "medium"
        else:
            self.confidence_level = "low"
        
        # v1.1: Determine insight strength
        if self.sample_size >= 10:
            self.insight_strength = "strong"
        elif self.sample_size >= 5:
            self.insight_strength = "moderate"
        else:
            self.insight_strength = "weak"
        
        # v1.1: Calculate reliability score for ranking
        # Higher = more reliable and more informative (far from 50%)
        self.reliability_score = self.sample_size * abs(self.success_rate - 0.5)


@dataclass
class Lesson:
    """
    A synthesized lesson from patterns.
    
    v1.1: Added sample_size and success_rate for transparency.
    """
    lesson_text: str
    supporting_patterns: list[str] = field(default_factory=list)
    priority: str = "normal"  # low, normal, high
    actionable: bool = False
    
    # v1.1: Sample-size protection
    sample_size: int = 0
    success_rate: float = 0.0
    insight_strength: str = "weak"  # weak, moderate, strong


@dataclass
class Suggestion:
    """
    An actionable suggestion for system improvement.
    
    v1.1: New model for non-automatic suggestions.
    """
    suggestion_id: str
    target: str  # e.g., confidence_cap, mechanism_weight, media_only_threshold, check_date_policy
    rationale: str  # Must cite which pattern triggered it
    proposed_change: dict = field(default_factory=dict)  # Structured change
    safety: str = "manual_review_required"  # Always manual - never auto-apply
    
    # Context
    source_pattern: str = ""
    source_category: str = ""
    sample_size: int = 0
    success_rate: float = 0.0


@dataclass
class ReviewResult:
    """
    Complete review output for a given period.
    
    v1.1: Added suggestions list and updated review_version.
    """
    experiment_id: str
    review_date: date
    period_start: date
    period_end: date
    
    # Core data
    expired_predictions: list[ExpiredPrediction] = field(default_factory=list)
    resolved_outcomes: list[ResolvedOutcome] = field(default_factory=list)
    
    # Analysis
    metrics: ReviewMetrics = field(default_factory=ReviewMetrics)
    insights: list[LearningInsight] = field(default_factory=list)
    lessons: list[Lesson] = field(default_factory=list)
    
    # v1.1: Actionable suggestions
    suggestions: list[Suggestion] = field(default_factory=list)
    
    # Metadata
    generation_timestamp: str = ""
    review_version: str = "1.1.0"
