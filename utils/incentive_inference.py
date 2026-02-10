"""
Incentive Inference Module v1.0

Part of briefAI Action Forecasting System.

This module analyzes meta-signals and extracts economic/strategic pressure types
that constrain company behavior. The output drives action-based predictions.

Pipeline:
    MetaSignals → IncentiveInference → PressureTypes → ActionPredictions

Key features:
- Deterministic pressure detection (no LLM calls)
- Multi-pressure scoring with confidence
- Entity-specific pressure modifiers
- Evidence tracing for auditability
"""

import json
import re
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from pathlib import Path
from collections import Counter

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_PRESSURE_ACTION_MAP_PATH = Path(__file__).parent.parent / "config" / "pressure_action_map.json"

# Minimum keyword matches to claim pressure detection
MIN_PRESSURE_KEYWORDS = 2

# Maximum pressures to return per meta-signal
MAX_PRESSURES_PER_SIGNAL = 3

# Confidence thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.70
MEDIUM_CONFIDENCE_THRESHOLD = 0.50


# =============================================================================
# CONFIG LOADER
# =============================================================================

_PRESSURE_MAP_CACHE = None


def load_pressure_action_map(config_path: Path = None) -> Dict[str, Any]:
    """Load pressure-action mapping config with caching."""
    global _PRESSURE_MAP_CACHE
    
    if _PRESSURE_MAP_CACHE is not None:
        return _PRESSURE_MAP_CACHE
    
    if config_path is None:
        config_path = DEFAULT_PRESSURE_ACTION_MAP_PATH
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            _PRESSURE_MAP_CACHE = json.load(f)
            return _PRESSURE_MAP_CACHE
    except Exception as e:
        logger.warning(f"Failed to load pressure_action_map.json: {e}")
        return {'pressure_types': {}}


def clear_cache():
    """Clear the config cache (useful for testing)."""
    global _PRESSURE_MAP_CACHE
    _PRESSURE_MAP_CACHE = None


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PressureEvidence:
    """Evidence for a detected pressure."""
    source_field: str                    # Where the match was found
    matched_terms: List[str]             # Specific keywords matched
    pattern_matches: List[str]           # Pattern IDs matched
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'source_field': self.source_field,
            'matched_terms': self.matched_terms,
            'pattern_matches': self.pattern_matches,
        }


@dataclass
class DetectedPressure:
    """A detected economic/strategic pressure."""
    pressure_type: str                   # e.g., 'competitive_pressure'
    display_name: str                    # e.g., 'Competitive Pressure'
    confidence: float                    # 0.0 - 1.0
    evidence: PressureEvidence           # How we detected it
    entity: Optional[str] = None         # Primary entity under pressure
    entity_modifier: float = 1.0         # Entity-specific adjustment
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'pressure_type': self.pressure_type,
            'display_name': self.display_name,
            'confidence': round(self.confidence, 4),
            'evidence': self.evidence.to_dict(),
            'entity': self.entity,
            'entity_modifier': self.entity_modifier,
        }


@dataclass
class PressureAnalysis:
    """Complete pressure analysis for a meta-signal."""
    meta_signal_id: str
    entity: Optional[str]
    pressures: List[DetectedPressure]
    primary_pressure: Optional[DetectedPressure]
    analysis_version: str = "1.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'meta_signal_id': self.meta_signal_id,
            'entity': self.entity,
            'pressures': [p.to_dict() for p in self.pressures],
            'primary_pressure': self.primary_pressure.to_dict() if self.primary_pressure else None,
            'analysis_version': self.analysis_version,
        }


# =============================================================================
# TEXT EXTRACTION
# =============================================================================

