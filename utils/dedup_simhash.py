"""
SimHash Deduplication Module

Provides content-based deduplication using SimHash fingerprinting
with LSH (Locality-Sensitive Hashing) for efficient O(1) lookups.

This prevents duplicate articles from consuming LLM budget.
"""

import re
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict
import json
from pathlib import Path


@dataclass
class SimHashConfig:
    """Configuration for SimHash deduplication."""
    hash_bits: int = 64              # Hash size in bits
    hamming_threshold: int = 3       # Max Hamming distance for duplicates
    band_count: int = 8              # Number of LSH bands
    min_content_length: int = 100    # Minimum content length to hash
    ngram_size: int = 3              # Size of character n-grams
    cache_ttl_days: int = 30         # How long to keep fingerprints


@dataclass
class DedupResult:
    """Result of deduplication check."""
    content_hash: str           # SimHash fingerprint (hex)
    is_duplicate: bool
    duplicate_of: Optional[str] = None  # ID of original if duplicate
    hamming_distance: Optional[int] = None
    similarity: Optional[float] = None  # 1 - (distance / bits)


class SimHasher:
    """
    SimHash fingerprinting for content-based deduplication.

    SimHash produces similar hashes for similar content, allowing
    near-duplicate detection with configurable threshold.
    """

    def __init__(self, config: SimHashConfig = None):
        """Initialize SimHash calculator."""
        self.config = config or SimHashConfig()
        self._stopwords = self._load_stopwords()

    def _load_stopwords(self) -> Set[str]:
        """Load common English stopwords."""
        return {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'up', 'about', 'into', 'over', 'after',
            'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has',
            'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
            'this', 'that', 'these', 'those', 'it', 'its', 'they', 'their',
            'we', 'our', 'you', 'your', 'he', 'she', 'him', 'her', 'his',
        }

    def preprocess(self, text: str) -> List[str]:
        """
        Preprocess text for fingerprinting.

        - Lowercase
        - Remove special characters
        - Remove stopwords
        - Tokenize
        """
        # Lowercase and remove special chars
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', ' ', text)

        # Tokenize
        tokens = text.split()

        # Remove stopwords and short tokens
        tokens = [t for t in tokens if t not in self._stopwords and len(t) > 2]

        return tokens

    def get_ngrams(self, tokens: List[str], n: int = None) -> List[str]:
        """Generate n-grams from tokens."""
        n = n or self.config.ngram_size

        if len(tokens) < n:
            return tokens

        ngrams = []
        for i in range(len(tokens) - n + 1):
            ngrams.append(' '.join(tokens[i:i+n]))

        return ngrams

    def compute_simhash(self, text: str) -> int:
        """
        Compute SimHash fingerprint for text.

        Algorithm:
        1. Extract features (tokens/n-grams)
        2. Hash each feature
        3. Weight: +1 for 1-bit, -1 for 0-bit
        4. Sum weights per bit position
        5. Final hash: 1 if sum > 0, else 0

        Returns:
            Integer fingerprint
        """
        if len(text) < self.config.min_content_length:
            # Too short for reliable fingerprinting
            return hash(text) & ((1 << self.config.hash_bits) - 1)

        tokens = self.preprocess(text)
        features = self.get_ngrams(tokens)

        if not features:
            return hash(text) & ((1 << self.config.hash_bits) - 1)

        # Initialize weight vector
        weights = [0] * self.config.hash_bits

        for feature in features:
            # Hash the feature
            h = int(hashlib.md5(feature.encode()).hexdigest(), 16)
            h = h & ((1 << self.config.hash_bits) - 1)

            # Update weights
            for i in range(self.config.hash_bits):
                if h & (1 << i):
                    weights[i] += 1
                else:
                    weights[i] -= 1

        # Build final hash from weights
        fingerprint = 0
        for i in range(self.config.hash_bits):
            if weights[i] > 0:
                fingerprint |= (1 << i)

        return fingerprint

    def fingerprint_to_hex(self, fingerprint: int) -> str:
        """Convert fingerprint to hex string."""
        return format(fingerprint, f'0{self.config.hash_bits // 4}x')

    def hex_to_fingerprint(self, hex_str: str) -> int:
        """Convert hex string back to fingerprint."""
        return int(hex_str, 16)

    def hamming_distance(self, fp1: int, fp2: int) -> int:
        """
        Compute Hamming distance between two fingerprints.

        Hamming distance = number of differing bits.
        """
        xor = fp1 ^ fp2
        return bin(xor).count('1')

    def similarity(self, fp1: int, fp2: int) -> float:
        """
        Compute similarity between fingerprints.

        Returns:
            Similarity score 0-1 (1 = identical)
        """
        distance = self.hamming_distance(fp1, fp2)
        return 1 - (distance / self.config.hash_bits)

    def is_duplicate(self, fp1: int, fp2: int) -> bool:
        """Check if two fingerprints represent duplicates."""
        return self.hamming_distance(fp1, fp2) <= self.config.hamming_threshold


