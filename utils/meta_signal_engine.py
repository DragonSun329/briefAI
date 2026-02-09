"""
Meta-Signal Engine (Concept Synthesizer) - Detect structural trends from signals.

Part of Gravity Engine v2.6: Technology Foresight Layer.

This module sits above SignalTracker and synthesizes higher-level conceptual
trends by grouping multiple persistent signals. It answers:
  "What structural change is happening in AI?"
NOT
  "What company appeared in the news?"

Example transformation:
  Input signals:
    - OpenAI API pricing change
    - Anthropic enterprise contracts
    - AWS Bedrock usage billing
  
  Output meta-signal:
    "Enterprise Monetization Expanding"

Pipeline: Signals → Insight Extraction → Concept Embeddings → Clustering → 
          MetaSignals → Specificity Gate → Deduplication → Hierarchy → Confidence Hardening

v2.6 Enhancements:
  - Independence scoring using source independence levels
  - Stable concept_slug for rename churn prevention
  - Name freezing after persistence + confidence thresholds
  - Structured merge_reason and hierarchy_reason
  - Enhanced validation using independence_score
"""

import json
import math
import hashlib
import re
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from collections import defaultdict, Counter

from loguru import logger

# Try to import embeddings support
try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    np = None
    logger.info("Embeddings not available, meta-signal engine will use overlap-only mode")


# =============================================================================
# CONSTANTS
# =============================================================================

# Clustering thresholds
CONCEPT_SIMILARITY_THRESHOLD = 0.72
MIN_SUPPORTING_SIGNALS = 2
MIN_ENTITY_DIVERSITY = 2    # Must span >= 2 different entities OR
MIN_BUCKET_DIVERSITY = 2    # >= 2 different buckets

# Embedding settings
EMBEDDING_DECIMALS = 6

# Maturity mapping
MATURITY_PRIORITY = {
    'mainstream': 4,
    'trending': 3,
    'emerging': 2,
    'weak_signal': 1,
    'fading': 0,
    'dead': -1,
}

# Company names to filter from trend names
COMPANY_FILTER = {
    'openai', 'anthropic', 'google', 'meta', 'microsoft', 'apple', 'nvidia',
    'amazon', 'aws', 'deepmind', 'cohere', 'mistral', 'stability', 'midjourney',
    'hugging face', 'huggingface', 'inflection', 'character', 'runway', 'adobe',
    'salesforce', 'ibm', 'intel', 'amd', 'qualcomm', 'arm', 'tesla', 'baidu',
    'alibaba', 'tencent', 'bytedance', 'samsung', 'xai', 'perplexity', 'deepseek',
}

# Model names to filter
MODEL_FILTER = {
    'gpt', 'gpt-4', 'gpt-5', 'claude', 'gemini', 'llama', 'mistral', 'mixtral',
    'palm', 'bard', 'copilot', 'chatgpt', 'dall-e', 'dalle', 'stable diffusion',
    'midjourney', 'sora', 'opus', 'sonnet', 'haiku', 'o1', 'o3', 'r1',
}

# =============================================================================
# V2.5: GENERIC NAME DETECTION PATTERNS
# =============================================================================

GENERIC_NAME_PATTERNS = [
    r"\bai\b.*\baccelerat",
    r"\bai\b.*\bgrowing\b",
    r"\bai\b.*\bmarket\b",
    r"\bai\b.*\bimprov",
    r"\bai\b.*\bboom\b",
    r"\bai\b.*\bhype\b",
    r"\bai\b.*\bevolving\b",
    r"\bai\b.*\bshifting\b",
    r"\bai\b.*\bchanging\b",
    r"\bai\b.*\bdynamics\b",
    r"\bai\b.*\becosystem\b",
    r"\bai\b.*\blandscape\b",
]

# =============================================================================
# V2.5: MECHANISM KEYWORD BUCKETS (for specificity gate)
# =============================================================================

MECHANISM_KEYWORD_BUCKETS = {
    'pricing-monetization': {
        'keywords': ['price', 'pricing', 'monetization', 'subscription', 'margin', 
                    'revenue', 'cfo', 'capex', 'fee', 'billing', 'rate'],
        'directions': ['Pressure Rising', 'Wars Intensifying', 'Models Shifting'],
        'display_name': 'Pricing',
    },
    'inference-cost': {
        'keywords': ['inference', 'latency', 'throughput', 'token', 'distill', 
                    'quant', 'optimization', 'efficiency', 'speed'],
        'directions': ['Efficiency Improving', 'Costs Declining', 'Optimization Advancing'],
        'display_name': 'Inference Cost',
    },
    'enterprise-adoption': {
        'keywords': ['enterprise', 'procurement', 'contract', 'seat', 'compliance',
                    'rollout', 'integration', 'corporate', 'business', 'b2b', 'deal'],
        'directions': ['Expanding', 'Accelerating', 'Maturing'],
        'display_name': 'Enterprise Adoption',
    },
    'regulation': {
        'keywords': ['regulation', 'regulator', 'ban', 'policy', 'law', 'antitrust',
                    'export', 'sanction', 'legislation', 'compliance', 'govern'],
        'directions': ['Tightening', 'Framework Emerging', 'Pressure Rising'],
        'display_name': 'Regulation',
    },
    'open-source': {
        'keywords': ['open weights', 'open-source', 'opensource', 'apache', 'mit',
                    'fork', 'repo', 'community', 'local', 'self-hosted'],
        'directions': ['Adoption Rising', 'Quality Improving', 'Ecosystem Growing'],
        'display_name': 'Open-Source',
    },
    'compute-hardware': {
        'keywords': ['gpu', 'nvidia', 'chip', 'datacenter', 'hbm', 'networking',
                    'infrastructure', 'capacity', 'accelerator', 'hardware'],
        'directions': ['Capacity Expanding', 'Constraints Easing', 'Investment Surging'],
        'display_name': 'Compute',
    },
    'security-misuse': {
        'keywords': ['jailbreak', 'exploit', 'phishing', 'abuse', 'watermark',
                    'safety', 'misuse', 'vulnerability', 'risk', 'alignment'],
        'directions': ['Concerns Growing', 'Measures Tightening', 'Research Advancing'],
        'display_name': 'Security',
    },
    'data-privacy': {
        'keywords': ['dataset', 'privacy', 'pii', 'consent', 'copyright', 
                    'licensing', 'training data', 'synthetic'],
        'directions': ['Privacy Focus Rising', 'Constraints Tightening', 'Quality Improving'],
        'display_name': 'Data Privacy',
    },
    'research': {
        'keywords': ['research', 'paper', 'benchmark', 'breakthrough', 'capability',
                    'sota', 'state-of-the-art', 'arxiv', 'publication'],
        'directions': ['Breakthroughs Accelerating', 'Capabilities Advancing'],
        'display_name': 'Research',
    },
    'investment': {
        'keywords': ['investment', 'funding', 'valuation', 'raise', 'capital',
                    'vc', 'series', 'investor', 'round'],
        'directions': ['Surge Continuing', 'Focus Shifting', 'Cooling Down'],
        'display_name': 'Investment',
    },
}

# Minimum mechanism keyword hits threshold
MIN_MECHANISM_HITS = 3

# =============================================================================
# V2.5: DEDUPLICATION THRESHOLDS
# =============================================================================

META_DEDUP_SIMILARITY_THRESHOLD = 0.80
META_DEDUP_OVERLAP_THRESHOLD = 0.40

# =============================================================================
# V2.5: HIERARCHY THRESHOLDS
# =============================================================================

HIERARCHY_SIMILARITY_MIN = 0.72
HIERARCHY_OVERLAP_MIN = 0.25
HIERARCHY_OVERLAP_MAX = 0.40

# =============================================================================
# V2.5: CONFIDENCE HARDENING FACTORS & CAPS
# =============================================================================

PERSISTENCE_BONUS_MULTI_DAY = 0.10
PERSISTENCE_PENALTY_SINGLE_DAY = -0.05
CATEGORY_BONUS_TWO = 0.08
CATEGORY_BONUS_THREE_PLUS = 0.12
SINGLE_CATEGORY_CONFIDENCE_CAP = 0.60
REVIEW_REQUIRED_CONFIDENCE_CAP = 0.45
UNVALIDATED_EARLY_CONFIDENCE_CAP = 0.50

# =============================================================================
# V2.6: INDEPENDENCE SCORING
# =============================================================================

INDEPENDENCE_VALUES = {
    "high": 1.0,
    "medium": 0.7,
    "low": 0.4,
}

INDEPENDENCE_BONUS_MULTIPLIER = 0.12  # max independence bonus

# =============================================================================
# V2.6: NAME FREEZE THRESHOLDS
# =============================================================================

NAME_FREEZE_MIN_PERSISTENCE = 3
NAME_FREEZE_MIN_CONFIDENCE = 0.60
NAME_FREEZE_MECHANISM_IMPROVEMENT_THRESHOLD = 0.25

# =============================================================================
# V2.6: VALIDATION THRESHOLDS (independence-aware)
# =============================================================================

VALIDATED_MIN_WEIGHTED_DIVERSITY = 1.5
VALIDATED_MIN_INDEPENDENCE = 0.75
WEAKLY_VALIDATED_MIN_INDEPENDENCE = 0.6

# Default config paths
DEFAULT_SOURCE_CATEGORIES_PATH = Path(__file__).parent.parent / "config" / "source_categories.json"
DEFAULT_ENTITY_REGISTRY_PATH = Path(__file__).parent.parent / "config" / "entity_registry.json"


