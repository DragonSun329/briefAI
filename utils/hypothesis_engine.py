"""
Hypothesis Engine v2.1 - Observability & Auditability Upgrade.

Part of Gravity Engine v2.7: Predictive Foresight Layer.

This module sits AFTER meta-signals are generated and BEFORE UI/report output.
It converts structural meta-signals into testable causal hypotheses with
predicted next signals.

v2.1 Improvements:
- Confidence Transparency: confidence_inputs + confidence_debug fields
- Canonical Metric Types: Controlled vocabulary for metrics
- Observable Query: Machine-testable observables for every prediction
- Ranked Watchlist: Structured watch_items with priority scoring
- Mechanism Evidence Sources Cleanup: Primary vs secondary separation
- Measurable Falsifiers: Observable structure for each falsifier
- Full backward compatibility with v2.0

v2.0 Features (retained):
- Mechanism Scoring Trace (full explainability)
- Strength-Conditioned Predictions (weak/moderate/strong evidence)
- Observable Gate (anti-vagueness filter)
- Null Hypothesis Competition (attention_spike fallback)
- Bundle Watchlist Output (what_to_watch_next)
- Hypothesis Title Sanitization (6-8 words, no filler)

Pipeline:
    MetaSignals → HypothesisEngine → MetaHypothesisBundles → Report/UI

Key features:
- Rule-first hypothesis generation (deterministic, no LLM required)
- Mechanism taxonomy mapping with scoring trace
- Predicted next signals with measurable metrics
- Falsifiers for each hypothesis
- Confidence scoring with full breakdown
- Title sanitization (no company names, no filler words)
- Observable signal validation with anti-vagueness filter
"""

import json
import hashlib
import re
from typing import List, Dict, Any, Optional, Tuple, Set, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from collections import Counter

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_TAXONOMY_PATH = Path(__file__).parent.parent / "config" / "mechanism_taxonomy.json"
DEFAULT_ENTITY_REGISTRY_PATH = Path(__file__).parent.parent / "config" / "entity_registry.json"
DEFAULT_OBSERVABLE_METRICS_PATH = Path(__file__).parent.parent / "config" / "observable_metrics.json"

# Confidence formula weights
CONFIDENCE_WEIGHTS = {
    'meta_confidence': 0.55,
    'category_diversity': 0.15,
    'persistence': 0.10,
    'independence': 0.10,
    'specificity': 0.10,
}

# Confidence caps
REVIEW_REQUIRED_CAP = 0.55
MEDIA_ONLY_CAP = 0.50

# Penalties
PENALTY_GENERIC_PREDICTIONS = 0.10
PENALTY_WEAK_MECHANISM = 0.10

# Minimum keyword hits for confident mechanism detection
MIN_MECHANISM_KEYWORDS = 3

# =============================================================================
# EVIDENCE SOURCE CLASSIFICATION (v2.1)
# =============================================================================

# Primary sources: allowed for scoring
PRIMARY_EVIDENCE_SOURCES = frozenset([
    'concept_name',
    'meta_insight',
    'signal_name',
    'signal_titles',
    'bucket_tags',
    'entity_tags',
    'description',
])

# Secondary sources: derived only, not for scoring by default
SECONDARY_EVIDENCE_SOURCES = frozenset([
    'naming_reason',
    'mechanism_bucket',
    'mechanism_field',
    'structural_analysis',
    'no_mechanism_match',
])

# =============================================================================
# OBSERVABLE GATE TERMS (v2.0)
# =============================================================================

# Measurable terms that predictions must include
MEASURABLE_TERMS = frozenset([
    "revenue", "downloads", "stars", "contracts", "arr", "filings",
    "volume", "users", "seat", "capex", "funding", "traffic",
    "metric", "filing", "repo", "release", "price",
    "adoption", "integration", "regulation", "benchmark", "announcement",
    "contract", "patent", "publication", "download", "star", "fork",
    "earnings", "launch", "deprecation",
    "certification", "compliance", "lawsuit", "settlement", "hire",
    "layoff", "acquisition", "partnership", "api", "sdk", "model",
    "valuation", "round", "deal", "merger", "ipo", "license",
])

# Direction terms that indicate change
DIRECTION_TERMS = frozenset([
    "increase", "rise", "accelerate", "grow", "decline", "drop",
    "slow", "fall", "surge", "spike", "jump", "plunge", "climb",
    "shrink", "expand", "reduce", "boost", "cut", "raise", "lower",
    "improve", "worsen", "strengthen", "weaken", "gain", "lose",
])

# Filler words to remove from titles (v2.0)
TITLE_FILLER_WORDS = frozenset([
    "trend", "signal", "strengthening", "weakening", "pattern",
    "dynamics", "movement", "development", "activity", "behavior",
    "the", "a", "an", "is", "are", "being", "was", "were",
    "and", "or", "but", "yet", "so", "for", "with", "from",
])

# Legacy observable terms (kept for backward compatibility)
OBSERVABLE_TERMS = MEASURABLE_TERMS


# =============================================================================
# CONFIG LOADERS
# =============================================================================

_TAXONOMY_CACHE = None
_ENTITY_NAMES_CACHE = None
_OBSERVABLE_METRICS_CACHE = None


def load_mechanism_taxonomy(config_path: Path = None) -> Dict[str, Any]:
    """Load mechanism taxonomy config with caching."""
    global _TAXONOMY_CACHE
    
    if _TAXONOMY_CACHE is not None:
        return _TAXONOMY_CACHE
    
    if config_path is None:
        config_path = DEFAULT_TAXONOMY_PATH
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            _TAXONOMY_CACHE = json.load(f)
            return _TAXONOMY_CACHE
    except Exception as e:
        logger.warning(f"Failed to load mechanism_taxonomy.json: {e}")
        return {'mechanisms': {}}


def load_entity_names(config_path: Path = None) -> Set[str]:
    """Load all entity names and aliases for sanitization."""
    global _ENTITY_NAMES_CACHE
    
    if _ENTITY_NAMES_CACHE is not None:
        return _ENTITY_NAMES_CACHE
    
    if config_path is None:
        config_path = DEFAULT_ENTITY_REGISTRY_PATH
    
    names = set()
    
    # Always include common company names
    common_companies = {
        'openai', 'anthropic', 'google', 'meta', 'microsoft', 'apple', 'nvidia',
        'amazon', 'aws', 'deepmind', 'cohere', 'mistral', 'stability', 'midjourney',
        'huggingface', 'inflection', 'character', 'runway', 'adobe', 'salesforce',
        'ibm', 'intel', 'amd', 'qualcomm', 'arm', 'tesla', 'baidu', 'alibaba',
        'tencent', 'bytedance', 'samsung', 'xai', 'perplexity', 'deepseek',
    }
    names.update(common_companies)
    
    # Common model names
    model_names = {
        'gpt', 'gpt-4', 'gpt-5', 'claude', 'gemini', 'llama', 'mistral', 'mixtral',
        'palm', 'bard', 'copilot', 'chatgpt', 'dall-e', 'dalle', 'stable diffusion',
        'midjourney', 'sora', 'opus', 'sonnet', 'haiku', 'o1', 'o3', 'r1',
    }
    names.update(model_names)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            registry = json.load(f)
            
        for key, entity in registry.items():
            if key.startswith('_'):
                continue
            names.add(key.lower())
            if 'canonical_name' in entity:
                names.add(entity['canonical_name'].lower())
            if 'aliases' in entity:
                for alias in entity['aliases']:
                    names.add(alias.lower())
            if 'products' in entity:
                for product in entity['products']:
                    names.add(product.lower())
    except Exception as e:
        logger.debug(f"Could not load entity_registry.json: {e}")
    
    _ENTITY_NAMES_CACHE = names
    return names


def load_observable_metrics(config_path: Path = None) -> Dict[str, Any]:
    """Load observable metrics vocabulary with caching (v2.1)."""
    global _OBSERVABLE_METRICS_CACHE
    
    if _OBSERVABLE_METRICS_CACHE is not None:
        return _OBSERVABLE_METRICS_CACHE
    
    if config_path is None:
        config_path = DEFAULT_OBSERVABLE_METRICS_PATH
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            _OBSERVABLE_METRICS_CACHE = json.load(f)
            return _OBSERVABLE_METRICS_CACHE
    except Exception as e:
        logger.warning(f"Failed to load observable_metrics.json: {e}")
        return {'categories': {}, 'source_query_templates': {}, 'fallback_metric': 'custom_metric'}


def get_canonical_metric(raw_metric: str, category: str = None) -> Tuple[str, str]:
    """
    Map a raw metric to canonical form (v2.1).
    
    Args:
        raw_metric: Free-form metric string
        category: Optional category hint (financial, technical, etc.)
    
    Returns:
        (canonical_metric, category) tuple
    """
    metrics_config = load_observable_metrics()
    raw_lower = raw_metric.lower().strip()
    
    # Search all categories for match
    categories_to_search = [category] if category else list(metrics_config.get('categories', {}).keys())
    
    for cat in categories_to_search:
        cat_config = metrics_config.get('categories', {}).get(cat, {})
        for canonical, info in cat_config.get('metrics', {}).items():
            # Direct match
            if raw_lower == canonical:
                return canonical, cat
            # Alias match
            if raw_lower in [a.lower() for a in info.get('aliases', [])]:
                return canonical, cat
            # Partial match
            if raw_lower in canonical or canonical in raw_lower:
                return canonical, cat
    
    # Fallback
    return metrics_config.get('fallback_metric', 'custom_metric'), category or 'unknown'


def get_metric_defaults(canonical_metric: str, category: str) -> Dict[str, Any]:
    """
    Get default source, aggregation, and window for a canonical metric (v2.1).
    
    Returns:
        Dict with default_source, default_aggregation, default_window_days
    """
    metrics_config = load_observable_metrics()
    cat_config = metrics_config.get('categories', {}).get(category, {})
    metric_info = cat_config.get('metrics', {}).get(canonical_metric, {})
    
    return {
        'default_source': metric_info.get('default_source', 'unknown'),
        'default_aggregation': metric_info.get('default_aggregation', 'count'),
        'default_window_days': metric_info.get('default_window_days', 14),
    }


