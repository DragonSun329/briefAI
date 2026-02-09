"""
Tests for Signal Tracker.

Tests:
1. Signal/Event data structure serialization
2. Cluster-to-signal linking algorithm
3. Signal creation from new clusters
4. Metrics computation
5. Multi-day signal continuity
"""

import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from utils.signal_tracker import (
    Signal,
    SignalEvent,
    SignalMetrics,
    SignalProfile,
    SignalTracker,
    jaccard_overlap,
    derive_signal_name,
    generate_signal_id,
    days_between,
)


# =============================================================================
# FIXTURES
# =============================================================================

def make_cluster_item(
    cluster_id: str,
    title: str,
    entities: list,
    buckets: list,
    gravity_score: float = 6.0,
    confidence: float = 0.8,
    sources: list = None,
    domains: list = None,
):
    """Create a mock theme cluster item."""
    return {
        'item_type': 'cluster',
        'cluster_id': cluster_id,
        'rank_score': gravity_score + 0.5,
        'gravity_score': gravity_score,
        'canonical': {
            'title': title,
            'url': f'https://example.com/{cluster_id}',
            'source': sources[0] if sources else 'TestSource',
            'key_insight': f'Key insight about {title}',
        },
        'related': [
            {'title': f'Related {i}', 'url': f'https://r{i}.com/a', 'source': s}
            for i, s in enumerate(sources[1:] if sources else [])
        ],
        'cluster_stats': {
            'cluster_confidence': confidence,
            'shared_entities': entities,
            'shared_bucket_tags': buckets,
        },
        'top_domains': domains or ['example.com'],
        'confidence_bonus': confidence * 0.3,
    }


def make_singleton_item(
    title: str,
    url: str,
    gravity_score: float = 5.0,
):
    """Create a mock singleton item."""
    return {
        'item_type': 'singleton',
        'rank_score': gravity_score,
        'gravity_score': gravity_score,
        'article': {
            'title': title,
            'url': url,
            'source': 'SingleSource',
            'key_insight': '',
        },
    }


def make_dual_feed(date: str, theme_items: list):
    """Create a mock dual feed."""
    return {
        'version': '2.2',
        'date': date,
        'generated_at': datetime.now().isoformat(),
        'top_themes': {
            'items': theme_items,
        },
        'top_events': {
            'items': [],
        },
    }


# =============================================================================
# DATA STRUCTURE TESTS
# =============================================================================

class TestSignalEventSerialization:
    """Test SignalEvent data structure."""
    
    def test_to_dict_and_back(self):
        """SignalEvent should roundtrip through dict."""
        event = SignalEvent(
            date='2026-02-09',
            cluster_id='abc123',
            rank_score=7.5,
            gravity_score=6.8,
            cluster_confidence=0.85,
            sources=['TechCrunch', 'Verge'],
            domains=['techcrunch.com', 'theverge.com'],
            entities=['openai', 'gpt'],
            buckets=['llm-release'],
            title='OpenAI launches GPT-5',
            url='https://example.com/article',
        )
        
        d = event.to_dict()
        restored = SignalEvent.from_dict(d)
        
        assert restored.date == event.date
        assert restored.cluster_id == event.cluster_id
        assert restored.rank_score == event.rank_score
        assert restored.entities == event.entities
        assert restored.buckets == event.buckets
    
    def test_json_serializable(self):
        """SignalEvent dict should be JSON-serializable."""
        event = SignalEvent(
            date='2026-02-09', cluster_id='x', rank_score=5.0,
            gravity_score=5.0, cluster_confidence=0.5,
            sources=['A'], domains=['a.com'], entities=['e'],
            buckets=['b'], title='T', url='http://x.com',
        )
        
        json_str = json.dumps(event.to_dict())
        assert len(json_str) > 0


class TestSignalSerialization:
    """Test Signal data structure."""
    
    def test_to_dict_and_back(self):
        """Signal should roundtrip through dict."""
        signal = Signal(
            signal_id='sig123',
            name='OpenAI • LLM Release',
            created_at='2026-02-01T10:00:00',
            first_seen_date='2026-02-01',
            last_seen_date='2026-02-09',
            status='emerging',
            metrics=SignalMetrics(mentions_7d=5, velocity=2.1, confidence=0.72),
            profile=SignalProfile(
                top_entities=['openai'],
                top_buckets=['llm-release'],
                example_titles=['GPT-5 released'],
            ),
            embedding=[0.1, 0.2, 0.3],
        )
        signal._consecutive_mainstream_days = 1
        
        d = signal.to_dict()
        restored = Signal.from_dict(d)
        
        assert restored.signal_id == signal.signal_id
        assert restored.status == signal.status
        assert restored.metrics.mentions_7d == signal.metrics.mentions_7d
        assert restored.embedding == signal.embedding
        assert restored._consecutive_mainstream_days == 1
    
    def test_without_embedding(self):
        """Signal without embedding should serialize."""
        signal = Signal(
            signal_id='sig456',
            name='Test Signal',
            created_at='2026-02-01T10:00:00',
            first_seen_date='2026-02-01',
            last_seen_date='2026-02-01',
            status='weak_signal',
        )
        
        d = signal.to_dict(include_embedding=False)
        assert 'embedding' not in d
        
        d = signal.to_dict(include_embedding=True)
        # embedding is None, so may or may not be in dict
        restored = Signal.from_dict(d)
        assert restored.embedding is None


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================