# =============================================================================
# CONFIG LOADERS
# =============================================================================

_SOURCE_CATEGORIES_CACHE = None
_ENTITY_REGISTRY_CACHE = None


def load_source_categories(config_path: Path = None) -> Dict[str, Any]:
    """Load source categories config with caching."""
    global _SOURCE_CATEGORIES_CACHE
    
    if _SOURCE_CATEGORIES_CACHE is not None:
        return _SOURCE_CATEGORIES_CACHE
    
    if config_path is None:
        config_path = DEFAULT_SOURCE_CATEGORIES_PATH
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            _SOURCE_CATEGORIES_CACHE = json.load(f)
            return _SOURCE_CATEGORIES_CACHE
    except Exception as e:
        logger.warning(f"Failed to load source_categories.json: {e}")
        return {}


def load_entity_registry(config_path: Path = None) -> Dict[str, Any]:
    """Load entity registry config with caching."""
    global _ENTITY_REGISTRY_CACHE
    
    if _ENTITY_REGISTRY_CACHE is not None:
        return _ENTITY_REGISTRY_CACHE
    
    if config_path is None:
        config_path = DEFAULT_ENTITY_REGISTRY_PATH
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            _ENTITY_REGISTRY_CACHE = json.load(f)
            return _ENTITY_REGISTRY_CACHE
    except Exception as e:
        logger.warning(f"Failed to load entity_registry.json: {e}")
        return {}


def get_all_entity_names() -> Set[str]:
    """Get all entity names and aliases for sanitization."""
    registry = load_entity_registry()
    names = set()
    
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
    
    return names


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class SignalInsight:
    """Extracted structural implication from a signal."""
    signal_id: str
    signal_name: str
    date: str
    insight_text: str           # Structural implication, not summary
    entities: List[str]
    buckets: List[str]
    velocity: float
    confidence: float
    status: str
    embedding: Optional[List[float]] = None
    source_category: Optional[str] = None
    corroborating_sources: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'signal_id': self.signal_id,
            'signal_name': self.signal_name,
            'date': self.date,
            'insight_text': self.insight_text,
            'entities': self.entities,
            'buckets': self.buckets,
            'velocity': round(self.velocity, 3),
            'confidence': round(self.confidence, 3),
            'status': self.status,
        }
        if self.embedding:
            result['embedding'] = self.embedding
        if self.source_category:
            result['source_category'] = self.source_category
        if self.corroborating_sources:
            result['corroborating_sources'] = self.corroborating_sources
        return result
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'SignalInsight':
        return cls(
            signal_id=d['signal_id'],
            signal_name=d['signal_name'],
            date=d['date'],
            insight_text=d['insight_text'],
            entities=d.get('entities', []),
            buckets=d.get('buckets', []),
            velocity=d.get('velocity', 1.0),
            confidence=d.get('confidence', 0.5),
            status=d.get('status', 'weak_signal'),
            embedding=d.get('embedding'),
            source_category=d.get('source_category'),
            corroborating_sources=d.get('corroborating_sources', []),
        )


@dataclass
class NamingReason:
    """v2.5: Explanation for how a meta-signal was named."""
    was_generic: bool = False
    original_name: str = ""
    mechanism_terms: List[str] = field(default_factory=list)
    mechanism_bucket: Optional[str] = None
    mechanism_score: int = 0
    review_required: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'was_generic': self.was_generic,
            'original_name': self.original_name,
            'mechanism_terms': self.mechanism_terms,
            'mechanism_bucket': self.mechanism_bucket,
            'mechanism_score': self.mechanism_score,
            'review_required': self.review_required,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'NamingReason':
        return cls(
            was_generic=d.get('was_generic', False),
            original_name=d.get('original_name', ''),
            mechanism_terms=d.get('mechanism_terms', []),
            mechanism_bucket=d.get('mechanism_bucket'),
            mechanism_score=d.get('mechanism_score', 0),
            review_required=d.get('review_required', False),
        )


@dataclass
class CategoryDiversity:
    """v2.5: Category diversity breakdown."""
    categories: List[str] = field(default_factory=list)
    category_count: int = 0
    weighted_diversity: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'categories': self.categories,
            'category_count': self.category_count,
            'weighted_diversity': round(self.weighted_diversity, 3),
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'CategoryDiversity':
        return cls(
            categories=d.get('categories', []),
            category_count=d.get('category_count', 0),
            weighted_diversity=d.get('weighted_diversity', 0.0),
        )


@dataclass
class ConfidenceBreakdown:
    """v2.5/v2.6: Explainable confidence computation breakdown."""
    base: float = 0.0
    diversity: float = 0.0
    count: float = 0.0
    persistence: float = 0.0
    category: float = 0.0
    independence: float = 0.0  # v2.6: independence bonus
    caps_applied: List[str] = field(default_factory=list)
    final: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'base': round(self.base, 3),
            'diversity': round(self.diversity, 3),
            'count': round(self.count, 3),
            'persistence': round(self.persistence, 3),
            'category': round(self.category, 3),
            'independence': round(self.independence, 3),
            'caps_applied': self.caps_applied,
            'final': round(self.final, 3),
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ConfidenceBreakdown':
        return cls(
            base=d.get('base', 0.0),
            diversity=d.get('diversity', 0.0),
            count=d.get('count', 0.0),
            persistence=d.get('persistence', 0.0),
            category=d.get('category', 0.0),
            independence=d.get('independence', 0.0),
            caps_applied=d.get('caps_applied', []),
            final=d.get('final', 0.0),
        )


@dataclass
class MergeReason:
    """v2.6: Structured reasoning for meta merges."""
    rule: str = "DEDUP_MERGE_V2"
    centroid_similarity: float = 0.0
    signal_overlap: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'rule': self.rule,
            'centroid_similarity': round(self.centroid_similarity, 3),
            'signal_overlap': round(self.signal_overlap, 3),
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'MergeReason':
        return cls(
            rule=d.get('rule', 'DEDUP_MERGE_V2'),
            centroid_similarity=d.get('centroid_similarity', 0.0),
            signal_overlap=d.get('signal_overlap', 0.0),
        )


@dataclass
class HierarchyReason:
    """v2.6: Structured reasoning for hierarchy creation."""
    rule: str = "PARENT_CHILD_V2"
    centroid_similarity: float = 0.0
    signal_overlap: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'rule': self.rule,
            'centroid_similarity': round(self.centroid_similarity, 3),
            'signal_overlap': round(self.signal_overlap, 3),
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'HierarchyReason':
        return cls(
            rule=d.get('rule', 'PARENT_CHILD_V2'),
            centroid_similarity=d.get('centroid_similarity', 0.0),
            signal_overlap=d.get('signal_overlap', 0.0),
        )


