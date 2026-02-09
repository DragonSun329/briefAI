"""
Tests for Dual Feed Builder.

Tests:
1. Dual feed format matches expected schema
2. EVENT and THEME feeds are ranked independently
3. Theme scoring uses reduced bonus weights
4. Feed items are sorted correctly
5. top_k limiting works

No network calls - uses synthetic clusters and singletons.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import json
from datetime import datetime

from utils.cluster_ranker import (
    build_dual_feed,
    compute_cluster_rank_score,
    compute_theme_rank_score,
    print_dual_feed_summary,
)


class MockCluster:
    """Mock StoryCluster for testing."""
    
    def __init__(
        self,
        cluster_id: str,
        gravity_score: float,
        confidence: float,
        related_count: int = 2,
        title: str = None,
    ):
        self.cluster_id = cluster_id
        self.canonical_story = {
            'title': title or f'Cluster {cluster_id}',
            'url': f'https://{cluster_id}.com/article',
            'source': 'TestSource',
            'gravity_score': gravity_score,
            'tldr': 'Test summary',
            'gravity_details': {'key_insight': 'Test insight'},
        }
        self.related_stories = [
            {
                'title': f'Related {i}',
                'url': f'https://related{i}-{cluster_id}.com/post',
                'source': f'Source{i}',
            }
            for i in range(related_count)
        ]
        self.cluster_size = 1 + related_count
        self.cluster_confidence = confidence
        self.avg_pair_similarity = 0.80
        self.max_pair_similarity = 0.85
        self.gate_mix = {'merges_by_entity': related_count}
        self.shared_entities = ['test-entity']
        self.shared_bucket_tags = ['test-bucket']
        self.merge_evidence = ['sim=0.80+entity(test)']


class TestDualFeedFormat:
    """Test dual feed output format."""
    
    def test_has_version_2_2(self):
        """Dual feed should have version 2.2."""
        feed = build_dual_feed([], [], [], [], candidate_count=0)
        assert feed['version'] == '2.2'
    
    def test_has_required_top_level_fields(self):
        """Feed should have all required top-level fields."""
        feed = build_dual_feed([], [], [], [], candidate_count=0)
        
        assert 'version' in feed
        assert 'date' in feed
        assert 'generated_at' in feed
        assert 'summary' in feed
        assert 'top_events' in feed
        assert 'top_themes' in feed
    
    def test_summary_has_candidate_count(self):
        """Summary should include candidate article count."""
        feed = build_dual_feed([], [], [], [], candidate_count=42)
        
        assert feed['summary']['candidate_articles'] == 42
    
    def test_summary_has_event_counts(self):
        """Summary should have events section with cluster/singleton counts."""
        clusters = [MockCluster('e1', 6.0, 0.8)]
        singletons = [{'title': 'S1', 'url': 'https://s1.com', 'gravity_score': 5.0}]
        
        feed = build_dual_feed(clusters, singletons, [], [], candidate_count=2)
        
        assert 'events' in feed['summary']
        assert feed['summary']['events']['clusters'] == 1
        assert feed['summary']['events']['singletons'] == 1
    
    def test_summary_has_theme_counts(self):
        """Summary should have themes section with cluster/singleton counts."""
        clusters = [MockCluster('t1', 6.0, 0.8), MockCluster('t2', 5.5, 0.7)]
        singletons = [
            {'title': 'S1', 'url': 'https://s1.com', 'gravity_score': 5.0},
            {'title': 'S2', 'url': 'https://s2.com', 'gravity_score': 4.0},
        ]
        
        feed = build_dual_feed([], [], clusters, singletons, candidate_count=4)
        
        assert 'themes' in feed['summary']
        assert feed['summary']['themes']['clusters'] == 2
        assert feed['summary']['themes']['singletons'] == 2
    
    def test_top_events_has_items(self):
        """top_events should have items array."""
        feed = build_dual_feed([], [], [], [], candidate_count=0)
        
        assert 'items' in feed['top_events']
        assert isinstance(feed['top_events']['items'], list)
    
    def test_top_themes_has_items(self):
        """top_themes should have items array."""
        feed = build_dual_feed([], [], [], [], candidate_count=0)
        
        assert 'items' in feed['top_themes']
        assert isinstance(feed['top_themes']['items'], list)
    
    def test_json_serializable(self):
        """Feed should be JSON-serializable."""
        clusters = [MockCluster('c1', 6.0, 0.8)]
        singletons = [{'title': 'S1', 'url': 'https://s1.com', 'gravity_score': 5.0}]
        
        feed = build_dual_feed(clusters, singletons, clusters, singletons, candidate_count=2)
        
        # Should not raise
        json_str = json.dumps(feed, default=str)
        assert len(json_str) > 0


class TestIndependentRanking:
    """Test that EVENT and THEME feeds are ranked independently."""
    
    def test_event_and_theme_items_separate(self):
        """EVENT and THEME items should be separate lists."""
        event_clusters = [MockCluster('event1', 7.0, 0.9)]
        theme_clusters = [MockCluster('theme1', 6.0, 0.8)]
        
        feed = build_dual_feed(
            event_clusters, [],
            theme_clusters, [],
            candidate_count=2,
        )
        
        event_ids = {i['cluster_id'] for i in feed['top_events']['items']}
        theme_ids = {i['cluster_id'] for i in feed['top_themes']['items']}
        
        assert 'event1' in event_ids
        assert 'theme1' in theme_ids
        assert 'event1' not in theme_ids
        assert 'theme1' not in event_ids
    
    def test_same_cluster_can_appear_in_both(self):
        """Same cluster object in both feeds should produce separate items."""
        shared = MockCluster('shared', 6.5, 0.85, title='Shared Story')
        
        feed = build_dual_feed(
            [shared], [],
            [shared], [],
            candidate_count=1,
        )
        
        # Should appear in both
        event_ids = [i['cluster_id'] for i in feed['top_events']['items']]
        theme_ids = [i['cluster_id'] for i in feed['top_themes']['items']]
        
        assert 'shared' in event_ids
        assert 'shared' in theme_ids


class TestThemeScoringWeights:
    """Test that THEME scoring uses reduced bonus weights."""
    
    def test_theme_rank_score_different_from_event(self):
        """Theme rank score should be lower due to reduced weights."""
        event_score = compute_cluster_rank_score(
            gravity_score=6.0,
            unique_domain_count=5,
            domain_entropy=1.5,
            cluster_confidence=0.8,
        )
        
        theme_score = compute_theme_rank_score(
            gravity_score=6.0,
            unique_domain_count=5,
            domain_entropy=1.5,
            cluster_confidence=0.8,
        )
        
        # Same inputs, but theme should have lower bonuses
        assert theme_score['rank_score'] < event_score['rank_score']
        assert theme_score['coverage_bonus'] < event_score['coverage_bonus']
        assert theme_score['entropy_bonus'] < event_score['entropy_bonus']
        assert theme_score['confidence_bonus'] < event_score['confidence_bonus']
    
    def test_theme_coverage_bonus_weight(self):
        """Theme coverage bonus should use 0.18 weight."""
        result = compute_theme_rank_score(
            gravity_score=5.0,
            unique_domain_count=10,
            domain_entropy=0,
            cluster_confidence=0,
        )
        
        import math
        expected = 0.18 * math.log1p(10)
        assert abs(result['coverage_bonus'] - expected) < 0.01
    
    def test_theme_entropy_bonus_weight(self):
        """Theme entropy bonus should use 0.12 weight."""
        result = compute_theme_rank_score(
            gravity_score=5.0,
            unique_domain_count=0,
            domain_entropy=2.0,  # max entropy / 2.0 = 1.0
            cluster_confidence=0,
        )
        
        expected = 0.12 * 1.0  # min(1.0, 2.0/2.0) = 1.0
        assert abs(result['entropy_bonus'] - expected) < 0.01
    
    def test_theme_confidence_bonus_weight(self):
        """Theme confidence bonus should use 0.30 weight."""
        result = compute_theme_rank_score(
            gravity_score=5.0,
            unique_domain_count=0,
            domain_entropy=0,
            cluster_confidence=1.0,
        )
        
        expected = 0.30 * 1.0
        assert abs(result['confidence_bonus'] - expected) < 0.01


class TestSorting:
    """Test that feed items are sorted correctly."""
    
    def test_event_items_sorted_by_rank_desc(self):
        """Event items should be sorted by rank_score descending."""
        clusters = [
            MockCluster('low', 4.0, 0.3),
            MockCluster('high', 8.0, 0.9),
            MockCluster('mid', 6.0, 0.6),
        ]
        
        feed = build_dual_feed(clusters, [], [], [], candidate_count=3)
        
        scores = [i['rank_score'] for i in feed['top_events']['items']]
        assert scores == sorted(scores, reverse=True)
        
        # High should be first
        assert feed['top_events']['items'][0]['cluster_id'] == 'high'
    
    def test_theme_items_sorted_by_rank_desc(self):
        """Theme items should be sorted by rank_score descending."""
        clusters = [
            MockCluster('low', 4.0, 0.3),
            MockCluster('high', 8.0, 0.9),
            MockCluster('mid', 6.0, 0.6),
        ]
        
        feed = build_dual_feed([], [], clusters, [], candidate_count=3)
        
        scores = [i['rank_score'] for i in feed['top_themes']['items']]
        assert scores == sorted(scores, reverse=True)
    
    def test_singleton_rank_equals_gravity(self):
        """Singletons should have rank_score = gravity_score."""
        singletons = [
            {'title': 'High', 'url': 'https://high.com', 'gravity_score': 8.0},
            {'title': 'Low', 'url': 'https://low.com', 'gravity_score': 3.0},
        ]
        
        feed = build_dual_feed([], singletons, [], singletons, candidate_count=2)
        
        for section in ['top_events', 'top_themes']:
            for item in feed[section]['items']:
                assert item['rank_score'] == item['gravity_score']


class TestTopKLimiting:
    """Test that top_k limits output."""
    
    def test_respects_top_k_for_events(self):
        """Event items should be limited by top_k."""
        clusters = [MockCluster(f'c{i}', 5.0 + i*0.1, 0.7) for i in range(20)]
        
        feed = build_dual_feed(clusters, [], [], [], top_k=5, candidate_count=20)
        
        assert len(feed['top_events']['items']) == 5
    
    def test_respects_top_k_for_themes(self):
        """Theme items should be limited by top_k."""
        clusters = [MockCluster(f'c{i}', 5.0 + i*0.1, 0.7) for i in range(20)]
        
        feed = build_dual_feed([], [], clusters, [], top_k=5, candidate_count=20)
        
        assert len(feed['top_themes']['items']) == 5
    
    def test_keeps_best_items(self):
        """top_k should keep highest ranked items."""
        clusters = [
            MockCluster('best', 9.0, 0.95),
            MockCluster('worst', 2.0, 0.1),
            MockCluster('mid', 5.0, 0.5),
        ]
        
        feed = build_dual_feed(clusters, [], [], [], top_k=2, candidate_count=3)
        
        ids = {i['cluster_id'] for i in feed['top_events']['items']}
        assert 'best' in ids
        assert 'mid' in ids
        assert 'worst' not in ids
    
    def test_summary_reflects_top_k(self):
        """Summary should show top_k_items count."""
        clusters = [MockCluster(f'c{i}', 5.0, 0.7) for i in range(10)]
        
        feed = build_dual_feed(clusters, [], clusters, [], top_k=3, candidate_count=10)
        
        assert feed['summary']['events']['top_k_items'] == 3
        assert feed['summary']['themes']['top_k_items'] == 3


class TestClusterItemFields:
    """Test that cluster items have expected fields."""
    
    def test_has_cluster_id(self):
        """Cluster items should have cluster_id."""
        clusters = [MockCluster('test123', 6.0, 0.8)]
        feed = build_dual_feed(clusters, [], [], [], candidate_count=1)
        
        item = feed['top_events']['items'][0]
        assert item['cluster_id'] == 'test123'
    
    def test_has_canonical(self):
        """Cluster items should have canonical article."""
        clusters = [MockCluster('test', 6.0, 0.8)]
        feed = build_dual_feed(clusters, [], [], [], candidate_count=1)
        
        item = feed['top_events']['items'][0]
        assert 'canonical' in item
        assert 'title' in item['canonical']
        assert 'url' in item['canonical']
    
    def test_has_related(self):
        """Cluster items should have related articles."""
        clusters = [MockCluster('test', 6.0, 0.8, related_count=3)]
        feed = build_dual_feed(clusters, [], [], [], candidate_count=1)
        
        item = feed['top_events']['items'][0]
        assert 'related' in item
        assert len(item['related']) == 3
    
    def test_has_bonus_breakdown(self):
        """Cluster items should have bonus breakdown."""
        clusters = [MockCluster('test', 6.0, 0.8)]
        feed = build_dual_feed(clusters, [], [], [], candidate_count=1)
        
        item = feed['top_events']['items'][0]
        assert 'coverage_bonus' in item
        assert 'entropy_bonus' in item
        assert 'confidence_bonus' in item
    
    def test_has_domain_metrics(self):
        """Cluster items should have domain metrics."""
        clusters = [MockCluster('test', 6.0, 0.8)]
        feed = build_dual_feed(clusters, [], [], [], candidate_count=1)
        
        item = feed['top_events']['items'][0]
        assert 'unique_domains' in item
        assert 'domain_entropy' in item


class TestSingletonItemFields:
    """Test that singleton items have expected fields."""
    
    def test_has_article(self):
        """Singleton items should have article dict."""
        singletons = [{'title': 'Test', 'url': 'https://t.com', 'gravity_score': 5.0}]
        feed = build_dual_feed([], singletons, [], [], candidate_count=1)
        
        item = feed['top_events']['items'][0]
        assert 'article' in item
        assert item['article']['title'] == 'Test'
    
    def test_item_type_is_singleton(self):
        """Singleton items should have item_type='singleton'."""
        singletons = [{'title': 'Test', 'url': 'https://t.com', 'gravity_score': 5.0}]
        feed = build_dual_feed([], singletons, [], [], candidate_count=1)
        
        item = feed['top_events']['items'][0]
        assert item['item_type'] == 'singleton'


class TestDateHandling:
    """Test date handling."""
    
    def test_uses_provided_date(self):
        """Should use provided target_date."""
        feed = build_dual_feed([], [], [], [], target_date='2026-02-15', candidate_count=0)
        assert feed['date'] == '2026-02-15'
    
    def test_defaults_to_today(self):
        """Should default to today's date."""
        feed = build_dual_feed([], [], [], [], candidate_count=0)
        
        expected = datetime.now().strftime('%Y-%m-%d')
        assert feed['date'] == expected
    
    def test_generated_at_is_iso_format(self):
        """generated_at should be ISO format."""
        feed = build_dual_feed([], [], [], [], candidate_count=0)
        
        # Should parse without error
        datetime.fromisoformat(feed['generated_at'])


