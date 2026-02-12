#!/usr/bin/env python
"""
Learning Status Report Generator

Generates a rolling 30-day learning status report from review data.

Output: data/reviews/learning_status.md

Usage:
    python scripts/generate_learning_status.py
    python scripts/generate_learning_status.py --days 30
    python scripts/generate_learning_status.py --output-dir data/reviews

NO LLM USAGE. All metrics are computed deterministically.
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def safe_divide(num: float, denom: float, default: float = 0.0) -> float:
    return num / denom if denom > 0 else default


def load_review_files(reviews_dir: Path, days: int) -> list[dict]:
    """
    Load review JSON files.
    
    First tries to find files from the last N days.
    If none found, falls back to loading all review_*.json files.
    """
    reviews = []
    today = date.today()
    
    # Try last N days first
    for i in range(days):
        check_date = today - timedelta(days=i)
        review_path = reviews_dir / f"review_{check_date.isoformat()}.json"
        
        if review_path.exists():
            with open(review_path, "r", encoding="utf-8") as f:
                try:
                    review = json.load(f)
                    review["_file_date"] = check_date.isoformat()
                    reviews.append(review)
                except json.JSONDecodeError:
                    continue
    
    # If no reviews found, try loading all review_*.json files
    if not reviews:
        for review_path in sorted(reviews_dir.glob("review_*.json"), reverse=True):
            if review_path.stem.startswith("review_"):
                with open(review_path, "r", encoding="utf-8") as f:
                    try:
                        review = json.load(f)
                        review["_file_date"] = review.get("review_date", review_path.stem.replace("review_", ""))
                        reviews.append(review)
                    except json.JSONDecodeError:
                        continue
    
    return reviews


def compute_rolling_accuracy(reviews: list[dict]) -> dict:
    """Compute rolling accuracy metrics across all reviews."""
    total_predictions = 0
    total_correct = 0
    total_incorrect = 0
    total_unclear = 0
    
    for review in reviews:
        metrics = review.get("metrics", {})
        total_predictions += metrics.get("total_predictions", 0)
        total_correct += metrics.get("overall_correct", 0)
        total_incorrect += metrics.get("overall_incorrect", 0)
        total_unclear += metrics.get("total_unclear", 0)
    
    resolved = total_correct + total_incorrect
    
    return {
        "total_predictions": total_predictions,
        "total_correct": total_correct,
        "total_incorrect": total_incorrect,
        "total_unclear": total_unclear,
        "overall_accuracy": safe_divide(total_correct, resolved),
        "unclear_rate": safe_divide(total_unclear, total_predictions),
    }


def compute_rolling_calibration(reviews: list[dict]) -> float:
    """Compute weighted average calibration error."""
    total_error = 0.0
    total_weight = 0
    
    for review in reviews:
        metrics = review.get("metrics", {})
        error = metrics.get("calibration_error", 0)
        weight = metrics.get("total_predictions", 0) - metrics.get("total_unclear", 0)
        
        if weight > 0:
            total_error += error * weight
            total_weight += weight
    
    return safe_divide(total_error, total_weight)


def compute_mechanism_performance(reviews: list[dict]) -> dict[str, dict]:
    """Compute performance by mechanism across all reviews."""
    mechanism_stats = defaultdict(lambda: {"correct": 0, "total": 0})
    
    for review in reviews:
        predictions = review.get("expired_predictions", [])
        outcomes = review.get("resolved_outcomes", [])
        
        # Create outcome lookup
        outcome_map = {o["prediction_id"]: o for o in outcomes}
        
        for pred in predictions:
            outcome = outcome_map.get(pred["prediction_id"])
            if not outcome or outcome["outcome"] == "unclear":
                continue
            
            mechanism = pred.get("mechanism", "unknown")
            mechanism_stats[mechanism]["total"] += 1
            if outcome["outcome"] == "correct":
                mechanism_stats[mechanism]["correct"] += 1
    
    # Calculate rates
    result = {}
    for mech, stats in mechanism_stats.items():
        result[mech] = {
            "correct": stats["correct"],
            "total": stats["total"],
            "accuracy": safe_divide(stats["correct"], stats["total"]),
        }
    
    return result


def compute_overconfidence_metric(reviews: list[dict]) -> dict:
    """
    Compute overconfidence metric.
    
    Overconfidence = avg(predicted_confidence - actual_accuracy) for high-confidence predictions.
    Positive = overconfident, Negative = underconfident.
    """
    high_conf_predictions = []
    
    for review in reviews:
        predictions = review.get("expired_predictions", [])
        outcomes = review.get("resolved_outcomes", [])
        outcome_map = {o["prediction_id"]: o for o in outcomes}
        
        for pred in predictions:
            conf = pred.get("confidence", 0.5)
            if conf < 0.7:  # Only look at high-confidence
                continue
            
            outcome = outcome_map.get(pred["prediction_id"])
            if not outcome or outcome["outcome"] == "unclear":
                continue
            
            is_correct = 1 if outcome["outcome"] == "correct" else 0
            high_conf_predictions.append({
                "confidence": conf,
                "correct": is_correct,
            })
    
    if not high_conf_predictions:
        return {
            "overconfidence_score": 0.0,
            "sample_size": 0,
            "avg_confidence": 0.0,
            "actual_accuracy": 0.0,
        }
    
    avg_conf = sum(p["confidence"] for p in high_conf_predictions) / len(high_conf_predictions)
    actual_acc = sum(p["correct"] for p in high_conf_predictions) / len(high_conf_predictions)
    
    return {
        "overconfidence_score": avg_conf - actual_acc,
        "sample_size": len(high_conf_predictions),
        "avg_confidence": avg_conf,
        "actual_accuracy": actual_acc,
    }


def generate_status_markdown(
    days: int,
    accuracy: dict,
    calibration_error: float,
    mechanism_perf: dict,
    overconfidence: dict,
) -> str:
    """Generate markdown report."""
    lines = [
        "# briefAI Learning Status Report",
        "",
        f"**Period:** Rolling {days} days",
        f"**Generated:** {date.today().isoformat()}",
        "",
        "---",
        "",
        "## Rolling Accuracy",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Predictions | {accuracy['total_predictions']} |",
        f"| Correct | {accuracy['total_correct']} |",
        f"| Incorrect | {accuracy['total_incorrect']} |",
        f"| Unclear | {accuracy['total_unclear']} |",
        f"| **Overall Accuracy** | {accuracy['overall_accuracy']:.1%} |",
        f"| Unclear Rate | {accuracy['unclear_rate']:.1%} |",
        "",
        "## Calibration",
        "",
        f"**Mean Calibration Error:** {calibration_error:.3f}",
        "",
    ]
    
    if calibration_error < 0.05:
        lines.append("Status: Well-calibrated")
    elif calibration_error < 0.15:
        lines.append("Status: Moderate calibration error")
    else:
        lines.append("Status: Poorly calibrated - needs attention")
    lines.append("")
    
    # Top mechanisms
    sorted_mechs = sorted(
        [(m, s) for m, s in mechanism_perf.items() if s["total"] >= 3],
        key=lambda x: -x[1]["accuracy"]
    )
    
    lines.append("## Top Performing Mechanisms")
    lines.append("")
    if sorted_mechs:
        lines.append("| Mechanism | Accuracy | Sample Size |")
        lines.append("|-----------|----------|-------------|")
        for mech, stats in sorted_mechs[:5]:
            lines.append(f"| {mech} | {stats['accuracy']:.0%} | {stats['total']} |")
        lines.append("")
    else:
        lines.append("_Insufficient data_")
        lines.append("")
    
    # Worst mechanisms
    lines.append("## Worst Performing Mechanisms")
    lines.append("")
    if sorted_mechs:
        lines.append("| Mechanism | Accuracy | Sample Size |")
        lines.append("|-----------|----------|-------------|")
        for mech, stats in reversed(sorted_mechs[-5:]):
            lines.append(f"| {mech} | {stats['accuracy']:.0%} | {stats['total']} |")
        lines.append("")
    else:
        lines.append("_Insufficient data_")
        lines.append("")
    
    # Overconfidence
    lines.append("## Overconfidence Metric")
    lines.append("")
    lines.append(f"**High-Confidence Predictions (>=70%):** {overconfidence['sample_size']}")
    lines.append(f"**Average Confidence:** {overconfidence['avg_confidence']:.1%}")
    lines.append(f"**Actual Accuracy:** {overconfidence['actual_accuracy']:.1%}")
    lines.append(f"**Overconfidence Score:** {overconfidence['overconfidence_score']:+.3f}")
    lines.append("")
    
    if overconfidence['overconfidence_score'] > 0.15:
        lines.append("Status: Significantly overconfident - reduce confidence scores")
    elif overconfidence['overconfidence_score'] > 0.05:
        lines.append("Status: Moderately overconfident")
    elif overconfidence['overconfidence_score'] < -0.05:
        lines.append("Status: Underconfident - can increase confidence")
    else:
        lines.append("Status: Well-calibrated confidence levels")
    lines.append("")
    
    lines.append("---")
    lines.append("")
    lines.append("*Generated by briefAI Learning Status Reporter*")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate learning status report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--days", "-d",
        type=int,
        default=30,
        help="Number of days to include (default: 30)",
    )
    parser.add_argument(
        "--reviews-dir",
        type=Path,
        help="Directory containing review files (default: data/reviews)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        help="Output directory (default: same as reviews-dir)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress",
    )
    
    args = parser.parse_args()
    
    # Determine directories
    project_root = Path(__file__).parent.parent
    
    if args.reviews_dir:
        reviews_dir = args.reviews_dir
    else:
        reviews_dir = project_root / "data" / "reviews"
    
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = reviews_dir
    
    if not reviews_dir.exists():
        print(f"Error: Reviews directory not found: {reviews_dir}", file=sys.stderr)
        return 1
    
    if args.verbose:
        print(f"[Learning Status] Loading reviews from last {args.days} days...")
    
    # Load reviews
    reviews = load_review_files(reviews_dir, args.days)
    
    if not reviews:
        print(f"No review files found in {reviews_dir}")
        return 0
    
    if args.verbose:
        print(f"[Learning Status] Found {len(reviews)} review files")
    
    # Compute metrics
    accuracy = compute_rolling_accuracy(reviews)
    calibration = compute_rolling_calibration(reviews)
    mechanism_perf = compute_mechanism_performance(reviews)
    overconfidence = compute_overconfidence_metric(reviews)
    
    # Generate report
    report = generate_status_markdown(
        args.days,
        accuracy,
        calibration,
        mechanism_perf,
        overconfidence,
    )
    
    # Write output
    output_path = output_dir / "learning_status.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"OUTPUT: {output_path}")
    
    if args.verbose:
        print(f"\n{report}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
