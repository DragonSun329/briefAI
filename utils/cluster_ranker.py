"""
Cluster-First Ranker - Rank events (clusters), not links.

Part of Gravity Engine v2.1.

Produces a ranked feed mixing clusters and singletons:
- Clusters get coverage/entropy/confidence bonuses
- Singletons use raw gravity score
- Final output is a JSON feed ready for dashboard consumption
"""

import math
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from dataclasses import dataclass

from loguru import logger

try:
    from utils.cluster_dossier import (
        ClusterDossier,
        build_cluster_dossier,
        build_dossiers_from_clusters,
    )
except ImportError:
    from cluster_dossier import (
        ClusterDossier,
        build_cluster_dossier,
        build_dossiers_from_clusters,
    )


@dataclass
class FeedItem:
    """A ranked feed item (cluster or singleton)."""
    item_type: str  # "cluster" or "singleton"
    rank_score: float
    gravity_score: float
    data: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'item_type': self.item_type,
            'rank_score': round(self.rank_score, 3),
            'gravity_score': round(self.gravity_score, 3),
            **self.data
        }


def score_cluster_event(
    dossier: ClusterDossier,
    scorer_fn: Optional[Callable] = None,
) -> ClusterDossier:
    """
    Score a cluster as a single event using the Gravity scorer.
    
    Args:
        dossier: ClusterDossier to score
        scorer_fn: Optional function(text, metadata) -> dict with gravity_score + details
                   If None, uses canonical article's gravity_score
    
    Returns:
        Dossier with gravity_score and gravity_details populated
    """
    if scorer_fn is not None:
        # Build event text for scoring
        event_text = _build_event_text(dossier)
        metadata = {
            'cluster_size': dossier.cluster_stats.get('cluster_size', 1),
            'unique_domains': dossier.cluster_stats.get('unique_domain_count', 1),
            'domain_entropy': dossier.cluster_stats.get('domain_entropy', 0),
            'cluster_confidence': dossier.cluster_stats.get('cluster_confidence', 0),
            'time_span_hours': dossier.cluster_stats.get('time_span_hours'),
        }
        
        try:
            result = scorer_fn(event_text, metadata)
            dossier.gravity_score = result.get('gravity_score', 5.0)
            dossier.gravity_details = result.get('gravity_details', {})
        except Exception as e:
            logger.warning(f"Cluster scoring failed: {e}")
            # Fall back to canonical score
            dossier.gravity_score = dossier.canonical.get('gravity_score') or 5.0
            dossier.gravity_details = {}
    else:
        # Use canonical article's gravity score
        dossier.gravity_score = dossier.canonical.get('gravity_score') or 5.0
        dossier.gravity_details = {}
    
    return dossier


def _build_event_text(dossier: ClusterDossier) -> str:
    """
    Build event text for cluster-level scoring.
    
    Format:
    [Main story]
    Title: ...
    Insight: ...
    TLDR: ...
    
    [Coverage from N sources]
    - Source1: headline1
    - Source2: headline2
    ...
    
    [Cluster stats]
    Size: N, Domains: M, Confidence: X
    """
    parts = []
    
    # Main story
    parts.append("[Main story]")
    parts.append(f"Title: {dossier.canonical.get('title', '')}")
    
    if dossier.canonical.get('key_insight'):
        parts.append(f"Insight: {dossier.canonical['key_insight']}")
    
    if dossier.canonical.get('tldr'):
        parts.append(f"TLDR: {dossier.canonical['tldr']}")
    
    # Related coverage
    if dossier.related:
        parts.append(f"\n[Coverage from {len(dossier.related) + 1} sources]")
        for r in dossier.related[:6]:
            source = r.get('source', 'Unknown')
            title = r.get('title', '')[:80]
            parts.append(f"- {source}: {title}")
    
    # Cluster stats
    stats = dossier.cluster_stats
    parts.append(f"\n[Cluster stats]")
    parts.append(
        f"Size: {stats.get('cluster_size', 1)}, "
        f"Domains: {stats.get('unique_domain_count', 1)}, "
        f"Entropy: {stats.get('domain_entropy', 0):.2f}, "
        f"Confidence: {stats.get('cluster_confidence', 0):.2f}"
    )
    
    if stats.get('time_span_hours'):
        parts.append(f"Time span: {stats['time_span_hours']:.1f} hours")
    
    return '\n'.join(parts)


