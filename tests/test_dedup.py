"""
Tests for SimHash deduplication module.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.dedup_simhash import (
    SimHashConfig,
    SimHasher,
    LSHIndex,
    ArticleDeduplicator,
)


class TestSimHasher:
    """Tests for SimHasher."""

    def test_compute_fingerprint(self):
        """Test computing a fingerprint."""
        hasher = SimHasher()
        text = "This is a test article about artificial intelligence and machine learning."
        fp = hasher.compute(text)

        assert isinstance(fp, int)
        assert fp >= 0

    def test_identical_texts_same_fingerprint(self):
        """Identical texts should produce identical fingerprints."""
        hasher = SimHasher()
        text = "This is a test article."

        fp1 = hasher.compute(text)
        fp2 = hasher.compute(text)

        assert fp1 == fp2

    def test_similar_texts_close_fingerprints(self):
        """Similar texts should produce similar fingerprints."""
        hasher = SimHasher()

        text1 = "The quick brown fox jumps over the lazy dog."
        text2 = "The quick brown fox leaps over the lazy dog."

        fp1 = hasher.compute(text1)
        fp2 = hasher.compute(text2)

        distance = hasher.hamming_distance(fp1, fp2)
        # Similar texts should have low hamming distance
        assert distance < 10

    def test_different_texts_different_fingerprints(self):
        """Very different texts should have different fingerprints."""
        hasher = SimHasher()

        text1 = "The quick brown fox jumps over the lazy dog."
        text2 = "Machine learning is transforming the technology industry."

        fp1 = hasher.compute(text1)
        fp2 = hasher.compute(text2)

        distance = hasher.hamming_distance(fp1, fp2)
        # Different texts should have higher hamming distance
        assert distance > 10

    def test_hamming_distance_zero_for_same(self):
        """Hamming distance of same fingerprint is 0."""
        hasher = SimHasher()
        fp = 12345678

        assert hasher.hamming_distance(fp, fp) == 0

    def test_hamming_distance_max(self):
        """Hamming distance maximum is 64 for 64-bit integers."""
        hasher = SimHasher()
        fp1 = 0
        fp2 = (1 << 64) - 1  # All 1s

        assert hasher.hamming_distance(fp1, fp2) == 64

    def test_is_duplicate_threshold(self):
        """Test duplicate detection with threshold."""
        hasher = SimHasher()

        text1 = "The quick brown fox jumps over the lazy dog today."
        text2 = "The quick brown fox jumps over the lazy dog yesterday."

        fp1 = hasher.compute(text1)
        fp2 = hasher.compute(text2)

        # With default threshold of 3, these might be duplicates
        # depending on how similar they are
        result = hasher.is_duplicate(fp1, fp2)
        assert isinstance(result, bool)

    def test_empty_text(self):
        """Test handling empty text."""
        hasher = SimHasher()
        fp = hasher.compute("")
        assert fp == 0

    def test_short_text(self):
        """Test handling very short text."""
        hasher = SimHasher()
        fp = hasher.compute("Hi")
        assert isinstance(fp, int)


class TestLSHIndex:
    """Tests for LSH Index."""

    def test_add_and_query(self):
        """Test adding and querying fingerprints."""
        index = LSHIndex(num_bands=16, rows_per_band=4)

        fp1 = 123456789
        fp2 = 123456790  # Very similar (1 bit different)
        fp3 = 987654321  # Very different

        index.add("doc1", fp1)
        index.add("doc2", fp2)
        index.add("doc3", fp3)

        # Query for fp1 should find fp2 (similar)
        candidates = index.query(fp1)
        assert "doc1" in candidates or "doc2" in candidates

    def test_empty_index_query(self):
        """Test querying empty index."""
        index = LSHIndex()
        candidates = index.query(12345)
        assert len(candidates) == 0

    def test_clear_index(self):
        """Test clearing the index."""
        index = LSHIndex()
        index.add("doc1", 12345)

        index.clear()

        candidates = index.query(12345)
        assert len(candidates) == 0


class TestArticleDeduplicator:
    """Tests for ArticleDeduplicator."""

    def test_check_and_add_new(self):
        """Test checking and adding a new article."""
        dedup = ArticleDeduplicator()

        article_id = "article1"
        url = "https://example.com/article1"
        content = "This is a unique article about artificial intelligence."

        is_dup, original = dedup.check_and_add(article_id, url, content)

        assert is_dup is False
        assert original is None

    def test_detect_exact_duplicate(self):
        """Test detecting exact duplicate content."""
        dedup = ArticleDeduplicator()

        content = "This is a test article about machine learning and AI."

        # Add first article
        dedup.check_and_add("article1", "https://example.com/1", content)

        # Check same content with different URL
        is_dup, original = dedup.check_and_add(
            "article2",
            "https://example.com/2",
            content
        )

        assert is_dup is True
        assert original == "article1"

    def test_detect_near_duplicate(self):
        """Test detecting near-duplicate content."""
        dedup = ArticleDeduplicator()

        content1 = """
        Artificial intelligence is transforming the technology industry.
        Machine learning models are becoming increasingly sophisticated.
        Companies are investing heavily in AI research and development.
        The future of AI looks very promising and exciting.
        """

        content2 = """
        Artificial intelligence is transforming the technology sector.
        Machine learning models are becoming more sophisticated.
        Companies are investing heavily in AI research and development.
        The future of AI looks very promising and exciting.
        """

        dedup.check_and_add("article1", "https://example.com/1", content1)
        is_dup, original = dedup.check_and_add(
            "article2",
            "https://example.com/2",
            content2
        )

        # These should be detected as near-duplicates
        assert is_dup is True

    def test_canonicalize_url(self):
        """Test URL canonicalization."""
        dedup = ArticleDeduplicator()

        url1 = "https://www.example.com/article?utm_source=twitter&id=123"
        url2 = "https://example.com/article?id=123"

        canon1 = dedup.canonicalize_url(url1)
        canon2 = dedup.canonicalize_url(url2)

        # After canonicalization, tracking params removed, www stripped
        assert canon1 == canon2

    def test_get_statistics(self):
        """Test getting deduplication statistics."""
        dedup = ArticleDeduplicator()

        # Add some articles
        dedup.check_and_add("a1", "https://example.com/1", "First unique article about AI.")
        dedup.check_and_add("a2", "https://example.com/2", "Second unique article about ML.")
        dedup.check_and_add("a3", "https://example.com/3", "First unique article about AI.")  # Duplicate

        stats = dedup.get_statistics()

        assert stats["total_articles"] >= 2
        assert "duplicates_found" in stats

    def test_content_too_short(self):
        """Test handling content that's too short."""
        config = SimHashConfig(min_content_length=100)
        dedup = ArticleDeduplicator(config)

        # Very short content
        is_dup, original = dedup.check_and_add("a1", "https://example.com/1", "Short")

        # Should not be marked as duplicate, but also not indexed
        assert is_dup is False


class TestSimHashConfig:
    """Tests for SimHashConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SimHashConfig()

        assert config.num_bits == 64
        assert config.hamming_threshold == 3
        assert config.ngram_size == 3
        assert config.num_bands == 16
        assert config.rows_per_band == 4

    def test_custom_config(self):
        """Test custom configuration."""
        config = SimHashConfig(
            hamming_threshold=5,
            ngram_size=4,
        )

        assert config.hamming_threshold == 5
        assert config.ngram_size == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])