"""
Outcome Tracker

Links predictions to actual outcomes.
Defines what "correct" means for each prediction type and
automatically resolves predictions when their horizon passes.

The key challenge: what does "rising" or "breakout" actually mean?
This module codifies those definitions so we measure consistently.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from .prediction_store import (
    Prediction, PredictionStore, PredictionType, PredictionStatus, PredictionMode
)


class OutcomeDefinitions:
    """
    Defines what counts as a correct prediction for each type.
    
    These are the rules of the game. Being explicit about them
    prevents post-hoc rationalization ("oh, it was rising, just slowly").
    """
    
    # For RISING predictions: score must increase by this % from baseline
    RISING_THRESHOLD_PCT = 15.0
    
    # For FALLING predictions: score must decrease by this % from baseline
    FALLING_THRESHOLD_PCT = 15.0
    
    # For BREAKOUT predictions: must appear in this many mainstream sources
    BREAKOUT_MIN_MAINSTREAM_MENTIONS = 3
    
    # For DECLINE predictions: media score must drop below this
    DECLINE_MEDIA_THRESHOLD = 30.0
    
    # Minimum data points needed to validate
    MIN_DATA_POINTS = 2
    
    @classmethod
    def evaluate_rising(
        cls,
        baseline_value: float,
        current_value: float,
        threshold_override: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """
        Evaluate if a RISING prediction was correct.
        
        Args:
            baseline_value: Value at prediction time
            current_value: Value now
            threshold_override: Custom threshold (optional)
            
        Returns:
            (is_correct, explanation)
        """
        threshold = threshold_override or cls.RISING_THRESHOLD_PCT
        
        if baseline_value <= 0:
            return False, "Cannot evaluate: baseline value is zero or negative"
        
        pct_change = ((current_value - baseline_value) / baseline_value) * 100
        
        if pct_change >= threshold:
            return True, f"Correct: value rose {pct_change:.1f}% (threshold: {threshold}%)"
        else:
            return False, f"Incorrect: value changed {pct_change:+.1f}% (needed +{threshold}%)"
    
    @classmethod
    def evaluate_falling(
        cls,
        baseline_value: float,
        current_value: float,
        threshold_override: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """
        Evaluate if a FALLING prediction was correct.
        
        Args:
            baseline_value: Value at prediction time
            current_value: Value now
            threshold_override: Custom threshold (optional)
            
        Returns:
            (is_correct, explanation)
        """
        threshold = threshold_override or cls.FALLING_THRESHOLD_PCT
        
        if baseline_value <= 0:
            return False, "Cannot evaluate: baseline value is zero or negative"
        
        pct_change = ((baseline_value - current_value) / baseline_value) * 100
        
        if pct_change >= threshold:
            return True, f"Correct: value fell {pct_change:.1f}% (threshold: {threshold}%)"
        else:
            return False, f"Incorrect: value changed {-pct_change:+.1f}% (needed -{threshold}%)"
    
    @classmethod
    def evaluate_breakout(
        cls,
        mainstream_mentions: int,
        threshold_override: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Evaluate if a BREAKOUT prediction was correct.
        
        A breakout means the entity appeared in mainstream media.
        
        Args:
            mainstream_mentions: Number of mainstream media mentions
            threshold_override: Custom threshold (optional)
            
        Returns:
            (is_correct, explanation)
        """
        threshold = threshold_override or cls.BREAKOUT_MIN_MAINSTREAM_MENTIONS
        
        if mainstream_mentions >= threshold:
            return True, f"Correct: {mainstream_mentions} mainstream mentions (threshold: {threshold})"
        else:
            return False, f"Incorrect: only {mainstream_mentions} mainstream mentions (needed {threshold})"
    
    @classmethod
    def evaluate_decline(
        cls,
        media_score: float,
        threshold_override: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """
        Evaluate if a DECLINE prediction was correct.
        
        A decline means the entity faded from relevance.
        
        Args:
            media_score: Current media sentiment score (0-100)
            threshold_override: Custom threshold (optional)
            
        Returns:
            (is_correct, explanation)
        """
        threshold = threshold_override or cls.DECLINE_MEDIA_THRESHOLD
        
        if media_score <= threshold:
            return True, f"Correct: media score dropped to {media_score:.1f} (threshold: {threshold})"
        else:
            return False, f"Incorrect: media score still {media_score:.1f} (needed ≤{threshold})"


class OutcomeTracker:
    """
    Tracks and validates prediction outcomes.
    
    Workflow:
    1. System makes predictions via PredictionStore
    2. OutcomeTracker checks pending predictions daily
    3. For predictions past horizon, fetches current data
    4. Applies OutcomeDefinitions to determine correctness
    5. Updates prediction status
    """
    
    def __init__(
        self,
        prediction_store: Optional[PredictionStore] = None,
        signal_store=None,  # Optional: SignalStore for fetching current values
    ):
        """
        Initialize outcome tracker.
        
        Args:
            prediction_store: PredictionStore instance
            signal_store: Optional SignalStore for current signal values
        """
        self.prediction_store = prediction_store or PredictionStore()
        self.signal_store = signal_store
        self._outcome_log: List[Dict[str, Any]] = []
    
    def resolve_pending_predictions(
        self,
        mode: Optional[PredictionMode] = None,
        dry_run: bool = False,
    ) -> List[Tuple[Prediction, str]]:
        """
        Resolve all pending predictions that are past their horizon.
        
        Args:
            mode: Filter by mode (production/shadow)
            dry_run: If True, don't actually update the store
            
        Returns:
            List of (prediction, resolution_message) tuples
        """
        pending = self.prediction_store.get_pending_predictions(
            past_horizon_only=True,
            mode=mode,
        )
        
        results = []
        for prediction in pending:
            try:
                resolved, message = self.resolve_prediction(prediction, dry_run=dry_run)
                results.append((resolved, message))
            except Exception as e:
                results.append((prediction, f"Error resolving: {e}"))
        
        return results
    
    def resolve_prediction(
        self,
        prediction: Prediction,
        current_data: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
    ) -> Tuple[Prediction, str]:
        """
        Resolve a single prediction.
        
        Args:
            prediction: The prediction to resolve
            current_data: Current data for evaluation (optional, will fetch if not provided)
            dry_run: If True, don't update the store
            
        Returns:
            (updated_prediction, resolution_message)
        """
        if prediction.status != PredictionStatus.PENDING:
            return prediction, f"Already resolved: {prediction.status.value}"
        
        # Fetch current data if not provided
        if current_data is None:
            current_data = self._fetch_current_data(prediction)
        
        # Evaluate based on prediction type
        is_correct, explanation, evidence = self._evaluate_prediction(
            prediction, current_data
        )
        
        # Update prediction
        prediction.status = (
            PredictionStatus.CORRECT if is_correct 
            else PredictionStatus.INCORRECT
        )
        prediction.resolved_at = datetime.utcnow()
        prediction.actual_outcome = explanation
        prediction.actual_value = current_data.get("current_value")
        prediction.outcome_evidence = evidence
        
        # Log the outcome
        self._log_outcome(prediction, is_correct, explanation)
        
        # Persist unless dry run
        if not dry_run:
            self.prediction_store.update_prediction(prediction)
        
        status_emoji = "✓" if is_correct else "✗"
        message = f"{status_emoji} {prediction.entity_name}: {explanation}"
        
        return prediction, message
    
    def _fetch_current_data(self, prediction: Prediction) -> Dict[str, Any]:
        """
        Fetch current data for evaluating a prediction.
        
        Uses SignalStore if available, otherwise returns empty dict.
        """
        data = {
            "fetched_at": datetime.utcnow().isoformat(),
            "entity_id": prediction.entity_id,
        }
        
        if self.signal_store is None:
            # No signal store, return what we have
            data["current_value"] = prediction.baseline_value  # Will result in no change
            data["source"] = "fallback"
            return data
        
        try:
            # Try to get current profile
            profile = self.signal_store.get_latest_profile(prediction.entity_id)
            if profile:
                data["current_value"] = profile.composite_score
                data["technical_score"] = profile.technical_score
                data["financial_score"] = profile.financial_score
                data["product_score"] = profile.product_score
                data["media_score"] = profile.media_score
                data["source"] = "signal_store"
            else:
                data["current_value"] = prediction.baseline_value
                data["source"] = "no_profile"
        except Exception as e:
            data["current_value"] = prediction.baseline_value
            data["source"] = f"error: {e}"
        
        return data
    
    def _evaluate_prediction(
        self,
        prediction: Prediction,
        current_data: Dict[str, Any],
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Evaluate whether a prediction was correct.
        
        Returns:
            (is_correct, explanation, evidence_dict)
        """
        evidence = {
            "prediction_type": prediction.prediction_type.value,
            "baseline_value": prediction.baseline_value,
            "current_value": current_data.get("current_value"),
            "threshold_value": prediction.threshold_value,
            "data_source": current_data.get("source"),
            "evaluated_at": datetime.utcnow().isoformat(),
        }
        
        baseline = prediction.baseline_value or 0
        current = current_data.get("current_value", baseline)
        
        if prediction.prediction_type == PredictionType.RISING:
            is_correct, explanation = OutcomeDefinitions.evaluate_rising(
                baseline, current, prediction.threshold_value
            )
        
        elif prediction.prediction_type == PredictionType.FALLING:
            is_correct, explanation = OutcomeDefinitions.evaluate_falling(
                baseline, current, prediction.threshold_value
            )
        
        elif prediction.prediction_type == PredictionType.BREAKOUT:
            # For breakout, we need mainstream mention count
            mentions = current_data.get("mainstream_mentions", 0)
            is_correct, explanation = OutcomeDefinitions.evaluate_breakout(mentions)
            evidence["mainstream_mentions"] = mentions
        
        elif prediction.prediction_type == PredictionType.DECLINE:
            media_score = current_data.get("media_score", 50)
            is_correct, explanation = OutcomeDefinitions.evaluate_decline(media_score)
            evidence["media_score"] = media_score
        
        else:
            # STABLE or unknown - can't really be wrong
            is_correct = True
            explanation = "Stable prediction (no directional bet)"
        
        evidence["is_correct"] = is_correct
        evidence["explanation"] = explanation
        
        return is_correct, explanation, evidence
    
    def _log_outcome(
        self,
        prediction: Prediction,
        is_correct: bool,
        explanation: str,
    ):
        """Log outcome for analysis."""
        self._outcome_log.append({
            "prediction_id": prediction.id,
            "entity_id": prediction.entity_id,
            "entity_name": prediction.entity_name,
            "prediction_type": prediction.prediction_type.value,
            "signal_type": prediction.signal_type,
            "confidence": prediction.confidence,
            "is_correct": is_correct,
            "explanation": explanation,
            "horizon_days": prediction.horizon_days,
            "resolved_at": datetime.utcnow().isoformat(),
        })
    
    def get_outcome_log(self) -> List[Dict[str, Any]]:
        """Get the outcome log from this session."""
        return self._outcome_log.copy()
    
    def generate_resolution_report(
        self,
        predictions: List[Prediction],
        title: str = "Prediction Resolution Report",
    ) -> str:
        """
        Generate a human-readable report of resolved predictions.
        
        Args:
            predictions: List of resolved predictions
            title: Report title
            
        Returns:
            Formatted report string
        """
        if not predictions:
            return f"{title}\n{'='*len(title)}\n\nNo predictions to report."
        
        correct = [p for p in predictions if p.status == PredictionStatus.CORRECT]
        incorrect = [p for p in predictions if p.status == PredictionStatus.INCORRECT]
        
        accuracy = len(correct) / len(predictions) if predictions else 0
        
        lines = [
            f"{title}",
            "=" * len(title),
            "",
            f"Total Predictions: {len(predictions)}",
            f"Correct: {len(correct)} ({len(correct)/len(predictions)*100:.1f}%)",
            f"Incorrect: {len(incorrect)} ({len(incorrect)/len(predictions)*100:.1f}%)",
            "",
            "─" * 60,
            "",
        ]
        
        # Group by signal type
        by_signal = {}
        for p in predictions:
            if p.signal_type not in by_signal:
                by_signal[p.signal_type] = {"correct": 0, "incorrect": 0, "total": 0}
            by_signal[p.signal_type]["total"] += 1
            if p.status == PredictionStatus.CORRECT:
                by_signal[p.signal_type]["correct"] += 1
            else:
                by_signal[p.signal_type]["incorrect"] += 1
        
        lines.append("Accuracy by Signal Type:")
        for signal, counts in sorted(by_signal.items()):
            acc = counts["correct"] / counts["total"] if counts["total"] > 0 else 0
            lines.append(f"  • {signal}: {acc*100:.1f}% ({counts['correct']}/{counts['total']})")
        
        lines.extend(["", "─" * 60, "", "Individual Predictions:", ""])
        
        # List individual predictions
        for p in sorted(predictions, key=lambda x: x.resolved_at or datetime.min, reverse=True):
            emoji = "✓" if p.status == PredictionStatus.CORRECT else "✗"
            lines.append(f"{emoji} [{p.prediction_type.value.upper()}] {p.entity_name}")
            lines.append(f"   Predicted: {p.predicted_outcome}")
            lines.append(f"   Outcome: {p.actual_outcome or 'N/A'}")
            lines.append(f"   Confidence: {p.confidence:.0%}")
            lines.append("")
        
        return "\n".join(lines)


class OutcomeDataCollector:
    """
    Collects outcome data from various sources.
    
    This is the bridge between briefAI's signals and external reality.
    """
    
    def __init__(self, signal_store=None):
        self.signal_store = signal_store
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    def collect_for_entity(
        self,
        entity_id: str,
        prediction_date: datetime,
        include_mainstream_check: bool = True,
    ) -> Dict[str, Any]:
        """
        Collect current outcome data for an entity.
        
        Args:
            entity_id: Entity to collect for
            prediction_date: When the prediction was made
            include_mainstream_check: Whether to check mainstream media
            
        Returns:
            Dict with current values and evidence
        """
        cache_key = f"{entity_id}:{datetime.utcnow().date()}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        data = {
            "entity_id": entity_id,
            "collected_at": datetime.utcnow().isoformat(),
            "prediction_date": prediction_date.isoformat(),
        }
        
        # Collect from signal store if available
        if self.signal_store:
            try:
                profile = self.signal_store.get_latest_profile(entity_id)
                if profile:
                    data["current_value"] = profile.composite_score
                    data["technical_score"] = profile.technical_score
                    data["financial_score"] = profile.financial_score
                    data["product_score"] = profile.product_score
                    data["media_score"] = profile.media_score
                    data["momentum_7d"] = profile.momentum_7d
                    data["momentum_30d"] = profile.momentum_30d
            except Exception as e:
                data["signal_store_error"] = str(e)
        
        # TODO: Check mainstream media sources
        # This would integrate with news scrapers
        if include_mainstream_check:
            data["mainstream_mentions"] = 0  # Placeholder
            data["mainstream_sources"] = []
        
        self._cache[cache_key] = data
        return data


if __name__ == "__main__":
    # Quick test
    from .prediction_store import PredictionStore
    
    store = PredictionStore()
    tracker = OutcomeTracker(store)
    
    # Test outcome definitions
    print("Testing OutcomeDefinitions:")
    print("-" * 40)
    
    # Rising
    is_correct, msg = OutcomeDefinitions.evaluate_rising(50, 60)
    print(f"Rising 50→60: {is_correct} - {msg}")
    
    is_correct, msg = OutcomeDefinitions.evaluate_rising(50, 52)
    print(f"Rising 50→52: {is_correct} - {msg}")
    
    # Falling
    is_correct, msg = OutcomeDefinitions.evaluate_falling(50, 40)
    print(f"Falling 50→40: {is_correct} - {msg}")
    
    # Breakout
    is_correct, msg = OutcomeDefinitions.evaluate_breakout(5)
    print(f"Breakout 5 mentions: {is_correct} - {msg}")
    
    print("\n" + "=" * 40)
    print("Outcome tracker initialized.")
