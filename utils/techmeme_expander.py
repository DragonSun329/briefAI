"""
TechMeme Story Expander - Expand TechMeme stories into flat article candidates.

Part of Gravity Engine v2.2: Dual Event/Theme Feed.

TechMeme stories include a canonical article and related coverage links.
This module expands each story into individual article candidates for
clustering, enabling true multi-source event detection.

Key features:
- Expands canonical + related links into flat candidate list
- Stable story_id generation for tracking
- URL deduplication with normalization
- Inherits ai_relevance from parent story
"""

import hashlib
from typing import List, Dict, Any, Set, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from loguru import logger


# URL parameters to strip for normalization
TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
    'ref', 'referrer', 'source', 'fbclid', 'gclid', 'mc_eid', 'mc_cid',
    '_ga', '_gid', 'share', 'sharetype', 'token', 'accessToken',
    'smid', 'smtyp', 'smprod', 'sf', 's_kwcid', 'ef_id',
}


def normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication.
    
    - Strips tracking parameters
    - Lowercases scheme and domain
    - Removes trailing slashes from path
    
    Args:
        url: Raw URL string
        
    Returns:
        Normalized URL string
    """
    if not url:
        return ""
    
    try:
        parsed = urlparse(url)
        
        # Lowercase scheme and netloc
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        
        # Strip www. prefix for dedup purposes
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        
        # Parse and filter query params
        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=True)
            filtered_params = {
                k: v for k, v in params.items()
                if k.lower() not in TRACKING_PARAMS
            }
            query = urlencode(filtered_params, doseq=True)
        else:
            query = ""
        
        # Normalize path (strip trailing slash unless root)
        path = parsed.path.rstrip('/') if parsed.path != '/' else '/'
        
        # Reconstruct
        normalized = urlunparse((scheme, netloc, path, '', query, ''))
        return normalized
        
    except Exception:
        return url


def generate_story_id(url: str, title: str = "") -> str:
    """
    Generate stable story_id from URL (preferred) or title.
    
    Args:
        url: Canonical URL
        title: Title as fallback
        
    Returns:
        12-character hex hash
    """
    # Prefer URL for stability
    key = normalize_url(url) if url else title
    if not key:
        key = "unknown"
    
    return hashlib.md5(key.encode('utf-8')).hexdigest()[:12]


def expand_techmeme_stories(
    stories: List[Dict[str, Any]],
    max_related: int = 8,
    include_source_only_links: bool = False,
) -> List[Dict[str, Any]]:
    """
    Expand TechMeme stories into flat article candidates.
    
    Input story shape:
    {
        "title": "...",
        "url": "https://...",
        "source": "...",
        "related": [
            {"title": "...", "url": "...", "source": "..."},
            ...
        ],
        "related_count": 7,
        "scraped_at": "...",
        "ai_relevance": 0.75
    }
    
    Output candidate shape:
    {
        "story_id": str,           # stable hash from canonical URL
        "role": "canonical" | "related",
        "title": str,
        "url": str,
        "source": str,
        "published_at": str | None,
        "scraped_at": str,
        "ai_relevance": float,     # inherited from parent
        "parent_story_title": str | None,  # only for related
        "source_name": "techmeme",
        "signal_type": "techmeme_story_expanded"
    }
    
    Args:
        stories: List of TechMeme story dicts
        max_related: Maximum related links to include per story (default 8)
        include_source_only_links: Include links that only have source domain (no title)
        
    Returns:
        Flat list of article candidate dicts
    """
    candidates = []
    seen_urls: Set[str] = set()
    
    for story in stories:
        title = story.get('title', '')
        url = story.get('url', '')
        source = story.get('source', 'Unknown')
        ai_relevance = story.get('ai_relevance', 0.5)
        scraped_at = story.get('scraped_at', '')
        published_at = story.get('published_at')
        
        # Generate stable story_id
        story_id = generate_story_id(url, title)
        
        # Add canonical
        normalized_url = normalize_url(url)
        if normalized_url and normalized_url not in seen_urls:
            canonical = {
                'story_id': story_id,
                'role': 'canonical',
                'title': title,
                'url': url,
                'source': source,
                'published_at': published_at,
                'scraped_at': scraped_at,
                'ai_relevance': ai_relevance,
                'parent_story_title': None,
                'source_name': 'techmeme',
                'signal_type': 'techmeme_story_expanded',
            }
            candidates.append(canonical)
            seen_urls.add(normalized_url)
        
        # Add related links
        related = story.get('related', [])
        related_added = 0
        
        for rel in related:
            if related_added >= max_related:
                break
            
            rel_url = rel.get('url', '')
            rel_source = rel.get('source', '')
            rel_title = rel.get('title', '')
            
            # Skip if no URL
            if not rel_url:
                continue
            
            # Skip source-only links unless explicitly included
            if not rel_title and not include_source_only_links:
                # These are typically just source homepage links
                # from TechMeme's "Also at:" section
                continue
            
            # Check if URL looks like a homepage (no path or just /)
            try:
                parsed = urlparse(rel_url)
                if not parsed.path or parsed.path == '/':
                    if not include_source_only_links:
                        continue
            except Exception:
                pass
            
            # Deduplicate
            normalized_rel = normalize_url(rel_url)
            if not normalized_rel or normalized_rel in seen_urls:
                continue
            
            # Use canonical title with source if related has no title
            if not rel_title:
                rel_title = f"{title} ({rel_source})" if rel_source else title
            
            related_candidate = {
                'story_id': story_id,
                'role': 'related',
                'title': rel_title,
                'url': rel_url,
                'source': rel_source or 'Unknown',
                'published_at': None,  # Related links typically don't have timestamps
                'scraped_at': scraped_at,
                'ai_relevance': ai_relevance,  # Inherit from parent
                'parent_story_title': title,
                'source_name': 'techmeme',
                'signal_type': 'techmeme_story_expanded',
            }
            candidates.append(related_candidate)
            seen_urls.add(normalized_rel)
            related_added += 1
    
    logger.info(
        f"Expanded {len(stories)} TechMeme stories into {len(candidates)} candidates "
        f"({sum(1 for c in candidates if c['role'] == 'canonical')} canonical, "
        f"{sum(1 for c in candidates if c['role'] == 'related')} related)"
    )
    
    return candidates


def group_candidates_by_story(
    candidates: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group candidates by their story_id.
    
    Useful for analyzing expansion per story.
    
    Args:
        candidates: List of expanded candidates
        
    Returns:
        Dict mapping story_id -> list of candidates
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    
    for candidate in candidates:
        story_id = candidate.get('story_id', 'unknown')
        if story_id not in groups:
            groups[story_id] = []
        groups[story_id].append(candidate)
    
    return groups


def filter_ai_relevant_candidates(
    candidates: List[Dict[str, Any]],
    min_relevance: float = 0.3,
) -> List[Dict[str, Any]]:
    """
    Filter candidates by AI relevance threshold.
    
    Args:
        candidates: List of candidates
        min_relevance: Minimum ai_relevance score (default 0.3)
        
    Returns:
        Filtered list
    """
    return [
        c for c in candidates
        if c.get('ai_relevance', 0) >= min_relevance
    ]


# =============================================================================
# TESTS (inline for quick validation)
# =============================================================================

def _test_normalize_url():
    """Test URL normalization."""
    # Strip tracking params
    url = "https://example.com/article?utm_source=twitter&id=123"
    normalized = normalize_url(url)
    assert 'utm_source' not in normalized
    assert 'id=123' in normalized
    
    # Lowercase domain
    url = "HTTPS://WWW.EXAMPLE.COM/Page"
    normalized = normalize_url(url)
    assert normalized.startswith('https://')
    assert 'example.com' in normalized
    
    # Strip www
    url = "https://www.example.com/article"
    normalized = normalize_url(url)
    assert 'www.' not in normalized
    
    # Handle empty
    assert normalize_url('') == ''
    assert normalize_url(None) == ''
    
    print("[PASS] _test_normalize_url")


def _test_generate_story_id():
    """Test story ID generation."""
    # Same URL = same ID
    id1 = generate_story_id('https://example.com/article')
    id2 = generate_story_id('https://example.com/article')
    assert id1 == id2
    
    # Different URLs = different IDs
    id3 = generate_story_id('https://other.com/article')
    assert id1 != id3
    
    # Length check
    assert len(id1) == 12
    
    print("[PASS] _test_generate_story_id")


def _test_expand_includes_canonical():
    """Test that expansion includes canonical article."""
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
    assert candidates[0]['ai_relevance'] == 0.8
    
    print("[PASS] _test_expand_includes_canonical")


def _test_expand_limits_related():
    """Test that max_related is respected."""
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
    
    # Default max_related = 8
    candidates = expand_techmeme_stories(stories)
    assert len(candidates) == 9  # 1 canonical + 8 related
    
    # Custom max_related = 3
    candidates = expand_techmeme_stories(stories, max_related=3)
    assert len(candidates) == 4  # 1 canonical + 3 related
    
    print("[PASS] _test_expand_limits_related")


def _test_dedup_urls():
    """Test URL deduplication."""
    stories = [
        {
            'title': 'Story 1',
            'url': 'https://example.com/story',
            'source': 'Example',
            'related': [
                {'url': 'https://example.com/story', 'source': 'Dupe', 'title': 'Dupe'},
                {'url': 'https://example.com/story?utm_source=foo', 'source': 'Dupe2', 'title': 'Dupe2'},
                {'url': 'https://other.com/different', 'source': 'Other', 'title': 'Different'},
            ],
            'ai_relevance': 0.5,
            'scraped_at': '2026-02-09T10:00:00Z',
        }
    ]
    
    candidates = expand_techmeme_stories(stories)
    
    # Should only get canonical + 1 different (dupes removed)
    assert len(candidates) == 2
    urls = [c['url'] for c in candidates]
    assert 'https://example.com/story' in urls
    assert 'https://other.com/different' in urls
    
    print("[PASS] _test_dedup_urls")


def _test_role_fields_present():
    """Test that required fields are present in output."""
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
    
    # Check canonical
    canonical = [c for c in candidates if c['role'] == 'canonical'][0]
    assert canonical['parent_story_title'] is None
    assert canonical['source_name'] == 'techmeme'
    assert canonical['signal_type'] == 'techmeme_story_expanded'
    
    # Check related
    related = [c for c in candidates if c['role'] == 'related'][0]
    assert related['parent_story_title'] == 'Main Story'
    
    print("[PASS] _test_role_fields_present")


def _test_skips_homepage_links():
    """Test that homepage-only links are skipped by default."""
    stories = [
        {
            'title': 'Main Story',
            'url': 'https://main.com/story',
            'source': 'Main',
            'related': [
                {'url': 'https://bloomberg.com/', 'source': 'Bloomberg'},  # Homepage
                {'url': 'https://reuters.com', 'source': 'Reuters'},       # Homepage no slash
                {'url': 'https://wired.com/article/123', 'source': 'Wired', 'title': 'Real Article'},
            ],
            'ai_relevance': 0.5,
            'scraped_at': '2026-02-09T10:00:00Z',
        }
    ]
    
    candidates = expand_techmeme_stories(stories)
    
    # Should only get canonical + real article
    assert len(candidates) == 2
    urls = [c['url'] for c in candidates]
    assert 'https://bloomberg.com/' not in urls
    assert 'https://wired.com/article/123' in urls
    
    print("[PASS] _test_skips_homepage_links")


def run_tests():
    """Run all unit tests."""
    print("\n=== TECHMEME EXPANDER TESTS ===\n")
    
    _test_normalize_url()
    _test_generate_story_id()
    _test_expand_includes_canonical()
    _test_expand_limits_related()
    _test_dedup_urls()
    _test_role_fields_present()
    _test_skips_homepage_links()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
