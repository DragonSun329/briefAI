"""
Calibration Engine - System Accuracy Metrics.

Part of briefAI Prediction Verification Engine.

This module computes calibration metrics to measure how well
the system's confidence scores align with actual outcomes.

Metrics computed:
- Accuracy: Fraction of correct predictions
- Precision: True positives / Predicted positives
- Recall: True positives / Actual positives
- Brier Score: Mean squared error of probability predictions
- Calibration Curve: Binned accuracy vs confidence

No LLM calls. Deterministic calculation.
"""

import json
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_METRICS_DIR = Path(__file__).parent.parent / "data" / "metrics"
DEFAULT_REPORT_FILE = "calibration_report.json"

# Confidence bins for calibration curve
CONFIDENCE_BINS = [
    (0.0, 0.2),
    (0.2, 0.4),
    (0.4, 0.6),
    (0.6, 0.8),
    (0.8, 1.0),
]


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class CalibrationBin:
    """A single bin in the calibration curve."""
    bin_start: float
    bin_end: float
    predicted_count: int
    actual_true_count: int
    mean_confidence: float
    actual_accuracy: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CalibrationReport:
    """Complete calibration report."""
    generated_at: str
    total_predictions: int
    evaluated_predictions: int
    
    # Verdict counts
    verified_true: int
    verified_false: int
    inconclusive: int
    data_missing: int
    
    # Core metrics
    accuracy: float                      # Correct / Total evaluated
    precision: float                     # True positives / Predicted positives
    recall: float                        # True positives / Actual positives
    brier_score: float                   # Mean squared error
    
    # Calibration curve
    calibration_bins: List[Dict[str, Any]]
    
    # Breakdown by mechanism
    mechanism_accuracy: Dict[str, float]
    
    # Breakdown by category
    category_accuracy: Dict[str, float]
    
    # Breakdown by metric
    metric_accuracy: Dict[str, float]
    
    # Time series (optional)
    weekly_accuracy: Dict[str, float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        return result
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'CalibrationReport':
        return cls(**d)


# =============================================================================
# CALIBRATION CALCULATIONS
# =============================================================================

def calculate_accuracy(true_count: int, total: int) -> float:
    """Calculate accuracy with zero handling."""
    if total == 0:
        return 0.0
    return round(true_count / total, 4)


def calculate_precision(true_positives: int, predicted_positives: int) -> float:
    """Calculate precision with zero handling."""
    if predicted_positives == 0:
        return 0.0
    return round(true_positives / predicted_positives, 4)


def calculate_recall(true_positives: int, actual_positives: int) -> float:
    """Calculate recall with zero handling."""
    if actual_positives == 0:
        return 0.0
    return round(true_positives / actual_positives, 4)


def calculate_brier_score(predictions: List[Tuple[float, float]]) -> float:
    """
    Calculate Brier score (mean squared error).
    
    Args:
        predictions: List of (predicted_probability, actual_outcome)
                    where actual_outcome is 1.0 (true) or 0.0 (false)
    
    Returns:
        Brier score (lower is better, 0.0 is perfect)
    """
    if not predictions:
        return 0.0
    
    mse = sum((p - a) ** 2 for p, a in predictions) / len(predictions)
    return round(mse, 4)


def build_calibration_curve(
    predictions: List[Tuple[float, float]],
    bins: List[Tuple[float, float]] = None,
) -> List[CalibrationBin]:
    """
    Build calibration curve from predictions.
    
    Args:
        predictions: List of (confidence, actual_outcome)
        bins: List of (start, end) tuples for binning
    
    Returns:
        List of CalibrationBin objects
    """
    if bins is None:
        bins = CONFIDENCE_BINS
    
    calibration_bins = []
    
    for bin_start, bin_end in bins:
        # Filter predictions in this bin
        in_bin = [
            (conf, actual) for conf, actual in predictions
            if bin_start <= conf < bin_end
        ]
        
        if not in_bin:
            calibration_bins.append(CalibrationBin(
                bin_start=bin_start,
                bin_end=bin_end,
                predicted_count=0,
                actual_true_count=0,
                mean_confidence=0.0,
                actual_accuracy=0.0,
            ))
            continue
        
        predicted_count = len(in_bin)
        actual_true_count = sum(1 for _, actual in in_bin if actual >= 0.5)
        mean_confidence = sum(conf for conf, _ in in_bin) / len(in_bin)
        actual_accuracy = actual_true_count / predicted_count
        
        calibration_bins.append(CalibrationBin(
            bin_start=bin_start,
            bin_end=bin_end,
            predicted_count=predicted_count,
            actual_true_count=actual_true_count,
            mean_confidence=round(mean_confidence, 4),
            actual_accuracy=round(actual_accuracy, 4),
        ))
    
    return calibration_bins


# =============================================================================
# CALIBRATION ENGINE
# =============================================================================

class CalibrationEngine:
    """
    Computes calibration metrics from prediction records.
    
    Processes evaluated predictions to produce accuracy,
    precision, recall, Brier score, and calibration curves.
    """
    
    def __init__(self, output_dir: Path = None):
        """Initialize calibration engine."""
        if output_dir is None:
            output_dir = DEFAULT_METRICS_DIR
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"CalibrationEngine initialized at {self.output_dir}")
    
    def compute_report(
        self,
        records: List[Dict[str, Any]],
    ) -> CalibrationReport:
        """
        Compute calibration report from prediction records.
        
        Args:
            records: List of PredictionRecord dicts
        
        Returns:
            CalibrationReport with all metrics
        """
        # Filter to evaluated records only
        evaluated = [
            r for r in records
            if r.get('status') == 'evaluated'
        ]
        
        # Count verdicts
        verdicts = defaultdict(int)
        for r in evaluated:
            verdicts[r.get('verdict', 'unknown')] += 1
        
        verified_true = verdicts.get('verified_true', 0)
        verified_false = verdicts.get('verified_false', 0)
        inconclusive = verdicts.get('inconclusive', 0)
        data_missing = verdicts.get('data_missing', 0)
        
        # Calculate core metrics
        # For accuracy, we only consider verified predictions
        verified_total = verified_true + verified_false
        accuracy = calculate_accuracy(verified_true, verified_total)
        
        # For precision/recall, treat verified_true as positive
        # Predicted positive = high confidence predictions (>0.5)
        high_conf = [r for r in evaluated if r.get('confidence_at_prediction', 0) > 0.5]
        high_conf_true = sum(1 for r in high_conf if r.get('verdict') == 'verified_true')
        
        precision = calculate_precision(high_conf_true, len(high_conf))
        recall = calculate_recall(verified_true, verified_total)
        
        # Brier score
        predictions_for_brier = []
        for r in evaluated:
            conf = r.get('confidence_at_prediction', 0.5)
            verdict = r.get('verdict')
            
            if verdict == 'verified_true':
                actual = 1.0
            elif verdict == 'verified_false':
                actual = 0.0
            else:
                continue  # Skip inconclusive/missing for Brier
            
            predictions_for_brier.append((conf, actual))
        
        brier_score = calculate_brier_score(predictions_for_brier)
        
        # Calibration curve
        calibration_bins = build_calibration_curve(predictions_for_brier)
        
        # Breakdown by mechanism
        mechanism_accuracy = self._compute_breakdown(evaluated, 'mechanism')
        
        # Breakdown by category
        category_accuracy = self._compute_breakdown(evaluated, 'category')
        
        # Breakdown by metric
        metric_accuracy = self._compute_breakdown(evaluated, 'canonical_metric')
        
        # Weekly accuracy
        weekly_accuracy = self._compute_weekly_accuracy(evaluated)
        
        return CalibrationReport(
            generated_at=datetime.now().isoformat(),
            total_predictions=len(records),
            evaluated_predictions=len(evaluated),
            verified_true=verified_true,
            verified_false=verified_false,
            inconclusive=inconclusive,
            data_missing=data_missing,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            brier_score=brier_score,
            calibration_bins=[b.to_dict() for b in calibration_bins],
            mechanism_accuracy=mechanism_accuracy,
            category_accuracy=category_accuracy,
            metric_accuracy=metric_accuracy,
            weekly_accuracy=weekly_accuracy,
        )
    
    def _compute_breakdown(
        self,
        records: List[Dict[str, Any]],
        key: str,
    ) -> Dict[str, float]:
        """Compute accuracy breakdown by a key field."""
        groups = defaultdict(list)
        
        for r in records:
            group = r.get(key, 'unknown')
            groups[group].append(r)
        
        result = {}
        for group, group_records in groups.items():
            verified_total = sum(
                1 for r in group_records
                if r.get('verdict') in ['verified_true', 'verified_false']
            )
            verified_true = sum(
                1 for r in group_records
                if r.get('verdict') == 'verified_true'
            )
            
            if verified_total > 0:
                result[group] = round(verified_true / verified_total, 4)
        
        return result
    
    def _compute_weekly_accuracy(
        self,
        records: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """Compute accuracy by week."""
        weeks = defaultdict(list)
        
        for r in records:
            evaluated_at = r.get('evaluated_at')
            if evaluated_at:
                try:
                    dt = datetime.fromisoformat(evaluated_at)
                    week_key = dt.strftime('%Y-W%W')
                    weeks[week_key].append(r)
                except Exception:
                    pass
        
        result = {}
        for week, week_records in sorted(weeks.items()):
            verified_total = sum(
                1 for r in week_records
                if r.get('verdict') in ['verified_true', 'verified_false']
            )
            verified_true = sum(
                1 for r in week_records
                if r.get('verdict') == 'verified_true'
            )
            
            if verified_total > 0:
                result[week] = round(verified_true / verified_total, 4)
        
        return result
    
    def save_report(self, report: CalibrationReport, filename: str = None) -> Path:
        """
        Save calibration report to file.
        
        Args:
            report: CalibrationReport to save
            filename: Optional filename (defaults to calibration_report.json)
        
        Returns:
            Path to saved file
        """
        if filename is None:
            filename = DEFAULT_REPORT_FILE
        
        output_path = self.output_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved calibration report to {output_path}")
        return output_path
    
    def load_report(self, filename: str = None) -> Optional[CalibrationReport]:
        """
        Load calibration report from file.
        
        Args:
            filename: Optional filename (defaults to calibration_report.json)
        
        Returns:
            CalibrationReport or None if not found
        """
        if filename is None:
            filename = DEFAULT_REPORT_FILE
        
        report_path = self.output_dir / filename
        
        if not report_path.exists():
            return None
        
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return CalibrationReport.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load calibration report: {e}")
            return None


# =============================================================================
# REPORT FORMATTING
# =============================================================================

def format_calibration_report(report: CalibrationReport) -> str:
    """
    Format calibration report for display.
    
    Args:
        report: CalibrationReport to format
    
    Returns:
        Formatted string for printing
    """
    lines = []
    
    lines.append("=" * 60)
    lines.append("CALIBRATION REPORT")
    lines.append("=" * 60)
    lines.append(f"Generated: {report.generated_at}")
    lines.append("")
    
    # Summary
    lines.append("SUMMARY")
    lines.append("-" * 40)
    lines.append(f"Total predictions: {report.total_predictions}")
    lines.append(f"Evaluated: {report.evaluated_predictions}")
    lines.append("")
    
    # Verdicts
    lines.append("VERDICTS")
    lines.append("-" * 40)
    lines.append(f"Verified True: {report.verified_true}")
    lines.append(f"Verified False: {report.verified_false}")
    lines.append(f"Inconclusive: {report.inconclusive}")
    lines.append(f"Data Missing: {report.data_missing}")
    lines.append("")
    
    # Core metrics
    lines.append("METRICS")
    lines.append("-" * 40)
    lines.append(f"Accuracy: {report.accuracy:.1%}")
    lines.append(f"Precision: {report.precision:.1%}")
    lines.append(f"Recall: {report.recall:.1%}")
    lines.append(f"Brier Score: {report.brier_score:.4f}")
    lines.append("")
    
    # Calibration curve
    lines.append("CALIBRATION CURVE")
    lines.append("-" * 40)
    lines.append(f"{'Confidence':<15} {'Count':<10} {'Accuracy':<10}")
    for bin_data in report.calibration_bins:
        bin_range = f"{bin_data['bin_start']:.1f}-{bin_data['bin_end']:.1f}"
        count = bin_data['predicted_count']
        acc = bin_data['actual_accuracy']
        lines.append(f"{bin_range:<15} {count:<10} {acc:.1%}")
    lines.append("")
    
    # Mechanism breakdown
    if report.mechanism_accuracy:
        lines.append("BY MECHANISM")
        lines.append("-" * 40)
        for mech, acc in sorted(report.mechanism_accuracy.items(), key=lambda x: -x[1]):
            lines.append(f"{mech:<30} {acc:.1%}")
        lines.append("")
    
    # Category breakdown
    if report.category_accuracy:
        lines.append("BY CATEGORY")
        lines.append("-" * 40)
        for cat, acc in sorted(report.category_accuracy.items(), key=lambda x: -x[1]):
            lines.append(f"{cat:<30} {acc:.1%}")
        lines.append("")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


# =============================================================================
# TESTS
# =============================================================================

def _test_accuracy():
    """Test accuracy calculation."""
    assert calculate_accuracy(8, 10) == 0.8
    assert calculate_accuracy(0, 10) == 0.0
    assert calculate_accuracy(10, 0) == 0.0
    
    print("[PASS] _test_accuracy")


def _test_brier_score():
    """Test Brier score calculation."""
    # Perfect predictions
    perfect = [(1.0, 1.0), (0.0, 0.0)]
    assert calculate_brier_score(perfect) == 0.0
    
    # Worst predictions
    worst = [(1.0, 0.0), (0.0, 1.0)]
    assert calculate_brier_score(worst) == 1.0
    
    # Mixed
    mixed = [(0.8, 1.0), (0.2, 0.0)]
    assert calculate_brier_score(mixed) == 0.04
    
    print("[PASS] _test_brier_score")


def _test_calibration_curve():
    """Test calibration curve building."""
    predictions = [
        (0.1, 0.0),  # Low confidence, false
        (0.3, 0.0),  # Medium-low, false
        (0.7, 1.0),  # Medium-high, true
        (0.9, 1.0),  # High confidence, true
    ]
    
    curve = build_calibration_curve(predictions)
    
    assert len(curve) == 5
    assert curve[0].predicted_count == 1  # 0.0-0.2 bin
    assert curve[4].actual_accuracy == 1.0  # 0.8-1.0 bin
    
    print("[PASS] _test_calibration_curve")


def run_tests():
    """Run all calibration tests."""
    print("\n=== CALIBRATION ENGINE TESTS ===\n")
    
    _test_accuracy()
    _test_brier_score()
    _test_calibration_curve()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
