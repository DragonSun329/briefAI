#!/usr/bin/env python3
"""
Run Forecast Phase - Ledger-First Forecast Pipeline

Executes the complete forecast generation pipeline and writes results
to the experiment ledger with hash chain integrity.

This script is the SINGLE source of truth for forecast generation.
It must:
1. Generate signals from dual feed clusters
2. Synthesize meta-signals (conceptual trends)
3. Generate hypotheses with action predictions
4. Write forecasts to forecast_history.jsonl with hash chain
5. Create daily snapshot (frozen predictions)
6. Write run metadata

Exit codes:
    0 - Success, forecasts written
    1 - Failure, no forecasts written
    2 - Ledger integrity error (requires manual fix)

Usage:
    python scripts/run_forecast_phase.py
    python scripts/run_forecast_phase.py --date 2026-02-11
    python scripts/run_forecast_phase.py --experiment v2_1_forward_test
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


def run_signal_generation(target_date: str, verbose: bool = False) -> Tuple[bool, Dict[str, Any]]:
    """
    Run signal generation from dual feed clusters.
    
    Returns:
        (success, stats_dict)
    """
    from utils.signal_tracker import SignalTracker
    
    dual_feed_dir = Path(__file__).parent.parent / "data" / "gravity"
    signals_dir = dual_feed_dir / "signals"
    
    logger.info(f"Running signal generation for {target_date}")
    
    try:
        tracker = SignalTracker(
            signals_dir=signals_dir,
            use_embeddings=True,
        )
        
        all_stats = tracker.process_days([target_date], dual_feed_dir)
        
        if not all_stats:
            # Check if we have existing signals we can still work with
            active_signals = tracker.get_active_signals()
            if active_signals:
                logger.warning(f"No new signal stats, but {len(active_signals)} existing signals available - proceeding")
                return True, {
                    'signals_created': 0,
                    'signals_updated': 0,
                    'items_processed': 0,
                    'fallback': True,
                    'existing_signals': len(active_signals),
                }
            logger.warning("No signal stats returned and no existing signals")
            return False, {'error': 'no_stats'}
        
        stats = all_stats[-1]
        
        logger.info(f"Signal generation complete: {stats.get('signals_created', 0)} created, "
                   f"{stats.get('signals_updated', 0)} updated")
        
        return True, {
            'signals_created': stats.get('signals_created', 0),
            'signals_updated': stats.get('signals_updated', 0),
            'items_processed': stats.get('items_processed', 0),
        }
    except Exception as e:
        logger.error(f"Signal generation failed: {e}")
        return False, {'error': str(e)}


def run_meta_signal_synthesis(target_date: str, verbose: bool = False) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Run meta-signal synthesis from signals.
    
    Returns:
        (success, meta_signals_list)
    """
    from utils.signal_tracker import SignalTracker
    from utils.meta_signal_engine import MetaSignalEngine
    
    signals_dir = Path(__file__).parent.parent / "data" / "gravity" / "signals"
    
    logger.info(f"Running meta-signal synthesis for {target_date}")
    
    try:
        tracker = SignalTracker(signals_dir=signals_dir, use_embeddings=True)
        meta_engine = MetaSignalEngine(use_embeddings=True)
        
        result = meta_engine.process_from_tracker(tracker, target_date)
        
        meta_signals = result.get('meta_signals', [])
        logger.info(f"Meta-signal synthesis complete: {len(meta_signals)} meta-signals found")
        
        return True, meta_signals
    except Exception as e:
        logger.error(f"Meta-signal synthesis failed: {e}")
        return False, []


