"""
Event Schemas for Trend Intelligence Platform

Defines ArticleEvent and TrendUpdateEvent for tracking
ingestion lineage and signal updates.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
import hashlib
import json
import uuid


class EventType(str, Enum):
    """Types of events in the system."""
    ARTICLE_INGESTED = "article_ingested"
    ARTICLE_PROCESSED = "article_processed"
    ARTICLE_DEDUPLICATED = "article_deduplicated"
    TREND_UPDATE = "trend_update"
    ALERT_TRIGGERED = "alert_triggered"
    SIGNAL_COMPUTED = "signal_computed"


class ProcessingStatus(str, Enum):
    """Processing status for articles."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    DEDUPLICATED = "deduplicated"


@dataclass
class ArticleEvent:
    """
    Ingested article before processing.

    Tracks the full lineage from scrape to signal contribution.
    """
    # Identity
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""  # e.g., "hackernews", "reddit", "rss"

    # Content
    url: str = ""
    canonical_url: str = ""  # Normalized URL for dedup
    title: str = ""
    content: str = ""
    summary: Optional[str] = None

    # Metadata
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    scraped_at: datetime = field(default_factory=datetime.now)

    # Deduplication
    simhash: Optional[str] = None
    content_hash: Optional[str] = None  # SHA256 of content
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None  # event_id of original

    # Processing state
    status: ProcessingStatus = ProcessingStatus.PENDING
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    # Extracted data
    entities: List[str] = field(default_factory=list)
    buckets: List[str] = field(default_factory=list)
    sentiment_score: Optional[float] = None
    relevance_score: Optional[float] = None

    # Cost tracking
    llm_tokens_used: int = 0
    llm_cost_usd: float = 0.0

    def compute_content_hash(self) -> str:
        """Compute SHA256 hash of content."""
        content = f"{self.title}\n{self.content}".encode('utf-8')
        self.content_hash = hashlib.sha256(content).hexdigest()
        return self.content_hash

    def canonicalize_url(self) -> str:
        """Normalize URL for deduplication."""
        import re
        from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

        url = self.url.lower().strip()

        # Remove tracking params
        tracking_params = {
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'ref', 'source', 'fbclid', 'gclid', 'mc_cid', 'mc_eid'
        }

        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        filtered_query = {k: v for k, v in query.items() if k not in tracking_params}

        # Rebuild URL
        self.canonical_url = urlunparse((
            parsed.scheme,
            parsed.netloc.replace('www.', ''),
            parsed.path.rstrip('/'),
            '',
            urlencode(filtered_query, doseq=True) if filtered_query else '',
            ''
        ))

        return self.canonical_url

    def mark_processing(self) -> None:
        """Mark article as currently processing."""
        self.status = ProcessingStatus.PROCESSING
        self.processing_started_at = datetime.now()

    def mark_completed(self) -> None:
        """Mark article as successfully processed."""
        self.status = ProcessingStatus.COMPLETED
        self.processing_completed_at = datetime.now()

    def mark_failed(self, error: str) -> None:
        """Mark article as failed with error message."""
        self.status = ProcessingStatus.FAILED
        self.processing_completed_at = datetime.now()
        self.error_message = error

    def mark_duplicate(self, original_id: str) -> None:
        """Mark article as duplicate of another."""
        self.is_duplicate = True
        self.duplicate_of = original_id
        self.status = ProcessingStatus.DEDUPLICATED

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "event_type": EventType.ARTICLE_INGESTED.value,
            "source": self.source,
            "url": self.url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "content_length": len(self.content),
            "summary": self.summary,
            "author": self.author,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
            "simhash": self.simhash,
            "content_hash": self.content_hash,
            "is_duplicate": self.is_duplicate,
            "duplicate_of": self.duplicate_of,
            "status": self.status.value,
            "processing_started_at": self.processing_started_at.isoformat() if self.processing_started_at else None,
            "processing_completed_at": self.processing_completed_at.isoformat() if self.processing_completed_at else None,
            "error_message": self.error_message,
            "entities": self.entities,
            "buckets": self.buckets,
            "sentiment_score": self.sentiment_score,
            "relevance_score": self.relevance_score,
            "llm_tokens_used": self.llm_tokens_used,
            "llm_cost_usd": self.llm_cost_usd,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArticleEvent":
        """Create from dictionary."""
        event = cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            source=data.get("source", ""),
            url=data.get("url", ""),
            canonical_url=data.get("canonical_url", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            summary=data.get("summary"),
            author=data.get("author"),
            simhash=data.get("simhash"),
            content_hash=data.get("content_hash"),
            is_duplicate=data.get("is_duplicate", False),
            duplicate_of=data.get("duplicate_of"),
            entities=data.get("entities", []),
            buckets=data.get("buckets", []),
            sentiment_score=data.get("sentiment_score"),
            relevance_score=data.get("relevance_score"),
            llm_tokens_used=data.get("llm_tokens_used", 0),
            llm_cost_usd=data.get("llm_cost_usd", 0.0),
        )

        if data.get("published_at"):
            event.published_at = datetime.fromisoformat(data["published_at"])
        if data.get("scraped_at"):
            event.scraped_at = datetime.fromisoformat(data["scraped_at"])
        if data.get("processing_started_at"):
            event.processing_started_at = datetime.fromisoformat(data["processing_started_at"])
        if data.get("processing_completed_at"):
            event.processing_completed_at = datetime.fromisoformat(data["processing_completed_at"])
        if data.get("status"):
            event.status = ProcessingStatus(data["status"])
        if data.get("error_message"):
            event.error_message = data["error_message"]

        return event


