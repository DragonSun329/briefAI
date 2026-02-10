"""
Cluster Dossier Builder - Transform StoryCluster into ranked event dossiers.

Part of Gravity Engine v2.1: "Rank events (clusters), not links."

A ClusterDossier provides:
- Canonical story + related coverage
- Domain diversity metrics (unique count, entropy)
- Time span across coverage
- Merge evidence for explainability
"""

import math
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse
from collections import Counter

from loguru import logger

try:
    from dateutil import parser as dateutil_parser
    DATEUTIL_AVAILABLE = True
except ImportError:
    DATEUTIL_AVAILABLE = False


@dataclass
class ClusterDossier:
    """
    A scored cluster dossier ready for ranking.
    
    Represents an "event" composed of multiple related articles,
    with domain diversity and temporal metrics.
    """
    cluster_id: str
    canonical: Dict[str, Any]
    related: List[Dict[str, Any]]
    
    # Cluster stats
    cluster_stats: Dict[str, Any] = field(default_factory=dict)
    
    # Evidence
    merge_evidence: List[str] = field(default_factory=list)
    top_domains: List[str] = field(default_factory=list)
    
    # Scoring (populated by cluster scorer)
    gravity_score: Optional[float] = None
    gravity_details: Optional[Dict[str, Any]] = None
    coverage_bonus_hint: float = 0.0
    confidence_hint: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """JSON-serializable representation."""
        return {
            'cluster_id': self.cluster_id,
            'canonical': self.canonical,
            'related': self.related,
            'cluster_stats': self.cluster_stats,
            'merge_evidence': self.merge_evidence,
            'top_domains': self.top_domains,
            'gravity_score': self.gravity_score,
            'gravity_details': self.gravity_details,
            'coverage_bonus_hint': round(self.coverage_bonus_hint, 3),
            'confidence_hint': round(self.confidence_hint, 3),
        }


def extract_domain(url: str) -> str:
    """
    Extract normalized domain from URL.
    
    - Strips leading "www."
    - Returns "unknown" if invalid/missing
    """
    if not url:
        return "unknown"
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        if not domain:
            return "unknown"
        
        # Strip www.
        if domain.startswith('www.'):
            domain = domain[4:]
        
        return domain if domain else "unknown"
    except Exception:
        return "unknown"


def compute_domain_entropy(domains: List[str]) -> float:
    """
    Compute Shannon entropy over domain frequencies.
    
    H = -sum(p_i * log2(p_i))
    
    Returns:
        Entropy (0.0 if single/no domains, higher = more diverse)
    """
    if not domains or len(domains) < 2:
        return 0.0
    
    counts = Counter(domains)
    total = len(domains)
    
    entropy = 0.0
    for count in counts.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    
    return round(entropy, 3)


def parse_timestamp(article: Dict[str, Any]) -> Optional[datetime]:
    """
    Parse timestamp from article.
    
    Checks: published_at, published, created_at, scraped_at
    """
    if not DATEUTIL_AVAILABLE:
        return None
    
    fields = ['published_at', 'published', 'created_at', 'scraped_at']
    
    for field in fields:
        value = article.get(field)
        if not value:
            continue
        
        try:
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                return dateutil_parser.parse(value)
        except (ValueError, TypeError):
            continue
    
    return None


def compute_time_span_hours(articles: List[Dict[str, Any]]) -> Optional[float]:
    """
    Compute time span in hours between oldest and newest article.
    
    Returns None if fewer than 2 valid timestamps.
    """
    timestamps = []
    
    for article in articles:
        ts = parse_timestamp(article)
        if ts:
            timestamps.append(ts)
    
    if len(timestamps) < 2:
        return None
    
    min_ts = min(timestamps)
    max_ts = max(timestamps)
    delta_seconds = (max_ts - min_ts).total_seconds()
    
    return round(delta_seconds / 3600, 2)


