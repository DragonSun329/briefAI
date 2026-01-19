"""Tests for Wikidata funding fetcher."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.wikidata_funding_fetcher import WikidataFetcher


class TestWikidataFetcher:
    """Tests for the Wikidata fetcher."""

    @pytest.fixture
    def fetcher(self):
        return WikidataFetcher()

    @pytest.mark.integration
    def test_fetch_major_company(self, fetcher):
        """Test fetching a well-known company."""
        result = fetcher.fetch_company("Microsoft")
        assert result is not None
        assert "companyLabel" in result

    @pytest.mark.integration
    def test_fetch_nonexistent(self, fetcher):
        """Test fetching a company that doesn't exist."""
        result = fetcher.fetch_company("XYZ123NonExistentCompany999ABC")
        # May return None or empty result
        # Just ensure it doesn't crash

    @pytest.mark.integration
    def test_caching(self, fetcher):
        """Test that results are cached."""
        # First fetch
        fetcher.fetch_company("Google")
        # Cache should be populated (even if result is None due to network issues)
        assert "google" in fetcher._cache

        # Second fetch should use cache (no additional network request)
        # We can't assert result is not None since it depends on network
        result = fetcher.fetch_company("Google")
        # Just verify cache is still populated
        assert "google" in fetcher._cache


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
