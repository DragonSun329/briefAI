"""
Action Predictions Module v1.0

Integrates incentive-based action predictions into the Hypothesis Engine.
Converts pressure analysis into predicted company actions.

Part of briefAI Action Forecasting System.

Pipeline:
    HypothesisEngine → PressureAnalysis → ActionPredictions → EnhancedHypothesis
"""

import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

from loguru import logger

from utils.incentive_inference import (
    analyze_meta_signal,
    get_all_actions_from_analysis,
    PressureAnalysis,
    PredictedAction,
    DetectedPressure,
)


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_ACTION_EVENT_TYPES_PATH = Path(__file__).parent.parent / "config" / "action_event_types.json"

# Confidence adjustments
ACTION_PREDICTION_BONUS = 0.12           # Bonus for having action predictions
MEDIA_ONLY_CONFIDENCE_CAP = 0.45         # Cap for media-only predictions
MIN_ACTION_PROBABILITY = 0.25            # Minimum probability to include action

# =============================================================================
# CONFIG LOADER
# =============================================================================

_ACTION_EVENT_TYPES_CACHE = None


def load_action_event_types(config_path: Path = None) -> Dict[str, Any]:
    """Load action event types config with caching."""
    global _ACTION_EVENT_TYPES_CACHE
    
    if _ACTION_EVENT_TYPES_CACHE is not None:
        return _ACTION_EVENT_TYPES_CACHE
    
    if config_path is None:
        config_path = DEFAULT_ACTION_EVENT_TYPES_PATH
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            _ACTION_EVENT_TYPES_CACHE = json.load(f)
            return _ACTION_EVENT_TYPES_CACHE
    except Exception as e:
        logger.warning(f"Failed to load action_event_types.json: {e}")
        return {'event_types': {}}


def clear_cache():
    """Clear config cache."""
    global _ACTION_EVENT_TYPES_CACHE
    _ACTION_EVENT_TYPES_CACHE = None


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ActionPredictionEvent:
    """
    A predicted company action event.
    
    This is the core output of the action forecasting system.
    Each event is:
    - Specific to a company
    - Tied to a measurable outcome
    - Time-bounded
    - Derived from incentive analysis
    """
    event_type: str                      # e.g., 'partnership_announcement'
    event_display_name: str              # e.g., 'Partnership Announcement'
    entity: str                          # Company expected to act
    probability: float                   # 0.0 - 1.0
    timeframe_days: int                  # Expected timeframe
    source_pressure: str                 # Driving pressure type
    source_pressure_confidence: float    # Confidence in pressure detection
    
    # Optional fields
    counterparty_type: Optional[str] = None      # Expected counterparty type
    direction: Optional[str] = None               # For directional events (e.g., pricing up/down)
    note: Optional[str] = None                    # Additional context
    
    # Observable query (machine-testable)
    observable_query: Optional[Dict[str, Any]] = None
    
    # Tracking
    prediction_id: str = ""              # Unique ID for tracking
    created_at: str = ""                 # ISO timestamp
    
    def __post_init__(self):
        if not self.prediction_id:
            self.prediction_id = self._generate_id()
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
    
    def _generate_id(self) -> str:
        """Generate stable prediction ID."""
        content = f"{self.event_type}|{self.entity}|{self.source_pressure}"
        return "ap_" + hashlib.sha256(content.encode()).hexdigest()[:12]
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'event_type': self.event_type,
            'event_display_name': self.event_display_name,
            'entity': self.entity,
            'probability': round(self.probability, 4),
            'timeframe_days': self.timeframe_days,
            'source_pressure': self.source_pressure,
            'source_pressure_confidence': round(self.source_pressure_confidence, 4),
            'prediction_id': self.prediction_id,
            'created_at': self.created_at,
        }
        if self.counterparty_type:
            result['counterparty_type'] = self.counterparty_type
        if self.direction:
            result['direction'] = self.direction
        if self.note:
            result['note'] = self.note
        if self.observable_query:
            result['observable_query'] = self.observable_query
        return result
    
    @classmethod
    def from_predicted_action(
        cls,
        action: PredictedAction,
        pressure_confidence: float,
        event_types_config: Dict[str, Any] = None,
    ) -> 'ActionPredictionEvent':
        """Create from PredictedAction."""
        if event_types_config is None:
            event_types_config = load_action_event_types().get('event_types', {})
        
        event_config = event_types_config.get(action.event_type, {})
        display_name = event_config.get('display_name', action.event_type.replace('_', ' ').title())
        
        # Build observable query from event config
        observables = event_config.get('observables', [])
        observable_query = None
        if observables:
            first_obs = observables[0]
            observable_query = {
                'source': first_obs.get('source', 'news'),
                'metric': first_obs.get('metric', 'count'),
                'aggregation': first_obs.get('aggregation', 'count'),
                'window_days': first_obs.get('window_days', action.timeframe_days),
                'entity': action.entity,
            }
        
        return cls(
            event_type=action.event_type,
            event_display_name=display_name,
            entity=action.entity or 'unknown',
            probability=action.probability,
            timeframe_days=action.timeframe_days,
            source_pressure=action.source_pressure,
            source_pressure_confidence=pressure_confidence,
            counterparty_type=action.counterparty_type,
            direction=action.direction,
            note=action.note,
            observable_query=observable_query,
        )


