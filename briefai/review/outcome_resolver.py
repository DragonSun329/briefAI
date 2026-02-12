"""
Outcome Resolution Engine

Deterministically resolves whether predictions were correct
by analyzing post-prediction signal data.

NO LLM USAGE. All heuristics are rule-based.

v1.1: Added explainability (debug_features, decision_trace, unclear_reason)
"""

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from .models import (
    ExpiredPrediction,
    ResolvedOutcome,
    OutcomeStatus,
    SupportingEvidence,
    Direction,
    UnclearReason,
)


class SignalDataLoader:
    """
    Loads signal data from various sources for outcome determination.
    
    READ ONLY. Never modifies source files.
    """
    
    def __init__(self, data_root: Path = None):
        if data_root is None:
            data_root = Path(__file__).parent.parent.parent / "data"
        self.data_root = data_root
        self._cache = {}
    
    def get_meta_signals(self, for_date: date) -> list[dict]:
        """Load meta_signals for a specific date."""
        cache_key = f"meta_{for_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        path = self.data_root / "meta_signals" / f"meta_signals_{for_date}.json"
        if not path.exists():
            return []
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        signals = data.get("meta_signals", [])
        self._cache[cache_key] = signals
        return signals
    
    def get_insights(self, for_date: date) -> list[dict]:
        """Load insights/hypotheses for a specific date."""
        cache_key = f"insights_{for_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Check multiple possible locations
        possible_paths = [
            self.data_root / "insights" / f"hypotheses_{for_date}.json",
            self.data_root / "insights" / f"insights_{for_date}.json",
        ]
        
        for path in possible_paths:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                bundles = data.get("bundles", [])
                self._cache[cache_key] = bundles
                return bundles
        
        return []
    
    def get_briefs(self, for_date: date) -> list[dict]:
        """Load daily briefs for a specific date."""
        cache_key = f"briefs_{for_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        path = self.data_root / "briefs" / f"daily_brief_{for_date}.json"
        if not path.exists():
            return []
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        briefs = data.get("briefs", data.get("stories", []))
        self._cache[cache_key] = briefs
        return briefs
    
    def get_date_range_signals(self, start_date: date, end_date: date) -> list[dict]:
        """Get all meta_signals in a date range."""
        all_signals = []
        current = start_date
        while current <= end_date:
            all_signals.extend(self.get_meta_signals(current))
            current += timedelta(days=1)
        return all_signals
    
    def get_date_range_insights(self, start_date: date, end_date: date) -> list[dict]:
        """Get all insights in a date range."""
        all_insights = []
        current = start_date
        while current <= end_date:
            all_insights.extend(self.get_insights(current))
            current += timedelta(days=1)
        return all_insights


def entity_matches(entity: str, signal_data: dict) -> bool:
    """
    Check if an entity appears in signal data.
    
    Looks in concept_name, description, entities list, etc.
    """
    entity_lower = entity.lower()
    
    # Direct name match
    concept_name = signal_data.get("concept_name", "").lower()
    if entity_lower in concept_name:
        return True
    
    # Description match
    description = signal_data.get("description", "").lower()
    if entity_lower in description:
        return True
    
    # Entities list match
    entities = signal_data.get("entities", [])
    if isinstance(entities, list):
        for e in entities:
            if entity_lower in str(e).lower():
                return True
    
    # Supporting insights entities
    for insight in signal_data.get("supporting_insights", []):
        insight_entities = insight.get("entities", [])
        for e in insight_entities:
            if entity_lower in str(e).lower():
                return True
    
    return False


