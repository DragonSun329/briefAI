"""
Review System CLI

Entry point for running prediction reviews.

Usage:
    python -m briefai review --experiment v2_2_forward_test

v1.1: Added suggestions generation, unclear breakdown in reports.
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .models import (
    ReviewResult,
    ExpiredPrediction,
    ResolvedOutcome,
    ReviewMetrics,
    LearningInsight,
    Lesson,
    Suggestion,
    OutcomeStatus,
    Direction,
    UnclearReason,
)
from .expired_predictions import find_expired_predictions
from .outcome_resolver import resolve_all
from .metrics import compute_metrics, format_metrics_summary
from .patterns import discover_patterns, get_top_performers, get_worst_performers
from .lessons import synthesize_lessons, format_lessons_markdown
from .suggestions import generate_suggestions, write_suggestions_json, format_suggestions_markdown


def serialize_dataclass(obj):
    """JSON serializer for dataclasses and enums."""
    if hasattr(obj, "__dataclass_fields__"):
        result = {}
        for field in obj.__dataclass_fields__:
            value = getattr(obj, field)
            result[field] = serialize_dataclass(value)
        return result
    elif isinstance(obj, (list, tuple)):
        return [serialize_dataclass(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: serialize_dataclass(v) for k, v in obj.items()}
    elif isinstance(obj, (date, datetime)):
        return obj.isoformat()
    elif isinstance(obj, (OutcomeStatus, Direction, UnclearReason)):
        return obj.value
    else:
        return obj


def run_review(
    experiment_id: str,
    data_root: Path = None,
    output_dir: Path = None,
    as_of_date: date = None,
    verbose: bool = False,
) -> ReviewResult:
    """
    Run a complete prediction review.
    
    Pipeline:
    1. Load ledger
    2. Detect expired predictions
    3. Resolve outcomes
    4. Compute metrics
    5. Discover patterns
    6. Synthesize lessons
    7. Write outputs
    """
    if data_root is None:
        data_root = Path(__file__).parent.parent.parent / "data"
    
    if output_dir is None:
        output_dir = data_root / "reviews"
    
    if as_of_date is None:
        as_of_date = date.today()
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if verbose:
        print(f"[*] Running prediction review for experiment: {experiment_id}")
        print(f"    Data root: {data_root}")
        print(f"    As of date: {as_of_date}")
        print()
    
    # Step 1 & 2: Find expired predictions
    if verbose:
        print("[*] Finding expired predictions...")
    
    experiment_path = data_root / "public" / "experiments"
    expired = find_expired_predictions(
        experiment_id=experiment_id,
        data_root=experiment_path,
        as_of_date=as_of_date,
    )
    
    if verbose:
        print(f"    Found {len(expired)} expired predictions")
    
    if not expired:
        if verbose:
            print("[!] No expired predictions found. Nothing to review.")
        return ReviewResult(
            experiment_id=experiment_id,
            review_date=as_of_date,
            period_start=as_of_date,
            period_end=as_of_date,
            generation_timestamp=datetime.utcnow().isoformat() + "Z",
        )
    
    # Step 3: Resolve outcomes
    if verbose:
        print("[*] Resolving outcomes...")
    
    outcomes = resolve_all(expired, data_root)
    
    correct_count = sum(1 for o in outcomes if o.outcome == OutcomeStatus.CORRECT)
    incorrect_count = sum(1 for o in outcomes if o.outcome == OutcomeStatus.INCORRECT)
    unclear_count = sum(1 for o in outcomes if o.outcome == OutcomeStatus.UNCLEAR)
    
    if verbose:
        print(f"    [+] Correct: {correct_count}")
        print(f"    [-] Incorrect: {incorrect_count}")
        print(f"    [?] Unclear: {unclear_count}")
    
    # Step 4: Compute metrics
    if verbose:
        print("[*] Computing metrics...")
    
    metrics = compute_metrics(expired, outcomes)
    
    if verbose:
        print(f"    Overall accuracy: {metrics.overall_accuracy:.1%}")
    
    # Step 5: Discover patterns
    if verbose:
        print("[*] Discovering patterns...")
    
    insights = discover_patterns(expired, outcomes)
    
    if verbose:
        print(f"    Found {len(insights)} patterns")
    
    # Step 6: Synthesize lessons
    if verbose:
        print("[*] Synthesizing lessons...")
    
    lessons = synthesize_lessons(metrics, insights)
    
    if verbose:
        print(f"    Generated {len(lessons)} lessons")
    
    # v1.1 Step 7: Generate suggestions
    if verbose:
        print("[*] Generating suggestions...")
    
    suggestions = generate_suggestions(metrics, insights, lessons, as_of_date)
    
    if verbose:
        print(f"    Generated {len(suggestions)} suggestions")
    
    # Determine period
    if expired:
        dates = [p.date_made for p in expired if p.date_made]
        if dates:
            period_start = min(dates)
            period_end = max(dates)
        else:
            period_start = as_of_date
            period_end = as_of_date
    else:
        period_start = as_of_date
        period_end = as_of_date
    
    # Build result
    result = ReviewResult(
        experiment_id=experiment_id,
        review_date=as_of_date,
        period_start=period_start,
        period_end=period_end,
        expired_predictions=expired,
        resolved_outcomes=outcomes,
        metrics=metrics,
        insights=insights,
        lessons=lessons,
        suggestions=suggestions,  # v1.1
        generation_timestamp=datetime.utcnow().isoformat() + "Z",
    )
    
    # Step 8: Write outputs
    if verbose:
        print("[*] Writing outputs...")
    
    write_outputs(result, output_dir)
    
    # v1.1: Write suggestions JSON
    if suggestions:
        write_suggestions_json(suggestions, output_dir, as_of_date)
    
    if verbose:
        print(f"    [+] Wrote review_{as_of_date}.json")
        print(f"    [+] Wrote review_{as_of_date}.md")
        if suggestions:
            print(f"    [+] Wrote suggestions_{as_of_date}.json")
        print()
        print("[OK] Review complete!")
    
    return result


def write_outputs(result: ReviewResult, output_dir: Path):
    """
    Write JSON and Markdown outputs.
    """
    date_str = result.review_date.isoformat()
    
    # JSON output
    json_path = output_dir / f"review_{date_str}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(serialize_dataclass(result), f, indent=2, ensure_ascii=False)
    
    # Markdown output
    md_path = output_dir / f"review_{date_str}.md"
    md_content = generate_markdown_report(result)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)


def generate_markdown_report(result: ReviewResult) -> str:
    """
    Generate human-readable markdown report.
    """
    lines = [
        f"# briefAI Prediction Review",
        "",
        f"**Experiment:** {result.experiment_id}",
        f"**Review Date:** {result.review_date}",
        f"**Period:** {result.period_start} to {result.period_end}",
        f"**Generated:** {result.generation_timestamp}",
        "",
        "---",
        "",
    ]
    
    # Accuracy section
    lines.append("## Accuracy")
    lines.append("")
    metrics = result.metrics
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| **Overall Accuracy** | {metrics.overall_accuracy:.1%} |")
    lines.append(f"| Total Predictions | {metrics.total_predictions} |")
    lines.append(f"| Resolved | {metrics.total_resolved} |")
    lines.append(f"| Unclear | {metrics.total_unclear} |")
    lines.append(f"| Correct | {metrics.overall_correct} |")
    lines.append(f"| Incorrect | {metrics.overall_incorrect} |")
    lines.append("")
    
    # Direction breakdown
    lines.append("### By Direction")
    lines.append("")
    lines.append(f"| Direction | Accuracy | Count |")
    lines.append(f"|-----------|----------|-------|")
    lines.append(f"| Bullish (up) | {metrics.bullish_accuracy:.1%} | {metrics.bullish_count} |")
    lines.append(f"| Bearish (down) | {metrics.bearish_accuracy:.1%} | {metrics.bearish_count} |")
    lines.append("")
    
    # Confidence breakdown
    lines.append("### By Confidence Level")
    lines.append("")
    lines.append(f"| Level | Accuracy | Count |")
    lines.append(f"|-------|----------|-------|")
    lines.append(f"| High (>0.8) | {metrics.high_confidence_accuracy:.1%} | {metrics.high_confidence_count} |")
    lines.append(f"| Medium (0.5-0.8) | {metrics.medium_confidence_accuracy:.1%} | {metrics.medium_confidence_count} |")
    lines.append(f"| Low (<0.5) | {metrics.low_confidence_accuracy:.1%} | {metrics.low_confidence_count} |")
    lines.append("")
    
    # v1.1: Unclear Analysis section
    lines.append("## Unclear Analysis")
    lines.append("")
    lines.append(f"**Unclear Rate:** {metrics.unclear_rate:.1%} ({metrics.total_unclear}/{metrics.total_predictions})")
    lines.append("")
    if metrics.unclear_breakdown:
        lines.append("| Reason | Count |")
        lines.append("|--------|-------|")
        for reason, count in metrics.unclear_breakdown.items():
            lines.append(f"| {reason} | {count} |")
        lines.append("")
    
    # Calibration section
    lines.append("## Calibration")
    lines.append("")
    lines.append(f"**Mean Calibration Error:** {metrics.calibration_error:.3f}")
    lines.append(f"**Avg Time to Resolution:** {metrics.avg_time_to_resolution_days:.1f} days")
    lines.append("")
    
    if metrics.calibration_error < 0.05:
        lines.append("Confidence scores are well-calibrated")
    elif metrics.calibration_error < 0.15:
        lines.append("Confidence scores have moderate calibration error")
    else:
        lines.append("Confidence scores are poorly calibrated - needs attention")
    lines.append("")
    
    # What we're good at
    lines.append("## What We Are Good At Predicting")
    lines.append("")
    top_performers = get_top_performers(result.insights, n=5)
    if top_performers:
        for insight in top_performers:
            lines.append(f"- **{insight.pattern}** ({insight.category}): {insight.success_rate:.0%} accuracy (n={insight.sample_size})")
        lines.append("")
    else:
        lines.append("_Insufficient data to determine strengths_")
        lines.append("")
    
    # What we predict poorly
    lines.append("## What We Predict Poorly")
    lines.append("")
    worst_performers = get_worst_performers(result.insights, n=5)
    if worst_performers:
        for insight in worst_performers:
            lines.append(f"- **{insight.pattern}** ({insight.category}): {insight.success_rate:.0%} accuracy (n={insight.sample_size})")
        lines.append("")
    else:
        lines.append("_Insufficient data to determine weaknesses_")
        lines.append("")
    
    # Failure Analysis
    lines.append("## Failure Analysis")
    lines.append("")
    incorrect_outcomes = [o for o in result.resolved_outcomes if o.outcome == OutcomeStatus.INCORRECT]
    if incorrect_outcomes:
        lines.append(f"**{len(incorrect_outcomes)} predictions were incorrect:**")
        lines.append("")
        # Group by mechanism
        mechanism_failures = {}
        for pred in result.expired_predictions:
            outcome = next((o for o in result.resolved_outcomes if o.prediction_id == pred.prediction_id), None)
            if outcome and outcome.outcome == OutcomeStatus.INCORRECT:
                mech = pred.mechanism or "unknown"
                if mech not in mechanism_failures:
                    mechanism_failures[mech] = 0
                mechanism_failures[mech] += 1
        
        for mech, count in sorted(mechanism_failures.items(), key=lambda x: -x[1]):
            lines.append(f"- {mech}: {count} failures")
        lines.append("")
    else:
        lines.append("_No incorrect predictions in this period_")
        lines.append("")
    
    # System Lessons
    lines.append(format_lessons_markdown(result.lessons))
    
    # v1.1: Suggestions section
    lines.append(format_suggestions_markdown(result.suggestions))
    
    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated by briefAI Review System v{result.review_version}*")
    
    return "\n".join(lines)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="briefAI Prediction Review System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m briefai review --experiment v2_2_forward_test
  python -m briefai review --experiment v2_2_forward_test --verbose
  python -m briefai review --experiment v2_2_forward_test --as-of 2026-02-15
        """,
    )
    
    parser.add_argument(
        "--experiment", "-e",
        default="v2_2_forward_test",
        help="Experiment ID to review (default: v2_2_forward_test)",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        help="Root data directory (default: ./data)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        help="Output directory for reviews (default: data/reviews)",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        help="Date to use as 'today' for expiration check (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result summary as JSON",
    )
    
    args = parser.parse_args()
    
    # Parse as-of date
    as_of_date = None
    if args.as_of:
        as_of_date = date.fromisoformat(args.as_of)
    
    try:
        result = run_review(
            experiment_id=args.experiment,
            data_root=args.data_root,
            output_dir=args.output_dir,
            as_of_date=as_of_date,
            verbose=args.verbose,
        )
        
        if args.json:
            summary = {
                "experiment_id": result.experiment_id,
                "review_date": result.review_date.isoformat(),
                "total_predictions": result.metrics.total_predictions,
                "overall_accuracy": result.metrics.overall_accuracy,
                "lessons_count": len(result.lessons),
            }
            print(json.dumps(summary, indent=2))
        
        return 0
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