@dataclass
class ActionPredictionBundle:
    """
    Bundle of action predictions for a meta-signal.
    """
    meta_signal_id: str
    entity: Optional[str]
    pressure_analysis: Dict[str, Any]    # Serialized PressureAnalysis
    action_predictions: List[ActionPredictionEvent]
    has_action_predictions: bool
    action_count: int
    confidence_adjustment: float         # How much to adjust hypothesis confidence
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'meta_signal_id': self.meta_signal_id,
            'entity': self.entity,
            'pressure_analysis': self.pressure_analysis,
            'action_predictions': [ap.to_dict() for ap in self.action_predictions],
            'has_action_predictions': self.has_action_predictions,
            'action_count': self.action_count,
            'confidence_adjustment': round(self.confidence_adjustment, 4),
        }


# =============================================================================
# MAIN FUNCTIONS
# =============================================================================

def generate_action_predictions(
    meta: Dict[str, Any],
    min_probability: float = MIN_ACTION_PROBABILITY,
) -> ActionPredictionBundle:
    """
    Generate action predictions for a meta-signal.
    
    Args:
        meta: Meta-signal dict
        min_probability: Minimum probability to include action
    
    Returns:
        ActionPredictionBundle with action predictions
    """
    meta_id = meta.get('id', meta.get('slug', meta.get('meta_id', 'unknown')))
    
    # Run pressure analysis
    pressure_analysis = analyze_meta_signal(meta)
    
    # Get actions from pressures
    raw_actions = get_all_actions_from_analysis(pressure_analysis, min_probability)
    
    # Convert to ActionPredictionEvents
    event_types_config = load_action_event_types().get('event_types', {})
    action_predictions = []
    
    for action in raw_actions:
        # Get pressure confidence for this action
        pressure_conf = 0.5  # Default
        for p in pressure_analysis.pressures:
            if p.pressure_type == action.source_pressure:
                pressure_conf = p.confidence
                break
        
        event = ActionPredictionEvent.from_predicted_action(
            action=action,
            pressure_confidence=pressure_conf,
            event_types_config=event_types_config,
        )
        action_predictions.append(event)
    
    # Calculate confidence adjustment
    has_actions = len(action_predictions) > 0
    if has_actions:
        # Bonus for having action predictions
        confidence_adjustment = ACTION_PREDICTION_BONUS
    else:
        # No penalty, but track that it's media-only
        confidence_adjustment = 0.0
    
    return ActionPredictionBundle(
        meta_signal_id=meta_id,
        entity=pressure_analysis.entity,
        pressure_analysis=pressure_analysis.to_dict(),
        action_predictions=action_predictions,
        has_action_predictions=has_actions,
        action_count=len(action_predictions),
        confidence_adjustment=confidence_adjustment,
    )


def enhance_hypothesis_with_actions(
    hypothesis_dict: Dict[str, Any],
    action_bundle: ActionPredictionBundle,
) -> Dict[str, Any]:
    """
    Enhance a hypothesis with action predictions.
    
    Adds:
    - action_predictions field
    - pressure_analysis field
    - Adjusts confidence if needed
    
    Args:
        hypothesis_dict: Hypothesis as dict
        action_bundle: ActionPredictionBundle
    
    Returns:
        Enhanced hypothesis dict
    """
    enhanced = hypothesis_dict.copy()
    
    # Add action predictions
    enhanced['action_predictions'] = [ap.to_dict() for ap in action_bundle.action_predictions]
    enhanced['pressure_analysis'] = action_bundle.pressure_analysis
    enhanced['has_action_predictions'] = action_bundle.has_action_predictions
    
    # Adjust confidence
    if action_bundle.has_action_predictions:
        # Apply bonus (capped at 1.0)
        current_conf = enhanced.get('confidence', 0.5)
        enhanced['confidence'] = min(current_conf + action_bundle.confidence_adjustment, 1.0)
        enhanced['confidence_adjustment_reason'] = 'action_prediction_bonus'
    else:
        # Apply media-only cap if no action predictions
        current_conf = enhanced.get('confidence', 0.5)
        if current_conf > MEDIA_ONLY_CONFIDENCE_CAP:
            enhanced['confidence'] = MEDIA_ONLY_CONFIDENCE_CAP
            enhanced['confidence_adjustment_reason'] = 'media_only_cap'
    
    return enhanced