def get_source_query_template(source: str) -> Dict[str, Any]:
    """Get query template for a source (v2.1)."""
    metrics_config = load_observable_metrics()
    return metrics_config.get('source_query_templates', {}).get(source, {
        'query_template': 'search:{keyword}',
        'aggregations': ['count'],
    })


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ConfidenceInputs:
    """
    Explicit confidence input tracking for transparency (v2.1).
    """
    meta_confidence_raw: float           # Original meta_signal.confidence
    meta_to_hypothesis_scaling: float    # Multiplier used (CONFIDENCE_WEIGHTS['meta_confidence'])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'meta_confidence_raw': round(self.meta_confidence_raw, 4),
            'meta_to_hypothesis_scaling': round(self.meta_to_hypothesis_scaling, 4),
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ConfidenceInputs':
        return cls(
            meta_confidence_raw=d.get('meta_confidence_raw', 0.0),
            meta_to_hypothesis_scaling=d.get('meta_to_hypothesis_scaling', 0.55),
        )


@dataclass
class ConfidenceDebug:
    """
    Detailed confidence debug info (v2.1).
    """
    base_scaled: float                   # base_from_meta_confidence (after scaling)
    base_raw: float                      # meta_confidence before scaling
    scaling_factor: float                # The multiplier applied
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'base_scaled': round(self.base_scaled, 4),
            'base_raw': round(self.base_raw, 4),
            'scaling_factor': round(self.scaling_factor, 4),
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ConfidenceDebug':
        return cls(
            base_scaled=d.get('base_scaled', 0.0),
            base_raw=d.get('base_raw', 0.0),
            scaling_factor=d.get('scaling_factor', 0.55),
        )


@dataclass
class ObservableQuery:
    """
    Machine-testable observable for a prediction (v2.1).
    
    Describes how the system WOULD test this prediction later.
    """
    source: str                          # e.g., 'sec', 'github', 'linkedin'
    query: str                           # Query template filled in
    aggregation: str                     # e.g., 'count', 'sum', 'delta'
    window_days: int                     # Observation window
    expected_direction: str              # 'up', 'down', 'increase', 'decrease'
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'source': self.source,
            'query': self.query,
            'aggregation': self.aggregation,
            'window_days': self.window_days,
            'expected_direction': self.expected_direction,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ObservableQuery':
        return cls(
            source=d.get('source', 'unknown'),
            query=d.get('query', ''),
            aggregation=d.get('aggregation', 'count'),
            window_days=d.get('window_days', 14),
            expected_direction=d.get('expected_direction', 'up'),
        )


@dataclass
class WatchItem:
    """
    Structured watchlist item with priority scoring (v2.1).
    """
    description: str
    watch_priority_score: float
    watch_priority_reason: List[str]
    timeframe_bucket: str                # '7d', '14d', '30d', '60d'
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'description': self.description,
            'watch_priority_score': round(self.watch_priority_score, 4),
            'watch_priority_reason': self.watch_priority_reason,
            'timeframe_bucket': self.timeframe_bucket,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'WatchItem':
        return cls(
            description=d.get('description', ''),
            watch_priority_score=d.get('watch_priority_score', 0.0),
            watch_priority_reason=d.get('watch_priority_reason', []),
            timeframe_bucket=d.get('timeframe_bucket', '14d'),
        )


@dataclass
class FalsifierObservable:
    """
    Observable structure for a falsifier (v2.1).
    """
    metric: str                          # Canonical metric to watch
    direction: str                       # 'down', 'up' - what would falsify
    window_days: int                     # How long to wait
    available: bool                      # Can we actually measure this?
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'metric': self.metric,
            'direction': self.direction,
            'window_days': self.window_days,
            'available': self.available,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'FalsifierObservable':
        return cls(
            metric=d.get('metric', ''),
            direction=d.get('direction', ''),
            window_days=d.get('window_days', 30),
            available=d.get('available', False),
        )


@dataclass
class MeasurableFalsifier:
    """
    Falsifier with optional observable (v2.1).
    """
    text: str                            # Original falsifier text
    observable: Optional[FalsifierObservable] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {'text': self.text}
        if self.observable:
            result['observable'] = self.observable.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'MeasurableFalsifier':
        observable = None
        if 'observable' in d and d['observable']:
            observable = FalsifierObservable.from_dict(d['observable'])
        return cls(
            text=d.get('text', ''),
            observable=observable,
        )


@dataclass
class MechanismTrace:
    """
    Full explainability trace for mechanism detection (v2.0 + v2.1).
    
    v2.1 adds: evidence_sources_primary, evidence_sources_secondary
    """
    candidate_scores: Dict[str, int]           # mechanism_id -> keyword_hits
    matched_terms: List[str]                   # All matched keywords
    evidence_sources: List[str]                # Where matches came from (v2.0 - kept for compat)
    selection_reason: str                      # Why this mechanism was chosen
    evidence_sources_primary: List[str] = field(default_factory=list)    # v2.1
    evidence_sources_secondary: List[str] = field(default_factory=list)  # v2.1
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'candidate_scores': self.candidate_scores,
            'matched_terms': self.matched_terms,
            'evidence_sources': self.evidence_sources,
            'selection_reason': self.selection_reason,
        }
        # v2.1 fields
        if self.evidence_sources_primary:
            result['evidence_sources_primary'] = self.evidence_sources_primary
        if self.evidence_sources_secondary:
            result['evidence_sources_secondary'] = self.evidence_sources_secondary
        return result
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'MechanismTrace':
        return cls(
            candidate_scores=d.get('candidate_scores', {}),
            matched_terms=d.get('matched_terms', []),
            evidence_sources=d.get('evidence_sources', []),
            selection_reason=d.get('selection_reason', ''),
            evidence_sources_primary=d.get('evidence_sources_primary', []),
            evidence_sources_secondary=d.get('evidence_sources_secondary', []),
        )


@dataclass
class PredictedSignal:
    """
    A predicted future signal to watch for (v2.0 + v2.1 enhanced).
    
    v2.0 fields:
    - metric: Measurable variable to track
    - direction: Expected change direction
    - speculative: Whether this is a weak-evidence prediction
    
    v2.1 fields:
    - canonical_metric: Controlled vocabulary metric
    - observable_query: Machine-testable observable
    """
    category: str                                # technical/social/financial/predictive/media
    description: str                             # Concrete, observable description
    example_sources: List[str]                   # e.g., ['github', 'arxiv']
    expected_timeframe_days: int                 # 7/14/30/etc
    metric: str = ""                             # Measurable variable (v2.0)
    direction: str = ""                          # up/down/increase/decline (v2.0)
    speculative: bool = False                    # Weak evidence marker (v2.0)
    canonical_metric: str = ""                   # Controlled vocabulary metric (v2.1)
    observable_query: Optional[ObservableQuery] = None  # v2.1
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'category': self.category,
            'description': self.description,
            'example_sources': self.example_sources,
            'expected_timeframe_days': self.expected_timeframe_days,
        }
        # v2.0 fields (only include if set to maintain backward compatibility)
        if self.metric:
            result['metric'] = self.metric
        if self.direction:
            result['direction'] = self.direction
        if self.speculative:
            result['speculative'] = self.speculative
        # v2.1 fields
        if self.canonical_metric:
            result['canonical_metric'] = self.canonical_metric
        if self.observable_query:
            result['observable_query'] = self.observable_query.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'PredictedSignal':
        observable_query = None
        if 'observable_query' in d and d['observable_query']:
            observable_query = ObservableQuery.from_dict(d['observable_query'])
        return cls(
            category=d['category'],
            description=d['description'],
            example_sources=d.get('example_sources', []),
            expected_timeframe_days=d.get('expected_timeframe_days', 14),
            metric=d.get('metric', ''),
            direction=d.get('direction', ''),
            speculative=d.get('speculative', False),
            canonical_metric=d.get('canonical_metric', ''),
            observable_query=observable_query,
        )


@dataclass
class EvidenceUsed:
    """Evidence supporting a hypothesis."""
    supporting_signals: List[str]    # signal_ids
    source_categories: List[str]     # e.g., ['technical', 'financial']
    key_entities: List[str]          # Sanitized entity list
    key_quotes: List[str]            # Up to 2 short excerpts (<= 20 words each)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'supporting_signals': self.supporting_signals,
            'source_categories': self.source_categories,
            'key_entities': self.key_entities,
            'key_quotes': self.key_quotes,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'EvidenceUsed':
        return cls(
            supporting_signals=d.get('supporting_signals', []),
            source_categories=d.get('source_categories', []),
            key_entities=d.get('key_entities', []),
            key_quotes=d.get('key_quotes', []),
        )


@dataclass
class ConfidenceBreakdown:
    """Detailed confidence score breakdown."""
    base_from_meta_confidence: float
    diversity_bonus: float
    persistence_bonus: float
    independence_bonus: float
    specificity_bonus: float
    penalties_applied: List[str]
    final: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'base_from_meta_confidence': round(self.base_from_meta_confidence, 3),
            'diversity_bonus': round(self.diversity_bonus, 3),
            'persistence_bonus': round(self.persistence_bonus, 3),
            'independence_bonus': round(self.independence_bonus, 3),
            'specificity_bonus': round(self.specificity_bonus, 3),
            'penalties_applied': self.penalties_applied,
            'final': round(self.final, 3),
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ConfidenceBreakdown':
        return cls(
            base_from_meta_confidence=d.get('base_from_meta_confidence', 0.0),
            diversity_bonus=d.get('diversity_bonus', 0.0),
            persistence_bonus=d.get('persistence_bonus', 0.0),
            independence_bonus=d.get('independence_bonus', 0.0),
            specificity_bonus=d.get('specificity_bonus', 0.0),
            penalties_applied=d.get('penalties_applied', []),
            final=d.get('final', 0.0),
        )


