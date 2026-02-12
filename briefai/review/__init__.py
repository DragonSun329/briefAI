"""
briefAI Prediction Review System

A post-mortem learning engine that analyzes expired predictions
and teaches the system what it is good and bad at predicting.

v1.1: Added explainability, unclear bucketing, sample-size protection, suggestions.
v1.2: Added config_patch generation for Learning Loop integration.
"""

from .models import (
    ExpiredPrediction,
    ResolvedOutcome,
    ReviewMetrics,
    LearningInsight,
    ReviewResult,
    Suggestion,
    UnclearReason,
    OutcomeStatus,
    Direction,
)
from .expired_predictions import find_expired_predictions
from .outcome_resolver import resolve_outcome
from .metrics import compute_metrics
from .patterns import discover_patterns
from .lessons import synthesize_lessons
from .suggestions import generate_suggestions
from .config_patch import generate_config_patches, load_patch_document, validate_patch

__all__ = [
    "ExpiredPrediction",
    "ResolvedOutcome",
    "ReviewMetrics",
    "LearningInsight",
    "ReviewResult",
    "Suggestion",
    "UnclearReason",
    "OutcomeStatus",
    "Direction",
    "find_expired_predictions",
    "resolve_outcome",
    "compute_metrics",
    "discover_patterns",
    "synthesize_lessons",
    "generate_suggestions",
    "generate_config_patches",
    "load_patch_document",
    "validate_patch",
]