def process_hypothesis_bundle(
    bundle_dict: Dict[str, Any],
    meta: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Process a MetaHypothesisBundle and add action predictions.
    
    This is the main integration point for the hypothesis engine.
    
    Args:
        bundle_dict: MetaHypothesisBundle as dict
        meta: Original meta-signal
    
    Returns:
        Enhanced bundle dict with action predictions
    """
    # Generate action predictions
    action_bundle = generate_action_predictions(meta)
    
    # Enhance each hypothesis in the bundle
    enhanced_hypotheses = []
    for hyp in bundle_dict.get('hypotheses', []):
        enhanced = enhance_hypothesis_with_actions(hyp, action_bundle)
        enhanced_hypotheses.append(enhanced)
    
    # Update bundle
    enhanced_bundle = bundle_dict.copy()
    enhanced_bundle['hypotheses'] = enhanced_hypotheses
    enhanced_bundle['action_bundle'] = action_bundle.to_dict()
    enhanced_bundle['has_action_predictions'] = action_bundle.has_action_predictions
    enhanced_bundle['total_action_predictions'] = action_bundle.action_count
    
    return enhanced_bundle


# =============================================================================
# FORECAST HISTORY INTEGRATION
# =============================================================================

def action_predictions_to_forecast_records(
    action_bundle: ActionPredictionBundle,
    concept_name: str,
    base_date: str = None,
) -> List[Dict[str, Any]]:
    """
    Convert action predictions to forecast history records.
    
    These records are appended to forecast_history.jsonl.
    
    Args:
        action_bundle: ActionPredictionBundle
        concept_name: Concept name from meta-signal
        base_date: Base date (defaults to today)
    
    Returns:
        List of forecast records
    """
    if base_date is None:
        base_date = datetime.utcnow().strftime('%Y-%m-%d')
    
    records = []
    
    for ap in action_bundle.action_predictions:
        record = {
            'forecast_id': ap.prediction_id,
            'forecast_type': 'action_event',  # New type!
            'event_type': ap.event_type,
            'entity': ap.entity,
            'concept_name': concept_name,
            'probability': ap.probability,
            'timeframe_days': ap.timeframe_days,
            'source_pressure': ap.source_pressure,
            'date': base_date,
            'logged_at': datetime.utcnow().isoformat(),
        }
        
        if ap.counterparty_type:
            record['counterparty_type'] = ap.counterparty_type
        if ap.direction:
            record['direction'] = ap.direction
        if ap.note:
            record['note'] = ap.note
        if ap.observable_query:
            record['observable_query'] = ap.observable_query
        
        records.append(record)
    
    return records


# =============================================================================
# BRIEF OUTPUT HELPERS
# =============================================================================

def format_action_predictions_for_brief(
    action_predictions: List[ActionPredictionEvent],
    max_items: int = 5,
) -> str:
    """
    Format action predictions for daily brief output.
    
    Returns markdown-formatted section.
    """
    if not action_predictions:
        return ""
    
    lines = ["## 🎯 Expected Company Actions\n"]
    
    # Sort by probability descending
    sorted_predictions = sorted(
        action_predictions, 
        key=lambda x: x.probability, 
        reverse=True
    )[:max_items]
    
    for ap in sorted_predictions:
        # Format entity
        entity = ap.entity.title() if ap.entity else "Unknown"
        
        # Format event with direction if applicable
        event_desc = ap.event_display_name
        if ap.direction:
            event_desc = f"{ap.event_display_name} ({ap.direction})"
        
        # Format counterparty if applicable
        counterparty_str = ""
        if ap.counterparty_type:
            counterparty_str = f" with {ap.counterparty_type.replace('_', ' ')}"
        
        # Format timeframe
        timeframe_str = f"within {ap.timeframe_days} days"
        
        # Format probability
        prob_pct = int(ap.probability * 100)
        
        # Build line
        line = f"- **{entity}** likely to announce **{event_desc}**{counterparty_str} {timeframe_str} ({prob_pct}% confidence)"
        
        # Add note if present
        if ap.note:
            line += f"\n  - _{ap.note}_"
        
        lines.append(line)
    
    lines.append("")
    return "\n".join(lines)


def get_action_summary_stats(
    action_predictions: List[ActionPredictionEvent],
) -> Dict[str, Any]:
    """
    Get summary statistics for action predictions.
    """
    if not action_predictions:
        return {
            'total': 0,
            'by_event_type': {},
            'by_entity': {},
            'avg_probability': 0,
            'avg_timeframe_days': 0,
        }
    
    by_event_type = {}
    by_entity = {}
    
    for ap in action_predictions:
        by_event_type[ap.event_type] = by_event_type.get(ap.event_type, 0) + 1
        if ap.entity:
            by_entity[ap.entity] = by_entity.get(ap.entity, 0) + 1
    
    return {
        'total': len(action_predictions),
        'by_event_type': by_event_type,
        'by_entity': by_entity,
        'avg_probability': sum(ap.probability for ap in action_predictions) / len(action_predictions),
        'avg_timeframe_days': sum(ap.timeframe_days for ap in action_predictions) / len(action_predictions),
    }
