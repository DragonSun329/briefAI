"""
Signal Analysis Data Models

Multi-dimensional signal tracking for AI trend analysis.
Each signal category measures a different aspect of significance:
- Technical: Developer adoption, research momentum
- Company: Market position, organizational strength
- Financial: Capital flows, investor confidence
- Product: End-user demand, product-market fit
- Media: Public perception, narrative, hype

Key insight: Signals should NOT be mixed. Divergences between
signal types reveal opportunities and risks.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field
import uuid


class EntityType(str, Enum):
    """Types of entities we track across signals."""
    COMPANY = "company"         # OpenAI, Anthropic
    TECHNOLOGY = "technology"   # GPT-4, LangChain, PyTorch
    CONCEPT = "concept"         # AI Safety, AGI, Alignment
    PERSON = "person"           # Sam Altman, Dario Amodei


class SignalCategory(str, Enum):
    """
    Five distinct dimensions of AI significance.
    Each category has its own scoring methodology.
    """
    TECHNICAL = "technical"           # GitHub, HuggingFace, Papers
    COMPANY_PRESENCE = "company"      # Crunchbase, LinkedIn
    FINANCIAL = "financial"           # SEC, Funding rounds
    PRODUCT_TRACTION = "product"      # ProductHunt, App stores
    MEDIA_SENTIMENT = "media"         # News pipeline


class Entity(BaseModel):
    """
    Canonical entity tracked across all signal types.
    This is the "master record" for cross-signal correlation.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    canonical_id: str             # Normalized ID (e.g., "openai")
    name: str                     # Display name (e.g., "OpenAI")
    entity_type: EntityType

    # Aliases for entity resolution
    aliases: List[str] = Field(default_factory=list)  # ["Open AI", "open-ai"]

    # Metadata
    description: Optional[str] = None
    website: Optional[str] = None
    founded_date: Optional[str] = None
    headquarters: Optional[str] = None

    # Relationships (for future use)
    parent_entity: Optional[str] = None      # For subsidiaries/models
    related_entities: List[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SignalSource(BaseModel):
    """
    Configuration for a specific data source within a signal category.
    """
    id: str                           # e.g., "github_trending", "crunchbase_rank"
    name: str                         # Display name
    category: SignalCategory
    url: Optional[str] = None

    # Update characteristics
    update_frequency: Literal["hourly", "daily", "weekly", "monthly", "quarterly"] = "daily"
    latency_hours: int = 0            # How delayed is this data typically?

    # Reliability
    confidence_base: float = 0.7      # Base confidence score (0-1)
    requires_api_key: bool = False
    enabled: bool = True


class SignalObservation(BaseModel):
    """
    A single observation/measurement for an entity from a specific source.
    This is the "fact" layer - raw data before scoring.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_id: str                    # FK to Entity.id
    source_id: str                    # FK to SignalSource.id
    category: SignalCategory

    # Time context
    observed_at: datetime = Field(default_factory=datetime.utcnow)
    data_timestamp: Optional[datetime] = None  # When the data is from (may be historical)

    # Raw metrics (source-specific)
    raw_value: Optional[float] = None  # Primary metric (stars, rank, funding, etc.)
    raw_value_unit: Optional[str] = None  # "count", "usd", "rank", "percent"

    # Additional raw data
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    # Examples:
    # GitHub: {"stars": 5000, "forks": 800, "language": "Python"}
    # Crunchbase: {"rank": 150, "employee_count": 500, "funding_total": 100000000}
    # SEC: {"filing_type": "S-1", "filing_date": "2024-01-15"}

    # Confidence in this specific observation
    confidence: float = 1.0           # May be lowered for scraped vs API data

    created_at: datetime = Field(default_factory=datetime.utcnow)


class SignalScore(BaseModel):
    """
    Normalized score for a signal observation.
    Transforms raw values into comparable 0-100 scale per signal type.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    observation_id: Optional[str] = None  # FK to SignalObservation.id (optional for direct scoring)
    entity_id: str                    # FK to Entity.id
    source_id: str = "direct"         # Default for direct scoring
    category: SignalCategory

    # Normalized score (0-100 scale within category)
    score: float                      # Normalized score
    percentile: Optional[float] = None  # Percentile rank within category

    # Change detection
    score_delta_7d: Optional[float] = None   # Change vs 7 days ago
    score_delta_30d: Optional[float] = None  # Change vs 30 days ago

    # Context
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)


