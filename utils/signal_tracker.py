"""
Signal Persistence Engine - Link daily THEME clusters into long-lived Signals.

Part of Gravity Engine v2.3: Multi-day trend intelligence.

Transforms the daily dual feed into persistent signals that track:
- Emerging trends (new topics gaining traction)
- Trending signals (accelerating coverage)
- Mainstream signals (saturated coverage)
- Fading/dead signals (declining attention)

Key concepts:
- Signal: A persistent topic/trend tracked across days
- SignalEvent: A single day's cluster linked to a signal
- Linking: Matching today's clusters to existing signals via entity/bucket/embedding overlap
"""

import json
import math
import hashlib
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

from loguru import logger

# Try to import embeddings support
try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    np = None
    logger.info("Embeddings not available, using overlap-only mode for signal tracking")


# =============================================================================
# CONSTANTS
# =============================================================================

LOOKBACK_DAYS = 21          # How far back to look for candidate signals
MAX_GAP_DAYS = 14           # Max gap before requiring strong overlap
LINK_THRESHOLD = 0.72       # Minimum match score to link cluster to signal (with embeddings)
LINK_THRESHOLD_OVERLAP_ONLY = 0.50  # Lower threshold for overlap-only mode
MIN_OVERLAP_THRESHOLD = 0.15  # Minimum entity OR bucket overlap
MIN_EMBEDDING_SIM = 0.72    # Minimum embedding similarity alone

# Metrics windows
WINDOW_7D = 7
WINDOW_21D = 21
BASELINE_WINDOW = 28        # 4 weeks for velocity baseline

# State machine thresholds
EMERGING_MENTIONS_7D = 2
EMERGING_CONFIDENCE = 0.45
TRENDING_MENTIONS_7D = 3
TRENDING_VELOCITY = 1.8
TRENDING_CONFIDENCE = 0.60
MAINSTREAM_MENTIONS_21D = 8
MAINSTREAM_DOMAINS_7D = 5
MAINSTREAM_CONFIDENCE = 0.70
FADING_VELOCITY = 0.9
FADING_DAYS = 7
DEAD_DAYS = 30

# Centroid settings
CENTROID_MAX_EVENTS = 20
EMBEDDING_DECIMALS = 6


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class SignalEvent:
    """A single day's cluster linked to a signal."""
    date: str                       # YYYY-MM-DD
    cluster_id: str
    rank_score: float
    gravity_score: float
    cluster_confidence: float
    sources: List[str]
    domains: List[str]
    entities: List[str]
    buckets: List[str]
    title: str
    url: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'SignalEvent':
        return cls(**d)


@dataclass
class SignalMetrics:
    """Rolling metrics for a signal."""
    mentions_7d: int = 0
    mentions_21d: int = 0
    coverage_sources_7d: int = 0
    coverage_domains_7d: int = 0
    avg_gravity_7d: float = 0.0
    velocity: float = 1.0
    acceleration: float = 0.0
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'mentions_7d': self.mentions_7d,
            'mentions_21d': self.mentions_21d,
            'coverage_sources_7d': self.coverage_sources_7d,
            'coverage_domains_7d': self.coverage_domains_7d,
            'avg_gravity_7d': round(self.avg_gravity_7d, 3),
            'velocity': round(self.velocity, 3),
            'acceleration': round(self.acceleration, 3),
            'confidence': round(self.confidence, 3),
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'SignalMetrics':
        return cls(**d)


@dataclass
class SignalProfile:
    """Profile information for a signal."""
    top_entities: List[str] = field(default_factory=list)
    top_buckets: List[str] = field(default_factory=list)
    example_titles: List[str] = field(default_factory=list)
    key_insight: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'SignalProfile':
        return cls(**d)