@dataclass
class MetaSignal:
    """A higher-level conceptual trend synthesized from multiple signals."""
    meta_id: str
    concept_name: str           # Human-readable trend name (≤ 6 words, no companies)
    description: str            # Longer description of the trend
    supporting_signals: List[str]  # signal_ids
    supporting_insights: List[SignalInsight] = field(default_factory=list)
    first_seen: str = ""
    last_updated: str = ""
    maturity_stage: str = "weak"  # weak, emerging, trending, established
    concept_confidence: float = 0.0
    acceleration: float = 0.0
    entity_diversity: int = 0
    bucket_diversity: int = 0
    centroid_embedding: Optional[List[float]] = None
    
    # v2.5: Fields
    mechanism: Optional[str] = None
    naming_reason: Optional[NamingReason] = None
    merged_from: List[str] = field(default_factory=list)
    parent_meta_id: Optional[str] = None
    child_meta_ids: List[str] = field(default_factory=list)
    persistence_days: int = 1
    persistence_factor: float = 0.0
    category_diversity: Optional[CategoryDiversity] = None
    validation_status: str = "unvalidated_early_meta"
    review_required: bool = False
    confidence_breakdown: Optional[ConfidenceBreakdown] = None
    
    # v2.6: New fields
    concept_slug: str = ""                          # Stable ID survives renames
    name_frozen: bool = False                       # True if name locked
    independence_score: float = 0.0                 # Source independence weighted avg
    merge_reason: Optional[MergeReason] = None      # Structured merge explanation
    hierarchy_reason: Optional[HierarchyReason] = None  # Structured hierarchy explanation
    
    def to_dict(self, include_insights: bool = False, include_embedding: bool = False) -> Dict[str, Any]:
        result = {
            'meta_id': self.meta_id,
            'concept_name': self.concept_name,
            'description': self.description,
            'supporting_signals': self.supporting_signals,
            'first_seen': self.first_seen,
            'last_updated': self.last_updated,
            'maturity_stage': self.maturity_stage,
            'concept_confidence': round(self.concept_confidence, 3),
            'acceleration': round(self.acceleration, 3),
            'entity_diversity': self.entity_diversity,
            'bucket_diversity': self.bucket_diversity,
            # v2.5 fields
            'mechanism': self.mechanism,
            'naming_reason': self.naming_reason.to_dict() if self.naming_reason else None,
            'merged_from': self.merged_from,
            'parent_meta_id': self.parent_meta_id,
            'child_meta_ids': self.child_meta_ids,
            'persistence_days': self.persistence_days,
            'persistence_factor': round(self.persistence_factor, 3),
            'category_diversity': self.category_diversity.to_dict() if self.category_diversity else None,
            'validation_status': self.validation_status,
            'review_required': self.review_required,
            'confidence_breakdown': self.confidence_breakdown.to_dict() if self.confidence_breakdown else None,
            # v2.6 fields
            'concept_slug': self.concept_slug,
            'name_frozen': self.name_frozen,
            'independence_score': round(self.independence_score, 3),
            'merge_reason': self.merge_reason.to_dict() if self.merge_reason else None,
            'hierarchy_reason': self.hierarchy_reason.to_dict() if self.hierarchy_reason else None,
        }
        if include_insights:
            result['supporting_insights'] = [i.to_dict() for i in self.supporting_insights]
        if include_embedding and self.centroid_embedding:
            result['centroid_embedding'] = self.centroid_embedding
        return result
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'MetaSignal':
        naming_reason = None
        if d.get('naming_reason'):
            naming_reason = NamingReason.from_dict(d['naming_reason'])
        
        category_diversity = None
        if d.get('category_diversity'):
            category_diversity = CategoryDiversity.from_dict(d['category_diversity'])
        
        confidence_breakdown = None
        if d.get('confidence_breakdown'):
            confidence_breakdown = ConfidenceBreakdown.from_dict(d['confidence_breakdown'])
        
        merge_reason = None
        if d.get('merge_reason'):
            merge_reason = MergeReason.from_dict(d['merge_reason'])
        
        hierarchy_reason = None
        if d.get('hierarchy_reason'):
            hierarchy_reason = HierarchyReason.from_dict(d['hierarchy_reason'])
        
        return cls(
            meta_id=d['meta_id'],
            concept_name=d['concept_name'],
            description=d.get('description', ''),
            supporting_signals=d.get('supporting_signals', []),
            supporting_insights=[SignalInsight.from_dict(i) for i in d.get('supporting_insights', [])],
            first_seen=d.get('first_seen', ''),
            last_updated=d.get('last_updated', ''),
            maturity_stage=d.get('maturity_stage', 'weak'),
            concept_confidence=d.get('concept_confidence', 0.0),
            acceleration=d.get('acceleration', 0.0),
            entity_diversity=d.get('entity_diversity', 0),
            bucket_diversity=d.get('bucket_diversity', 0),
            centroid_embedding=d.get('centroid_embedding'),
            # v2.5 fields
            mechanism=d.get('mechanism'),
            naming_reason=naming_reason,
            merged_from=d.get('merged_from', []),
            parent_meta_id=d.get('parent_meta_id'),
            child_meta_ids=d.get('child_meta_ids', []),
            persistence_days=d.get('persistence_days', 1),
            persistence_factor=d.get('persistence_factor', 0.0),
            category_diversity=category_diversity,
            validation_status=d.get('validation_status', 'unvalidated_early_meta'),
            review_required=d.get('review_required', False),
            confidence_breakdown=confidence_breakdown,
            # v2.6 fields
            concept_slug=d.get('concept_slug', ''),
            name_frozen=d.get('name_frozen', False),
            independence_score=d.get('independence_score', 0.0),
            merge_reason=merge_reason,
            hierarchy_reason=hierarchy_reason,
        )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def generate_meta_id(insight_texts: List[str]) -> str:
    """Generate stable meta-signal ID from insight texts."""
    key = '|'.join(sorted(insight_texts)[:5])
    return hashlib.md5(key.encode()).hexdigest()[:12]


def generate_concept_slug(entities: List[str], mechanism: Optional[str], first_seen: str) -> str:
    """
    v2.6: Generate stable concept slug that survives renames.
    
    Args:
        entities: Top entities (sorted)
        mechanism: Primary mechanism bucket or None
        first_seen: First seen date
    
    Returns:
        12-char hex slug
    """
    # Sort and take top 3 entities
    sorted_entities = sorted(set(e.lower() for e in entities))[:3]
    
    # Use mechanism or 'general'
    mech = mechanism if mechanism else 'general'
    
    # Build slug source
    slug_source = '|'.join(sorted_entities) + '|' + mech
    
    # SHA1 hash
    return hashlib.sha1(slug_source.encode()).hexdigest()[:12]


def clean_trend_name(name: str) -> str:
    """Remove company/model names from trend name."""
    words = name.lower().split()
    cleaned = []
    
    # Get entity names from registry
    entity_names = get_all_entity_names()
    all_filtered = COMPANY_FILTER | MODEL_FILTER | entity_names
    
    for word in words:
        # Clean punctuation for matching
        word_clean = re.sub(r'[^a-z0-9]', '', word)
        
        # Check if word (or cleaned version) is filtered
        is_filtered = (
            word_clean in all_filtered or
            word in all_filtered
        )
        
        # Also check if word starts with a filtered term
        for term in all_filtered:
            if len(term) > 2 and (word_clean.startswith(term) or word.startswith(term)):
                is_filtered = True
                break
        
        if word_clean and not is_filtered:
            cleaned.append(word)
    
    return ' '.join(cleaned).strip()


def sanitize_name_with_registry(name: str) -> str:
    """Sanitize a name by removing entity names from registry."""
    entity_names = get_all_entity_names()
    words = name.split()
    sanitized = []
    
    for word in words:
        word_lower = word.lower()
        word_clean = re.sub(r'[^a-z0-9]', '', word_lower)
        
        if word_clean not in entity_names and word_lower not in entity_names:
            sanitized.append(word)
    
    return ' '.join(sanitized).strip()


def is_company_or_model(text: str) -> bool:
    """Check if text is primarily a company or model name."""
    text_lower = text.lower()
    entity_names = get_all_entity_names()
    
    for company in COMPANY_FILTER | entity_names:
        if company in text_lower:
            return True
    for model in MODEL_FILTER:
        if model in text_lower:
            return True
    return False


def jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


# =============================================================================
# V2.6: INDEPENDENCE SCORING
# =============================================================================

def compute_independence_score(
    category_diversity: CategoryDiversity,
    source_cfg: Dict[str, Any] = None,
) -> float:
    """
    v2.6: Compute weighted independence score from categories.
    
    Uses independence_level from source_categories.json:
    - high: 1.0
    - medium: 0.7
    - low: 0.4
    
    Returns:
        Weighted average independence score [0, 1]
    """
    if source_cfg is None:
        source_cfg = load_source_categories()
    
    categories_cfg = source_cfg.get('categories', {})
    
    if not category_diversity or not category_diversity.categories:
        return 0.4  # Default to low
    
    total_weight = 0.0
    weighted_independence = 0.0
    
    for cat in category_diversity.categories:
        cat_info = categories_cfg.get(cat, {})
        weight = cat_info.get('weight', 0.7)
        independence_level = cat_info.get('independence_level', 'medium')
        independence_value = INDEPENDENCE_VALUES.get(independence_level, 0.7)
        
        weighted_independence += weight * independence_value
        total_weight += weight
    
    if total_weight == 0:
        return 0.4
    
    return weighted_independence / total_weight


# =============================================================================
# V2.6: VALIDATION STATUS WITH INDEPENDENCE
# =============================================================================

def compute_validation_status_v26(
    category_diversity: CategoryDiversity,
    independence_score: float,
) -> str:
    """
    v2.6: Compute validation status using independence.
    
    Rules:
    - Validated if: weighted_diversity >= 1.5 OR independence_score >= 0.75
    - Weakly validated if: category_count == 1 AND independence_score >= 0.6
    - Else: unvalidated_early_meta
    """
    weighted_div = category_diversity.weighted_diversity if category_diversity else 0.0
    cat_count = category_diversity.category_count if category_diversity else 0
    
    if weighted_div >= VALIDATED_MIN_WEIGHTED_DIVERSITY or independence_score >= VALIDATED_MIN_INDEPENDENCE:
        return "validated"
    
    if cat_count == 1 and independence_score >= WEAKLY_VALIDATED_MIN_INDEPENDENCE:
        return "weakly_validated"
    
    if cat_count >= 1:
        return "weakly_validated"
    
    return "unvalidated_early_meta"


# =============================================================================
# V2.6: NAME FREEZE LOGIC
# =============================================================================

def should_freeze_name(
    persistence_days: int,
    confidence: float,
    current_frozen: bool = False,
) -> bool:
    """
    v2.6: Check if name should be frozen.
    
    Freeze if:
    - persistence_days >= 3 AND confidence >= 0.60
    - OR already frozen
    """
    if current_frozen:
        return True
    
    return (
        persistence_days >= NAME_FREEZE_MIN_PERSISTENCE and
        confidence >= NAME_FREEZE_MIN_CONFIDENCE
    )


def can_unfreeze_name(
    old_mechanism_score: int,
    new_mechanism_score: int,
) -> bool:
    """
    v2.6: Check if frozen name can be unfrozen.
    
    Only unfreeze if mechanism confidence improves by > 0.25 (normalized).
    """
    if old_mechanism_score == 0:
        return new_mechanism_score >= MIN_MECHANISM_HITS
    
    improvement = (new_mechanism_score - old_mechanism_score) / max(old_mechanism_score, 1)
    return improvement > NAME_FREEZE_MECHANISM_IMPROVEMENT_THRESHOLD


# =============================================================================
# V2.5/V2.6: CATEGORY DIVERSITY FUNCTIONS
# =============================================================================