class SignalProfile(BaseModel):
    """
    Unified view of an entity across all signal types.
    This is the "insight" layer for CEO dashboard.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_id: str
    entity_name: str
    entity_type: EntityType

    # Snapshot timestamp
    as_of: datetime = Field(default_factory=datetime.utcnow)

    # Per-category scores (0-100)
    technical_score: Optional[float] = None
    company_score: Optional[float] = None
    financial_score: Optional[float] = None
    product_score: Optional[float] = None
    media_score: Optional[float] = None

    # Composite score (weighted average of available signals)
    composite_score: float = 0.0

    # Per-category confidence (0-1)
    technical_confidence: float = 0.0
    company_confidence: float = 0.0
    financial_confidence: float = 0.0
    product_confidence: float = 0.0
    media_confidence: float = 0.0

    # Momentum (change over time, -100 to +100)
    momentum_7d: Optional[float] = None
    momentum_30d: Optional[float] = None

    # Data freshness per category
    data_freshness: Dict[str, datetime] = Field(default_factory=dict)
    # {"technical": "2025-01-05T...", "financial": "2024-12-31T..."}

    # Evidence - top contributing signal IDs
    top_signals: List[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    def get_radar_data(self) -> List[Dict[str, Any]]:
        """Get data formatted for radar/spider chart visualization."""
        return [
            {"axis": "Technical", "value": self.technical_score or 0, "confidence": self.technical_confidence},
            {"axis": "Company", "value": self.company_score or 0, "confidence": self.company_confidence},
            {"axis": "Financial", "value": self.financial_score or 0, "confidence": self.financial_confidence},
            {"axis": "Product", "value": self.product_score or 0, "confidence": self.product_confidence},
            {"axis": "Media", "value": self.media_score or 0, "confidence": self.media_confidence},
        ]

    def get_score_dict(self) -> Dict[str, Optional[float]]:
        """Get all scores as a dictionary."""
        return {
            SignalCategory.TECHNICAL: self.technical_score,
            SignalCategory.COMPANY_PRESENCE: self.company_score,
            SignalCategory.FINANCIAL: self.financial_score,
            SignalCategory.PRODUCT_TRACTION: self.product_score,
            SignalCategory.MEDIA_SENTIMENT: self.media_score,
        }


class DivergenceType(str, Enum):
    """Types of signal divergences we detect."""
    TECHNICAL_VS_FINANCIAL = "technical_vs_financial"
    FINANCIAL_VS_PRODUCT = "financial_vs_product"
    TECHNICAL_VS_MEDIA = "technical_vs_media"
    PRODUCT_VS_MEDIA = "product_vs_media"
    FUNDING_SPIKE_NO_NEWS = "funding_spike_no_news"
    MEDIA_HYPE_NO_SUBSTANCE = "media_hype_no_substance"


class DivergenceInterpretation(str, Enum):
    """How to interpret a divergence."""
    OPPORTUNITY = "opportunity"
    RISK = "risk"
    ANOMALY = "anomaly"
    NEUTRAL = "neutral"


class SignalDivergence(BaseModel):
    """
    Detected divergence between signal types.
    Key insight: when signals disagree, there may be opportunity or risk.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_id: str
    entity_name: str

    # Divergence details
    divergence_type: DivergenceType

    # The diverging signals
    high_signal_category: SignalCategory
    high_signal_score: float
    low_signal_category: SignalCategory
    low_signal_score: float

    # Magnitude and confidence
    divergence_magnitude: float       # 0-100, how divergent
    confidence: float                 # 0-1

    # Interpretation
    interpretation: DivergenceInterpretation
    interpretation_rationale: str

    # Time context
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    first_detected_at: Optional[datetime] = None  # If recurring
    resolved_at: Optional[datetime] = None

    # Evidence
    evidence_signals: List[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# Configuration Models
# ============================================================================

class CategoryWeights(BaseModel):
    """Weights for composite score calculation."""
    technical: float = 0.20
    company: float = 0.15
    financial: float = 0.25
    product: float = 0.20
    media: float = 0.20

    def get_weight(self, category: SignalCategory) -> float:
        """Get weight for a specific category."""
        mapping = {
            SignalCategory.TECHNICAL: self.technical,
            SignalCategory.COMPANY_PRESENCE: self.company,
            SignalCategory.FINANCIAL: self.financial,
            SignalCategory.PRODUCT_TRACTION: self.product,
            SignalCategory.MEDIA_SENTIMENT: self.media,
        }
        return mapping.get(category, 0.2)


class DivergenceThresholds(BaseModel):
    """Thresholds for detecting divergences (score difference required)."""
    technical_vs_financial: float = 30.0
    financial_vs_product: float = 25.0
    technical_vs_media: float = 25.0
    product_vs_media: float = 20.0

    def get_threshold(self, divergence_type: DivergenceType) -> float:
        """Get threshold for a specific divergence type."""
        mapping = {
            DivergenceType.TECHNICAL_VS_FINANCIAL: self.technical_vs_financial,
            DivergenceType.FINANCIAL_VS_PRODUCT: self.financial_vs_product,
            DivergenceType.TECHNICAL_VS_MEDIA: self.technical_vs_media,
            DivergenceType.PRODUCT_VS_MEDIA: self.product_vs_media,
        }
        return mapping.get(divergence_type, 25.0)


class SignalConfig(BaseModel):
    """Master configuration for signal analysis."""
    category_weights: CategoryWeights = Field(default_factory=CategoryWeights)
    divergence_thresholds: DivergenceThresholds = Field(default_factory=DivergenceThresholds)
    min_confidence: float = 0.5       # Minimum confidence for divergence detection
    freshness_half_life_hours: Dict[str, int] = Field(default_factory=lambda: {
        "hourly": 24,
        "daily": 72,
        "weekly": 168,
        "monthly": 720,
        "quarterly": 2160,
    })


# ============================================================================
# Helper Functions
# ============================================================================

def normalize_entity_id(name: str) -> str:
    """
    Normalize entity name to canonical ID.
    "OpenAI" -> "openai"
    "GPT-4" -> "gpt-4"
    """
    import re

    # Lowercase
    normalized = name.lower().strip()

    # Remove common suffixes
    suffixes = [", inc.", ", inc", " inc.", " inc", ", llc", " llc",
                ", ltd", " ltd", ", corp", " corp", " corporation"]
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]

    # Replace spaces and special chars with hyphens
    normalized = re.sub(r'[^\w\-]', '-', normalized)
    normalized = re.sub(r'-+', '-', normalized)  # Collapse multiple hyphens
    normalized = normalized.strip('-')

    return normalized