def build_cluster_dossier(
    cluster,  # StoryCluster
    max_related: int = 8
) -> ClusterDossier:
    """
    Build a ClusterDossier from a StoryCluster.
    
    Args:
        cluster: StoryCluster object
        max_related: Max related articles to include
    
    Returns:
        ClusterDossier with domain metrics and stats
    """
    canonical_story = cluster.canonical_story
    related_stories = cluster.related_stories[:max_related]
    
    # Build canonical dict
    canonical = {
        'title': canonical_story.get('title', ''),
        'url': canonical_story.get('url', ''),
        'source': canonical_story.get('source', 'Unknown'),
        'published_at': canonical_story.get('published_at') or canonical_story.get('scraped_at'),
        'tldr': canonical_story.get('tldr', ''),
        'key_insight': canonical_story.get('gravity_details', {}).get('key_insight', ''),
        'gravity_score': canonical_story.get('gravity_score'),
    }
    
    # Build related list
    related = []
    for story in related_stories:
        related.append({
            'title': story.get('title', ''),
            'url': story.get('url', ''),
            'source': story.get('source', 'Unknown'),
            'published_at': story.get('published_at') or story.get('scraped_at'),
        })
    
    # Collect all articles for domain analysis
    all_articles = [canonical_story] + related_stories
    
    # Extract domains
    domains = [extract_domain(a.get('url', '')) for a in all_articles]
    domains = [d for d in domains if d != 'unknown']
    
    # Domain metrics
    unique_domains = list(set(domains))
    unique_domain_count = len(unique_domains)
    domain_entropy = compute_domain_entropy(domains)
    
    # Top domains by frequency
    domain_counts = Counter(domains)
    top_domains = [d for d, _ in domain_counts.most_common(5)]
    
    # Time span
    time_span_hours = compute_time_span_hours(all_articles)
    
    # Build cluster stats
    cluster_stats = {
        'cluster_size': cluster.cluster_size,
        'unique_domain_count': unique_domain_count,
        'domain_entropy': domain_entropy,
        'avg_pair_similarity': getattr(cluster, 'avg_pair_similarity', 0.0),
        'max_pair_similarity': getattr(cluster, 'max_pair_similarity', 0.0),
        'cluster_confidence': getattr(cluster, 'cluster_confidence', 0.0),
        'gate_mix': getattr(cluster, 'gate_mix', {}),
        'shared_entities': getattr(cluster, 'shared_entities', [])[:10],
        'shared_bucket_tags': getattr(cluster, 'shared_bucket_tags', [])[:5],
        'time_span_hours': time_span_hours,
    }
    
    # Coverage bonus hint (for ranking)
    # Higher with more unique domains
    coverage_bonus_hint = min(1.0, math.log1p(unique_domain_count) / math.log1p(10))
    
    # Confidence hint
    confidence_hint = cluster_stats['cluster_confidence']
    
    return ClusterDossier(
        cluster_id=cluster.cluster_id,
        canonical=canonical,
        related=related,
        cluster_stats=cluster_stats,
        merge_evidence=getattr(cluster, 'merge_evidence', [])[:5],
        top_domains=top_domains,
        coverage_bonus_hint=coverage_bonus_hint,
        confidence_hint=confidence_hint,
    )


def build_dossiers_from_clusters(
    clusters,  # List[StoryCluster]
    max_related: int = 8
) -> List[ClusterDossier]:
    """
    Build dossiers from a list of clusters.
    """
    dossiers = []
    
    for cluster in clusters:
        try:
            dossier = build_cluster_dossier(cluster, max_related)
            dossiers.append(dossier)
        except Exception as e:
            logger.warning(f"Failed to build dossier for cluster {cluster.cluster_id}: {e}")
    
    return dossiers


# =============================================================================
# TESTS (inline for quick validation)
# =============================================================================

def _test_domain_extraction():
    """Test domain extraction helper."""
    assert extract_domain('https://www.techcrunch.com/article') == 'techcrunch.com'
    assert extract_domain('https://blog.openai.com/post') == 'blog.openai.com'
    assert extract_domain('http://example.org/page') == 'example.org'
    assert extract_domain('') == 'unknown'
    assert extract_domain(None) == 'unknown'
    print("[PASS] _test_domain_extraction")


def _test_domain_entropy():
    """Test entropy computation."""
    # Single domain -> 0
    assert compute_domain_entropy(['a.com']) == 0.0
    
    # Empty -> 0
    assert compute_domain_entropy([]) == 0.0
    
    # Two equal domains -> entropy = 1.0
    entropy = compute_domain_entropy(['a.com', 'b.com'])
    assert abs(entropy - 1.0) < 0.01
    
    # Four equal domains -> entropy = 2.0
    entropy = compute_domain_entropy(['a.com', 'b.com', 'c.com', 'd.com'])
    assert abs(entropy - 2.0) < 0.01
    
    print("[PASS] _test_domain_entropy")


def _test_time_span():
    """Test time span computation."""
    articles = [
        {'published_at': '2026-02-09T10:00:00Z'},
        {'published_at': '2026-02-09T12:00:00Z'},
        {'published_at': '2026-02-09T14:00:00Z'},
    ]
    
    span = compute_time_span_hours(articles)
    assert span == 4.0, f"Expected 4.0, got {span}"
    
    # Single article -> None
    assert compute_time_span_hours([{'published_at': '2026-02-09T10:00:00Z'}]) is None
    
    print("[PASS] _test_time_span")


if __name__ == "__main__":
    print("Running cluster_dossier tests...")
    _test_domain_extraction()
    _test_domain_entropy()
    _test_time_span()
    print("All tests passed!")
