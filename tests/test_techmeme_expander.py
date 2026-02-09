"""
Tests for TechMeme Expander.

Tests:
1. Canonical articles are always included
2. Related link count is limited by max_related
3. Duplicate URLs are removed
4. Required fields are present in output
5. Homepage links are skipped by default
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from utils.techmeme_expander import (
    expand_techmeme_stories,
    normalize_url,
    generate_story_id,
    filter_ai_relevant_candidates,
    group_candidates_by_story,
)


class TestNormalizeUrl:
    """Test URL normalization."""
    
    def test_strips_tracking_params(self):
        """Tracking parameters should be stripped."""
        url = "https://example.com/article?utm_source=twitter&id=123"
        normalized = normalize_url(url)
        
        assert 'utm_source' not in normalized
        assert 'id=123' in normalized
    
    def test_lowercases_domain(self):
        """Domain should be lowercased."""
        url = "HTTPS://WWW.EXAMPLE.COM/Page"
        normalized = normalize_url(url)
        
        assert 'example.com' in normalized
        assert 'WWW' not in normalized
    
    def test_strips_www(self):
        """www prefix should be stripped."""
        url = "https://www.example.com/article"
        normalized = normalize_url(url)
        
        assert 'www.' not in normalized
        assert 'example.com' in normalized
    
    def test_handles_empty(self):
        """Empty/None URLs should return empty string."""
        assert normalize_url('') == ''
        assert normalize_url(None) == ''
    
    def test_strips_trailing_slash(self):
        """Trailing slashes should be stripped."""
        url = "https://example.com/path/"
        normalized = normalize_url(url)
        
        assert not normalized.endswith('/path/')
        assert '/path' in normalized
    
    def test_preserves_root_slash(self):
        """Root path should keep its slash."""
        url = "https://example.com/"
        normalized = normalize_url(url)
        
        # Root path should be preserved as /
        assert normalized.endswith('/')


class TestGenerateStoryId:
    """Test story ID generation."""
    
    def test_same_url_same_id(self):
        """Same URL should produce same ID."""
        id1 = generate_story_id('https://example.com/article')
        id2 = generate_story_id('https://example.com/article')
        
        assert id1 == id2
    
    def test_different_urls_different_ids(self):
        """Different URLs should produce different IDs."""
        id1 = generate_story_id('https://example.com/article')
        id2 = generate_story_id('https://other.com/article')
        
        assert id1 != id2
    
    def test_id_length(self):
        """Story ID should be 12 characters."""
        story_id = generate_story_id('https://example.com/article')
        assert len(story_id) == 12
    
    def test_uses_title_if_no_url(self):
        """Should use title as fallback."""
        id1 = generate_story_id('', 'OpenAI launches GPT-5')
        id2 = generate_story_id('', 'OpenAI launches GPT-5')
        
        assert id1 == id2
        assert len(id1) == 12


class TestExpandIncludesCanonical:
    """Test that canonical articles are included."""
    
    def test_includes_canonical(self):
        """Expansion should include the canonical article."""
        stories = [
            {
                'title': 'Test Story',
                'url': 'https://example.com/story',
                'source': 'Example',
                'related': [],
                'ai_relevance': 0.8,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories)
        
        assert len(candidates) == 1
        assert candidates[0]['role'] == 'canonical'
        assert candidates[0]['title'] == 'Test Story'
    
    def test_canonical_inherits_ai_relevance(self):
        """Canonical should inherit ai_relevance."""
        stories = [
            {
                'title': 'Test',
                'url': 'https://example.com/story',
                'source': 'Example',
                'related': [],
                'ai_relevance': 0.75,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories)
        
        assert candidates[0]['ai_relevance'] == 0.75


class TestLimitsRelated:
    """Test that max_related is respected."""
    
    def test_default_limit(self):
        """Default max_related should be 8."""
        stories = [
            {
                'title': 'Main Story',
                'url': 'https://main.com/story',
                'source': 'Main',
                'related': [
                    {'url': f'https://r{i}.com/article', 'source': f'R{i}', 'title': f'Related {i}'}
                    for i in range(20)
                ],
                'ai_relevance': 0.5,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories)
        
        # 1 canonical + 8 related = 9
        assert len(candidates) == 9
    
    def test_custom_limit(self):
        """Custom max_related should be respected."""
        stories = [
            {
                'title': 'Main Story',
                'url': 'https://main.com/story',
                'source': 'Main',
                'related': [
                    {'url': f'https://r{i}.com/article', 'source': f'R{i}', 'title': f'Related {i}'}
                    for i in range(20)
                ],
                'ai_relevance': 0.5,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories, max_related=3)
        
        # 1 canonical + 3 related = 4
        assert len(candidates) == 4
    
    def test_zero_related(self):
        """max_related=0 should only include canonical."""
        stories = [
            {
                'title': 'Main Story',
                'url': 'https://main.com/story',
                'source': 'Main',
                'related': [
                    {'url': 'https://r.com/article', 'source': 'R', 'title': 'Related'}
                ],
                'ai_relevance': 0.5,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories, max_related=0)
        
        assert len(candidates) == 1
        assert candidates[0]['role'] == 'canonical'


class TestDedupUrls:
    """Test URL deduplication."""
    
    def test_removes_exact_duplicates(self):
        """Exact duplicate URLs should be removed."""
        stories = [
            {
                'title': 'Story 1',
                'url': 'https://example.com/story',
                'source': 'Example',
                'related': [
                    {'url': 'https://example.com/story', 'source': 'Dupe', 'title': 'Dupe'},
                ],
                'ai_relevance': 0.5,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories)
        
        # Only canonical should be included
        assert len(candidates) == 1
        assert candidates[0]['role'] == 'canonical'
    
    def test_removes_normalized_duplicates(self):
        """URLs that normalize to the same should be removed."""
        stories = [
            {
                'title': 'Story 1',
                'url': 'https://example.com/story',
                'source': 'Example',
                'related': [
                    {'url': 'https://example.com/story?utm_source=foo', 'source': 'Dupe', 'title': 'Dupe'},
                    {'url': 'https://WWW.example.com/story', 'source': 'Dupe2', 'title': 'Dupe2'},
                ],
                'ai_relevance': 0.5,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories)
        
        # Only canonical should be included
        assert len(candidates) == 1
    
    def test_keeps_different_urls(self):
        """Different URLs should all be kept."""
        stories = [
            {
                'title': 'Story 1',
                'url': 'https://example.com/story',
                'source': 'Example',
                'related': [
                    {'url': 'https://other.com/different', 'source': 'Other', 'title': 'Different'},
                    {'url': 'https://third.com/another', 'source': 'Third', 'title': 'Another'},
                ],
                'ai_relevance': 0.5,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories)
        
        assert len(candidates) == 3
        urls = {c['url'] for c in candidates}
        assert 'https://example.com/story' in urls
        assert 'https://other.com/different' in urls
        assert 'https://third.com/another' in urls


class TestRoleFieldsPresent:
    """Test that required fields are present."""
    
    def test_all_fields_present(self):
        """All required fields should be present."""
        stories = [
            {
                'title': 'Main Story',
                'url': 'https://main.com/story',
                'source': 'Main',
                'related': [
                    {'url': 'https://related.com/article', 'source': 'Related', 'title': 'Related Story'},
                ],
                'ai_relevance': 0.75,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories)
        
        required_fields = [
            'story_id', 'role', 'title', 'url', 'source',
            'published_at', 'scraped_at', 'ai_relevance',
            'parent_story_title', 'source_name', 'signal_type'
        ]
        
        for candidate in candidates:
            for field in required_fields:
                assert field in candidate, f"Missing field: {field}"
    
    def test_canonical_parent_is_none(self):
        """Canonical articles should have parent_story_title=None."""
        stories = [
            {
                'title': 'Main Story',
                'url': 'https://main.com/story',
                'source': 'Main',
                'related': [],
                'ai_relevance': 0.75,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories)
        canonical = candidates[0]
        
        assert canonical['parent_story_title'] is None
    
    def test_related_has_parent(self):
        """Related articles should have parent_story_title set."""
        stories = [
            {
                'title': 'Main Story',
                'url': 'https://main.com/story',
                'source': 'Main',
                'related': [
                    {'url': 'https://related.com/article', 'source': 'Related', 'title': 'Related'},
                ],
                'ai_relevance': 0.75,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories)
        related = [c for c in candidates if c['role'] == 'related'][0]
        
        assert related['parent_story_title'] == 'Main Story'
    
    def test_source_name_and_signal_type(self):
        """source_name and signal_type should be set correctly."""
        stories = [
            {
                'title': 'Test',
                'url': 'https://example.com/story',
                'source': 'Example',
                'related': [],
                'ai_relevance': 0.5,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories)
        
        assert candidates[0]['source_name'] == 'techmeme'
        assert candidates[0]['signal_type'] == 'techmeme_story_expanded'


class TestSkipsHomepageLinks:
    """Test homepage link filtering."""
    
    def test_skips_homepage_by_default(self):
        """Homepage links should be skipped by default."""
        stories = [
            {
                'title': 'Main Story',
                'url': 'https://main.com/story',
                'source': 'Main',
                'related': [
                    {'url': 'https://bloomberg.com/', 'source': 'Bloomberg'},
                    {'url': 'https://reuters.com', 'source': 'Reuters'},
                ],
                'ai_relevance': 0.5,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories)
        
        # Only canonical
        assert len(candidates) == 1
    
    def test_skips_links_without_title(self):
        """Links without titles are skipped by default."""
        stories = [
            {
                'title': 'Main Story',
                'url': 'https://main.com/story',
                'source': 'Main',
                'related': [
                    {'url': 'https://other.com/article', 'source': 'Other'},  # No title
                ],
                'ai_relevance': 0.5,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories)
        
        # Only canonical (related has no title and looks like homepage)
        # Actually this should still include it if it's not a homepage
        # Let me check the logic...
        urls = [c['url'] for c in candidates]
        # The related link has a path, so it should be included with constructed title
        # Wait, looking at the code again - it skips if no title AND not include_source_only_links
        assert len(candidates) == 1  # Only canonical since no title
    
    def test_includes_homepage_when_requested(self):
        """Homepage links should be included when requested."""
        stories = [
            {
                'title': 'Main Story',
                'url': 'https://main.com/story',
                'source': 'Main',
                'related': [
                    {'url': 'https://bloomberg.com/', 'source': 'Bloomberg'},
                ],
                'ai_relevance': 0.5,
                'scraped_at': '2026-02-09T10:00:00Z',
            }
        ]
        
        candidates = expand_techmeme_stories(stories, include_source_only_links=True)
        
        # Canonical + homepage link
        assert len(candidates) == 2


class TestFilterAiRelevant:
    """Test AI relevance filtering."""
    
    def test_filters_below_threshold(self):
        """Candidates below threshold should be filtered."""
        candidates = [
            {'title': 'A', 'ai_relevance': 0.8},
            {'title': 'B', 'ai_relevance': 0.2},
            {'title': 'C', 'ai_relevance': 0.5},
        ]
        
        filtered = filter_ai_relevant_candidates(candidates, min_relevance=0.4)
        
        assert len(filtered) == 2
        titles = {c['title'] for c in filtered}
        assert 'A' in titles
        assert 'C' in titles
        assert 'B' not in titles
    
    def test_zero_threshold_keeps_all(self):
        """Zero threshold should keep all candidates."""
        candidates = [
            {'title': 'A', 'ai_relevance': 0.0},
            {'title': 'B', 'ai_relevance': 0.5},
        ]
        
        filtered = filter_ai_relevant_candidates(candidates, min_relevance=0.0)
        
        assert len(filtered) == 2


class TestGroupCandidates:
    """Test grouping by story ID."""
    
    def test_groups_by_story_id(self):
        """Candidates should be grouped by story_id."""
        candidates = [
            {'story_id': 'abc123', 'role': 'canonical', 'title': 'Main'},
            {'story_id': 'abc123', 'role': 'related', 'title': 'Related 1'},
            {'story_id': 'xyz789', 'role': 'canonical', 'title': 'Other'},
        ]
        
        groups = group_candidates_by_story(candidates)
        
        assert len(groups) == 2
        assert len(groups['abc123']) == 2
        assert len(groups['xyz789']) == 1


def run_tests():
    """Run all tests."""
    print("\n=== TECHMEME EXPANDER TESTS ===\n")
    
    # URL normalization
    t = TestNormalizeUrl()
    t.test_strips_tracking_params()
    t.test_lowercases_domain()
    t.test_strips_www()
    t.test_handles_empty()
    t.test_strips_trailing_slash()
    t.test_preserves_root_slash()
    print("[PASS] URL normalization tests")
    
    # Story ID generation
    t = TestGenerateStoryId()
    t.test_same_url_same_id()
    t.test_different_urls_different_ids()
    t.test_id_length()
    t.test_uses_title_if_no_url()
    print("[PASS] Story ID tests")
    
    # Canonical inclusion
    t = TestExpandIncludesCanonical()
    t.test_includes_canonical()
    t.test_canonical_inherits_ai_relevance()
    print("[PASS] Canonical inclusion tests")
    
    # Related limits
    t = TestLimitsRelated()
    t.test_default_limit()
    t.test_custom_limit()
    t.test_zero_related()
    print("[PASS] Related limit tests")
    
    # Deduplication
    t = TestDedupUrls()
    t.test_removes_exact_duplicates()
    t.test_removes_normalized_duplicates()
    t.test_keeps_different_urls()
    print("[PASS] Deduplication tests")
    
    # Field presence
    t = TestRoleFieldsPresent()
    t.test_all_fields_present()
    t.test_canonical_parent_is_none()
    t.test_related_has_parent()
    t.test_source_name_and_signal_type()
    print("[PASS] Field presence tests")
    
    # Homepage filtering
    t = TestSkipsHomepageLinks()
    t.test_skips_homepage_by_default()
    t.test_skips_links_without_title()
    t.test_includes_homepage_when_requested()
    print("[PASS] Homepage filtering tests")
    
    # AI relevance filter
    t = TestFilterAiRelevant()
    t.test_filters_below_threshold()
    t.test_zero_threshold_keeps_all()
    print("[PASS] AI relevance filter tests")
    
    # Grouping
    t = TestGroupCandidates()
    t.test_groups_by_story_id()
    print("[PASS] Grouping tests")
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
