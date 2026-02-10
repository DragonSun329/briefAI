#!/usr/bin/env python
"""
Generate Calibration Report.

Part of briefAI Validation & Public Credibility Layer.

Computes calibration metrics by confidence bucket:
    0.5-0.6, 0.6-0.7, 0.7-0.8, 0.8-0.9

For each bucket:
    - predictions count
    - verified_true count
    - verified_false count
    - accuracy

Output:
    data/metrics/calibration_report.json

Usage:
    python scripts/generate_calibration_report.py
    python scripts/generate_calibration_report.py --print
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
CALIBRATION_REPORT_FILE = "calibration_report.json"

# Confidence buckets
BUCKETS = [
    (0.5, 0.6, "0.5-0.6"),
    (0.6, 0.7, "0.6-0.7"),
    (0.7, 0.8, "0.7-0.8"),
    (0.8, 0.9, "0.8-0.9"),
    (0.9, 1.0, "0.9-1.0"),
]


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class CalibrationBucket:
    """Calibration metrics for a confidence range."""
    bucket_name: str
    confidence_min: float
    confidence_max: float
    predictions: int
    verified_true: int
    verified_false: int
    inconclusive: int
    accuracy: float
    expected_accuracy: float  # Midpoint of bucket
    calibration_error: float  # Difference from expected
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CalibrationReport:
    """Complete calibration report."""
    generated_at: str
    period_start: str
    period_end: str
    
    # Totals
    total_predictions: int
    total_evaluated: int
    overall_accuracy: float
    brier_score: float
    
    # Buckets
    buckets: List[Dict[str, Any]]
    
    # Reliability curve data (for plotting)
    reliability_curve: List[Dict[str, float]]
    
    # Mean calibration error
    mean_calibration_error: float
    
    # Interpretation
    calibration_quality: str  # well-calibrated, overconfident, underconfident
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def format_markdown(self) -> str:
        """Format report as markdown."""
        lines = []
        
        lines.append("# Calibration Report")
        lines.append("")
        lines.append(f"**Generated:** {self.generated_at}")
        lines.append(f"**Period:** {self.period_start} to {self.period_end}")
        lines.append("")
        
        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total Predictions | {self.total_predictions} |")
        lines.append(f"| Evaluated | {self.total_evaluated} |")
        lines.append(f"| Overall Accuracy | {self.overall_accuracy:.0%} |")
        lines.append(f"| Brier Score | {self.brier_score:.4f} |")
        lines.append(f"| Mean Calibration Error | {self.mean_calibration_error:.4f} |")
        lines.append(f"| **Calibration Quality** | **{self.calibration_quality}** |")
        lines.append("")
        
        # Buckets
        lines.append("## Calibration by Confidence Level")
        lines.append("")
        lines.append("| Confidence | Count | True | False | Accuracy | Expected | Error |")
        lines.append("|------------|-------|------|-------|----------|----------|-------|")
        
        for bucket in self.buckets:
            name = bucket["bucket_name"]
            count = bucket["predictions"]
            true_count = bucket["verified_true"]
            false_count = bucket["verified_false"]
            acc = bucket["accuracy"]
            expected = bucket["expected_accuracy"]
            error = bucket["calibration_error"]
            
            if count > 0:
                lines.append(
                    f"| {name} | {count} | {true_count} | {false_count} | "
                    f"{acc:.0%} | {expected:.0%} | {error:+.0%} |"
                )
        
        lines.append("")
        
        # Reliability curve
        lines.append("## Reliability Curve Data")
        lines.append("")
        lines.append("```")
        lines.append("Expected  Actual")
        for point in self.reliability_curve:
            exp = point["expected"]
            act = point["actual"]
            lines.append(f"{exp:.2f}      {act:.2f}")
        lines.append("```")
        lines.append("")
        
        # Interpretation
        lines.append("## Interpretation")
        lines.append("")
        
        if self.calibration_quality == "well-calibrated":
            lines.append("The system is **well-calibrated**. Predicted confidence aligns with actual accuracy.")
        elif self.calibration_quality == "overconfident":
            lines.append("The system is **overconfident**. Actual accuracy is lower than predicted confidence.")
            lines.append("Recommendation: Apply calibration factor < 1.0 to raw confidence scores.")
        elif self.calibration_quality == "underconfident":
            lines.append("The system is **underconfident**. Actual accuracy is higher than predicted confidence.")
            lines.append("Recommendation: Apply calibration factor > 1.0 to raw confidence scores.")
        
        lines.append("")
        
        return "\n".join(lines)


# =============================================================================
# CALIBRATION CALCULATOR
# =============================================================================

class CalibrationCalculator:
    """Computes calibration metrics from predictions."""
    
    def __init__(self, data_dir: Path = None):
        """Initialize calculator."""
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.metrics_dir = self.data_dir / "metrics"
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        
        self.report_file = self.metrics_dir / CALIBRATION_REPORT_FILE
    
    def compute_buckets(
        self,
        predictions: List[Dict[str, Any]],
    ) -> List[CalibrationBucket]:
        """Compute calibration for each bucket."""
        buckets = []
        
        for min_conf, max_conf, name in BUCKETS:
            # Filter predictions in this bucket
            in_bucket = [
                p for p in predictions
                if min_conf <= p.get("confidence_at_prediction", 0) < max_conf
            ]
            
            # Count verdicts
            true_count = sum(1 for p in in_bucket if p.get("verdict") == "verified_true")
            false_count = sum(1 for p in in_bucket if p.get("verdict") == "verified_false")
            inconclusive = sum(1 for p in in_bucket if p.get("verdict") == "inconclusive")
            
            # Calculate accuracy
            decisive = true_count + false_count
            accuracy = true_count / decisive if decisive > 0 else 0.0
            
            # Expected accuracy (midpoint)
            expected = (min_conf + max_conf) / 2
            
            # Calibration error
            cal_error = accuracy - expected
            
            buckets.append(CalibrationBucket(
                bucket_name=name,
                confidence_min=min_conf,
                confidence_max=max_conf,
                predictions=len(in_bucket),
                verified_true=true_count,
                verified_false=false_count,
                inconclusive=inconclusive,
                accuracy=round(accuracy, 4),
                expected_accuracy=expected,
                calibration_error=round(cal_error, 4),
            ))
        
        return buckets
    
    def compute_brier_score(
        self,
        predictions: List[Dict[str, Any]],
    ) -> float:
        """Compute Brier score."""
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
        
        return round(mse_sum / count, 4) if count > 0 else 0.0
    
    def generate_report(
        self,
        predictions: List[Dict[str, Any]],
    ) -> CalibrationReport:
        """Generate complete calibration report."""
        # Filter to evaluated predictions
        evaluated = [
            p for p in predictions
            if p.get("status") == "evaluated"
            and p.get("verdict") in ["verified_true", "verified_false", "inconclusive"]
        ]
        
        # Get date range
        dates = []
        for p in evaluated:
            created = p.get("created_at", "")
            if created:
                dates.append(created[:10])
        
        period_start = min(dates) if dates else datetime.now().strftime("%Y-%m-%d")
        period_end = max(dates) if dates else datetime.now().strftime("%Y-%m-%d")
        
        # Compute buckets
        buckets = self.compute_buckets(evaluated)
        
        # Compute Brier score
        brier = self.compute_brier_score(evaluated)
        
        # Calculate overall accuracy
        true_count = sum(b.verified_true for b in buckets)
        false_count = sum(b.verified_false for b in buckets)
        decisive = true_count + false_count
        overall_acc = true_count / decisive if decisive > 0 else 0.0
        
        # Build reliability curve
        reliability_curve = []
        for bucket in buckets:
            if bucket.predictions > 0:
                reliability_curve.append({
                    "expected": bucket.expected_accuracy,
                    "actual": bucket.accuracy,
                    "count": bucket.predictions,
                })
        
        # Mean calibration error
        total_error = sum(abs(b.calibration_error) * b.predictions for b in buckets)
        total_count = sum(b.predictions for b in buckets)
        mean_error = total_error / total_count if total_count > 0 else 0.0
        
        # Determine calibration quality
        avg_error = sum(b.calibration_error * b.predictions for b in buckets if b.predictions > 0) / max(total_count, 1)
        
        if abs(avg_error) < 0.05:
            quality = "well-calibrated"
        elif avg_error < -0.05:
            quality = "overconfident"
        else:
            quality = "underconfident"
        
        return CalibrationReport(
            generated_at=datetime.now().isoformat(),
            period_start=period_start,
            period_end=period_end,
            total_predictions=len(predictions),
            total_evaluated=len(evaluated),
            overall_accuracy=round(overall_acc, 4),
            brier_score=brier,
            buckets=[b.to_dict() for b in buckets],
            reliability_curve=reliability_curve,
            mean_calibration_error=round(mean_error, 4),
            calibration_quality=quality,
        )
    
    def save_report(self, report: CalibrationReport) -> Path:
        """Save report to file."""
        with open(self.report_file, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved calibration report to {self.report_file}")
        return self.report_file
    
    def load_predictions(self) -> List[Dict[str, Any]]:
        """Load predictions from store."""
        predictions_file = self.data_dir / "predictions" / "prediction_records.jsonl"
        
        if not predictions_file.exists():
            return []
        
        predictions = []
        with open(predictions_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        predictions.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        
        return predictions
    
    def run(self) -> CalibrationReport:
        """Load predictions and generate report."""
        predictions = self.load_predictions()
        report = self.generate_report(predictions)
        self.save_report(report)
        return report


# =============================================================================
# CLI
# =============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate calibration report",
    )
    
    parser.add_argument(
        '--data-dir',
        type=Path,
        default=None,
        help='Override data directory',
    )
    
    parser.add_argument(
        '--print', '-p',
        action='store_true',
        dest='print_report',
        help='Print report to stdout',
    )
    
    parser.add_argument(
        '--markdown', '-m',
        action='store_true',
        help='Output as markdown',
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    print("=" * 60)
    print("CALIBRATION REPORT GENERATOR")
    print("=" * 60)
    print()
    
    calculator = CalibrationCalculator(args.data_dir)
    report = calculator.run()
    
    if args.print_report or args.markdown:
        print()
        print(report.format_markdown())
    else:
        print(f"Total Predictions: {report.total_predictions}")
        print(f"Evaluated: {report.total_evaluated}")
        print(f"Overall Accuracy: {report.overall_accuracy:.0%}")
        print(f"Brier Score: {report.brier_score:.4f}")
        print(f"Calibration Quality: {report.calibration_quality}")
        print()
        print(f"Report saved to: {calculator.report_file}")
    
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