def infer_source_from_signal(signal_name: str, buckets: List[str], entities: List[str]) -> List[str]:
    """Infer corroborating sources from signal data."""
    text = f"{signal_name} {' '.join(buckets)} {' '.join(entities)}".lower()
    
    sources = []
    
    source_hints = {
        'github': ['github', 'repo', 'commit', 'fork', 'star'],
        'arxiv': ['arxiv', 'paper', 'research', 'publication'],
        'huggingface': ['huggingface', 'hf', 'model card', 'transformers'],
        'reddit': ['reddit', 'r/', 'subreddit'],
        'hackernews': ['hackernews', 'hn', 'hacker news', 'ycombinator'],
        'twitter': ['twitter', 'tweet', 'x.com'],
        'sec': ['sec', 'filing', '10-k', '10-q', '8-k'],
        'crunchbase': ['crunchbase', 'funding', 'series'],
        'polymarket': ['polymarket', 'prediction market'],
        'news': ['news', 'article', 'report', 'press'],
    }
    
    for source, hints in source_hints.items():
        for hint in hints:
            if hint in text:
                sources.append(source)
                break
    
    if not sources:
        sources = ['news']
    
    return sources


def compute_category_diversity(
    insights: List[SignalInsight],
    source_cfg: Dict[str, Any] = None,
) -> CategoryDiversity:
    """Compute category diversity for supporting insights."""
    if source_cfg is None:
        source_cfg = load_source_categories()
    
    source_metadata = source_cfg.get('source_metadata', {})
    categories_cfg = source_cfg.get('categories', {})
    
    all_categories = set()
    
    for insight in insights:
        sources = insight.corroborating_sources
        if not sources:
            sources = infer_source_from_signal(
                insight.signal_name,
                insight.buckets,
                insight.entities
            )
        
        for source in sources:
            source_lower = source.lower()
            if source_lower in source_metadata:
                cat = source_metadata[source_lower].get('category')
                if cat:
                    all_categories.add(cat)
                    insight.source_category = cat
            else:
                if any(s in source_lower for s in ['github', 'arxiv', 'paper']):
                    all_categories.add('technical')
                elif any(s in source_lower for s in ['reddit', 'twitter', 'hn']):
                    all_categories.add('social')
                elif any(s in source_lower for s in ['sec', 'funding', 'crunchbase']):
                    all_categories.add('financial')
                elif any(s in source_lower for s in ['polymarket', 'metaculus']):
                    all_categories.add('predictive')
                else:
                    all_categories.add('media')
    
    weighted = 0.0
    for cat in all_categories:
        if cat in categories_cfg:
            weighted += categories_cfg[cat].get('weight', 0.7)
        else:
            weighted += 0.7
    
    return CategoryDiversity(
        categories=sorted(list(all_categories)),
        category_count=len(all_categories),
        weighted_diversity=weighted,
    )


def compute_category_factor(category_diversity: CategoryDiversity) -> Tuple[float, str]:
    """Compute category factor for confidence adjustment (legacy v2.5 compatible)."""
    count = category_diversity.category_count
    
    if count >= 3:
        return CATEGORY_BONUS_THREE_PLUS, "validated"
    elif count >= 2:
        return CATEGORY_BONUS_TWO, "validated"
    else:
        return 0.0, "weakly_validated"


# =============================================================================
# V2.5: PERSISTENCE FACTOR FUNCTIONS
# =============================================================================

def compute_persistence_days(insights: List[SignalInsight]) -> int:
    """Count distinct dates across supporting insights."""
    dates = set()
    for insight in insights:
        if insight.date:
            dates.add(insight.date)
    return len(dates) if dates else 1


def compute_persistence_factor(persistence_days: int) -> float:
    """Compute persistence factor for confidence adjustment."""
    if persistence_days >= 2:
        return PERSISTENCE_BONUS_MULTI_DAY
    else:
        return PERSISTENCE_PENALTY_SINGLE_DAY


# =============================================================================
# V2.5: SPECIFICITY GATE FUNCTIONS
# =============================================================================

def is_generic_name(name: str) -> bool:
    """Check if a concept name matches generic patterns."""
    name_lower = name.lower()
    for pattern in GENERIC_NAME_PATTERNS:
        if re.search(pattern, name_lower):
            return True
    return False


def extract_mechanism_keywords(insights: List[SignalInsight]) -> Dict[str, Any]:
    """Extract mechanism keywords from insights using keyword buckets."""
    all_text = []
    for insight in insights:
        all_text.append(insight.insight_text.lower())
        all_text.append(insight.signal_name.lower())
        all_text.extend(b.lower().replace('-', ' ') for b in insight.buckets)
    
    combined_text = ' '.join(all_text)
    
    bucket_scores = {}
    bucket_terms = {}
    
    for bucket_id, bucket_info in MECHANISM_KEYWORD_BUCKETS.items():
        keywords = bucket_info['keywords']
        matches = []
        
        for kw in keywords:
            if kw.lower() in combined_text:
                matches.append(kw)
        
        bucket_scores[bucket_id] = len(matches)
        bucket_terms[bucket_id] = matches
    
    if not bucket_scores:
        return {'mechanism': None, 'score': 0, 'terms': [], 'bucket_scores': {}}
    
    winner = max(bucket_scores.items(), key=lambda x: x[1])
    winner_id, winner_score = winner
    
    return {
        'mechanism': winner_id if winner_score >= MIN_MECHANISM_HITS else None,
        'score': winner_score,
        'terms': bucket_terms.get(winner_id, []),
        'bucket_scores': bucket_scores,
    }


def infer_direction(insights: List[SignalInsight], mechanism: str) -> str:
    """Infer trend direction based on velocity and mechanism."""
    avg_velocity = sum(i.velocity for i in insights) / len(insights) if insights else 1.0
    
    bucket_info = MECHANISM_KEYWORD_BUCKETS.get(mechanism, {})
    directions = bucket_info.get('directions', ['Shifting'])
    
    if avg_velocity > 2.5:
        idx = 0
    elif avg_velocity > 1.5:
        idx = min(1, len(directions) - 1)
    else:
        idx = min(2, len(directions) - 1)
    
    return directions[idx] if idx < len(directions) else 'Shifting'


def rename_generic_meta(
    meta: MetaSignal,
    mechanism_result: Dict[str, Any],
) -> Tuple[str, bool, NamingReason]:
    """Rename a generic meta-signal using mechanism-driven naming."""
    original_name = meta.concept_name
    mechanism = mechanism_result['mechanism']
    terms = mechanism_result['terms']
    score = mechanism_result['score']
    
    naming_reason = NamingReason(
        was_generic=True,
        original_name=original_name,
        mechanism_terms=terms,
        mechanism_bucket=mechanism,
        mechanism_score=score,
    )
    
    if mechanism is None or score < MIN_MECHANISM_HITS:
        naming_reason.review_required = True
        return "Mixed Signals Review", True, naming_reason
    
    bucket_info = MECHANISM_KEYWORD_BUCKETS.get(mechanism, {})
    display_name = bucket_info.get('display_name', mechanism.replace('-', ' ').title())
    
    direction = infer_direction(meta.supporting_insights, mechanism)
    
    new_name = f"{display_name} {direction}"
    new_name = sanitize_name_with_registry(new_name)
    
    words = new_name.split()
    if len(words) > 6:
        new_name = ' '.join(words[:6])
    
    naming_reason.review_required = False
    return new_name, False, naming_reason


def apply_specificity_gate(meta: MetaSignal) -> MetaSignal:
    """
    Apply specificity gate to a meta-signal.
    
    v2.6: Respects name_frozen flag.
    """
    # v2.6: Skip renaming if name is frozen
    if meta.name_frozen:
        if meta.naming_reason is None:
            meta.naming_reason = NamingReason(was_generic=False)
        return meta
    
    if not is_generic_name(meta.concept_name):
        meta.naming_reason = NamingReason(was_generic=False)
        return meta
    
    mechanism_result = extract_mechanism_keywords(meta.supporting_insights)
    
    new_name, review_required, naming_reason = rename_generic_meta(meta, mechanism_result)
    
    meta.concept_name = new_name
    meta.mechanism = mechanism_result['mechanism']
    meta.naming_reason = naming_reason
    meta.review_required = review_required
    
    return meta


# =============================================================================
# V2.5/V2.6: DEDUPLICATION FUNCTIONS
# =============================================================================

def compute_meta_similarity(
    meta_a: MetaSignal,
    meta_b: MetaSignal,
    embedder: 'ConceptEmbedder' = None,
) -> Tuple[float, float]:
    """Compute similarity between two meta-signals."""
    centroid_sim = 0.0
    if embedder and meta_a.centroid_embedding and meta_b.centroid_embedding:
        centroid_sim = embedder.cosine_similarity(
            meta_a.centroid_embedding,
            meta_b.centroid_embedding
        )
    
    signals_a = set(meta_a.supporting_signals)
    signals_b = set(meta_b.supporting_signals)
    signal_overlap = jaccard_similarity(signals_a, signals_b)
    
    return centroid_sim, signal_overlap


