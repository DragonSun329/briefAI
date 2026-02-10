"""
Tests for Cluster Ranker.

Tests:
1. Rank score includes coverage and confidence bonuses for clusters
2. Singleton rank score equals gravity score (no bonuses)
3. Sorting mixes clusters and singletons correctly
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import json

from utils.cluster_ranker import (
    compute_cluster_rank_score,
    rank_feed,
    FeedItem,
)


class MockCluster:
    """Mock StoryCluster for testing."""
    
    def __init__(
        self,
        cluster_id: str,
        gravity_score: float,
        confidence: float,
        related_count: int = 2,
        domains: int = 3,
    ):
        self.cluster_id = cluster_id
        self.canonical_story = {
            'title': f'Cluster {cluster_id}',
            'url': f'https://{cluster_id}.com/article',
            'source': 'TestSource',
            'gravity_score': gravity_score,
            'tldr': 'Test summary',
            'gravity_details': {'key_insight': 'Test insight'},
        }
        self.related_stories = [
            {
                'title': f'Related {i}',
                'url': f'https://related{i}.com/post',
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


class TestRankScoreFormula:
    """Test rank score computation formula."""
    
    def test_cluster_gets_bonuses(self):
        """Clusters should get coverage/entropy/confidence bonuses."""
        result = compute_cluster_rank_score(
            gravity_score=6.0,
            unique_domain_count=5,
            domain_entropy=1.5,
            cluster_confidence=0.8,
        )
        
        # rank_score should be higher than gravity_score
        assert result['rank_score'] > 6.0
        assert result['coverage_bonus'] > 0
        assert result['entropy_bonus'] > 0
        assert result['confidence_bonus'] > 0
    
    def test_zero_stats_no_bonus(self):
        """With zero stats, rank_score should equal gravity_score."""
        result = compute_cluster_rank_score(
            gravity_score=5.0,
            unique_domain_count=0,
            domain_entropy=0,
            cluster_confidence=0,
        )
        
        assert result['rank_score'] == 5.0
        assert result['coverage_bonus'] == 0
        assert result['entropy_bonus'] == 0
        assert result['confidence_bonus'] == 0
    
    def test_rank_score_clamped_to_ten(self):
        """Rank score should be clamped to max 10."""
        result = compute_cluster_rank_score(
            gravity_score=9.5,
            unique_domain_count=100,
            domain_entropy=5.0,
            cluster_confidence=1.0,
        )
        
        assert result['rank_score'] <= 10.0
    
    def test_higher_confidence_means_higher_rank(self):
        """Higher confidence should increase rank score."""
        low_conf = compute_cluster_rank_score(
            gravity_score=6.0,
            unique_domain_count=3,
            domain_entropy=1.0,
            cluster_confidence=0.3,
        )
        
        high_conf = compute_cluster_rank_score(
            gravity_score=6.0,
            unique_domain_count=3,
            domain_entropy=1.0,
            cluster_confidence=0.9,
        )
        
        assert high_conf['rank_score'] > low_conf['rank_score']


class TestSingletonNoBonuses:
    """Test that singletons don't receive bonuses."""
    
    def test_singleton_rank_equals_gravity(self):
        """Singleton rank_score should equal gravity_score."""
        singleton = {
            'title': 'Single Article',
            'url': 'https://example.com/single',
            'source': 'Example',
            'gravity_score': 6.5,
            'gravity_details': {'key_insight': 'Some insight'},
        }
        
        feed = rank_feed([], [singleton])
        
        assert len(feed['items']) == 1
        item = feed['items'][0]
        
        assert item['item_type'] == 'singleton'
        assert item['rank_score'] == item['gravity_score']
        assert item['rank_score'] == 6.5
    
    def test_singleton_has_no_coverage_bonus(self):
        """Singletons should not have coverage/entropy/confidence bonuses."""
        singleton = {'title': 'Test', 'url': 'https://a.com', 'gravity_score': 5.0}
        
        feed = rank_feed([], [singleton])
        item = feed['items'][0]
        
        # Singletons don't have these fields
        assert 'coverage_bonus' not in item
        assert 'entropy_bonus' not in item
        assert 'confidence_bonus' not in item