@dataclass
class DebugInfo:
    """Debug information for hypothesis generation."""
    rules_fired: List[str]
    scoring_terms: Dict[str, float]
    mechanism_keyword_hits: int
    mechanism_keywords_matched: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'rules_fired': self.rules_fired,
            'scoring_terms': {k: round(v, 3) if isinstance(v, float) else v for k, v in self.scoring_terms.items()},
            'mechanism_keyword_hits': self.mechanism_keyword_hits,
            'mechanism_keywords_matched': self.mechanism_keywords_matched,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'DebugInfo':
        return cls(
            rules_fired=d.get('rules_fired', []),
            scoring_terms=d.get('scoring_terms', {}),
            mechanism_keyword_hits=d.get('mechanism_keyword_hits', 0),
            mechanism_keywords_matched=d.get('mechanism_keywords_matched', []),
        )


@dataclass
class Hypothesis:
    """
    A causal hypothesis derived from a meta-signal (v2.0 + v2.1 enhanced).
    
    v2.0 adds:
    - mechanism_trace: Full explainability for mechanism selection
    
    v2.1 adds:
    - confidence_inputs: Explicit tracking of confidence inputs
    - confidence_debug: Detailed debug for confidence calculation
    - falsifiers_v2: Structured falsifiers with observables
    """
    hypothesis_id: str                                        # Stable hash
    title: str                                                # <= 8 words, no company names
    mechanism: str                                            # From controlled taxonomy
    claim: str                                                # 1-2 sentences, causal
    why_now: str                                              # 1 sentence using time-series facts
    evidence_used: EvidenceUsed
    predicted_next_signals: List[PredictedSignal]
    falsifiers: List[str]                                     # 1-3 items (v2.0 compat)
    confidence: float                                         # 0-1
    confidence_breakdown: ConfidenceBreakdown
    review_required: bool
    debug: DebugInfo
    mechanism_trace: Optional[MechanismTrace] = None          # v2.0
    confidence_inputs: Optional[ConfidenceInputs] = None      # v2.1
    confidence_debug: Optional[ConfidenceDebug] = None        # v2.1
    falsifiers_v2: List[MeasurableFalsifier] = field(default_factory=list)  # v2.1
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'hypothesis_id': self.hypothesis_id,
            'title': self.title,
            'mechanism': self.mechanism,
            'claim': self.claim,
            'why_now': self.why_now,
            'evidence_used': self.evidence_used.to_dict(),
            'predicted_next_signals': [p.to_dict() for p in self.predicted_next_signals],
            'falsifiers': self.falsifiers,
            'confidence': round(self.confidence, 3),
            'confidence_breakdown': self.confidence_breakdown.to_dict(),
            'review_required': self.review_required,
            'debug': self.debug.to_dict(),
        }
        # v2.0: Add mechanism trace if present
        if self.mechanism_trace:
            result['mechanism_trace'] = self.mechanism_trace.to_dict()
        # v2.1 fields
        if self.confidence_inputs:
            result['confidence_inputs'] = self.confidence_inputs.to_dict()
        if self.confidence_debug:
            result['confidence_debug'] = self.confidence_debug.to_dict()
        if self.falsifiers_v2:
            result['falsifiers_v2'] = [f.to_dict() for f in self.falsifiers_v2]
        return result
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Hypothesis':
        mechanism_trace = None
        if 'mechanism_trace' in d:
            mechanism_trace = MechanismTrace.from_dict(d['mechanism_trace'])
        
        confidence_inputs = None
        if 'confidence_inputs' in d:
            confidence_inputs = ConfidenceInputs.from_dict(d['confidence_inputs'])
        
        confidence_debug = None
        if 'confidence_debug' in d:
            confidence_debug = ConfidenceDebug.from_dict(d['confidence_debug'])
        
        falsifiers_v2 = []
        if 'falsifiers_v2' in d:
            falsifiers_v2 = [MeasurableFalsifier.from_dict(f) for f in d['falsifiers_v2']]
        
        return cls(
            hypothesis_id=d['hypothesis_id'],
            title=d['title'],
            mechanism=d['mechanism'],
            claim=d['claim'],
            why_now=d.get('why_now', ''),
            evidence_used=EvidenceUsed.from_dict(d.get('evidence_used', {})),
            predicted_next_signals=[PredictedSignal.from_dict(p) for p in d.get('predicted_next_signals', [])],
            falsifiers=d.get('falsifiers', []),
            confidence=d.get('confidence', 0.0),
            confidence_breakdown=ConfidenceBreakdown.from_dict(d.get('confidence_breakdown', {})),
            review_required=d.get('review_required', False),
            debug=DebugInfo.from_dict(d.get('debug', {})),
            mechanism_trace=mechanism_trace,
            confidence_inputs=confidence_inputs,
            confidence_debug=confidence_debug,
            falsifiers_v2=falsifiers_v2,
        )


@dataclass
class MetaHypothesisBundle:
    """
    A bundle of hypotheses for a single meta-signal (v2.0 + v2.1 enhanced).
    
    v2.0 adds:
    - what_to_watch_next: Top predictions across all hypotheses
    
    v2.1 adds:
    - watch_items: Structured watchlist with priority scoring
    """
    meta_id: str
    concept_slug: str
    concept_name: str
    maturity_stage: str
    hypotheses: List[Hypothesis]
    selected_hypothesis_id: str      # Top ranked
    bundle_confidence: float         # 0-1
    generated_at: str
    version: str = "2.1"
    what_to_watch_next: List[str] = field(default_factory=list)  # v2.0 (kept for compat)
    watch_items: List[WatchItem] = field(default_factory=list)   # v2.1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'meta_id': self.meta_id,
            'concept_slug': self.concept_slug,
            'concept_name': self.concept_name,
            'maturity_stage': self.maturity_stage,
            'hypotheses': [h.to_dict() for h in self.hypotheses],
            'selected_hypothesis_id': self.selected_hypothesis_id,
            'bundle_confidence': round(self.bundle_confidence, 3),
            'generated_at': self.generated_at,
            'version': self.version,
            'what_to_watch_next': self.what_to_watch_next,  # v2.0
            'watch_items': [w.to_dict() for w in self.watch_items],  # v2.1
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'MetaHypothesisBundle':
        watch_items = []
        if 'watch_items' in d:
            watch_items = [WatchItem.from_dict(w) for w in d['watch_items']]
        
        return cls(
            meta_id=d['meta_id'],
            concept_slug=d.get('concept_slug', ''),
            concept_name=d['concept_name'],
            maturity_stage=d.get('maturity_stage', 'weak'),
            hypotheses=[Hypothesis.from_dict(h) for h in d.get('hypotheses', [])],
            selected_hypothesis_id=d.get('selected_hypothesis_id', ''),
            bundle_confidence=d.get('bundle_confidence', 0.0),
            generated_at=d.get('generated_at', ''),
            version=d.get('version', '2.1'),
            what_to_watch_next=d.get('what_to_watch_next', []),
            watch_items=watch_items,
        )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def sanitize_title(text: str, entity_names: Set[str] = None) -> str:
    """
    Remove company/model names and filler words from a title (v2.0 enhanced).
    
    Rules:
    - 6-8 words maximum
    - Remove filler words: "trend", "signal", "strengthening"
    - Prefer mechanism-first naming
    
    Args:
        text: Input title text
        entity_names: Set of names to filter (loads default if None)
    
    Returns:
        Sanitized title without company/model names or filler
    """
    if entity_names is None:
        entity_names = load_entity_names()
    
    words = text.split()
    sanitized = []
    
    for word in words:
        word_lower = word.lower()
        word_clean = re.sub(r'[^a-z0-9]', '', word_lower)
        
        # Skip filler words (v2.0)
        if word_clean in TITLE_FILLER_WORDS:
            continue
        
        # Check if word matches any entity name
        is_entity = (
            word_lower in entity_names or
            word_clean in entity_names
        )
        
        # Check if word starts with entity name
        if not is_entity:
            for name in entity_names:
                if len(name) > 2 and (word_lower.startswith(name) or word_clean.startswith(name)):
                    is_entity = True
                    break
        
        if not is_entity:
            sanitized.append(word)
    
    result = ' '.join(sanitized).strip()
    
    # Truncate to 6-8 words (v2.0)
    result = truncate_to_words(result, 8)
    
    # Ensure we have at least something
    if not result or len(result.split()) < 2:
        result = "Market Dynamics Shifting"
    
    return result