def compute_cluster_rank_score(
    gravity_score: float,
    unique_domain_count: int,
    domain_entropy: float,
    cluster_confidence: float,
) -> Dict[str, float]:
    """
    Compute rank score for a cluster with bonuses.
    
    Formula:
    - coverage_bonus = 0.25 * log1p(unique_domain_count)
    - entropy_bonus = 0.15 * min(1.0, domain_entropy / 2.0)
    - confidence_bonus = 0.35 * cluster_confidence
    - rank_score = gravity_score + coverage_bonus + entropy_bonus + confidence_bonus
    - Clamped to [0, 10]
    
    Returns dict with rank_score and breakdown.
    """
    coverage_bonus = 0.25 * math.log1p(unique_domain_count)
    entropy_bonus = 0.15 * min(1.0, domain_entropy / 2.0)
    confidence_bonus = 0.35 * cluster_confidence
    
    rank_score = gravity_score + coverage_bonus + entropy_bonus + confidence_bonus
    rank_score = max(0.0, min(10.0, rank_score))
    
    return {
        'rank_score': rank_score,
        'coverage_bonus': round(coverage_bonus, 3),
        'entropy_bonus': round(entropy_bonus, 3),
        'confidence_bonus': round(confidence_bonus, 3),
    }


def rank_feed(
    clusters,  # List[StoryCluster]
    singletons: List[Dict[str, Any]],
    target_date: str = None,
    scorer_fn: Optional[Callable] = None,
    max_related: int = 8,
) -> Dict[str, Any]:
    """
    Build a ranked feed mixing clusters and singletons.
    
    Args:
        clusters: List of StoryCluster objects
        singletons: List of article dicts (not clustered)
        target_date: Date string (YYYY-MM-DD) for the feed
        scorer_fn: Optional cluster scoring function
        max_related: Max related articles per cluster
    
    Returns:
        Feed dict with version, date, items sorted by rank_score desc
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')
    
    items = []
    
    # Process clusters
    for cluster in clusters:
        try:
            dossier = build_cluster_dossier(cluster, max_related)
            dossier = score_cluster_event(dossier, scorer_fn)
            
            # Compute rank score with bonuses
            stats = dossier.cluster_stats
            rank_info = compute_cluster_rank_score(
                gravity_score=dossier.gravity_score or 5.0,
                unique_domain_count=stats.get('unique_domain_count', 1),
                domain_entropy=stats.get('domain_entropy', 0),
                cluster_confidence=stats.get('cluster_confidence', 0),
            )
            
            item = FeedItem(
                item_type='cluster',
                rank_score=rank_info['rank_score'],
                gravity_score=dossier.gravity_score or 5.0,
                data={
                    'cluster_id': dossier.cluster_id,
                    'coverage_bonus': rank_info['coverage_bonus'],
                    'entropy_bonus': rank_info['entropy_bonus'],
                    'confidence_bonus': rank_info['confidence_bonus'],
                    'domain_entropy': stats.get('domain_entropy', 0),
                    'unique_domains': stats.get('unique_domain_count', 1),
                    'canonical': dossier.canonical,
                    'related': dossier.related,
                    'cluster_stats': dossier.cluster_stats,
                    'gravity_details': dossier.gravity_details,
                    'merge_evidence': dossier.merge_evidence,
                    'top_domains': dossier.top_domains,
                }
            )
            items.append(item)
            
        except Exception as e:
            logger.warning(f"Failed to process cluster: {e}")
    
    # Process singletons (no bonuses)
    for article in singletons:
        gravity_score = article.get('gravity_score', 5.0)
        
        item = FeedItem(
            item_type='singleton',
            rank_score=gravity_score,  # No bonuses for singletons
            gravity_score=gravity_score,
            data={
                'article': {
                    'title': article.get('title', ''),
                    'url': article.get('url', ''),
                    'source': article.get('source', 'Unknown'),
                    'published_at': article.get('published_at') or article.get('scraped_at'),
                    'tldr': article.get('tldr', ''),
                    'key_insight': article.get('gravity_details', {}).get('key_insight', ''),
                },
                'gravity_details': article.get('gravity_details', {}),
            }
        )
        items.append(item)
    
    # Sort by rank_score desc
    items.sort(key=lambda x: x.rank_score, reverse=True)
    
    # Build feed
    feed = {
        'version': '2.1',
        'date': target_date,
        'generated_at': datetime.now().isoformat(),
        'summary': {
            'total_items': len(items),
            'clusters': sum(1 for i in items if i.item_type == 'cluster'),
            'singletons': sum(1 for i in items if i.item_type == 'singleton'),
        },
        'items': [item.to_dict() for item in items],
    }
    
    return feed


def compute_theme_rank_score(
    gravity_score: float,
    unique_domain_count: int,
    domain_entropy: float,
    cluster_confidence: float,
) -> Dict[str, float]:
    """
    Compute rank score for THEME clusters with reduced coverage weight.
    
    Theme clusters are broader, so we reduce coverage bonus but maintain
    confidence importance.
    
    Formula:
    - coverage_bonus = 0.18 * log1p(unique_domain_count)  # (reduced from 0.25)
    - entropy_bonus = 0.12 * min(1.0, domain_entropy / 2.0)  # (reduced from 0.15)
    - confidence_bonus = 0.30 * cluster_confidence  # (reduced from 0.35)
    - rank_score = gravity_score + coverage + entropy + confidence
    - Clamped to [0, 10]
    
    Returns dict with rank_score and breakdown.
    """
    coverage_bonus = 0.18 * math.log1p(unique_domain_count)
    entropy_bonus = 0.12 * min(1.0, domain_entropy / 2.0)
    confidence_bonus = 0.30 * cluster_confidence
    
    rank_score = gravity_score + coverage_bonus + entropy_bonus + confidence_bonus
    rank_score = max(0.0, min(10.0, rank_score))
    
    return {
        'rank_score': rank_score,
        'coverage_bonus': round(coverage_bonus, 3),
        'entropy_bonus': round(entropy_bonus, 3),
        'confidence_bonus': round(confidence_bonus, 3),
    }


def _build_feed_items(
    clusters,  # List[StoryCluster]
    singletons: List[Dict[str, Any]],
    scorer_fn: Optional[Callable] = None,
    max_related: int = 8,
    mode: str = "event",  # "event" or "theme"
) -> List[FeedItem]:
    """
    Build feed items from clusters and singletons.
    
    Internal helper for rank_feed and build_dual_feed.
    """
    items = []
    
    # Choose rank score function based on mode
    rank_fn = compute_cluster_rank_score if mode == "event" else compute_theme_rank_score
    
    # Process clusters
    for cluster in clusters:
        try:
            dossier = build_cluster_dossier(cluster, max_related)
            dossier = score_cluster_event(dossier, scorer_fn)
            
            # Compute rank score with bonuses
            stats = dossier.cluster_stats
            rank_info = rank_fn(
                gravity_score=dossier.gravity_score or 5.0,
                unique_domain_count=stats.get('unique_domain_count', 1),
                domain_entropy=stats.get('domain_entropy', 0),
                cluster_confidence=stats.get('cluster_confidence', 0),
            )
            
            item = FeedItem(
                item_type='cluster',
                rank_score=rank_info['rank_score'],
                gravity_score=dossier.gravity_score or 5.0,
                data={
                    'cluster_id': dossier.cluster_id,
                    'coverage_bonus': rank_info['coverage_bonus'],
                    'entropy_bonus': rank_info['entropy_bonus'],
                    'confidence_bonus': rank_info['confidence_bonus'],
                    'domain_entropy': stats.get('domain_entropy', 0),
                    'unique_domains': stats.get('unique_domain_count', 1),
                    'canonical': dossier.canonical,
                    'related': dossier.related,
                    'cluster_stats': dossier.cluster_stats,
                    'gravity_details': dossier.gravity_details,
                    'merge_evidence': dossier.merge_evidence,
                    'top_domains': dossier.top_domains,
                }
            )
            items.append(item)
            
        except Exception as e:
            logger.warning(f"Failed to process cluster: {e}")
    
    # Process singletons (no bonuses, same for both modes)
    for article in singletons:
        gravity_score = article.get('gravity_score', 5.0)
        
        item = FeedItem(
            item_type='singleton',
            rank_score=gravity_score,  # No bonuses for singletons
            gravity_score=gravity_score,
            data={
                'article': {
                    'title': article.get('title', ''),
                    'url': article.get('url', ''),
                    'source': article.get('source', 'Unknown'),
                    'published_at': article.get('published_at') or article.get('scraped_at'),
                    'tldr': article.get('tldr', ''),
                    'key_insight': article.get('gravity_details', {}).get('key_insight', ''),
                },
                'gravity_details': article.get('gravity_details', {}),
            }
        )
        items.append(item)
    
    return items


def build_dual_feed(
    clusters_event,  # List[StoryCluster]
    singletons_event: List[Dict[str, Any]],
    clusters_theme,  # List[StoryCluster]
    singletons_theme: List[Dict[str, Any]],
    target_date: str = None,
    candidate_count: int = 0,
    scorer_fn: Optional[Callable] = None,
    max_related: int = 8,
    top_k: int = 30,
) -> Dict[str, Any]:
    """
    Build a dual-ranked feed with separate EVENT and THEME sections.
    
    Args:
        clusters_event: EVENT clusters (tight threshold, same story)
        singletons_event: EVENT singletons
        clusters_theme: THEME clusters (loose threshold + gates)
        singletons_theme: THEME singletons
        target_date: Date string (YYYY-MM-DD) for the feed
        candidate_count: Total candidate articles (for summary)
        scorer_fn: Optional cluster scoring function
        max_related: Max related articles per cluster
        top_k: Max items per feed section
    
    Returns:
        Dual feed dict with:
        {
            "version": "2.2",
            "date": "YYYY-MM-DD",
            "generated_at": "...",
            "summary": {
                "candidate_articles": N,
                "events": {"clusters": a, "singletons": b},
                "themes": {"clusters": c, "singletons": d}
            },
            "top_events": {"items": [...]},
            "top_themes": {"items": [...]}
        }
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')
    
    # Build EVENT items
    event_items = _build_feed_items(
        clusters_event, singletons_event,
        scorer_fn=scorer_fn,
        max_related=max_related,
        mode="event",
    )
    event_items.sort(key=lambda x: x.rank_score, reverse=True)
    event_items = event_items[:top_k]
    
    # Build THEME items
    theme_items = _build_feed_items(
        clusters_theme, singletons_theme,
        scorer_fn=scorer_fn,
        max_related=max_related,
        mode="theme",
    )
    theme_items.sort(key=lambda x: x.rank_score, reverse=True)
    theme_items = theme_items[:top_k]
    
    # Build dual feed
    feed = {
        'version': '2.2',
        'date': target_date,
        'generated_at': datetime.now().isoformat(),
        'summary': {
            'candidate_articles': candidate_count,
            'events': {
                'clusters': len(clusters_event),
                'singletons': len(singletons_event),
                'top_k_items': len(event_items),
            },
            'themes': {
                'clusters': len(clusters_theme),
                'singletons': len(singletons_theme),
                'top_k_items': len(theme_items),
            },
        },
        'top_events': {
            'items': [item.to_dict() for item in event_items],
        },
        'top_themes': {
            'items': [item.to_dict() for item in theme_items],
        },
    }
    
    return feed


