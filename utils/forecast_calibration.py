"""
Forecast Calibration v1.0 - The Real Moat.

Part of briefAI Phase 3: Calibration.

This is the most important feature: measuring and improving forecast accuracy.

You can measure: predicted confidence vs real outcome

Metrics computed:
- Brier score: Mean squared error of probability predictions
- Reliability curve: Predicted probability vs actual outcome by bin
- Overconfidence penalty: How much system overestimates
- Per-mechanism accuracy: Which mechanisms predict best

Then automatically adjust: confidence_calibration_factor

Result: The system learns how trustworthy it is.

This is the difference between: news aggregator vs forecasting engine.
"""

import json
import math
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
DEFAULT_CALIBRATION_FILE = "calibration_state.json"

# Number of bins for reliability curve
RELIABILITY_BINS = 10

# Minimum samples for reliable calibration
MIN_SAMPLES_FOR_CALIBRATION = 20


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class CalibrationBin:
    """A single bin in the reliability curve."""
    bin_start: float
    bin_end: float
    predicted_mean: float
    actual_rate: float
    sample_count: int
    
    @property
    def calibration_error(self) -> float:
        """Absolute error between predicted and actual."""
        return abs(self.predicted_mean - self.actual_rate)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CalibrationState:
    """Complete calibration state for the system."""
    
    # Metadata
    last_updated: str
    sample_count: int
    
    # Overall metrics
    brier_score: float
    overconfidence_penalty: float
    calibration_error: float  # Mean absolute calibration error
    
    # Calibration factor (multiply raw confidence by this)
    global_calibration_factor: float
    
    # Per-mechanism calibration
    mechanism_calibration: Dict[str, Dict[str, float]]
    
    # Reliability curve
    reliability_curve: List[Dict[str, Any]]
    
    # Recent history
    weekly_brier_scores: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'CalibrationState':
        return cls(**d)
    
    def apply_calibration(self, raw_confidence: float, mechanism: str = None) -> float:
        """
        Apply calibration to a raw confidence score.
        
        Args:
            raw_confidence: Original confidence
            mechanism: Optional mechanism for mechanism-specific calibration
        
        Returns:
            Calibrated confidence
        """
        if mechanism and mechanism in self.mechanism_calibration:
            factor = self.mechanism_calibration[mechanism].get(
                'calibration_factor',
                self.global_calibration_factor
            )
        else:
            factor = self.global_calibration_factor
        
        calibrated = raw_confidence * factor
        return max(0.0, min(1.0, calibrated))


# =============================================================================
# CALIBRATION CALCULATOR
# =============================================================================

def calculate_brier_score(predictions: List[Tuple[float, float]]) -> float:
    """
    Calculate Brier score (mean squared error).
    
    Args:
        predictions: List of (predicted_probability, actual_outcome)
                    where actual is 1.0 (true) or 0.0 (false)
    
    Returns:
        Brier score (lower is better, 0.0 is perfect)
    """
    if not predictions:
        return 0.0
    
    mse = sum((p - a) ** 2 for p, a in predictions) / len(predictions)
    return round(mse, 4)


def calculate_overconfidence_penalty(predictions: List[Tuple[float, float]]) -> float:
    """
    Calculate overconfidence penalty.
    
    Measures how much the system overestimates its accuracy.
    Positive = overconfident, Negative = underconfident.
    
    Args:
        predictions: List of (predicted, actual)
    
    Returns:
        Overconfidence penalty (0.0 is well-calibrated)
    """
    if not predictions:
        return 0.0
    
    avg_predicted = sum(p for p, _ in predictions) / len(predictions)
    avg_actual = sum(a for _, a in predictions) / len(predictions)
    
    return round(avg_predicted - avg_actual, 4)