class LSHIndex:
    """
    Locality-Sensitive Hashing index for O(1) duplicate lookup.

    Divides the hash into bands for efficient candidate lookup.
    """

    def __init__(self, config: SimHashConfig = None):
        """Initialize LSH index."""
        self.config = config or SimHashConfig()
        self.hasher = SimHasher(config)

        # Band configuration
        self.band_count = self.config.band_count
        self.rows_per_band = self.config.hash_bits // self.band_count

        # Index: band_idx -> band_hash -> list of (doc_id, full_fingerprint)
        self.index: Dict[int, Dict[int, List[Tuple[str, int]]]] = defaultdict(
            lambda: defaultdict(list)
        )

        # Full fingerprint store: doc_id -> fingerprint
        self.fingerprints: Dict[str, int] = {}

        # Metadata: doc_id -> metadata dict
        self.metadata: Dict[str, Dict] = {}

    def _get_bands(self, fingerprint: int) -> List[int]:
        """Split fingerprint into bands."""
        bands = []
        mask = (1 << self.rows_per_band) - 1

        for i in range(self.band_count):
            shift = i * self.rows_per_band
            band = (fingerprint >> shift) & mask
            bands.append(band)

        return bands

    def add(self, doc_id: str, content: str,
            metadata: Dict = None) -> DedupResult:
        """
        Add document to index.

        Args:
            doc_id: Document identifier
            content: Document content
            metadata: Optional metadata to store

        Returns:
            DedupResult indicating if duplicate was found
        """
        fingerprint = self.hasher.compute_simhash(content)

        # Check for duplicates first
        result = self.check_duplicate(fingerprint, doc_id)

        if not result.is_duplicate:
            # Add to index
            bands = self._get_bands(fingerprint)
            for band_idx, band_hash in enumerate(bands):
                self.index[band_idx][band_hash].append((doc_id, fingerprint))

            self.fingerprints[doc_id] = fingerprint

            if metadata:
                self.metadata[doc_id] = metadata

        result.content_hash = self.hasher.fingerprint_to_hex(fingerprint)
        return result

    def check_duplicate(self, fingerprint: int,
                        exclude_id: str = None) -> DedupResult:
        """
        Check if fingerprint matches any existing document.

        Uses LSH bands to find candidates, then verifies with Hamming distance.

        Args:
            fingerprint: Fingerprint to check
            exclude_id: Document ID to exclude from matching

        Returns:
            DedupResult
        """
        bands = self._get_bands(fingerprint)
        candidates = set()

        # Gather candidates from matching bands
        for band_idx, band_hash in enumerate(bands):
            for doc_id, fp in self.index[band_idx].get(band_hash, []):
                if doc_id != exclude_id:
                    candidates.add((doc_id, fp))

        # Check candidates for actual duplicates
        best_match = None
        best_distance = self.config.hash_bits + 1

        for doc_id, fp in candidates:
            distance = self.hasher.hamming_distance(fingerprint, fp)
            if distance < best_distance:
                best_distance = distance
                best_match = doc_id

        if best_match and best_distance <= self.config.hamming_threshold:
            return DedupResult(
                content_hash="",
                is_duplicate=True,
                duplicate_of=best_match,
                hamming_distance=best_distance,
                similarity=self.hasher.similarity(fingerprint, self.fingerprints[best_match]),
            )

        return DedupResult(
            content_hash="",
            is_duplicate=False,
            hamming_distance=best_distance if best_match else None,
        )

    def remove(self, doc_id: str) -> bool:
        """Remove document from index."""
        if doc_id not in self.fingerprints:
            return False

        fingerprint = self.fingerprints[doc_id]
        bands = self._get_bands(fingerprint)

        for band_idx, band_hash in enumerate(bands):
            self.index[band_idx][band_hash] = [
                (did, fp) for did, fp in self.index[band_idx][band_hash]
                if did != doc_id
            ]

        del self.fingerprints[doc_id]
        self.metadata.pop(doc_id, None)

        return True

    def get_statistics(self) -> Dict[str, int]:
        """Get index statistics."""
        return {
            "total_documents": len(self.fingerprints),
            "band_count": self.band_count,
            "rows_per_band": self.rows_per_band,
        }