def truncate_to_words(text: str, max_words: int) -> str:
    """Truncate text to max_words."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return ' '.join(words[:max_words])


def is_observable(description: str) -> bool:
    """Check if a prediction description mentions observable terms."""
    desc_lower = description.lower()
    return any(term in desc_lower for term in OBSERVABLE_TERMS)


def passes_observable_gate(description: str) -> bool:
    """
    Anti-vagueness filter (v2.0).
    
    A prediction is valid ONLY if:
    - Contains a measurable noun AND
    - Contains a directional word
    
    Returns:
        True if prediction passes the gate
    """
    desc_lower = description.lower()
    
    has_measurable = any(term in desc_lower for term in MEASURABLE_TERMS)
    has_direction = any(term in desc_lower for term in DIRECTION_TERMS)
    
    return has_measurable and has_direction


def extract_metric_and_direction(description: str) -> Tuple[str, str]:
    """
    Extract metric and direction from a prediction description (v2.0).
    
    Returns:
        (metric, direction) tuple
    """
    desc_lower = description.lower()
    
    metric = ""
    direction = ""
    
    # Find first measurable term
    for term in MEASURABLE_TERMS:
        if term in desc_lower:
            metric = term
            break
    
    # Find first direction term
    for term in DIRECTION_TERMS:
        if term in desc_lower:
            direction = term
            break
    
    return metric, direction


def normalize_direction(direction: str) -> str:
    """
    Normalize direction to standard values (v2.1).
    
    Returns:
        'up', 'down', 'increase', or 'decrease'
    """
    direction_lower = direction.lower()
    
    up_terms = {'increase', 'rise', 'accelerate', 'grow', 'surge', 'spike', 
                'jump', 'climb', 'expand', 'boost', 'raise', 'improve', 
                'strengthen', 'gain', 'up'}
    down_terms = {'decline', 'drop', 'slow', 'fall', 'plunge', 'shrink', 
                  'reduce', 'cut', 'lower', 'worsen', 'weaken', 'lose', 
                  'decrease', 'down'}
    
    if direction_lower in up_terms:
        return 'up'
    elif direction_lower in down_terms:
        return 'down'
    elif 'increas' in direction_lower:
        return 'increase'
    elif 'decreas' in direction_lower:
        return 'decrease'
    else:
        return 'up'  # Default


def get_timeframe_bucket(days: int) -> str:
    """Convert days to timeframe bucket (v2.1)."""
    if days <= 7:
        return '7d'
    elif days <= 14:
        return '14d'
    elif days <= 30:
        return '30d'
    else:
        return '60d'


def build_observable_query(
    category: str,
    metric: str,
    direction: str,
    sources: List[str],
    timeframe_days: int,
) -> ObservableQuery:
    """
    Build a machine-testable observable query (v2.1).
    
    Args:
        category: Prediction category
        metric: Raw or canonical metric
        direction: Expected direction
        sources: Example sources list
        timeframe_days: Expected timeframe
    
    Returns:
        ObservableQuery object
    """
    # Get canonical metric
    canonical, _ = get_canonical_metric(metric, category)
    
    # Get defaults for this metric
    defaults = get_metric_defaults(canonical, category)
    
    # Determine source (prefer from sources list, fallback to defaults)
    source = sources[0] if sources else defaults.get('default_source', 'unknown')
    
    # Get query template
    template_info = get_source_query_template(source)
    query_template = template_info.get('query_template', 'search:{keyword}')
    
    # Fill in template
    query = query_template.replace('{keyword}', canonical).replace('{metric}', canonical)
    
    # Determine aggregation
    aggregation = defaults.get('default_aggregation', 'count')
    
    # Normalize direction
    expected_direction = normalize_direction(direction)
    
    return ObservableQuery(
        source=source,
        query=query,
        aggregation=aggregation,
        window_days=timeframe_days,
        expected_direction=expected_direction,
    )


def generate_hypothesis_id(concept_slug: str, mechanism: str, claim: str) -> str:
    """Generate stable hypothesis ID from key components."""
    # Normalize claim for stability
    normalized_claim = re.sub(r'\s+', ' ', claim.lower().strip())
    
    source = f"{concept_slug}|{mechanism}|{normalized_claim}"
    return hashlib.sha256(source.encode()).hexdigest()[:16]


def extract_key_quotes(meta: Dict[str, Any], max_quotes: int = 2, max_words: int = 20) -> List[str]:
    """Extract key quotes from meta-signal insights."""
    quotes = []
    
    # Try to get quotes from supporting insights
    for insight in meta.get('supporting_insights', []):
        insight_text = insight.get('insight_text', '')
        if insight_text and len(insight_text.split()) >= 5:
            quotes.append(truncate_to_words(insight_text, max_words))
            if len(quotes) >= max_quotes:
                break
    
    # If not enough, try description
    if len(quotes) < max_quotes:
        description = meta.get('description', '')
        if description:
            quotes.append(truncate_to_words(description, max_words))
    
    return quotes[:max_quotes]


def classify_evidence_strength(meta: Dict[str, Any]) -> str:
    """
    Classify meta-signal evidence strength (v2.0).
    
    Returns:
        'weak', 'moderate', or 'strong'
    """
    confidence = meta.get('concept_confidence', 0.5)
    category_diversity = meta.get('category_diversity', {})
    category_count = category_diversity.get('category_count', 1) if isinstance(category_diversity, dict) else 1
    
    # Weak evidence conditions
    if confidence < 0.55 or category_count == 1:
        return 'weak'
    
    # Strong evidence conditions
    if confidence >= 0.75 and category_count >= 2:
        return 'strong'
    
    # Otherwise moderate
    return 'moderate'


def get_prediction_limits(evidence_strength: str) -> Tuple[int, int, int]:
    """
    Get prediction limits based on evidence strength (v2.0).
    
    Returns:
        (min_predictions, max_predictions, max_timeframe_days)
    """
    if evidence_strength == 'weak':
        return (1, 2, 14)  # max 2 predictions, 7-14 day timeframe
    elif evidence_strength == 'strong':
        return (4, 6, 60)  # 4-6 predictions, up to 60 days
    else:  # moderate
        return (3, 4, 30)  # 3-4 predictions, 14-30 days


def classify_evidence_sources(sources: List[str]) -> Tuple[List[str], List[str]]:
    """
    Split evidence sources into primary and secondary (v2.1).
    
    Args:
        sources: List of evidence source names
    
    Returns:
        (primary_sources, secondary_sources) tuple
    """
    primary = []
    secondary = []
    
    for source in sources:
        if source in PRIMARY_EVIDENCE_SOURCES:
            primary.append(source)
        elif source in SECONDARY_EVIDENCE_SOURCES:
            secondary.append(source)
        else:
            # Unknown sources default to secondary
            secondary.append(source)
    
    return primary, secondary


# =============================================================================
# MECHANISM DETECTION
# =============================================================================

def detect_mechanisms(
    meta: Dict[str, Any], 
    taxonomy: Dict[str, Any],
    allow_secondary_evidence: bool = False,
) -> List[Tuple[str, int, List[str], List[str], List[str]]]:
    """
    Detect candidate mechanisms from meta-signal (v2.0 + v2.1 enhanced).
    
    Now tracks evidence sources and classifies them as primary/secondary.
    
    Args:
        meta: Meta-signal dict
        taxonomy: Mechanism taxonomy
        allow_secondary_evidence: If True, count secondary sources in scoring
    
    Returns:
        List of (mechanism_id, keyword_hits, matched_keywords, primary_sources, secondary_sources) 
        sorted by hits descending
    """
    mechanisms = taxonomy.get('mechanisms', {})
    
    # Build text corpus from meta-signal with source tracking
    text_sources = []  # List of (text, source_name)
    
    # From naming_reason (secondary)
    naming_reason = meta.get('naming_reason', {})
    if naming_reason:
        for term in naming_reason.get('mechanism_terms', []):
            text_sources.append((term, 'naming_reason'))
        if naming_reason.get('mechanism_bucket'):
            text_sources.append((naming_reason['mechanism_bucket'], 'mechanism_bucket'))
    
    # From mechanism field (secondary)
    if meta.get('mechanism'):
        text_sources.append((meta['mechanism'], 'mechanism_field'))
    
    # From concept_name (primary)
    text_sources.append((meta.get('concept_name', ''), 'concept_name'))
    
    # From description (primary)
    text_sources.append((meta.get('description', ''), 'description'))
    
    # From supporting insights (primary)
    for insight in meta.get('supporting_insights', []):
        text_sources.append((insight.get('insight_text', ''), 'meta_insight'))
        text_sources.append((insight.get('signal_name', ''), 'signal_name'))
        for bucket in insight.get('buckets', []):
            text_sources.append((bucket, 'bucket_tags'))
        for entity in insight.get('entities', []):
            text_sources.append((entity, 'entity_tags'))
    
    # Combine and lowercase
    corpus = ' '.join([t[0] for t in text_sources]).lower()
    corpus = re.sub(r'[_-]', ' ', corpus)
    
    # Score each mechanism with source tracking
    results = []
    
    for mech_id, mech_info in mechanisms.items():
        keywords = mech_info.get('keywords', [])
        matched = []
        all_sources = set()
        
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in corpus:
                matched.append(kw)
                # Track which sources contained this keyword
                for text, source in text_sources:
                    if kw_lower in text.lower():
                        all_sources.add(source)
        
        if matched:
            # Classify sources
            primary, secondary = classify_evidence_sources(list(all_sources))
            
            # Calculate hits based on allow_secondary_evidence
            if allow_secondary_evidence:
                hits = len(matched)
            else:
                # Only count hits from primary sources
                primary_corpus = ' '.join([t[0] for t, s in zip([ts[0] for ts in text_sources], [ts[1] for ts in text_sources]) if s in PRIMARY_EVIDENCE_SOURCES]).lower()
                primary_hits = sum(1 for kw in matched if kw.lower() in primary_corpus)
                hits = primary_hits if primary_hits > 0 else len(matched)  # Fallback to all if no primary
            
            results.append((mech_id, hits, matched, primary, secondary))
    
    # Sort by hits descending
    results.sort(key=lambda x: x[1], reverse=True)
    
    return results


def build_mechanism_trace(
    detections: List[Tuple[str, int, List[str], List[str], List[str]]],
    selected_mechanism: str,
    selection_reason: str,
) -> MechanismTrace:
    """
    Build full mechanism trace for explainability (v2.0 + v2.1).
    
    Now includes primary/secondary source separation.
    
    Args:
        detections: List of (mechanism_id, hits, keywords, primary_sources, secondary_sources)
        selected_mechanism: The mechanism that was selected
        selection_reason: Why this mechanism was chosen
    
    Returns:
        MechanismTrace object
    """
    candidate_scores = {}
    all_matched_terms = []
    all_sources = set()
    primary_sources = []
    secondary_sources = []
    
    for mech_id, hits, keywords, primary, secondary in detections:
        candidate_scores[mech_id] = hits
        if mech_id == selected_mechanism:
            all_matched_terms = keywords
            all_sources = set(primary + secondary)
            primary_sources = primary
            secondary_sources = secondary
    
    return MechanismTrace(
        candidate_scores=candidate_scores,
        matched_terms=all_matched_terms,
        evidence_sources=list(all_sources),  # v2.0 compat
        selection_reason=selection_reason,
        evidence_sources_primary=primary_sources,      # v2.1
        evidence_sources_secondary=secondary_sources,  # v2.1
    )


def get_primary_mechanism(
    detections: List[Tuple[str, int, List[str], List[str], List[str]]]
) -> Tuple[str, int, List[str], List[str], List[str]]:
    """Get the primary mechanism from detections."""
    if detections:
        return detections[0]
    return ('null_hypothesis', 0, [], [], [])


def get_alternative_mechanism(
    detections: List[Tuple[str, int, List[str], List[str], List[str]]], 
    primary: str
) -> Optional[Tuple[str, int, List[str], List[str], List[str]]]:
    """Get an alternative mechanism different from primary."""
    for mech_id, hits, matched, primary_src, secondary_src in detections:
        if mech_id != primary and hits >= 2:
            return (mech_id, hits, matched, primary_src, secondary_src)
    return None


# =============================================================================
# HYPOTHESIS GENERATION
# =============================================================================

def build_why_now(meta: Dict[str, Any]) -> str:
    """Build a why_now statement from meta-signal time-series data."""
    parts = []
    
    persistence = meta.get('persistence_days', 1)
    if persistence >= 3:
        parts.append(f"persistent for {persistence} days")
    
    acceleration = meta.get('acceleration', 0)
    if acceleration > 0.5:
        parts.append("accelerating")
    elif acceleration < -0.3:
        parts.append("decelerating")
    
    maturity = meta.get('maturity_stage', '')
    if maturity == 'trending':
        parts.append("now trending")
    elif maturity == 'emerging':
        parts.append("emerging pattern")
    elif maturity == 'established':
        parts.append("established trend")
    
    independence = meta.get('independence_score', 0)
    if independence >= 0.75:
        parts.append("from independent sources")
    
    if not parts:
        return "Recent signal activity indicates developing pattern."
    
    return f"Signal is {', '.join(parts)}."


def build_claim(mechanism_id: str, mechanism_info: Dict[str, Any], meta: Dict[str, Any]) -> str:
    """Build a causal claim statement."""
    display_name = mechanism_info.get('display_name', mechanism_id.replace('_', ' ').title())
    concept = meta.get('concept_name', 'AI market')
    
    # Build causal statement based on mechanism
    claim_templates = {
        'pricing_cost_down': f"{concept} signals downward price pressure, likely driven by competition and efficiency gains.",
        'pricing_cost_up': f"{concept} indicates pricing power shifts, potentially due to demand or differentiation.",
        'enterprise_adoption': f"{concept} suggests enterprise adoption acceleration, driven by proven ROI or compliance readiness.",
        'regulation_enforcement': f"{concept} points to increasing regulatory scrutiny, which may reshape market dynamics.",
        'model_capability_jump': f"{concept} reflects capability improvements that could shift competitive positioning.",
        'infra_scaling': f"{concept} indicates infrastructure expansion, signaling demand growth or strategic positioning.",
        'security_risk': f"{concept} highlights emerging security concerns that may trigger defensive measures.",
        'compute_constraint': f"{concept} suggests compute availability issues affecting development velocity.",
        'data_rights_ip': f"{concept} reflects evolving data rights landscape affecting training practices.",
        'distribution_shift': f"{concept} indicates changing distribution channels reshaping market access.",
        'consolidation_mna': f"{concept} points to market consolidation pressures among AI companies.",
        'open_source_acceleration': f"{concept} signals open source momentum challenging proprietary models.",
        'talent_dynamics': f"{concept} reflects talent market shifts affecting AI development capacity.",
        'investment_surge': f"{concept} indicates investment activity changes in AI sector.",
        'media_attention_spike': f"{concept} shows elevated media attention without clear underlying mechanism.",
        'null_hypothesis': f"{concept} lacks clear causal mechanism; may be noise or early signal.",
    }
    
    return claim_templates.get(mechanism_id, f"{concept} represents {display_name} dynamics.")


def build_predicted_signals(
    mechanism_id: str,
    mechanism_info: Dict[str, Any],
    meta: Dict[str, Any],
    evidence_strength: str = 'moderate',
) -> List[PredictedSignal]:
    """
    Build predicted next signals from mechanism templates (v2.0 + v2.1 enhanced).
    
    Now includes canonical metrics and observable queries.
    """
    predicted = []
    templates = mechanism_info.get('predicted_signals', {})
    
    # Get limits based on evidence strength
    min_pred, max_pred, max_timeframe = get_prediction_limits(evidence_strength)
    is_speculative = (evidence_strength == 'weak')
    
    # Default timeframes by category (capped by max_timeframe)
    base_timeframes = {
        'technical': 14,
        'financial': 30,
        'social': 7,
        'media': 7,
        'predictive': 14,
    }
    
    for category, template in templates.items():
        if len(predicted) >= max_pred:
            break
            
        description = template.get('description', f"Monitor {category} signals")
        sources = template.get('example_sources', [])
        base_tf = base_timeframes.get(category, 14)
        
        # Apply timeframe limits based on evidence strength
        if evidence_strength == 'weak':
            timeframe = min(base_tf, 14)  # 7-14 days max
        else:
            timeframe = min(base_tf, max_timeframe)
        
        # Extract metric and direction (v2.0)
        metric, direction = extract_metric_and_direction(description)
        
        # Apply observable gate - enhance description if needed
        if not passes_observable_gate(description):
            # Try to add measurable/directional context
            if not metric:
                description = f"{description} (watch for metric changes)"
                metric = "metric"
            if not direction:
                description = f"{description} indicating increase or decline"
                direction = "change"
        
        # v2.1: Get canonical metric
        canonical_metric, _ = get_canonical_metric(metric, category)
        
        # v2.1: Build observable query
        observable_query = build_observable_query(
            category=category,
            metric=metric or canonical_metric,
            direction=direction or 'up',
            sources=sources,
            timeframe_days=timeframe,
        )
        
        predicted.append(PredictedSignal(
            category=category,
            description=description,
            example_sources=sources,
            expected_timeframe_days=timeframe,
            metric=metric,
            direction=direction,
            speculative=is_speculative,
            canonical_metric=canonical_metric,
            observable_query=observable_query,
        ))
    
    # Ensure minimum predictions (only for moderate/strong evidence)
    if evidence_strength != 'weak' and len(predicted) < min_pred:
        missing = ['technical', 'social', 'media']
        for cat in missing:
            if cat not in [p.category for p in predicted]:
                metric = 'volume'
                direction = 'increase'
                canonical, _ = get_canonical_metric(metric, cat)
                
                predicted.append(PredictedSignal(
                    category=cat,
                    description=f"Monitor {cat} channels for related volume increase",
                    example_sources=['twitter', 'hackernews'] if cat == 'social' else ['techmeme'],
                    expected_timeframe_days=min(base_timeframes.get(cat, 14), max_timeframe),
                    metric=metric,
                    direction=direction,
                    speculative=is_speculative,
                    canonical_metric=canonical,
                    observable_query=build_observable_query(
                        category=cat,
                        metric=metric,
                        direction=direction,
                        sources=['twitter', 'hackernews'] if cat == 'social' else ['techmeme'],
                        timeframe_days=min(base_timeframes.get(cat, 14), max_timeframe),
                    ),
                ))
                if len(predicted) >= min_pred:
                    break
    
    # Final filter: reject predictions without measurable metric (v2.0)
    valid_predictions = []
    for pred in predicted:
        # Re-check with strict gate
        if passes_observable_gate(pred.description) or pred.metric:
            valid_predictions.append(pred)
    
    # Ensure we have at least 1 prediction
    if not valid_predictions:
        valid_predictions.append(PredictedSignal(
            category='media',
            description='Monitor for substantive developments with volume increase',
            example_sources=['techmeme', 'twitter'],
            expected_timeframe_days=14,
            metric='volume',
            direction='increase',
            speculative=True,
            canonical_metric='keyword_frequency',
            observable_query=build_observable_query(
                category='media',
                metric='volume',
                direction='increase',
                sources=['techmeme', 'twitter'],
                timeframe_days=14,
            ),
        ))
    
    return valid_predictions[:max_pred]


def build_falsifiers(mechanism_id: str, mechanism_info: Dict[str, Any]) -> Tuple[List[str], List[MeasurableFalsifier]]:
    """
    Build falsifiers from mechanism templates (v2.0 + v2.1).
    
    Returns:
        (falsifiers_list, falsifiers_v2) - both for compatibility
    """
    falsifier_texts = mechanism_info.get('falsifiers', [])
    
    if not falsifier_texts:
        falsifier_texts = [
            "Pattern fails to persist beyond current cycle",
            "Contradicting evidence emerges",
            "Alternative explanation proves more likely",
        ]
    
    falsifier_texts = falsifier_texts[:3]
    
    # v2.1: Build structured falsifiers
    falsifiers_v2 = []
    
    # Mapping of keywords to observables
    falsifier_observables = {
        'price': FalsifierObservable(metric='price_change', direction='up', window_days=30, available=True),
        'stabilize': FalsifierObservable(metric='price_change', direction='up', window_days=30, available=True),
        'demand': FalsifierObservable(metric='keyword_frequency', direction='down', window_days=14, available=True),
        'competition': FalsifierObservable(metric='contract_count', direction='down', window_days=30, available=True),
        'pilot': FalsifierObservable(metric='contract_count', direction='down', window_days=30, available=True),
        'compliance': FalsifierObservable(metric='certification', direction='down', window_days=30, available=True),
        'roi': FalsifierObservable(metric='earnings_mentions', direction='down', window_days=90, available=True),
        'regulation': FalsifierObservable(metric='article_count', direction='down', window_days=30, available=True),
        'attention': FalsifierObservable(metric='keyword_frequency', direction='down', window_days=7, available=True),
        'fade': FalsifierObservable(metric='keyword_frequency', direction='down', window_days=7, available=True),
    }
    
    for text in falsifier_texts:
        observable = None
        text_lower = text.lower()
        
        # Try to match to an observable
        for keyword, obs in falsifier_observables.items():
            if keyword in text_lower:
                observable = obs
                break
        
        if observable is None:
            # Default: not measurable yet
            observable = FalsifierObservable(
                metric='custom_metric',
                direction='down',
                window_days=30,
                available=False,
            )
        
        falsifiers_v2.append(MeasurableFalsifier(
            text=text,
            observable=observable,
        ))
    
    return falsifier_texts, falsifiers_v2


def compute_hypothesis_confidence(
    meta: Dict[str, Any],
    mechanism_hits: int,
    predictions_observable: bool,
) -> Tuple[float, ConfidenceBreakdown, ConfidenceInputs, ConfidenceDebug, bool, List[str]]:
    """
    Compute hypothesis confidence with full breakdown (v2.0 + v2.1).
    
    Returns:
        (confidence, breakdown, confidence_inputs, confidence_debug, review_required, rules_fired)
    """
    rules_fired = []
    penalties = []
    
    # Extract meta fields
    meta_confidence = meta.get('concept_confidence', 0.5)
    category_diversity = meta.get('category_diversity', {})
    category_count = category_diversity.get('category_count', 1) if isinstance(category_diversity, dict) else 1
    categories = category_diversity.get('categories', ['media']) if isinstance(category_diversity, dict) else ['media']
    persistence_days = meta.get('persistence_days', 1)
    independence_score = meta.get('independence_score', 0.5)
    review_required = meta.get('review_required', False)
    
    # v2.1: Track scaling factor
    scaling_factor = CONFIDENCE_WEIGHTS['meta_confidence']
    
    # Base from meta confidence
    base = scaling_factor * meta_confidence
    rules_fired.append(f"base_from_meta:{meta_confidence:.2f}")
    
    # v2.1: Create confidence inputs and debug
    confidence_inputs = ConfidenceInputs(
        meta_confidence_raw=meta_confidence,
        meta_to_hypothesis_scaling=scaling_factor,
    )
    
    confidence_debug = ConfidenceDebug(
        base_scaled=base,
        base_raw=meta_confidence,
        scaling_factor=scaling_factor,
    )
    
    # Category diversity bonus
    diversity_factor = min(1.0, category_count / 3)
    diversity_bonus = CONFIDENCE_WEIGHTS['category_diversity'] * diversity_factor
    rules_fired.append(f"category_diversity:{category_count}")
    
    # Persistence bonus
    persistence_factor = min(1.0, persistence_days / 5)
    persistence_bonus = CONFIDENCE_WEIGHTS['persistence'] * persistence_factor
    rules_fired.append(f"persistence_days:{persistence_days}")
    
    # Independence bonus
    independence_bonus = CONFIDENCE_WEIGHTS['independence'] * independence_score
    rules_fired.append(f"independence:{independence_score:.2f}")
    
    # Specificity bonus (based on mechanism detection strength)
    specificity_factor = min(1.0, mechanism_hits / 5)
    specificity_bonus = CONFIDENCE_WEIGHTS['specificity'] * specificity_factor
    rules_fired.append(f"mechanism_hits:{mechanism_hits}")
    
    # Sum up
    raw_confidence = base + diversity_bonus + persistence_bonus + independence_bonus + specificity_bonus
    
    # Apply penalties
    if not predictions_observable:
        raw_confidence -= PENALTY_GENERIC_PREDICTIONS
        penalties.append(f"generic_predictions:-{PENALTY_GENERIC_PREDICTIONS}")
        rules_fired.append("penalty:generic_predictions")
    
    if mechanism_hits < MIN_MECHANISM_KEYWORDS:
        raw_confidence -= PENALTY_WEAK_MECHANISM
        penalties.append(f"weak_mechanism:-{PENALTY_WEAK_MECHANISM}")
        rules_fired.append("penalty:weak_mechanism")
        review_required = True
    
    # Apply caps
    if review_required:
        if raw_confidence > REVIEW_REQUIRED_CAP:
            penalties.append(f"review_required_cap:{REVIEW_REQUIRED_CAP}")
            rules_fired.append(f"cap:review_required:{REVIEW_REQUIRED_CAP}")
            raw_confidence = REVIEW_REQUIRED_CAP
    
    if category_count == 1 and 'media' in categories:
        if raw_confidence > MEDIA_ONLY_CAP:
            penalties.append(f"media_only_cap:{MEDIA_ONLY_CAP}")
            rules_fired.append(f"cap:media_only:{MEDIA_ONLY_CAP}")
            raw_confidence = MEDIA_ONLY_CAP
    
    # Clamp
    final_confidence = max(0.0, min(1.0, raw_confidence))
    
    breakdown = ConfidenceBreakdown(
        base_from_meta_confidence=base,
        diversity_bonus=diversity_bonus,
        persistence_bonus=persistence_bonus,
        independence_bonus=independence_bonus,
        specificity_bonus=specificity_bonus,
        penalties_applied=penalties,
        final=final_confidence,
    )
    
    return final_confidence, breakdown, confidence_inputs, confidence_debug, review_required, rules_fired


def should_emit_attention_spike(meta: Dict[str, Any], mechanism_hits: int) -> bool:
    """
    Determine if we should emit a competing attention_spike hypothesis (v2.0).
    
    Conditions:
    - Media only sources OR
    - review_required = true OR
    - mechanism hits < 3
    """
    category_diversity = meta.get('category_diversity', {})
    categories = category_diversity.get('categories', ['media']) if isinstance(category_diversity, dict) else ['media']
    
    media_only = len(categories) == 1 and 'media' in categories
    review_required = meta.get('review_required', False)
    weak_mechanism = mechanism_hits < MIN_MECHANISM_KEYWORDS
    
    return media_only or review_required or weak_mechanism


def generate_hypothesis(
    meta: Dict[str, Any],
    mechanism_id: str,
    mechanism_info: Dict[str, Any],
    keyword_hits: int,
    matched_keywords: List[str],
    primary_sources: List[str],
    secondary_sources: List[str],
    is_alternative: bool = False,
    mechanism_trace: Optional[MechanismTrace] = None,
) -> Hypothesis:
    """Generate a single hypothesis for a mechanism (v2.0 + v2.1 enhanced)."""
    
    # Classify evidence strength
    evidence_strength = classify_evidence_strength(meta)
    
    # Build title (sanitized, <= 8 words, no filler)
    display_name = mechanism_info.get('display_name', mechanism_id.replace('_', ' ').title())
    maturity = meta.get('maturity_stage', '')
    
    if is_alternative:
        raw_title = f"Alternative: {display_name}"
    else:
        # v2.0: Prefer mechanism-first, no filler words
        if maturity in ['trending', 'mainstream']:
            raw_title = f"{display_name} Accelerates"
        elif maturity == 'emerging':
            raw_title = f"Emerging {display_name}"
        else:
            raw_title = display_name
    
    title = sanitize_title(raw_title)
    
    # Build claim
    claim = build_claim(mechanism_id, mechanism_info, meta)
    
    # Build why_now
    why_now = build_why_now(meta)
    
    # Build evidence
    supporting_signals = meta.get('supporting_signals', [])
    category_diversity = meta.get('category_diversity', {})
    source_categories = category_diversity.get('categories', ['media']) if isinstance(category_diversity, dict) else ['media']
    
    # Extract entities (keep in evidence, just not title)
    entities = set()
    for insight in meta.get('supporting_insights', []):
        entities.update(insight.get('entities', []))
    
    key_quotes = extract_key_quotes(meta)
    
    evidence = EvidenceUsed(
        supporting_signals=supporting_signals[:10],
        source_categories=source_categories,
        key_entities=list(entities)[:10],
        key_quotes=key_quotes,
    )
    
    # Build predicted signals with strength conditioning (v2.0 + v2.1)
    predicted = build_predicted_signals(
        mechanism_id, 
        mechanism_info, 
        meta,
        evidence_strength=evidence_strength,
    )
    
    # Check if predictions are observable
    predictions_observable = all(
        passes_observable_gate(p.description) or p.metric 
        for p in predicted
    )
    
    # Build falsifiers (v2.0 + v2.1)
    falsifiers, falsifiers_v2 = build_falsifiers(mechanism_id, mechanism_info)
    
    # Compute confidence (v2.0 + v2.1)
    confidence, breakdown, conf_inputs, conf_debug, review_required, rules_fired = compute_hypothesis_confidence(
        meta, keyword_hits, predictions_observable
    )
    
    # Generate stable ID
    concept_slug = meta.get('concept_slug', meta.get('meta_id', ''))
    hypothesis_id = generate_hypothesis_id(concept_slug, mechanism_id, claim)
    
    # Build debug info
    debug = DebugInfo(
        rules_fired=rules_fired,
        scoring_terms={
            'meta_confidence': meta.get('concept_confidence', 0.5),
            'category_count': category_diversity.get('category_count', 1) if isinstance(category_diversity, dict) else 1,
            'persistence_days': meta.get('persistence_days', 1),
            'independence_score': meta.get('independence_score', 0.5),
            'evidence_strength': {'weak': 0.33, 'moderate': 0.66, 'strong': 1.0}.get(evidence_strength, 0.5),
        },
        mechanism_keyword_hits=keyword_hits,
        mechanism_keywords_matched=matched_keywords,
    )
    
    return Hypothesis(
        hypothesis_id=hypothesis_id,
        title=title,
        mechanism=mechanism_id,
        claim=claim,
        why_now=why_now,
        evidence_used=evidence,
        predicted_next_signals=predicted,
        falsifiers=falsifiers,
        confidence=confidence,
        confidence_breakdown=breakdown,
        review_required=review_required,
        debug=debug,
        mechanism_trace=mechanism_trace,
        confidence_inputs=conf_inputs,
        confidence_debug=conf_debug,
        falsifiers_v2=falsifiers_v2,
    )


def generate_attention_spike_hypothesis(meta: Dict[str, Any], taxonomy: Dict[str, Any]) -> Hypothesis:
    """
    Generate an attention_spike competing hypothesis (v2.0).
    
    Used when evidence is weak to provide an alternative "noise" explanation.
    """
    mechanism_info = taxonomy.get('mechanisms', {}).get('media_attention_spike', {
        'display_name': 'Media Attention Spike',
        'keywords': ['viral', 'trending', 'hype', 'buzz'],
        'predicted_signals': {
            'media': {'description': 'Monitor for sustained coverage or fade', 'example_sources': ['techmeme', 'twitter']}
        },
        'falsifiers': ['Attention fades without substantive developments', 'Story debunked or corrected'],
    })
    
    # Build trace for attention_spike selection
    trace = MechanismTrace(
        candidate_scores={'media_attention_spike': 1},
        matched_terms=['media-only', 'weak-mechanism'],
        evidence_sources=['structural_analysis'],
        selection_reason='competing_null_hypothesis:weak_evidence',
        evidence_sources_primary=[],
        evidence_sources_secondary=['structural_analysis'],
    )
    
    return generate_hypothesis(
        meta=meta,
        mechanism_id='media_attention_spike',
        mechanism_info=mechanism_info,
        keyword_hits=1,
        matched_keywords=['media'],
        primary_sources=[],
        secondary_sources=['structural_analysis'],
        is_alternative=True,
        mechanism_trace=trace,
    )


def generate_null_hypothesis(meta: Dict[str, Any], taxonomy: Dict[str, Any]) -> Hypothesis:
    """Generate a null/noise hypothesis when evidence is weak."""
    mechanism_info = taxonomy.get('mechanisms', {}).get('null_hypothesis', {
        'display_name': 'Noise / Insufficient Signal',
        'predicted_signals': {
            'media': {'description': 'Monitor for substantive developments', 'example_sources': ['techmeme']}
        },
        'falsifiers': ['Pattern resolves into clear mechanism', 'Additional corroborating signals emerge'],
    })
    
    trace = MechanismTrace(
        candidate_scores={'null_hypothesis': 0},
        matched_terms=[],
        evidence_sources=['no_mechanism_match'],
        selection_reason='null_hypothesis:no_mechanism_detected',
        evidence_sources_primary=[],
        evidence_sources_secondary=['no_mechanism_match'],
    )
    
    return generate_hypothesis(
        meta=meta,
        mechanism_id='null_hypothesis',
        mechanism_info=mechanism_info,
        keyword_hits=0,
        matched_keywords=[],
        primary_sources=[],
        secondary_sources=['no_mechanism_match'],
        is_alternative=False,
        mechanism_trace=trace,
    )


def build_watch_items(hypotheses: List[Hypothesis], top_n: int = 3) -> Tuple[List[str], List[WatchItem]]:
    """
    Build ranked watch items from hypotheses (v2.0 + v2.1).
    
    Formula:
        watch_priority_score = (hypothesis_confidence * 0.5) + 
                               (measurability_score * 0.3) + 
                               (time_proximity_score * 0.2)
    
    Returns:
        (what_to_watch_next, watch_items) - both for compatibility
    """
    candidates = []
    
    for hyp in hypotheses:
        for pred in hyp.predicted_next_signals:
            # Measurability score
            is_canonical = pred.canonical_metric and pred.canonical_metric != 'custom_metric'
            measurability_score = 1.0 if is_canonical else 0.5
            
            # Time proximity score
            time_proximity_score = 1.0 / (pred.expected_timeframe_days / 7)
            time_proximity_score = min(1.0, time_proximity_score)  # Cap at 1
            
            # Final score
            score = (
                hyp.confidence * 0.5 +
                measurability_score * 0.3 +
                time_proximity_score * 0.2
            )
            
            # Build reasons
            reasons = []
            reasons.append(f"hypothesis_confidence:{hyp.confidence:.2f}")
            reasons.append(f"measurable:{is_canonical}")
            reasons.append(f"timeframe:{pred.expected_timeframe_days}d")
            
            # Timeframe bucket
            bucket = get_timeframe_bucket(pred.expected_timeframe_days)
            
            candidates.append(WatchItem(
                description=pred.description.split('(')[0].strip(),  # Clean up
                watch_priority_score=score,
                watch_priority_reason=reasons,
                timeframe_bucket=bucket,
            ))
    
    # Sort by score descending
    candidates.sort(key=lambda x: x.watch_priority_score, reverse=True)
    
    # Deduplicate
    seen = set()
    unique_items = []
    
    for item in candidates:
        normalized = item.description.lower()[:40]
        if normalized not in seen:
            seen.add(normalized)
            unique_items.append(item)
            if len(unique_items) >= top_n:
                break
    
    # Build v2.0 compat list
    what_to_watch_next = [item.description for item in unique_items]
    
    return what_to_watch_next, unique_items


def build_watchlist(hypotheses: List[Hypothesis], top_n: int = 3) -> List[str]:
    """
    Build what_to_watch_next from top predictions across hypotheses (v2.0 compat).
    """
    what_to_watch, _ = build_watch_items(hypotheses, top_n)
    return what_to_watch


# =============================================================================
# HYPOTHESIS ENGINE
# =============================================================================

class HypothesisEngine:
    """
    Converts meta-signals into causal hypotheses with predicted next signals (v2.1).
    
    This engine uses a rule-first approach (deterministic, no LLM required)
    to generate testable hypotheses from meta-signal patterns.
    
    v2.1 enhancements:
    - Confidence transparency (inputs + debug)
    - Canonical metric types
    - Observable queries for every prediction
    - Ranked watchlist with priority scoring
    - Primary/secondary evidence source separation
    - Measurable falsifiers
    
    v2.0 features (retained):
    - Mechanism scoring trace for full explainability
    - Strength-conditioned predictions
    - Observable gate (anti-vagueness filter)
    - Null hypothesis competition
    - Bundle watchlist output
    - Improved title sanitization
    """
    
    def __init__(
        self,
        taxonomy_path: Path = None,
        entity_registry_path: Path = None,
        observable_metrics_path: Path = None,
        output_dir: Path = None,
        allow_secondary_evidence: bool = False,
    ):
        """Initialize HypothesisEngine."""
        self.taxonomy = load_mechanism_taxonomy(taxonomy_path)
        self.entity_names = load_entity_names(entity_registry_path)
        self.observable_metrics = load_observable_metrics(observable_metrics_path)
        self.allow_secondary_evidence = allow_secondary_evidence
        
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "data" / "insights"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"HypothesisEngine v2.1 initialized with {len(self.taxonomy.get('mechanisms', {}))} mechanisms")
    
    def process_meta_signal(self, meta: Dict[str, Any]) -> MetaHypothesisBundle:
        """
        Generate hypothesis bundle for a single meta-signal.
        
        Args:
            meta: Meta-signal dict from meta_signal_engine output
        
        Returns:
            MetaHypothesisBundle with ranked hypotheses
        """
        meta_id = meta.get('meta_id', '')
        concept_slug = meta.get('concept_slug', '')
        concept_name = meta.get('concept_name', '')
        maturity_stage = meta.get('maturity_stage', 'weak')
        
        logger.debug(f"Processing meta-signal: {concept_name} ({meta_id})")
        
        # Step A: Detect mechanisms with source tracking (v2.0 + v2.1)
        detections = detect_mechanisms(
            meta, 
            self.taxonomy,
            allow_secondary_evidence=self.allow_secondary_evidence,
        )
        
        # Step B: Generate 2-4 hypothesis candidates
        hypotheses = []
        
        # Primary mechanism hypothesis
        primary_mech, primary_hits, primary_keywords, primary_src, secondary_src = get_primary_mechanism(detections)
        primary_info = self.taxonomy.get('mechanisms', {}).get(primary_mech, {})
        
        # Build mechanism trace for primary (v2.0 + v2.1)
        primary_trace = build_mechanism_trace(
            detections,
            primary_mech,
            selection_reason='highest_score' if primary_hits >= MIN_MECHANISM_KEYWORDS else 'best_available',
        )
        
        if primary_hits >= MIN_MECHANISM_KEYWORDS or primary_mech != 'null_hypothesis':
            primary_hyp = generate_hypothesis(
                meta=meta,
                mechanism_id=primary_mech,
                mechanism_info=primary_info,
                keyword_hits=primary_hits,
                matched_keywords=primary_keywords,
                primary_sources=primary_src,
                secondary_sources=secondary_src,
                is_alternative=False,
                mechanism_trace=primary_trace,
            )
            hypotheses.append(primary_hyp)
        
        # Alternative mechanism hypothesis
        alt = get_alternative_mechanism(detections, primary_mech)
        if alt:
            alt_mech, alt_hits, alt_keywords, alt_primary, alt_secondary = alt
            alt_info = self.taxonomy.get('mechanisms', {}).get(alt_mech, {})
            alt_trace = build_mechanism_trace(
                detections,
                alt_mech,
                selection_reason='second_highest_score',
            )
            alt_hyp = generate_hypothesis(
                meta=meta,
                mechanism_id=alt_mech,
                mechanism_info=alt_info,
                keyword_hits=alt_hits,
                matched_keywords=alt_keywords,
                primary_sources=alt_primary,
                secondary_sources=alt_secondary,
                is_alternative=True,
                mechanism_trace=alt_trace,
            )
            hypotheses.append(alt_hyp)
        
        # v2.0: Null hypothesis competition - emit attention_spike when evidence weak
        if should_emit_attention_spike(meta, primary_hits):
            # Check if attention_spike isn't already the primary
            if primary_mech not in ['media_attention_spike', 'null_hypothesis']:
                attention_hyp = generate_attention_spike_hypothesis(meta, self.taxonomy)
                hypotheses.append(attention_hyp)
            else:
                # Already using noise mechanism, add null hypothesis
                null_hyp = generate_null_hypothesis(meta, self.taxonomy)
                hypotheses.append(null_hyp)
        
        # Null hypothesis if no valid mechanisms
        if not hypotheses or (primary_hits < MIN_MECHANISM_KEYWORDS and primary_mech == 'null_hypothesis'):
            null_hyp = generate_null_hypothesis(meta, self.taxonomy)
            if not any(h.mechanism == 'null_hypothesis' for h in hypotheses):
                hypotheses.append(null_hyp)
        
        # Step C: Sort by confidence
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        
        # Select top hypothesis
        selected_id = hypotheses[0].hypothesis_id if hypotheses else ''
        bundle_confidence = hypotheses[0].confidence if hypotheses else 0.0
        
        # v2.0 + v2.1: Build watchlist from all hypotheses
        what_to_watch_next, watch_items = build_watch_items(hypotheses, top_n=3)
        
        bundle = MetaHypothesisBundle(
            meta_id=meta_id,
            concept_slug=concept_slug,
            concept_name=concept_name,
            maturity_stage=maturity_stage,
            hypotheses=hypotheses,
            selected_hypothesis_id=selected_id,
            bundle_confidence=bundle_confidence,
            generated_at=datetime.now().isoformat(),
            version="2.1",
            what_to_watch_next=what_to_watch_next,
            watch_items=watch_items,
        )
        
        logger.debug(f"Generated {len(hypotheses)} hypotheses for '{concept_name}', top: {hypotheses[0].title if hypotheses else 'none'}")
        
        return bundle
    
    def process_meta_signals(
        self,
        meta_signals: List[Dict[str, Any]],
        date: str = None,
    ) -> Dict[str, Any]:
        """
        Process multiple meta-signals into hypothesis bundles.
        
        Args:
            meta_signals: List of meta-signal dicts
            date: Date string for output file naming
        
        Returns:
            Result dict with bundles and summary stats
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        logger.info(f"Processing {len(meta_signals)} meta-signals into hypotheses")
        
        bundles = []
        mechanism_counts = Counter()
        review_required_count = 0
        
        for meta in meta_signals:
            bundle = self.process_meta_signal(meta)
            bundles.append(bundle)
            
            # Track stats
            if bundle.hypotheses:
                top_hyp = bundle.hypotheses[0]
                mechanism_counts[top_hyp.mechanism] += 1
                if top_hyp.review_required:
                    review_required_count += 1
        
        # Build result
        result = {
            'date': date,
            'generated_at': datetime.now().isoformat(),
            'version': '2.1',
            'summary': {
                'total_metas': len(meta_signals),
                'total_bundles': len(bundles),
                'total_hypotheses': sum(len(b.hypotheses) for b in bundles),
                'top_mechanisms': dict(mechanism_counts.most_common(5)),
                'metas_requiring_review': review_required_count,
            },
            'bundles': [b.to_dict() for b in bundles],
        }
        
        # Write output file
        output_file = self.output_dir / f"hypotheses_{date}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Wrote {len(bundles)} hypothesis bundles to {output_file}")
        
        return result
    
    def format_report_section(self, bundles: List[MetaHypothesisBundle], max_items: int = 5) -> str:
        """
        Format a minimal report section for hypothesis output.
        
        Args:
            bundles: List of MetaHypothesisBundle objects
            max_items: Maximum items to show
        
        Returns:
            Formatted string for report inclusion
        """
        lines = []
        lines.append("## Hypotheses from Meta-Signals")
        lines.append("")
        
        for bundle in bundles[:max_items]:
            if not bundle.hypotheses:
                continue
            
            top_hyp = bundle.hypotheses[0]
            
            lines.append(f"**{bundle.concept_name}** → {top_hyp.title} (conf: {top_hyp.confidence:.0%})")
            lines.append("")
            lines.append("What to watch:")
            
            for pred in top_hyp.predicted_next_signals[:3]:
                spec_marker = " ⚠️" if pred.speculative else ""
                lines.append(f"  - [{pred.category}] {pred.description} ({pred.expected_timeframe_days}d){spec_marker}")
            
            lines.append("")
        
        return '\n'.join(lines)