def build_reliability_curve(
    predictions: List[Tuple[float, float]],
    num_bins: int = RELIABILITY_BINS,
) -> List[CalibrationBin]:
    """
    Build reliability curve (calibration plot data).
    
    Groups predictions into bins by confidence and compares
    predicted probability to actual outcome rate.
    
    Args:
        predictions: List of (predicted, actual)
        num_bins: Number of bins
    
    Returns:
        List of CalibrationBin objects
    """
    bins = []
    bin_size = 1.0 / num_bins
    
    for i in range(num_bins):
        bin_start = i * bin_size
        bin_end = (i + 1) * bin_size
        
        # Get predictions in this bin
        in_bin = [
            (p, a) for p, a in predictions
            if bin_start <= p < bin_end or (i == num_bins - 1 and p == 1.0)
        ]
        
        if not in_bin:
            bins.append(CalibrationBin(
                bin_start=round(bin_start, 2),
                bin_end=round(bin_end, 2),
                predicted_mean=round((bin_start + bin_end) / 2, 2),
                actual_rate=0.0,
                sample_count=0,
            ))
            continue
        
        predicted_mean = sum(p for p, _ in in_bin) / len(in_bin)
        actual_rate = sum(a for _, a in in_bin) / len(in_bin)
        
        bins.append(CalibrationBin(
            bin_start=round(bin_start, 2),
            bin_end=round(bin_end, 2),
            predicted_mean=round(predicted_mean, 4),
            actual_rate=round(actual_rate, 4),
            sample_count=len(in_bin),
        ))
    
    return bins


def calculate_calibration_factor(
    reliability_curve: List[CalibrationBin],
) -> float:
    """
    Calculate optimal calibration factor from reliability curve.
    
    If system is overconfident, factor < 1.0
    If system is underconfident, factor > 1.0
    
    Args:
        reliability_curve: List of CalibrationBin
    
    Returns:
        Calibration factor to multiply raw confidence by
    """
    # Weighted regression of predicted vs actual
    total_weight = 0
    weighted_ratio_sum = 0
    
    for bin_data in reliability_curve:
        if bin_data.sample_count == 0 or bin_data.predicted_mean == 0:
            continue
        
        weight = bin_data.sample_count
        ratio = bin_data.actual_rate / bin_data.predicted_mean
        
        weighted_ratio_sum += weight * ratio
        total_weight += weight
    
    if total_weight == 0:
        return 1.0
    
    factor = weighted_ratio_sum / total_weight
    
    # Clamp to reasonable range
    factor = max(0.5, min(1.5, factor))
    
    return round(factor, 4)


def calculate_mechanism_accuracy(
    predictions: List[Dict[str, Any]],
) -> Dict[str, Dict[str, float]]:
    """
    Calculate per-mechanism accuracy metrics.
    
    Args:
        predictions: List of prediction records with 'mechanism' field
    
    Returns:
        Dict of mechanism -> {accuracy, brier_score, calibration_factor, count}
    """
    # Group by mechanism
    by_mechanism: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    
    for pred in predictions:
        mechanism = pred.get('mechanism', 'unknown')
        confidence = pred.get('confidence_at_prediction', 0.5)
        verdict = pred.get('verdict', '')
        
        if verdict == 'verified_true':
            actual = 1.0
        elif verdict == 'verified_false':
            actual = 0.0
        else:
            continue  # Skip inconclusive
        
        by_mechanism[mechanism].append((confidence, actual))
    
    # Calculate metrics for each
    result = {}
    
    for mechanism, preds in by_mechanism.items():
        if not preds:
            continue
        
        brier = calculate_brier_score(preds)
        overconf = calculate_overconfidence_penalty(preds)
        
        # Calculate accuracy
        correct = sum(1 for p, a in preds if (p >= 0.5 and a == 1) or (p < 0.5 and a == 0))
        accuracy = correct / len(preds) if preds else 0.0
        
        # Calculate calibration factor
        curve = build_reliability_curve(preds, num_bins=5)  # Fewer bins for mechanism
        factor = calculate_calibration_factor(curve)
        
        result[mechanism] = {
            'accuracy': round(accuracy, 4),
            'brier_score': brier,
            'overconfidence': overconf,
            'calibration_factor': factor,
            'sample_count': len(preds),
        }
    
    return result


# =============================================================================
# CALIBRATION ENGINE
# =============================================================================

