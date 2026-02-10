from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class Document(BaseModel):
    id: str
    source_id: str
    url_or_path: Optional[str] = None
    published_at: Optional[datetime] = None
    language: Optional[str] = None
    content: str
    credibility: Optional[float] = None
    hash: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RiskSignal(BaseModel):
    id: str
    document_id: str
    title: str
    signal_type: Optional[str] = None
    evidence_span: Optional[str] = None
    impact: float
    relevance: float
    recency: float
    credibility: float
    risk_score: float
    entities: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    published_date: Optional[datetime] = None
    summary: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Cluster(BaseModel):
    id: str
    label: str
    member_signal_ids: List[str]
    theme_keywords: List[str] = Field(default_factory=list)
    centroid_ref: Optional[str] = None


class EntityMention(BaseModel):
    """
    Tracks entity activity for a single week.
    Represents weekly facts: how many times an entity appeared and with what scores.
    """
    entity_id: str  # Normalized form (e.g., "openai")
    entity_name: str  # Display form (e.g., "OpenAI")
    entity_type: Literal["company", "model", "topic", "person"]
    week_id: str  # Format: "2025-W01"
    mention_count: int  # Number of articles mentioning this entity
    avg_score: float  # Average 5D score across articles
    max_score: float  # Highest score among articles
    total_score: float  # Sum of all scores (intensity metric)
    article_ids: List[str]  # References to articles
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TrendSignal(BaseModel):
    """
    Represents a detected trend or breakout moment.
    Captures discoveries: when an entity shows unusual activity patterns.
    """
    entity_id: str  # Normalized form
    entity_name: str  # Display form
    entity_type: Literal["company", "model", "topic", "person"]
    signal_type: Literal["velocity_spike", "new_entity", "score_surge", "combo"]
    confidence: float  # 0-1, clamped to min_confidence threshold

    # Time context
    current_week: str  # Week being analyzed
    baseline_weeks: int  # Number of weeks in baseline (e.g., 4)

    # Baseline metrics
    baseline_mentions: float  # Average mentions per week in baseline
    baseline_score: Optional[float]  # Average score in baseline (None if no baseline)
    weeks_observed: int  # How many weeks entity appeared in baseline

    # Current metrics
    current_mentions: int
    current_score: Optional[float]

    # Deltas
    velocity_change: float  # Percentage change: (current - baseline) / baseline
    score_delta: Optional[float]  # Absolute change: current_score - baseline_score

    # Evidence
    evidence_article_ids: List[str]
    evidence_titles: List[str]  # For display (separate from IDs)

    created_at: datetime = Field(default_factory=datetime.utcnow)


