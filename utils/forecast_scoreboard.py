"""
Forecast Scoreboard v1.0 - Public Accuracy Metrics.

This is the single feature that determines if briefAI lives or dies.

Without this → you are a newsletter.
With this → you are a forecaster.

This is how prediction markets gain credibility.

Shows:
- Predictions evaluated
- Correct / Incorrect / Inconclusive
- Calibration by confidence level
- Brier score
- Lead time metrics
"""

import json
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


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class CalibrationBucket:
    """Calibration for a confidence range."""
    confidence_range: str  # e.g., "70-80%"
    confidence_min: float
    confidence_max: float
    predictions_count: int
    correct_count: int
    actual_rate: float
    
    @property
    def is_well_calibrated(self) -> bool:
        """True if actual rate is within 5% of confidence midpoint."""
        midpoint = (self.confidence_min + self.confidence_max) / 2
        return abs(self.actual_rate - midpoint) <= 0.05


@dataclass
class MechanismScore:
    """Accuracy for a specific mechanism."""
    mechanism: str
    predictions_count: int
    correct_count: int
    accuracy: float
    avg_confidence: float
    overconfidence: float  # avg_confidence - accuracy
    
    @property
    def reliability(self) -> str:
        """Reliability rating."""
        if self.accuracy >= 0.80:
            return "High"
        elif self.accuracy >= 0.65:
            return "Medium"
        elif self.accuracy >= 0.50:
            return "Low"
        else:
            return "Unreliable"


@dataclass
class LeadTimeMetric:
    """Lead time measurement for a prediction."""
    prediction_id: str
    hypothesis_title: str
    prediction_date: str
    mainstream_coverage_date: Optional[str]
    lead_time_days: Optional[int]
    
    @property
    def has_lead_time(self) -> bool:
        return self.lead_time_days is not None


@dataclass
class ForecastScoreboard:
    """Complete forecast scoreboard."""
    
    # Metadata
    generated_at: str
    period_days: int
    
    # Core metrics
    total_predictions: int
    evaluated_predictions: int
    correct_predictions: int
    incorrect_predictions: int
    inconclusive_predictions: int
    
    # Accuracy
    overall_accuracy: float
    brier_score: float
    
    # Calibration
    calibration_buckets: List[CalibrationBucket]
    calibration_score: float  # Mean absolute calibration error
    
    # Mechanism breakdown
    mechanism_scores: List[MechanismScore]
    
    # Lead time
    avg_lead_time_days: Optional[float]
    lead_time_samples: List[LeadTimeMetric]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "period_days": self.period_days,
            "total_predictions": self.total_predictions,
            "evaluated_predictions": self.evaluated_predictions,
            "correct_predictions": self.correct_predictions,
            "incorrect_predictions": self.incorrect_predictions,
            "inconclusive_predictions": self.inconclusive_predictions,
            "overall_accuracy": self.overall_accuracy,
            "brier_score": self.brier_score,
            "calibration_buckets": [
                {
                    "range": b.confidence_range,
                    "count": b.predictions_count,
                    "correct": b.correct_count,
                    "actual_rate": b.actual_rate,
                }
                for b in self.calibration_buckets
            ],
            "calibration_score": self.calibration_score,
            "mechanism_scores": [asdict(m) for m in self.mechanism_scores],
            "avg_lead_time_days": self.avg_lead_time_days,
        }
    
    def format_markdown(self) -> str:
        """Format scoreboard as markdown."""
        lines = []
        
        lines.append("## Forecast Scoreboard")
        lines.append("")
        lines.append(f"*System performance over last {self.period_days} days*")
        lines.append("")
        
        # Core metrics
        lines.append("### Performance Summary")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Predictions Evaluated | {self.evaluated_predictions} |")
        lines.append(f"| Correct | {self.correct_predictions} |")
        lines.append(f"| Incorrect | {self.incorrect_predictions} |")
        lines.append(f"| Inconclusive | {self.inconclusive_predictions} |")
        lines.append(f"| **Overall Accuracy** | **{self.overall_accuracy:.0%}** |")
        lines.append(f"| Brier Score | {self.brier_score:.3f} |")
        lines.append("")
        
        # Calibration
        if self.calibration_buckets:
            lines.append("### Calibration by Confidence")
            lines.append("")
            lines.append("| Confidence | Predictions | Correct | Actual Rate |")
            lines.append("|------------|-------------|---------|-------------|")
            
            for bucket in self.calibration_buckets:
                if bucket.predictions_count > 0:
                    well_cal = "✓" if bucket.is_well_calibrated else ""
                    lines.append(
                        f"| {bucket.confidence_range} | {bucket.predictions_count} | "
                        f"{bucket.correct_count} | {bucket.actual_rate:.0%} {well_cal}|"
                    )
            
            lines.append("")
            lines.append(f"*Calibration Score: {self.calibration_score:.3f} (lower is better)*")
            lines.append("")
        
        # Mechanism accuracy
        if self.mechanism_scores:
            lines.append("### Accuracy by Mechanism")
            lines.append("")
            lines.append("| Mechanism | Accuracy | Count | Reliability |")
            lines.append("|-----------|----------|-------|-------------|")
            
            for score in sorted(self.mechanism_scores, key=lambda x: x.accuracy, reverse=True):
                lines.append(
                    f"| {score.mechanism.replace('_', ' ')} | {score.accuracy:.0%} | "
                    f"{score.predictions_count} | {score.reliability} |"
                )
            
            lines.append("")
        
        # Lead time
        if self.avg_lead_time_days is not None:
            lines.append("### Signal Lead Time")
            lines.append("")
            lines.append(f"**Average Lead Time:** {self.avg_lead_time_days:.1f} days before mainstream coverage")
            lines.append("")
            
            if self.lead_time_samples:
                lines.append("Recent examples:")
                for sample in self.lead_time_samples[:5]:
                    if sample.has_lead_time:
                        lines.append(
                            f"- {sample.hypothesis_title}: detected {sample.prediction_date}, "
                            f"mainstream {sample.mainstream_coverage_date} "
                            f"(**{sample.lead_time_days} day lead**)"
                        )
                lines.append("")
        
        return "\n".join(lines)