def calculate_momentum_delta(
    entity: str,
    pre_signals: list[dict],
    post_signals: list[dict],
) -> tuple[float, list[SupportingEvidence]]:
    """
    Calculate momentum change for an entity between pre and post periods.
    
    Returns (delta, supporting_evidence)
    - Positive delta = increased momentum (good for bullish)
    - Negative delta = decreased momentum (good for bearish)
    """
    evidence = []
    
    def count_mentions(signals):
        count = 0
        total_confidence = 0.0
        for s in signals:
            if entity_matches(entity, s):
                count += 1
                total_confidence += s.get("concept_confidence", 0.5)
        return count, total_confidence
    
    pre_count, pre_confidence = count_mentions(pre_signals)
    post_count, post_confidence = count_mentions(post_signals)
    
    # Calculate delta
    if pre_count == 0:
        # New appearance
        delta = post_count * 0.5
    else:
        # Relative change
        delta = (post_count - pre_count) / pre_count
    
    # Record evidence if significant
    if post_count > 0:
        evidence.append(SupportingEvidence(
            source="meta_signals",
            signal_type="mention_count",
            date="post_period",
            description=f"Entity mentioned {post_count} times (vs {pre_count} pre)",
            relevance_score=min(1.0, post_count / 5),
        ))
    
    # Confidence delta
    if pre_confidence > 0 and post_confidence > 0:
        conf_delta = (post_confidence / max(1, post_count)) - (pre_confidence / max(1, pre_count))
        evidence.append(SupportingEvidence(
            source="meta_signals",
            signal_type="confidence_trend",
            date="post_period",
            description=f"Avg confidence changed by {conf_delta:+.2f}",
            relevance_score=abs(conf_delta),
        ))
    
    return delta, evidence


def check_maturity_progression(
    entity: str,
    pre_signals: list[dict],
    post_signals: list[dict],
) -> tuple[bool, list[SupportingEvidence]]:
    """
    Check if an entity's signal maturity progressed.
    
    emerging -> trending -> established is positive progression
    """
    maturity_order = {"emerging": 0, "trending": 1, "established": 2, "mature": 3}
    evidence = []
    
    def get_max_maturity(signals):
        max_stage = -1
        for s in signals:
            if entity_matches(entity, s):
                stage = s.get("maturity_stage", "emerging")
                if stage in maturity_order:
                    max_stage = max(max_stage, maturity_order[stage])
        return max_stage
    
    pre_maturity = get_max_maturity(pre_signals)
    post_maturity = get_max_maturity(post_signals)
    
    if post_maturity > pre_maturity and post_maturity >= 0:
        stages = list(maturity_order.keys())
        evidence.append(SupportingEvidence(
            source="meta_signals",
            signal_type="maturity_progression",
            date="post_period",
            description=f"Maturity progressed from {stages[pre_maturity] if pre_maturity >= 0 else 'none'} to {stages[post_maturity]}",
            relevance_score=0.7,
        ))
        return True, evidence
    
    return False, evidence


def check_signal_persistence(
    entity: str,
    signals: list[dict],
    min_days: int = 3,
) -> tuple[bool, list[SupportingEvidence]]:
    """
    Check if entity signals persist over multiple days.
    
    Persistence indicates genuine trend vs noise.
    """
    evidence = []
    
    dates_seen = set()
    for s in signals:
        if entity_matches(entity, s):
            # Try multiple date fields
            for date_field in ["date", "last_updated", "first_seen"]:
                if date_field in s:
                    dates_seen.add(str(s[date_field])[:10])
    
    persistent = len(dates_seen) >= min_days
    
    if dates_seen:
        evidence.append(SupportingEvidence(
            source="meta_signals",
            signal_type="persistence",
            date="aggregate",
            description=f"Entity appeared on {len(dates_seen)} unique dates",
            relevance_score=min(1.0, len(dates_seen) / 5),
        ))
    
    return persistent, evidence