def print_dual_feed_summary(feed: Dict[str, Any], top_n: int = 5):
    """Print a summary of the dual feed for CLI output."""
    print(f"\n{'='*60}")
    print(f"DUAL FEED v{feed['version']} - {feed['date']}")
    print(f"{'='*60}")
    print(f"Generated: {feed['generated_at']}")
    print(f"Candidate articles: {feed['summary']['candidate_articles']}")
    
    # Events summary
    events = feed['summary']['events']
    print(f"\nEVENTS: {events['clusters']} clusters, {events['singletons']} singletons")
    print(f"  (showing top {min(top_n, events['top_k_items'])} of {events['top_k_items']} items)")
    
    for i, item in enumerate(feed['top_events']['items'][:top_n]):
        rank = item['rank_score']
        gravity = item['gravity_score']
        item_type = item['item_type']
        
        if item_type == 'cluster':
            title = item['canonical']['title'][:45]
            domains = item['unique_domains']
            print(f"  {i+1}. [CLUSTER] {rank:.2f} (g={gravity:.2f}) {domains} domains")
            print(f"      {title}...")
        else:
            title = item['article']['title'][:45]
            print(f"  {i+1}. [SINGLE]  {rank:.2f}")
            print(f"      {title}...")
    
    # Themes summary
    themes = feed['summary']['themes']
    print(f"\nTHEMES: {themes['clusters']} clusters, {themes['singletons']} singletons")
    print(f"  (showing top {min(top_n, themes['top_k_items'])} of {themes['top_k_items']} items)")
    
    for i, item in enumerate(feed['top_themes']['items'][:top_n]):
        rank = item['rank_score']
        gravity = item['gravity_score']
        item_type = item['item_type']
        
        if item_type == 'cluster':
            title = item['canonical']['title'][:45]
            domains = item['unique_domains']
            print(f"  {i+1}. [CLUSTER] {rank:.2f} (g={gravity:.2f}) {domains} domains")
            print(f"      {title}...")
        else:
            title = item['article']['title'][:45]
            print(f"  {i+1}. [SINGLE]  {rank:.2f}")
            print(f"      {title}...")


