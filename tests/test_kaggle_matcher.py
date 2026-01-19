"""Tests for Kaggle Crunchbase matcher."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.kaggle_crunchbase_matcher import normalize_name, KaggleMatcher


class TestNormalizeName:
    """Tests for name normalization."""

    def test_normalize_lowercase(self):
        assert normalize_name("OpenAI") == "openai"

    def test_normalize_removes_inc(self):
        assert normalize_name("OpenAI, Inc.") == "openai"
        assert normalize_name("Stripe Inc") == "stripe"

    def test_normalize_removes_llc(self):
        assert normalize_name("Acme LLC") == "acme"

    def test_normalize_removes_corp(self):
        assert normalize_name("Microsoft Corp.") == "microsoft"

    def test_normalize_removes_ltd(self):
        assert normalize_name("Company Ltd") == "company"

    def test_normalize_removes_pbc(self):
        assert normalize_name("Anthropic PBC") == "anthropic"

    def test_normalize_whitespace(self):
        assert normalize_name("  OpenAI  Inc  ") == "openai"

    def test_normalize_empty(self):
        assert normalize_name("") == ""
        assert normalize_name(None) == ""


class TestKaggleMatcher:
    """Tests for the matcher class."""

    @pytest.fixture
    def matcher(self):
        csv_path = Path(__file__).parent.parent / "data" / "kaggle" / "comp.csv"
        if csv_path.exists():
            return KaggleMatcher(str(csv_path))
        pytest.skip("Kaggle CSV not found")

    def test_exact_match(self, matcher):
        result = matcher.match("Airbnb")
        assert result is not None
        assert "airbnb" in result["name"].lower()

    def test_fuzzy_match(self, matcher):
        result = matcher.match("AirBnB Inc.", threshold=80)
        assert result is not None

    def test_no_match(self, matcher):
        result = matcher.match("XYZ123NonExistentCompany999")
        assert result is None

    def test_get_funding(self, matcher):
        funding = matcher.get_funding("Airbnb")
        assert funding is not None
        assert funding > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
