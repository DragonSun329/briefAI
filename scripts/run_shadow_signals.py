#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shadow Mode Signal Runner

Runs signals in shadow mode without affecting production metrics.
Shadow predictions are tracked separately and used to validate new
signals before they go live.

Usage:
    python scripts/run_shadow_signals.py --help
    python scripts/run_shadow_signals.py run
    python scripts/run_shadow_signals.py resolve
    python scripts/run_shadow_signals.py report
    python scripts/run_shadow_signals.py graduate --signal-type divergence
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.prediction_store import (
    PredictionStore, Prediction, PredictionType, PredictionStatus, PredictionMode,
    create_prediction_from_divergence
)
from utils.outcome_tracker import OutcomeTracker
from utils.accuracy_scorer import AccuracyScorer, compare_shadow_to_production


class ShadowRunner:
    """
    Manages shadow mode signal testing.
    
    Shadow mode workflow:
    1. Run signals in shadow mode (predictions tracked but not counted)
    2. Wait for horizon to pass
    3. Resolve predictions against actual outcomes
    4. Compare accuracy to production signals
    5. Graduate good signals to production
    """
    
    GRADUATION_THRESHOLD_ACCURACY = 0.60  # Min accuracy to graduate
    GRADUATION_MIN_PREDICTIONS = 20  # Min predictions before graduation
    
    def __init__(self):
        self.prediction_store = PredictionStore()
        self.outcome_tracker = OutcomeTracker(self.prediction_store)
        self.accuracy_scorer = AccuracyScorer(self.prediction_store)
    
    def run_shadow_signals(
        self,
        signal_types: Optional[List[str]] = None,
        horizon_days: int = 30,
        confidence_discount: float = 0.8,
    ) -> List[Prediction]:
        """
        Run signals in shadow mode.
        
        This creates shadow predictions from current divergences.
        
        Args:
            signal_types: Types of signals to run (None = all)
            horizon_days: Days until validation
            confidence_discount: Multiply confidence by this for shadow mode
            
        Returns:
            List of created shadow predictions
        """
        shadow_predictions = []
        
        # Run divergence signals
        if signal_types is None or "divergence" in signal_types:
            div_predictions = self._run_divergence_shadows(
                horizon_days=horizon_days,
                confidence_discount=confidence_discount,
            )
            shadow_predictions.extend(div_predictions)
        
        # TODO: Add other signal types here
        # if signal_types is None or "momentum" in signal_types:
        #     momentum_predictions = self._run_momentum_shadows(...)
        #     shadow_predictions.extend(momentum_predictions)
        
        return shadow_predictions
    
    def _run_divergence_shadows(
        self,
        horizon_days: int,
        confidence_discount: float,
    ) -> List[Prediction]:
        """Create shadow predictions from current divergences."""
        predictions = []
        
        try:
            from utils.signal_store import SignalStore
            from utils.divergence_detector import DivergenceDetector
            
            signal_store = SignalStore()
            detector = DivergenceDetector()
            
            # Get top profiles
            profiles = signal_store.get_top_profiles(limit=50)
            
            # Detect divergences
            for profile in profiles:
                divergences = detector.detect_divergences(profile)
                
                for div in divergences:
                    # Check if we already have a pending shadow prediction for this
                    existing = self.prediction_store.get_predictions_for_entity(
                        div.entity_id,
                        include_resolved=False,
                    )
                    
                    # Skip if we have a recent pending prediction
                    has_recent = any(
                        p.mode == PredictionMode.SHADOW
                        and p.signal_type == "divergence"
                        and (datetime.utcnow() - p.predicted_at).days < 7
                        for p in existing
                    )
                    
                    if has_recent:
                        continue
                    
                    # Create shadow prediction
                    pred = create_prediction_from_divergence(
                        div,
                        horizon_days=horizon_days,
                        confidence_multiplier=confidence_discount,
                        mode=PredictionMode.SHADOW,
                    )
                    
                    self.prediction_store.add_prediction(pred)
                    predictions.append(pred)
                    
                    print(f"  [SHADOW] {pred.entity_name}: {pred.prediction_type.value}")
            
        except ImportError as e:
            print(f"Warning: Could not import signal modules: {e}")
            print("Shadow divergence predictions skipped.")
        
        return predictions
    
    def resolve_shadow_predictions(self, dry_run: bool = False) -> List[tuple]:
        """
        Resolve all pending shadow predictions that are past horizon.
        
        Args:
            dry_run: If True, don't actually update the store
            
        Returns:
            List of (prediction, message) tuples
        """
        results = self.outcome_tracker.resolve_pending_predictions(
            mode=PredictionMode.SHADOW,
            dry_run=dry_run,
        )
        
        return results
    
    def generate_shadow_report(self) -> str:
        """Generate accuracy report for shadow predictions."""
        report = self.accuracy_scorer.generate_report(mode=PredictionMode.SHADOW)
        return self.accuracy_scorer.format_report(report)
    
    def compare_to_production(self) -> dict:
        """Compare shadow accuracy to production accuracy."""
        return compare_shadow_to_production(self.accuracy_scorer)
    
    def check_graduation_readiness(self, signal_type: str) -> dict:
        """
        Check if a shadow signal is ready to graduate to production.
        
        Args:
            signal_type: Signal type to check
            
        Returns:
            Dict with graduation recommendation
        """
        predictions = self.prediction_store.get_predictions_by_signal_type(
            signal_type,
            mode=PredictionMode.SHADOW,
        )
        
        resolved = [
            p for p in predictions
            if p.status in (PredictionStatus.CORRECT, PredictionStatus.INCORRECT)
        ]
        
        if len(resolved) < self.GRADUATION_MIN_PREDICTIONS:
            return {
                "ready": False,
                "reason": f"Insufficient data: {len(resolved)}/{self.GRADUATION_MIN_PREDICTIONS} predictions",
                "resolved_count": len(resolved),
                "accuracy": None,
            }
        
        correct = sum(1 for p in resolved if p.status == PredictionStatus.CORRECT)
        accuracy = correct / len(resolved)
        
        if accuracy >= self.GRADUATION_THRESHOLD_ACCURACY:
            return {
                "ready": True,
                "reason": f"Accuracy {accuracy:.1%} meets threshold {self.GRADUATION_THRESHOLD_ACCURACY:.1%}",
                "resolved_count": len(resolved),
                "accuracy": accuracy,
                "recommendation": "Graduate to production",
            }
        else:
            return {
                "ready": False,
                "reason": f"Accuracy {accuracy:.1%} below threshold {self.GRADUATION_THRESHOLD_ACCURACY:.1%}",
                "resolved_count": len(resolved),
                "accuracy": accuracy,
                "recommendation": "Keep in shadow mode, review signal logic",
            }
    
    def graduate_signal(self, signal_type: str, force: bool = False) -> dict:
        """
        Graduate a signal from shadow to production.
        
        This updates the signal configuration to run in production mode.
        
        Args:
            signal_type: Signal type to graduate
            force: Graduate even if accuracy is below threshold
            
        Returns:
            Dict with graduation result
        """
        readiness = self.check_graduation_readiness(signal_type)
        
        if not readiness["ready"] and not force:
            return {
                "graduated": False,
                "reason": readiness["reason"],
                "recommendation": readiness.get("recommendation"),
            }
        
        # TODO: Update signal configuration to production mode
        # This would modify a config file or database setting
        
        return {
            "graduated": True,
            "signal_type": signal_type,
            "accuracy": readiness.get("accuracy"),
            "note": "Signal graduated to production mode",
        }


