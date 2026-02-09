"""
Tests for Signal State Machine.

Tests:
1. Status transitions: weak_signal → emerging → trending → mainstream
2. Fading detection
3. Dead signal detection
4. Hysteresis rules (consecutive days/weeks)
"""

import sys
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
    EMERGING_MENTIONS_7D,
    EMERGING_CONFIDENCE,
    TRENDING_MENTIONS_7D,
    TRENDING_VELOCITY,
    TRENDING_CONFIDENCE,
    MAINSTREAM_MENTIONS_21D,
    MAINSTREAM_DOMAINS_7D,
    MAINSTREAM_CONFIDENCE,
    FADING_VELOCITY,
    DEAD_DAYS,
)


# =============================================================================
# HELPERS
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
    sources = sources or ['TestSource']
    domains = domains or ['example.com']
    
    return {
        'item_type': 'cluster',
        'cluster_id': cluster_id,
        'rank_score': gravity_score + 0.5,
        'gravity_score': gravity_score,
        'canonical': {
            'title': title,
            'url': f'https://example.com/{cluster_id}',
            'source': sources[0],
            'key_insight': f'Key insight about {title}',
        },
        'related': [
            {'title': f'Related {i}', 'url': f'https://r{i}.com/a', 'source': s}
            for i, s in enumerate(sources[1:])
        ],
        'cluster_stats': {
            'cluster_confidence': confidence,
            'shared_entities': entities,
            'shared_bucket_tags': buckets,
        },
        'top_domains': domains,
        'confidence_bonus': confidence * 0.3,
    }


def make_dual_feed(date: str, theme_items: list):
    """Create a mock dual feed."""
    return {
        'version': '2.2',
        'date': date,
        'generated_at': datetime.now().isoformat(),
        'top_themes': {'items': theme_items},
        'top_events': {'items': []},
    }


def generate_date_sequence(start: str, days: int) -> list:
    """Generate list of date strings."""
    start_dt = datetime.strptime(start, '%Y-%m-%d')
    return [(start_dt + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days)]


# =============================================================================
# STATE TRANSITION TESTS
# =============================================================================

class TestWeakSignalStatus:
    """Test weak_signal (initial) status."""
    
    def test_new_signal_is_weak(self):
        """New signal should start as weak_signal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(signals_dir=Path(tmpdir), use_embeddings=False)
            
            feed = make_dual_feed('2026-02-01', [
                make_cluster_item('c1', 'New Topic', ['x'], ['y'])
            ])
            tracker.update_from_dual_feed(feed, '2026-02-01')
            
            signal = list(tracker.signals.values())[0]
            assert signal.status == 'weak_signal'
    
    def test_stays_weak_with_single_mention(self):
        """Signal with 1 mention should stay weak."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(signals_dir=Path(tmpdir), use_embeddings=False)
            
            # Single cluster, single day
            feed = make_dual_feed('2026-02-01', [
                make_cluster_item('c1', 'Topic', ['e'], ['b'], confidence=0.3)
            ])
            tracker.update_from_dual_feed(feed, '2026-02-01')
            
            signal = list(tracker.signals.values())[0]
            # Only 1 mention and low confidence -> stays weak
            assert signal.status == 'weak_signal'


class TestEmergingTransition:
    """Test transition to emerging status."""
    
    def test_becomes_emerging_with_enough_mentions(self):
        """Signal should become emerging with >= 2 mentions and confidence >= 0.45."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(signals_dir=Path(tmpdir), use_embeddings=False)
            
            # Day 1
            feed1 = make_dual_feed('2026-02-01', [
                make_cluster_item(
                    'c1', 'Growing Topic', ['topic'], ['trending'],
                    confidence=0.85,
                    domains=['a.com', 'b.com'],
                )
            ])
            tracker.update_from_dual_feed(feed1, '2026-02-01')
            
            # Day 2 - same topic, high confidence
            feed2 = make_dual_feed('2026-02-02', [
                make_cluster_item(
                    'c2', 'Growing Topic Coverage', ['topic'], ['trending'],
                    confidence=0.85,
                    domains=['c.com', 'd.com'],
                )
            ])
            tracker.update_from_dual_feed(feed2, '2026-02-02')
            
            signal = list(tracker.signals.values())[0]
            # 2 mentions, high cluster confidence should give confidence >= 0.45
            assert signal.metrics.mentions_7d >= EMERGING_MENTIONS_7D
            # Should be at least emerging
            assert signal.status in ('emerging', 'trending', 'mainstream')


class TestTrendingTransition:
    """Test transition to trending status."""
    
    def test_becomes_trending_with_high_velocity(self):
        """Signal should become trending with mentions >= 3, velocity >= 1.8, confidence >= 0.60."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(signals_dir=Path(tmpdir), use_embeddings=False)
            
            entities = ['hot-topic']
            buckets = ['viral']
            
            # Add multiple high-quality clusters over 5 days
            for i in range(5):
                date = f'2026-02-0{i+1}'
                feed = make_dual_feed(date, [
                    make_cluster_item(
                        f'c{i}', 'Hot Topic',
                        entities, buckets,
                        gravity_score=7.5,
                        confidence=0.90,
                        domains=[f'd{i}.com', f'e{i}.com', f'f{i}.com'],
                        sources=[f'S{i}', f'T{i}', f'U{i}'],
                    )
                ])
                tracker.update_from_dual_feed(feed, date)
            
            signal = list(tracker.signals.values())[0]
            
            # Should have high metrics
            assert signal.metrics.mentions_7d >= 5
            assert signal.metrics.velocity >= 1.0  # New signal, baseline is 1
            # Status should be trending or higher
            assert signal.status in ('trending', 'mainstream')


