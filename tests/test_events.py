"""
Tests for events module.
"""

import pytest
from datetime import datetime
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.events import (
    EventType,
    ProcessingStatus,
    ArticleEvent,
    TrendUpdateEvent,
    SignalComputedEvent,
    AlertTriggeredEvent,
    EventStore,
)


class TestArticleEvent:
    """Tests for ArticleEvent."""

    def test_create_article_event(self):
        """Test creating a basic article event."""
        event = ArticleEvent(
            source="hackernews",
            url="https://example.com/article",
            title="Test Article",
            content="This is test content for the article.",
        )

        assert event.source == "hackernews"
        assert event.url == "https://example.com/article"
        assert event.status == ProcessingStatus.PENDING
        assert event.event_id is not None

    def test_compute_content_hash(self):
        """Test content hash computation."""
        event = ArticleEvent(
            title="Test Title",
            content="Test content",
        )

        hash1 = event.compute_content_hash()
        assert hash1 is not None
        assert len(hash1) == 64  # SHA256 hex length

        # Same content should produce same hash
        event2 = ArticleEvent(
            title="Test Title",
            content="Test content",
        )
        hash2 = event2.compute_content_hash()
        assert hash1 == hash2

    def test_canonicalize_url(self):
        """Test URL canonicalization."""
        event = ArticleEvent(
            url="https://WWW.Example.com/Article/?utm_source=twitter&id=123&ref=home"
        )

        canonical = event.canonicalize_url()

        # Should strip www, lowercase, remove tracking params
        assert "www" not in canonical
        assert "utm_source" not in canonical
        assert "ref=" not in canonical
        assert "id=123" in canonical

    def test_mark_processing(self):
        """Test marking article as processing."""
        event = ArticleEvent()
        event.mark_processing()

        assert event.status == ProcessingStatus.PROCESSING
        assert event.processing_started_at is not None

    def test_mark_completed(self):
        """Test marking article as completed."""
        event = ArticleEvent()
        event.mark_completed()

        assert event.status == ProcessingStatus.COMPLETED
        assert event.processing_completed_at is not None

    def test_mark_failed(self):
        """Test marking article as failed."""
        event = ArticleEvent()
        event.mark_failed("Network timeout")

        assert event.status == ProcessingStatus.FAILED
        assert event.error_message == "Network timeout"

    def test_mark_duplicate(self):
        """Test marking article as duplicate."""
        event = ArticleEvent()
        event.mark_duplicate("original-id-123")

        assert event.is_duplicate is True
        assert event.duplicate_of == "original-id-123"
        assert event.status == ProcessingStatus.DEDUPLICATED

    def test_to_dict(self):
        """Test converting to dictionary."""
        event = ArticleEvent(
            source="reddit",
            url="https://reddit.com/r/test",
            title="Test Post",
            content="Post content",
            entities=["OpenAI", "GPT-4"],
            buckets=["llm-foundation"],
        )

        data = event.to_dict()

        assert data["source"] == "reddit"
        assert data["entities"] == ["OpenAI", "GPT-4"]
        assert data["event_type"] == EventType.ARTICLE_INGESTED.value

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "event_id": "test-123",
            "source": "arxiv",
            "url": "https://arxiv.org/abs/1234",
            "title": "Research Paper",
            "content": "Abstract content",
            "status": "completed",
            "entities": ["Transformer", "BERT"],
        }

        event = ArticleEvent.from_dict(data)

        assert event.event_id == "test-123"
        assert event.source == "arxiv"
        assert event.status == ProcessingStatus.COMPLETED
        assert "Transformer" in event.entities


class TestTrendUpdateEvent:
    """Tests for TrendUpdateEvent."""

    def test_create_trend_update(self):
        """Test creating a trend update event."""
        event = TrendUpdateEvent(
            bucket_id="ai-agents",
            signal_type="tms",
            old_value=50.0,
            new_value=65.0,
        )

        assert event.bucket_id == "ai-agents"
        assert event.signal_type == "tms"
        assert event.new_value == 65.0

    def test_compute_delta(self):
        """Test delta computation."""
        event = TrendUpdateEvent(
            bucket_id="ai-agents",
            signal_type="tms",
            old_value=50.0,
            new_value=65.0,
        )

        event.compute_delta()

        assert event.delta == 15.0
        assert event.delta_percent == pytest.approx(30.0)

    def test_compute_delta_from_zero(self):
        """Test delta computation when old value is zero."""
        event = TrendUpdateEvent(
            bucket_id="ai-agents",
            signal_type="tms",
            old_value=0.0,
            new_value=65.0,
        )

        event.compute_delta()

        assert event.delta == 65.0
        assert event.delta_percent is None  # Division by zero case

    def test_is_significant_change(self):
        """Test significant change detection."""
        small_change = TrendUpdateEvent(
            bucket_id="ai-agents",
            signal_type="tms",
            delta=2.0,
        )
        assert small_change.is_significant_change(threshold=5.0) is False

        large_change = TrendUpdateEvent(
            bucket_id="ai-agents",
            signal_type="tms",
            delta=10.0,
        )
        assert large_change.is_significant_change(threshold=5.0) is True

    def test_get_direction(self):
        """Test direction detection."""
        rising = TrendUpdateEvent(bucket_id="test", signal_type="tms", delta=5.0)
        assert rising.get_direction() == "rising"

        falling = TrendUpdateEvent(bucket_id="test", signal_type="tms", delta=-5.0)
        assert falling.get_direction() == "falling"

        stable = TrendUpdateEvent(bucket_id="test", signal_type="tms", delta=1.0)
        assert stable.get_direction() == "stable"

    def test_to_dict(self):
        """Test converting to dictionary."""
        event = TrendUpdateEvent(
            bucket_id="ai-agents",
            signal_type="tms",
            old_value=50.0,
            new_value=65.0,
            delta=15.0,
            confidence=0.85,
            contributing_entities=["langchain", "llamaindex"],
        )

        data = event.to_dict()

        assert data["bucket_id"] == "ai-agents"
        assert data["direction"] == "rising"
        assert data["event_type"] == EventType.TREND_UPDATE.value

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "event_id": "trend-123",
            "bucket_id": "ai-coding",
            "signal_type": "ccs",
            "old_value": 40.0,
            "new_value": 55.0,
            "delta": 15.0,
            "confidence": 0.9,
        }

        event = TrendUpdateEvent.from_dict(data)

        assert event.event_id == "trend-123"
        assert event.bucket_id == "ai-coding"
        assert event.confidence == 0.9