def merge_meta_signals(
    primary: MetaSignal,
    secondary: MetaSignal,
    centroid_sim: float,
    signal_overlap: float,
    embedder: 'ConceptEmbedder' = None,
) -> MetaSignal:
    """
    Merge secondary into primary meta-signal.
    
    v2.6: Adds merge_reason.
    """
    all_signals = list(set(primary.supporting_signals) | set(secondary.supporting_signals))
    
    insight_ids = {i.signal_id for i in primary.supporting_insights}
    all_insights = list(primary.supporting_insights)
    for insight in secondary.supporting_insights:
        if insight.signal_id not in insight_ids:
            all_insights.append(insight)
            insight_ids.add(insight.signal_id)
    
    all_entities = set()
    all_buckets = set()
    for insight in all_insights:
        all_entities.update(e.lower() for e in insight.entities)
        all_buckets.update(b.lower() for b in insight.buckets)
    
    entity_div = len(all_entities)
    bucket_div = len(all_buckets)
    
    new_centroid = None
    if embedder:
        embeddings = [i.embedding for i in all_insights if i.embedding]
        if embeddings:
            new_centroid = embedder.compute_centroid(embeddings)
    
    all_dates = [i.date for i in all_insights if i.date]
    first_seen = min(all_dates) if all_dates else primary.first_seen
    last_updated = max(all_dates) if all_dates else primary.last_updated
    
    merged_from = list(primary.merged_from)
    if secondary.meta_id not in merged_from:
        merged_from.append(secondary.meta_id)
    
    # v2.6: Add merge reason
    merge_reason = MergeReason(
        rule="DEDUP_MERGE_V2",
        centroid_similarity=centroid_sim,
        signal_overlap=signal_overlap,
    )
    
    primary.supporting_signals = all_signals
    primary.supporting_insights = all_insights
    primary.entity_diversity = entity_div
    primary.bucket_diversity = bucket_div
    primary.centroid_embedding = new_centroid
    primary.first_seen = first_seen
    primary.last_updated = last_updated
    primary.merged_from = merged_from
    primary.merge_reason = merge_reason
    
    primary.acceleration = compute_meta_acceleration(all_insights)
    primary.maturity_stage = derive_maturity_stage(all_insights)
    
    # v2.6: Preserve slug from primary (stable identity)
    if not primary.concept_slug and secondary.concept_slug:
        primary.concept_slug = secondary.concept_slug
    
    logger.info(f"Merged meta '{secondary.concept_name}' into '{primary.concept_name}' (merged_from={merged_from})")
    
    return primary


def dedupe_meta_signals(
    meta_signals: List[MetaSignal],
    embedder: 'ConceptEmbedder' = None,
) -> List[MetaSignal]:
    """Deduplicate near-duplicate meta-signals."""
    if len(meta_signals) < 2:
        return meta_signals
    
    sorted_metas = sorted(meta_signals, key=lambda m: m.concept_confidence, reverse=True)
    
    merged_into = {}
    result = []
    
    for i, meta_i in enumerate(sorted_metas):
        if meta_i.meta_id in merged_into:
            continue
        
        for j in range(i + 1, len(sorted_metas)):
            meta_j = sorted_metas[j]
            
            if meta_j.meta_id in merged_into:
                continue
            
            centroid_sim, signal_overlap = compute_meta_similarity(meta_i, meta_j, embedder)
            
            if centroid_sim >= META_DEDUP_SIMILARITY_THRESHOLD and signal_overlap >= META_DEDUP_OVERLAP_THRESHOLD:
                meta_i = merge_meta_signals(meta_i, meta_j, centroid_sim, signal_overlap, embedder)
                merged_into[meta_j.meta_id] = meta_i.meta_id
                logger.debug(f"Dedup: '{meta_j.concept_name}' merged into '{meta_i.concept_name}' "
                           f"(sim={centroid_sim:.2f}, overlap={signal_overlap:.2f})")
        
        result.append(meta_i)
    
    logger.info(f"Deduplication: {len(meta_signals)} -> {len(result)} meta-signals")
    return result


# =============================================================================
# V2.5/V2.6: HIERARCHY FUNCTIONS
# =============================================================================

def should_create_hierarchy(
    meta_a: MetaSignal,
    meta_b: MetaSignal,
    embedder: 'ConceptEmbedder' = None,
) -> Tuple[bool, float, float]:
    """
    Check if two metas should form parent/child relationship.
    
    v2.6: Returns similarity values for reasoning.
    """
    centroid_sim, signal_overlap = compute_meta_similarity(meta_a, meta_b, embedder)
    
    should = (
        centroid_sim >= HIERARCHY_SIMILARITY_MIN and
        HIERARCHY_OVERLAP_MIN <= signal_overlap < HIERARCHY_OVERLAP_MAX
    )
    
    return should, centroid_sim, signal_overlap


def choose_parent(meta_a: MetaSignal, meta_b: MetaSignal) -> Tuple[MetaSignal, MetaSignal]:
    """Choose which meta should be parent vs child."""
    score_a = (
        meta_a.entity_diversity * 2 +
        meta_a.bucket_diversity * 1.5 +
        len(meta_a.supporting_signals)
    )
    score_b = (
        meta_b.entity_diversity * 2 +
        meta_b.bucket_diversity * 1.5 +
        len(meta_b.supporting_signals)
    )
    
    if score_a >= score_b:
        return meta_a, meta_b
    else:
        return meta_b, meta_a


def name_parent_meta(parent: MetaSignal, children: List[MetaSignal]) -> str:
    """Generate a parent meta name."""
    mechanisms = [c.mechanism for c in children if c.mechanism]
    
    commercialization_mechs = {'pricing-monetization', 'enterprise-adoption', 'investment'}
    
    if any(m in commercialization_mechs for m in mechanisms):
        return "AI Commercialization Shift"
    else:
        return "AI Ecosystem Shift"


def build_hierarchy(
    meta_signals: List[MetaSignal],
    embedder: 'ConceptEmbedder' = None,
) -> List[MetaSignal]:
    """
    Build parent/child relationships for partially overlapping metas.
    
    v2.6: Adds hierarchy_reason.
    """
    if len(meta_signals) < 2:
        return meta_signals
    
    hierarchy_pairs = []
    
    for i in range(len(meta_signals)):
        for j in range(i + 1, len(meta_signals)):
            should, centroid_sim, signal_overlap = should_create_hierarchy(
                meta_signals[i], meta_signals[j], embedder
            )
            if should:
                hierarchy_pairs.append((i, j, centroid_sim, signal_overlap))
    
    if not hierarchy_pairs:
        return meta_signals
    
    parent_children = defaultdict(list)
    
    for i, j, centroid_sim, signal_overlap in hierarchy_pairs:
        parent, child = choose_parent(meta_signals[i], meta_signals[j])
        parent_idx = i if parent.meta_id == meta_signals[i].meta_id else j
        child_idx = j if parent.meta_id == meta_signals[i].meta_id else i
        parent_children[parent_idx].append((child_idx, centroid_sim, signal_overlap))
    
    result = []
    processed_children = set()
    
    for parent_idx, child_data in parent_children.items():
        parent = meta_signals[parent_idx]
        child_indices = [cd[0] for cd in child_data]
        children = [meta_signals[ci] for ci in child_indices]
        
        parent.child_meta_ids = [c.meta_id for c in children]
        
        # v2.6: Add hierarchy reason (use first child's data)
        if child_data:
            _, centroid_sim, signal_overlap = child_data[0]
            parent.hierarchy_reason = HierarchyReason(
                rule="PARENT_CHILD_V2",
                centroid_similarity=centroid_sim,
                signal_overlap=signal_overlap,
            )
        
        if is_generic_name(parent.concept_name) and not parent.name_frozen:
            parent.concept_name = name_parent_meta(parent, children)
        
        result.append(parent)
        
        for child in children:
            child.parent_meta_id = parent.meta_id
            processed_children.add(child.meta_id)
        
        logger.info(f"Hierarchy: '{parent.concept_name}' -> {[c.concept_name for c in children]}")
    
    for meta in meta_signals:
        if meta.meta_id not in [r.meta_id for r in result]:
            result.append(meta)
    
    return result


# =============================================================================
# V2.5/V2.6: CONFIDENCE FORMULA
# =============================================================================

def compute_hardened_confidence(
    insights: List[SignalInsight],
    entity_diversity: int,
    bucket_diversity: int,
    persistence_days: int,
    category_diversity: CategoryDiversity,
    independence_score: float,
    review_required: bool,
    validation_status: str,
) -> Tuple[float, ConfidenceBreakdown]:
    """
    v2.6: Compute hardened meta-signal confidence with independence bonus.
    """
    breakdown = ConfidenceBreakdown()
    caps_applied = []
    
    if not insights:
        breakdown.final = 0.0
        return 0.0, breakdown
    
    # Base: average signal confidence
    base = sum(i.confidence for i in insights) / len(insights)
    breakdown.base = base
    
    # Diversity bonus
    diversity = 0.15 * min(1.0, entity_diversity / 4) + 0.10 * min(1.0, bucket_diversity / 3)
    breakdown.diversity = diversity
    
    # Count bonus (log scale)
    count_bonus = 0.15 * min(1.0, math.log1p(len(insights)) / math.log1p(5))
    breakdown.count = count_bonus
    
    # Persistence factor
    persistence_factor = compute_persistence_factor(persistence_days)
    breakdown.persistence = persistence_factor
    
    # Category factor
    category_factor, _ = compute_category_factor(category_diversity)
    breakdown.category = category_factor
    
    # v2.6: Independence bonus
    independence_bonus = INDEPENDENCE_BONUS_MULTIPLIER * independence_score
    breakdown.independence = independence_bonus
    
    # Sum up
    raw_confidence = base + diversity + count_bonus + persistence_factor + category_factor + independence_bonus
    
    # Apply caps
    if review_required:
        if raw_confidence > REVIEW_REQUIRED_CONFIDENCE_CAP:
            caps_applied.append(f"review_required_cap:{REVIEW_REQUIRED_CONFIDENCE_CAP}")
            raw_confidence = REVIEW_REQUIRED_CONFIDENCE_CAP
    
    if validation_status == "weakly_validated":
        if raw_confidence > SINGLE_CATEGORY_CONFIDENCE_CAP:
            caps_applied.append(f"weakly_validated_cap:{SINGLE_CATEGORY_CONFIDENCE_CAP}")
            raw_confidence = min(raw_confidence, SINGLE_CATEGORY_CONFIDENCE_CAP)
    elif validation_status == "unvalidated_early_meta":
        if raw_confidence > UNVALIDATED_EARLY_CONFIDENCE_CAP:
            caps_applied.append(f"unvalidated_early_cap:{UNVALIDATED_EARLY_CONFIDENCE_CAP}")
            raw_confidence = min(raw_confidence, UNVALIDATED_EARLY_CONFIDENCE_CAP)
    
    final_confidence = max(0.0, min(1.0, raw_confidence))
    
    breakdown.caps_applied = caps_applied
    breakdown.final = final_confidence
    
    return final_confidence, breakdown


