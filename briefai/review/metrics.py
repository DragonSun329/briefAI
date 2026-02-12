"""
Review Metrics Computation

Calculates accuracy, calibration, and performance metrics
from resolved predictions.

v1.1: Added unclear_rate, unclear_breakdown, accuracy_excluding_unclear
"""

from datetime import date, timedelta
from typing import Optional

from .models import (
    ExpiredPrediction,
    ResolvedOutcome,
    ReviewMetrics,
    OutcomeStatus,
    Direction,
    UnclearReason,
)


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division with default for zero denominator."""
    return numerator / denominator if denominator > 0 else default


def compute_overall_accuracy(
    outcomes: list[ResolvedOutcome],
) -> tuple[float, int, int]:
    """
    Compute overall accuracy.
    
    Returns (accuracy, correct_count, incorrect_count)
    """
    correct = sum(1 for o in outcomes if o.outcome == OutcomeStatus.CORRECT)
    incorrect = sum(1 for o in outcomes if o.outcome == OutcomeStatus.INCORRECT)
    total = correct + incorrect  # Exclude unclear
    
    accuracy = safe_divide(correct, total)
    return accuracy, correct, incorrect


def compute_unclear_breakdown(outcomes: list[ResolvedOutcome]) -> dict:
    """
    v1.1: Compute unclear rate and breakdown by reason.
    
    Returns dict with:
    - unclear_rate: proportion of unclear outcomes
    - unclear_breakdown: {UnclearReason -> count}
    """
    total = len(outcomes)
    unclear_outcomes = [o for o in outcomes if o.outcome == OutcomeStatus.UNCLEAR]
    unclear_count = len(unclear_outcomes)
    
    # Count by reason
    breakdown = {
        UnclearReason.DATA_MISSING.value: 0,
        UnclearReason.MIXED_EVIDENCE.value: 0,
        UnclearReason.LOW_SIGNAL.value: 0,
    }
    
    for o in unclear_outcomes:
        reason = o.unclear_reason
        if reason and reason != UnclearReason.NONE:
            breakdown[reason.value] = breakdown.get(reason.value, 0) + 1
    
    return {
        "unclear_rate": safe_divide(unclear_count, total),
        "unclear_count": unclear_count,
        "unclear_breakdown": breakdown,
    }


def compute_direction_accuracy(
    predictions: list[ExpiredPrediction],
    outcomes: list[ResolvedOutcome],
) -> dict:
    """
    Compute accuracy broken down by prediction direction.
    
    Returns dict with bullish/bearish accuracy and counts.
    """
    # Create outcome lookup
    outcome_map = {o.prediction_id: o for o in outcomes}
    
    bullish_correct = 0
    bullish_total = 0
    bearish_correct = 0
    bearish_total = 0
    
    for pred in predictions:
        outcome = outcome_map.get(pred.prediction_id)
        if not outcome or outcome.outcome == OutcomeStatus.UNCLEAR:
            continue
        
        if pred.direction == Direction.UP:
            bullish_total += 1
            if outcome.outcome == OutcomeStatus.CORRECT:
                bullish_correct += 1
        elif pred.direction == Direction.DOWN:
            bearish_total += 1
            if outcome.outcome == OutcomeStatus.CORRECT:
                bearish_correct += 1
    
    return {
        "bullish_accuracy": safe_divide(bullish_correct, bullish_total),
        "bullish_count": bullish_total,
        "bearish_accuracy": safe_divide(bearish_correct, bearish_total),
        "bearish_count": bearish_total,
    }


def compute_confidence_accuracy(
    predictions: list[ExpiredPrediction],
    outcomes: list[ResolvedOutcome],
) -> dict:
    """
    Compute accuracy broken down by confidence level.
    
    High: > 0.8
    Medium: 0.5 - 0.8
    Low: < 0.5
    """
    outcome_map = {o.prediction_id: o for o in outcomes}
    
    buckets = {
        "high": {"correct": 0, "total": 0},
        "medium": {"correct": 0, "total": 0},
        "low": {"correct": 0, "total": 0},
    }
    
    for pred in predictions:
        outcome = outcome_map.get(pred.prediction_id)
        if not outcome or outcome.outcome == OutcomeStatus.UNCLEAR:
            continue
        
        # Determine bucket
        if pred.confidence > 0.8:
            bucket = "high"
        elif pred.confidence >= 0.5:
            bucket = "medium"
        else:
            bucket = "low"
        
        buckets[bucket]["total"] += 1
        if outcome.outcome == OutcomeStatus.CORRECT:
            buckets[bucket]["correct"] += 1
    
    return {
        "high_confidence_accuracy": safe_divide(
            buckets["high"]["correct"], buckets["high"]["total"]
        ),
        "high_confidence_count": buckets["high"]["total"],
        "medium_confidence_accuracy": safe_divide(
            buckets["medium"]["correct"], buckets["medium"]["total"]
        ),
        "medium_confidence_count": buckets["medium"]["total"],
        "low_confidence_accuracy": safe_divide(
            buckets["low"]["correct"], buckets["low"]["total"]
        ),
        "low_confidence_count": buckets["low"]["total"],
    }


def compute_calibration(
    predictions: list[ExpiredPrediction],
    outcomes: list[ResolvedOutcome],
    bucket_size: float = 0.1,
) -> tuple[float, dict]:
    """
    Compute calibration error and bucket-level calibration.
    
    Calibration measures how well confidence aligns with actual correctness.
    Perfect calibration: 80% confident predictions are correct 80% of the time.
    
    Returns (mean_calibration_error, calibration_buckets)
    """
    outcome_map = {o.prediction_id: o for o in outcomes}
    
    # Initialize buckets: 0.0-0.1, 0.1-0.2, ..., 0.9-1.0
    buckets = {}
    for i in range(10):
        lower = i * bucket_size
        upper = lower + bucket_size
        key = f"{lower:.1f}-{upper:.1f}"
        buckets[key] = {"total": 0, "correct": 0, "avg_confidence": 0.0}
    
    # Fill buckets
    for pred in predictions:
        outcome = outcome_map.get(pred.prediction_id)
        if not outcome or outcome.outcome == OutcomeStatus.UNCLEAR:
            continue
        
        # Find bucket
        bucket_idx = min(int(pred.confidence * 10), 9)
        lower = bucket_idx * bucket_size
        upper = lower + bucket_size
        key = f"{lower:.1f}-{upper:.1f}"
        
        buckets[key]["total"] += 1
        if outcome.outcome == OutcomeStatus.CORRECT:
            buckets[key]["correct"] += 1
        buckets[key]["avg_confidence"] += pred.confidence
    
    # Calculate calibration error
    total_error = 0.0
    total_samples = 0
    
    for key, data in buckets.items():
        if data["total"] == 0:
            continue
        
        actual_accuracy = data["correct"] / data["total"]
        avg_confidence = data["avg_confidence"] / data["total"]
        data["actual_accuracy"] = actual_accuracy
        data["avg_confidence"] = avg_confidence
        
        # Weighted calibration error
        error = abs(avg_confidence - actual_accuracy)
        total_error += error * data["total"]
        total_samples += data["total"]
    
    mean_calibration_error = safe_divide(total_error, total_samples)
    
    return mean_calibration_error, buckets


def compute_time_to_resolution(
    predictions: list[ExpiredPrediction],
) -> float:
    """
    Compute average time from prediction to check date.
    
    This is essentially the average timeframe of predictions.
    """
    if not predictions:
        return 0.0
    
    total_days = 0
    count = 0
    
    for pred in predictions:
        if pred.date_made and pred.check_date:
            delta = (pred.check_date - pred.date_made).days
            total_days += delta
            count += 1
    
    return safe_divide(total_days, count)


def compute_metrics(
    predictions: list[ExpiredPrediction],
    outcomes: list[ResolvedOutcome],
) -> ReviewMetrics:
    """
    Compute all metrics from predictions and outcomes.
    
    Main entry point for metrics computation.
    
    Args:
        predictions: List of expired predictions
        outcomes: List of resolved outcomes
    
    Returns:
        ReviewMetrics with all computed values
    
    v1.1: Added unclear_rate, unclear_breakdown, accuracy_excluding_unclear
    """
    # Overall accuracy
    accuracy, correct, incorrect = compute_overall_accuracy(outcomes)
    
    # v1.1: Unclear breakdown
    unclear_stats = compute_unclear_breakdown(outcomes)
    unclear_count = unclear_stats["unclear_count"]
    
    # Direction breakdown
    direction_stats = compute_direction_accuracy(predictions, outcomes)
    
    # Confidence breakdown
    confidence_stats = compute_confidence_accuracy(predictions, outcomes)
    
    # Calibration
    calibration_error, calibration_buckets = compute_calibration(predictions, outcomes)
    
    # Time analysis
    avg_time = compute_time_to_resolution(predictions)
    
    return ReviewMetrics(
        total_predictions=len(predictions),
        total_resolved=len(outcomes) - unclear_count,
        total_unclear=unclear_count,
        
        overall_accuracy=accuracy,
        overall_correct=correct,
        overall_incorrect=incorrect,
        
        # v1.1: Unclear analysis
        unclear_rate=unclear_stats["unclear_rate"],
        unclear_breakdown=unclear_stats["unclear_breakdown"],
        accuracy_excluding_unclear=accuracy,  # Same as overall (excluded by design)
        
        bullish_accuracy=direction_stats["bullish_accuracy"],
        bullish_count=direction_stats["bullish_count"],
        bearish_accuracy=direction_stats["bearish_accuracy"],
        bearish_count=direction_stats["bearish_count"],
        
        high_confidence_accuracy=confidence_stats["high_confidence_accuracy"],
        high_confidence_count=confidence_stats["high_confidence_count"],
        medium_confidence_accuracy=confidence_stats["medium_confidence_accuracy"],
        medium_confidence_count=confidence_stats["medium_confidence_count"],
        low_confidence_accuracy=confidence_stats["low_confidence_accuracy"],
        low_confidence_count=confidence_stats["low_confidence_count"],
        
        calibration_error=calibration_error,
        calibration_buckets=calibration_buckets,
        
        avg_time_to_resolution_days=avg_time,
    )


def format_metrics_summary(metrics: ReviewMetrics) -> str:
    """
    Format metrics as a human-readable summary.
    """
    lines = [
        "## Metrics Summary",
        "",
        f"**Total Predictions:** {metrics.total_predictions}",
        f"**Resolved:** {metrics.total_resolved} | **Unclear:** {metrics.total_unclear}",
        "",
        "### Overall Accuracy",
        f"- **Accuracy:** {metrics.overall_accuracy:.1%}",
        f"- Correct: {metrics.overall_correct} | Incorrect: {metrics.overall_incorrect}",
        "",
        "### By Direction",
        f"- Bullish: {metrics.bullish_accuracy:.1%} ({metrics.bullish_count} predictions)",
        f"- Bearish: {metrics.bearish_accuracy:.1%} ({metrics.bearish_count} predictions)",
        "",
        "### By Confidence Level",
        f"- High (>0.8): {metrics.high_confidence_accuracy:.1%} ({metrics.high_confidence_count} predictions)",
        f"- Medium (0.5-0.8): {metrics.medium_confidence_accuracy:.1%} ({metrics.medium_confidence_count} predictions)",
        f"- Low (<0.5): {metrics.low_confidence_accuracy:.1%} ({metrics.low_confidence_count} predictions)",
        "",
        "### Calibration",
        f"- **Mean Calibration Error:** {metrics.calibration_error:.3f}",
        f"- Avg Resolution Time: {metrics.avg_time_to_resolution_days:.1f} days",
    ]
    
    return "\n".join(lines)