class TestJaccardOverlap:
    """Test Jaccard similarity."""
    
    def test_identical_sets(self):
        """Identical sets should have overlap 1.0."""
        a = {'x', 'y', 'z'}
        assert jaccard_overlap(a, a) == 1.0
    
    def test_disjoint_sets(self):
        """Disjoint sets should have overlap 0.0."""
        a = {'a', 'b'}
        b = {'c', 'd'}
        assert jaccard_overlap(a, b) == 0.0
    
    def test_partial_overlap(self):
        """Partial overlap should be correct."""
        a = {'openai', 'gpt', 'llm'}
        b = {'openai', 'anthropic', 'llm'}
        # Intersection: openai, llm (2)
        # Union: openai, gpt, llm, anthropic (4)
        assert jaccard_overlap(a, b) == 0.5
    
    def test_empty_sets(self):
        """Empty sets should return 0.0."""
        assert jaccard_overlap(set(), {'a'}) == 0.0
        assert jaccard_overlap({'a'}, set()) == 0.0
        assert jaccard_overlap(set(), set()) == 0.0


class TestSignalNaming:
    """Test signal name derivation."""
    
    def test_entity_and_bucket(self):
        """Name should include entity and bucket."""
        name = derive_signal_name(['OpenAI', 'ChatGPT'], ['llm-release'])
        assert 'OpenAI' in name
    
    def test_entity_only(self):
        """Name should work with only entities."""
        name = derive_signal_name(['Anthropic', 'Claude'], [])
        assert 'Anthropic' in name
    
    def test_bucket_only(self):
        """Name should work with only buckets."""
        name = derive_signal_name([], ['ai-funding'])
        assert 'Funding' in name
    
    def test_empty_inputs(self):
        """Name should handle empty inputs."""
        name = derive_signal_name([], [])
        assert name == 'Unnamed Signal'


class TestDaysBetween:
    """Test date difference calculation."""
    
    def test_same_day(self):
        """Same day should be 0."""
        assert days_between('2026-02-09', '2026-02-09') == 0
    
    def test_different_days(self):
        """Different days should compute correctly."""
        assert days_between('2026-02-01', '2026-02-09') == 8
        assert days_between('2026-02-09', '2026-02-01') == 8  # Absolute


class TestSignalIdGeneration:
    """Test signal ID generation."""
    
    def test_stable_id(self):
        """Same inputs should produce same ID."""
        id1 = generate_signal_id(['openai'], ['llm'], '2026-02-01')
        id2 = generate_signal_id(['openai'], ['llm'], '2026-02-01')
        assert id1 == id2
    
    def test_different_inputs(self):
        """Different inputs should produce different IDs."""
        id1 = generate_signal_id(['openai'], ['llm'], '2026-02-01')
        id2 = generate_signal_id(['anthropic'], ['llm'], '2026-02-01')
        assert id1 != id2
    
    def test_id_length(self):
        """ID should be 12 characters."""
        signal_id = generate_signal_id(['x'], ['y'], '2026-02-01')
        assert len(signal_id) == 12


# =============================================================================
# TRACKER INTEGRATION TESTS
# =============================================================================

class TestSignalCreation:
    """Test signal creation from clusters."""
    
    def test_creates_signal_from_new_cluster(self):
        """New cluster should create new signal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(
                signals_dir=Path(tmpdir),
                use_embeddings=False,
            )
            
            feed = make_dual_feed('2026-02-01', [
                make_cluster_item(
                    'c1', 'OpenAI launches GPT-5',
                    entities=['openai', 'gpt'],
                    buckets=['llm-release'],
                )
            ])
            
            stats = tracker.update_from_dual_feed(feed, '2026-02-01')
            
            assert stats['signals_created'] == 1
            assert len(tracker.signals) == 1
            
            signal = list(tracker.signals.values())[0]
            assert signal.status == 'weak_signal'
            assert signal.first_seen_date == '2026-02-01'
            assert 'openai' in [e.lower() for e in signal.profile.top_entities]
    
    def test_singleton_creates_signal(self):
        """Singleton item should create signal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(
                signals_dir=Path(tmpdir),
                use_embeddings=False,
            )
            
            feed = make_dual_feed('2026-02-01', [
                make_singleton_item('Anthropic raises $2B', 'https://example.com/a')
            ])
            
            stats = tracker.update_from_dual_feed(feed, '2026-02-01')
            
            assert stats['signals_created'] == 1