def detect_entity_type(name: str, source_category: Optional[SignalCategory] = None) -> EntityType:
    """
    Detect entity type based on name patterns and source.
    """
    name_lower = name.lower()

    # Source-based hints
    if source_category == SignalCategory.COMPANY_PRESENCE:
        return EntityType.COMPANY
    if source_category == SignalCategory.TECHNICAL:
        # GitHub repos and HF models are technologies
        if "/" in name:  # repo or model format
            return EntityType.TECHNOLOGY

    # Pattern-based detection
    tech_patterns = [
        "gpt", "llama", "bert", "transformer", "diffusion",
        "pytorch", "tensorflow", "langchain", "huggingface",
        "-model", "-ai", "v1", "v2", "v3", "-base", "-large"
    ]
    for pattern in tech_patterns:
        if pattern in name_lower:
            return EntityType.TECHNOLOGY

    concept_patterns = [
        "safety", "alignment", "agi", "asi", "regulation",
        "ethics", "bias", "fairness", "interpretability"
    ]
    for pattern in concept_patterns:
        if pattern in name_lower:
            return EntityType.CONCEPT

    # Person detection (title patterns)
    person_indicators = ["ceo", "cto", "founder", "researcher", "professor"]
    # Note: More sophisticated person detection would need NER

    # Default to company for unrecognized entities
    return EntityType.COMPANY