def resolve_bullish_prediction(
    prediction: ExpiredPrediction,
    loader: SignalDataLoader,
) -> ResolvedOutcome:
    """
    Resolve a bullish (direction=up) prediction.
    
    Correct if ANY of:
    - Entity appears in positive momentum signals
    - Strong narrative emergence
    - Price/progress indicators in meta_signals
    - Continued multi-source mentions
    
    v1.1: Added debug_features, decision_trace, unclear_reason for explainability.
    """
    all_evidence = []
    correctness_score = 0.0
    debug_features = {}
    decision_trace = []
    
    # Define time windows
    check_date = prediction.check_date
    prediction_date = prediction.date_made or (check_date - timedelta(days=14))
    
    decision_trace.append(f"Evaluating bullish prediction for entity '{prediction.entity}'")
    decision_trace.append(f"Period: {prediction_date} to {check_date}")
    
    # Pre-period: 3 days before prediction
    pre_start = prediction_date - timedelta(days=3)
    pre_signals = loader.get_date_range_signals(pre_start, prediction_date)
    
    # Post-period: prediction date to check date
    post_signals = loader.get_date_range_signals(prediction_date, check_date)
    
    entity = prediction.entity
    
    # Feature: meta_signal_presence
    post_mention_count = sum(1 for s in post_signals if entity_matches(entity, s))
    debug_features["meta_signal_presence"] = 1.0 if post_mention_count > 0 else 0.0
    debug_features["post_mention_count"] = float(post_mention_count)
    decision_trace.append(f"Post-period mentions: {post_mention_count}")
    
    # Check 1: Momentum delta
    momentum_delta, evidence = calculate_momentum_delta(entity, pre_signals, post_signals)
    all_evidence.extend(evidence)
    debug_features["mention_delta_7d"] = momentum_delta
    debug_features["momentum_direction"] = 1.0 if momentum_delta > 0 else (-1.0 if momentum_delta < 0 else 0.0)
    
    if momentum_delta > 0.2:
        correctness_score += 0.3
        decision_trace.append(f"[+0.3] Positive momentum delta: {momentum_delta:.2f}")
    elif momentum_delta < -0.2:
        correctness_score -= 0.2
        decision_trace.append(f"[-0.2] Negative momentum delta: {momentum_delta:.2f}")
    else:
        decision_trace.append(f"[  0] Neutral momentum delta: {momentum_delta:.2f}")
    
    # Check 2: Maturity progression
    progressed, evidence = check_maturity_progression(entity, pre_signals, post_signals)
    all_evidence.extend(evidence)
    debug_features["maturity_progressed"] = 1.0 if progressed else 0.0
    
    if progressed:
        correctness_score += 0.25
        decision_trace.append("[+0.25] Maturity stage progressed")
    else:
        decision_trace.append("[  0] No maturity progression")
    
    # Check 3: Signal persistence
    persistent, evidence = check_signal_persistence(entity, post_signals)
    all_evidence.extend(evidence)
    debug_features["signal_persistent"] = 1.0 if persistent else 0.0
    
    if persistent:
        correctness_score += 0.2
        decision_trace.append("[+0.2] Signals persisted across multiple days")
    else:
        decision_trace.append("[  0] No signal persistence")
    
    # Check 4: Multi-source validation
    post_insights = loader.get_date_range_insights(prediction_date, check_date)
    categories_seen = set()
    for insight in post_insights:
        for hyp in insight.get("hypotheses", []):
            if entity_matches(entity, hyp.get("evidence_used", {})):
                for cat in hyp.get("evidence_used", {}).get("source_categories", []):
                    categories_seen.add(cat)
    
    debug_features["source_diversity_count"] = float(len(categories_seen))
    
    if len(categories_seen) >= 2:
        all_evidence.append(SupportingEvidence(
            source="insights",
            signal_type="multi_source",
            date="post_period",
            description=f"Validated across {len(categories_seen)} source categories",
            relevance_score=min(1.0, len(categories_seen) / 3),
        ))
        correctness_score += 0.25
        decision_trace.append(f"[+0.25] Multi-source validation: {len(categories_seen)} categories")
    else:
        decision_trace.append(f"[  0] Limited source diversity: {len(categories_seen)} categories")
    
    debug_features["final_score"] = correctness_score
    decision_trace.append(f"Final score: {correctness_score:.2f}")
    
    # Determine outcome and unclear_reason
    if correctness_score >= 0.5:
        outcome = OutcomeStatus.CORRECT
        unclear_reason = UnclearReason.NONE
        decision_trace.append("Outcome: CORRECT (score >= 0.5)")
    elif correctness_score <= 0.0:
        outcome = OutcomeStatus.INCORRECT
        unclear_reason = UnclearReason.NONE
        decision_trace.append("Outcome: INCORRECT (score <= 0.0)")
    else:
        outcome = OutcomeStatus.UNCLEAR
        # Determine why unclear
        if post_mention_count == 0 and len(pre_signals) == 0:
            unclear_reason = UnclearReason.DATA_MISSING
            decision_trace.append("Outcome: UNCLEAR - no signal data available")
        elif momentum_delta > 0 and not persistent:
            unclear_reason = UnclearReason.LOW_SIGNAL
            decision_trace.append("Outcome: UNCLEAR - signals too weak/transient")
        else:
            unclear_reason = UnclearReason.MIXED_EVIDENCE
            decision_trace.append("Outcome: UNCLEAR - mixed evidence")
    
    return ResolvedOutcome(
        prediction_id=prediction.prediction_id,
        outcome=outcome,
        confidence_score=abs(correctness_score),
        supporting_evidence=all_evidence,
        resolution_method="bullish_heuristics",
        debug_features=debug_features,
        decision_trace=decision_trace,
        unclear_reason=unclear_reason,
    )