def print_feed_summary(feed: Dict[str, Any], top_n: int = 5):
    """Print a summary of the feed for CLI output."""
    print(f"\n{'='*60}")
    print(f"CLUSTER FEED v{feed['version']} - {feed['date']}")
    print(f"{'='*60}")
    print(f"Generated: {feed['generated_at']}")
    print(f"Total items: {feed['summary']['total_items']}")
    print(f"  Clusters: {feed['summary']['clusters']}")
    print(f"  Singletons: {feed['summary']['singletons']}")
    
    print(f"\nTop {top_n} items:")
    for i, item in enumerate(feed['items'][:top_n]):
        rank = item['rank_score']
        gravity = item['gravity_score']
        item_type = item['item_type']
        
        if item_type == 'cluster':
            title = item['canonical']['title'][:50]
            domains = item['unique_domains']
            conf_bonus = item.get('confidence_bonus', 0)
            print(f"  {i+1}. [CLUSTER] {rank:.2f} (g={gravity:.2f} +conf={conf_bonus:.2f})")
            print(f"      {title}...")
            print(f"      {domains} domains, {len(item.get('related', []))+1} sources")
        else:
            title = item['article']['title'][:50]
            print(f"  {i+1}. [SINGLE]  {rank:.2f}")
            print(f"      {title}...")


