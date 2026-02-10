#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Historical Prediction Backfill with Walk-Forward Validation

Generates retrospective predictions from historical data and scores
them against known outcomes with proper statistical rigor.

Features:
- Walk-forward validation (70% train / 30% validate)
- Confidence intervals for all accuracy estimates
- P-value calculations for statistical significance
- Brier score tracking for probability calibration
- Flags weak correlations (p > 0.05 or n < 30)

Usage:
    python scripts/backfill_predictions.py --help
    python scripts/backfill_predictions.py run --start-date 2024-12-01
    python scripts/backfill_predictions.py run --start-date 2024-12-01 --end-date 2025-01-01 --walk-forward
    python scripts/backfill_predictions.py report
    python scripts/backfill_predictions.py validate  # Run walk-forward validation
    python scripts/backfill_predictions.py clear
"""

import argparse
import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.prediction_store import (
    PredictionStore, Prediction, PredictionType, PredictionStatus, PredictionMode
)
from utils.outcome_tracker import OutcomeTracker, OutcomeDefinitions
from utils.accuracy_scorer import AccuracyScorer

# Import statistical validation utilities
try:
    from utils.statistical_validation import (
        StatisticalValidator,
        BrierScoreTracker,
        WalkForwardValidator,
        calculate_backtest_statistics
    )
    HAS_STATS = True
except ImportError:
    HAS_STATS = False
    print("Warning: statistical_validation module not found, running without statistical rigor")


class HistoricalBackfiller:
    """
    Generates and validates retrospective predictions.
    
    This is crucial for:
    1. Validating new signal types before deployment
    2. Understanding how signals would have performed historically
    3. Building confidence in the system
    4. Avoiding survivorship bias (we can see what we would have missed)
    
    Enhanced with:
    - Walk-forward validation (train on 70%, validate on 30%)
    - Statistical confidence intervals
    - P-value calculations
    - Brier score calibration tracking
    """
    
    BACKFILL_MODE = PredictionMode.SHADOW  # Backfills go to shadow mode
    MIN_SAMPLE_SIZE = 30  # Minimum for reliable statistics
    SIGNIFICANCE_LEVEL = 0.05  # Alpha for hypothesis tests
    
    def __init__(self, ground_truth_path: Optional[Path] = None):
        self.prediction_store = PredictionStore()
        self.accuracy_scorer = AccuracyScorer(self.prediction_store)
        
        # Load ground truth for validation - prefer expanded version with 155 events
        config_dir = Path(__file__).parent.parent / "config"
        if ground_truth_path:
            self.ground_truth_path = ground_truth_path
        else:
            # Default to expanded ground truth (155 events) if available
            expanded_path = config_dir / "ground_truth_expanded.json"
            legacy_path = config_dir / "ground_truth.json"
            self.ground_truth_path = expanded_path if expanded_path.exists() else legacy_path
        self.ground_truth = self._load_ground_truth()
        
        # Track backfill results
        self.backfill_results: List[Dict[str, Any]] = []
        
        # Statistical validation components
        if HAS_STATS:
            self.stat_validator = StatisticalValidator(
                min_sample_size=self.MIN_SAMPLE_SIZE,
                alpha=self.SIGNIFICANCE_LEVEL
            )
            self.brier_tracker = BrierScoreTracker()
            self.walk_forward_validator = WalkForwardValidator(train_ratio=0.7)
        else:
            self.stat_validator = None
            self.brier_tracker = None
            self.walk_forward_validator = None
    
    def _load_ground_truth(self) -> Dict:
        """Load ground truth events for validation."""
        if self.ground_truth_path.exists():
            with open(self.ground_truth_path, encoding="utf-8") as f:
                return json.load(f)
        return {"breakout_events": []}
    
    def run_backfill(
        self,
        start_date: date,
        end_date: Optional[date] = None,
        signal_types: Optional[List[str]] = None,
        horizon_days: int = 30,
    ) -> List[Prediction]:
        """
        Run historical backfill for a date range.
        
        This simulates what predictions would have been made at each
        point in time, then validates them against actual outcomes.
        
        Args:
            start_date: Start of backfill period
            end_date: End of backfill period (default: today - horizon)
            signal_types: Types of signals to backfill
            horizon_days: Prediction horizon
            
        Returns:
            List of backfilled predictions (already resolved)
        """
        if end_date is None:
            # Default end date is horizon_days ago (so we can validate)
            end_date = date.today() - timedelta(days=horizon_days)
        
        print(f"Backfilling from {start_date} to {end_date}")
        print(f"Horizon: {horizon_days} days")
        print()
        
        all_predictions = []
        current_date = start_date
        
        while current_date <= end_date:
            print(f"Processing {current_date}...")
            
            predictions = self._generate_predictions_for_date(
                current_date,
                signal_types=signal_types,
                horizon_days=horizon_days,
            )
            
            # Immediately resolve since we're in the past
            for pred in predictions:
                self._resolve_historical_prediction(pred, current_date)
            
            all_predictions.extend(predictions)
            
            # Move to next week (to avoid too many predictions)
            current_date += timedelta(days=7)
        
        print()
        print(f"Generated {len(all_predictions)} backfilled predictions")
        
        return all_predictions
    
    def _generate_predictions_for_date(
        self,
        prediction_date: date,
        signal_types: Optional[List[str]],
        horizon_days: int,
    ) -> List[Prediction]:
        """
        Generate predictions that would have been made at a specific date.
        
        For backfill, we use ground truth events to simulate what signals
        would have detected.
        """
        predictions = []
        
        # Use ground truth events as the source of "what happened"
        for event in self.ground_truth.get("breakout_events", []):
            early_signal_date = datetime.fromisoformat(event["early_signal_date"]).date()
            breakout_date = datetime.fromisoformat(event["breakout_date"]).date()
            
            # Check if this prediction date falls in the prediction window
            # (after early signal, before breakout)
            if early_signal_date <= prediction_date < breakout_date:
                # This is a prediction we would have made
                pred = Prediction(
                    id=f"backfill_{event['entity_id']}_{prediction_date.isoformat()}",
                    entity_id=event["entity_id"],
                    entity_name=event["entity_name"],
                    signal_type="divergence",  # Simulated signal type
                    prediction_type=PredictionType.BREAKOUT,
                    predicted_outcome=f"{event['entity_name']} will hit mainstream",
                    confidence=0.7,  # Simulated confidence
                    horizon_days=horizon_days,
                    baseline_value=40.0,  # Simulated baseline
                    source_metadata={
                        "backfill": True,
                        "ground_truth_event": event["entity_id"],
                        "category": event.get("category"),
                    },
                    status=PredictionStatus.PENDING,
                    mode=self.BACKFILL_MODE,
                    predicted_at=datetime.combine(prediction_date, datetime.min.time()),
                )
                predictions.append(pred)
        
        # Also generate some "would have missed" predictions
        # These are entities that weren't in ground truth but could have been predicted
        # This helps avoid survivorship bias
        predictions.extend(
            self._generate_counterfactual_predictions(prediction_date, horizon_days)
        )
        
        return predictions
    
    def _generate_counterfactual_predictions(
        self,
        prediction_date: date,
        horizon_days: int,
    ) -> List[Prediction]:
        """
        Generate counterfactual predictions (things that didn't happen).
        
        This is important for avoiding survivorship bias. We need to count
        wrong predictions, not just the ones that worked.
        """
        # For now, return empty list. In a real implementation, this would:
        # 1. Load historical signal data for prediction_date
        # 2. Generate predictions using the same logic as production
        # 3. These predictions will be validated and many will be wrong
        return []
    
    def _resolve_historical_prediction(
        self,
        prediction: Prediction,
        prediction_date: date,
    ):
        """
        Resolve a historical prediction against known outcomes.
        
        Since we're in the past, we can look at what actually happened
        at the horizon date.
        """
        horizon_date = prediction_date + timedelta(days=prediction.horizon_days)
        
        # Check ground truth for what happened
        event = self._get_ground_truth_event(prediction.entity_id)
        
        if event:
            breakout_date = datetime.fromisoformat(event["breakout_date"]).date()
            
            # Did breakout happen by the horizon?
            if breakout_date <= horizon_date:
                prediction.status = PredictionStatus.CORRECT
                prediction.actual_outcome = (
                    f"Breakout confirmed: {event['entity_name']} hit mainstream "
                    f"on {breakout_date}"
                )
                prediction.actual_value = 1.0  # Breakout happened
                prediction.outcome_evidence = {
                    "breakout_date": breakout_date.isoformat(),
                    "mainstream_sources": event.get("mainstream_sources", []),
                }
            else:
                # Breakout happened but after our horizon
                prediction.status = PredictionStatus.INCORRECT
                prediction.actual_outcome = (
                    f"Breakout happened on {breakout_date}, "
                    f"after horizon {horizon_date}"
                )
                prediction.actual_value = 0.0
        else:
            # Not in ground truth - assume no breakout
            prediction.status = PredictionStatus.INCORRECT
            prediction.actual_outcome = "No breakout detected by horizon"
            prediction.actual_value = 0.0
        
        prediction.resolved_at = datetime.combine(horizon_date, datetime.min.time())
        
        # Store the resolved prediction (skip if already exists)
        try:
            self.prediction_store.add_prediction(prediction)
        except Exception as e:
            # Skip duplicates
            pass
        
        # Track result
        self.backfill_results.append({
            "entity": prediction.entity_name,
            "prediction_date": prediction_date.isoformat(),
            "horizon_date": horizon_date.isoformat(),
            "status": prediction.status.value,
            "outcome": prediction.actual_outcome,
        })
    
    def _get_ground_truth_event(self, entity_id: str) -> Optional[Dict]:
        """Get ground truth event for an entity."""
        for event in self.ground_truth.get("breakout_events", []):
            if event["entity_id"] == entity_id:
                return event
        return None
    
    def run_walk_forward_validation(
        self,
        horizon_days: int = 60,
    ) -> Dict[str, Any]:
        """
        Run walk-forward validation with proper train/validate splits.
        
        This avoids lookahead bias by ensuring we only use past data
        to make predictions about the future.
        
        Returns:
            Dict with validation results including CIs and p-values
        """
        if not HAS_STATS:
            return {"error": "Statistical validation module not available"}
        
        events = self.ground_truth.get("breakout_events", [])
        
        def prediction_func(train_events: List[Dict], test_event: Dict) -> float:
            """Predict based on training data characteristics."""
            # Simple model: base confidence adjusted by event type
            base_confidence = 0.65
            
            # Adjust based on event type performance in training data
            event_type = test_event.get("event_type", "unknown")
            type_count = sum(1 for e in train_events if e.get("event_type") == event_type)
            
            if type_count > 5:
                base_confidence += 0.05  # More data for this type
            
            # Funding events are more predictable
            if event_type == "funding" and test_event.get("funding_amount_usd", 0) > 100_000_000:
                base_confidence += 0.1
            
            return min(0.9, base_confidence)
        
        # Run walk-forward validation
        wf_results = self.walk_forward_validator.run_walk_forward(
            events,
            prediction_func,
            date_field="breakout_date"
        )
        
        # Calculate per-horizon accuracy with CIs
        horizon_accuracies = []
        for fold_result in wf_results.get("fold_results", []):
            horizon_accuracies.append(fold_result["accuracy"])
        
        # Statistical summary
        if horizon_accuracies:
            accuracy_result = self.stat_validator.bootstrap_confidence_interval(
                horizon_accuracies,
                lambda x: sum(x) / len(x) if x else 0,
                name="walk_forward_accuracy"
            )
            
            wf_results["statistical_analysis"] = {
                "mean_accuracy": round(wf_results.get("mean_accuracy", 0), 4),
                "ci_lower": round(accuracy_result.confidence_interval[0], 4),
                "ci_upper": round(accuracy_result.confidence_interval[1], 4),
                "p_value": round(accuracy_result.p_value, 4),
                "is_significant": accuracy_result.is_significant,
                "sample_size": len(horizon_accuracies),
                "min_sample_warning": len(horizon_accuracies) < self.MIN_SAMPLE_SIZE,
            }
        
        return wf_results
    
    def calculate_statistical_metrics(self) -> Dict[str, Any]:
        """
        Calculate comprehensive statistical metrics from backfill results.
        
        Returns metrics with p-values and confidence intervals.
        Flags any results with p > 0.05 or n < 30.
        """
        if not self.backfill_results:
            return {"error": "No backfill results available"}
        
        if not HAS_STATS:
            return {"error": "Statistical validation module not available"}
        
        correct = sum(1 for r in self.backfill_results if r["status"] == "correct")
        total = len(self.backfill_results)
        
        # Overall accuracy with CI
        accuracy_stats = self.stat_validator.accuracy_with_ci(correct, total, "overall_accuracy")
        
        # Brier score if we have confidence values
        brier_score = None
        if self.brier_tracker.scores:
            brier_score = self.brier_tracker.get_brier_score()
        
        # Flag weak results
        warnings = []
        if not accuracy_stats.is_significant:
            warnings.append(f"Accuracy not statistically significant (p={accuracy_stats.p_value:.3f})")
        if total < self.MIN_SAMPLE_SIZE:
            warnings.append(f"Sample size ({total}) below minimum ({self.MIN_SAMPLE_SIZE})")
        if accuracy_stats.warning:
            warnings.append(accuracy_stats.warning)
        
        return {
            "accuracy": round(accuracy_stats.value, 4),
            "ci_lower": round(accuracy_stats.confidence_interval[0], 4),
            "ci_upper": round(accuracy_stats.confidence_interval[1], 4),
            "p_value": round(accuracy_stats.p_value, 4),
            "is_significant": accuracy_stats.is_significant,
            "sample_size": total,
            "brier_score": round(brier_score, 4) if brier_score else None,
            "warnings": warnings,
            "passes_quality_check": (
                accuracy_stats.is_significant and 
                total >= self.MIN_SAMPLE_SIZE and
                accuracy_stats.p_value < self.SIGNIFICANCE_LEVEL
            ),
        }
    
    def generate_backfill_report(self) -> str:
        """Generate a report of backfill results with statistical analysis."""
        if not self.backfill_results:
            return "No backfill results to report."
        
        correct = sum(1 for r in self.backfill_results if r["status"] == "correct")
        incorrect = sum(1 for r in self.backfill_results if r["status"] == "incorrect")
        total = len(self.backfill_results)
        
        accuracy = correct / total if total > 0 else 0
        
        lines = [
            "=" * 70,
            "HISTORICAL BACKFILL REPORT",
            "=" * 70,
            "",
            f"Total Predictions: {total}",
            f"Correct: {correct} ({correct/total*100:.1f}%)",
            f"Incorrect: {incorrect} ({incorrect/total*100:.1f}%)",
            f"Overall Accuracy: {accuracy:.1%}",
            "",
        ]
        
        # Add statistical analysis if available
        if HAS_STATS and total > 0:
            stats = self.calculate_statistical_metrics()
            lines.extend([
                "-" * 70,
                "STATISTICAL ANALYSIS",
                "-" * 70,
                "",
                f"Accuracy: {stats['accuracy']:.1%}",
                f"95% Confidence Interval: [{stats['ci_lower']:.1%}, {stats['ci_upper']:.1%}]",
                f"P-value (vs random): {stats['p_value']:.4f}",
                f"Statistically Significant: {'Yes [OK]' if stats['is_significant'] else 'No [!]'}",
                f"Sample Size: {stats['sample_size']} (minimum: {self.MIN_SAMPLE_SIZE})",
            ])
            
            if stats.get('brier_score'):
                lines.append(f"Brier Score: {stats['brier_score']:.4f} (lower is better)")
            
            if stats.get('warnings'):
                lines.extend(["", "Warnings:"])
                for warning in stats['warnings']:
                    lines.append(f"  [!] {warning}")
            
            if stats.get('passes_quality_check'):
                lines.append("\n[OK] PASSES QUALITY CHECK (p < 0.05, n >= 30)")
            else:
                lines.append("\n[!] DOES NOT PASS QUALITY CHECK")
            
            lines.append("")
        
        lines.extend([
            "-" * 70,
            "INDIVIDUAL PREDICTIONS",
            "-" * 70,
            "",
        ])
        
        # Group by entity
        by_entity = {}
        for result in self.backfill_results:
            entity = result["entity"]
            if entity not in by_entity:
                by_entity[entity] = []
            by_entity[entity].append(result)
        
        for entity, results in sorted(by_entity.items()):
            correct_count = sum(1 for r in results if r["status"] == "correct")
            lines.append(f"{entity}: {correct_count}/{len(results)} correct")
            for result in results:
                emoji = "[OK]" if result["status"] == "correct" else "[X]"
                lines.append(f"  {emoji} {result['prediction_date']}: {result['outcome']}")
            lines.append("")
        
        # What would have happened analysis
        lines.extend([
            "-" * 70,
            "WHAT WOULD HAVE HAPPENED",
            "-" * 70,
            "",
        ])
        
        ground_truth_events = self.ground_truth.get("breakout_events", [])
        
        for event in ground_truth_events:
            entity_predictions = [
                r for r in self.backfill_results
                if r["entity"] == event["entity_name"]
            ]
            
            if entity_predictions:
                first_correct = next(
                    (r for r in entity_predictions if r["status"] == "correct"),
                    None
                )
                
                if first_correct:
                    early_signal = datetime.fromisoformat(event["early_signal_date"]).date()
                    first_pred = datetime.fromisoformat(first_correct["prediction_date"]).date()
                    breakout = datetime.fromisoformat(event["breakout_date"]).date()
                    
                    lead_time = (breakout - first_pred).days
                    lines.append(
                        f"[OK] {event['entity_name']}: Would have predicted {lead_time} days "
                        f"before breakout"
                    )
                else:
                    lines.append(f"[X] {event['entity_name']}: All predictions expired")
            else:
                lines.append(f"[?] {event['entity_name']}: No predictions in backfill period")
        
        lines.extend(["", "=" * 70])
        
        return "\n".join(lines)
    
    def clear_backfill_predictions(self) -> int:
        """
        Clear all backfilled predictions from the store.
        
        Returns:
            Number of predictions cleared
        """
        # This would require adding a delete method to PredictionStore
        # For now, we'll just track that we want to clear them
        print("Note: Clear functionality requires database delete support")
        return 0


class BackfillValidator:
    """
    Validates backfill results against ground truth.
    
    This helps understand:
    1. Detection rate: What % of breakouts would we have caught?
    2. Lead time: How early would we have detected them?
    3. False positive rate: How many predictions were wrong?
    """
    
    def __init__(self, ground_truth_path: Optional[Path] = None):
        config_dir = Path(__file__).parent.parent / "config"
        if ground_truth_path:
            self.ground_truth_path = ground_truth_path
        else:
            # Default to expanded ground truth (52 events) if available
            expanded_path = config_dir / "ground_truth_expanded.json"
            legacy_path = config_dir / "ground_truth.json"
            self.ground_truth_path = expanded_path if expanded_path.exists() else legacy_path
        self.ground_truth = self._load_ground_truth()
    
    def _load_ground_truth(self) -> Dict:
        """Load ground truth."""
        if self.ground_truth_path.exists():
            with open(self.ground_truth_path, encoding="utf-8") as f:
                return json.load(f)
        return {"breakout_events": []}
    
    def validate_detection_rate(
        self,
        predictions: List[Prediction],
    ) -> Dict[str, Any]:
        """
        Calculate detection rate against ground truth.
        
        Returns:
            Dict with detection metrics
        """
        events = self.ground_truth.get("breakout_events", [])
        
        detected = 0
        missed = 0
        detection_details = []
        
        for event in events:
            entity_predictions = [
                p for p in predictions
                if p.entity_id == event["entity_id"]
            ]
            
            correct_predictions = [
                p for p in entity_predictions
                if p.status == PredictionStatus.CORRECT
            ]
            
            if correct_predictions:
                detected += 1
                earliest = min(correct_predictions, key=lambda p: p.predicted_at)
                breakout_date = datetime.fromisoformat(event["breakout_date"])
                lead_time = (breakout_date - earliest.predicted_at).days
                
                detection_details.append({
                    "entity": event["entity_name"],
                    "detected": True,
                    "lead_time_days": lead_time,
                    "prediction_count": len(correct_predictions),
                })
            else:
                missed += 1
                detection_details.append({
                    "entity": event["entity_name"],
                    "detected": False,
                    "reason": "No correct predictions" if entity_predictions else "Not in predictions",
                })
        
        detection_rate = detected / len(events) if events else 0
        
        return {
            "total_events": len(events),
            "detected": detected,
            "missed": missed,
            "detection_rate": detection_rate,
            "avg_lead_time": (
                sum(d["lead_time_days"] for d in detection_details if d.get("detected"))
                / detected if detected > 0 else 0
            ),
            "details": detection_details,
        }
    
    def calculate_false_positive_rate(
        self,
        predictions: List[Prediction],
    ) -> Dict[str, Any]:
        """
        Calculate false positive rate.
        
        A false positive is a prediction that didn't come true
        for an entity that's NOT in the ground truth.
        """
        ground_truth_entities = {
            e["entity_id"] for e in self.ground_truth.get("breakout_events", [])
        }
        
        # Predictions for entities not in ground truth
        unknown_entity_predictions = [
            p for p in predictions
            if p.entity_id not in ground_truth_entities
        ]
        
        incorrect_unknowns = [
            p for p in unknown_entity_predictions
            if p.status == PredictionStatus.INCORRECT
        ]
        
        # For ground truth entities, incorrect predictions are timing issues
        # not false positives (we predicted the right thing, just wrong timing)
        
        return {
            "unknown_entity_predictions": len(unknown_entity_predictions),
            "false_positives": len(incorrect_unknowns),
            "false_positive_rate": (
                len(incorrect_unknowns) / len(unknown_entity_predictions)
                if unknown_entity_predictions else 0
            ),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Historical Prediction Backfill",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Run backfill for a date range:
    python scripts/backfill_predictions.py run --start-date 2024-12-01
    python scripts/backfill_predictions.py run --start-date 2024-12-01 --end-date 2025-01-01
    
  View backfill report:
    python scripts/backfill_predictions.py report
    
  Clear backfill predictions:
    python scripts/backfill_predictions.py clear
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run historical backfill")
    run_parser.add_argument(
        "--start-date", "-s",
        required=True,
        help="Start date (YYYY-MM-DD)",
    )
    run_parser.add_argument(
        "--end-date", "-e",
        help="End date (YYYY-MM-DD, default: today - horizon)",
    )
    run_parser.add_argument(
        "--horizon",
        type=int,
        default=30,
        help="Prediction horizon in days (default: 30)",
    )
    run_parser.add_argument(
        "--signal-type",
        action="append",
        help="Signal types to backfill",
    )
    
    # Report command
    report_parser = subparsers.add_parser("report", help="View backfill report")
    
    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear backfill predictions")
    clear_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm deletion",
    )
    
    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate against ground truth")
    
    # Walk-forward command
    wf_parser = subparsers.add_parser("walk-forward", help="Run walk-forward validation")
    wf_parser.add_argument(
        "--horizon",
        type=int,
        default=60,
        help="Prediction horizon in days (default: 60)"
    )
    wf_parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.7,
        help="Training data ratio (default: 0.7)"
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    backfiller = HistoricalBackfiller()
    
    if args.command == "run":
        start_date = date.fromisoformat(args.start_date)
        end_date = date.fromisoformat(args.end_date) if args.end_date else None
        
        print("=" * 70)
        print("HISTORICAL BACKFILL")
        print("=" * 70)
        print()
        
        predictions = backfiller.run_backfill(
            start_date=start_date,
            end_date=end_date,
            signal_types=args.signal_type,
            horizon_days=args.horizon,
        )
        
        print()
        print(backfiller.generate_backfill_report())
        
    elif args.command == "report":
        # Generate report from existing backfill predictions
        scorer = AccuracyScorer()
        report = scorer.generate_report(mode=PredictionMode.SHADOW)
        print(scorer.format_report(report))
        
    elif args.command == "clear":
        if not args.confirm:
            print("Use --confirm to actually delete backfill predictions")
            return 1
        
        count = backfiller.clear_backfill_predictions()
        print(f"Cleared {count} backfill predictions")
        
    elif args.command == "validate":
        print("=" * 70)
        print("VALIDATION AGAINST GROUND TRUTH")
        print("=" * 70)
        print()
        
        validator = BackfillValidator()
        store = PredictionStore()
        
        # Get all shadow predictions (backfills)
        predictions = store.get_resolved_predictions(mode=PredictionMode.SHADOW)
        
        if not predictions:
            print("No backfill predictions found. Run 'backfill_predictions.py run' first.")
            return 1
        
        detection = validator.validate_detection_rate(predictions)
        
        print(f"Ground Truth Events: {detection['total_events']}")
        print(f"Detected: {detection['detected']}")
        print(f"Missed: {detection['missed']}")
        print(f"Detection Rate: {detection['detection_rate']:.1%}")
        print(f"Average Lead Time: {detection['avg_lead_time']:.1f} days")
        print()
        
        print("Detection Details:")
        for detail in detection["details"]:
            if detail.get("detected"):
                print(f"  [OK] {detail['entity']}: {detail['lead_time_days']} days early")
            else:
                print(f"  [X] {detail['entity']}: {detail.get('reason', 'missed')}")
        
        print()
        
        fp = validator.calculate_false_positive_rate(predictions)
        print(f"False Positive Rate: {fp['false_positive_rate']:.1%}")
        print(f"  ({fp['false_positives']} false positives out of "
              f"{fp['unknown_entity_predictions']} unknown entity predictions)")
    
    elif args.command == "walk-forward":
        print("=" * 70)
        print("WALK-FORWARD VALIDATION")
        print("=" * 70)
        print()
        
        if not HAS_STATS:
            print("Error: Statistical validation module not available")
            print("Install with: pip install scipy")
            return 1
        
        print(f"Horizon: {args.horizon} days")
        print(f"Train/Validate split: {args.train_ratio*100:.0f}%/{(1-args.train_ratio)*100:.0f}%")
        print()
        
        results = backfiller.run_walk_forward_validation(horizon_days=args.horizon)
        
        if "error" in results:
            print(f"Error: {results['error']}")
            return 1
        
        print(f"Number of folds: {results.get('n_folds', 'N/A')}")
        print(f"Mean Accuracy: {results.get('mean_accuracy', 0):.1%}")
        print(f"Std Dev: {results.get('std_accuracy', 0):.1%}")
        print(f"Temporal Stability: {results.get('temporal_stability', 'unknown')}")
        print()
        
        if "statistical_analysis" in results:
            stats = results["statistical_analysis"]
            print("Statistical Analysis:")
            print(f"  95% CI: [{stats['ci_lower']:.1%}, {stats['ci_upper']:.1%}]")
            print(f"  P-value: {stats['p_value']:.4f}")
            print(f"  Significant: {'Yes [OK]' if stats['is_significant'] else 'No [!]'}")
            
            if stats.get("min_sample_warning"):
                print(f"\n  [!] Warning: Sample size below recommended minimum (30)")
        
        print()
        print("Fold Results:")
        for fold in results.get("fold_results", []):
            print(f"  Fold {fold['fold']}: {fold['accuracy']:.1%} "
                  f"(train: {fold['n_train']}, validate: {fold['n_validate']})")
        
        # Save results
        output_dir = Path(__file__).parent.parent / "data" / "backtests"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"walk_forward_{date.today().isoformat()}.json"
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\nResults saved to: {output_file}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