def apply_confidence_hardening(
    meta: MetaSignal,
    source_cfg: Dict[str, Any] = None,
) -> MetaSignal:
    """Apply confidence hardening with persistence, category, and independence."""
    if source_cfg is None:
        source_cfg = load_source_categories()
    
    # Compute persistence
    persistence_days = compute_persistence_days(meta.supporting_insights)
    meta.persistence_days = persistence_days
    meta.persistence_factor = compute_persistence_factor(persistence_days)
    
    # Compute category diversity
    cat_diversity = compute_category_diversity(meta.supporting_insights, source_cfg)
    meta.category_diversity = cat_diversity
    
    # v2.6: Compute independence score
    independence_score = compute_independence_score(cat_diversity, source_cfg)
    meta.independence_score = independence_score
    
    # v2.6: Compute validation status with independence
    validation_status = compute_validation_status_v26(cat_diversity, independence_score)
    meta.validation_status = validation_status
    
    # Compute hardened confidence
    confidence, breakdown = compute_hardened_confidence(
        insights=meta.supporting_insights,
        entity_diversity=meta.entity_diversity,
        bucket_diversity=meta.bucket_diversity,
        persistence_days=persistence_days,
        category_diversity=cat_diversity,
        independence_score=independence_score,
        review_required=meta.review_required,
        validation_status=validation_status,
    )
    
    meta.concept_confidence = confidence
    meta.confidence_breakdown = breakdown
    
    # v2.6: Check if name should be frozen
    meta.name_frozen = should_freeze_name(
        persistence_days,
        confidence,
        meta.name_frozen,
    )
    
    return meta


# =============================================================================
# V2.6: SLUG GENERATION
# =============================================================================

def generate_slug_for_meta(meta: MetaSignal) -> str:
    """Generate stable concept slug for a meta-signal."""
    # Collect all entities from insights
    all_entities = []
    for insight in meta.supporting_insights:
        all_entities.extend(insight.entities)
    
    return generate_concept_slug(
        entities=all_entities,
        mechanism=meta.mechanism,
        first_seen=meta.first_seen,
    )


# =============================================================================
# INSIGHT EXTRACTION
# =============================================================================

INSIGHT_PATTERNS = [
    (r'pricing|cost|price|cheaper|expensive|fee|rate', 
     "{mechanism} cost dynamics shifting in AI market"),
    (r'enterprise|business|corporate|commercial|adoption|deploy',
     "Enterprise AI {mechanism} gaining momentum"),
    (r'gpu|compute|infrastructure|capacity|scaling|hardware',
     "AI infrastructure {mechanism} constraints evolving"),
    (r'open.?source|open.?weight|local|self.?hosted|on.?prem',
     "Local/open AI {mechanism} landscape expanding"),
    (r'compet|rival|versus|vs|alternative|challenger',
     "AI market {mechanism} competition intensifying"),
    (r'regulat|law|policy|govern|compliance|safety',
     "AI {mechanism} regulatory environment developing"),
    (r'research|paper|benchmark|capability|breakthrough',
     "AI {mechanism} research advancing"),
    (r'integrat|api|platform|ecosystem|tool|workflow',
     "AI {mechanism} integration patterns emerging"),
    (r'fund|invest|valuation|raise|capital|vc',
     "AI {mechanism} investment trends shifting"),
    (r'hire|talent|team|engineer|researcher|recruit',
     "AI {mechanism} talent dynamics changing"),
]


def extract_mechanism_from_text(text: str) -> str:
    """Extract the core mechanism/behavior from text."""
    text_clean = text.lower()
    
    entity_names = get_all_entity_names()
    for name in COMPANY_FILTER | MODEL_FILTER | entity_names:
        text_clean = re.sub(rf'\b{re.escape(name)}\b', '', text_clean)
    
    words = text_clean.split()
    
    action_words = []
    for word in words:
        if len(word) > 3 and word not in {'the', 'and', 'for', 'with', 'this', 'that', 'from'}:
            action_words.append(word)
    
    if action_words:
        return ' '.join(action_words[:3])
    return "deployment"


def build_signal_insight(signal: Dict[str, Any], date: str = None) -> SignalInsight:
    """Extract structural implication from a signal."""
    signal_id = signal.get('signal_id', '')
    signal_name = signal.get('name', '')
    
    profile = signal.get('profile', {})
    entities = profile.get('top_entities', [])
    buckets = profile.get('top_buckets', [])
    example_titles = profile.get('example_titles', [])
    key_insight = profile.get('key_insight', '')
    
    metrics = signal.get('metrics', {})
    velocity = metrics.get('velocity', 1.0)
    confidence = metrics.get('confidence', 0.5)
    status = signal.get('status', 'weak_signal')
    
    validation = signal.get('validation', {})
    corroborating_sources = list(validation.get('corroborating_sources', {}).keys())
    
    analysis_text = ' '.join([
        signal_name,
        key_insight,
        ' '.join(example_titles[:3]),
        ' '.join(buckets),
    ]).lower()
    
    insight_text = None
    for pattern, template in INSIGHT_PATTERNS:
        if re.search(pattern, analysis_text):
            mechanism = extract_mechanism_from_text(analysis_text)
            insight_text = template.format(mechanism=mechanism)
            break
    
    if not insight_text:
        if buckets:
            bucket_phrase = buckets[0].replace('-', ' ')
            insight_text = f"AI {bucket_phrase} landscape evolving"
        else:
            insight_text = "AI ecosystem dynamics shifting"
    
    insight_text = clean_trend_name(insight_text)
    if not insight_text:
        insight_text = "AI market dynamics evolving"
    
    insight_text = insight_text.capitalize()
    
    return SignalInsight(
        signal_id=signal_id,
        signal_name=signal_name,
        date=date or signal.get('last_seen_date', ''),
        insight_text=insight_text,
        entities=entities[:5],
        buckets=buckets[:3],
        velocity=velocity,
        confidence=confidence,
        status=status,
        corroborating_sources=corroborating_sources,
    )


def build_insights_from_signals(signals: List[Dict[str, Any]], date: str = None) -> List[SignalInsight]:
    """Build insights from a list of signals."""
    insights = []
    
    for signal in signals:
        status = signal.get('status', 'weak_signal')
        if status in ('dead', 'fading'):
            continue
        
        try:
            insight = build_signal_insight(signal, date)
            insights.append(insight)
        except Exception as e:
            logger.warning(f"Failed to build insight for signal {signal.get('signal_id')}: {e}")
    
    return insights


# =============================================================================
# EMBEDDING HELPER
# =============================================================================

class ConceptEmbedder:
    """Embed insight texts for concept clustering."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.available = EMBEDDINGS_AVAILABLE
        self.model = None
        self.model_name = model_name
        
        if self.available:
            try:
                logger.info(f"Loading embedding model for meta-signals: {model_name}")
                self.model = SentenceTransformer(model_name)
            except Exception as e:
                logger.warning(f"Failed to load embedding model: {e}")
                self.available = False
    
    def embed_insight(self, insight: SignalInsight) -> Optional[List[float]]:
        """Embed an insight's text."""
        if not self.available or not self.model:
            return None
        
        text = insight.insight_text
        if not text:
            return None
        
        try:
            embedding = self.model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
            return [round(float(x), EMBEDDING_DECIMALS) for x in embedding]
        except Exception as e:
            logger.warning(f"Embedding failed: {e}")
            return None
    
    def embed_batch(self, insights: List[SignalInsight]) -> List[SignalInsight]:
        """Embed all insights and attach embeddings."""
        if not self.available or not self.model:
            return insights
        
        texts = [i.insight_text for i in insights]
        
        try:
            embeddings = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
            
            for i, emb in enumerate(embeddings):
                insights[i].embedding = [round(float(x), EMBEDDING_DECIMALS) for x in emb]
        except Exception as e:
            logger.warning(f"Batch embedding failed: {e}")
        
        return insights
    
    def cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        
        if EMBEDDINGS_AVAILABLE and np is not None:
            a = np.array(vec_a)
            b = np.array(vec_b)
            dot = np.dot(a, b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return float(dot / (norm_a * norm_b))
        else:
            dot = sum(a * b for a, b in zip(vec_a, vec_b))
            norm_a = math.sqrt(sum(a * a for a in vec_a))
            norm_b = math.sqrt(sum(b * b for b in vec_b))
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)
    
    def compute_centroid(self, embeddings: List[List[float]]) -> Optional[List[float]]:
        """Compute centroid of embeddings."""
        if not embeddings:
            return None
        
        if EMBEDDINGS_AVAILABLE and np is not None:
            arr = np.array(embeddings)
            centroid = np.mean(arr, axis=0)
            norm = np.linalg.norm(centroid)
            if norm > 0:
                centroid = centroid / norm
            return [round(float(x), EMBEDDING_DECIMALS) for x in centroid]
        else:
            n = len(embeddings)
            dim = len(embeddings[0])
            centroid = [sum(e[i] for e in embeddings) / n for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in centroid))
            if norm > 0:
                centroid = [x / norm for x in centroid]
            return [round(x, EMBEDDING_DECIMALS) for x in centroid]


