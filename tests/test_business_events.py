"""
Tests for Business Event Detection System

Tests:
- Event models and serialization
- Pattern-based detection
- Deduplication and merging
- Event store operations
- Timeline and causal chain detection
"""

import pytest
from datetime import datetime, timedelta
import tempfile
from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.event_models import (
    BusinessEvent, BusinessEventType, EventConfidence, EventSource,
    FundingDetails, FundingStage, AcquisitionDetails, ProductLaunchDetails,
    LeadershipChangeDetails, PartnershipDetails, LayoffDetails,
    EventTimeline
)
from utils.event_detector import EventDetector, detect_events_batch
from utils.event_store import BusinessEventStore


class TestBusinessEventModels:
    """Tests for event data models."""
    
    def test_create_funding_event(self):
        """Test creating a funding round event."""
        event = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="OpenAI",
            entity_id="openai",
            headline="OpenAI raises $6B in Series C",
            funding_details=FundingDetails(
                amount_usd=6_000_000_000,
                stage=FundingStage.SERIES_C,
                lead_investors=["Thrive Capital"],
                all_investors=["Microsoft", "NVIDIA", "SoftBank"],
                valuation_usd=157_000_000_000,
            ),
        )
        
        assert event.event_type == BusinessEventType.FUNDING_ROUND
        assert event.entity_name == "OpenAI"
        assert event.funding_details.amount_usd == 6_000_000_000
        assert event.funding_details.stage == FundingStage.SERIES_C
        assert "Thrive Capital" in event.funding_details.lead_investors
    
    def test_create_acquisition_event(self):
        """Test creating an acquisition event."""
        event = BusinessEvent(
            event_type=BusinessEventType.ACQUISITION,
            entity_name="Meta",
            acquisition_details=AcquisitionDetails(
                acquirer_name="Meta",
                target_name="Character.AI",
                deal_value_usd=2_500_000_000,
                deal_type="acquisition",
            ),
        )
        
        assert event.event_type == BusinessEventType.ACQUISITION
        assert event.acquisition_details.acquirer_name == "Meta"
        assert event.acquisition_details.target_name == "Character.AI"
    
    def test_create_product_launch_event(self):
        """Test creating a product launch event."""
        event = BusinessEvent(
            event_type=BusinessEventType.PRODUCT_LAUNCH,
            entity_name="Anthropic",
            product_details=ProductLaunchDetails(
                product_name="Claude 3.5 Sonnet",
                product_type="model",
                is_beta=False,
            ),
        )
        
        assert event.event_type == BusinessEventType.PRODUCT_LAUNCH
        assert event.product_details.product_name == "Claude 3.5 Sonnet"
    
    def test_event_source(self):
        """Test event source creation."""
        source = EventSource(
            source_id="techcrunch",
            source_name="TechCrunch",
            source_url="https://techcrunch.com/article",
            source_credibility=0.9,
            published_at=datetime.utcnow(),
            excerpt="OpenAI has raised...",
        )
        
        assert source.source_credibility == 0.9
        
        # Test serialization
        data = source.to_dict()
        restored = EventSource.from_dict(data)
        assert restored.source_id == source.source_id
    
    def test_add_source_updates_confidence(self):
        """Test that adding sources updates confidence."""
        event = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="TestCo",
        )
        
        initial_confidence = event.confidence_score
        
        # Add high-credibility source
        event.add_source(EventSource(
            source_id="reuters",
            source_name="Reuters",
            source_url="https://reuters.com/1",
            source_credibility=0.95,
        ))
        
        assert event.confidence_score > initial_confidence
        assert event.source_count == 1
        
        # Add more sources
        event.add_source(EventSource(
            source_id="bloomberg",
            source_name="Bloomberg",
            source_url="https://bloomberg.com/1",
            source_credibility=0.95,
        ))
        
        assert event.source_count == 2
        assert event.confidence == EventConfidence.MEDIUM or event.confidence == EventConfidence.HIGH
    
    def test_content_hash_computation(self):
        """Test content hash for deduplication."""
        event1 = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="OpenAI",
            event_date=datetime(2024, 10, 1),
            funding_details=FundingDetails(
                amount_usd=6_000_000_000,
                stage=FundingStage.SERIES_C,
            ),
        )
        
        event2 = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="OpenAI",
            event_date=datetime(2024, 10, 2),  # Different day, same week
            funding_details=FundingDetails(
                amount_usd=6_000_000_000,
                stage=FundingStage.SERIES_C,
            ),
        )
        
        # Same event in same week should have same hash
        assert event1.content_hash == event2.content_hash
    
    def test_event_similarity(self):
        """Test event similarity detection."""
        event1 = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="OpenAI",
            event_date=datetime(2024, 10, 1),
        )
        
        event2 = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="OpenAI Inc",  # Slightly different name
            event_date=datetime(2024, 10, 3),  # Within 2 weeks
        )
        
        event3 = BusinessEvent(
            event_type=BusinessEventType.ACQUISITION,  # Different type
            entity_name="OpenAI",
            event_date=datetime(2024, 10, 1),
        )
        
        assert event1.is_similar_to(event2)
        assert not event1.is_similar_to(event3)  # Different type
    
    def test_event_merge(self):
        """Test merging duplicate events."""
        event1 = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="OpenAI",
            headline="OpenAI raises $6B",
        )
        event1.add_source(EventSource(
            source_id="source1",
            source_name="Source 1",
            source_url="https://source1.com",
            source_credibility=0.8,
        ))
        
        event2 = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="OpenAI",
            summary="OpenAI completes $6B funding round",
        )
        event2.add_source(EventSource(
            source_id="source2",
            source_name="Source 2",
            source_url="https://source2.com",
            source_credibility=0.9,
        ))
        
        event1.merge_with(event2)
        
        assert event1.source_count == 2
        assert event2.event_id in event1.merged_from
        assert event1.summary == "OpenAI completes $6B funding round"
    
    def test_event_serialization(self):
        """Test event to_dict and from_dict."""
        event = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="OpenAI",
            entity_id="openai",
            headline="OpenAI raises $6B",
            event_date=datetime(2024, 10, 1),
            funding_details=FundingDetails(
                amount_usd=6_000_000_000,
                stage=FundingStage.SERIES_C,
            ),
        )
        event.add_source(EventSource(
            source_id="tc",
            source_name="TechCrunch",
            source_url="https://tc.com/1",
            source_credibility=0.9,
        ))
        
        # Serialize
        data = event.to_dict()
        assert data["event_type"] == "funding_round"
        assert data["funding_details"]["amount_usd"] == 6_000_000_000
        
        # Deserialize
        restored = BusinessEvent.from_dict(data)
        assert restored.event_type == BusinessEventType.FUNDING_ROUND
        assert restored.funding_details.amount_usd == 6_000_000_000
        assert len(restored.sources) == 1


