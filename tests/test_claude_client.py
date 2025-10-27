"""
Unit tests for Claude Client

Run these tests after setting up the environment with:
  export ANTHROPIC_API_KEY=your_key_here
  python tests/test_claude_client.py
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from unittest.mock import Mock, patch
from utils.claude_client import ClaudeClient
from utils.cache_manager import CacheManager


class TestClaudeClientInit(unittest.TestCase):
    """Test ClaudeClient initialization"""

    def test_init_with_api_key(self):
        """Test initialization with explicit API key"""
        client = ClaudeClient(api_key="test-key")
        self.assertEqual(client.api_key, "test-key")
        self.assertEqual(client.model, "claude-sonnet-4-5-20250429")
        self.assertEqual(client.max_tokens, 4096)
        self.assertEqual(client.temperature, 0.3)

    def test_init_without_api_key_raises(self):
        """Test initialization without API key raises error"""
        # Temporarily remove env var
        old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with self.assertRaises(ValueError):
                ClaudeClient()
        finally:
            if old_key:
                os.environ["ANTHROPIC_API_KEY"] = old_key

    def test_custom_parameters(self):
        """Test initialization with custom parameters"""
        client = ClaudeClient(
            api_key="test-key",
            model="claude-3-opus-20240229",
            max_tokens=2000,
            temperature=0.7
        )
        self.assertEqual(client.model, "claude-3-opus-20240229")
        self.assertEqual(client.max_tokens, 2000)
        self.assertEqual(client.temperature, 0.7)

    def test_stats_initialized(self):
        """Test that stats are properly initialized"""
        client = ClaudeClient(api_key="test-key")
        self.assertEqual(client.stats["total_calls"], 0)
        self.assertEqual(client.stats["cache_hits"], 0)
        self.assertEqual(client.stats["total_cost"], 0.0)


class TestClaudeClientMethods(unittest.TestCase):
    """Test ClaudeClient methods (mocked)"""

    def setUp(self):
        """Set up test client with mocked API"""
        self.client = ClaudeClient(api_key="test-key", enable_caching=False)

    def test_cache_key_generation(self):
        """Test cache key generation is consistent"""
        key1 = self.client._generate_cache_key("system", "user", temp=0.5)
        key2 = self.client._generate_cache_key("system", "user", temp=0.5)
        key3 = self.client._generate_cache_key("system", "user2", temp=0.5)

        self.assertEqual(key1, key2)  # Same inputs = same key
        self.assertNotEqual(key1, key3)  # Different inputs = different key

    def test_stats_update(self):
        """Test statistics updating"""
        usage = {"input_tokens": 100, "output_tokens": 50}
        self.client._update_stats(usage)

        self.assertEqual(self.client.stats["total_input_tokens"], 100)
        self.assertEqual(self.client.stats["total_output_tokens"], 50)
        self.assertGreater(self.client.stats["total_cost"], 0)

    def test_get_stats(self):
        """Test statistics retrieval"""
        stats = self.client.get_stats()

        self.assertIn("total_calls", stats)
        self.assertIn("cache_hit_rate", stats)
        self.assertIn("total_cost", stats)
        self.assertIn("average_cost_per_call", stats)

    def test_reset_stats(self):
        """Test statistics reset"""
        # Simulate some usage
        self.client.stats["total_calls"] = 10
        self.client.stats["total_cost"] = 1.5

        # Reset
        self.client.reset_stats()

        self.assertEqual(self.client.stats["total_calls"], 0)
        self.assertEqual(self.client.stats["total_cost"], 0.0)


class TestClaudeClientIntegration(unittest.TestCase):
    """Integration tests requiring real API key"""

    @classmethod
    def setUpClass(cls):
        """Check if API key is available"""
        cls.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not cls.api_key:
            raise unittest.SkipTest("ANTHROPIC_API_KEY not set - skipping integration tests")

    def setUp(self):
        """Set up test client"""
        self.client = ClaudeClient(enable_caching=False)

    def test_basic_chat(self):
        """Test basic chat functionality"""
        response = self.client.chat(
            system_prompt="You are a helpful assistant. Be very brief.",
            user_message="Say 'test' in one word"
        )

        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 0)
        self.assertEqual(self.client.stats["total_calls"], 1)

    def test_chat_structured(self):
        """Test structured JSON response"""
        response = self.client.chat_structured(
            system_prompt="Return JSON only.",
            user_message='Return {"status": "ok", "number": 42}'
        )

        self.assertIsInstance(response, dict)
        self.assertIn("status", response)

    def test_batch_processing(self):
        """Test batch request processing"""
        requests = [
            {
                "system_prompt": "You are brief.",
                "user_message": "Say 'one'"
            },
            {
                "system_prompt": "You are brief.",
                "user_message": "Say 'two'"
            }
        ]

        responses = self.client.batch_chat(requests, delay_between_calls=0.5)

        self.assertEqual(len(responses), 2)
        self.assertIsNotNone(responses[0])
        self.assertIsNotNone(responses[1])

    def test_caching(self):
        """Test response caching"""
        cache = CacheManager()
        client = ClaudeClient(enable_caching=True, cache_manager=cache)

        # First call (cache miss)
        resp1 = client.chat(
            system_prompt="Be brief.",
            user_message="Say exactly: 'cache test'"
        )

        # Second call (cache hit)
        resp2 = client.chat(
            system_prompt="Be brief.",
            user_message="Say exactly: 'cache test'"
        )

        self.assertEqual(resp1, resp2)
        self.assertEqual(client.stats["cache_hits"], 1)
        self.assertEqual(client.stats["cache_misses"], 1)


def run_tests():
    """Run all tests"""
    # Run tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestClaudeClientInit))
    suite.addTests(loader.loadTestsFromTestCase(TestClaudeClientMethods))

    # Only add integration tests if API key is available
    if os.getenv("ANTHROPIC_API_KEY"):
        suite.addTests(loader.loadTestsFromTestCase(TestClaudeClientIntegration))
        print("Running with integration tests (API key found)\n")
    else:
        print("Running without integration tests (no API key)\n")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