def run_tests():
    """Run all tests."""
    print("\n=== DUAL FEED TESTS ===\n")
    
    # Format
    t = TestDualFeedFormat()
    t.test_has_version_2_2()
    t.test_has_required_top_level_fields()
    t.test_summary_has_candidate_count()
    t.test_summary_has_event_counts()
    t.test_summary_has_theme_counts()
    t.test_top_events_has_items()
    t.test_top_themes_has_items()
    t.test_json_serializable()
    print("[PASS] Format tests")
    
    # Independent ranking
    t = TestIndependentRanking()
    t.test_event_and_theme_items_separate()
    t.test_same_cluster_can_appear_in_both()
    print("[PASS] Independent ranking tests")
    
    # Theme scoring weights
    t = TestThemeScoringWeights()
    t.test_theme_rank_score_different_from_event()
    t.test_theme_coverage_bonus_weight()
    t.test_theme_entropy_bonus_weight()
    t.test_theme_confidence_bonus_weight()
    print("[PASS] Theme scoring weight tests")
    
    # Sorting
    t = TestSorting()
    t.test_event_items_sorted_by_rank_desc()
    t.test_theme_items_sorted_by_rank_desc()
    t.test_singleton_rank_equals_gravity()
    print("[PASS] Sorting tests")
    
    # Top-k limiting
    t = TestTopKLimiting()
    t.test_respects_top_k_for_events()
    t.test_respects_top_k_for_themes()
    t.test_keeps_best_items()
    t.test_summary_reflects_top_k()
    print("[PASS] Top-k limiting tests")
    
    # Cluster item fields
    t = TestClusterItemFields()
    t.test_has_cluster_id()
    t.test_has_canonical()
    t.test_has_related()
    t.test_has_bonus_breakdown()
    t.test_has_domain_metrics()
    print("[PASS] Cluster item field tests")
    
    # Singleton item fields
    t = TestSingletonItemFields()
    t.test_has_article()
    t.test_item_type_is_singleton()
    print("[PASS] Singleton item field tests")
    
    # Date handling
    t = TestDateHandling()
    t.test_uses_provided_date()
    t.test_defaults_to_today()
    t.test_generated_at_is_iso_format()
    print("[PASS] Date handling tests")
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