# =============================================================================
# CONCEPT CLUSTERING
# =============================================================================

class UnionFind:
    """Union-Find for transitive clustering."""
    
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n
    
    def find(self, x: int) -> int:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
    
    def union(self, x: int, y: int) -> None:
        px, py = self.find(x), self.find(y)
        if px == py:
            return
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1
    
    def get_clusters(self) -> Dict[int, List[int]]:
        clusters = defaultdict(list)
        for i in range(len(self.parent)):
            clusters[self.find(i)].append(i)
        return dict(clusters)


def compute_insight_overlap(i1: SignalInsight, i2: SignalInsight) -> Dict[str, Any]:
    """Compute overlap between two insights."""
    e1 = set(e.lower() for e in i1.entities)
    e2 = set(e.lower() for e in i2.entities)
    entity_shared = e1 & e2
    entity_union = e1 | e2
    entity_overlap = len(entity_shared) / len(entity_union) if entity_union else 0.0
    
    b1 = set(b.lower() for b in i1.buckets)
    b2 = set(b.lower() for b in i2.buckets)
    bucket_shared = b1 & b2
    bucket_union = b1 | b2
    bucket_overlap = len(bucket_shared) / len(bucket_union) if bucket_union else 0.0
    
    return {
        'entity_overlap': entity_overlap,
        'entity_shared': list(entity_shared),
        'bucket_overlap': bucket_overlap,
        'bucket_shared': list(bucket_shared),
        'different_entities': len(e1 - e2) > 0 or len(e2 - e1) > 0,
    }


def cluster_insights(
    insights: List[SignalInsight],
    embedder: ConceptEmbedder = None,
    similarity_threshold: float = CONCEPT_SIMILARITY_THRESHOLD,
) -> Tuple[List[List[int]], Dict[Tuple[int, int], Dict]]:
    """Cluster insights into conceptual groups."""
    n = len(insights)
    if n < MIN_SUPPORTING_SIGNALS:
        return [], {}
    
    uf = UnionFind(n)
    merge_info = {}
    
    for i in range(n):
        for j in range(i + 1, n):
            similarity = 0.0
            
            if embedder and insights[i].embedding and insights[j].embedding:
                similarity = embedder.cosine_similarity(
                    insights[i].embedding,
                    insights[j].embedding
                )
            
            overlap = compute_insight_overlap(insights[i], insights[j])
            
            if similarity == 0:
                similarity = 0.5 * overlap['entity_overlap'] + 0.5 * overlap['bucket_overlap']
            
            if similarity >= similarity_threshold:
                uf.union(i, j)
                merge_info[(i, j)] = {
                    'similarity': similarity,
                    **overlap,
                }
    
    cluster_dict = uf.get_clusters()
    clusters = [indices for indices in cluster_dict.values() if len(indices) >= MIN_SUPPORTING_SIGNALS]
    
    return clusters, merge_info


def check_diversity_requirement(insights: List[SignalInsight]) -> Tuple[bool, int, int]:
    """Check if insights meet diversity requirement."""
    all_entities = set()
    all_buckets = set()
    
    for insight in insights:
        all_entities.update(e.lower() for e in insight.entities)
        all_buckets.update(b.lower() for b in insight.buckets)
    
    entity_diversity = len(all_entities)
    bucket_diversity = len(all_buckets)
    
    meets = (entity_diversity >= MIN_ENTITY_DIVERSITY or 
             bucket_diversity >= MIN_BUCKET_DIVERSITY)
    
    return meets, entity_diversity, bucket_diversity


# =============================================================================
# META-SIGNAL SYNTHESIS
# =============================================================================

def derive_maturity_stage(insights: List[SignalInsight]) -> str:
    """Derive meta-signal maturity from supporting signals' states."""
    max_priority = -1
    
    for insight in insights:
        status = insight.status
        priority = MATURITY_PRIORITY.get(status, 0)
        if priority > max_priority:
            max_priority = priority
    
    if max_priority >= 4:
        return 'established'
    elif max_priority >= 3:
        return 'trending'
    elif max_priority >= 2:
        return 'emerging'
    else:
        return 'weak'


def compute_meta_acceleration(insights: List[SignalInsight]) -> float:
    """Compute average velocity change (acceleration) across signals."""
    if not insights:
        return 0.0
    
    velocities = [i.velocity for i in insights]
    avg_velocity = sum(velocities) / len(velocities)
    
    return avg_velocity - 1.0


def name_meta_signal(insights: List[SignalInsight]) -> str:
    """Generate a human-readable trend name."""
    bucket_counts = Counter()
    term_counts = Counter()
    
    for insight in insights:
        for bucket in insight.buckets:
            cleaned = bucket.replace('-', ' ').lower()
            if not is_company_or_model(cleaned):
                bucket_counts[cleaned] += 1
        
        words = insight.insight_text.lower().split()
        for word in words:
            if len(word) > 3 and not is_company_or_model(word):
                if word not in {'the', 'and', 'for', 'with', 'this', 'that', 'from', 'into', 'over'}:
                    term_counts[word] += 1
    
    name_parts = []
    name_parts.append("AI")
    
    if bucket_counts:
        top_bucket = bucket_counts.most_common(1)[0][0]
        name_parts.append(top_bucket)
    
    action_words = ['adoption', 'deployment', 'development', 'integration', 'market', 
                    'investment', 'competition', 'growth', 'shift', 'evolution']
    for action in action_words:
        if term_counts.get(action, 0) > 0:
            name_parts.append(action)
            break
    
    for insight in insights:
        if insight.velocity > 1.5:
            name_parts.append('accelerating')
            break
    
    if 'accelerating' not in name_parts:
        name_parts.append('evolving')
    
    name = ' '.join(name_parts[:6])
    name = sanitize_name_with_registry(name)
    
    return name.title()


def build_meta_description(insights: List[SignalInsight]) -> str:
    """Build a description for the meta-signal."""
    if not insights:
        return ""
    
    unique_insights = list(set(i.insight_text for i in insights))[:3]
    
    if len(unique_insights) == 1:
        return unique_insights[0]
    else:
        return ". ".join(unique_insights)


def synthesize_meta_signals(
    insights: List[SignalInsight],
    embedder: ConceptEmbedder = None,
    current_date: str = None,
    source_cfg: Dict[str, Any] = None,
) -> List[MetaSignal]:
    """
    Synthesize meta-signals from insights.
    
    v2.6 Pipeline:
    1. Cluster insights
    2. Create initial meta-signals with concept_slug
    3. Apply specificity gate (rename generic names, respect name_frozen)
    4. Deduplicate similar metas (with merge_reason)
    5. Build hierarchy (with hierarchy_reason)
    6. Apply confidence hardening (with independence)
    """
    if len(insights) < MIN_SUPPORTING_SIGNALS:
        logger.info(f"Not enough insights ({len(insights)}) for meta-signal synthesis")
        return []
    
    if source_cfg is None:
        source_cfg = load_source_categories()
    
    # Step 1: Cluster insights
    clusters, merge_info = cluster_insights(insights, embedder)
    
    logger.info(f"Found {len(clusters)} concept clusters from {len(insights)} insights")
    
    # Step 2: Create initial meta-signals
    meta_signals = []
    
    for cluster_indices in clusters:
        grouped_insights = [insights[i] for i in cluster_indices]
        
        meets_diversity, entity_div, bucket_div = check_diversity_requirement(grouped_insights)
        
        if not meets_diversity:
            logger.debug(f"Cluster rejected: insufficient diversity (entities={entity_div}, buckets={bucket_div})")
            continue
        
        meta_id = generate_meta_id([i.insight_text for i in grouped_insights])
        concept_name = name_meta_signal(grouped_insights)
        description = build_meta_description(grouped_insights)
        maturity = derive_maturity_stage(grouped_insights)
        acceleration = compute_meta_acceleration(grouped_insights)
        
        dates = [i.date for i in grouped_insights if i.date]
        first_seen = min(dates) if dates else current_date or ''
        last_updated = max(dates) if dates else current_date or ''
        
        centroid = None
        if embedder:
            embeddings = [i.embedding for i in grouped_insights if i.embedding]
            if embeddings:
                centroid = embedder.compute_centroid(embeddings)
        
        # Collect entities for slug
        all_entities = []
        for insight in grouped_insights:
            all_entities.extend(insight.entities)
        
        meta = MetaSignal(
            meta_id=meta_id,
            concept_name=concept_name,
            description=description,
            supporting_signals=[i.signal_id for i in grouped_insights],
            supporting_insights=grouped_insights,
            first_seen=first_seen,
            last_updated=last_updated,
            maturity_stage=maturity,
            concept_confidence=0.0,
            acceleration=acceleration,
            entity_diversity=entity_div,
            bucket_diversity=bucket_div,
            centroid_embedding=centroid,
        )
        
        meta_signals.append(meta)
        
        logger.debug(f"Initial meta: '{concept_name}' (maturity={maturity}, signals={len(grouped_insights)})")
    
    if not meta_signals:
        logger.info("No meta-signals created after diversity check")
        return []
    
    # Step 3: Apply specificity gate (determines mechanism)
    for i, meta in enumerate(meta_signals):
        meta_signals[i] = apply_specificity_gate(meta)
    
    # v2.6: Generate concept_slug after mechanism is determined
    for meta in meta_signals:
        meta.concept_slug = generate_slug_for_meta(meta)
    
    renamed_count = sum(1 for m in meta_signals if m.naming_reason and m.naming_reason.was_generic)
    logger.info(f"Specificity gate: {renamed_count}/{len(meta_signals)} renamed")
    
    # Step 4: Deduplicate
    meta_signals = dedupe_meta_signals(meta_signals, embedder)
    
    # Step 5: Build hierarchy
    meta_signals = build_hierarchy(meta_signals, embedder)
    
    # Step 6: Apply confidence hardening
    for i, meta in enumerate(meta_signals):
        meta_signals[i] = apply_confidence_hardening(meta, source_cfg)
    
    # Final sort by confidence
    meta_signals.sort(key=lambda m: m.concept_confidence, reverse=True)
    
    # Log final results
    for meta in meta_signals:
        logger.info(
            f"Meta-signal: '{meta.concept_name}' (slug={meta.concept_slug}) "
            f"(maturity={meta.maturity_stage}, conf={meta.concept_confidence:.2f}, "
            f"signals={len(meta.supporting_signals)}, days={meta.persistence_days}, "
            f"indep={meta.independence_score:.2f}, status={meta.validation_status}, "
            f"frozen={meta.name_frozen})"
        )
    
    return meta_signals