class TestSignalLinking:
    """Test cluster-to-signal linking."""
    
    def test_links_similar_clusters_across_days(self):
        """Clusters with same entities/buckets should link."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(
                signals_dir=Path(tmpdir),
                use_embeddings=False,
            )
            
            # Day 1: Create signal
            feed1 = make_dual_feed('2026-02-01', [
                make_cluster_item(
                    'c1', 'OpenAI announces GPT-5',
                    entities=['openai', 'gpt'],
                    buckets=['llm-release'],
                )
            ])
            tracker.update_from_dual_feed(feed1, '2026-02-01')
            
            assert len(tracker.signals) == 1
            signal_id = list(tracker.signals.keys())[0]
            
            # Day 2: Similar cluster should link
            feed2 = make_dual_feed('2026-02-02', [
                make_cluster_item(
                    'c2', 'GPT-5 receives positive reviews',
                    entities=['openai', 'gpt', 'gpt-5'],
                    buckets=['llm-release', 'product-review'],
                )
            ])
            stats = tracker.update_from_dual_feed(feed2, '2026-02-02')
            
            # Should link, not create new
            assert stats['signals_updated'] == 1
            assert stats['signals_created'] == 0
            assert len(tracker.signals) == 1
            
            signal = tracker.signals[signal_id]
            assert len(signal.cluster_refs) == 2
            assert signal.last_seen_date == '2026-02-02'
    
    def test_creates_new_signal_for_different_topic(self):
        """Clusters with different entities/buckets should create new signal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(
                signals_dir=Path(tmpdir),
                use_embeddings=False,
            )
            
            # Day 1: OpenAI signal
            feed1 = make_dual_feed('2026-02-01', [
                make_cluster_item(
                    'c1', 'OpenAI launches GPT-5',
                    entities=['openai', 'gpt'],
                    buckets=['llm-release'],
                )
            ])
            tracker.update_from_dual_feed(feed1, '2026-02-01')
            
            # Day 2: Completely different topic
            feed2 = make_dual_feed('2026-02-02', [
                make_cluster_item(
                    'c2', 'Nvidia announces new AI chip',
                    entities=['nvidia', 'ai-chip'],
                    buckets=['hardware', 'semiconductor'],
                )
            ])
            stats = tracker.update_from_dual_feed(feed2, '2026-02-02')
            
            # Should create new signal
            assert stats['signals_created'] == 1
            assert len(tracker.signals) == 2
    
    def test_does_not_link_after_max_gap(self):
        """Clusters should not link after MAX_GAP_DAYS without strong overlap."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(
                signals_dir=Path(tmpdir),
                use_embeddings=False,
            )
            
            # Day 1
            feed1 = make_dual_feed('2026-01-01', [
                make_cluster_item(
                    'c1', 'OpenAI launches GPT-5',
                    entities=['openai'],
                    buckets=['llm-release'],
                )
            ])
            tracker.update_from_dual_feed(feed1, '2026-01-01')
            
            # Day 30 (way past MAX_GAP_DAYS of 14)
            # With weak overlap, should create new signal
            feed2 = make_dual_feed('2026-01-30', [
                make_cluster_item(
                    'c2', 'Different AI news',
                    entities=['different'],  # No entity overlap
                    buckets=['ai-news'],    # No bucket overlap
                )
            ])
            stats = tracker.update_from_dual_feed(feed2, '2026-01-30')
            
            # Should create new (no overlap + large gap)
            assert stats['signals_created'] == 1
            assert len(tracker.signals) == 2


class TestMetricsComputation:
    """Test signal metrics computation."""
    
    def test_mentions_count(self):
        """Mentions should be counted correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(
                signals_dir=Path(tmpdir),
                use_embeddings=False,
            )
            
            # Add 3 clusters over 3 days
            for i in range(3):
                date = f'2026-02-0{i+1}'
                feed = make_dual_feed(date, [
                    make_cluster_item(
                        f'c{i}', 'OpenAI GPT-5',
                        entities=['openai', 'gpt'],
                        buckets=['llm-release'],
                    )
                ])
                tracker.update_from_dual_feed(feed, date)
            
            signal = list(tracker.signals.values())[0]
            assert signal.metrics.mentions_7d == 3
            assert signal.metrics.mentions_21d == 3
    
    def test_velocity_increases_with_activity(self):
        """Velocity should be > 1 when activity exceeds baseline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(
                signals_dir=Path(tmpdir),
                use_embeddings=False,
            )
            
            # Create signal with multiple events in 7 days
            for i in range(5):
                date = f'2026-02-0{i+1}'
                feed = make_dual_feed(date, [
                    make_cluster_item(
                        f'c{i}', 'Hot Topic',
                        entities=['hot'],
                        buckets=['trending'],
                    )
                ])
                tracker.update_from_dual_feed(feed, date)
            
            signal = list(tracker.signals.values())[0]
            # With no baseline (new signal), velocity should be mentions_7d / 1
            assert signal.metrics.velocity >= 1.0
    
    def test_coverage_domains(self):
        """Coverage domains should count unique domains."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(
                signals_dir=Path(tmpdir),
                use_embeddings=False,
            )
            
            feed = make_dual_feed('2026-02-01', [
                make_cluster_item(
                    'c1', 'Wide Coverage Story',
                    entities=['topic'],
                    buckets=['news'],
                    domains=['a.com', 'b.com', 'c.com'],
                    sources=['A', 'B', 'C'],
                )
            ])
            tracker.update_from_dual_feed(feed, '2026-02-01')
            
            signal = list(tracker.signals.values())[0]
            assert signal.metrics.coverage_domains_7d == 3
            assert signal.metrics.coverage_sources_7d == 3


