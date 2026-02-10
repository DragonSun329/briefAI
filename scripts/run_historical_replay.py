#!/usr/bin/env python
"""
Historical Replay Backtest Runner.

Part of briefAI Validation & Public Credibility Layer.

Runs the briefAI pipeline on historical data with strict temporal causality:
- When simulating a past date, only use information available up to that date
- No forward-looking leakage

Usage:
    python scripts/run_historical_replay.py --start 2025-11-01 --end 2026-02-01
    python scripts/run_historical_replay.py --start 2026-01-01 --end 2026-01-31 --dry-run

Output:
    data/backtest/{date}/signals.json
    data/backtest/{date}/metas.json
    data/backtest/{date}/hypotheses.json
    data/backtest/{date}/predictions.json
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from utils.historical_replay_runner import HistoricalReplayRunner


# =============================================================================
# CLI
# =============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run historical replay backtest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Replay November to February
    python scripts/run_historical_replay.py --start 2025-11-01 --end 2026-02-01
    
    # Replay single month
    python scripts/run_historical_replay.py --start 2026-01-01 --end 2026-01-31
    
    # Dry run (no file writes)
    python scripts/run_historical_replay.py --start 2026-01-01 --end 2026-01-07 --dry-run
        """
    )
    
    parser.add_argument(
        '--start', '-s',
        type=str,
        required=True,
        help='Start date (YYYY-MM-DD)',
    )
    
    parser.add_argument(
        '--end', '-e',
        type=str,
        required=True,
        help='End date (YYYY-MM-DD)',
    )
    
    parser.add_argument(
        '--data-dir',
        type=Path,
        default=None,
        help='Override data directory',
    )
    
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Dry run (no file writes)',
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging',
    )
    
    return parser.parse_args()


def validate_date(date_str: str, name: str):
    """Validate date format."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        print(f"Error: {name} must be in YYYY-MM-DD format")
        sys.exit(1)


def main():
    """Main entry point."""
    args = parse_args()
    
    # Validate dates
    validate_date(args.start, "start date")
    validate_date(args.end, "end date")
    
    # Check date order
    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end, "%Y-%m-%d")
    
    if start_dt > end_dt:
        print("Error: start date must be before end date")
        sys.exit(1)
    
    # Configure logging
    if args.debug:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="INFO")
    
    # Print header
    print("=" * 60)
    print("HISTORICAL REPLAY BACKTEST")
    print("=" * 60)
    print()
    print(f"Date Range: {args.start} to {args.end}")
    print(f"Days: {(end_dt - start_dt).days + 1}")
    print(f"Dry Run: {args.dry_run}")
    print()
    
    # Run replay
    runner = HistoricalReplayRunner(args.data_dir)
    summary = runner.run_replay(args.start, args.end, args.dry_run)
    
    # Print summary
    print()
    print("=" * 60)
    print("REPLAY SUMMARY")
    print("=" * 60)
    print(f"Run ID: {summary.run_id}")
    print(f"Days Processed: {summary.days_processed}")
    print(f"Success Rate: {summary.success_rate:.0%}")
    print()
    print(f"Total Signals: {summary.total_signals}")
    print(f"Total Meta-Signals: {summary.total_metas}")
    print(f"Total Hypotheses: {summary.total_hypotheses}")
    print(f"Total Predictions: {summary.total_predictions}")
    print()
    print(f"Execution Time: {summary.execution_time_seconds:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
