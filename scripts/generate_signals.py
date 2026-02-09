#!/usr/bin/env python3
"""
Generate Signals - Signal Persistence Engine CLI

Links daily THEME clusters from dual feeds into persistent signals,
tracking momentum/velocity/acceleration across days.

Usage:
    python scripts/generate_signals.py
    python scripts/generate_signals.py --date 2026-02-09
    python scripts/generate_signals.py --days 7
    python scripts/generate_signals.py --no-embeddings

Output:
    data/gravity/signals/signals_state.json (canonical state)
    data/gravity/signals/signals_snapshot_YYYY-MM-DD.json (daily snapshots)
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from utils.signal_tracker import SignalTracker


def find_available_dates(dual_feed_dir: Path, days: int = None) -> list:
    """
    Find available dual feed dates.
    
    Args:
        dual_feed_dir: Directory containing dual feed files
        days: If set, return only last N days
    
    Returns:
        List of date strings in chronological order
    """
    files = sorted(dual_feed_dir.glob("dual_feed_*.json"))
    
    dates = []
    for f in files:
        # Extract date from filename
        name = f.stem  # dual_feed_2026-02-09
        if name.startswith('dual_feed_'):
            date_str = name[10:]  # 2026-02-09
            if len(date_str) == 10:  # YYYY-MM-DD
                dates.append(date_str)
    
    dates = sorted(dates)
    
    if days and len(dates) > days:
        dates = dates[-days:]
    
    return dates


def print_signal_summary(tracker: SignalTracker, stats: dict, verbose: bool = False):
    """Print summary of signal tracking results."""
    summary = tracker.get_signal_summary()
    
    print(f"\n{'='*60}")
    print(f"SIGNAL TRACKING RESULTS - {stats.get('date', 'unknown')}")
    print(f"{'='*60}")
    
    print(f"\nItems processed: {stats.get('items_processed', 0)}")
    print(f"Signals created: {stats.get('signals_created', 0)}")
    print(f"Signals updated: {stats.get('signals_updated', 0)}")
    
    print(f"\nTotal signals: {summary['total']}")
    print(f"Active signals: {summary['active']}")
    print(f"By status:")
    for status, count in sorted(summary['by_status'].items()):
        print(f"  {status}: {count}")
    
    # Top signals
    active = tracker.get_active_signals()[:5]
    if active:
        print(f"\nTop 5 signals (by confidence):")
        for i, s in enumerate(active):
            m = s.metrics
            print(f"  {i+1}. [{s.status.upper()}] {s.name}")
            print(f"      mentions_7d={m.mentions_7d}, velocity={m.velocity:.2f}, conf={m.confidence:.2f}")
            if verbose and s.profile.example_titles:
                print(f"      recent: {s.profile.example_titles[-1][:50]}...")
    
    # Link details
    if verbose and stats.get('links'):
        print(f"\nCluster→Signal links:")
        for link in stats['links'][:10]:
            if link.get('new'):
                print(f"  [NEW] {link['cluster_id'][:8]} → {link['signal_name']}")
            else:
                print(f"  [LINK] {link['cluster_id'][:8]} → {link['signal_name']} (score={link['match_score']:.2f})")


def main():
    parser = argparse.ArgumentParser(
        description='Generate/update signals from dual feed THEME clusters'
    )
    parser.add_argument('--date', type=str, help='Process specific date (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, default=1, help='Process last N days (default: 1)')
    parser.add_argument('--no-embeddings', action='store_true', help='Disable embeddings (overlap-only mode)')
    parser.add_argument('--reset', action='store_true', help='Reset signals state before processing')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()
    
    dual_feed_dir = Path(__file__).parent.parent / "data" / "gravity"
    signals_dir = dual_feed_dir / "signals"
    
    print(f"\n{'='*60}")
    print("SIGNAL PERSISTENCE ENGINE")
    print(f"{'='*60}\n")
    
    # Reset if requested
    if args.reset:
        state_file = signals_dir / "signals_state.json"
        if state_file.exists():
            state_file.unlink()
            print("Reset: signals_state.json deleted")
    
    # Initialize tracker
    tracker = SignalTracker(
        signals_dir=signals_dir,
        use_embeddings=not args.no_embeddings,
    )
    
    # Determine dates to process
    if args.date:
        dates = [args.date]
    else:
        dates = find_available_dates(dual_feed_dir, args.days)
    
    if not dates:
        print("No dual feed files found!")
        return 1
    
    print(f"Processing {len(dates)} date(s): {dates[0]} to {dates[-1]}" if len(dates) > 1 else f"Processing date: {dates[0]}")
    print(f"Embeddings: {'enabled' if tracker.embedding_helper and tracker.embedding_helper.available else 'disabled (overlap-only)'}")
    print()
    
    # Process each date
    all_stats = tracker.process_days(dates, dual_feed_dir)
    
    # Print summary for last day
    if all_stats:
        print_signal_summary(tracker, all_stats[-1], args.verbose)
    
    print(f"\nOutput files:")
    print(f"  State: {tracker.state_file}")
    for date in dates:
        snapshot = tracker.snapshot_file(date)
        if snapshot.exists():
            print(f"  Snapshot: {snapshot}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
