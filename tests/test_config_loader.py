"""Tests for unified config loader."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from utils.config_loader import (
    load_ticker_buckets,
    load_token_buckets,
    load_macro_series,
    reload_configs
)


class TestConfigLoader(unittest.TestCase):
    """Test config loading functions."""

    def test_load_ticker_buckets_returns_dict(self):
        """Test that ticker buckets are loaded."""
        result = load_ticker_buckets()
        self.assertIsInstance(result, dict)
        self.assertIn("ai-chips", result)
        self.assertIn("NVDA", result["ai-chips"])

    def test_load_token_buckets_returns_dict(self):
        """Test that token buckets are loaded."""
        result = load_token_buckets()
        self.assertIsInstance(result, dict)
        self.assertIn("FET", result)
        self.assertEqual(result["FET"]["primary"], "agent-orchestration")

    def test_load_macro_series_returns_dict(self):
        """Test that macro series are loaded."""
        result = load_macro_series()
        self.assertIsInstance(result, dict)
        self.assertIn("FRED/VIXCLS", result)

    def test_reload_clears_cache(self):
        """Test that reload clears the cache."""
        # Load once to populate cache
        load_ticker_buckets()
        # Reload should not raise
        reload_configs()
        # Load again should work
        result = load_ticker_buckets()
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main()