@dataclass
class Signal:
    """A persistent signal tracking a topic/trend across days."""
    signal_id: str
    name: str
    created_at: str
    first_seen_date: str
    last_seen_date: str
    status: str                     # weak_signal|emerging|trending|mainstream|fading|dead
    cluster_refs: List[SignalEvent] = field(default_factory=list)
    metrics: SignalMetrics = field(default_factory=SignalMetrics)
    profile: SignalProfile = field(default_factory=SignalProfile)
    embedding: Optional[List[float]] = None  # Centroid embedding (optional)
    
    # Hysteresis tracking (not serialized to main output)
    _consecutive_mainstream_days: int = field(default=0, repr=False)
    _consecutive_fading_weeks: int = field(default=0, repr=False)
    _last_velocity: float = field(default=1.0, repr=False)
    
    def to_dict(self, include_embedding: bool = True) -> Dict[str, Any]:
        result = {
            'signal_id': self.signal_id,
            'name': self.name,
            'created_at': self.created_at,
            'first_seen_date': self.first_seen_date,
            'last_seen_date': self.last_seen_date,
            'status': self.status,
            'cluster_refs': [e.to_dict() for e in self.cluster_refs],
            'metrics': self.metrics.to_dict(),
            'profile': self.profile.to_dict(),
        }
        if include_embedding and self.embedding is not None:
            result['embedding'] = self.embedding
        # Include hysteresis state for state continuity
        result['_hysteresis'] = {
            'consecutive_mainstream_days': self._consecutive_mainstream_days,
            'consecutive_fading_weeks': self._consecutive_fading_weeks,
            'last_velocity': self._last_velocity,
        }
        return result
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Signal':
        hysteresis = d.pop('_hysteresis', {})
        signal = cls(
            signal_id=d['signal_id'],
            name=d['name'],
            created_at=d['created_at'],
            first_seen_date=d['first_seen_date'],
            last_seen_date=d['last_seen_date'],
            status=d['status'],
            cluster_refs=[SignalEvent.from_dict(e) for e in d.get('cluster_refs', [])],
            metrics=SignalMetrics.from_dict(d.get('metrics', {})),
            profile=SignalProfile.from_dict(d.get('profile', {})),
            embedding=d.get('embedding'),
        )
        signal._consecutive_mainstream_days = hysteresis.get('consecutive_mainstream_days', 0)
        signal._consecutive_fading_weeks = hysteresis.get('consecutive_fading_weeks', 0)
        signal._last_velocity = hysteresis.get('last_velocity', 1.0)
        return signal


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def generate_signal_id(entities: List[str], buckets: List[str], date: str) -> str:
    """Generate stable signal ID from entities + buckets + date."""
    key = f"{sorted(entities)[:3]}|{sorted(buckets)[:2]}|{date}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def derive_signal_name(entities: List[str], buckets: List[str]) -> str:
    """
    Derive human-readable signal name from entities and buckets.
    
    Format: "Entity • Bucket" or "Bucket" if no clear entity
    """
    # Clean and prioritize
    clean_entities = [e for e in entities if e and len(e) > 2][:2]
    clean_buckets = [b.replace('-', ' ').title() for b in buckets if b][:2]
    
    if clean_entities and clean_buckets:
        return f"{clean_entities[0]} • {clean_buckets[0]}"
    elif clean_entities:
        return " & ".join(clean_entities[:2])
    elif clean_buckets:
        return " / ".join(clean_buckets[:2])
    else:
        return "Unnamed Signal"


