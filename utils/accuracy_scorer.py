"""
Accuracy Scorer

Calculates prediction accuracy metrics including:
- Simple accuracy (correct/total)
- Brier score (calibration quality)
- Accuracy by signal type, entity type, prediction type
- Confidence calibration analysis
- Historical accuracy trends

The goal: know which signals to trust and by how much.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from .prediction_store import (
    Prediction, PredictionStore, PredictionType, PredictionStatus, PredictionMode
)


@dataclass
class AccuracyBucket:
    """Accuracy stats for a confidence bucket."""
    bucket_min: float
    bucket_max: float
    predictions: int = 0
    correct: int = 0
    avg_confidence: float = 0.0
    
    @property
    def accuracy(self) -> float:
        return self.correct / self.predictions if self.predictions > 0 else 0.0
    
    @property
    def calibration_error(self) -> float:
        """How far off is accuracy from confidence?"""
        return abs(self.accuracy - self.avg_confidence)


@dataclass
class SignalAccuracyReport:
    """Accuracy report for a specific signal type."""
    signal_type: str
    total_predictions: int = 0
    correct: int = 0
    incorrect: int = 0
    pending: int = 0
    
    # Accuracy metrics
    accuracy: float = 0.0
    brier_score: float = 0.0
    
    # Confidence stats
    avg_confidence: float = 0.0
    avg_confidence_correct: float = 0.0
    avg_confidence_incorrect: float = 0.0
    
    # By prediction type
    by_prediction_type: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Calibration buckets
    calibration_buckets: List[AccuracyBucket] = field(default_factory=list)


@dataclass  
class AccuracyReport:
    """Complete accuracy report."""
    generated_at: datetime = field(default_factory=datetime.utcnow)
    report_period_start: Optional[datetime] = None
    report_period_end: Optional[datetime] = None
    mode: Optional[str] = None
    
    # Overall stats
    total_predictions: int = 0
    resolved_predictions: int = 0
    correct: int = 0
    incorrect: int = 0
    pending: int = 0
    expired: int = 0
    
    # Overall metrics
    overall_accuracy: float = 0.0
    overall_brier_score: float = 0.0
    
    # By signal type
    by_signal_type: Dict[str, SignalAccuracyReport] = field(default_factory=dict)
    
    # By prediction type
    by_prediction_type: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Calibration
    calibration_buckets: List[AccuracyBucket] = field(default_factory=list)
    expected_calibration_error: float = 0.0
    
    # Top performers and underperformers
    top_signals: List[Dict[str, Any]] = field(default_factory=list)
    worst_signals: List[Dict[str, Any]] = field(default_factory=list)


class AccuracyScorer:
    """
    Calculates accuracy metrics for predictions.
    
    Key metrics:
    - Accuracy: Simple correct/total ratio
    - Brier Score: Measures calibration (lower is better, 0 is perfect)
      BS = (1/N) * Σ(confidence - outcome)²
      where outcome is 1 if correct, 0 if incorrect
    - Calibration Error: How well confidence predicts accuracy
    """
    
    # Confidence bucket boundaries
    BUCKET_BOUNDARIES = [0.0, 0.3, 0.5, 0.7, 0.85, 1.0]
    
    def __init__(self, prediction_store: Optional[PredictionStore] = None):
        self.prediction_store = prediction_store or PredictionStore()
    
    def calculate_brier_score(self, predictions: List[Prediction]) -> float:
        """
        Calculate Brier score for a set of predictions.
        
        Brier Score = (1/N) * Σ(confidence - outcome)²
        
        Lower is better:
        - 0.0 = perfect calibration
        - 0.25 = random guessing at 50% confidence
        - 1.0 = perfectly wrong
        
        Args:
            predictions: Resolved predictions
            
        Returns:
            Brier score (0 to 1)
        """
        if not predictions:
            return 0.0
        
        # Filter to only resolved predictions
        resolved = [
            p for p in predictions 
            if p.status in (PredictionStatus.CORRECT, PredictionStatus.INCORRECT)
        ]
        
        if not resolved:
            return 0.0
        
        total_error = 0.0
        for pred in resolved:
            outcome = 1.0 if pred.status == PredictionStatus.CORRECT else 0.0
            error = (pred.confidence - outcome) ** 2
            total_error += error
        
        return total_error / len(resolved)
    
    def calculate_calibration_buckets(
        self,
        predictions: List[Prediction],
    ) -> List[AccuracyBucket]:
        """
        Calculate accuracy per confidence bucket.
        
        Good calibration means:
        - 70% confident predictions are correct ~70% of the time
        - 90% confident predictions are correct ~90% of the time
        
        Args:
            predictions: Resolved predictions
            
        Returns:
            List of AccuracyBucket objects
        """
        # Filter to resolved
        resolved = [
            p for p in predictions
            if p.status in (PredictionStatus.CORRECT, PredictionStatus.INCORRECT)
        ]
        
        # Create buckets
        buckets = []
        for i in range(len(self.BUCKET_BOUNDARIES) - 1):
            bucket = AccuracyBucket(
                bucket_min=self.BUCKET_BOUNDARIES[i],
                bucket_max=self.BUCKET_BOUNDARIES[i + 1],
            )
            buckets.append(bucket)
        
        # Assign predictions to buckets
        for pred in resolved:
            for bucket in buckets:
                if bucket.bucket_min <= pred.confidence < bucket.bucket_max:
                    bucket.predictions += 1
                    if pred.status == PredictionStatus.CORRECT:
                        bucket.correct += 1
                    # Running average for confidence
                    if bucket.predictions == 1:
                        bucket.avg_confidence = pred.confidence
                    else:
                        bucket.avg_confidence = (
                            (bucket.avg_confidence * (bucket.predictions - 1) + pred.confidence)
                            / bucket.predictions
                        )
                    break
        
        return buckets
    
    def calculate_expected_calibration_error(
        self,
        buckets: List[AccuracyBucket],
    ) -> float:
        """
        Calculate Expected Calibration Error (ECE).
        
        ECE = Σ(n_bucket/n_total) * |accuracy - confidence|
        
        Lower is better. Measures how well confidence predicts accuracy.
        """
        total_predictions = sum(b.predictions for b in buckets)
        if total_predictions == 0:
            return 0.0
        
        ece = 0.0
        for bucket in buckets:
            if bucket.predictions > 0:
                weight = bucket.predictions / total_predictions
                ece += weight * bucket.calibration_error
        
        return ece
    
    def generate_report(
        self,
        mode: Optional[PredictionMode] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> AccuracyReport:
        """
        Generate a complete accuracy report.
        
        Args:
            mode: Filter by prediction mode
            since: Start of report period
            until: End of report period
            
        Returns:
            AccuracyReport with all metrics
        """
        report = AccuracyReport(
            report_period_start=since,
            report_period_end=until,
            mode=mode.value if mode else None,
        )
        
        # Get all predictions
        all_predictions = self._get_predictions(mode, since, until)
        
        if not all_predictions:
            return report
        
        # Count by status
        for pred in all_predictions:
            report.total_predictions += 1
            if pred.status == PredictionStatus.CORRECT:
                report.correct += 1
            elif pred.status == PredictionStatus.INCORRECT:
                report.incorrect += 1
            elif pred.status == PredictionStatus.PENDING:
                report.pending += 1
            elif pred.status == PredictionStatus.EXPIRED:
                report.expired += 1
        
        report.resolved_predictions = report.correct + report.incorrect
        
        # Calculate overall metrics
        if report.resolved_predictions > 0:
            report.overall_accuracy = report.correct / report.resolved_predictions
        
        resolved = [
            p for p in all_predictions
            if p.status in (PredictionStatus.CORRECT, PredictionStatus.INCORRECT)
        ]
        
        report.overall_brier_score = self.calculate_brier_score(resolved)
        report.calibration_buckets = self.calculate_calibration_buckets(resolved)
        report.expected_calibration_error = self.calculate_expected_calibration_error(
            report.calibration_buckets
        )
        
        # Calculate by signal type
        by_signal = defaultdict(list)
        for pred in all_predictions:
            by_signal[pred.signal_type].append(pred)
        
        for signal_type, preds in by_signal.items():
            signal_report = self._calculate_signal_report(signal_type, preds)
            report.by_signal_type[signal_type] = signal_report
        
        # Calculate by prediction type
        by_pred_type = defaultdict(list)
        for pred in resolved:
            by_pred_type[pred.prediction_type.value].append(pred)
        
        for pred_type, preds in by_pred_type.items():
            correct = sum(1 for p in preds if p.status == PredictionStatus.CORRECT)
            accuracy = correct / len(preds) if preds else 0
            report.by_prediction_type[pred_type] = {
                "total": len(preds),
                "correct": correct,
                "accuracy": accuracy,
                "brier_score": self.calculate_brier_score(preds),
            }
        
        # Find top and worst signals (by accuracy, min 5 predictions)
        signal_stats = []
        for signal_type, signal_report in report.by_signal_type.items():
            if signal_report.total_predictions >= 5:
                signal_stats.append({
                    "signal_type": signal_type,
                    "accuracy": signal_report.accuracy,
                    "total": signal_report.total_predictions,
                    "brier_score": signal_report.brier_score,
                })
        
        signal_stats.sort(key=lambda x: x["accuracy"], reverse=True)
        report.top_signals = signal_stats[:5]
        report.worst_signals = signal_stats[-5:][::-1]
        
        return report
    
    def _get_predictions(
        self,
        mode: Optional[PredictionMode],
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> List[Prediction]:
        """Get predictions with filters."""
        # Get all resolved predictions
        resolved = self.prediction_store.get_resolved_predictions(
            since=since,
            mode=mode,
        )
        
        # Get pending predictions
        pending = self.prediction_store.get_pending_predictions(
            past_horizon_only=False,
            mode=mode,
        )
        
        all_predictions = resolved + pending
        
        # Filter by until date if specified
        if until:
            all_predictions = [
                p for p in all_predictions
                if p.predicted_at <= until
            ]
        
        return all_predictions
    
    def _calculate_signal_report(
        self,
        signal_type: str,
        predictions: List[Prediction],
    ) -> SignalAccuracyReport:
        """Calculate accuracy report for a signal type."""
        report = SignalAccuracyReport(signal_type=signal_type)
        
        correct_confidences = []
        incorrect_confidences = []
        
        for pred in predictions:
            report.total_predictions += 1
            
            if pred.status == PredictionStatus.CORRECT:
                report.correct += 1
                correct_confidences.append(pred.confidence)
            elif pred.status == PredictionStatus.INCORRECT:
                report.incorrect += 1
                incorrect_confidences.append(pred.confidence)
            elif pred.status == PredictionStatus.PENDING:
                report.pending += 1
        
        resolved_count = report.correct + report.incorrect
        if resolved_count > 0:
            report.accuracy = report.correct / resolved_count
        
        # Confidence stats
        all_confidences = correct_confidences + incorrect_confidences
        if all_confidences:
            report.avg_confidence = sum(all_confidences) / len(all_confidences)
        if correct_confidences:
            report.avg_confidence_correct = sum(correct_confidences) / len(correct_confidences)
        if incorrect_confidences:
            report.avg_confidence_incorrect = sum(incorrect_confidences) / len(incorrect_confidences)
        
        # Brier score
        resolved = [
            p for p in predictions
            if p.status in (PredictionStatus.CORRECT, PredictionStatus.INCORRECT)
        ]
        report.brier_score = self.calculate_brier_score(resolved)
        
        # By prediction type
        by_type = defaultdict(lambda: {"total": 0, "correct": 0})
        for pred in resolved:
            by_type[pred.prediction_type.value]["total"] += 1
            if pred.status == PredictionStatus.CORRECT:
                by_type[pred.prediction_type.value]["correct"] += 1
        
        for pred_type, stats in by_type.items():
            stats["accuracy"] = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
            report.by_prediction_type[pred_type] = stats
        
        # Calibration buckets
        report.calibration_buckets = self.calculate_calibration_buckets(resolved)
        
        return report
    
    def format_report(self, report: AccuracyReport) -> str:
        """
        Format accuracy report as human-readable text.
        
        Args:
            report: AccuracyReport to format
            
        Returns:
            Formatted string
        """
        lines = [
            "=" * 70,
            "PREDICTION ACCURACY REPORT",
            "=" * 70,
            f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        
        if report.report_period_start or report.report_period_end:
            period = f"{report.report_period_start or 'start'} to {report.report_period_end or 'now'}"
            lines.append(f"Period: {period}")
        
        if report.mode:
            lines.append(f"Mode: {report.mode}")
        
        lines.extend([
            "",
            "─" * 70,
            "OVERALL STATISTICS",
            "─" * 70,
            f"Total Predictions: {report.total_predictions}",
            f"  • Resolved: {report.resolved_predictions}",
            f"    - Correct: {report.correct}",
            f"    - Incorrect: {report.incorrect}",
            f"  • Pending: {report.pending}",
            f"  • Expired: {report.expired}",
            "",
            f"Overall Accuracy: {report.overall_accuracy:.1%}",
            f"Brier Score: {report.overall_brier_score:.4f} (lower is better, 0 = perfect)",
            f"Expected Calibration Error: {report.expected_calibration_error:.4f}",
            "",
        ])
        
        # Calibration analysis
        lines.extend([
            "─" * 70,
            "CALIBRATION ANALYSIS",
            "─" * 70,
            "How well does confidence predict accuracy?",
            "",
            f"{'Confidence Range':<20} {'Predictions':<12} {'Accuracy':<12} {'Calibration'}",
            "-" * 60,
        ])
        
        for bucket in report.calibration_buckets:
            if bucket.predictions > 0:
                conf_range = f"{bucket.bucket_min:.0%}-{bucket.bucket_max:.0%}"
                acc = f"{bucket.accuracy:.1%}"
                expected = f"{bucket.avg_confidence:.1%}"
                error = bucket.calibration_error
                
                # Show if over/under confident
                if error < 0.05:
                    cal = "✓ Well calibrated"
                elif bucket.accuracy < bucket.avg_confidence:
                    cal = f"↑ Overconfident by {error:.0%}"
                else:
                    cal = f"↓ Underconfident by {error:.0%}"
                
                lines.append(f"{conf_range:<20} {bucket.predictions:<12} {acc:<12} {cal}")
        
        # By signal type
        if report.by_signal_type:
            lines.extend([
                "",
                "─" * 70,
                "ACCURACY BY SIGNAL TYPE",
                "─" * 70,
                "",
                f"{'Signal Type':<25} {'Total':<8} {'Accuracy':<12} {'Brier':<10} {'Status'}",
                "-" * 65,
            ])
            
            sorted_signals = sorted(
                report.by_signal_type.items(),
                key=lambda x: x[1].accuracy,
                reverse=True
            )
            
            for signal_type, signal_report in sorted_signals:
                if signal_report.correct + signal_report.incorrect > 0:
                    status = self._get_signal_status(signal_report)
                    lines.append(
                        f"{signal_type:<25} {signal_report.total_predictions:<8} "
                        f"{signal_report.accuracy:<12.1%} {signal_report.brier_score:<10.4f} {status}"
                    )
        
        # By prediction type
        if report.by_prediction_type:
            lines.extend([
                "",
                "─" * 70,
                "ACCURACY BY PREDICTION TYPE",
                "─" * 70,
                "",
            ])
            
            for pred_type, stats in sorted(report.by_prediction_type.items()):
                lines.append(
                    f"  {pred_type.upper():<12}: {stats['accuracy']:.1%} "
                    f"({stats['correct']}/{stats['total']} correct)"
                )
        
        # Top and worst signals
        if report.top_signals:
            lines.extend([
                "",
                "─" * 70,
                "TOP PERFORMING SIGNALS (min 5 predictions)",
                "─" * 70,
            ])
            for i, sig in enumerate(report.top_signals, 1):
                lines.append(
                    f"  {i}. {sig['signal_type']}: {sig['accuracy']:.1%} "
                    f"({sig['total']} predictions)"
                )
        
        if report.worst_signals:
            lines.extend([
                "",
                "UNDERPERFORMING SIGNALS",
            ])
            for i, sig in enumerate(report.worst_signals, 1):
                lines.append(
                    f"  {i}. {sig['signal_type']}: {sig['accuracy']:.1%} "
                    f"({sig['total']} predictions)"
                )
        
        lines.extend(["", "=" * 70])
        
        return "\n".join(lines)
    
    def _get_signal_status(self, signal_report: SignalAccuracyReport) -> str:
        """Get status emoji/text for a signal."""
        if signal_report.accuracy >= 0.7:
            return "🟢 Strong"
        elif signal_report.accuracy >= 0.5:
            return "🟡 Moderate"
        elif signal_report.accuracy >= 0.3:
            return "🟠 Weak"
        else:
            return "🔴 Poor"
    
    def get_signal_recommendation(
        self,
        signal_type: str,
        min_predictions: int = 10,
    ) -> Dict[str, Any]:
        """
        Get recommendation for a signal type based on accuracy.
        
        Returns dict with:
        - should_use: bool
        - confidence_adjustment: float (multiply user's confidence by this)
        - reason: str
        """
        predictions = self.prediction_store.get_predictions_by_signal_type(signal_type)
        
        resolved = [
            p for p in predictions
            if p.status in (PredictionStatus.CORRECT, PredictionStatus.INCORRECT)
        ]
        
        if len(resolved) < min_predictions:
            return {
                "should_use": True,  # Not enough data to reject
                "confidence_adjustment": 0.7,  # But discount confidence
                "reason": f"Insufficient data ({len(resolved)} predictions, need {min_predictions})",
                "status": "insufficient_data",
            }
        
        accuracy = sum(1 for p in resolved if p.status == PredictionStatus.CORRECT) / len(resolved)
        brier = self.calculate_brier_score(resolved)
        
        if accuracy >= 0.65:
            return {
                "should_use": True,
                "confidence_adjustment": 1.0,
                "reason": f"Strong accuracy ({accuracy:.1%})",
                "status": "recommended",
            }
        elif accuracy >= 0.50:
            return {
                "should_use": True,
                "confidence_adjustment": 0.8,
                "reason": f"Moderate accuracy ({accuracy:.1%}), reduce confidence",
                "status": "use_with_caution",
            }
        elif accuracy >= 0.35:
            return {
                "should_use": False,
                "confidence_adjustment": 0.5,
                "reason": f"Weak accuracy ({accuracy:.1%}), shadow mode recommended",
                "status": "shadow_recommended",
            }
        else:
            return {
                "should_use": False,
                "confidence_adjustment": 0.0,
                "reason": f"Poor accuracy ({accuracy:.1%}), disable signal",
                "status": "disable_recommended",
            }


def compare_shadow_to_production(
    scorer: AccuracyScorer,
) -> Dict[str, Any]:
    """
    Compare shadow mode accuracy to production accuracy.
    
    This helps determine if a shadow signal is ready for production.
    """
    prod_report = scorer.generate_report(mode=PredictionMode.PRODUCTION)
    shadow_report = scorer.generate_report(mode=PredictionMode.SHADOW)
    
    return {
        "production": {
            "total": prod_report.total_predictions,
            "accuracy": prod_report.overall_accuracy,
            "brier_score": prod_report.overall_brier_score,
        },
        "shadow": {
            "total": shadow_report.total_predictions,
            "accuracy": shadow_report.overall_accuracy,
            "brier_score": shadow_report.overall_brier_score,
        },
        "shadow_better": (
            shadow_report.overall_accuracy > prod_report.overall_accuracy
            if shadow_report.resolved_predictions > 10 else None
        ),
        "recommendation": _get_graduation_recommendation(shadow_report),
    }


def _get_graduation_recommendation(shadow_report: AccuracyReport) -> str:
    """Get recommendation for graduating shadow signals to production."""
    if shadow_report.resolved_predictions < 20:
        return "Need more data (min 20 predictions)"
    
    if shadow_report.overall_accuracy >= 0.65:
        return "Ready for production"
    elif shadow_report.overall_accuracy >= 0.50:
        return "Consider partial graduation (highest confidence only)"
    else:
        return "Keep in shadow mode, needs improvement"


if __name__ == "__main__":
    # Quick test
    scorer = AccuracyScorer()
    report = scorer.generate_report()
    print(scorer.format_report(report))