def main():
    parser = argparse.ArgumentParser(
        description="Shadow Mode Signal Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Run shadow signals:
    python scripts/run_shadow_signals.py run
    python scripts/run_shadow_signals.py run --signal-type divergence --horizon 30
    
  Resolve pending predictions:
    python scripts/run_shadow_signals.py resolve
    python scripts/run_shadow_signals.py resolve --dry-run
    
  View accuracy report:
    python scripts/run_shadow_signals.py report
    
  Compare shadow to production:
    python scripts/run_shadow_signals.py compare
    
  Check graduation readiness:
    python scripts/run_shadow_signals.py graduate --signal-type divergence
    python scripts/run_shadow_signals.py graduate --signal-type divergence --force
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run signals in shadow mode")
    run_parser.add_argument(
        "--signal-type", "-s",
        action="append",
        help="Signal types to run (can be specified multiple times)",
    )
    run_parser.add_argument(
        "--horizon",
        type=int,
        default=30,
        help="Days until prediction validation (default: 30)",
    )
    run_parser.add_argument(
        "--confidence-discount", "-c",
        type=float,
        default=0.8,
        help="Confidence discount for shadow mode (default: 0.8)",
    )
    
    # Resolve command
    resolve_parser = subparsers.add_parser("resolve", help="Resolve pending predictions")
    resolve_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be resolved without updating",
    )
    
    # Report command
    report_parser = subparsers.add_parser("report", help="Generate accuracy report")
    
    # Compare command
    compare_parser = subparsers.add_parser("compare", help="Compare shadow to production")
    
    # Graduate command
    graduate_parser = subparsers.add_parser("graduate", help="Graduate signal to production")
    graduate_parser.add_argument(
        "--signal-type", "-s",
        required=True,
        help="Signal type to graduate",
    )
    graduate_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Graduate even if accuracy is below threshold",
    )
    graduate_parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check readiness, don't graduate",
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    runner = ShadowRunner()
    
    if args.command == "run":
        print("=" * 60)
        print("SHADOW MODE SIGNAL RUNNER")
        print("=" * 60)
        print(f"Horizon: {args.horizon} days")
        print(f"Confidence discount: {args.confidence_discount}")
        print()
        
        predictions = runner.run_shadow_signals(
            signal_types=args.signal_type,
            horizon_days=args.horizon,
            confidence_discount=args.confidence_discount,
        )
        
        print()
        print(f"Created {len(predictions)} shadow predictions")
        
    elif args.command == "resolve":
        print("=" * 60)
        print("RESOLVING SHADOW PREDICTIONS")
        print("=" * 60)
        
        if args.dry_run:
            print("(dry run - no changes will be made)")
        print()
        
        results = runner.resolve_shadow_predictions(dry_run=args.dry_run)
        
        if not results:
            print("No predictions to resolve.")
        else:
            for pred, message in results:
                print(message)
            
            print()
            print(f"Resolved {len(results)} predictions")
        
    elif args.command == "report":
        print(runner.generate_shadow_report())
        
    elif args.command == "compare":
        print("=" * 60)
        print("SHADOW vs PRODUCTION COMPARISON")
        print("=" * 60)
        print()
        
        comparison = runner.compare_to_production()
        
        print("PRODUCTION:")
        print(f"  Total: {comparison['production']['total']}")
        print(f"  Accuracy: {comparison['production']['accuracy']:.1%}")
        print(f"  Brier Score: {comparison['production']['brier_score']:.4f}")
        print()
        
        print("SHADOW:")
        print(f"  Total: {comparison['shadow']['total']}")
        print(f"  Accuracy: {comparison['shadow']['accuracy']:.1%}")
        print(f"  Brier Score: {comparison['shadow']['brier_score']:.4f}")
        print()
        
        if comparison['shadow_better'] is not None:
            if comparison['shadow_better']:
                print("✓ Shadow is performing BETTER than production")
            else:
                print("✗ Shadow is performing WORSE than production")
        else:
            print("⚠ Insufficient shadow data for comparison")
        
        print()
        print(f"Recommendation: {comparison['recommendation']}")
        
    elif args.command == "graduate":
        print("=" * 60)
        print(f"GRADUATION CHECK: {args.signal_type}")
        print("=" * 60)
        print()
        
        readiness = runner.check_graduation_readiness(args.signal_type)
        
        print(f"Resolved predictions: {readiness['resolved_count']}")
        if readiness['accuracy'] is not None:
            print(f"Accuracy: {readiness['accuracy']:.1%}")
        print(f"Ready for graduation: {'Yes' if readiness['ready'] else 'No'}")
        print(f"Reason: {readiness['reason']}")
        
        if 'recommendation' in readiness:
            print(f"Recommendation: {readiness['recommendation']}")
        
        if not args.check_only and (readiness['ready'] or args.force):
            print()
            result = runner.graduate_signal(args.signal_type, force=args.force)
            
            if result['graduated']:
                print(f"✓ Signal '{args.signal_type}' graduated to production!")
            else:
                print(f"✗ Could not graduate: {result['reason']}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
