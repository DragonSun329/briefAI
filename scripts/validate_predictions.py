#!/usr/bin/env python
"""
Validate Vertical Predictions

Validates pending predictions against actual market performance.
Run weekly to update accuracy metrics.

Usage:
    python scripts/validate_predictions.py
    python scripts/validate_predictions.py --min-age 14
    python scripts/validate_predictions.py --vertical ai_healthcare
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.vertical_validator import get_vertical_validator


def main():
    parser = argparse.ArgumentParser(description="Validate vertical predictions")
    parser.add_argument(
        "--min-age", type=int, default=30,
        help="Minimum prediction age in days to validate (default: 30)"
    )
    parser.add_argument(
        "--vertical", type=str,
        help="Validate specific vertical only"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be validated without updating database"
    )
    args = parser.parse_args()
    
    print(f"=== Prediction Validation ({date.today()}) ===\n")
    
    validator = get_vertical_validator()
    
    # Get pending predictions
    print(f"Finding predictions older than {args.min_age} days...")
    predictions = validator.get_pending_predictions(args.min_age)
    
    if args.vertical:
        predictions = [p for p in predictions if p["vertical_id"] == args.vertical]
    
    if not predictions:
        print("No pending predictions to validate.")
        return
    
    print(f"Found {len(predictions)} pending predictions\n")
    
    if args.dry_run:
        print("[DRY RUN] Would validate:")
        for p in predictions[:10]:
            print(f"  {p['vertical_id']}: {p['prediction_type']} ({p['prediction_date']})")
        if len(predictions) > 10:
            print(f"  ... and {len(predictions) - 10} more")
        return
    
    # Run validation
    print("Validating against market performance...")
    results = validator.validate_all_pending(args.min_age)
    
    # Print results
    print(f"\n=== Validation Results ===")
    print(f"Total validated: {results.get('total_validated', 0)}")
    print(f"Errors: {results.get('errors', 0)}")
    
    avg_acc = results.get('average_accuracy')
    if avg_acc is not None:
        print(f"Average accuracy: {avg_acc:.1%}")
    
    # Show individual results
    print("\nDetails:")
    for r in results.get("results", [])[:10]:
        if "error" in r:
            print(f"  [ERROR] {r.get('vertical_id', 'unknown')}: {r['error']}")
        else:
            emoji = "✓" if r["accuracy_score"] >= 0.7 else "○" if r["accuracy_score"] >= 0.4 else "✗"
            print(f"  [{emoji}] {r['vertical_id']}: predicted={r['predicted_outcome']}, actual={r['actual_outcome']} ({r['actual_pct_change']:+.1f}%), accuracy={r['accuracy_score']:.0%}")
    
    # Get overall summary
    print("\n=== Overall Accuracy Summary ===")
    summary = validator.get_validation_summary(days=90)
    
    if summary.get("by_type"):
        print("\nBy Prediction Type:")
        for ptype, data in summary["by_type"].items():
            if data["accuracy"]:
                print(f"  {ptype}: {data['accuracy']:.1%} ({data['count']} validated)")
    
    if summary.get("by_vertical"):
        print("\nTop Accurate Verticals:")
        sorted_verticals = sorted(
            summary["by_vertical"].items(),
            key=lambda x: x[1]["accuracy"] or 0,
            reverse=True
        )
        for vid, data in sorted_verticals[:5]:
            if data["accuracy"]:
                print(f"  {vid}: {data['accuracy']:.1%} ({data['count']} predictions)")


if __name__ == "__main__":
    main()
