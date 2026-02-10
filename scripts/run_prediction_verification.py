#!/usr/bin/env python
"""
Prediction Verification Scheduler v2.0 - Evidence Engine Integration.

Part of briefAI Gravity Engine v2.8: Evidence-Based Belief Updates.

This script:
1. Loads all pending predictions
2. Checks which are due for evaluation
3. Collects observed metric data
4. Evaluates predictions and produces verdicts
5. Generates graded evidence (NEW v2.0)
6. Updates hypothesis beliefs (NEW v2.0)
7. Updates prediction records
8. Generates calibration report

Usage:
    python scripts/run_prediction_verification.py
    python scripts/run_prediction_verification.py --force
    python scripts/run_prediction_verification.py --debug
    python scripts/run_prediction_verification.py --dry-run
    python scripts/run_prediction_verification.py --no-evidence  # Skip evidence/beliefs
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from utils.prediction_verifier import (
    PredictionStore,
    PredictionRecord,
    PredictionStatus,
    PredictionVerdict,
    evaluate_prediction,
    evaluate_prediction_with_evidence,
    print_prediction_summary,
)
from utils.metric_observer import (
    UnifiedMetricObserver,
    observe_metric,
)
from utils.calibration_engine import (
    CalibrationEngine,
    format_calibration_report,
)


# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"


# =============================================================================
# VERIFICATION RUNNER v2.0
# =============================================================================

class VerificationRunner:
    """
    Runs prediction verification workflow with Evidence Engine integration.
    
    Steps:
    1. Load due predictions
    2. Observe metrics for each
    3. Evaluate and produce verdicts
    4. Generate evidence results (v2.0)
    5. Update hypothesis beliefs (v2.0)
    6. Update records
    7. Generate calibration report
    """
    
    def __init__(
        self,
        data_dir: Path = None,
        force: bool = False,
        dry_run: bool = False,
        debug: bool = False,
        enable_evidence: bool = True,
    ):
        """
        Initialize verification runner.
        
        Args:
            data_dir: Base data directory
            force: Force evaluation of all pending predictions
            dry_run: Don't update records, just show what would happen
            debug: Enable debug logging
            enable_evidence: Enable evidence generation and belief updates
        """
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.force = force
        self.dry_run = dry_run
        self.debug = debug
        self.enable_evidence = enable_evidence
        
        # Initialize components
        self.store = PredictionStore(self.data_dir / "predictions")
        self.observer = UnifiedMetricObserver(self.data_dir)
        self.calibration = CalibrationEngine(self.data_dir / "metrics")
        
        # Evidence components (lazy loaded)
        self._evidence_store = None
        self._belief_updater = None
        self._hypothesis_priors = {}
        
        # Configure logging
        if debug:
            logger.remove()
            logger.add(sys.stderr, level="DEBUG")
        else:
            logger.remove()
            logger.add(sys.stderr, level="INFO")
    
    def _init_evidence_components(self):
        """Lazily initialize evidence engine components."""
        if not self.enable_evidence:
            return False
        
        try:
            from utils.evidence_engine import EvidenceStore
            from utils.belief_updater import BeliefUpdater
            
            self._evidence_store = EvidenceStore(self.data_dir / "predictions")
            self._belief_updater = BeliefUpdater(self.data_dir / "predictions")
            
            logger.debug("Evidence engine components initialized")
            return True
            
        except ImportError as e:
            logger.warning(f"Evidence engine not available: {e}")
            self.enable_evidence = False
            return False
    
    def run(self) -> dict:
        """
        Run verification workflow.
        
        Returns:
            Summary dict with counts and results
        """
        now = datetime.now()
        
        logger.info(f"Starting prediction verification at {now.isoformat()}")
        
        # Initialize evidence components if enabled
        if self.enable_evidence:
            self._init_evidence_components()
        
        # Load predictions
        if self.force:
            pending = self.store.load_pending_records()
            logger.info(f"Force mode: evaluating all {len(pending)} pending predictions")
        else:
            pending = self.store.load_due_records(now)
            logger.info(f"Found {len(pending)} predictions due for evaluation")
        
        if not pending:
            logger.info("No predictions to evaluate")
            return {
                'evaluated': 0,
                'verified_true': 0,
                'verified_false': 0,
                'inconclusive': 0,
                'data_missing': 0,
                'evidence_generated': 0,
                'beliefs_updated': 0,
            }
        
        # Collect hypothesis priors for belief updates
        self._collect_hypothesis_priors(pending)
        
        # Evaluate each prediction
        results = {
            'evaluated': 0,
            'verified_true': 0,
            'verified_false': 0,
            'inconclusive': 0,
            'data_missing': 0,
            'evidence_generated': 0,
            'beliefs_updated': 0,
        }
        
        evidence_results = []
        
        for record in pending:
            try:
                evaluated_record, evidence = self._evaluate_record_with_evidence(record)
                
                if self.dry_run:
                    logger.info(f"[DRY RUN] Would evaluate: {record.prediction_id}")
                    print_prediction_summary(evaluated_record)
                    if evidence:
                        logger.info(f"  Evidence: {evidence.direction} (score={evidence.evidence_score:.2f})")
                else:
                    self.store.update_record(evaluated_record)
                    results['evaluated'] += 1
                    results[evaluated_record.verdict] = results.get(evaluated_record.verdict, 0) + 1
                    
                    # Collect evidence for batch belief update
                    if evidence:
                        evidence_results.append(evidence)
                        results['evidence_generated'] += 1
                    
            except Exception as e:
                logger.error(f"Failed to evaluate {record.prediction_id}: {e}")
                if self.debug:
                    import traceback
                    traceback.print_exc()
        
        # Save evidence and update beliefs
        if not self.dry_run and evidence_results:
            self._process_evidence(evidence_results, results)
        
        # Generate calibration report
        if not self.dry_run and results['evaluated'] > 0:
            self._generate_calibration_report()
        
        # Print summary
        self._print_summary(results)
        
        return results
    
    def _collect_hypothesis_priors(self, records: List[PredictionRecord]):
        """Collect hypothesis prior information for belief updates."""
        for record in records:
            hyp_id = record.hypothesis_id
            if hyp_id not in self._hypothesis_priors:
                self._hypothesis_priors[hyp_id] = {
                    'meta_id': record.meta_id,
                    'prior_confidence': record.confidence_at_prediction or 0.5,
                    # TODO: Get review_required from hypothesis store
                    'review_required': False,
                    'weakly_validated': False,
                }
    
    def _evaluate_record_with_evidence(
        self,
        record: PredictionRecord,
    ) -> tuple:
        """
        Evaluate a single prediction record and generate evidence.
        
        Args:
            record: Prediction to evaluate
        
        Returns:
            Tuple of (evaluated PredictionRecord, EvidenceResult or None)
        """
        logger.debug(f"Evaluating prediction {record.prediction_id}")
        logger.debug(f"  Entity: {record.entity}")
        logger.debug(f"  Metric: {record.canonical_metric}")
        logger.debug(f"  Expected: {record.expected_direction}")
        
        # Get created_at as datetime
        created_at = datetime.fromisoformat(record.created_at)
        
        # Observe metrics
        baseline, current = self.observer.observe_for_prediction(
            entity=record.entity,
            metric=record.canonical_metric,
            window_days=record.window_days,
            created_at=created_at,
        )
        
        logger.debug(f"  Observed: baseline={baseline}, current={current}")
        
        # Evaluate with evidence generation
        if self.enable_evidence:
            evaluated, evidence = evaluate_prediction_with_evidence(record, baseline, current)
        else:
            evaluated = evaluate_prediction(record, baseline, current)
            evidence = None
        
        logger.debug(f"  Verdict: {evaluated.verdict}")
        if evaluated.percent_change is not None:
            logger.debug(f"  Change: {evaluated.percent_change:.1%}")
        if evidence:
            logger.debug(f"  Evidence: {evidence.direction} (score={evidence.evidence_score:.2f})")
        
        return evaluated, evidence
    
    def _process_evidence(self, evidence_results: list, results: dict):
        """Process evidence results and update beliefs."""
        if not self._evidence_store or not self._belief_updater:
            return
        
        logger.info(f"Processing {len(evidence_results)} evidence results...")
        
        # Save evidence log
        self._evidence_store.save_evidence_batch(evidence_results)
        
        # Update beliefs
        updated_beliefs = self._belief_updater.process_evidence_batch(
            evidence_results,
            self._hypothesis_priors,
        )
        
        results['beliefs_updated'] = len(updated_beliefs)
        
        # Log belief changes
        for hyp_id, state in updated_beliefs.items():
            change = state.confidence_change
            direction = "↑" if change > 0 else "↓" if change < 0 else "→"
            logger.info(
                f"Belief {hyp_id}: {state.prior_confidence:.2f} {direction} "
                f"{state.posterior_confidence:.2f} ({change:+.3f})"
            )
    
    def _generate_calibration_report(self):
        """Generate and save calibration report."""
        logger.info("Generating calibration report...")
        
        # Load all records
        all_records = self.store.load_all_records()
        record_dicts = [r.to_dict() for r in all_records]
        
        # Compute report
        report = self.calibration.compute_report(record_dicts)
        
        # Save report
        output_path = self.calibration.save_report(report)
        
        # Print summary
        print("\n" + format_calibration_report(report))
        
        # Print belief summary if available
        if self._belief_updater:
            self._print_belief_summary()
    
    def _print_belief_summary(self):
        """Print belief state summary."""
        summary = self._belief_updater.get_belief_summary()
        
        print("\n" + "-" * 40)
        print("BELIEF STATE SUMMARY")
        print("-" * 40)
        print(f"Total hypotheses: {summary['total_hypotheses']}")
        if summary['average_posterior']:
            print(f"Average posterior: {summary['average_posterior']:.1%}")
            print(f"Strengthened: {summary['strengthened_count']}")
            print(f"Weakened: {summary['weakened_count']}")
            print(f"Unchanged: {summary['unchanged_count']}")
    
    def _print_summary(self, results: dict):
        """Print verification summary."""
        print("\n" + "=" * 60)
        print("VERIFICATION SUMMARY (v2.0 - Evidence Engine)")
        print("=" * 60)
        print(f"Evaluated: {results['evaluated']}")
        print(f"Verified True: {results.get('verified_true', 0)}")
        print(f"Verified False: {results.get('verified_false', 0)}")
        print(f"Inconclusive: {results.get('inconclusive', 0)}")
        print(f"Data Missing: {results.get('data_missing', 0)}")
        print("-" * 40)
        print(f"Evidence Generated: {results.get('evidence_generated', 0)}")
        print(f"Beliefs Updated: {results.get('beliefs_updated', 0)}")
        print("=" * 60)


# =============================================================================
# CLI
# =============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run prediction verification workflow with Evidence Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Normal run - evaluate due predictions with evidence
    python scripts/run_prediction_verification.py
    
    # Force evaluate all pending predictions
    python scripts/run_prediction_verification.py --force
    
    # Dry run - show what would happen
    python scripts/run_prediction_verification.py --dry-run
    
    # Debug mode with verbose logging
    python scripts/run_prediction_verification.py --debug
    
    # Skip evidence generation (legacy mode)
    python scripts/run_prediction_verification.py --no-evidence
        """
    )
    
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Force evaluation of all pending predictions (not just due ones)',
    )
    
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Show what would be evaluated without making changes',
    )
    
    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='Enable debug logging',
    )
    
    parser.add_argument(
        '--data-dir',
        type=Path,
        default=None,
        help='Override data directory',
    )
    
    parser.add_argument(
        '--show-stats',
        action='store_true',
        help='Show prediction statistics and exit',
    )
    
    parser.add_argument(
        '--show-beliefs',
        action='store_true',
        help='Show belief states and exit',
    )
    
    parser.add_argument(
        '--no-evidence',
        action='store_true',
        help='Skip evidence generation and belief updates (legacy mode)',
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    # Just show stats if requested
    if args.show_stats:
        store = PredictionStore(args.data_dir or DEFAULT_DATA_DIR / "predictions")
        stats = store.get_statistics()
        
        print("\nPREDICTION STORE STATISTICS")
        print("=" * 40)
        print(f"Total predictions: {stats['total']}")
        print(f"Pending: {stats['pending']}")
        print(f"Evaluated: {stats['evaluated']}")
        print("\nVerdicts:")
        for verdict, count in stats.get('verdicts', {}).items():
            print(f"  {verdict}: {count}")
        print()
        return
    
    # Show beliefs if requested
    if args.show_beliefs:
        try:
            from utils.belief_updater import BeliefUpdater
            
            updater = BeliefUpdater(args.data_dir or DEFAULT_DATA_DIR / "predictions")
            summary = updater.get_belief_summary()
            
            print("\nBELIEF STATE SUMMARY")
            print("=" * 40)
            print(f"Total hypotheses: {summary['total_hypotheses']}")
            if summary['average_posterior']:
                print(f"Average posterior: {summary['average_posterior']:.1%}")
                print(f"Range: {summary['min_posterior']:.1%} - {summary['max_posterior']:.1%}")
                print(f"Strengthened: {summary['strengthened_count']}")
                print(f"Weakened: {summary['weakened_count']}")
            print()
            
        except ImportError:
            print("Evidence engine not available")
        return
    
    # Run verification
    runner = VerificationRunner(
        data_dir=args.data_dir,
        force=args.force,
        dry_run=args.dry_run,
        debug=args.debug,
        enable_evidence=not args.no_evidence,
    )
    
    results = runner.run()
    
    # Exit with error if no predictions evaluated (for CI)
    if results['evaluated'] == 0 and not args.dry_run:
        sys.exit(0)  # Not an error, just nothing to do


if __name__ == "__main__":
    main()