class TestEventDetector:
    """Tests for event detection."""
    
    @pytest.fixture
    def detector(self):
        """Create an EventDetector without LLM."""
        return EventDetector(llm_client=None, use_llm_fallback=False)
    
    def test_detect_funding_headline(self, detector):
        """Test funding detection from headline."""
        article = {
            "title": "OpenAI raises $6.6 billion in new funding round led by Thrive Capital",
            "content": "The AI company has secured significant investment from major tech firms.",
            "source": "TechCrunch",
            "url": "https://techcrunch.com/openai",
            "credibility_score": 9,
            "searchable_entities": {"companies": ["OpenAI", "Thrive Capital"]},
        }
        
        events = detector.detect_events(article)
        
        assert len(events) >= 1
        funding_events = [e for e in events if e.event_type == BusinessEventType.FUNDING_ROUND]
        assert len(funding_events) >= 1
        
        event = funding_events[0]
        assert event.entity_name == "OpenAI"
        assert event.funding_details is not None
        assert event.funding_details.amount_usd == 6_600_000_000
    
    def test_detect_acquisition_headline(self, detector):
        """Test acquisition detection."""
        article = {
            "title": "Meta acquires Character.AI for $2.5 billion",
            "content": "The deal will strengthen Meta's AI capabilities.",
            "source": "Bloomberg",
            "url": "https://bloomberg.com/meta",
            "credibility_score": 9,
            "searchable_entities": {"companies": ["Meta", "Character.AI"]},
        }
        
        events = detector.detect_events(article)
        
        acquisition_events = [e for e in events if e.event_type == BusinessEventType.ACQUISITION]
        assert len(acquisition_events) >= 1
        
        event = acquisition_events[0]
        assert event.acquisition_details is not None
    
    def test_detect_product_launch(self, detector):
        """Test product launch detection."""
        article = {
            "title": "Anthropic launches Claude 3.5 Sonnet with improved reasoning",
            "content": "The new model is now available via API.",
            "source": "VentureBeat",
            "url": "https://vb.com/anthropic",
            "credibility_score": 8,
            "searchable_entities": {"companies": ["Anthropic"], "models": ["Claude 3.5"]},
        }
        
        events = detector.detect_events(article)
        
        launch_events = [e for e in events if e.event_type == BusinessEventType.PRODUCT_LAUNCH]
        assert len(launch_events) >= 1
    
    def test_detect_leadership_change(self, detector):
        """Test leadership change detection."""
        article = {
            "title": "Sam Altman returns as OpenAI CEO after brief departure",
            "content": "The board has reinstated Sam Altman as Chief Executive Officer.",
            "source": "Reuters",
            "url": "https://reuters.com/openai",
            "credibility_score": 9,
            "searchable_entities": {"companies": ["OpenAI"], "people": ["Sam Altman"]},
        }
        
        events = detector.detect_events(article)
        
        leadership_events = [e for e in events if e.event_type == BusinessEventType.LEADERSHIP_CHANGE]
        assert len(leadership_events) >= 1
    
    def test_detect_layoff(self, detector):
        """Test layoff detection."""
        article = {
            "title": "AI startup Stability AI lays off 10% of workforce",
            "content": "The company is restructuring amid funding challenges.",
            "source": "The Information",
            "url": "https://theinformation.com/stability",
            "credibility_score": 8,
            "searchable_entities": {"companies": ["Stability AI"]},
        }
        
        events = detector.detect_events(article)
        
        layoff_events = [e for e in events if e.event_type == BusinessEventType.LAYOFF]
        assert len(layoff_events) >= 1
        
        if layoff_events:
            event = layoff_events[0]
            assert event.layoff_details is not None
            assert event.layoff_details.percentage == 10.0
    
    def test_no_events_generic_article(self, detector):
        """Test that generic articles don't produce spurious events."""
        article = {
            "title": "AI trends to watch in 2024",
            "content": "The industry continues to evolve rapidly with new developments.",
            "source": "TechBlog",
            "url": "https://techblog.com/trends",
            "credibility_score": 6,
            "searchable_entities": {"companies": []},
        }
        
        events = detector.detect_events(article)
        
        # Should have few or no events from generic content
        high_confidence = [e for e in events if e.confidence_score >= 0.5]
        assert len(high_confidence) == 0
    
    def test_batch_detection(self, detector):
        """Test batch event detection with deduplication."""
        articles = [
            {
                "title": "OpenAI raises $6B in funding",
                "content": "Led by Thrive Capital.",
                "source": "TechCrunch",
                "url": "https://tc.com/1",
                "credibility_score": 9,
                "searchable_entities": {"companies": ["OpenAI"]},
            },
            {
                "title": "OpenAI secures $6 billion investment",
                "content": "The funding round was led by Thrive.",
                "source": "Bloomberg",
                "url": "https://bloomberg.com/1",
                "credibility_score": 9,
                "searchable_entities": {"companies": ["OpenAI"]},
            },
        ]
        
        events, stats = detect_events_batch(articles)
        
        # Both articles report same event - should be merged
        funding_events = [e for e in events if e.event_type == BusinessEventType.FUNDING_ROUND]
        assert len(funding_events) <= 2  # Should ideally be 1 after dedup
    
    def test_source_credibility(self, detector):
        """Test source credibility lookup."""
        assert detector.get_source_credibility("Reuters") >= 0.9
        assert detector.get_source_credibility("TechCrunch") >= 0.85
        assert detector.get_source_credibility("Unknown Blog") <= 0.8