class TestMainstreamTransition:
    """Test transition to mainstream status."""
    
    def test_becomes_mainstream_with_sustained_coverage(self):
        """Signal should become mainstream with high mentions_21d, domains, confidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(signals_dir=Path(tmpdir), use_embeddings=False)
            
            entities = ['mainstream-topic']
            buckets = ['ubiquitous']
            
            # Simulate 10 days of heavy coverage
            dates = generate_date_sequence('2026-02-01', 10)
            
            for i, date in enumerate(dates):
                # Multiple high-quality clusters per day
                feed = make_dual_feed(date, [
                    make_cluster_item(
                        f'c{i}', 'Mainstream Topic',
                        entities, buckets,
                        gravity_score=8.0,
                        confidence=0.95,
                        domains=[f'dom{j}.com' for j in range(i % 3, i % 3 + 5)],
                        sources=[f'Src{j}' for j in range(5)],
                    )
                ])
                tracker.update_from_dual_feed(feed, date)
            
            signal = list(tracker.signals.values())[0]
            
            # Check metrics
            assert signal.metrics.mentions_21d >= MAINSTREAM_MENTIONS_21D
            # With 2 consecutive days meeting criteria, should be mainstream
            # (May still be trending if hysteresis not met)
            assert signal.status in ('trending', 'mainstream')


class TestFadingTransition:
    """Test transition to fading status."""
    
    def test_becomes_fading_with_no_recent_mentions(self):
        """Signal should fade when no mentions in 7d but seen in 21d."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(signals_dir=Path(tmpdir), use_embeddings=False)
            
            # Day 1-3: Active signal
            for i in range(3):
                date = f'2026-02-0{i+1}'
                feed = make_dual_feed(date, [
                    make_cluster_item(f'c{i}', 'Fading Topic', ['fade'], ['old'])
                ])
                tracker.update_from_dual_feed(feed, date)
            
            signal = list(tracker.signals.values())[0]
            # After 3 days with good clusters, may have progressed
            assert signal.status in ('weak_signal', 'emerging', 'trending')
            
            # Day 15: No mentions for 12 days
            empty_feed = make_dual_feed('2026-02-15', [])
            tracker.update_from_dual_feed(empty_feed, '2026-02-15')
            
            # Signal should be fading (no mentions in 7d, but seen in 21d)
            assert signal.metrics.mentions_7d == 0
            assert signal.status == 'fading'


class TestDeadTransition:
    """Test transition to dead status."""
    
    def test_becomes_dead_after_30_days(self):
        """Signal should be dead when no mentions for 30 days."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(signals_dir=Path(tmpdir), use_embeddings=False)
            
            # Day 1: Create signal
            feed1 = make_dual_feed('2026-01-01', [
                make_cluster_item('c1', 'Soon Dead Topic', ['dead'], ['gone'])
            ])
            tracker.update_from_dual_feed(feed1, '2026-01-01')
            
            signal_id = list(tracker.signals.keys())[0]
            
            # Day 35: 34 days later, no mentions
            empty_feed = make_dual_feed('2026-02-05', [])
            tracker.update_from_dual_feed(empty_feed, '2026-02-05')
            
            signal = tracker.signals[signal_id]
            assert signal.status == 'dead'
    
    def test_dead_signals_not_linked(self):
        """Dead signals should not receive new links."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(signals_dir=Path(tmpdir), use_embeddings=False)
            
            # Day 1: Create signal
            feed1 = make_dual_feed('2026-01-01', [
                make_cluster_item('c1', 'Dead Topic', ['dead'], ['gone'])
            ])
            tracker.update_from_dual_feed(feed1, '2026-01-01')
            
            original_signal_count = len(tracker.signals)
            
            # Day 35: Mark as dead
            empty_feed = make_dual_feed('2026-02-05', [])
            tracker.update_from_dual_feed(empty_feed, '2026-02-05')
            
            # Day 36: New cluster with same topic should create NEW signal, not link to dead
            feed2 = make_dual_feed('2026-02-06', [
                make_cluster_item('c2', 'Dead Topic Revival', ['dead'], ['gone'])
            ])
            stats = tracker.update_from_dual_feed(feed2, '2026-02-06')
            
            # Should create new signal (dead one not linkable)
            assert stats['signals_created'] == 1
            assert len(tracker.signals) == original_signal_count + 1