class TestSignalComputedEvent:
    """Tests for SignalComputedEvent."""

    def test_create_signal_computed(self):
        """Test creating a signal computed event."""
        event = SignalComputedEvent(
            bucket_id="ai-agents",
            signal_type="tms",
            raw_value=1250.0,
            normalized_value=78.5,
            components={"github_stars": 800, "hf_downloads": 450},
            weights={"github_stars": 0.6, "hf_downloads": 0.4},
        )

        assert event.bucket_id == "ai-agents"
        assert event.normalized_value == 78.5
        assert event.components["github_stars"] == 800

    def test_to_dict(self):
        """Test converting to dictionary."""
        event = SignalComputedEvent(
            bucket_id="ai-agents",
            signal_type="tms",
            raw_value=100.0,
            normalized_value=75.0,
            confidence=0.88,
        )

        data = event.to_dict()

        assert data["event_type"] == EventType.SIGNAL_COMPUTED.value
        assert data["confidence"] == 0.88


class TestAlertTriggeredEvent:
    """Tests for AlertTriggeredEvent."""

    def test_create_alert_triggered(self):
        """Test creating an alert triggered event."""
        event = AlertTriggeredEvent(
            alert_id="alert-123",
            bucket_id="ai-agents",
            alert_type="alpha_zone",
            severity="WARN",
            trigger_scores={"tms": 92, "ccs": 28},
            trigger_rules_met=["TMS >= 90", "CCS <= 30"],
        )

        assert event.alert_type == "alpha_zone"
        assert event.trigger_scores["tms"] == 92
        assert len(event.trigger_rules_met) == 2

    def test_to_dict(self):
        """Test converting to dictionary."""
        event = AlertTriggeredEvent(
            alert_id="alert-456",
            bucket_id="ai-coding",
            alert_type="hype_zone",
            severity="INFO",
        )

        data = event.to_dict()

        assert data["event_type"] == EventType.ALERT_TRIGGERED.value
        assert data["alert_id"] == "alert-456"


class TestEventStore:
    """Tests for EventStore."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def event_store(self, temp_db):
        """Create an EventStore with temporary database."""
        store = EventStore(db_path=temp_db)
        yield store
        store.close()

    def test_store_and_retrieve_event(self, event_store):
        """Test storing and retrieving an event."""
        event = ArticleEvent(
            source="hackernews",
            url="https://example.com/test",
            title="Test Article",
        )

        event_id = event_store.store_event(event)
        assert event_id is not None

        retrieved = event_store.get_event(event_id)
        assert retrieved is not None
        assert retrieved["source"] == "hackernews"

    def test_get_events_by_type(self, event_store):
        """Test getting events by type."""
        # Store article event
        article = ArticleEvent(source="reddit", url="https://reddit.com/r/test")
        event_store.store_event(article)

        # Store trend update event
        trend = TrendUpdateEvent(bucket_id="ai-agents", signal_type="tms")
        event_store.store_event(trend)

        # Get only article events
        articles = event_store.get_events_by_type(EventType.ARTICLE_INGESTED)
        assert len(articles) == 1
        assert articles[0]["source"] == "reddit"

    def test_get_events_for_bucket(self, event_store):
        """Test getting events for a specific bucket."""
        # Store events for different buckets
        trend1 = TrendUpdateEvent(bucket_id="ai-agents", signal_type="tms")
        trend2 = TrendUpdateEvent(bucket_id="ai-coding", signal_type="ccs")

        event_store.store_event(trend1)
        event_store.store_event(trend2)

        # Get events for ai-agents
        events = event_store.get_events_for_bucket("ai-agents")
        assert len(events) == 1
        assert events[0]["bucket_id"] == "ai-agents"

    def test_get_nonexistent_event(self, event_store):
        """Test getting an event that doesn't exist."""
        result = event_store.get_event("nonexistent-id")
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])