# =============================================================================
# TESTS (inline for quick validation)
# =============================================================================

def _test_rank_score_formula():
    """Test rank score computation."""
    # Basic case
    result = compute_cluster_rank_score(
        gravity_score=6.0,
        unique_domain_count=5,
        domain_entropy=1.5,
        cluster_confidence=0.8,
    )
    
    assert result['rank_score'] > 6.0, "Cluster should get bonus"
    assert result['coverage_bonus'] > 0
    assert result['entropy_bonus'] > 0
    assert result['confidence_bonus'] > 0
    
    # Zero everything
    result = compute_cluster_rank_score(
        gravity_score=5.0,
        unique_domain_count=0,
        domain_entropy=0,
        cluster_confidence=0,
    )
    assert result['rank_score'] == 5.0, "No bonuses with zero stats"
    
    print("[PASS] _test_rank_score_formula")


def _test_singleton_no_bonus():
    """Test that singletons don't get bonuses."""
    # Mock cluster and singleton
    class MockCluster:
        cluster_id = "test123"
        canonical_story = {'title': 'Test', 'url': 'http://a.com', 'gravity_score': 6.0}
        related_stories = []
        cluster_size = 1
        cluster_confidence = 0.9
        avg_pair_similarity = 0.0
        max_pair_similarity = 0.0
        gate_mix = {}
        shared_entities = []
        shared_bucket_tags = []
        merge_evidence = []
    
    singleton = {'title': 'Single', 'url': 'http://b.com', 'gravity_score': 6.0}
    
    feed = rank_feed([MockCluster()], [singleton])
    
    # Find items
    cluster_item = next(i for i in feed['items'] if i['item_type'] == 'cluster')
    single_item = next(i for i in feed['items'] if i['item_type'] == 'singleton')
    
    # Singleton rank_score should equal gravity_score
    assert single_item['rank_score'] == single_item['gravity_score']
    
    print("[PASS] _test_singleton_no_bonus")


def _test_sorting():
    """Test that feed is sorted by rank_score desc."""
    class MockCluster:
        def __init__(self, cid, score, conf):
            self.cluster_id = cid
            self.canonical_story = {'title': f'Cluster {cid}', 'url': f'http://{cid}.com', 'gravity_score': score}
            self.related_stories = [{'title': 'R', 'url': 'http://r.com'}]
            self.cluster_size = 2
            self.cluster_confidence = conf
            self.avg_pair_similarity = 0.8
            self.max_pair_similarity = 0.85
            self.gate_mix = {}
            self.shared_entities = []
            self.shared_bucket_tags = []
            self.merge_evidence = []
    
    clusters = [
        MockCluster('low', 4.0, 0.3),
        MockCluster('high', 7.0, 0.9),
        MockCluster('mid', 5.5, 0.6),
    ]
    singletons = [
        {'title': 'S1', 'url': 'http://s1.com', 'gravity_score': 6.0},
    ]
    
    feed = rank_feed(clusters, singletons)
    
    # Check sorted descending
    scores = [item['rank_score'] for item in feed['items']]
    assert scores == sorted(scores, reverse=True), f"Not sorted: {scores}"
    
    # High cluster should be first (7.0 + bonuses)
    assert feed['items'][0]['cluster_id'] == 'high'
    
    print("[PASS] _test_sorting")


if __name__ == "__main__":
    print("Running cluster_ranker tests...")
    _test_rank_score_formula()
    _test_singleton_no_bonus()
    _test_sorting()
    print("All tests passed!")
