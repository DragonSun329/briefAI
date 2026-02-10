#!/usr/bin/env python3
"""
Generate Signals - Signal Persistence Engine CLI

Links daily THEME clusters from dual feeds into persistent signals,
tracking momentum/velocity/acceleration across days.

Optionally synthesizes meta-signals (higher-level conceptual trends)
from the persistent signals.

Usage:
    python scripts/generate_signals.py
    python scripts/generate_signals.py --date 2026-02-09
    python scripts/generate_signals.py --days 7
    python scripts/generate_signals.py --no-embeddings
    python scripts/generate_signals.py --with-meta

Output:
    data/gravity/signals/signals_state.json (canonical state)
    data/gravity/signals/signals_snapshot_YYYY-MM-DD.json (daily snapshots)
    data/meta_signals/meta_signals_YYYY-MM-DD.json (meta-signals, if --with-meta)
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
    parser.add_argument('--with-meta', action='store_true', help='Generate meta-signals (conceptual trends)')
    parser.add_argument('--with-hypotheses', action='store_true', help='Generate hypotheses from meta-signals (implies --with-meta)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()
    
    # --with-hypotheses implies --with-meta (need meta-signals first)
    if args.with_hypotheses:
        args.with_meta = True
    
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
    
    # Optional: Generate meta-signals
    if args.with_meta:
        print(f"\n{'='*60}")
        print("META-SIGNAL SYNTHESIS (Conceptual Trends)")
        print(f"{'='*60}\n")
        
        try:
            from utils.meta_signal_engine import MetaSignalEngine
            
            meta_engine = MetaSignalEngine(use_embeddings=not args.no_embeddings)
            
            # Use the last processed date
            target_date = dates[-1] if dates else datetime.now().strftime('%Y-%m-%d')
            
            # Process signals into meta-signals
            result = meta_engine.process_from_tracker(tracker, target_date)
            
            print(f"Insights generated: {result['stats']['insights_generated']}")
            print(f"Meta-signals found: {result['stats']['meta_signals_found']}")
            
            # Print meta-signals
            if result['meta_signals']:
                print(f"\nMeta-signals (conceptual trends):")
                for i, meta in enumerate(result['meta_signals'][:5]):
                    print(f"  {i+1}. [{meta['maturity_stage'].upper()}] {meta['concept_name']}")
                    print(f"      signals={len(meta['supporting_signals'])}, "
                          f"conf={meta['concept_confidence']:.2f}, "
                          f"accel={meta['acceleration']:.2f}")
                    if args.verbose:
                        print(f"      {meta['description'][:60]}...")
            else:
                print("\nNo meta-signals detected (need more diverse signals)")
            
            print(f"\nMeta-signal output: {meta_engine.output_file(target_date)}")
            
            # Optional: Generate hypotheses from meta-signals
            if args.with_hypotheses and result['meta_signals']:
                print(f"\n{'='*60}")
                print("HYPOTHESIS ENGINE (Causal Predictions)")
                print(f"{'='*60}\n")
                
                try:
                    from utils.hypothesis_engine import HypothesisEngine
                    
                    hyp_engine = HypothesisEngine()
                    hyp_result = hyp_engine.process_meta_signals(
                        result['meta_signals'],
                        date=target_date
                    )
                    
                    print(f"Meta-signals processed: {hyp_result['summary']['total_metas']}")
                    print(f"Hypothesis bundles: {hyp_result['summary']['total_bundles']}")
                    print(f"Total hypotheses: {hyp_result['summary']['total_hypotheses']}")
                    print(f"Requiring review: {hyp_result['summary']['metas_requiring_review']}")
                    
                    if hyp_result['summary']['top_mechanisms']:
                        print(f"\nTop mechanisms:")
                        for mech, count in hyp_result['summary']['top_mechanisms'].items():
                            print(f"  {mech}: {count}")
                    
                    # Print top hypotheses
                    if hyp_result['bundles']:
                        print(f"\nTop hypotheses:")
                        for i, bundle in enumerate(hyp_result['bundles'][:3]):
                            if bundle['hypotheses']:
                                top_hyp = bundle['hypotheses'][0]
                                print(f"  {i+1}. {bundle['concept_name']}")
                                print(f"      → {top_hyp['title']} (conf={top_hyp['confidence']:.0%})")
                                print(f"      What to watch:")
                                for pred in top_hyp['predicted_next_signals'][:2]:
                                    print(f"        - [{pred['category']}] {pred['description'][:50]}...")
                    
                    print(f"\nHypothesis output: {hyp_engine.output_dir / f'hypotheses_{target_date}.json'}")
                    
                except Exception as e:
                    logger.error(f"Hypothesis generation failed: {e}")
                    if args.verbose:
                        import traceback
                        traceback.print_exc()
            
        except Exception as e:
            logger.error(f"Meta-signal generation failed: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
    
    # Standalone hypothesis generation (when --with-hypotheses but not --with-meta)
    elif args.with_hypotheses:
        print(f"\n{'='*60}")
        print("HYPOTHESIS ENGINE (Causal Predictions)")
        print(f"{'='*60}\n")
        
        try:
            from utils.hypothesis_engine import run_hypothesis_engine
            
            target_date = dates[-1] if dates else datetime.now().strftime('%Y-%m-%d')
            result = run_hypothesis_engine(date=target_date)
            
            if 'error' in result:
                print(f"Error: {result['error']}")
                print(f"Path: {result.get('path', 'unknown')}")
                print("\nHint: Run with --with-meta first to generate meta-signals.")
            else:
                print(f"Meta-signals processed: {result['summary']['total_metas']}")
                print(f"Total hypotheses: {result['summary']['total_hypotheses']}")
                
        except Exception as e:
            logger.error(f"Hypothesis generation failed: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