def jaccard_overlap(set_a: Set[str], set_b: Set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def parse_date(date_str: str) -> datetime:
    """Parse YYYY-MM-DD date string."""
    return datetime.strptime(date_str, '%Y-%m-%d')


def format_date(dt: datetime) -> str:
    """Format datetime as YYYY-MM-DD."""
    return dt.strftime('%Y-%m-%d')


def days_between(date1: str, date2: str) -> int:
    """Calculate days between two date strings."""
    d1 = parse_date(date1)
    d2 = parse_date(date2)
    return abs((d2 - d1).days)


# =============================================================================
# EMBEDDING HELPERS
# =============================================================================

class EmbeddingHelper:
    """Helper for computing and comparing embeddings."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.available = EMBEDDINGS_AVAILABLE
        self.model = None
        self.model_name = model_name
        
        if self.available:
            try:
                logger.info(f"Loading embedding model for signal tracking: {model_name}")
                self.model = SentenceTransformer(model_name)
            except Exception as e:
                logger.warning(f"Failed to load embedding model: {e}")
                self.available = False
    
    def build_embed_text(self, item: Dict[str, Any]) -> str:
        """Build text for embedding from cluster/singleton item."""
        parts = []
        
        # For clusters
        if 'canonical' in item:
            canonical = item['canonical']
            if canonical.get('title'):
                parts.append(canonical['title'])
            if canonical.get('key_insight'):
                parts.append(canonical['key_insight'])
            if canonical.get('tldr'):
                parts.append(canonical['tldr'])
        # For singletons
        elif 'article' in item:
            article = item['article']
            if article.get('title'):
                parts.append(article['title'])
            if article.get('key_insight'):
                parts.append(article['key_insight'])
            if article.get('tldr'):
                parts.append(article['tldr'])
        
        return '. '.join(p.strip().rstrip('.') for p in parts if p)
    
    def compute_embedding(self, text: str) -> Optional[List[float]]:
        """Compute embedding for text, return as list of floats."""
        if not self.available or not self.model or not text:
            return None
        
        try:
            embedding = self.model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
            # Round to save space
            return [round(float(x), EMBEDDING_DECIMALS) for x in embedding]
        except Exception as e:
            logger.warning(f"Embedding computation failed: {e}")
            return None
    
    def cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        
        if self.available and np is not None:
            a = np.array(vec_a)
            b = np.array(vec_b)
            dot = np.dot(a, b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return float(dot / (norm_a * norm_b))
        else:
            # Pure Python fallback
            dot = sum(a * b for a, b in zip(vec_a, vec_b))
            norm_a = math.sqrt(sum(a * a for a in vec_a))
            norm_b = math.sqrt(sum(b * b for b in vec_b))
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)
    
    def compute_centroid(self, embeddings: List[List[float]]) -> Optional[List[float]]:
        """Compute centroid (average) of embeddings."""
        if not embeddings:
            return None
        
        if self.available and np is not None:
            arr = np.array(embeddings)
            centroid = np.mean(arr, axis=0)
            # Normalize
            norm = np.linalg.norm(centroid)
            if norm > 0:
                centroid = centroid / norm
            return [round(float(x), EMBEDDING_DECIMALS) for x in centroid]
        else:
            # Pure Python fallback
            n = len(embeddings)
            dim = len(embeddings[0])
            centroid = [sum(e[i] for e in embeddings) / n for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in centroid))
            if norm > 0:
                centroid = [x / norm for x in centroid]
            return [round(x, EMBEDDING_DECIMALS) for x in centroid]


# =============================================================================
# SIGNAL TRACKER
# =============================================================================

class SignalTracker:
    """
    Track signals across days by linking THEME clusters to persistent signals.
    """
    
    def __init__(
        self,
        signals_dir: Path = None,
        use_embeddings: bool = True,
        lookback_days: int = LOOKBACK_DAYS,
        link_threshold: float = LINK_THRESHOLD,
    ):
        """
        Initialize signal tracker.
        
        Args:
            signals_dir: Directory for signal state files
            use_embeddings: Whether to use embeddings (if available)
            lookback_days: How far back to look for candidate signals
            link_threshold: Minimum match score to link cluster to signal
        """
        if signals_dir is None:
            signals_dir = Path(__file__).parent.parent / "data" / "gravity" / "signals"
        
        self.signals_dir = Path(signals_dir)
        self.signals_dir.mkdir(parents=True, exist_ok=True)
        
        self.lookback_days = lookback_days
        self.link_threshold = link_threshold
        
        # Embeddings
        self.use_embeddings = use_embeddings
        self.embedding_helper = None
        if use_embeddings:
            self.embedding_helper = EmbeddingHelper()
            if not self.embedding_helper.available:
                logger.info("Embeddings unavailable, using overlap-only mode")
        
        # State
        self.signals: Dict[str, Signal] = {}
        self._load_state()
    
    @property
    def state_file(self) -> Path:
        return self.signals_dir / "signals_state.json"
    
    def snapshot_file(self, date: str) -> Path:
        return self.signals_dir / f"signals_snapshot_{date}.json"
    
    def _load_state(self):
        """Load signals state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for s in data.get('signals', []):
                    signal = Signal.from_dict(s)
                    self.signals[signal.signal_id] = signal
                
                logger.info(f"Loaded {len(self.signals)} signals from state")
            except Exception as e:
                logger.error(f"Failed to load signals state: {e}")
                self.signals = {}
        else:
            logger.info("No existing signals state, starting fresh")
    
    def _save_state(self):
        """Save signals state to file."""
        data = {
            'version': '2.3',
            'updated_at': datetime.now().isoformat(),
            'signal_count': len(self.signals),
            'signals': [s.to_dict(include_embedding=True) for s in self.signals.values()],
        }
        
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(self.signals)} signals to state")
    
    def _save_snapshot(self, date: str, stats: Dict[str, Any]):
        """Save daily snapshot."""
        # Rank signals by composite score
        ranked = sorted(
            self.signals.values(),
            key=lambda s: s.metrics.confidence * s.metrics.velocity * s.metrics.avg_gravity_7d,
            reverse=True
        )
        
        data = {
            'date': date,
            'generated_at': datetime.now().isoformat(),
            'stats': stats,
            'top_signals': [s.to_dict(include_embedding=False) for s in ranked[:10]],
            'all_signals': [
                {
                    'signal_id': s.signal_id,
                    'name': s.name,
                    'status': s.status,
                    'metrics': s.metrics.to_dict(),
                }
                for s in ranked
            ],
        }
        
        with open(self.snapshot_file(date), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    # =========================================================================
    # EXTRACTION HELPERS
    # =========================================================================
    
    def _extract_from_cluster_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardized fields from a cluster or singleton item."""
        result = {
            'cluster_id': item.get('cluster_id', ''),
            'rank_score': item.get('rank_score', 5.0),
            'gravity_score': item.get('gravity_score', 5.0),
            'cluster_confidence': 0.0,
            'sources': [],
            'domains': [],
            'entities': [],
            'buckets': [],
            'title': '',
            'url': '',
        }
        
        if item.get('item_type') == 'cluster':
            # Cluster item
            canonical = item.get('canonical', {})
            result['title'] = canonical.get('title', '')
            result['url'] = canonical.get('url', '')
            result['cluster_id'] = item.get('cluster_id', hashlib.md5(result['title'].encode()).hexdigest()[:12])
            
            # Stats
            stats = item.get('cluster_stats', {})
            result['cluster_confidence'] = stats.get('cluster_confidence', item.get('confidence_bonus', 0) * 2)
            result['entities'] = stats.get('shared_entities', [])
            result['buckets'] = stats.get('shared_bucket_tags', [])
            
            # Domains from top_domains or related
            result['domains'] = item.get('top_domains', [])
            
            # Sources from canonical + related
            sources = [canonical.get('source', '')]
            for rel in item.get('related', []):
                if rel.get('source'):
                    sources.append(rel['source'])
            result['sources'] = list(set(s for s in sources if s))
            
        elif item.get('item_type') == 'singleton':
            # Singleton item
            article = item.get('article', {})
            result['title'] = article.get('title', '')
            result['url'] = article.get('url', '')
            result['cluster_id'] = hashlib.md5(result['url'].encode()).hexdigest()[:12] if result['url'] else 'singleton'
            result['cluster_confidence'] = 0.3  # Lower confidence for singletons
            
            source = article.get('source', '')
            result['sources'] = [source] if source else []
            
            # Extract domain from URL
            if result['url']:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(result['url']).netloc.lower()
                    if domain.startswith('www.'):
                        domain = domain[4:]
                    result['domains'] = [domain] if domain else []
                except Exception:
                    pass
            
            # Try to extract entities from title
            result['entities'] = self._extract_entities_from_title(result['title'])
        
        return result
    
    def _extract_entities_from_title(self, title: str) -> List[str]:
        """Extract basic entities from title (simplified extraction)."""
        if not title:
            return []
        
        entities = set()
        words = title.split()
        
        # Known tech entities
        known = [
            'openai', 'anthropic', 'google', 'meta', 'microsoft', 'apple',
            'nvidia', 'amazon', 'claude', 'gpt', 'gemini', 'llama',
            'chatgpt', 'copilot', 'midjourney', 'deepmind', 'mistral',
        ]
        title_lower = title.lower()
        for entity in known:
            if entity in title_lower:
                entities.add(entity)
        
        # Capitalized words (not at sentence start)
        for i, word in enumerate(words):
            if i == 0:
                continue
            clean = word.strip('.,!?:;"\'-()[]')
            if clean and clean[0].isupper() and len(clean) >= 2:
                entities.add(clean.lower())
        
        return list(entities)[:5]
    
    # =========================================================================
    # LINKING ALGORITHM
    # =========================================================================
    
    def _compute_match_score(
        self,
        cluster_data: Dict[str, Any],
        signal: Signal,
        cluster_embedding: Optional[List[float]],
        current_date: str,
    ) -> Tuple[float, Dict[str, float]]:
        """
        Compute match score between a cluster and a signal.
        
        Returns (match_score, breakdown_dict)
        """
        breakdown = {}
        
        # Entity overlap
        cluster_entities = set(e.lower() for e in cluster_data.get('entities', []))
        signal_entities = set(e.lower() for e in signal.profile.top_entities)
        entity_overlap = jaccard_overlap(cluster_entities, signal_entities)
        breakdown['entity_overlap'] = round(entity_overlap, 3)
        
        # Bucket overlap
        cluster_buckets = set(b.lower() for b in cluster_data.get('buckets', []))
        signal_buckets = set(b.lower() for b in signal.profile.top_buckets)
        bucket_overlap = jaccard_overlap(cluster_buckets, signal_buckets)
        breakdown['bucket_overlap'] = round(bucket_overlap, 3)
        
        # Time decay
        delta_days = days_between(signal.last_seen_date, current_date)
        time_decay = math.exp(-delta_days / 10.0)
        breakdown['time_decay'] = round(time_decay, 3)
        breakdown['delta_days'] = delta_days
        
        # Embedding similarity
        embedding_sim = 0.0
        if cluster_embedding and signal.embedding:
            embedding_sim = self.embedding_helper.cosine_similarity(cluster_embedding, signal.embedding) if self.embedding_helper else 0.0
        breakdown['embedding_sim'] = round(embedding_sim, 3)
        
        # Compute total match score
        if embedding_sim > 0:
            # Full formula with embeddings
            match = (
                0.55 * embedding_sim +
                0.20 * entity_overlap +
                0.15 * bucket_overlap +
                0.10 * time_decay
            )
        else:
            # Fallback: overlap-only
            match = (
                0.60 * entity_overlap +
                0.40 * bucket_overlap
            )
        
        breakdown['match_score'] = round(match, 3)
        
        return match, breakdown
    
    def _check_link_requirements(
        self,
        match_score: float,
        breakdown: Dict[str, float],
        delta_days: int,
    ) -> bool:
        """Check if linking requirements are met."""
        # Determine threshold based on mode
        has_embedding = breakdown.get('embedding_sim', 0) > 0
        threshold = self.link_threshold if has_embedding else LINK_THRESHOLD_OVERLAP_ONLY
        
        # Basic threshold
        if match_score < threshold:
            return False
        
        # Require minimum overlap for linking
        entity_ok = breakdown.get('entity_overlap', 0) >= MIN_OVERLAP_THRESHOLD
        bucket_ok = breakdown.get('bucket_overlap', 0) >= MIN_OVERLAP_THRESHOLD
        embedding_ok = breakdown.get('embedding_sim', 0) >= MIN_EMBEDDING_SIM
        
        if not (entity_ok or bucket_ok or embedding_ok):
            return False
        
        # Extra check for large gaps
        if delta_days > MAX_GAP_DAYS:
            # Require strong overlap for large gaps
            if not (entity_ok or bucket_ok):
                return False
        
        return True
    
    def _find_best_signal(
        self,
        cluster_data: Dict[str, Any],
        cluster_embedding: Optional[List[float]],
        current_date: str,
    ) -> Tuple[Optional[Signal], float, Dict[str, float]]:
        """
        Find the best matching signal for a cluster.
        
        Returns (signal, match_score, breakdown) or (None, 0, {}) if no match.
        """
        best_signal = None
        best_score = 0.0
        best_breakdown = {}
        
        current_dt = parse_date(current_date)
        cutoff_dt = current_dt - timedelta(days=self.lookback_days)
        
        for signal in self.signals.values():
            # Skip dead signals
            if signal.status == 'dead':
                continue
            
            # Check lookback window
            last_seen_dt = parse_date(signal.last_seen_date)
            if last_seen_dt < cutoff_dt:
                continue
            
            score, breakdown = self._compute_match_score(
                cluster_data, signal, cluster_embedding, current_date
            )
            
            if score > best_score:
                if self._check_link_requirements(score, breakdown, breakdown.get('delta_days', 0)):
                    best_signal = signal
                    best_score = score
                    best_breakdown = breakdown
        
        return best_signal, best_score, best_breakdown
    
    # =========================================================================
    # SIGNAL CREATION & UPDATE
    # =========================================================================
    
    def _create_signal(
        self,
        cluster_data: Dict[str, Any],
        cluster_embedding: Optional[List[float]],
        current_date: str,
    ) -> Signal:
        """Create a new signal from a cluster."""
        entities = cluster_data.get('entities', [])
        buckets = cluster_data.get('buckets', [])
        
        signal_id = generate_signal_id(entities, buckets, current_date)
        name = derive_signal_name(entities, buckets)
        
        now = datetime.now().isoformat()
        
        signal = Signal(
            signal_id=signal_id,
            name=name,
            created_at=now,
            first_seen_date=current_date,
            last_seen_date=current_date,
            status='weak_signal',
            profile=SignalProfile(
                top_entities=entities[:5],
                top_buckets=buckets[:3],
                example_titles=[cluster_data['title']] if cluster_data['title'] else [],
                key_insight='',
            ),
            embedding=cluster_embedding,
        )
        
        return signal
    
    def _add_event_to_signal(
        self,
        signal: Signal,
        cluster_data: Dict[str, Any],
        cluster_embedding: Optional[List[float]],
        current_date: str,
    ):
        """Add a cluster event to a signal."""
        event = SignalEvent(
            date=current_date,
            cluster_id=cluster_data['cluster_id'],
            rank_score=cluster_data['rank_score'],
            gravity_score=cluster_data['gravity_score'],
            cluster_confidence=cluster_data['cluster_confidence'],
            sources=cluster_data['sources'],
            domains=cluster_data['domains'],
            entities=cluster_data['entities'],
            buckets=cluster_data['buckets'],
            title=cluster_data['title'],
            url=cluster_data['url'],
        )
        
        signal.cluster_refs.append(event)
        signal.last_seen_date = current_date
        
        # Keep rolling window (last 60 days)
        cutoff = parse_date(current_date) - timedelta(days=60)
        signal.cluster_refs = [
            e for e in signal.cluster_refs
            if parse_date(e.date) >= cutoff
        ]
        
        # Update profile
        self._update_signal_profile(signal)
        
        # Update centroid embedding
        if cluster_embedding and self.embedding_helper:
            self._update_signal_centroid(signal, cluster_embedding)
    
    def _update_signal_profile(self, signal: Signal):
        """Update signal profile from recent events."""
        if not signal.cluster_refs:
            return
        
        # Aggregate from recent events
        entity_counts = defaultdict(int)
        bucket_counts = defaultdict(int)
        recent_titles = []
        
        for event in signal.cluster_refs[-20:]:
            for e in event.entities:
                entity_counts[e.lower()] += 1
            for b in event.buckets:
                bucket_counts[b.lower()] += 1
            if event.title and event.title not in recent_titles:
                recent_titles.append(event.title)
        
        # Top entities/buckets
        signal.profile.top_entities = [
            e for e, _ in sorted(entity_counts.items(), key=lambda x: -x[1])
        ][:5]
        signal.profile.top_buckets = [
            b for b, _ in sorted(bucket_counts.items(), key=lambda x: -x[1])
        ][:3]
        
        # Recent example titles
        signal.profile.example_titles = recent_titles[-3:]
        
        # Update name if we have better info now
        if signal.profile.top_entities or signal.profile.top_buckets:
            signal.name = derive_signal_name(
                signal.profile.top_entities,
                signal.profile.top_buckets
            )
    
    def _update_signal_centroid(self, signal: Signal, new_embedding: List[float]):
        """Update signal centroid with new embedding."""
        if not self.embedding_helper:
            return
        
        # Collect recent embeddings
        # For simplicity, we just average old centroid with new embedding
        if signal.embedding:
            # Weighted average favoring recent
            old_weight = 0.7
            new_weight = 0.3
            signal.embedding = [
                round(old_weight * o + new_weight * n, EMBEDDING_DECIMALS)
                for o, n in zip(signal.embedding, new_embedding)
            ]
            # Re-normalize
            if EMBEDDINGS_AVAILABLE and np is not None:
                arr = np.array(signal.embedding)
                norm = np.linalg.norm(arr)
                if norm > 0:
                    signal.embedding = [round(float(x / norm), EMBEDDING_DECIMALS) for x in arr]
        else:
            signal.embedding = new_embedding
    
    # =========================================================================
    # METRICS COMPUTATION
    # =========================================================================
    
    def _compute_metrics(self, signal: Signal, current_date: str):
        """Compute rolling metrics for a signal."""
        current_dt = parse_date(current_date)
        
        # Filter events by windows
        events_7d = [
            e for e in signal.cluster_refs
            if (current_dt - parse_date(e.date)).days <= WINDOW_7D
        ]
        events_21d = [
            e for e in signal.cluster_refs
            if (current_dt - parse_date(e.date)).days <= WINDOW_21D
        ]
        
        # Basic counts
        signal.metrics.mentions_7d = len(events_7d)
        signal.metrics.mentions_21d = len(events_21d)
        
        # Coverage
        domains_7d = set()
        sources_7d = set()
        gravity_7d = []
        
        for e in events_7d:
            domains_7d.update(e.domains)
            sources_7d.update(e.sources)
            gravity_7d.append(e.gravity_score)
        
        signal.metrics.coverage_domains_7d = len(domains_7d)
        signal.metrics.coverage_sources_7d = len(sources_7d)
        signal.metrics.avg_gravity_7d = sum(gravity_7d) / len(gravity_7d) if gravity_7d else 0.0
        
        # Velocity (compared to baseline)
        # Baseline = avg mentions per 7d over prior 4 weeks (days -35 to -8)
        baseline_start = current_dt - timedelta(days=35)
        baseline_end = current_dt - timedelta(days=8)
        
        baseline_events = [
            e for e in signal.cluster_refs
            if baseline_start <= parse_date(e.date) <= baseline_end
        ]
        
        # Baseline mentions per week
        baseline_weeks = 4
        baseline_per_week = len(baseline_events) / baseline_weeks if baseline_events else 0
        baseline = max(1.0, baseline_per_week)
        
        signal.metrics.velocity = signal.metrics.mentions_7d / baseline
        
        # Acceleration (velocity delta vs prior week)
        prior_velocity = signal._last_velocity
        signal.metrics.acceleration = signal.metrics.velocity - prior_velocity
        signal._last_velocity = signal.metrics.velocity
        
        # Confidence
        avg_cluster_conf = 0.0
        if events_7d:
            avg_cluster_conf = sum(e.cluster_confidence for e in events_7d) / len(events_7d)
        
        confidence = (
            0.25 * avg_cluster_conf +
            0.25 * min(1.0, signal.metrics.coverage_domains_7d / 6) +
            0.20 * min(1.0, signal.metrics.mentions_21d / 8) +
            0.30 * min(1.0, signal.metrics.velocity / 3.0)
        )
        signal.metrics.confidence = max(0.0, min(1.0, confidence))
    
    # =========================================================================
    # STATE MACHINE
    # =========================================================================
    
    def _update_signal_status(self, signal: Signal, current_date: str):
        """Update signal status based on metrics and hysteresis rules."""
        m = signal.metrics
        old_status = signal.status
        
        # Check for dead (30 days without mentions)
        days_since_last = days_between(signal.last_seen_date, current_date)
        if days_since_last >= DEAD_DAYS:
            signal.status = 'dead'
            return
        
        # Check for fading (velocity < 0.9 for 2 consecutive weeks OR no mentions in 7d but seen in 21d)
        if m.mentions_7d == 0 and m.mentions_21d > 0:
            signal._consecutive_fading_weeks += 1
            if signal._consecutive_fading_weeks >= 1:  # After 7 days of no events
                signal.status = 'fading'
                return
        elif m.velocity < FADING_VELOCITY:
            signal._consecutive_fading_weeks += 1
            if signal._consecutive_fading_weeks >= 2:
                signal.status = 'fading'
                return
        else:
            signal._consecutive_fading_weeks = 0
        
        # Check for mainstream (requires 2 consecutive days meeting criteria)
        mainstream_criteria = (
            m.mentions_21d >= MAINSTREAM_MENTIONS_21D and
            m.coverage_domains_7d >= MAINSTREAM_DOMAINS_7D and
            m.confidence >= MAINSTREAM_CONFIDENCE
        )
        
        if mainstream_criteria:
            signal._consecutive_mainstream_days += 1
            if signal._consecutive_mainstream_days >= 2:
                signal.status = 'mainstream'
                return
        else:
            signal._consecutive_mainstream_days = 0
        
        # Check for trending
        if (m.mentions_7d >= TRENDING_MENTIONS_7D and
            m.velocity >= TRENDING_VELOCITY and
            m.confidence >= TRENDING_CONFIDENCE):
            signal.status = 'trending'
            return
        
        # Check for emerging
        if m.mentions_7d >= EMERGING_MENTIONS_7D and m.confidence >= EMERGING_CONFIDENCE:
            signal.status = 'emerging'
            return
        
        # Default: weak_signal (but don't downgrade from higher states without fading check)
        if old_status == 'weak_signal':
            signal.status = 'weak_signal'
    
    # =========================================================================
    # MAIN UPDATE LOGIC
    # =========================================================================
    
    def update_from_dual_feed(
        self,
        dual_feed: Dict[str, Any],
        date: str = None,
    ) -> Dict[str, Any]:
        """
        Update signals from a dual feed's THEME section.
        
        Args:
            dual_feed: Dual feed dict (from JSON)
            date: Date string (defaults to feed's date)
        
        Returns:
            Stats dict with counts
        """
        if date is None:
            date = dual_feed.get('date', format_date(datetime.now()))
        
        logger.info(f"Processing signals for {date}")
        
        # Get theme items
        theme_items = dual_feed.get('top_themes', {}).get('items', [])
        if not theme_items:
            logger.warning("No theme items in dual feed")
            # Still update metrics for existing signals (for fading/dead detection)
            self._update_all_signals(date)
            self._save_state()
            return {'date': date, 'items_processed': 0, 'signals_created': 0, 'signals_updated': 0}
        
        stats = {
            'date': date,
            'items_processed': len(theme_items),
            'signals_created': 0,
            'signals_updated': 0,
            'links': [],
        }
        
        # Process each theme item
        for item in theme_items:
            cluster_data = self._extract_from_cluster_item(item)
            
            # Compute embedding if available
            cluster_embedding = None
            if self.embedding_helper and self.embedding_helper.available:
                embed_text = self.embedding_helper.build_embed_text(item)
                cluster_embedding = self.embedding_helper.compute_embedding(embed_text)
            
            # Find best matching signal
            best_signal, match_score, breakdown = self._find_best_signal(
                cluster_data, cluster_embedding, date
            )
            
            if best_signal:
                # Link to existing signal
                self._add_event_to_signal(best_signal, cluster_data, cluster_embedding, date)
                stats['signals_updated'] += 1
                stats['links'].append({
                    'cluster_id': cluster_data['cluster_id'],
                    'signal_id': best_signal.signal_id,
                    'signal_name': best_signal.name,
                    'match_score': match_score,
                })
                logger.debug(f"Linked cluster to signal '{best_signal.name}' (score={match_score:.2f})")
            else:
                # Create new signal
                new_signal = self._create_signal(cluster_data, cluster_embedding, date)
                self._add_event_to_signal(new_signal, cluster_data, cluster_embedding, date)
                self.signals[new_signal.signal_id] = new_signal
                stats['signals_created'] += 1
                stats['links'].append({
                    'cluster_id': cluster_data['cluster_id'],
                    'signal_id': new_signal.signal_id,
                    'signal_name': new_signal.name,
                    'match_score': 0,
                    'new': True,
                })
                logger.debug(f"Created new signal '{new_signal.name}'")
        
        # Update metrics and status for all active signals
        self._update_all_signals(date)
        
        # Save state and snapshot
        self._save_state()
        self._save_snapshot(date, stats)
        
        logger.info(
            f"Signal update complete: {stats['signals_created']} created, "
            f"{stats['signals_updated']} updated, {len(self.signals)} total signals"
        )
        
        return stats
    
    def _update_all_signals(self, current_date: str):
        """Update metrics and status for all signals."""
        for signal in self.signals.values():
            if signal.status != 'dead':
                self._compute_metrics(signal, current_date)
                self._update_signal_status(signal, current_date)
    
    def process_days(
        self,
        dates: List[str],
        dual_feed_dir: Path = None,
    ) -> List[Dict[str, Any]]:
        """
        Process multiple days sequentially.
        
        Args:
            dates: List of date strings in chronological order
            dual_feed_dir: Directory containing dual feed files
        
        Returns:
            List of stats dicts, one per day
        """
        if dual_feed_dir is None:
            dual_feed_dir = Path(__file__).parent.parent / "data" / "gravity"
        
        dual_feed_dir = Path(dual_feed_dir)
        all_stats = []
        
        for date in sorted(dates):
            feed_file = dual_feed_dir / f"dual_feed_{date}.json"
            
            if not feed_file.exists():
                logger.warning(f"No dual feed for {date}, skipping")
                continue
            
            try:
                with open(feed_file, 'r', encoding='utf-8') as f:
                    dual_feed = json.load(f)
                
                stats = self.update_from_dual_feed(dual_feed, date)
                all_stats.append(stats)
                
            except Exception as e:
                logger.error(f"Failed to process {date}: {e}")
        
        return all_stats
    
    def get_active_signals(self, exclude_dead: bool = True) -> List[Signal]:
        """Get list of active signals."""
        signals = list(self.signals.values())
        if exclude_dead:
            signals = [s for s in signals if s.status != 'dead']
        return sorted(signals, key=lambda s: -s.metrics.confidence)
    
    def get_signal_summary(self) -> Dict[str, Any]:
        """Get summary of signal states."""
        by_status = defaultdict(int)
        for s in self.signals.values():
            by_status[s.status] += 1
        
        return {
            'total': len(self.signals),
            'by_status': dict(by_status),
            'active': len([s for s in self.signals.values() if s.status not in ('dead', 'fading')]),
        }


# =============================================================================
# TESTS (inline for quick validation)
# =============================================================================

def _test_signal_event_serialization():
    """Test SignalEvent serialization."""
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
    
    print("[PASS] _test_signal_event_serialization")


def _test_signal_serialization():
    """Test Signal serialization."""
    signal = Signal(
        signal_id='sig123',
        name='OpenAI • LLM Release',
        created_at='2026-02-01T10:00:00',
        first_seen_date='2026-02-01',
        last_seen_date='2026-02-09',
        status='emerging',
        metrics=SignalMetrics(mentions_7d=5, velocity=2.1, confidence=0.72),
        profile=SignalProfile(top_entities=['openai'], top_buckets=['llm-release']),
        embedding=[0.1, 0.2, 0.3],
    )
    
    d = signal.to_dict()
    restored = Signal.from_dict(d)
    
    assert restored.signal_id == signal.signal_id
    assert restored.status == signal.status
    assert restored.metrics.mentions_7d == signal.metrics.mentions_7d
    assert restored.embedding == signal.embedding
    
    print("[PASS] _test_signal_serialization")


def _test_jaccard_overlap():
    """Test Jaccard overlap computation."""
    a = {'openai', 'gpt', 'llm'}
    b = {'openai', 'anthropic', 'llm'}
    
    overlap = jaccard_overlap(a, b)
    # Intersection: openai, llm (2)
    # Union: openai, gpt, llm, anthropic (4)
    assert overlap == 0.5
    
    # Empty sets
    assert jaccard_overlap(set(), {'a'}) == 0.0
    assert jaccard_overlap(set(), set()) == 0.0
    
    print("[PASS] _test_jaccard_overlap")


def _test_signal_naming():
    """Test signal name derivation."""
    name = derive_signal_name(['OpenAI', 'ChatGPT'], ['llm-release', 'product-launch'])
    assert 'OpenAI' in name
    assert 'Llm Release' in name or 'llm-release' in name.lower()
    
    # Entity only
    name = derive_signal_name(['Anthropic'], [])
    assert 'Anthropic' in name
    
    # Bucket only
    name = derive_signal_name([], ['ai-funding'])
    assert 'Funding' in name
    
    print("[PASS] _test_signal_naming")


def _test_days_between():
    """Test date difference calculation."""
    assert days_between('2026-02-01', '2026-02-09') == 8
    assert days_between('2026-02-09', '2026-02-01') == 8
    assert days_between('2026-02-09', '2026-02-09') == 0
    
    print("[PASS] _test_days_between")


def run_tests():
    """Run all unit tests."""
    print("\n=== SIGNAL TRACKER TESTS ===\n")
    
    _test_signal_event_serialization()
    _test_signal_serialization()
    _test_jaccard_overlap()
    _test_signal_naming()
    _test_days_between()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