def resolve_bearish_prediction(
    prediction: ExpiredPrediction,
    loader: SignalDataLoader,
) -> ResolvedOutcome:
    """
    Resolve a bearish (direction=down) prediction.
    
    Correct if:
    - Narrative collapse
    - Signal disappearance
    - Negative evidence dominance
    
    v1.1: Added debug_features, decision_trace, unclear_reason for explainability.
    """
    all_evidence = []
    correctness_score = 0.0
    debug_features = {}
    decision_trace = []
    
    check_date = prediction.check_date
    prediction_date = prediction.date_made or (check_date - timedelta(days=14))
    
    decision_trace.append(f"Evaluating bearish prediction for entity '{prediction.entity}'")
    decision_trace.append(f"Period: {prediction_date} to {check_date}")
    
    pre_start = prediction_date - timedelta(days=3)
    pre_signals = loader.get_date_range_signals(pre_start, prediction_date)
    post_signals = loader.get_date_range_signals(prediction_date, check_date)
    
    entity = prediction.entity
    
    # Feature: counts
    pre_count = sum(1 for s in pre_signals if entity_matches(entity, s))
    post_count = sum(1 for s in post_signals if entity_matches(entity, s))
    debug_features["pre_mention_count"] = float(pre_count)
    debug_features["post_mention_count"] = float(post_count)
    debug_features["meta_signal_presence"] = 1.0 if post_count > 0 else 0.0
    decision_trace.append(f"Pre-period mentions: {pre_count}, Post-period: {post_count}")
    
    # Check 1: Momentum collapse
    momentum_delta, evidence = calculate_momentum_delta(entity, pre_signals, post_signals)
    all_evidence.extend(evidence)
    debug_features["mention_delta_7d"] = momentum_delta
    debug_features["momentum_direction"] = 1.0 if momentum_delta > 0 else (-1.0 if momentum_delta < 0 else 0.0)
    
    if momentum_delta < -0.3:
        correctness_score += 0.4
        decision_trace.append(f"[+0.4] Significant momentum collapse: {momentum_delta:.2f}")
    elif momentum_delta > 0.2:
        correctness_score -= 0.3
        decision_trace.append(f"[-0.3] Momentum actually increased: {momentum_delta:.2f}")
    else:
        decision_trace.append(f"[  0] Neutral momentum change: {momentum_delta:.2f}")
    
    # Check 2: Signal disappearance
    debug_features["signal_disappeared"] = 1.0 if (pre_count > 0 and post_count == 0) else 0.0
    
    if pre_count > 0 and post_count == 0:
        all_evidence.append(SupportingEvidence(
            source="meta_signals",
            signal_type="signal_disappearance",
            date="post_period",
            description=f"Entity signals disappeared (was {pre_count}, now 0)",
            relevance_score=0.8,
        ))
        correctness_score += 0.3
        decision_trace.append(f"[+0.3] Signals disappeared completely")
    else:
        decision_trace.append(f"[  0] Signals still present ({post_count} mentions)")
    
    # Check 3: Maturity regression or stagnation
    progressed, _ = check_maturity_progression(entity, pre_signals, post_signals)
    debug_features["maturity_progressed"] = 1.0 if progressed else 0.0
    
    if not progressed and pre_count > 0:
        all_evidence.append(SupportingEvidence(
            source="meta_signals",
            signal_type="no_progression",
            date="post_period",
            description="No maturity progression despite prior activity",
            relevance_score=0.5,
        ))
        correctness_score += 0.15
        decision_trace.append("[+0.15] No maturity progression (stagnation)")
    else:
        decision_trace.append("[  0] Maturity check: N/A or progressed")
    
    # Check 4: Lack of persistence
    persistent, evidence = check_signal_persistence(entity, post_signals)
    all_evidence.extend(evidence)
    debug_features["signal_persistent"] = 1.0 if persistent else 0.0
    
    if not persistent:
        correctness_score += 0.15
        decision_trace.append("[+0.15] Signals not persistent (fading)")
    else:
        decision_trace.append("[  0] Signals persisted")
    
    debug_features["final_score"] = correctness_score
    decision_trace.append(f"Final score: {correctness_score:.2f}")
    
    # Determine outcome and unclear_reason
    if correctness_score >= 0.5:
        outcome = OutcomeStatus.CORRECT
        unclear_reason = UnclearReason.NONE
        decision_trace.append("Outcome: CORRECT (score >= 0.5)")
    elif correctness_score <= 0.0:
        outcome = OutcomeStatus.INCORRECT
        unclear_reason = UnclearReason.NONE
        decision_trace.append("Outcome: INCORRECT (score <= 0.0)")
    else:
        outcome = OutcomeStatus.UNCLEAR
        # Determine why unclear
        if pre_count == 0 and post_count == 0:
            unclear_reason = UnclearReason.DATA_MISSING
            decision_trace.append("Outcome: UNCLEAR - no signal data available")
        elif momentum_delta > -0.1 and momentum_delta < 0.1:
            unclear_reason = UnclearReason.LOW_SIGNAL
            decision_trace.append("Outcome: UNCLEAR - signals too weak to determine")
        else:
            unclear_reason = UnclearReason.MIXED_EVIDENCE
            decision_trace.append("Outcome: UNCLEAR - mixed evidence")
    
    return ResolvedOutcome(
        prediction_id=prediction.prediction_id,
        outcome=outcome,
        confidence_score=abs(correctness_score),
        supporting_evidence=all_evidence,
        resolution_method="bearish_heuristics",
        debug_features=debug_features,
        decision_trace=decision_trace,
        unclear_reason=unclear_reason,
    )


