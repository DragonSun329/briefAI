"""
Story Clustering Module - Group Related Stories by Semantic Similarity

Part of the Gravity Engine integration.
Uses vector embeddings to:
1. Cluster related stories covering the same event
2. Identify the "canonical" story in each cluster
3. Surface story clusters for editorial review

Supports two clustering modes:
- EVENT: Strict same-story clustering (threshold ~0.86, requires enriched content)
- TOPIC: Loose topic clustering (adaptive threshold ~0.60-0.78, summary-first embedding)

Key features:
- Summary-first embeddings using Gravity outputs (key_insight, verdict)
- Adaptive threshold tuning based on batch similarity distribution
- Entity AND bucket/tag overlap gates for topic clustering
- Temporal locality constraints (TOPIC mode)
- Cluster confidence scoring with UI-ready explainability
- Union-Find for transitive clustering

TOPIC merge rule:
  merge = (similarity >= threshold) AND (entity_overlap OR bucket_overlap) AND temporal_locality
"""

import json
import math
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timedelta
from dateutil import parser as dateutil_parser
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
import hashlib

from loguru import logger

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    np = None
    logger.warning("Story clustering requires: pip install sentence-transformers numpy")


class ClusterMode(Enum):
    EVENT = "event"   # Strict: same story, different sources
    TOPIC = "topic"   # Loose: same topic/entity, related coverage


@dataclass
class StoryCluster:
    """A cluster of related stories about the same topic/event"""
    cluster_id: str
    canonical_story: Dict[str, Any]
    related_stories: List[Dict[str, Any]] = field(default_factory=list)
    cluster_size: int = 1
    sources: List[str] = field(default_factory=list)
    avg_gravity_score: float = 0.0
    topic_summary: str = ""
    
    # Entity/bucket sharing
    shared_entities: List[str] = field(default_factory=list)
    shared_bucket_tags: List[str] = field(default_factory=list)
    merge_reason: str = ""
    merge_evidence: List[str] = field(default_factory=list)
    
    # Confidence scoring
    cluster_confidence: float = 0.0
    avg_pair_similarity: float = 0.0
    max_pair_similarity: float = 0.0
    confidence_breakdown: Dict[str, float] = field(default_factory=dict)
    
    # Gate mix stats
    gate_mix: Dict[str, int] = field(default_factory=lambda: {
        'merges_by_entity': 0,
        'merges_by_bucket': 0,
        'merges_blocked_by_time': 0
    })
    
    mode: str = "event"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'cluster_id': self.cluster_id,
            'canonical_story': {
                'title': self.canonical_story.get('title'),
                'source': self.canonical_story.get('source'),
                'url': self.canonical_story.get('url'),
                'gravity_score': self.canonical_story.get('gravity_score', 0)
            },
            'related_count': len(self.related_stories),
            'sources': self.sources,
            'cluster_size': self.cluster_size,
            'avg_gravity_score': self.avg_gravity_score,
            'shared_entities': self.shared_entities,
            'shared_bucket_tags': self.shared_bucket_tags,
            'merge_reason': self.merge_reason,
            'merge_evidence': self.merge_evidence,
            'cluster_confidence': round(self.cluster_confidence, 3),
            'avg_pair_similarity': round(self.avg_pair_similarity, 3),
            'max_pair_similarity': round(self.max_pair_similarity, 3),
            'confidence_breakdown': self.confidence_breakdown,
            'gate_mix': self.gate_mix,
            'mode': self.mode,
            'created_at': self.created_at
        }


class UnionFind:
    """Union-Find for transitive clustering."""
    
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n
    
    def find(self, x: int) -> int:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
    
    def union(self, x: int, y: int) -> None:
        px, py = self.find(x), self.find(y)
        if px == py:
            return
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1
    
    def get_clusters(self) -> Dict[int, List[int]]:
        clusters = defaultdict(list)
        for i in range(len(self.parent)):
            clusters[self.find(i)].append(i)
        return dict(clusters)


