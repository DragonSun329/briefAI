"""
Prediction Integration - Connects Hypothesis Engine to Verification Engine.

Part of briefAI Prediction Verification Engine.

This module provides the bridge between hypothesis generation and
prediction tracking, automatically registering predictions for
later verification.

Usage:
    from utils.prediction_integration import register_predictions
    
    # After generating hypotheses
    register_predictions(hypothesis_bundles)
"""

import sys
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from loguru import logger


# =============================================================================
# INTEGRATION FUNCTIONS
# =============================================================================

def register_predictions(
    bundles: List[Dict[str, Any]],
    data_dir: Path = None,
    skip_unmeasurable: bool = True,
) -> int:
    """
    Register predictions from hypothesis bundles for later verification.
    
    This is the main integration point. Call this after hypothesis
    generation to automatically track all predictions.
    
    Args:
        bundles: List of MetaHypothesisBundle dicts
        data_dir: Optional data directory override
        skip_unmeasurable: Skip predictions with measurable=False
    
    Returns:
        Number of predictions registered
    """
    # Import here to avoid circular imports
    from utils.prediction_verifier import (
        PredictionStore,
        register_predictions_from_bundle,
    )
    
    if data_dir is None:
        data_dir = Path(__file__).parent.parent / "data"
    
    store = PredictionStore(data_dir / "predictions")
    
    total_registered = 0
    
    for bundle in bundles:
        try:
            records = register_predictions_from_bundle(bundle, store)
            total_registered += len(records)
        except Exception as e:
            logger.warning(f"Failed to register predictions for bundle {bundle.get('meta_id', '?')}: {e}")
    
    if total_registered > 0:
        logger.info(f"Registered {total_registered} predictions from {len(bundles)} bundles")
    
    return total_registered


def register_predictions_from_file(
    hypothesis_file: Path,
    data_dir: Path = None,
) -> int:
    """
    Register predictions from a hypothesis output file.
    
    Args:
        hypothesis_file: Path to hypotheses_YYYY-MM-DD.json
        data_dir: Optional data directory override
    
    Returns:
        Number of predictions registered
    """
    import json
    
    with open(hypothesis_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    bundles = data.get('bundles', [])
    
    return register_predictions(bundles, data_dir)


def get_prediction_status_for_hypothesis(
    hypothesis_id: str,
    data_dir: Path = None,
) -> Dict[str, Any]:
    """
    Get prediction status for a specific hypothesis.
    
    Args:
        hypothesis_id: ID of the hypothesis
        data_dir: Optional data directory override
    
    Returns:
        Dict with prediction status summary
    """
    from utils.prediction_verifier import PredictionStore
    
    if data_dir is None:
        data_dir = Path(__file__).parent.parent / "data"
    
    store = PredictionStore(data_dir / "predictions")
    records = store.get_records_by_hypothesis(hypothesis_id)
    
    if not records:
        return {
            'hypothesis_id': hypothesis_id,
            'predictions_count': 0,
            'status': 'no_predictions',
        }
    
    # Summarize
    verdicts = {}
    for r in records:
        verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
    
    # Calculate overall status
    pending_count = verdicts.get('pending', 0)
    verified_true = verdicts.get('verified_true', 0)
    verified_false = verdicts.get('verified_false', 0)
    
    if pending_count == len(records):
        status = 'pending'
    elif verified_true > verified_false:
        status = 'mostly_true'
    elif verified_false > verified_true:
        status = 'mostly_false'
    else:
        status = 'mixed'
    
    return {
        'hypothesis_id': hypothesis_id,
        'predictions_count': len(records),
        'verdicts': verdicts,
        'status': status,
        'accuracy': verified_true / (verified_true + verified_false) if (verified_true + verified_false) > 0 else None,
    }


def enrich_hypothesis_with_verification(
    hypothesis: Dict[str, Any],
    data_dir: Path = None,
) -> Dict[str, Any]:
    """
    Enrich a hypothesis with verification status.
    
    Adds prediction_status, prediction_verdict, and percent_change
    fields to the hypothesis.
    
    Args:
        hypothesis: Hypothesis dict
        data_dir: Optional data directory override
    
    Returns:
        Enriched hypothesis dict
    """
    from utils.prediction_verifier import PredictionStore
    
    if data_dir is None:
        data_dir = Path(__file__).parent.parent / "data"
    
    hypothesis_id = hypothesis.get('hypothesis_id', '')
    
    if not hypothesis_id:
        return hypothesis
    
    store = PredictionStore(data_dir / "predictions")
    records = store.get_records_by_hypothesis(hypothesis_id)
    
    # Enrich each predicted_next_signal
    for pred in hypothesis.get('predicted_next_signals', []):
        # Find matching record
        matching = [
            r for r in records
            if r.canonical_metric == pred.get('canonical_metric')
            and r.category == pred.get('category')
        ]
        
        if matching:
            record = matching[0]
            pred['prediction_status'] = record.status
            pred['prediction_verdict'] = record.verdict
            pred['percent_change'] = record.percent_change
            pred['verification_date'] = record.evaluated_at
    
    return hypothesis


def enrich_bundle_with_verification(
    bundle: Dict[str, Any],
    data_dir: Path = None,
) -> Dict[str, Any]:
    """
    Enrich a hypothesis bundle with verification status.
    
    Args:
        bundle: MetaHypothesisBundle dict
        data_dir: Optional data directory override
    
    Returns:
        Enriched bundle dict
    """
    for hypothesis in bundle.get('hypotheses', []):
        enrich_hypothesis_with_verification(hypothesis, data_dir)
    
    return bundle


# =============================================================================
# HOOK FOR GENERATE_SIGNALS.PY
# =============================================================================

def on_hypotheses_generated(
    result: Dict[str, Any],
    data_dir: Path = None,
) -> None:
    """
    Hook to be called after hypotheses are generated.
    
    This should be called from generate_signals.py when --with-hypotheses
    is used.
    
    Args:
        result: The result dict from HypothesisEngine.process_meta_signals()
        data_dir: Optional data directory override
    """
    bundles = result.get('bundles', [])
    
    if not bundles:
        logger.debug("No hypothesis bundles to register")
        return
    
    try:
        registered = register_predictions(bundles, data_dir)
        logger.info(f"PVE: Registered {registered} predictions for verification")
    except Exception as e:
        logger.warning(f"PVE: Failed to register predictions: {e}")


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI for manual prediction registration."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Register predictions from hypothesis files"
    )
    
    parser.add_argument(
        'hypothesis_file',
        type=Path,
        help='Path to hypotheses_YYYY-MM-DD.json file',
    )
    
    parser.add_argument(
        '--data-dir',
        type=Path,
        default=None,
        help='Override data directory',
    )
    
    args = parser.parse_args()
    
    if not args.hypothesis_file.exists():
        print(f"File not found: {args.hypothesis_file}")
        sys.exit(1)
    
    registered = register_predictions_from_file(args.hypothesis_file, args.data_dir)
    print(f"Registered {registered} predictions")


if __name__ == "__main__":
    main()