# =============================================================================
# SCOREBOARD GENERATOR
# =============================================================================

class ScoreboardGenerator:
    """Generates forecast scoreboards from prediction data."""
    
    def __init__(self, data_dir: Path = None):
        """Initialize generator."""
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
    
    def generate(
        self,
        predictions: List[Dict[str, Any]],
        period_days: int = 30,
        lead_time_data: List[Dict] = None,
    ) -> ForecastScoreboard:
        """
        Generate a forecast scoreboard.
        
        Args:
            predictions: List of prediction records
            period_days: Period for the scoreboard
            lead_time_data: Optional lead time measurements
        
        Returns:
            ForecastScoreboard
        """
        # Filter to evaluated predictions
        evaluated = [
            p for p in predictions
            if p.get("status") == "evaluated"
            and p.get("verdict") in ["verified_true", "verified_false", "inconclusive"]
        ]
        
        # Count by verdict
        correct = sum(1 for p in evaluated if p.get("verdict") == "verified_true")
        incorrect = sum(1 for p in evaluated if p.get("verdict") == "verified_false")
        inconclusive = sum(1 for p in evaluated if p.get("verdict") == "inconclusive")
        
        # Calculate accuracy (exclude inconclusive)
        decisive = correct + incorrect
        accuracy = correct / decisive if decisive > 0 else 0.0
        
        # Calculate Brier score
        brier = self._calculate_brier_score(evaluated)
        
        # Build calibration buckets
        calibration_buckets = self._build_calibration_buckets(evaluated)
        calibration_score = self._calculate_calibration_score(calibration_buckets)
        
        # Build mechanism scores
        mechanism_scores = self._build_mechanism_scores(evaluated)
        
        # Process lead time data
        avg_lead_time = None
        lead_time_samples = []
        
        if lead_time_data:
            lead_times = [d["lead_time_days"] for d in lead_time_data if d.get("lead_time_days")]
            if lead_times:
                avg_lead_time = sum(lead_times) / len(lead_times)
            
            lead_time_samples = [
                LeadTimeMetric(
                    prediction_id=d.get("prediction_id", ""),
                    hypothesis_title=d.get("hypothesis_title", ""),
                    prediction_date=d.get("prediction_date", ""),
                    mainstream_coverage_date=d.get("mainstream_coverage_date"),
                    lead_time_days=d.get("lead_time_days"),
                )
                for d in lead_time_data
            ]
        
        return ForecastScoreboard(
            generated_at=datetime.now().isoformat(),
            period_days=period_days,
            total_predictions=len(predictions),
            evaluated_predictions=len(evaluated),
            correct_predictions=correct,
            incorrect_predictions=incorrect,
            inconclusive_predictions=inconclusive,
            overall_accuracy=round(accuracy, 4),
            brier_score=round(brier, 4),
            calibration_buckets=calibration_buckets,
            calibration_score=round(calibration_score, 4),
            mechanism_scores=mechanism_scores,
            avg_lead_time_days=avg_lead_time,
            lead_time_samples=lead_time_samples,
        )
    
    def _calculate_brier_score(self, predictions: List[Dict]) -> float:
        """Calculate Brier score."""
        if not predictions:
            return 0.0
        
        mse_sum = 0.0
        count = 0
        
        for p in predictions:
            confidence = p.get("confidence_at_prediction", 0.5)
            verdict = p.get("verdict")
            
            if verdict == "verified_true":
                actual = 1.0
            elif verdict == "verified_false":
                actual = 0.0
            else:
                continue
            
            mse_sum += (confidence - actual) ** 2
            count += 1
        
        return mse_sum / count if count > 0 else 0.0
    
    def _build_calibration_buckets(self, predictions: List[Dict]) -> List[CalibrationBucket]:
        """Build calibration buckets by confidence level."""
        # Define buckets
        bucket_ranges = [
            (0.5, 0.6, "50-60%"),
            (0.6, 0.7, "60-70%"),
            (0.7, 0.8, "70-80%"),
            (0.8, 0.9, "80-90%"),
            (0.9, 1.0, "90-100%"),
        ]
        
        buckets = []
        
        for min_conf, max_conf, label in bucket_ranges:
            # Filter predictions in this range
            in_bucket = [
                p for p in predictions
                if min_conf <= p.get("confidence_at_prediction", 0) < max_conf
                and p.get("verdict") in ["verified_true", "verified_false"]
            ]
            
            if not in_bucket:
                buckets.append(CalibrationBucket(
                    confidence_range=label,
                    confidence_min=min_conf,
                    confidence_max=max_conf,
                    predictions_count=0,
                    correct_count=0,
                    actual_rate=0.0,
                ))
                continue
            
            correct = sum(1 for p in in_bucket if p.get("verdict") == "verified_true")
            actual_rate = correct / len(in_bucket)
            
            buckets.append(CalibrationBucket(
                confidence_range=label,
                confidence_min=min_conf,
                confidence_max=max_conf,
                predictions_count=len(in_bucket),
                correct_count=correct,
                actual_rate=round(actual_rate, 4),
            ))
        
        return buckets
    
    def _calculate_calibration_score(self, buckets: List[CalibrationBucket]) -> float:
        """Calculate mean absolute calibration error."""
        total_error = 0.0
        total_count = 0
        
        for bucket in buckets:
            if bucket.predictions_count == 0:
                continue
            
            midpoint = (bucket.confidence_min + bucket.confidence_max) / 2
            error = abs(bucket.actual_rate - midpoint)
            
            total_error += error * bucket.predictions_count
            total_count += bucket.predictions_count
        
        return total_error / total_count if total_count > 0 else 0.0
    
    def _build_mechanism_scores(self, predictions: List[Dict]) -> List[MechanismScore]:
        """Build accuracy scores by mechanism."""
        # Group by mechanism
        by_mechanism: Dict[str, List[Dict]] = defaultdict(list)
        
        for p in predictions:
            mechanism = p.get("mechanism", "unknown")
            if p.get("verdict") in ["verified_true", "verified_false"]:
                by_mechanism[mechanism].append(p)
        
        scores = []
        
        for mechanism, preds in by_mechanism.items():
            if not preds:
                continue
            
            correct = sum(1 for p in preds if p.get("verdict") == "verified_true")
            accuracy = correct / len(preds)
            
            avg_conf = sum(p.get("confidence_at_prediction", 0.5) for p in preds) / len(preds)
            overconfidence = avg_conf - accuracy
            
            scores.append(MechanismScore(
                mechanism=mechanism,
                predictions_count=len(preds),
                correct_count=correct,
                accuracy=round(accuracy, 4),
                avg_confidence=round(avg_conf, 4),
                overconfidence=round(overconfidence, 4),
            ))
        
        return sorted(scores, key=lambda x: x.accuracy, reverse=True)
    
    def load_and_generate(self, period_days: int = 30) -> Optional[ForecastScoreboard]:
        """Load prediction data and generate scoreboard."""
        predictions_file = self.data_dir / "predictions" / "prediction_records.jsonl"
        
        if not predictions_file.exists():
            logger.warning("No prediction records found")
            return None
        
        # Load predictions
        predictions = []
        with open(predictions_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        predictions.append(json.loads(line))
                    except Exception:
                        pass
        
        # Filter by date
        cutoff = datetime.now() - timedelta(days=period_days)
        recent = []
        
        for p in predictions:
            try:
                created = datetime.fromisoformat(p.get("created_at", ""))
                if created >= cutoff:
                    recent.append(p)
            except Exception:
                pass
        
        if not recent:
            logger.warning("No recent predictions found")
            return None
        
        return self.generate(recent, period_days)


# =============================================================================
# BRIEF SECTION GENERATOR
# =============================================================================

def generate_scoreboard_section(scoreboard: Optional[ForecastScoreboard]) -> str:
    """Generate the Scoreboard section for the analyst brief."""
    if scoreboard is None:
        lines = []
        lines.append("## Forecast Scoreboard")
        lines.append("")
        lines.append("*Not enough evaluated predictions to generate scoreboard.*")
        lines.append("*Need at least 10 evaluated predictions.*")
        lines.append("")
        return "\n".join(lines)
    
    return scoreboard.format_markdown()


# =============================================================================
# TESTS
# =============================================================================

def _test_scoreboard_generation():
    """Test scoreboard generation."""
    generator = ScoreboardGenerator()
    
    predictions = [
        {"status": "evaluated", "verdict": "verified_true", "confidence_at_prediction": 0.75, "mechanism": "infra_scaling"},
        {"status": "evaluated", "verdict": "verified_true", "confidence_at_prediction": 0.80, "mechanism": "infra_scaling"},
        {"status": "evaluated", "verdict": "verified_false", "confidence_at_prediction": 0.70, "mechanism": "infra_scaling"},
        {"status": "evaluated", "verdict": "verified_true", "confidence_at_prediction": 0.85, "mechanism": "enterprise_adoption"},
        {"status": "evaluated", "verdict": "inconclusive", "confidence_at_prediction": 0.60, "mechanism": "enterprise_adoption"},
    ]
    
    scoreboard = generator.generate(predictions, period_days=30)
    
    assert scoreboard.evaluated_predictions == 5
    assert scoreboard.correct_predictions == 3
    assert scoreboard.incorrect_predictions == 1
    assert scoreboard.overall_accuracy == 0.75
    
    # Test markdown output
    md = scoreboard.format_markdown()
    assert "75%" in md
    assert "Forecast Scoreboard" in md
    
    print("[PASS] _test_scoreboard_generation")


def _test_calibration_buckets():
    """Test calibration bucket calculation."""
    generator = ScoreboardGenerator()
    
    predictions = [
        # 70-80% bucket: 2 predictions, 1 correct = 50% actual
        {"verdict": "verified_true", "confidence_at_prediction": 0.75},
        {"verdict": "verified_false", "confidence_at_prediction": 0.72},
        # 80-90% bucket: 2 predictions, 2 correct = 100% actual
        {"verdict": "verified_true", "confidence_at_prediction": 0.85},
        {"verdict": "verified_true", "confidence_at_prediction": 0.82},
    ]
    
    buckets = generator._build_calibration_buckets(predictions)
    
    # Find 70-80% bucket
    bucket_70_80 = next((b for b in buckets if b.confidence_range == "70-80%"), None)
    assert bucket_70_80 is not None
    assert bucket_70_80.predictions_count == 2
    assert bucket_70_80.actual_rate == 0.5
    
    print("[PASS] _test_calibration_buckets")


def run_tests():
    """Run all tests."""
    print("\n=== FORECAST SCOREBOARD TESTS ===\n")
    
    _test_scoreboard_generation()
    _test_calibration_buckets()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