@dataclass
class TrendUpdateEvent:
    """
    Signal update for a bucket.

    Captures when and why a bucket's signal changed.
    """
    # Identity
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    bucket_id: str = ""
    signal_type: str = ""  # tms, ccs, nas, eis, pms, css

    # Values
    old_value: Optional[float] = None
    new_value: float = 0.0
    delta: float = 0.0
    delta_percent: Optional[float] = None

    # Smoothed values
    old_ewma: Optional[float] = None
    new_ewma: Optional[float] = None

    # Historical context
    percentile_12w: Optional[float] = None
    percentile_26w: Optional[float] = None
    z_score: Optional[float] = None

    # Timing
    triggered_at: datetime = field(default_factory=datetime.now)
    data_timestamp: Optional[datetime] = None  # When the underlying data was from

    # Lineage
    contributing_entities: List[str] = field(default_factory=list)
    source_events: List[str] = field(default_factory=list)  # ArticleEvent IDs
    source_count: int = 0

    # Metadata
    confidence: float = 0.0
    coverage: float = 0.0
    freshness: float = 1.0

    # Alert linkage
    triggered_alert: Optional[str] = None  # alert_id if this update triggered an alert

    def compute_delta(self) -> None:
        """Compute delta and delta_percent from old/new values."""
        if self.old_value is not None:
            self.delta = self.new_value - self.old_value
            if self.old_value != 0:
                self.delta_percent = (self.delta / self.old_value) * 100

    def is_significant_change(self, threshold: float = 5.0) -> bool:
        """Check if this update represents a significant change."""
        return abs(self.delta) >= threshold

    def get_direction(self) -> str:
        """Get trend direction."""
        if self.delta > 2:
            return "rising"
        elif self.delta < -2:
            return "falling"
        return "stable"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "event_type": EventType.TREND_UPDATE.value,
            "bucket_id": self.bucket_id,
            "signal_type": self.signal_type,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "delta": self.delta,
            "delta_percent": self.delta_percent,
            "old_ewma": self.old_ewma,
            "new_ewma": self.new_ewma,
            "percentile_12w": self.percentile_12w,
            "percentile_26w": self.percentile_26w,
            "z_score": self.z_score,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "data_timestamp": self.data_timestamp.isoformat() if self.data_timestamp else None,
            "contributing_entities": self.contributing_entities,
            "source_events": self.source_events,
            "source_count": self.source_count,
            "confidence": self.confidence,
            "coverage": self.coverage,
            "freshness": self.freshness,
            "triggered_alert": self.triggered_alert,
            "direction": self.get_direction(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrendUpdateEvent":
        """Create from dictionary."""
        event = cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            bucket_id=data.get("bucket_id", ""),
            signal_type=data.get("signal_type", ""),
            old_value=data.get("old_value"),
            new_value=data.get("new_value", 0.0),
            delta=data.get("delta", 0.0),
            delta_percent=data.get("delta_percent"),
            old_ewma=data.get("old_ewma"),
            new_ewma=data.get("new_ewma"),
            percentile_12w=data.get("percentile_12w"),
            percentile_26w=data.get("percentile_26w"),
            z_score=data.get("z_score"),
            contributing_entities=data.get("contributing_entities", []),
            source_events=data.get("source_events", []),
            source_count=data.get("source_count", 0),
            confidence=data.get("confidence", 0.0),
            coverage=data.get("coverage", 0.0),
            freshness=data.get("freshness", 1.0),
            triggered_alert=data.get("triggered_alert"),
        )

        if data.get("triggered_at"):
            event.triggered_at = datetime.fromisoformat(data["triggered_at"])
        if data.get("data_timestamp"):
            event.data_timestamp = datetime.fromisoformat(data["data_timestamp"])

        return event