def extract_searchable_text(meta: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract all searchable text fields from a meta-signal.
    
    Returns dict mapping field names to their text content.
    """
    text_fields = {}
    
    # Direct fields
    if 'concept_name' in meta:
        text_fields['concept_name'] = meta['concept_name'].lower()
    
    if 'meta_insight' in meta:
        text_fields['meta_insight'] = meta['meta_insight'].lower()
    
    if 'description' in meta:
        text_fields['description'] = meta['description'].lower()
    
    if 'structural_analysis' in meta:
        text_fields['structural_analysis'] = meta['structural_analysis'].lower()
    
    # Bucket tags
    if 'bucket_tags' in meta:
        text_fields['bucket_tags'] = ' '.join(meta['bucket_tags']).lower()
    
    # Supporting insights
    insight_texts = []
    for insight in meta.get('supporting_insights', []):
        if 'title' in insight:
            insight_texts.append(insight['title'].lower())
        if 'summary' in insight:
            insight_texts.append(insight['summary'].lower())
        if 'snippet' in insight:
            insight_texts.append(insight['snippet'].lower())
    if insight_texts:
        text_fields['supporting_insights'] = ' '.join(insight_texts)
    
    # Signal names
    signal_names = []
    for insight in meta.get('supporting_insights', []):
        if 'signal_name' in insight:
            signal_names.append(insight['signal_name'].lower())
    if signal_names:
        text_fields['signal_names'] = ' '.join(signal_names)
    
    return text_fields


def extract_entities(meta: Dict[str, Any]) -> List[str]:
    """Extract all mentioned entities from a meta-signal."""
    entities = set()
    
    # From concept name (extract entity if embedded)
    concept = meta.get('concept_name', '')
    # Simple heuristic: first word if capitalized
    words = concept.split()
    if words and words[0][0].isupper():
        entities.add(words[0].lower())
    
    # From supporting insights
    for insight in meta.get('supporting_insights', []):
        for entity in insight.get('entities', []):
            entities.add(entity.lower().strip())
        for entity in insight.get('key_entities', []):
            entities.add(entity.lower().strip())
    
    return list(entities)


# =============================================================================
# PRESSURE DETECTION
# =============================================================================

def detect_keyword_matches(
    text_fields: Dict[str, str],
    keywords: List[str],
) -> Tuple[int, List[str], List[str]]:
    """
    Detect keyword matches across text fields.
    
    Returns:
        (total_matches, matched_keywords, source_fields)
    """
    total_matches = 0
    matched_keywords = []
    source_fields = []
    
    for field_name, text in text_fields.items():
        for keyword in keywords:
            # Support multi-word keywords
            if keyword.lower() in text:
                total_matches += 1
                if keyword not in matched_keywords:
                    matched_keywords.append(keyword)
                if field_name not in source_fields:
                    source_fields.append(field_name)
    
    return total_matches, matched_keywords, source_fields


def detect_pattern_matches(
    text_fields: Dict[str, str],
    patterns: Dict[str, Dict[str, Any]],
    entities: List[str] = None,
) -> List[str]:
    """
    Detect pattern matches in text fields.
    
    Patterns can include:
    - keywords: List of keywords to match
    - min_entities: Minimum entity count for multi-entity patterns
    - sources: Preferred source types
    
    Returns list of matched pattern IDs.
    """
    matched_patterns = []
    combined_text = ' '.join(text_fields.values())
    
    for pattern_id, pattern_def in patterns.items():
        matched = False
        
        # Keyword pattern
        if 'keywords' in pattern_def:
            keyword_matches = sum(
                1 for kw in pattern_def['keywords'] 
                if kw.lower() in combined_text
            )
            if keyword_matches >= 1:  # At least one keyword
                matched = True
        
        # Multi-entity pattern
        if 'min_entities' in pattern_def and entities:
            if len(entities) >= pattern_def['min_entities']:
                matched = True
        
        if matched:
            matched_patterns.append(pattern_id)
    
    return matched_patterns


def calculate_pressure_confidence(
    keyword_count: int,
    pattern_count: int,
    source_diversity: int,
    entity_modifier: float = 1.0,
) -> float:
    """
    Calculate confidence score for a pressure detection.
    
    Factors:
    - Keyword matches (primary signal)
    - Pattern matches (structural signal)
    - Source diversity (cross-field confirmation)
    - Entity-specific modifiers
    """
    # Base confidence from keyword matches
    keyword_score = min(keyword_count / 5.0, 1.0)  # Saturates at 5 keywords
    
    # Pattern bonus
    pattern_bonus = min(pattern_count * 0.15, 0.30)  # Up to 0.30 bonus
    
    # Source diversity bonus
    diversity_bonus = min((source_diversity - 1) * 0.10, 0.20)  # Up to 0.20 bonus
    
    # Combine
    raw_confidence = (keyword_score * 0.60) + pattern_bonus + diversity_bonus + 0.10
    
    # Apply entity modifier
    adjusted_confidence = raw_confidence * entity_modifier
    
    # Clamp to [0, 1]
    return min(max(adjusted_confidence, 0.0), 1.0)


def detect_pressures(
    meta: Dict[str, Any],
    config: Dict[str, Any] = None,
) -> List[DetectedPressure]:
    """
    Detect economic/strategic pressures from a meta-signal.
    
    Args:
        meta: Meta-signal dict
        config: Optional pressure_action_map config (loads default if None)
    
    Returns:
        List of DetectedPressure, sorted by confidence descending
    """
    if config is None:
        config = load_pressure_action_map()
    
    pressure_types = config.get('pressure_types', {})
    entity_overrides = config.get('entity_pressure_overrides', {})
    
    # Extract searchable text
    text_fields = extract_searchable_text(meta)
    entities = extract_entities(meta)
    primary_entity = entities[0] if entities else None
    
    detected = []
    
    for pressure_id, pressure_def in pressure_types.items():
        # Get detection keywords
        keywords = pressure_def.get('detection_keywords', [])
        patterns = pressure_def.get('detection_patterns', {})
        
        # Detect matches
        keyword_count, matched_terms, source_fields = detect_keyword_matches(
            text_fields, keywords
        )
        
        pattern_matches = detect_pattern_matches(text_fields, patterns, entities)
        
        # Skip if insufficient evidence
        if keyword_count < MIN_PRESSURE_KEYWORDS and len(pattern_matches) == 0:
            continue
        
        # Get entity-specific modifier
        entity_modifier = 1.0
        if primary_entity and primary_entity in entity_overrides:
            entity_modifier = entity_overrides[primary_entity].get(pressure_id, 1.0)
        
        # Calculate confidence
        confidence = calculate_pressure_confidence(
            keyword_count=keyword_count,
            pattern_count=len(pattern_matches),
            source_diversity=len(source_fields),
            entity_modifier=entity_modifier,
        )
        
        # Apply config modifier
        config_modifier = pressure_def.get('confidence_modifier', 1.0)
        confidence *= config_modifier
        confidence = min(confidence, 1.0)
        
        # Create evidence
        evidence = PressureEvidence(
            source_field=source_fields[0] if source_fields else 'unknown',
            matched_terms=matched_terms[:5],  # Limit for readability
            pattern_matches=pattern_matches,
        )
        
        detected.append(DetectedPressure(
            pressure_type=pressure_id,
            display_name=pressure_def.get('display_name', pressure_id),
            confidence=confidence,
            evidence=evidence,
            entity=primary_entity,
            entity_modifier=entity_modifier,
        ))
    
    # Sort by confidence and limit
    detected.sort(key=lambda p: p.confidence, reverse=True)
    return detected[:MAX_PRESSURES_PER_SIGNAL]


# =============================================================================
# MAIN ANALYSIS FUNCTION
# =============================================================================

def analyze_meta_signal(meta: Dict[str, Any]) -> PressureAnalysis:
    """
    Perform full pressure analysis on a meta-signal.
    
    Args:
        meta: Meta-signal dict with concept_name, supporting_insights, etc.
    
    Returns:
        PressureAnalysis with detected pressures and primary pressure
    """
    # Get meta signal ID
    meta_id = meta.get('id', meta.get('slug', 'unknown'))
    
    # Detect pressures
    pressures = detect_pressures(meta)
    
    # Extract primary entity
    entities = extract_entities(meta)
    primary_entity = entities[0] if entities else None
    
    # Primary pressure is highest confidence
    primary_pressure = pressures[0] if pressures else None
    
    return PressureAnalysis(
        meta_signal_id=meta_id,
        entity=primary_entity,
        pressures=pressures,
        primary_pressure=primary_pressure,
    )


def analyze_multiple_signals(metas: List[Dict[str, Any]]) -> List[PressureAnalysis]:
    """Analyze multiple meta-signals for pressures."""
    return [analyze_meta_signal(meta) for meta in metas]


# =============================================================================
# PRESSURE TO ACTION MAPPING
# =============================================================================

@dataclass
class PredictedAction:
    """A predicted company action based on pressure analysis."""
    event_type: str                      # e.g., 'partnership_announcement'
    entity: Optional[str]                # Company expected to act
    probability: float                   # Likelihood (0-1)
    source_pressure: str                 # Pressure that drives this action
    timeframe_days: int                  # Expected timeframe
    direction: Optional[str] = None      # For directional events (pricing up/down)
    counterparty_type: Optional[str] = None  # Expected counterparty type
    note: Optional[str] = None           # Additional context
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'event_type': self.event_type,
            'entity': self.entity,
            'probability': round(self.probability, 4),
            'source_pressure': self.source_pressure,
            'timeframe_days': self.timeframe_days,
        }
        if self.direction:
            result['direction'] = self.direction
        if self.counterparty_type:
            result['counterparty_type'] = self.counterparty_type
        if self.note:
            result['note'] = self.note
        return result


def get_actions_from_pressure(
    pressure: DetectedPressure,
    action_event_types: Dict[str, Any] = None,
) -> List[PredictedAction]:
    """
    Get predicted actions from a detected pressure.
    
    Args:
        pressure: DetectedPressure instance
        action_event_types: Optional action event types config
    
    Returns:
        List of PredictedAction
    """
    config = load_pressure_action_map()
    pressure_types = config.get('pressure_types', {})
    
    pressure_def = pressure_types.get(pressure.pressure_type, {})
    likely_actions = pressure_def.get('likely_actions', [])
    
    # Load action event types for timeframes
    if action_event_types is None:
        try:
            action_path = Path(__file__).parent.parent / "config" / "action_event_types.json"
            with open(action_path, 'r', encoding='utf-8') as f:
                action_event_types = json.load(f).get('event_types', {})
        except Exception:
            action_event_types = {}
    
    actions = []
    for action_def in likely_actions:
        event_type = action_def.get('event_type', '')
        
        # Get timeframe from action event types
        timeframe = 30  # Default
        if event_type in action_event_types:
            timeframe = action_event_types[event_type].get('typical_timeframe_days', 30)
        
        # Calculate probability adjusted by pressure confidence
        base_probability = action_def.get('probability', 0.5)
        adjusted_probability = base_probability * pressure.confidence
        
        actions.append(PredictedAction(
            event_type=event_type,
            entity=pressure.entity,
            probability=adjusted_probability,
            source_pressure=pressure.pressure_type,
            timeframe_days=timeframe,
            direction=action_def.get('direction'),
            counterparty_type=action_def.get('counterparty_type'),
            note=action_def.get('note'),
        ))
    
    return actions


def get_all_actions_from_analysis(
    analysis: PressureAnalysis,
    min_probability: float = 0.20,
) -> List[PredictedAction]:
    """
    Get all predicted actions from a pressure analysis.
    
    Args:
        analysis: PressureAnalysis instance
        min_probability: Minimum probability threshold
    
    Returns:
        List of PredictedAction, sorted by probability descending
    """
    all_actions = []
    seen_events = set()  # Dedupe same event type
    
    for pressure in analysis.pressures:
        actions = get_actions_from_pressure(pressure)
        for action in actions:
            # Dedupe by event type (keep highest probability)
            if action.event_type in seen_events:
                continue
            if action.probability >= min_probability:
                all_actions.append(action)
                seen_events.add(action.event_type)
    
    all_actions.sort(key=lambda a: a.probability, reverse=True)
    return all_actions


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def infer_actions_from_meta(
    meta: Dict[str, Any],
    min_probability: float = 0.20,
) -> Tuple[PressureAnalysis, List[PredictedAction]]:
    """
    One-shot inference: meta-signal → pressures → actions.
    
    Returns:
        (PressureAnalysis, List[PredictedAction])
    """
    analysis = analyze_meta_signal(meta)
    actions = get_all_actions_from_analysis(analysis, min_probability)
    return analysis, actions