def resolve_unknown_direction(
    prediction: ExpiredPrediction,
    loader: SignalDataLoader,
) -> ResolvedOutcome:
    """
    Resolve a prediction with unknown/neutral direction.
    
    For predictions like "monitor for developments", check if
    any significant signal activity occurred.
    
    v1.1: Added debug_features, decision_trace, unclear_reason for explainability.
    """
    all_evidence = []
    debug_features = {}
    decision_trace = []
    
    check_date = prediction.check_date
    prediction_date = prediction.date_made or (check_date - timedelta(days=14))
    
    decision_trace.append(f"Evaluating neutral/watch prediction for entity '{prediction.entity}'")
    decision_trace.append(f"Period: {prediction_date} to {check_date}")
    
    post_signals = loader.get_date_range_signals(prediction_date, check_date)
    
    entity = prediction.entity
    
    # Check for any activity
    mention_count = sum(1 for s in post_signals if entity_matches(entity, s))
    debug_features["meta_signal_presence"] = 1.0 if mention_count > 0 else 0.0
    debug_features["post_mention_count"] = float(mention_count)
    debug_features["mention_delta_7d"] = 0.0  # N/A for unknown direction
    debug_features["momentum_direction"] = 0.0
    
    decision_trace.append(f"Post-period mentions: {mention_count}")
    
    if mention_count > 0:
        all_evidence.append(SupportingEvidence(
            source="meta_signals",
            signal_type="activity_detected",
            date="post_period",
            description=f"Detected {mention_count} signal mentions",
            relevance_score=min(1.0, mention_count / 3),
        ))
    
    # For unknown direction, mark as unclear if no strong signal either way
    # Mark correct if entity showed significant activity (prediction to watch was validated)
    if mention_count >= 3:
        outcome = OutcomeStatus.CORRECT
        confidence = min(0.7, mention_count / 5)
        unclear_reason = UnclearReason.NONE
        decision_trace.append(f"[+] Significant activity detected ({mention_count} mentions)")
        decision_trace.append("Outcome: CORRECT (watch prediction validated)")
    elif mention_count == 0:
        outcome = OutcomeStatus.UNCLEAR
        confidence = 0.3
        unclear_reason = UnclearReason.DATA_MISSING
        decision_trace.append("[?] No activity detected")
        decision_trace.append("Outcome: UNCLEAR - no signal data available")
    else:
        outcome = OutcomeStatus.UNCLEAR
        confidence = 0.4
        unclear_reason = UnclearReason.LOW_SIGNAL
        decision_trace.append(f"[?] Minimal activity ({mention_count} mentions)")
        decision_trace.append("Outcome: UNCLEAR - signals too weak")
    
    debug_features["final_score"] = confidence
    debug_features["source_diversity_count"] = 0.0  # N/A
    debug_features["signal_persistent"] = 0.0  # N/A
    
    return ResolvedOutcome(
        prediction_id=prediction.prediction_id,
        outcome=outcome,
        confidence_score=confidence,
        supporting_evidence=all_evidence,
        resolution_method="unknown_direction_heuristics",
        debug_features=debug_features,
        decision_trace=decision_trace,
        unclear_reason=unclear_reason,
    )