class TestFeedSorting:
    """Test that feed is sorted correctly."""
    
    def test_sorted_by_rank_score_desc(self):
        """Feed items should be sorted by rank_score descending."""
        clusters = [
            MockCluster('low', gravity_score=4.0, confidence=0.3),
            MockCluster('high', gravity_score=7.0, confidence=0.9),
            MockCluster('mid', gravity_score=5.5, confidence=0.6),
        ]
        singletons = [
            {'title': 'S1', 'url': 'https://s1.com', 'gravity_score': 6.0},
            {'title': 'S2', 'url': 'https://s2.com', 'gravity_score': 3.0},
        ]
        
        feed = rank_feed(clusters, singletons)
        
        scores = [item['rank_score'] for item in feed['items']]
        assert scores == sorted(scores, reverse=True), f"Not sorted: {scores}"
    
    def test_high_cluster_beats_low_singleton(self):
        """High-scoring cluster should rank above low-scoring singleton."""
        clusters = [MockCluster('high', gravity_score=7.0, confidence=0.9)]
        singletons = [{'title': 'Low', 'url': 'https://a.com', 'gravity_score': 3.0}]
        
        feed = rank_feed(clusters, singletons)
        
        # Cluster should be first
        assert feed['items'][0]['item_type'] == 'cluster'
        assert feed['items'][0]['cluster_id'] == 'high'
    
    def test_high_singleton_can_beat_low_cluster(self):
        """High-scoring singleton can outrank low-scoring cluster."""
        clusters = [MockCluster('low', gravity_score=3.0, confidence=0.2)]
        singletons = [{'title': 'High', 'url': 'https://a.com', 'gravity_score': 8.0}]
        
        feed = rank_feed(clusters, singletons)
        
        # Singleton should be first (8.0 > ~3.5 with bonuses)
        assert feed['items'][0]['item_type'] == 'singleton'
    
    def test_mixed_feed_contains_both_types(self):
        """Feed should contain both clusters and singletons."""
        clusters = [MockCluster('c1', gravity_score=6.0, confidence=0.8)]
        singletons = [{'title': 'S1', 'url': 'https://a.com', 'gravity_score': 5.0}]
        
        feed = rank_feed(clusters, singletons)
        
        types = {item['item_type'] for item in feed['items']}
        assert 'cluster' in types
        assert 'singleton' in types


class TestFeedFormat:
    """Test feed output format."""
    
    def test_feed_has_required_fields(self):
        """Feed should have version, date, generated_at, summary, items."""
        feed = rank_feed([], [])
        
        assert 'version' in feed
        assert feed['version'] == '2.1'
        assert 'date' in feed
        assert 'generated_at' in feed
        assert 'summary' in feed
        assert 'items' in feed
    
    def test_feed_summary_counts(self):
        """Feed summary should correctly count clusters and singletons."""
        clusters = [
            MockCluster('c1', gravity_score=6.0, confidence=0.8),
            MockCluster('c2', gravity_score=5.0, confidence=0.7),
        ]
        singletons = [
            {'title': 'S1', 'url': 'https://a.com', 'gravity_score': 5.0},
            {'title': 'S2', 'url': 'https://b.com', 'gravity_score': 4.0},
            {'title': 'S3', 'url': 'https://c.com', 'gravity_score': 3.0},
        ]
        
        feed = rank_feed(clusters, singletons)
        
        assert feed['summary']['clusters'] == 2
        assert feed['summary']['singletons'] == 3
        assert feed['summary']['total_items'] == 5
    
    def test_feed_is_json_serializable(self):
        """Feed output should be JSON-serializable."""
        clusters = [MockCluster('c1', gravity_score=6.0, confidence=0.8)]
        singletons = [{'title': 'S1', 'url': 'https://a.com', 'gravity_score': 5.0}]
        
        feed = rank_feed(clusters, singletons)
        
        # Should not raise
        json_str = json.dumps(feed, default=str)
        assert len(json_str) > 0
    
    def test_cluster_item_has_bonuses(self):
        """Cluster items should include bonus breakdowns."""
        clusters = [MockCluster('c1', gravity_score=6.0, confidence=0.8)]
        
        feed = rank_feed(clusters, [])
        item = feed['items'][0]
        
        assert 'coverage_bonus' in item
        assert 'entropy_bonus' in item
        assert 'confidence_bonus' in item
        assert 'unique_domains' in item
        assert 'domain_entropy' in item


def run_tests():
    """Run all tests."""
    print("\n=== CLUSTER RANKER TESTS ===\n")
    
    # Rank score formula
    t = TestRankScoreFormula()
    t.test_cluster_gets_bonuses()
    t.test_zero_stats_no_bonus()
    t.test_rank_score_clamped_to_ten()
    t.test_higher_confidence_means_higher_rank()
    print("[PASS] Rank score formula tests")
    
    # Singleton no bonuses
    t = TestSingletonNoBonuses()
    t.test_singleton_rank_equals_gravity()
    t.test_singleton_has_no_coverage_bonus()
    print("[PASS] Singleton no bonus tests")
    
    # Sorting
    t = TestFeedSorting()
    t.test_sorted_by_rank_score_desc()
    t.test_high_cluster_beats_low_singleton()
    t.test_high_singleton_can_beat_low_cluster()
    t.test_mixed_feed_contains_both_types()
    print("[PASS] Feed sorting tests")
    
    # Format
    t = TestFeedFormat()
    t.test_feed_has_required_fields()
    t.test_feed_summary_counts()
    t.test_feed_is_json_serializable()
    t.test_cluster_item_has_bonuses()
    print("[PASS] Feed format tests")
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