class ForecastCalibrator:
    """
    Computes and maintains forecast calibration.
    
    This is the core of forecast reliability measurement.
    """
    
    def __init__(self, data_dir: Path = None):
        """Initialize calibrator."""
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.state_file = self.data_dir / "metrics" / DEFAULT_CALIBRATION_FILE
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.state: Optional[CalibrationState] = None
        self._load_state()
        
        logger.debug(f"ForecastCalibrator initialized at {self.data_dir}")
    
    def _load_state(self):
        """Load calibration state from file."""
        if not self.state_file.exists():
            self.state = None
            return
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.state = CalibrationState.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load calibration state: {e}")
            self.state = None
    
    def _save_state(self):
        """Save calibration state to file."""
        if self.state is None:
            return
        
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state.to_dict(), f, indent=2)
        
        logger.debug(f"Saved calibration state")
    
    def compute_calibration(
        self,
        prediction_records: List[Dict[str, Any]],
    ) -> CalibrationState:
        """
        Compute calibration from prediction records.
        
        Args:
            prediction_records: List of evaluated prediction records
        
        Returns:
            CalibrationState with all metrics
        """
        # Filter to evaluated predictions with clear verdicts
        evaluated = [
            r for r in prediction_records
            if r.get('verdict') in ['verified_true', 'verified_false']
        ]
        
        if len(evaluated) < MIN_SAMPLES_FOR_CALIBRATION:
            logger.warning(
                f"Only {len(evaluated)} samples, need {MIN_SAMPLES_FOR_CALIBRATION} for calibration"
            )
        
        # Build predictions list
        predictions = []
        for r in evaluated:
            confidence = r.get('confidence_at_prediction', 0.5)
            actual = 1.0 if r.get('verdict') == 'verified_true' else 0.0
            predictions.append((confidence, actual))
        
        # Calculate overall metrics
        brier_score = calculate_brier_score(predictions)
        overconfidence = calculate_overconfidence_penalty(predictions)
        
        # Build reliability curve
        reliability_curve = build_reliability_curve(predictions)
        
        # Calculate mean calibration error
        weighted_error = sum(
            b.calibration_error * b.sample_count
            for b in reliability_curve
            if b.sample_count > 0
        )
        total_samples = sum(b.sample_count for b in reliability_curve)
        calibration_error = weighted_error / total_samples if total_samples > 0 else 0.0
        
        # Calculate global calibration factor
        calibration_factor = calculate_calibration_factor(reliability_curve)
        
        # Calculate per-mechanism accuracy
        mechanism_calibration = calculate_mechanism_accuracy(prediction_records)
        
        # Build state
        self.state = CalibrationState(
            last_updated=datetime.now().isoformat(),
            sample_count=len(evaluated),
            brier_score=brier_score,
            overconfidence_penalty=overconfidence,
            calibration_error=round(calibration_error, 4),
            global_calibration_factor=calibration_factor,
            mechanism_calibration=mechanism_calibration,
            reliability_curve=[b.to_dict() for b in reliability_curve],
        )
        
        # Save state
        self._save_state()
        
        logger.info(
            f"Computed calibration: Brier={brier_score:.4f}, "
            f"Factor={calibration_factor:.2f}, "
            f"Samples={len(evaluated)}"
        )
        
        return self.state
    
    def get_calibrated_confidence(
        self,
        raw_confidence: float,
        mechanism: str = None,
    ) -> float:
        """
        Get calibrated confidence from raw confidence.
        
        Args:
            raw_confidence: Original confidence
            mechanism: Optional mechanism for mechanism-specific calibration
        
        Returns:
            Calibrated confidence
        """
        if self.state is None:
            return raw_confidence
        
        return self.state.apply_calibration(raw_confidence, mechanism)
    
    def get_calibration_summary(self) -> Dict[str, Any]:
        """Get calibration summary for display."""
        if self.state is None:
            return {
                'status': 'not_computed',
                'sample_count': 0,
            }
        
        return {
            'status': 'computed',
            'last_updated': self.state.last_updated,
            'sample_count': self.state.sample_count,
            'brier_score': self.state.brier_score,
            'calibration_factor': self.state.global_calibration_factor,
            'overconfidence': self.state.overconfidence_penalty,
            'best_mechanism': self._get_best_mechanism(),
            'worst_mechanism': self._get_worst_mechanism(),
        }
    
    def _get_best_mechanism(self) -> Optional[str]:
        """Get the most accurate mechanism."""
        if not self.state or not self.state.mechanism_calibration:
            return None
        
        best = max(
            self.state.mechanism_calibration.items(),
            key=lambda x: x[1].get('accuracy', 0),
        )
        return best[0] if best[1].get('accuracy', 0) > 0 else None
    
    def _get_worst_mechanism(self) -> Optional[str]:
        """Get the least accurate mechanism."""
        if not self.state or not self.state.mechanism_calibration:
            return None
        
        worst = min(
            self.state.mechanism_calibration.items(),
            key=lambda x: x[1].get('accuracy', 1),
        )
        return worst[0] if worst[1].get('accuracy', 1) < 1 else None