class TestStatePersistence:
    """Test state save/load."""
    
    def test_state_persists_across_tracker_instances(self):
        """State should be loaded from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            signals_dir = Path(tmpdir)
            
            # First tracker: create signal
            tracker1 = SignalTracker(signals_dir=signals_dir, use_embeddings=False)
            feed = make_dual_feed('2026-02-01', [
                make_cluster_item('c1', 'Persistent Topic', ['x'], ['y'])
            ])
            tracker1.update_from_dual_feed(feed, '2026-02-01')
            
            signal_id = list(tracker1.signals.keys())[0]
            
            # Second tracker: should load state
            tracker2 = SignalTracker(signals_dir=signals_dir, use_embeddings=False)
            
            assert len(tracker2.signals) == 1
            assert signal_id in tracker2.signals
            assert tracker2.signals[signal_id].first_seen_date == '2026-02-01'
    
    def test_snapshot_created(self):
        """Daily snapshot should be created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            signals_dir = Path(tmpdir)
            tracker = SignalTracker(signals_dir=signals_dir, use_embeddings=False)
            
            feed = make_dual_feed('2026-02-09', [
                make_cluster_item('c1', 'Topic', ['e'], ['b'])
            ])
            tracker.update_from_dual_feed(feed, '2026-02-09')
            
            snapshot_file = signals_dir / 'signals_snapshot_2026-02-09.json'
            assert snapshot_file.exists()
            
            with open(snapshot_file) as f:
                snapshot = json.load(f)
            
            assert snapshot['date'] == '2026-02-09'
            assert 'top_signals' in snapshot
            assert 'stats' in snapshot


def run_tests():
    """Run all tests."""
    print("\n=== SIGNAL TRACKER TESTS ===\n")
    
    # Data structures
    t = TestSignalEventSerialization()
    t.test_to_dict_and_back()
    t.test_json_serializable()
    print("[PASS] SignalEvent serialization tests")
    
    t = TestSignalSerialization()
    t.test_to_dict_and_back()
    t.test_without_embedding()
    print("[PASS] Signal serialization tests")
    
    # Helpers
    t = TestJaccardOverlap()
    t.test_identical_sets()
    t.test_disjoint_sets()
    t.test_partial_overlap()
    t.test_empty_sets()
    print("[PASS] Jaccard overlap tests")
    
    t = TestSignalNaming()
    t.test_entity_and_bucket()
    t.test_entity_only()
    t.test_bucket_only()
    t.test_empty_inputs()
    print("[PASS] Signal naming tests")
    
    t = TestDaysBetween()
    t.test_same_day()
    t.test_different_days()
    print("[PASS] Days between tests")
    
    t = TestSignalIdGeneration()
    t.test_stable_id()
    t.test_different_inputs()
    t.test_id_length()
    print("[PASS] Signal ID tests")
    
    # Integration
    t = TestSignalCreation()
    t.test_creates_signal_from_new_cluster()
    t.test_singleton_creates_signal()
    print("[PASS] Signal creation tests")
    
    t = TestSignalLinking()
    t.test_links_similar_clusters_across_days()
    t.test_creates_new_signal_for_different_topic()
    t.test_does_not_link_after_max_gap()
    print("[PASS] Signal linking tests")
    
    t = TestMetricsComputation()
    t.test_mentions_count()
    t.test_velocity_increases_with_activity()
    t.test_coverage_domains()
    print("[PASS] Metrics computation tests")
    
    t = TestStatePersistence()
    t.test_state_persists_across_tracker_instances()
    t.test_snapshot_created()
    print("[PASS] State persistence tests")
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
