#!/usr/bin/env python
"""
Daily Review Hook Script

Runs the prediction review system as part of the daily pipeline.
Only produces output if there are expired predictions to review.

v1.1: New script for optional daily integration.

Usage:
    python scripts/run_daily_review.py --experiment v2_2_forward_test
    python scripts/run_daily_review.py --experiment v2_2_forward_test --verbose

Integration with daily_bloomberg.ps1:
    # Add to daily_bloomberg.ps1 (commented out by default):
    # python scripts/run_daily_review.py --experiment v2_2_forward_test --verbose

Exit codes:
    0 - Success (review generated or skipped due to no expired predictions)
    1 - Error during review
"""

import argparse
import sys
from datetime import date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from briefai.review.expired_predictions import find_expired_predictions
from briefai.review.cli import run_review


def main():
    parser = argparse.ArgumentParser(
        description="Daily prediction review hook",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run review even if no expired predictions (for testing)",
    )
    
    args = parser.parse_args()
    
    # Determine data root
    if args.data_root:
        data_root = args.data_root
    else:
        data_root = Path(__file__).parent.parent / "data"
    
    experiment_path = data_root / "public" / "experiments"
    output_dir = data_root / "reviews"
    today = date.today()
    
    if args.verbose:
        print(f"[Daily Review] Checking for expired predictions...")
        print(f"  Experiment: {args.experiment}")
        print(f"  Date: {today}")
    
    # Check if there are expired predictions
    try:
        expired = find_expired_predictions(
            experiment_id=args.experiment,
            data_root=experiment_path,
            as_of_date=today,
        )
    except FileNotFoundError as e:
        print(f"[Daily Review] Error: {e}", file=sys.stderr)
        return 1
    
    if not expired and not args.force:
        print("No expired predictions — review skipped.")
        return 0
    
    if args.verbose:
        print(f"[Daily Review] Found {len(expired)} expired predictions. Running review...")
    
    # Run the review
    try:
        result = run_review(
            experiment_id=args.experiment,
            data_root=data_root,
            output_dir=output_dir,
            as_of_date=today,
            verbose=args.verbose,
        )
        
        # Only print output paths if we generated files
        if result.total_predictions > 0 or result.metrics.total_predictions > 0:
            json_path = output_dir / f"review_{today}.json"
            md_path = output_dir / f"review_{today}.md"
            suggestions_path = output_dir / f"suggestions_{today}.json"
            
            print(f"OUTPUT: {json_path}")
            print(f"OUTPUT: {md_path}")
            if suggestions_path.exists():
                print(f"OUTPUT: {suggestions_path}")
        else:
            print("No predictions to review — no output generated.")
        
        return 0
        
    except Exception as e:
        print(f"[Daily Review] Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