def resolve_outcome(
    prediction: ExpiredPrediction,
    data_root: Path = None,
) -> ResolvedOutcome:
    """
    Determine whether a prediction was correct.
    
    Main entry point for outcome resolution.
    
    Args:
        prediction: The expired prediction to resolve
        data_root: Root data directory
    
    Returns:
        ResolvedOutcome with determination and evidence
    """
    loader = SignalDataLoader(data_root)
    
    if prediction.direction == Direction.UP:
        return resolve_bullish_prediction(prediction, loader)
    elif prediction.direction == Direction.DOWN:
        return resolve_bearish_prediction(prediction, loader)
    else:
        return resolve_unknown_direction(prediction, loader)


def resolve_all(
    predictions: list[ExpiredPrediction],
    data_root: Path = None,
) -> list[ResolvedOutcome]:
    """
    Resolve outcomes for multiple predictions.
    
    Uses a shared loader for efficiency.
    """
    loader = SignalDataLoader(data_root)
    outcomes = []
    
    for pred in predictions:
        if pred.direction == Direction.UP:
            outcome = resolve_bullish_prediction(pred, loader)
        elif pred.direction == Direction.DOWN:
            outcome = resolve_bearish_prediction(pred, loader)
        else:
            outcome = resolve_unknown_direction(pred, loader)
        outcomes.append(outcome)
    
    return outcomes