class StoryClustering:
    """
    Cluster related stories using vector embeddings.
    
    Supports dual-threshold clustering:
    - EVENT mode: 0.86 threshold, requires body/summary text
    - TOPIC mode: adaptive threshold (0.60-0.78), summary-first embedding
      with entity/bucket gates and temporal locality constraints
    """
    
    # Thresholds per mode
    THRESHOLDS = {
        ClusterMode.EVENT: 0.86,
        ClusterMode.TOPIC: 0.68,
    }
    
    # Adaptive threshold bounds for TOPIC mode
    TOPIC_THRESHOLD_MIN = 0.60
    TOPIC_THRESHOLD_MAX = 0.78
    
    # Similarity boosts
    ENTITY_BOOST = 0.05
    BUCKET_BOOST = 0.03
    
    MIN_CLUSTER_SIZE = 2
    
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        mode: ClusterMode = ClusterMode.EVENT,
        threshold: float = None,
        normalize_embeddings: bool = True,
        auto_threshold: bool = True,
        max_topic_age_days: int = 7,
        enforce_temporal_locality: bool = True
    ):
        """
        Initialize story clustering.
        
        Args:
            model_name: Sentence-Transformers model
            mode: EVENT (strict) or TOPIC (loose)
            threshold: Override default threshold for mode
            normalize_embeddings: L2 normalize embeddings (recommended)
            auto_threshold: Auto-tune threshold for TOPIC mode based on batch
            max_topic_age_days: Max days apart for TOPIC clustering (default 7)
            enforce_temporal_locality: Require articles to be within age window
        """
        self.mode = mode
        self.base_threshold = threshold or self.THRESHOLDS.get(mode, 0.75)
        self.threshold = self.base_threshold
        self.normalize = normalize_embeddings
        self.auto_threshold = auto_threshold and (mode == ClusterMode.TOPIC)
        self.max_topic_age_days = max_topic_age_days
        # Temporal locality defaults to True for TOPIC, False for EVENT
        self.enforce_temporal_locality = enforce_temporal_locality if mode == ClusterMode.TOPIC else False
        
        if not EMBEDDINGS_AVAILABLE:
            logger.error("Story clustering unavailable - missing dependencies")
            self.available = False
            return
        
        try:
            logger.info(f"Loading embedding model: {model_name}")
            self.model = SentenceTransformer(model_name)
            self.available = True
            logger.info(
                f"Story clustering initialized "
                f"(mode={mode.value}, threshold={self.threshold}, "
                f"auto_threshold={self.auto_threshold}, "
                f"temporal_locality={self.enforce_temporal_locality}, "
                f"max_age_days={self.max_topic_age_days})"
            )
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self.available = False

    # =========================================================================
    # DATE PARSING
    # =========================================================================
    
    def _get_published_dt(self, article: Dict[str, Any]) -> Optional[datetime]:
        """
        Parse publication datetime from article.
        
        Checks fields in priority: published_at, published, created_at, scraped_at
        """
        date_fields = ['published_at', 'published', 'created_at', 'scraped_at']
        
        for field in date_fields:
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
    
    def _check_temporal_locality(
        self,
        a1: Dict[str, Any],
        a2: Dict[str, Any]
    ) -> Tuple[bool, Optional[float]]:
        """
        Check if two articles are within temporal locality window.
        
        Returns:
            (passes_check, delta_days or None if unknown)
        """
        if not self.enforce_temporal_locality:
            return True, None
        
        dt1 = self._get_published_dt(a1)
        dt2 = self._get_published_dt(a2)
        
        # If either is missing, allow merge (don't block on missing data)
        if dt1 is None or dt2 is None:
            return True, None
        
        delta = abs((dt1 - dt2).total_seconds()) / 86400  # days
        passes = delta <= self.max_topic_age_days
        
        return passes, delta

    # =========================================================================
    # BUCKET/TAG EXTRACTION
    # =========================================================================
    
    def _get_bucket_tags(self, article: Dict[str, Any]) -> Set[str]:
        """
        Extract bucket/category tags from article.
        
        Priority order (uses FIRST non-empty source):
        1. article["bucket_tags"]
        2. article["trend_buckets"]
        3. article["gravity_details"]["category_tags"]
        4. article["tags"]
        
        Normalizes: lowercase, strip, replace spaces with hyphen, drop empty.
        """
        # Priority sources - use first non-empty
        sources = [
            article.get('bucket_tags'),
            article.get('trend_buckets'),
            article.get('gravity_details', {}).get('category_tags'),
            article.get('tags'),
        ]
        
        for source in sources:
            if source:
                tags = set()
                if isinstance(source, (list, set, tuple)):
                    for tag in source:
                        if isinstance(tag, str):
                            normalized = tag.lower().strip().replace(' ', '-')
                            if normalized:
                                tags.add(normalized)
                elif isinstance(source, str):
                    normalized = source.lower().strip().replace(' ', '-')
                    if normalized:
                        tags.add(normalized)
                
                if tags:  # Return first non-empty result
                    return tags
        
        return set()
    
    def _bucket_overlap(
        self,
        a1: Dict[str, Any],
        a2: Dict[str, Any]
    ) -> Tuple[bool, Set[str]]:
        """
        Check if two articles share bucket tags.
        
        Returns:
            (has_overlap, shared_tags)
        """
        t1 = self._get_bucket_tags(a1)
        t2 = self._get_bucket_tags(a2)
        shared = t1 & t2
        return bool(shared), shared

    # =========================================================================
    # ENTITY EXTRACTION (existing, enhanced)
    # =========================================================================
    
    def _extract_entities(self, article: Dict[str, Any]) -> Set[str]:
        """
        Extract key entities from article for topic clustering gate.
        """
        title = article.get('title', '')
        words = title.split()
        entities = set()
        
        # Capitalized words (not sentence-start)
        for i, word in enumerate(words):
            if i == 0:
                continue
            clean = word.strip('.,!?:;"\'-()[]')
            if clean and clean[0].isupper() and len(clean) >= 2:
                entities.add(clean.lower())
        
        # Known tech entities
        known_entities = [
            'openai', 'anthropic', 'google', 'meta', 'microsoft', 'apple',
            'nvidia', 'amazon', 'claude', 'gpt', 'gemini', 'llama',
            'chatgpt', 'copilot', 'bard', 'midjourney', 'deepmind',
            'mistral', 'cohere', 'hugging face', 'stability ai',
            'perplexity', 'inflection', 'character ai', 'runway'
        ]
        title_lower = title.lower()
        for entity in known_entities:
            if entity in title_lower:
                entities.add(entity)
        
        return entities
    
    def _entities_overlap(
        self,
        a1: Dict[str, Any],
        a2: Dict[str, Any]
    ) -> Tuple[bool, Set[str]]:
        """
        Check if two articles share entities.
        """
        e1 = self._extract_entities(a1)
        e2 = self._extract_entities(a2)
        shared = e1 & e2
        return bool(shared), shared

    # =========================================================================
    # EFFECTIVE SIMILARITY + GATE LOGIC
    # =========================================================================
    
    def _compute_effective_similarity(
        self,
        sim: float,
        a1: Dict[str, Any],
        a2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute effective similarity with entity/bucket boosts and gates.
        
        Returns dict with:
            effective_sim, raw_sim,
            passes_entity_gate, shared_entities,
            passes_bucket_gate, shared_bucket_tags,
            passes_temporal, delta_days,
            passes_gate (overall), pass_reason
        """
        # Entity overlap
        has_entity_overlap, shared_entities = self._entities_overlap(a1, a2)
        
        # Bucket overlap
        has_bucket_overlap, shared_buckets = self._bucket_overlap(a1, a2)
        
        # Temporal locality
        passes_temporal, delta_days = self._check_temporal_locality(a1, a2)
        
        # Compute boost
        boost = 0.0
        if has_entity_overlap:
            boost += self.ENTITY_BOOST
        if has_bucket_overlap:
            boost += self.BUCKET_BOOST
        
        effective = min(1.0, max(0.0, sim + boost))
        
        # Determine pass reason
        passes_gate = False
        pass_reason = "none"
        
        if self.mode == ClusterMode.TOPIC:
            # TOPIC: require (entity OR bucket) AND temporal
            if passes_temporal:
                if has_entity_overlap:
                    passes_gate = True
                    pass_reason = "entity"
                elif has_bucket_overlap:
                    passes_gate = True
                    pass_reason = "bucket"
        else:
            # EVENT: no gate requirement (pure similarity)
            passes_gate = True
            pass_reason = "event_mode"
        
        return {
            'raw_similarity': sim,
            'effective_similarity': effective,
            'passes_entity_gate': has_entity_overlap,
            'shared_entities': list(shared_entities),
            'passes_bucket_gate': has_bucket_overlap,
            'shared_bucket_tags': list(shared_buckets),
            'passes_temporal': passes_temporal,
            'temporal_blocked': not passes_temporal if self.enforce_temporal_locality else False,
            'delta_days': round(delta_days, 1) if delta_days is not None else None,
            'passes_gate': passes_gate,
            'pass_reason': pass_reason,
        }

    # =========================================================================
    # EMBEDDING + SIMILARITY
    # =========================================================================
    
    def _build_embed_summary(self, article: Dict[str, Any]) -> str:
        """Build compact semantic fingerprint for embedding."""
        parts = []
        
        title = article.get('title', '')
        if title:
            parts.append(title)
        
        gravity = article.get('gravity_details', {})
        
        key_insight = gravity.get('key_insight', '')
        if key_insight:
            parts.append(key_insight)
        
        verdict = gravity.get('editorial_verdict', '') or article.get('verdict', '')
        if verdict:
            parts.append(verdict)
        
        key_points = article.get('key_points', [])
        if key_points and isinstance(key_points, list):
            for point in key_points[:5]:
                if isinstance(point, str):
                    parts.append(point)
                elif isinstance(point, dict):
                    parts.append(point.get('text', point.get('point', '')))
        
        tldr = article.get('tldr', '')
        if tldr and not key_insight:
            parts.append(tldr)
        
        summary = '. '.join(p.strip().rstrip('.') for p in parts if p)
        return summary if summary else title
    
    def _get_article_text(self, article: Dict[str, Any], max_chars: int = 1500) -> str:
        """Extract best text for embedding from article."""
        embed_summary = self._build_embed_summary(article)
        has_summary = len(embed_summary) > len(article.get('title', '')) + 10
        
        if self.mode == ClusterMode.TOPIC:
            if has_summary:
                return embed_summary[:max_chars]
            title = article.get('title', '')
            tldr = article.get('tldr', '')
            if tldr:
                return f"{title}. {tldr}"[:max_chars]
            return title
        
        if self.mode == ClusterMode.EVENT:
            if has_summary:
                text = embed_summary
                body = article.get('body_text', '')
                if body and len(text) < max_chars:
                    remaining = max_chars - len(text) - 1
                    text += f" {body[:remaining]}"
                return text[:max_chars]
            
            title = article.get('title', '')
            if article.get('enriched'):
                tldr = article.get('tldr', '')
                body = article.get('body_text', '')
                if tldr:
                    text = f"{title}. {tldr}"
                    if len(text) < max_chars and body:
                        remaining = max_chars - len(text) - 1
                        text += f" {body[:remaining]}"
                    return text[:max_chars]
                if body:
                    return f"{title}. {body[:max_chars - len(title) - 2]}"
        
        title = article.get('title', '')
        content = article.get('content', article.get('summary', ''))
        if content and content != title:
            return f"{title}. {content}"[:max_chars]
        return title
    
    def _compute_embeddings(self, articles: List[Dict[str, Any]]) -> np.ndarray:
        """Compute embeddings for all articles."""
        texts = [self._get_article_text(a) for a in articles]
        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=self.normalize
        )
        return embeddings
    
    def _compute_similarity_matrix(self, embeddings: np.ndarray) -> np.ndarray:
        """Compute pairwise similarity matrix."""
        if self.normalize:
            return np.dot(embeddings, embeddings.T)
        else:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            normalized = embeddings / norms
            return np.dot(normalized, normalized.T)
    
    def _auto_tune_threshold(self, sim_matrix: np.ndarray) -> float:
        """Auto-tune threshold for TOPIC mode based on p95."""
        n = sim_matrix.shape[0]
        if n < 2:
            return self.base_threshold
        
        upper_tri = sim_matrix[np.triu_indices(n, k=1)]
        if len(upper_tri) == 0:
            return self.base_threshold
        
        p95 = float(np.percentile(upper_tri, 95))
        tuned = max(self.TOPIC_THRESHOLD_MIN, min(self.TOPIC_THRESHOLD_MAX, p95 - 0.03))
        
        logger.debug(f"Auto-tuned threshold: p95={p95:.3f} -> threshold={tuned:.3f}")
        return tuned

    # =========================================================================
    # CLUSTER CONFIDENCE SCORING
    # =========================================================================
    
    def _compute_cluster_confidence(
        self,
        cluster_indices: List[int],
        articles: List[Dict[str, Any]],
        sim_matrix: np.ndarray,
        threshold: float
    ) -> Dict[str, Any]:
        """
        Compute confidence score and stats for a cluster.
        
        Returns dict with:
            confidence, avg_pair_similarity, max_pair_similarity, confidence_breakdown
        """
        n = len(cluster_indices)
        
        if n < 2:
            canonical = articles[cluster_indices[0]] if cluster_indices else {}
            is_enriched = canonical.get('enriched', False)
            return {
                'confidence': 0.5 if is_enriched else 0.35,
                'avg_pair_similarity': 0.0,
                'max_pair_similarity': 0.0,
                'confidence_breakdown': {
                    'base': 0.0,
                    'size_factor': 0.0,
                    'coverage_factor': 0.7 if is_enriched else 0.5,
                    'threshold': threshold,
                    'avg_sim': 0.0
                }
            }
        
        # Compute pairwise similarities within cluster
        pair_sims = []
        for i in range(n):
            for j in range(i + 1, n):
                idx_i, idx_j = cluster_indices[i], cluster_indices[j]
                pair_sims.append(float(sim_matrix[idx_i, idx_j]))
        
        avg_sim = sum(pair_sims) / len(pair_sims) if pair_sims else 0.0
        max_sim = max(pair_sims) if pair_sims else 0.0
        
        # Confidence heuristic
        # base = (avg_sim - threshold) / 0.10, clamped [0,1]
        base = max(0.0, min(1.0, (avg_sim - threshold) / 0.10))
        
        # size_factor = min(1.0, log1p(size)/log1p(6))
        size_factor = min(1.0, math.log1p(n) / math.log1p(6))
        
        # coverage_factor: 1.0 if canonical is enriched, else 0.7
        canonical = articles[cluster_indices[0]]  # First is typically highest scored
        coverage_factor = 1.0 if canonical.get('enriched') else 0.7
        
        # confidence = 0.15 + 0.55*base + 0.20*size + 0.10*coverage
        confidence = 0.15 + 0.55 * base + 0.20 * size_factor + 0.10 * coverage_factor
        confidence = max(0.0, min(1.0, confidence))
        
        return {
            'confidence': confidence,
            'avg_pair_similarity': avg_sim,
            'max_pair_similarity': max_sim,
            'confidence_breakdown': {
                'base': round(base, 3),
                'size_factor': round(size_factor, 3),
                'coverage_factor': round(coverage_factor, 3),
                'threshold': round(threshold, 3),
                'avg_sim': round(avg_sim, 3)
            }
        }

    # =========================================================================
    # UNION-FIND CLUSTERING
    # =========================================================================
    
    def _find_clusters_union_find(
        self,
        articles: List[Dict[str, Any]],
        sim_matrix: np.ndarray
    ) -> Tuple[List[List[int]], Dict[Tuple[int, int], Dict]]:
        """Find clusters using Union-Find with entity/bucket/temporal gates."""
        n = len(articles)
        uf = UnionFind(n)
        merge_info = {}
        
        for i in range(n):
            for j in range(i + 1, n):
                raw_sim = float(sim_matrix[i, j])
                
                gate_result = self._compute_effective_similarity(
                    raw_sim, articles[i], articles[j]
                )
                
                eff_sim = gate_result['effective_similarity']
                passes = gate_result['passes_gate'] and eff_sim >= self.threshold
                
                # Also check temporal for TOPIC mode
                if self.mode == ClusterMode.TOPIC and gate_result['temporal_blocked']:
                    passes = False
                
                if passes:
                    uf.union(i, j)
                    merge_info[(i, j)] = gate_result
        
        cluster_dict = uf.get_clusters()
        return list(cluster_dict.values()), merge_info

    # =========================================================================
    # DEBUG REPORT
    # =========================================================================
    
    def debug_report(
        self,
        articles: List[Dict[str, Any]],
        embeddings: np.ndarray = None,
        sim_matrix: np.ndarray = None,
        tuned_threshold: float = None
    ) -> Dict[str, Any]:
        """Generate debug report with entity/bucket/temporal info."""
        n = len(articles)
        
        has_body = sum(1 for a in articles if len(a.get('body_text', '')) > 200)
        has_tldr = sum(1 for a in articles if len(a.get('tldr', '')) > 50)
        has_gravity = sum(1 for a in articles if a.get('gravity_details'))
        enriched = sum(1 for a in articles if a.get('enriched'))
        has_bucket_tags = sum(1 for a in articles if self._get_bucket_tags(a))
        has_timestamps = sum(1 for a in articles if self._get_published_dt(a))
        
        if embeddings is None:
            embeddings = self._compute_embeddings(articles)
        if sim_matrix is None:
            sim_matrix = self._compute_similarity_matrix(embeddings)
        
        upper_tri_indices = np.triu_indices(n, k=1)
        similarities = sim_matrix[upper_tri_indices]
        
        if len(similarities) > 0:
            p50 = float(np.percentile(similarities, 50))
            p90 = float(np.percentile(similarities, 90))
            p95 = float(np.percentile(similarities, 95))
            max_sim = float(np.max(similarities))
            min_sim = float(np.min(similarities))
        else:
            p50 = p90 = p95 = max_sim = min_sim = 0.0
        
        current_threshold = tuned_threshold if tuned_threshold else self.threshold
        pairs_above = int(np.sum(similarities >= current_threshold))
        total_pairs = len(similarities)
        
        # Top pairs with full gate info
        top_k = min(5, len(similarities))
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        top_pairs = []
        
        for idx in top_indices:
            i, j = int(upper_tri_indices[0][idx]), int(upper_tri_indices[1][idx])
            raw_sim = float(similarities[idx])
            
            gate_result = self._compute_effective_similarity(
                raw_sim, articles[i], articles[j]
            )
            
            would_merge = (
                gate_result['effective_similarity'] >= current_threshold and
                gate_result['passes_gate'] and
                not gate_result['temporal_blocked']
            )
            
            top_pairs.append({
                'i': i,
                'j': j,
                'title_i': articles[i].get('title', '')[:50],
                'title_j': articles[j].get('title', '')[:50],
                'raw_similarity': round(raw_sim, 3),
                'effective_similarity': round(gate_result['effective_similarity'], 3),
                'passes_entity_gate': gate_result['passes_entity_gate'],
                'shared_entities': gate_result['shared_entities'],
                'passes_bucket_gate': gate_result['passes_bucket_gate'],
                'shared_bucket_tags': gate_result['shared_bucket_tags'],
                'passes_temporal': gate_result['passes_temporal'],
                'temporal_blocked': gate_result['temporal_blocked'],
                'delta_days': gate_result['delta_days'],
                'pass_reason': gate_result['pass_reason'],
                'would_merge': would_merge
            })
        
        return {
            'article_count': n,
            'content_coverage': {
                'enriched': enriched,
                'has_body_200': has_body,
                'has_tldr_50': has_tldr,
                'has_gravity_details': has_gravity,
                'has_bucket_tags': has_bucket_tags,
                'has_timestamps': has_timestamps,
            },
            'similarity_distribution': {
                'min': round(min_sim, 3),
                'p50': round(p50, 3),
                'p90': round(p90, 3),
                'p95': round(p95, 3),
                'max': round(max_sim, 3),
            },
            'clustering': {
                'mode': self.mode.value,
                'base_threshold': self.base_threshold,
                'threshold': round(current_threshold, 3),
                'auto_tuned': tuned_threshold is not None,
                'enforce_temporal_locality': self.enforce_temporal_locality,
                'max_topic_age_days': self.max_topic_age_days,
                'pairs_above_threshold': pairs_above,
                'total_pairs': total_pairs,
                'would_merge': pairs_above > 0,
            },
            'top_similar_pairs': top_pairs,
        }

    # =========================================================================
    # MAIN CLUSTERING
    # =========================================================================
    
    def cluster_stories(
        self,
        articles: List[Dict[str, Any]],
        return_debug: bool = False
    ) -> Tuple[List[StoryCluster], List[Dict[str, Any]]]:
        """Cluster articles by semantic similarity."""
        if not self.available:
            logger.warning("Clustering unavailable, returning all as singletons")
            return ([], articles, {}) if return_debug else ([], articles)
        
        if not articles:
            return ([], [], {}) if return_debug else ([], [])
        
        logger.info(f"Clustering {len(articles)} articles (mode={self.mode.value})...")
        
        embeddings = self._compute_embeddings(articles)
        sim_matrix = self._compute_similarity_matrix(embeddings)
        
        tuned_threshold = None
        if self.auto_threshold and self.mode == ClusterMode.TOPIC:
            tuned_threshold = self._auto_tune_threshold(sim_matrix)
            self.threshold = tuned_threshold
            logger.info(f"  Auto-tuned threshold: {tuned_threshold:.3f}")
        
        debug = self.debug_report(articles, embeddings, sim_matrix, tuned_threshold)
        
        logger.info(
            f"  Similarity: p50={debug['similarity_distribution']['p50']:.2f}, "
            f"p90={debug['similarity_distribution']['p90']:.2f}, "
            f"max={debug['similarity_distribution']['max']:.2f}"
        )
        logger.info(
            f"  Pairs >= {self.threshold:.2f}: {debug['clustering']['pairs_above_threshold']}"
        )
        
        cluster_indices, merge_info = self._find_clusters_union_find(articles, sim_matrix)
        
        story_clusters = []
        singletons = []
        
        for indices in cluster_indices:
            cluster_articles = [articles[i] for i in indices]
            
            if len(indices) >= self.MIN_CLUSTER_SIZE:
                # Sort by gravity score to get canonical
                sorted_indices = sorted(
                    indices,
                    key=lambda i: articles[i].get('gravity_score', 0),
                    reverse=True
                )
                canonical_idx = sorted_indices[0]
                canonical = articles[canonical_idx]
                related = [articles[i] for i in sorted_indices[1:]]
                
                sources = list(set(a.get('source', 'Unknown') for a in cluster_articles))
                scores = [a.get('gravity_score', 5) for a in cluster_articles]
                avg_score = sum(scores) / len(scores)
                
                # Collect shared entities and buckets
                all_entities = set()
                all_buckets = set()
                for a in cluster_articles:
                    all_entities.update(self._extract_entities(a))
                    all_buckets.update(self._get_bucket_tags(a))
                
                # Count gate types
                merges_by_entity = 0
                merges_by_bucket = 0
                merges_blocked_by_time = 0
                merge_evidence = []
                
                for (i, j), info in merge_info.items():
                    if articles[i] in cluster_articles and articles[j] in cluster_articles:
                        if info['pass_reason'] == 'entity':
                            merges_by_entity += 1
                            ent_str = ','.join(info['shared_entities'][:3])
                            merge_evidence.append(
                                f"sim={info['raw_similarity']:.2f}+entity({ent_str})"
                            )
                        elif info['pass_reason'] == 'bucket':
                            merges_by_bucket += 1
                            bucket_str = ','.join(info['shared_bucket_tags'][:2])
                            merge_evidence.append(
                                f"sim={info['raw_similarity']:.2f}+bucket({bucket_str})"
                            )
                        if info.get('temporal_blocked'):
                            merges_blocked_by_time += 1
                
                # Compute confidence
                conf = self._compute_cluster_confidence(
                    sorted_indices, articles, sim_matrix, self.threshold
                )
                
                cluster_id = hashlib.md5(
                    canonical.get('title', '')[:50].encode()
                ).hexdigest()[:12]
                
                cluster = StoryCluster(
                    cluster_id=cluster_id,
                    canonical_story=canonical,
                    related_stories=related,
                    cluster_size=len(cluster_articles),
                    sources=sources,
                    avg_gravity_score=round(avg_score, 2),
                    topic_summary=canonical.get('gravity_details', {}).get('key_insight', ''),
                    shared_entities=list(all_entities)[:10],
                    shared_bucket_tags=list(all_buckets)[:5],
                    merge_reason='; '.join(merge_evidence[:3]),
                    merge_evidence=merge_evidence[:5],
                    cluster_confidence=conf['confidence'],
                    avg_pair_similarity=conf['avg_pair_similarity'],
                    max_pair_similarity=conf['max_pair_similarity'],
                    confidence_breakdown=conf['confidence_breakdown'],
                    gate_mix={
                        'merges_by_entity': merges_by_entity,
                        'merges_by_bucket': merges_by_bucket,
                        'merges_blocked_by_time': merges_blocked_by_time,
                    },
                    mode=self.mode.value
                )
                story_clusters.append(cluster)
            else:
                singletons.extend(cluster_articles)
        
        logger.info(
            f"Clustering complete: {len(story_clusters)} clusters, "
            f"{len(singletons)} singletons"
        )
        
        self.threshold = self.base_threshold
        
        if return_debug:
            return story_clusters, singletons, debug
        return story_clusters, singletons
    
    def cluster_by_techmeme_related(
        self,
        articles: List[Dict[str, Any]]
    ) -> Tuple[List[StoryCluster], List[Dict[str, Any]]]:
        """Cluster using Techmeme's editorial 'related' links."""
        story_groups = defaultdict(list)
        
        for article in articles:
            related = article.get('related', [])
            if related:
                group_key = related[0] if isinstance(related[0], str) else related[0].get('url', article.get('url'))
            else:
                group_key = article.get('url', id(article))
            story_groups[group_key].append(article)
        
        clusters = []
        singletons = []
        
        for group_key, group_articles in story_groups.items():
            if len(group_articles) >= self.MIN_CLUSTER_SIZE:
                canonical = max(group_articles, key=lambda a: a.get('gravity_score', 0))
                related = [a for a in group_articles if a != canonical]
                sources = list(set(a.get('source', 'Unknown') for a in group_articles))
                
                cluster = StoryCluster(
                    cluster_id=hashlib.md5(str(group_key).encode()).hexdigest()[:12],
                    canonical_story=canonical,
                    related_stories=related,
                    cluster_size=len(group_articles),
                    sources=sources,
                    merge_reason='techmeme_editorial',
                    cluster_confidence=0.95,  # High confidence for editorial
                    mode='techmeme_editorial'
                )
                clusters.append(cluster)
            else:
                singletons.extend(group_articles)
        
        return clusters, singletons


# =============================================================================
# UNIT TESTS
# =============================================================================

def test_bucket_tag_extraction():
    """Test _get_bucket_tags normalization."""
    clustering = StoryClustering(mode=ClusterMode.TOPIC, auto_threshold=False)
    
    article = {
        'bucket_tags': ['AI Chips', 'semiconductor', '  GPU  '],
        'tags': ['ignored']
    }
    tags = clustering._get_bucket_tags(article)
    assert 'ai-chips' in tags
    assert 'semiconductor' in tags
    assert 'gpu' in tags
    assert 'ignored' not in tags  # bucket_tags takes priority
    
    print("[PASS] test_bucket_tag_extraction")


def test_bucket_tag_overlap_allows_merge_topic_mode():
    """Test that bucket overlap allows merge when entities don't match."""
    clustering = StoryClustering(mode=ClusterMode.TOPIC, auto_threshold=False)
    clustering.threshold = 0.60
    
    # No shared entities, but shared bucket tag
    a1 = {
        'title': 'TSMC announces new chip factory',
        'bucket_tags': ['ai-chips', 'manufacturing'],
        'published_at': '2026-02-09T10:00:00Z'
    }
    a2 = {
        'title': 'Intel expands semiconductor production',
        'bucket_tags': ['ai-chips', 'supply-chain'],
        'published_at': '2026-02-09T11:00:00Z'
    }
    
    result = clustering._compute_effective_similarity(0.65, a1, a2)
    
    assert result['passes_bucket_gate'] == True
    assert 'ai-chips' in result['shared_bucket_tags']
    assert result['pass_reason'] in ['entity', 'bucket']
    assert result['passes_gate'] == True
    
    print("[PASS] test_bucket_tag_overlap_allows_merge_topic_mode")


def test_temporal_locality_blocks_merge():
    """Test that articles far apart in time don't merge."""
    clustering = StoryClustering(
        mode=ClusterMode.TOPIC,
        auto_threshold=False,
        max_topic_age_days=7,
        enforce_temporal_locality=True
    )
    clustering.threshold = 0.60
    
    # Same bucket, but 30 days apart
    a1 = {
        'title': 'OpenAI releases GPT-5',
        'bucket_tags': ['llm-release'],
        'published_at': '2026-01-01T10:00:00Z'
    }
    a2 = {
        'title': 'OpenAI GPT-5 gains traction',
        'bucket_tags': ['llm-release'],
        'published_at': '2026-02-01T10:00:00Z'  # 31 days later
    }
    
    result = clustering._compute_effective_similarity(0.75, a1, a2)
    
    assert result['temporal_blocked'] == True
    assert result['delta_days'] > 7
    # Gate should fail due to temporal block
    
    print("[PASS] test_temporal_locality_blocks_merge")


def test_cluster_confidence_increases_with_similarity_and_size():
    """Test confidence scoring increases with better clusters."""
    clustering = StoryClustering(mode=ClusterMode.TOPIC, auto_threshold=False)
    
    # Create mock sim_matrix
    # 3 articles with high similarity
    high_sim = np.array([
        [1.0, 0.85, 0.82],
        [0.85, 1.0, 0.88],
        [0.82, 0.88, 1.0]
    ])
    
    articles_3 = [
        {'title': 'A', 'enriched': True},
        {'title': 'B', 'enriched': True},
        {'title': 'C', 'enriched': True}
    ]
    
    conf_3 = clustering._compute_cluster_confidence(
        [0, 1, 2], articles_3, high_sim, 0.70
    )
    
    # 2 articles with lower similarity
    low_sim = np.array([
        [1.0, 0.72],
        [0.72, 1.0]
    ])
    
    articles_2 = [
        {'title': 'A', 'enriched': False},
        {'title': 'B', 'enriched': False}
    ]
    
    conf_2 = clustering._compute_cluster_confidence(
        [0, 1], articles_2, low_sim, 0.70
    )
    
    # 3-article high-sim cluster should have higher confidence
    assert conf_3['confidence'] > conf_2['confidence'], \
        f"Expected {conf_3['confidence']} > {conf_2['confidence']}"
    assert conf_3['avg_pair_similarity'] > conf_2['avg_pair_similarity']
    
    print("[PASS] test_cluster_confidence_increases_with_similarity_and_size")


def test_debug_report_includes_bucket_and_temporal_fields():
    """Test debug report includes new fields."""
    clustering = StoryClustering(
        mode=ClusterMode.TOPIC,
        auto_threshold=False,
        enforce_temporal_locality=True
    )
    
    articles = [
        {
            'title': 'OpenAI GPT-5 released',
            'bucket_tags': ['llm'],
            'published_at': '2026-02-09T10:00:00Z'
        },
        {
            'title': 'Anthropic Claude update',
            'bucket_tags': ['llm'],
            'published_at': '2026-02-09T11:00:00Z'
        }
    ]
    
    if not clustering.available:
        print("[SKIP] test_debug_report_includes_bucket_and_temporal_fields")
        return
    
    embeddings = clustering._compute_embeddings(articles)
    sim_matrix = clustering._compute_similarity_matrix(embeddings)
    report = clustering.debug_report(articles, embeddings, sim_matrix)
    
    # Check content coverage includes bucket/timestamp counts
    assert 'has_bucket_tags' in report['content_coverage']
    assert 'has_timestamps' in report['content_coverage']
    
    # Check clustering includes temporal fields
    assert 'enforce_temporal_locality' in report['clustering']
    assert 'max_topic_age_days' in report['clustering']
    
    # Check top pairs include new fields
    for pair in report['top_similar_pairs']:
        assert 'passes_bucket_gate' in pair
        assert 'shared_bucket_tags' in pair
        assert 'temporal_blocked' in pair
        assert 'pass_reason' in pair
    
    print("[PASS] test_debug_report_includes_bucket_and_temporal_fields")


def test_embed_summary_priority():
    """Test that TOPIC mode uses embed_summary without body."""
    clustering = StoryClustering(mode=ClusterMode.TOPIC, auto_threshold=False)
    
    article = {
        'title': 'OpenAI launches GPT-5',
        'enriched': True,
        'tldr': 'GPT-5 brings major improvements.',
        'body_text': 'LONG_BODY_MARKER ' * 100,
        'gravity_details': {
            'key_insight': 'GPT-5 is 10x better at reasoning.',
        }
    }
    
    text = clustering._get_article_text(article)
    assert 'OpenAI launches GPT-5' in text
    assert 'GPT-5 is 10x better' in text
    assert 'LONG_BODY_MARKER' not in text
    
    print("[PASS] test_embed_summary_priority")


def test_event_mode_includes_body():
    """Test EVENT mode includes body excerpt."""
    clustering = StoryClustering(mode=ClusterMode.EVENT, auto_threshold=False)
    
    article = {
        'title': 'OpenAI launches GPT-5',
        'enriched': True,
        'body_text': 'UNIQUE_BODY_MARKER details here.',
        'gravity_details': {'key_insight': 'Important insight.'}
    }
    
    text = clustering._get_article_text(article, max_chars=2000)
    assert 'UNIQUE_BODY_MARKER' in text
    
    print("[PASS] test_event_mode_includes_body")


def test_auto_threshold_clamping():
    """Test auto threshold clamps correctly."""
    clustering = StoryClustering(mode=ClusterMode.TOPIC, auto_threshold=True)
    
    # High p95 -> clamp to max
    high_sim = np.array([[1.0, 0.95], [0.95, 1.0]])
    tuned = clustering._auto_tune_threshold(high_sim)
    assert tuned == clustering.TOPIC_THRESHOLD_MAX
    
    # Low p95 -> clamp to min
    low_sim = np.array([[1.0, 0.3], [0.3, 1.0]])
    tuned = clustering._auto_tune_threshold(low_sim)
    assert tuned == clustering.TOPIC_THRESHOLD_MIN
    
    # Mid p95 -> p95 - 0.03
    mid_sim = np.array([[1.0, 0.72], [0.72, 1.0]])
    tuned = clustering._auto_tune_threshold(mid_sim)
    assert abs(tuned - 0.69) < 0.01
    
    print("[PASS] test_auto_threshold_clamping")


def run_tests():
    """Run all unit tests."""
    print("\n=== RUNNING UNIT TESTS ===\n")
    
    test_bucket_tag_extraction()
    test_bucket_tag_overlap_allows_merge_topic_mode()
    test_temporal_locality_blocks_merge()
    test_cluster_confidence_increases_with_similarity_and_size()
    test_debug_report_includes_bucket_and_temporal_fields()
    test_embed_summary_priority()
    test_event_mode_includes_body()
    test_auto_threshold_clamping()
    
    print("\n=== ALL TESTS PASSED ===")


def demo_clustering():
    """Demo with synthetic data."""
    clustering = StoryClustering(mode=ClusterMode.TOPIC, auto_threshold=True)
    
    if not clustering.available:
        print("Clustering not available")
        return
    
    articles = [
        {
            'title': 'OpenAI launches GPT-5 with major improvements',
            'source': 'TechCrunch',
            'enriched': True,
            'bucket_tags': ['llm-release', 'openai'],
            'published_at': '2026-02-09T10:00:00Z',
            'gravity_details': {
                'key_insight': 'GPT-5 shows 10x reasoning improvement.',
            }
        },
        {
            'title': 'GPT-5 released by OpenAI, promises better reasoning',
            'source': 'The Verge',
            'enriched': True,
            'bucket_tags': ['llm-release'],
            'published_at': '2026-02-09T10:30:00Z',
            'gravity_details': {
                'key_insight': 'New GPT-5 dramatically improves reasoning.',
            }
        },
        {
            'title': "OpenAI's GPT-5 arrives with enhanced capabilities",
            'source': 'Wired',
            'enriched': True,
            'bucket_tags': ['llm-release', 'ai-news'],
            'published_at': '2026-02-09T11:00:00Z',
            'gravity_details': {
                'key_insight': 'GPT-5 next generation reasoning.',
            }
        },
        {
            'title': 'Anthropic raises $2B in new funding round',
            'source': 'Bloomberg',
            'enriched': True,
            'bucket_tags': ['ai-funding'],
            'published_at': '2026-02-09T12:00:00Z',
            'gravity_details': {
                'key_insight': 'Anthropic funding for Claude development.',
            }
        },
        {
            'title': 'Google announces Gemini 2.0 multimodal features',
            'source': 'Reuters',
            'enriched': True,
            'bucket_tags': ['llm-release', 'google'],
            'published_at': '2026-02-09T13:00:00Z',
            'gravity_details': {
                'key_insight': 'Gemini 2.0 vision and audio understanding.',
            }
        },
    ]
    
    clusters, singletons, debug = clustering.cluster_stories(articles, return_debug=True)
    
    print("\n=== DEBUG REPORT ===")
    print(json.dumps(debug, indent=2, default=str))
    
    print(f"\n=== RESULTS ===")
    print(f"Clusters found: {len(clusters)}")
    for c in clusters:
        print(f"\n  Cluster: {c.canonical_story['title'][:50]}...")
        print(f"  Sources: {', '.join(c.sources)}")
        print(f"  Size: {c.cluster_size}")
        print(f"  Confidence: {c.cluster_confidence:.2f}")
        print(f"  Shared entities: {c.shared_entities[:5]}")
        print(f"  Shared buckets: {c.shared_bucket_tags}")
        print(f"  Merge evidence: {c.merge_evidence[:2]}")
        print(f"  Gate mix: {c.gate_mix}")
    
    print(f"\nSingletons: {len(singletons)}")
    for s in singletons:
        print(f"  - {s['title'][:50]}...")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        run_tests()
    else:
        demo_clustering()
