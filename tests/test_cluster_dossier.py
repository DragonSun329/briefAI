"""
Tests for Cluster Dossier Builder.

Tests:
1. Domain extraction and unique count
2. Domain entropy computation
3. Time span hours computation
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime

from utils.cluster_dossier import (
    extract_domain,
    compute_domain_entropy,
    compute_time_span_hours,
    build_cluster_dossier,
    ClusterDossier,
)


class TestDomainExtraction:
    """Test domain extraction and unique counting."""
    
    def test_basic_domain_extraction(self):
        """Test extracting domain from standard URLs."""
        assert extract_domain('https://www.techcrunch.com/article') == 'techcrunch.com'
        assert extract_domain('https://blog.openai.com/post') == 'blog.openai.com'
        assert extract_domain('http://example.org/page') == 'example.org'
    
    def test_www_stripping(self):
        """Test that www. is stripped."""
        assert extract_domain('https://www.example.com/') == 'example.com'
        assert extract_domain('http://www.test.org') == 'test.org'
    
    def test_invalid_urls(self):
        """Test handling of invalid/empty URLs."""
        assert extract_domain('') == 'unknown'
        assert extract_domain(None) == 'unknown'
        assert extract_domain('not a url') == 'unknown'
    
    def test_unique_domain_count_in_dossier(self):
        """Test that dossier correctly counts unique domains."""
        class MockCluster:
            cluster_id = "test123"
            canonical_story = {
                'title': 'Test', 
                'url': 'https://techcrunch.com/article',
                'gravity_score': 6.0
            }
            related_stories = [
                {'title': 'R1', 'url': 'https://theverge.com/post'},
                {'title': 'R2', 'url': 'https://wired.com/story'},
                {'title': 'R3', 'url': 'https://techcrunch.com/other'},  # Duplicate domain
            ]
            cluster_size = 4
            cluster_confidence = 0.8
            avg_pair_similarity = 0.85
            max_pair_similarity = 0.90
            gate_mix = {}
            shared_entities = ['openai']
            shared_bucket_tags = ['ai-news']
            merge_evidence = []
        
        dossier = build_cluster_dossier(MockCluster())
        
        # 3 unique domains: techcrunch, theverge, wired
        assert dossier.cluster_stats['unique_domain_count'] == 3


class TestDomainEntropy:
    """Test domain entropy computation."""
    
    def test_single_domain_zero_entropy(self):
        """Single domain should have zero entropy."""
        assert compute_domain_entropy(['a.com']) == 0.0
    
    def test_empty_list_zero_entropy(self):
        """Empty list should have zero entropy."""
        assert compute_domain_entropy([]) == 0.0
    
    def test_two_equal_domains_entropy_one(self):
        """Two equal-frequency domains should have entropy = 1.0."""
        entropy = compute_domain_entropy(['a.com', 'b.com'])
        assert abs(entropy - 1.0) < 0.01
    
    def test_four_equal_domains_entropy_two(self):
        """Four equal-frequency domains should have entropy = 2.0."""
        entropy = compute_domain_entropy(['a.com', 'b.com', 'c.com', 'd.com'])
        assert abs(entropy - 2.0) < 0.01
    
    def test_skewed_distribution_lower_entropy(self):
        """Skewed distribution should have lower entropy than uniform."""
        uniform = compute_domain_entropy(['a.com', 'b.com', 'c.com', 'd.com'])
        skewed = compute_domain_entropy(['a.com', 'a.com', 'a.com', 'b.com'])
        assert skewed < uniform


class TestTimeSpanHours:
    """Test time span computation."""
    
    def test_basic_time_span(self):
        """Test basic time span calculation."""
        articles = [
            {'published_at': '2026-02-09T10:00:00Z'},
            {'published_at': '2026-02-09T12:00:00Z'},
            {'published_at': '2026-02-09T14:00:00Z'},
        ]
        
        span = compute_time_span_hours(articles)
        assert span == 4.0  # 10:00 to 14:00 = 4 hours
    
    def test_single_article_returns_none(self):
        """Single article should return None."""
        articles = [{'published_at': '2026-02-09T10:00:00Z'}]
        assert compute_time_span_hours(articles) is None
    
    def test_missing_timestamps_returns_none(self):
        """Articles without timestamps should return None."""
        articles = [
            {'title': 'No timestamp'},
            {'title': 'Also no timestamp'},
        ]
        assert compute_time_span_hours(articles) is None
    
    def test_partial_timestamps_still_works(self):
        """Should work if at least 2 articles have timestamps."""
        articles = [
            {'published_at': '2026-02-09T10:00:00Z'},
            {'title': 'No timestamp'},
            {'published_at': '2026-02-09T12:00:00Z'},
        ]
        span = compute_time_span_hours(articles)
        assert span == 2.0


class TestDossierBuilding:
    """Test full dossier building."""
    
    def test_dossier_to_dict_is_json_serializable(self):
        """Test that dossier.to_dict() produces JSON-serializable output."""
        import json
        
        class MockCluster:
            cluster_id = "test123"
            canonical_story = {
                'title': 'Test Article',
                'url': 'https://example.com/article',
                'source': 'Example',
                'gravity_score': 6.5,
                'tldr': 'Test summary',
                'gravity_details': {'key_insight': 'Test insight'},
            }
            related_stories = [
                {'title': 'Related 1', 'url': 'https://other.com/1', 'source': 'Other'},
            ]
            cluster_size = 2
            cluster_confidence = 0.75
            avg_pair_similarity = 0.82
            max_pair_similarity = 0.85
            gate_mix = {'merges_by_entity': 1}
            shared_entities = ['test']
            shared_bucket_tags = ['news']
            merge_evidence = ['sim=0.82+entity(test)']
        
        dossier = build_cluster_dossier(MockCluster())
        
        # Should not raise
        json_str = json.dumps(dossier.to_dict())
        assert len(json_str) > 0
    
    def test_max_related_limit(self):
        """Test that max_related parameter is respected."""
        class MockCluster:
            cluster_id = "test123"
            canonical_story = {'title': 'Main', 'url': 'https://a.com'}
            related_stories = [
                {'title': f'R{i}', 'url': f'https://r{i}.com'}
                for i in range(20)
            ]
            cluster_size = 21
            cluster_confidence = 0.8
            avg_pair_similarity = 0.8
            max_pair_similarity = 0.9
            gate_mix = {}
            shared_entities = []
            shared_bucket_tags = []
            merge_evidence = []
        
        dossier = build_cluster_dossier(MockCluster(), max_related=5)
        assert len(dossier.related) == 5


def run_tests():
    """Run all tests."""
    print("\n=== CLUSTER DOSSIER TESTS ===\n")
    
    # Domain extraction
    t = TestDomainExtraction()
    t.test_basic_domain_extraction()
    t.test_www_stripping()
    t.test_invalid_urls()
    t.test_unique_domain_count_in_dossier()
    print("[PASS] Domain extraction tests")
    
    # Entropy
    t = TestDomainEntropy()
    t.test_single_domain_zero_entropy()
    t.test_empty_list_zero_entropy()
    t.test_two_equal_domains_entropy_one()
    t.test_four_equal_domains_entropy_two()
    t.test_skewed_distribution_lower_entropy()
    print("[PASS] Domain entropy tests")
    
    # Time span
    t = TestTimeSpanHours()
    t.test_basic_time_span()
    t.test_single_article_returns_none()
    t.test_missing_timestamps_returns_none()
    t.test_partial_timestamps_still_works()
    print("[PASS] Time span tests")
    
    # Dossier building
    t = TestDossierBuilding()
    t.test_dossier_to_dict_is_json_serializable()
    t.test_max_related_limit()
    print("[PASS] Dossier building tests")
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