# =============================================================================
# BRIEF SECTION GENERATOR
# =============================================================================

def generate_calibration_section(state: Optional[CalibrationState]) -> str:
    """
    Generate the Calibration section for analyst brief.
    
    Args:
        state: CalibrationState or None
    
    Returns:
        Formatted markdown section
    """
    lines = []
    lines.append("## System Calibration")
    lines.append("")
    
    if state is None:
        lines.append("*Calibration not yet computed. Need more evaluated predictions.*")
        lines.append("")
        return "\n".join(lines)
    
    # Overall metrics
    lines.append(f"**Last Updated:** {state.last_updated[:10]}")
    lines.append(f"**Sample Size:** {state.sample_count} predictions")
    lines.append("")
    
    # Brier score interpretation
    brier = state.brier_score
    if brier < 0.1:
        quality = "Excellent"
    elif brier < 0.2:
        quality = "Good"
    elif brier < 0.3:
        quality = "Fair"
    else:
        quality = "Poor"
    
    lines.append(f"**Forecast Quality:** {quality} (Brier score: {brier:.3f})")
    lines.append("")
    
    # Calibration
    factor = state.global_calibration_factor
    if factor < 0.9:
        cal_status = "Overconfident - reducing raw confidence"
    elif factor > 1.1:
        cal_status = "Underconfident - increasing raw confidence"
    else:
        cal_status = "Well-calibrated"
    
    lines.append(f"**Calibration:** {cal_status} (factor: {factor:.2f})")
    lines.append("")
    
    # Mechanism accuracy
    if state.mechanism_calibration:
        lines.append("**Mechanism Accuracy:**")
        
        sorted_mechs = sorted(
            state.mechanism_calibration.items(),
            key=lambda x: x[1].get('accuracy', 0),
            reverse=True,
        )
        
        for mechanism, metrics in sorted_mechs[:5]:
            acc = metrics.get('accuracy', 0)
            count = metrics.get('sample_count', 0)
            lines.append(f"- {mechanism}: {acc:.0%} ({count} samples)")
        
        lines.append("")
    
    return "\n".join(lines)


# =============================================================================
# TESTS
# =============================================================================

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


def _test_overconfidence():
    """Test overconfidence calculation."""
    # Overconfident: predicts 0.8, actually 0.5
    overconf = [(0.8, 1.0), (0.8, 0.0)]
    penalty = calculate_overconfidence_penalty(overconf)
    assert penalty > 0  # Overconfident
    
    # Underconfident: predicts 0.3, actually 0.7
    underconf = [(0.3, 1.0), (0.3, 1.0), (0.3, 0.0)]
    penalty = calculate_overconfidence_penalty(underconf)
    assert penalty < 0  # Underconfident
    
    print("[PASS] _test_overconfidence")


def _test_reliability_curve():
    """Test reliability curve building."""
    predictions = [
        (0.1, 0.0),
        (0.2, 0.0),
        (0.3, 0.0),
        (0.7, 1.0),
        (0.8, 1.0),
        (0.9, 1.0),
    ]
    
    curve = build_reliability_curve(predictions, num_bins=5)
    
    assert len(curve) == 5
    # Low confidence bins should have low actual rate
    assert curve[0].actual_rate <= 0.5
    # High confidence bins should have high actual rate
    assert curve[4].actual_rate >= 0.5
    
    print("[PASS] _test_reliability_curve")


def _test_calibration_factor():
    """Test calibration factor calculation."""
    # Overconfident: predicts high, actually low
    overconf_curve = [
        CalibrationBin(0.6, 0.8, 0.7, 0.5, 10),  # Predicts 0.7, actually 0.5
        CalibrationBin(0.8, 1.0, 0.9, 0.7, 10),  # Predicts 0.9, actually 0.7
    ]
    
    factor = calculate_calibration_factor(overconf_curve)
    assert factor < 1.0  # Should reduce confidence
    
    print("[PASS] _test_calibration_factor")


def run_tests():
    """Run all calibration tests."""
    print("\n=== FORECAST CALIBRATION TESTS ===\n")
    
    _test_brier_score()
    _test_overconfidence()
    _test_reliability_curve()
    _test_calibration_factor()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
