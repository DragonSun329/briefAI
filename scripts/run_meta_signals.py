#!/usr/bin/env python3
"""
Run Meta-Signal Engine v2.6 to synthesize higher-level conceptual trends.

This script:
1. Loads current signals from SignalTracker
2. Synthesizes meta-signals (structural trends)
3. Outputs to data/meta_signals/meta_signals_YYYY-MM-DD.json

Part of the daily_bloomberg.ps1 pipeline.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from utils.meta_signal_engine import MetaSignalEngine
from utils.signal_tracker import SignalTracker


def main():
    """Run meta-signal synthesis."""
    date = datetime.now().strftime('%Y-%m-%d')
    logger.info(f"=== Meta-Signal Engine v2.6 - {date} ===")
    
    # Load signals
    logger.info("Loading signals from SignalTracker...")
    tracker = SignalTracker()
    active_signals = tracker.get_active_signals(exclude_dead=True)
    logger.info(f"Found {len(active_signals)} active signals")
    
    if len(active_signals) < 2:
        logger.warning("Not enough active signals for meta-signal synthesis (need >= 2)")
        return
    
    # Run meta-signal engine
    logger.info("Running meta-signal synthesis...")
    engine = MetaSignalEngine(use_embeddings=True)
    result = engine.process_from_tracker(tracker, date)
    
    # Report results
    stats = result['stats']
    logger.info(f"=== Meta-Signal Results ===")
    logger.info(f"Input signals: {stats['input_signals']}")
    logger.info(f"Meta-signals found: {stats['meta_signals_found']}")
    logger.info(f"Validated: {stats['validated']}")
    logger.info(f"Weakly validated: {stats['weakly_validated']}")
    logger.info(f"Review required: {stats['review_required']}")
    logger.info(f"Name frozen: {stats['name_frozen']}")
    
    # Show top meta-signals
    for i, meta in enumerate(result['meta_signals'][:3]):
        logger.info(f"  #{i+1}: {meta['concept_name']} "
                   f"(conf={meta['concept_confidence']:.2f}, "
                   f"signals={len(meta['supporting_signals'])}, "
                   f"status={meta['validation_status']})")
    
    logger.info(f"Output: {engine.output_file(date)}")
    logger.info("=== Meta-Signal Engine Complete ===")


if __name__ == "__main__":
    main()