@dataclass
class SignalComputedEvent:
    """
    Event emitted when a signal is computed for a bucket.

    Provides full lineage of signal computation.
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    bucket_id: str = ""
    signal_type: str = ""

    # Computation details
    raw_value: float = 0.0
    normalized_value: float = 0.0  # 0-100 percentile
    ewma_value: Optional[float] = None

    # Components
    components: Dict[str, float] = field(default_factory=dict)
    weights: Dict[str, float] = field(default_factory=dict)

    # Quality
    confidence: float = 0.0
    coverage: float = 0.0
    entity_count: int = 0
    source_count: int = 0

    # Timing
    computed_at: datetime = field(default_factory=datetime.now)
    data_window_start: Optional[datetime] = None
    data_window_end: Optional[datetime] = None

    # Lineage
    input_events: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": EventType.SIGNAL_COMPUTED.value,
            "bucket_id": self.bucket_id,
            "signal_type": self.signal_type,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "ewma_value": self.ewma_value,
            "components": self.components,
            "weights": self.weights,
            "confidence": self.confidence,
            "coverage": self.coverage,
            "entity_count": self.entity_count,
            "source_count": self.source_count,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
            "data_window_start": self.data_window_start.isoformat() if self.data_window_start else None,
            "data_window_end": self.data_window_end.isoformat() if self.data_window_end else None,
            "input_events": self.input_events,
        }


@dataclass
class AlertTriggeredEvent:
    """
    Event emitted when an alert is triggered.

    Links the alert to the signal updates that caused it.
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    alert_id: str = ""
    bucket_id: str = ""
    alert_type: str = ""
    severity: str = ""

    # Trigger details
    trigger_scores: Dict[str, float] = field(default_factory=dict)
    trigger_rules_met: List[str] = field(default_factory=list)

    # Context
    is_new: bool = True  # vs. recurring
    weeks_persistent: int = 1
    previous_severity: Optional[str] = None

    # Timing
    triggered_at: datetime = field(default_factory=datetime.now)
    cooldown_expires: Optional[datetime] = None

    # Lineage
    source_trend_events: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": EventType.ALERT_TRIGGERED.value,
            "alert_id": self.alert_id,
            "bucket_id": self.bucket_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "trigger_scores": self.trigger_scores,
            "trigger_rules_met": self.trigger_rules_met,
            "is_new": self.is_new,
            "weeks_persistent": self.weeks_persistent,
            "previous_severity": self.previous_severity,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "cooldown_expires": self.cooldown_expires.isoformat() if self.cooldown_expires else None,
            "source_trend_events": self.source_trend_events,
        }


class EventStore:
    """Simple event store for lineage tracking."""

    def __init__(self, db_path: Optional[str] = None):
        import sqlite3
        from pathlib import Path

        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "events.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self._create_tables()

    def _create_tables(self) -> None:
        """Create event tables."""
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                bucket_id TEXT,
                source TEXT,
                created_at TEXT NOT NULL,
                payload JSON NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_bucket ON events(bucket_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at)
        """)

        self.conn.commit()

    def store_event(self, event: Any) -> str:
        """Store an event."""
        cursor = self.conn.cursor()

        event_dict = event.to_dict()
        event_id = event_dict.get("event_id", str(uuid.uuid4()))
        event_type = event_dict.get("event_type", "unknown")
        bucket_id = event_dict.get("bucket_id")
        source = event_dict.get("source")

        cursor.execute("""
            INSERT OR REPLACE INTO events (event_id, event_type, bucket_id, source, created_at, payload)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            event_id,
            event_type,
            bucket_id,
            source,
            datetime.now().isoformat(),
            json.dumps(event_dict, default=str)
        ))

        self.conn.commit()
        return event_id

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve an event by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT payload FROM events WHERE event_id = ?", (event_id,))
        row = cursor.fetchone()

        if row:
            return json.loads(row[0])
        return None

    def get_events_by_type(self, event_type: EventType,
                          limit: int = 100) -> List[Dict[str, Any]]:
        """Get events by type."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT payload FROM events
            WHERE event_type = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (event_type.value, limit))

        return [json.loads(row[0]) for row in cursor.fetchall()]

    def get_events_for_bucket(self, bucket_id: str,
                              event_type: Optional[EventType] = None,
                              limit: int = 100) -> List[Dict[str, Any]]:
        """Get events for a bucket."""
        cursor = self.conn.cursor()

        if event_type:
            cursor.execute("""
                SELECT payload FROM events
                WHERE bucket_id = ? AND event_type = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (bucket_id, event_type.value, limit))
        else:
            cursor.execute("""
                SELECT payload FROM events
                WHERE bucket_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (bucket_id, limit))

        return [json.loads(row[0]) for row in cursor.fetchall()]

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()