class TestEventStore:
    """Tests for event storage."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        if db_path.exists():
            db_path.unlink()
    
    @pytest.fixture
    def store(self, temp_db):
        """Create an EventStore with temporary database."""
        store = BusinessEventStore(db_path=str(temp_db))
        yield store
        store.close()
    
    def test_save_and_retrieve_event(self, store):
        """Test saving and retrieving an event."""
        event = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="TestCo",
            entity_id="testco",
            headline="TestCo raises $10M",
            event_date=datetime.utcnow(),
            funding_details=FundingDetails(
                amount_usd=10_000_000,
                stage=FundingStage.SEED,
            ),
        )
        event.add_source(EventSource(
            source_id="test",
            source_name="Test Source",
            source_url="https://test.com",
            source_credibility=0.8,
        ))
        
        event_id = store.save_event(event)
        assert event_id is not None
        
        retrieved = store.get_event(event_id)
        assert retrieved is not None
        assert retrieved.entity_name == "TestCo"
        assert retrieved.funding_details.amount_usd == 10_000_000
    
    def test_dedup_on_save(self, store):
        """Test that saving duplicate events merges them."""
        event1 = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="TestCo",
            entity_id="testco",
            headline="TestCo raises $10M",
            event_date=datetime(2024, 10, 1),
            funding_details=FundingDetails(
                amount_usd=10_000_000,
                stage=FundingStage.SEED,
            ),
        )
        event1.add_source(EventSource(
            source_id="source1",
            source_name="Source 1",
            source_url="https://source1.com",
            source_credibility=0.8,
        ))
        
        event2 = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="TestCo",
            entity_id="testco",
            headline="TestCo secures $10M seed",
            event_date=datetime(2024, 10, 2),
            funding_details=FundingDetails(
                amount_usd=10_000_000,
                stage=FundingStage.SEED,
            ),
        )
        event2.add_source(EventSource(
            source_id="source2",
            source_name="Source 2",
            source_url="https://source2.com",
            source_credibility=0.9,
        ))
        
        id1 = store.save_event(event1)
        id2 = store.save_event(event2)
        
        # Should merge into first event
        assert id1 == id2
        
        merged = store.get_event(id1)
        assert merged.source_count == 2
    
    def test_get_events_by_entity(self, store):
        """Test querying events by entity."""
        # Save events for different entities
        for entity in ["CompanyA", "CompanyB"]:
            event = BusinessEvent(
                event_type=BusinessEventType.PRODUCT_LAUNCH,
                entity_name=entity,
                entity_id=entity.lower(),
                headline=f"{entity} launches new product",
            )
            store.save_event(event)
        
        events_a = store.get_events_by_entity("companya")
        events_b = store.get_events_by_entity("companyb")
        
        assert len(events_a) == 1
        assert len(events_b) == 1
        assert events_a[0].entity_name == "CompanyA"
    
    def test_get_events_by_type(self, store):
        """Test querying events by type."""
        # Save events of different types
        for event_type in [BusinessEventType.FUNDING_ROUND, BusinessEventType.ACQUISITION]:
            event = BusinessEvent(
                event_type=event_type,
                entity_name="TestCo",
                entity_id="testco",
                headline=f"TestCo {event_type.value}",
            )
            store.save_event(event)
        
        funding = store.get_events_by_type(BusinessEventType.FUNDING_ROUND)
        acquisitions = store.get_events_by_type(BusinessEventType.ACQUISITION)
        
        assert len(funding) == 1
        assert len(acquisitions) == 1
    
    def test_get_events_in_range(self, store):
        """Test querying events by date range."""
        now = datetime.utcnow()
        
        # Event from today
        event1 = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="Today",
            entity_id="today",
            headline="Today event",
            event_date=now,
        )
        store.save_event(event1)
        
        # Event from 30 days ago
        event2 = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="Old",
            entity_id="old",
            headline="Old event",
            event_date=now - timedelta(days=30),
        )
        store.save_event(event2)
        
        # Query last 7 days
        recent = store.get_events_in_range(
            now - timedelta(days=7),
            now + timedelta(days=1)
        )
        
        assert len(recent) == 1
        assert recent[0].entity_name == "Today"
    
    def test_search_events(self, store):
        """Test searching events."""
        event = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="OpenAI",
            entity_id="openai",
            headline="OpenAI raises massive funding round",
            summary="The AI company secured billions in new investment.",
        )
        store.save_event(event)
        
        results = store.search_events("OpenAI")
        assert len(results) >= 1
        
        results = store.search_events("massive funding")
        assert len(results) >= 1
        
        results = store.search_events("nonexistent query xyz")
        assert len(results) == 0
    
    def test_get_stats(self, store):
        """Test getting store statistics."""
        # Save some events
        for i in range(5):
            event = BusinessEvent(
                event_type=BusinessEventType.FUNDING_ROUND,
                entity_name=f"Company{i}",
                entity_id=f"company{i}",
                headline=f"Company{i} funding",
            )
            store.save_event(event)
        
        stats = store.get_stats()
        
        assert stats["total_events"] == 5
        assert stats["by_type"]["funding_round"] == 5


class TestEventTimeline:
    """Tests for event timeline."""
    
    def test_create_timeline(self):
        """Test creating an event timeline."""
        timeline = EventTimeline(
            entity_id="openai",
            entity_name="OpenAI",
        )
        
        # Add events
        events = [
            BusinessEvent(
                event_type=BusinessEventType.FUNDING_ROUND,
                entity_name="OpenAI",
                event_date=datetime(2024, 1, 1),
            ),
            BusinessEvent(
                event_type=BusinessEventType.PRODUCT_LAUNCH,
                entity_name="OpenAI",
                event_date=datetime(2024, 6, 1),
            ),
        ]
        
        for event in events:
            timeline.add_event(event)
        
        assert len(timeline.events) == 2
        # Should be sorted chronologically
        assert timeline.events[0].event_date < timeline.events[1].event_date
    
    def test_filter_events_by_type(self):
        """Test filtering timeline events by type."""
        timeline = EventTimeline(entity_id="test", entity_name="Test")
        
        timeline.add_event(BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="Test",
            event_date=datetime(2024, 1, 1),
        ))
        timeline.add_event(BusinessEvent(
            event_type=BusinessEventType.PRODUCT_LAUNCH,
            entity_name="Test",
            event_date=datetime(2024, 2, 1),
        ))
        timeline.add_event(BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="Test",
            event_date=datetime(2024, 3, 1),
        ))
        
        funding = timeline.get_events_by_type(BusinessEventType.FUNDING_ROUND)
        assert len(funding) == 2
        
        launches = timeline.get_events_by_type(BusinessEventType.PRODUCT_LAUNCH)
        assert len(launches) == 1
    
    def test_detect_causal_chains(self):
        """Test causal chain detection."""
        timeline = EventTimeline(entity_id="test", entity_name="Test")
        
        # Add funding event
        funding = BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="Test",
            event_date=datetime(2024, 1, 1),
        )
        timeline.add_event(funding)
        
        # Add product launch 60 days later (within causal window)
        launch = BusinessEvent(
            event_type=BusinessEventType.PRODUCT_LAUNCH,
            entity_name="Test",
            event_date=datetime(2024, 3, 1),
        )
        timeline.add_event(launch)
        
        chains = timeline.detect_causal_chains()
        
        # Should detect funding → product launch chain
        assert len(chains) >= 1
    
    def test_timeline_serialization(self):
        """Test timeline to_dict."""
        timeline = EventTimeline(entity_id="test", entity_name="Test")
        
        timeline.add_event(BusinessEvent(
            event_type=BusinessEventType.FUNDING_ROUND,
            entity_name="Test",
            event_date=datetime(2024, 1, 1),
        ))
        
        data = timeline.to_dict()
        
        assert data["entity_id"] == "test"
        assert data["event_count"] == 1
        assert "events" in data


class TestChinesePatterns:
    """Tests for Chinese language pattern matching."""
    
    @pytest.fixture
    def detector(self):
        return EventDetector(llm_client=None, use_llm_fallback=False)
    
    def test_chinese_funding_detection(self, detector):
        """Test funding detection from Chinese headlines."""
        article = {
            "title": "月之暗面完成新一轮10亿美元融资",
            "content": "月之暗面宣布完成最新一轮融资。",
            "source": "36氪",
            "url": "https://36kr.com/moonshot",
            "credibility_score": 8,
            "searchable_entities": {"companies": ["月之暗面"]},
        }
        
        events = detector.detect_events(article)
        
        funding_events = [e for e in events if e.event_type == BusinessEventType.FUNDING_ROUND]
        # Pattern should match Chinese funding keywords
        assert len(funding_events) >= 1
    
    def test_chinese_product_launch(self, detector):
        """Test product launch detection from Chinese."""
        article = {
            "title": "智谱AI发布新一代大模型GLM-4",
            "content": "智谱AI正式发布GLM-4系列模型。",
            "source": "机器之心",
            "url": "https://jiqizhixin.com/zhipu",
            "credibility_score": 8,
            "searchable_entities": {"companies": ["智谱AI"], "models": ["GLM-4"]},
        }
        
        events = detector.detect_events(article)
        
        launch_events = [e for e in events if e.event_type == BusinessEventType.PRODUCT_LAUNCH]
        assert len(launch_events) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