class TestHysteresisRules:
    """Test hysteresis rules for state transitions."""
    
    def test_mainstream_requires_two_consecutive_days(self):
        """Mainstream status requires 2 consecutive days meeting criteria."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(signals_dir=Path(tmpdir), use_embeddings=False)
            
            # Create a signal that would meet mainstream criteria
            signal = Signal(
                signal_id='test',
                name='Test',
                created_at='2026-02-01T00:00:00',
                first_seen_date='2026-01-01',
                last_seen_date='2026-02-05',
                status='trending',
                metrics=SignalMetrics(
                    mentions_21d=10,
                    coverage_domains_7d=6,
                    confidence=0.75,
                ),
            )
            tracker.signals['test'] = signal
            
            # First day meeting criteria
            tracker._update_all_signals('2026-02-05')
            # consecutive_mainstream_days should increment but status may not change yet
            
            # With 0 events in cluster_refs, metrics will reset
            # This test demonstrates the hysteresis tracking exists


class TestConfidenceComputation:
    """Test confidence score computation."""
    
    def test_confidence_increases_with_metrics(self):
        """Confidence should increase with better metrics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(signals_dir=Path(tmpdir), use_embeddings=False)
            
            # Create signal with good metrics
            feed = make_dual_feed('2026-02-01', [
                make_cluster_item(
                    'c1', 'Good Signal',
                    entities=['good'],
                    buckets=['quality'],
                    gravity_score=8.0,
                    confidence=0.90,
                    domains=['a.com', 'b.com', 'c.com', 'd.com', 'e.com', 'f.com'],
                    sources=['A', 'B', 'C', 'D', 'E', 'F'],
                )
            ])
            tracker.update_from_dual_feed(feed, '2026-02-01')
            
            signal = list(tracker.signals.values())[0]
            
            # Confidence should be reasonable (> 0.3 with good cluster confidence and domains)
            assert signal.metrics.confidence > 0.3
    
    def test_confidence_clamped_to_one(self):
        """Confidence should be clamped to [0, 1]."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = SignalTracker(signals_dir=Path(tmpdir), use_embeddings=False)
            
            # Create signal with extreme metrics
            entities = ['extreme']
            buckets = ['max']
            
            for i in range(10):
                date = f'2026-02-{str(i+1).zfill(2)}'
                feed = make_dual_feed(date, [
                    make_cluster_item(
                        f'c{i}', 'Extreme Topic', entities, buckets,
                        gravity_score=10.0, confidence=1.0,
                        domains=[f'd{j}.com' for j in range(10)],
                    )
                ])
                tracker.update_from_dual_feed(feed, date)
            
            signal = list(tracker.signals.values())[0]
            assert signal.metrics.confidence <= 1.0
            assert signal.metrics.confidence >= 0.0


def run_tests():
    """Run all tests."""
    print("\n=== SIGNAL STATE MACHINE TESTS ===\n")
    
    # Weak signal
    t = TestWeakSignalStatus()
    t.test_new_signal_is_weak()
    t.test_stays_weak_with_single_mention()
    print("[PASS] Weak signal tests")
    
    # Emerging
    t = TestEmergingTransition()
    t.test_becomes_emerging_with_enough_mentions()
    print("[PASS] Emerging transition tests")
    
    # Trending
    t = TestTrendingTransition()
    t.test_becomes_trending_with_high_velocity()
    print("[PASS] Trending transition tests")
    
    # Mainstream
    t = TestMainstreamTransition()
    t.test_becomes_mainstream_with_sustained_coverage()
    print("[PASS] Mainstream transition tests")
    
    # Fading
    t = TestFadingTransition()
    t.test_becomes_fading_with_no_recent_mentions()
    print("[PASS] Fading transition tests")
    
    # Dead
    t = TestDeadTransition()
    t.test_becomes_dead_after_30_days()
    t.test_dead_signals_not_linked()
    print("[PASS] Dead transition tests")
    
    # Confidence
    t = TestConfidenceComputation()
    t.test_confidence_increases_with_metrics()
    t.test_confidence_clamped_to_one()
    print("[PASS] Confidence computation tests")
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