# =============================================================================
# META-SIGNAL ENGINE
# =============================================================================

class MetaSignalEngine:
    """
    Meta-Signal Engine for detecting structural trends from signals.
    
    v2.6 Features:
    - Independence scoring using source independence levels
    - Stable concept_slug for rename churn prevention
    - Name freezing after persistence + confidence thresholds
    - Structured merge_reason and hierarchy_reason
    - Enhanced validation using independence_score
    """
    
    def __init__(
        self,
        output_dir: Path = None,
        use_embeddings: bool = True,
        source_categories_path: Path = None,
    ):
        """Initialize meta-signal engine."""
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "data" / "meta_signals"
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.embedder = None
        if use_embeddings:
            self.embedder = ConceptEmbedder()
            if not self.embedder.available:
                logger.info("Embeddings unavailable, using overlap-only mode")
        
        self.source_cfg = load_source_categories(source_categories_path)
    
    def output_file(self, date: str) -> Path:
        return self.output_dir / f"meta_signals_{date}.json"
    
    def process_signals(
        self,
        signals: List[Dict[str, Any]],
        date: str = None,
    ) -> Dict[str, Any]:
        """Process signals into meta-signals."""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        logger.info(f"Processing {len(signals)} signals for meta-signal synthesis")
        
        insights = build_insights_from_signals(signals, date)
        logger.info(f"Built {len(insights)} insights from active signals")
        
        if self.embedder and self.embedder.available:
            insights = self.embedder.embed_batch(insights)
            logger.info("Embedded insights for concept clustering")
        
        meta_signals = synthesize_meta_signals(
            insights, 
            self.embedder, 
            date,
            self.source_cfg,
        )
        
        result = {
            'date': date,
            'generated_at': datetime.now().isoformat(),
            'version': '2.6',
            'stats': {
                'input_signals': len(signals),
                'insights_generated': len(insights),
                'meta_signals_found': len(meta_signals),
                'review_required': sum(1 for m in meta_signals if m.review_required),
                'validated': sum(1 for m in meta_signals if m.validation_status == 'validated'),
                'weakly_validated': sum(1 for m in meta_signals if m.validation_status == 'weakly_validated'),
                'name_frozen': sum(1 for m in meta_signals if m.name_frozen),
            },
            'meta_signals': [m.to_dict(include_insights=True) for m in meta_signals],
        }
        
        with open(self.output_file(date), 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved meta-signals to {self.output_file(date)}")
        
        return result
    
    def process_from_tracker(
        self,
        tracker,
        date: str = None,
    ) -> Dict[str, Any]:
        """Process signals directly from a SignalTracker instance."""
        active = tracker.get_active_signals(exclude_dead=True)
        signals = [s.to_dict(include_embedding=False) for s in active]
        
        return self.process_signals(signals, date)


# =============================================================================
# TESTS (inline for quick validation)
# =============================================================================

def _test_signal_insight_serialization():
    """Test SignalInsight serialization."""
    insight = SignalInsight(
        signal_id='sig123',
        signal_name='Pricing Signal',
        date='2026-02-09',
        insight_text='AI pricing dynamics shifting in market',
        entities=['company_a'],
        buckets=['pricing'],
        velocity=1.5,
        confidence=0.7,
        status='emerging',
        source_category='financial',
        corroborating_sources=['news', 'sec'],
    )
    
    d = insight.to_dict()
    restored = SignalInsight.from_dict(d)
    
    assert restored.signal_id == insight.signal_id
    assert restored.insight_text == insight.insight_text
    assert restored.source_category == 'financial'
    
    print("[PASS] _test_signal_insight_serialization")


def _test_meta_signal_serialization():
    """Test MetaSignal serialization with v2.6 fields."""
    meta = MetaSignal(
        meta_id='meta123',
        concept_name='Pricing Pressure Rising',
        description='Test description',
        supporting_signals=['sig1', 'sig2'],
        maturity_stage='emerging',
        concept_confidence=0.55,
        mechanism='pricing-monetization',
        naming_reason=NamingReason(was_generic=True, original_name='AI Market'),
        merged_from=['meta456'],
        persistence_days=3,
        persistence_factor=0.10,
        category_diversity=CategoryDiversity(categories=['technical', 'financial'], category_count=2, weighted_diversity=2.0),
        validation_status='validated',
        confidence_breakdown=ConfidenceBreakdown(base=0.5, independence=0.09, final=0.55),
        concept_slug='a91c44e21fa2',
        name_frozen=True,
        independence_score=0.82,
        merge_reason=MergeReason(centroid_similarity=0.84, signal_overlap=0.47),
        hierarchy_reason=HierarchyReason(centroid_similarity=0.73, signal_overlap=0.31),
    )
    
    d = meta.to_dict()
    restored = MetaSignal.from_dict(d)
    
    assert restored.concept_slug == 'a91c44e21fa2'
    assert restored.name_frozen == True
    assert restored.independence_score == 0.82
    assert restored.merge_reason.centroid_similarity == 0.84
    assert restored.hierarchy_reason.signal_overlap == 0.31
    
    print("[PASS] _test_meta_signal_serialization")


def _test_concept_slug_generation():
    """Test stable concept slug generation."""
    slug1 = generate_concept_slug(['openai', 'anthropic'], 'pricing-monetization', '2026-02-01')
    slug2 = generate_concept_slug(['anthropic', 'openai'], 'pricing-monetization', '2026-02-01')
    
    # Should be the same (sorted entities)
    assert slug1 == slug2
    assert len(slug1) == 12
    
    # Different mechanism = different slug
    slug3 = generate_concept_slug(['openai', 'anthropic'], 'compute-hardware', '2026-02-01')
    assert slug3 != slug1
    
    print("[PASS] _test_concept_slug_generation")


def _test_independence_score():
    """Test independence score computation."""
    cat_div = CategoryDiversity(categories=['technical', 'financial'], category_count=2, weighted_diversity=2.0)
    
    # Mock source config
    source_cfg = {
        'categories': {
            'technical': {'weight': 1.0, 'independence_level': 'high'},
            'financial': {'weight': 1.0, 'independence_level': 'high'},
        }
    }
    
    score = compute_independence_score(cat_div, source_cfg)
    
    # Both high independence → should be 1.0
    assert score == 1.0
    
    print("[PASS] _test_independence_score")


def _test_name_freeze():
    """Test name freeze logic."""
    # Below thresholds
    assert should_freeze_name(2, 0.55, False) == False
    
    # Above thresholds
    assert should_freeze_name(3, 0.65, False) == True
    
    # Already frozen
    assert should_freeze_name(1, 0.30, True) == True
    
    print("[PASS] _test_name_freeze")


def _test_validation_status_v26():
    """Test v2.6 validation status with independence."""
    cat_div = CategoryDiversity(categories=['technical'], category_count=1, weighted_diversity=1.0)
    
    # High independence single category → validated
    status = compute_validation_status_v26(cat_div, 0.80)
    assert status == 'validated'
    
    # Medium independence single category → weakly_validated
    status = compute_validation_status_v26(cat_div, 0.65)
    assert status == 'weakly_validated'
    
    # High weighted diversity → validated
    cat_div2 = CategoryDiversity(categories=['technical', 'financial'], category_count=2, weighted_diversity=1.8)
    status = compute_validation_status_v26(cat_div2, 0.50)
    assert status == 'validated'
    
    print("[PASS] _test_validation_status_v26")


def run_tests():
    """Run all unit tests."""
    print("\n=== META-SIGNAL ENGINE v2.6 TESTS ===\n")
    
    _test_signal_insight_serialization()
    _test_meta_signal_serialization()
    _test_concept_slug_generation()
    _test_independence_score()
    _test_name_freeze()
    _test_validation_status_v26()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