class ArticleDeduplicator:
    """
    High-level deduplication service for articles.

    Handles:
    - Fingerprinting
    - Duplicate detection
    - URL canonicalization
    - Persistence
    """

    def __init__(self, config: SimHashConfig = None,
                 storage_path: Path = None):
        """
        Initialize deduplicator.

        Args:
            config: SimHash configuration
            storage_path: Path to persist index
        """
        self.config = config or SimHashConfig()
        self.index = LSHIndex(self.config)
        self.storage_path = storage_path or Path("data/cache/dedup_index.json")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # URL canonicalization patterns
        self._url_cleaners = [
            (r'\?utm_.*$', ''),           # Remove UTM params
            (r'#.*$', ''),                # Remove anchors
            (r'/amp/?$', '/'),            # Remove AMP suffix
            (r'www\.', ''),               # Remove www
            (r'^https?://', ''),          # Normalize protocol
        ]

        # Load existing index
        self._load_index()

    def _load_index(self) -> None:
        """Load index from disk."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)

            for doc_id, fp_hex in data.get("fingerprints", {}).items():
                fp = self.index.hasher.hex_to_fingerprint(fp_hex)
                self.index.fingerprints[doc_id] = fp

                bands = self.index._get_bands(fp)
                for band_idx, band_hash in enumerate(bands):
                    self.index.index[band_idx][band_hash].append((doc_id, fp))

            self.index.metadata = data.get("metadata", {})

        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load dedup index: {e}")

    def save_index(self) -> None:
        """Persist index to disk."""
        data = {
            "fingerprints": {
                doc_id: self.index.hasher.fingerprint_to_hex(fp)
                for doc_id, fp in self.index.fingerprints.items()
            },
            "metadata": self.index.metadata,
            "saved_at": datetime.now().isoformat(),
        }

        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)

    def canonicalize_url(self, url: str) -> str:
        """
        Canonicalize URL for dedup comparison.

        Removes tracking params, normalizes protocol, etc.
        """
        canonical = url.strip().lower()

        for pattern, replacement in self._url_cleaners:
            canonical = re.sub(pattern, replacement, canonical)

        return canonical

    def check_article(self, content: str, url: str = None,
                      article_id: str = None) -> DedupResult:
        """
        Check if article is a duplicate.

        Args:
            content: Article content
            url: Article URL (for canonicalization)
            article_id: Article identifier

        Returns:
            DedupResult
        """
        # Generate ID from URL if not provided
        if not article_id and url:
            canonical_url = self.canonicalize_url(url)
            article_id = hashlib.md5(canonical_url.encode()).hexdigest()[:12]

        # Compute fingerprint
        fingerprint = self.index.hasher.compute_simhash(content)

        # Check for duplicate
        result = self.index.check_duplicate(fingerprint, article_id)
        result.content_hash = self.index.hasher.fingerprint_to_hex(fingerprint)

        return result

    def add_article(self, content: str, url: str = None,
                    article_id: str = None,
                    metadata: Dict = None) -> DedupResult:
        """
        Add article to index (if not duplicate).

        Args:
            content: Article content
            url: Article URL
            article_id: Article identifier
            metadata: Additional metadata

        Returns:
            DedupResult
        """
        # Generate ID
        if not article_id:
            if url:
                canonical_url = self.canonicalize_url(url)
                article_id = hashlib.md5(canonical_url.encode()).hexdigest()[:12]
            else:
                article_id = hashlib.md5(content[:500].encode()).hexdigest()[:12]

        # Build metadata
        full_metadata = {
            "url": url,
            "canonical_url": self.canonicalize_url(url) if url else None,
            "added_at": datetime.now().isoformat(),
            **(metadata or {}),
        }

        # Add to index
        result = self.index.add(article_id, content, full_metadata)

        return result

    def get_duplicate_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        stats = self.index.get_statistics()
        stats["storage_path"] = str(self.storage_path)
        stats["config"] = {
            "hash_bits": self.config.hash_bits,
            "hamming_threshold": self.config.hamming_threshold,
            "band_count": self.config.band_count,
        }
        return stats

    def cleanup_old_entries(self, max_age_days: int = None) -> int:
        """
        Remove old entries from index.

        Args:
            max_age_days: Maximum age to keep (default: config.cache_ttl_days)

        Returns:
            Number of entries removed
        """
        max_age = max_age_days or self.config.cache_ttl_days
        cutoff = datetime.now() - timedelta(days=max_age)

        to_remove = []
        for doc_id, meta in self.index.metadata.items():
            added_at = meta.get("added_at")
            if added_at:
                added_date = datetime.fromisoformat(added_at)
                if added_date < cutoff:
                    to_remove.append(doc_id)

        for doc_id in to_remove:
            self.index.remove(doc_id)

        return len(to_remove)


# Convenience function
def is_duplicate_content(content: str, deduplicator: ArticleDeduplicator = None) -> bool:
    """
    Quick check if content is a duplicate.

    Args:
        content: Content to check
        deduplicator: Deduplicator instance (creates temporary if not provided)

    Returns:
        True if duplicate detected
    """
    if deduplicator is None:
        deduplicator = ArticleDeduplicator()

    result = deduplicator.check_article(content)
    return result.is_duplicate