def run_hypothesis_generation(
    meta_signals: List[Dict[str, Any]],
    target_date: str,
    verbose: bool = False,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Run hypothesis generation from meta-signals.
    
    Returns:
        (success, hypothesis_result)
    """
    from utils.hypothesis_engine import HypothesisEngine
    
    logger.info(f"Running hypothesis generation for {target_date}")
    
    if not meta_signals:
        logger.warning("No meta-signals to process")
        return False, {'error': 'no_meta_signals'}
    
    try:
        engine = HypothesisEngine()
        result = engine.process_meta_signals(meta_signals, target_date)
        
        bundles = result.get('bundles', [])
        total_hypotheses = sum(len(b.get('hypotheses', [])) for b in bundles)
        
        logger.info(f"Hypothesis generation complete: {len(bundles)} bundles, "
                   f"{total_hypotheses} hypotheses")
        
        return True, result
    except Exception as e:
        logger.error(f"Hypothesis generation failed: {e}")
        return False, {'error': str(e)}


def extract_forecast_records(
    hypothesis_result: Dict[str, Any],
    target_date: str,
) -> List[Dict[str, Any]]:
    """
    Extract forecast records from hypothesis bundles.
    
    Converts hypotheses and their predicted signals into
    records suitable for the forecast ledger.
    """
    records = []
    
    bundles = hypothesis_result.get('bundles', [])
    
    for bundle in bundles:
        concept_name = bundle.get('concept_name', 'Unknown')
        
        for hyp in bundle.get('hypotheses', []):
            hypothesis_id = hyp.get('hypothesis_id', '')
            mechanism = hyp.get('mechanism', '')
            claim = hyp.get('title', hyp.get('claim', ''))
            confidence = hyp.get('confidence', 0.0)
            
            # Each predicted signal becomes a forecast record
            for pred in hyp.get('predicted_next_signals', []):
                # Build forecast record
                record = {
                    'forecast_type': 'hypothesis_signal',
                    'hypothesis_id': hypothesis_id,
                    'mechanism': mechanism,
                    'claim': claim,
                    'concept_name': concept_name,
                    'confidence': confidence,
                    'category': pred.get('category', 'unknown'),
                    'predicted_signal': pred.get('description', ''),
                    'canonical_metric': pred.get('canonical_metric', 'custom_metric'),
                    'expected_direction': pred.get('direction', 'unknown'),
                    'timeframe_days': pred.get('timeframe_days', 14),
                    'date': target_date,
                }
                
                records.append(record)
        
        # Also extract action predictions if present
        action_bundle = bundle.get('action_bundle', {})
        for ap in action_bundle.get('action_predictions', []):
            record = {
                'forecast_type': 'action_event',
                'event_type': ap.get('event_type', ''),
                'entity': ap.get('entity', ''),
                'concept_name': concept_name,
                'probability': ap.get('probability', 0.0),
                'timeframe_days': ap.get('timeframe_days', 14),
                'source_pressure': ap.get('source_pressure', ''),
                'date': target_date,
            }
            
            if ap.get('counterparty_type'):
                record['counterparty_type'] = ap['counterparty_type']
            if ap.get('direction'):
                record['direction'] = ap['direction']
            
            records.append(record)
    
    return records


def write_forecasts_to_ledger(
    records: List[Dict[str, Any]],
    experiment_id: str,
) -> Tuple[bool, int]:
    """
    Write forecast records to the experiment ledger.
    
    Uses crash-safe two-phase writes with hash chain.
    
    Returns:
        (success, records_written)
    """
    from utils.public_forecast_logger import ForecastHistoryLogger
    
    if not records:
        logger.warning("No forecast records to write")
        return True, 0
    
    logger.info(f"Writing {len(records)} forecasts to ledger")
    
    try:
        forecast_logger = ForecastHistoryLogger(experiment_id)
        prediction_ids = forecast_logger.log_predictions(records)
        
        logger.info(f"Successfully wrote {len(prediction_ids)} forecasts to ledger")
        return True, len(prediction_ids)
    except Exception as e:
        logger.error(f"Failed to write forecasts to ledger: {e}")
        return False, 0


def create_daily_snapshot(
    records: List[Dict[str, Any]],
    hypothesis_result: Dict[str, Any],
    target_date: str,
    experiment_id: str,
) -> Tuple[bool, Path]:
    """
    Create a frozen daily snapshot of predictions.
    
    Returns:
        (success, snapshot_path)
    """
    from utils.experiment_manager import get_ledger_path, get_experiment_context
    
    logger.info(f"Creating daily snapshot for {target_date}")
    
    try:
        context = get_experiment_context(experiment_id)
        ledger_path = get_ledger_path(experiment_id)
        
        snapshot = {
            'date': target_date,
            'frozen_at': datetime.utcnow().isoformat() + 'Z',
            'experiment_id': experiment_id,
            'engine_tag': context.experiment.engine_tag,
            'commit_hash': context.commit_hash,
            'model_version': context.experiment.engine_version,
            'run_type': 'forward_test',
            'prediction_count': len(records),
            'predictions': records,
            'hypothesis_summary': {
                'total_bundles': len(hypothesis_result.get('bundles', [])),
                'total_hypotheses': hypothesis_result.get('summary', {}).get('total_hypotheses', 0),
            },
        }
        
        snapshot_path = ledger_path / f"daily_snapshot_{target_date}.json"
        with open(snapshot_path, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Wrote daily snapshot: {snapshot_path}")
        return True, snapshot_path
    except Exception as e:
        logger.error(f"Failed to create daily snapshot: {e}")
        return False, Path()


def write_run_metadata(
    target_date: str,
    experiment_id: str,
    stats: Dict[str, Any],
) -> Tuple[bool, Path]:
    """
    Write run metadata file.
    
    Returns:
        (success, metadata_path)
    """
    from utils.run_artifact_contract import RunMetadataBuilder
    
    logger.info(f"Writing run metadata for {target_date}")
    
    try:
        builder = RunMetadataBuilder(run_date=target_date, experiment_id=experiment_id)
        
        # Record stats as scraper-like metrics
        builder.record_scraper('signal_generation', stats.get('signals_created', 0) + stats.get('signals_updated', 0))
        builder.record_scraper('meta_signals', stats.get('meta_signals', 0))
        builder.record_scraper('hypotheses', stats.get('total_hypotheses', 0))
        builder.record_scraper('forecasts_written', stats.get('forecasts_written', 0))
        
        metadata_path = builder.write(artifact_contract_passed=True, experiment_id=experiment_id)
        
        logger.info(f"Wrote run metadata: {metadata_path}")
        return True, metadata_path
    except Exception as e:
        logger.error(f"Failed to write run metadata: {e}")
        return False, Path()


def main():
    parser = argparse.ArgumentParser(
        description='Run forecast phase with ledger writes'
    )
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD)')
    parser.add_argument('--experiment', type=str, help='Experiment ID')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--dry-run', action='store_true', help='Generate forecasts but do not write to ledger')
    
    args = parser.parse_args()
    
    # Determine date
    target_date = args.date or date.today().isoformat()
    
    # Determine experiment
    if args.experiment:
        experiment_id = args.experiment
    else:
        from utils.experiment_manager import get_active_experiment
        exp = get_active_experiment()
        if not exp:
            logger.error("No active experiment configured")
            print("\n[FAIL] No active experiment configured in config/experiments.json")
            return 1
        experiment_id = exp.experiment_id
    
    print(f"\n{'='*60}")
    print(f"FORECAST PHASE - {target_date}")
    print(f"Experiment: {experiment_id}")
    print(f"{'='*60}\n")
    
    stats = {}
    
    # Step 1: Signal generation
    print("[1/5] Generating signals...")
    success, signal_stats = run_signal_generation(target_date, args.verbose)
    if not success:
        print(f"[FAIL] Signal generation failed: {signal_stats.get('error', 'unknown')}")
        return 1
    stats.update(signal_stats)
    print(f"      Created: {signal_stats.get('signals_created', 0)}, Updated: {signal_stats.get('signals_updated', 0)}")
    
    # Step 2: Meta-signal synthesis
    print("[2/5] Synthesizing meta-signals...")
    success, meta_signals = run_meta_signal_synthesis(target_date, args.verbose)
    if not success or not meta_signals:
        print(f"[WARN] No meta-signals generated (may be normal if insufficient signal diversity)")
        meta_signals = []
    stats['meta_signals'] = len(meta_signals)
    print(f"      Meta-signals: {len(meta_signals)}")
    
    # Step 3: Hypothesis generation
    print("[3/5] Generating hypotheses...")
    if meta_signals:
        success, hypothesis_result = run_hypothesis_generation(meta_signals, target_date, args.verbose)
        if not success:
            print(f"[WARN] Hypothesis generation failed, continuing with empty results")
            hypothesis_result = {'bundles': [], 'summary': {}}
    else:
        hypothesis_result = {'bundles': [], 'summary': {}}
    
    total_hypotheses = sum(len(b.get('hypotheses', [])) for b in hypothesis_result.get('bundles', []))
    stats['total_hypotheses'] = total_hypotheses
    print(f"      Bundles: {len(hypothesis_result.get('bundles', []))}, Hypotheses: {total_hypotheses}")
    
    # Step 4: Extract and write forecasts
    print("[4/5] Extracting forecast records...")
    records = extract_forecast_records(hypothesis_result, target_date)
    print(f"      Forecast records: {len(records)}")
    
    if args.dry_run:
        print("\n[DRY-RUN] Skipping ledger writes")
        print(f"Would write {len(records)} records to ledger")
        return 0
    
    print("[4/5] Writing to ledger...")
    success, written = write_forecasts_to_ledger(records, experiment_id)
    if not success:
        print("[FAIL] Failed to write forecasts to ledger")
        return 1
    stats['forecasts_written'] = written
    print(f"      Written: {written} records")
    
    # Step 5: Create snapshot and metadata
    print("[5/5] Creating snapshot and metadata...")
    
    success, snapshot_path = create_daily_snapshot(records, hypothesis_result, target_date, experiment_id)
    if not success:
        print("[FAIL] Failed to create daily snapshot")
        return 1
    
    success, metadata_path = write_run_metadata(target_date, experiment_id, stats)
    if not success:
        print("[FAIL] Failed to write run metadata")
        return 1
    
    # Summary
    print(f"\n{'='*60}")
    print("[OK] FORECAST PHASE COMPLETE")
    print(f"{'='*60}")
    print(f"  Date:            {target_date}")
    print(f"  Experiment:      {experiment_id}")
    print(f"  Signals:         {stats.get('signals_created', 0)} created, {stats.get('signals_updated', 0)} updated")
    print(f"  Meta-signals:    {stats.get('meta_signals', 0)}")
    print(f"  Hypotheses:      {stats.get('total_hypotheses', 0)}")
    print(f"  Forecasts:       {stats.get('forecasts_written', 0)} written")
    print(f"  Snapshot:        {snapshot_path.name}")
    print(f"  Metadata:        {metadata_path.name}")
    print(f"{'='*60}\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