# =============================================================================
# CLI INTEGRATION
# =============================================================================

def run_hypothesis_engine(
    meta_signals_path: Path = None,
    output_dir: Path = None,
    date: str = None,
) -> Dict[str, Any]:
    """
    Run hypothesis engine on meta-signals file.
    
    Args:
        meta_signals_path: Path to meta_signals JSON file
        output_dir: Output directory for hypotheses
        date: Date string
    
    Returns:
        Result dict with bundles and stats
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    if meta_signals_path is None:
        meta_signals_path = Path(__file__).parent.parent / "data" / "meta_signals" / f"meta_signals_{date}.json"
    
    # Load meta-signals
    if not meta_signals_path.exists():
        logger.warning(f"Meta-signals file not found: {meta_signals_path}")
        return {'error': 'meta_signals_not_found', 'path': str(meta_signals_path)}
    
    with open(meta_signals_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    meta_signals = data.get('meta_signals', [])
    
    if not meta_signals:
        logger.warning("No meta-signals found in file")
        return {'error': 'no_meta_signals', 'path': str(meta_signals_path)}
    
    # Run engine
    engine = HypothesisEngine(output_dir=output_dir)
    result = engine.process_meta_signals(meta_signals, date)
    
    return result


# =============================================================================
# TESTS (inline)
# =============================================================================

def _test_sanitize_title():
    """Test title sanitization."""
    title = sanitize_title("OpenAI Pricing Strategy")
    assert 'openai' not in title.lower()
    
    title = sanitize_title("Google and Microsoft Competition")
    assert 'google' not in title.lower()
    assert 'microsoft' not in title.lower()
    
    title = sanitize_title("Enterprise Adoption Rising")
    assert 'enterprise' in title.lower()
    
    # v2.0: Test filler word removal
    title = sanitize_title("Pricing Pressure Trend Strengthening Signal Dynamics")
    assert 'trend' not in title.lower()
    assert 'signal' not in title.lower()
    
    print("[PASS] _test_sanitize_title")


def _test_is_observable():
    """Test observable detection."""
    assert is_observable("New benchmark results published")
    assert is_observable("Funding round announced")
    assert is_observable("API release scheduled")
    assert not is_observable("Things are changing")
    
    print("[PASS] _test_is_observable")


def _test_observable_gate():
    """Test anti-vagueness filter (v2.0)."""
    # Should pass: has measurable + direction
    assert passes_observable_gate("Revenue growth reported")
    assert passes_observable_gate("Downloads increase expected")
    assert passes_observable_gate("Contract volume decline")
    
    # Should fail: missing direction
    assert not passes_observable_gate("New benchmark results")
    
    # Should fail: missing measurable
    assert not passes_observable_gate("Things are increasing")
    
    print("[PASS] _test_observable_gate")


def _test_canonical_metric():
    """Test canonical metric mapping (v2.1)."""
    # Direct match
    canonical, cat = get_canonical_metric("arr", "financial")
    assert canonical == "arr"
    
    # Alias match
    canonical, cat = get_canonical_metric("revenue", "financial")
    assert canonical == "arr"
    
    # Fallback
    canonical, cat = get_canonical_metric("unknown_metric", None)
    assert canonical == "custom_metric"
    
    print("[PASS] _test_canonical_metric")


def _test_evidence_source_classification():
    """Test evidence source classification (v2.1)."""
    sources = ['concept_name', 'meta_insight', 'naming_reason', 'mechanism_bucket']
    primary, secondary = classify_evidence_sources(sources)
    
    assert 'concept_name' in primary
    assert 'meta_insight' in primary
    assert 'naming_reason' in secondary
    assert 'mechanism_bucket' in secondary
    
    print("[PASS] _test_evidence_source_classification")


def _test_evidence_strength():
    """Test evidence strength classification (v2.0)."""
    # Weak: low confidence
    weak_meta = {'concept_confidence': 0.45, 'category_diversity': {'category_count': 2}}
    assert classify_evidence_strength(weak_meta) == 'weak'
    
    # Strong: high confidence + diversity
    strong_meta = {'concept_confidence': 0.80, 'category_diversity': {'category_count': 3}}
    assert classify_evidence_strength(strong_meta) == 'strong'
    
    # Moderate: middle ground
    moderate_meta = {'concept_confidence': 0.65, 'category_diversity': {'category_count': 2}}
    assert classify_evidence_strength(moderate_meta) == 'moderate'
    
    print("[PASS] _test_evidence_strength")


def _test_hypothesis_id_stability():
    """Test hypothesis ID is stable."""
    id1 = generate_hypothesis_id("slug123", "pricing_cost_down", "Prices are declining")
    id2 = generate_hypothesis_id("slug123", "pricing_cost_down", "Prices are declining")
    id3 = generate_hypothesis_id("slug123", "pricing_cost_down", "Prices  are   declining")  # Different whitespace
    
    assert id1 == id2
    assert id1 == id3  # Normalized whitespace
    
    print("[PASS] _test_hypothesis_id_stability")


def _test_mechanism_detection():
    """Test mechanism detection."""
    taxonomy = load_mechanism_taxonomy()
    
    meta = {
        'concept_name': 'Pricing Pressure',
        'description': 'Price cuts and margin compression in AI market',
        'supporting_insights': [
            {'insight_text': 'API pricing reduced', 'buckets': ['pricing'], 'entities': []}
        ],
    }
    
    detections = detect_mechanisms(meta, taxonomy)
    
    assert len(detections) > 0
    assert detections[0][0] in ['pricing_cost_down', 'pricing_cost_up']
    
    # v2.1: Check that sources are tracked (now 5-tuple)
    assert len(detections[0]) == 5  # (mech_id, hits, keywords, primary, secondary)
    
    print("[PASS] _test_mechanism_detection")


def _test_observable_query():
    """Test observable query building (v2.1)."""
    query = build_observable_query(
        category='financial',
        metric='revenue',
        direction='increase',
        sources=['sec', 'earnings_call'],
        timeframe_days=30,
    )
    
    assert query.source == 'sec'
    assert query.window_days == 30
    assert query.expected_direction == 'up'
    
    print("[PASS] _test_observable_query")


def _test_watch_items():
    """Test watch items building (v2.1)."""
    # Create mock hypothesis
    hyp = Hypothesis(
        hypothesis_id='h1',
        title='Test',
        mechanism='test',
        claim='Claim',
        why_now='Now',
        evidence_used=EvidenceUsed([], [], [], []),
        predicted_next_signals=[
            PredictedSignal(
                'technical', 'New SDK releases expected', ['github'], 14,
                metric='sdk', direction='increase', canonical_metric='sdk_release',
                observable_query=ObservableQuery('github', 'repo:test', 'count', 14, 'up'),
            ),
        ],
        falsifiers=['Test falsifier'],
        confidence=0.75,
        confidence_breakdown=ConfidenceBreakdown(0.4, 0.1, 0.08, 0.08, 0.09, [], 0.75),
        review_required=False,
        debug=DebugInfo([], {}, 0, []),
    )
    
    what_to_watch, watch_items = build_watch_items([hyp], top_n=3)
    
    assert len(watch_items) >= 1
    assert watch_items[0].watch_priority_score > 0
    assert watch_items[0].timeframe_bucket in ['7d', '14d', '30d', '60d']
    
    print("[PASS] _test_watch_items")


def run_tests():
    """Run inline tests."""
    print("\n=== HYPOTHESIS ENGINE v2.1 TESTS ===\n")
    
    _test_sanitize_title()
    _test_is_observable()
    _test_observable_gate()
    _test_canonical_metric()
    _test_evidence_source_classification()
    _test_evidence_strength()
    _test_hypothesis_id_stability()
    _test_mechanism_detection()
    _test_observable_query()
    _test_watch_items()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
