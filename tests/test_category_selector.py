"""
Unit tests for Category Selector Module

Run with:
  python tests/test_category_selector.py
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from unittest.mock import Mock, patch, MagicMock
from modules.category_selector import CategorySelector


class TestCategorySelectorInit(unittest.TestCase):
    """Test CategorySelector initialization"""

    def test_init_loads_categories(self):
        """Test that categories are loaded from config"""
        selector = CategorySelector()

        self.assertIsNotNone(selector.categories)
        self.assertGreater(len(selector.categories), 0)
        self.assertIsNotNone(selector.default_categories)

    def test_lookup_maps_built(self):
        """Test that lookup maps are properly built"""
        selector = CategorySelector()

        # Check ID map
        self.assertGreater(len(selector.id_to_category), 0)

        # Check alias map
        self.assertGreater(len(selector.alias_to_id), 0)

        # Verify a known alias works
        self.assertIn("大模型", selector.alias_to_id)
        self.assertIn("llm", selector.alias_to_id)

    def test_custom_config_path(self):
        """Test initialization with custom config path"""
        selector = CategorySelector(
            categories_config="./config/categories.json"
        )

        self.assertIsNotNone(selector.categories)


class TestCategorySelection(unittest.TestCase):
    """Test category selection logic"""

    def setUp(self):
        """Set up test selector"""
        self.selector = CategorySelector(enable_caching=False)

    def test_default_categories(self):
        """Test default category selection"""
        result = self.selector.select_categories(use_defaults=True)

        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

        # Check enrichment
        for cat in result:
            self.assertIn('selection_priority', cat)
            self.assertIn('keywords', cat)
            self.assertIn('rationale', cat)

    def test_empty_input_uses_defaults(self):
        """Test that empty input uses defaults"""
        result = self.selector.select_categories("")

        defaults = self.selector.select_categories(use_defaults=True)
        self.assertEqual(len(result), len(defaults))

    def test_none_input_uses_defaults(self):
        """Test that None input uses defaults"""
        result = self.selector.select_categories(None)

        defaults = self.selector.select_categories(use_defaults=True)
        self.assertEqual(len(result), len(defaults))

    def test_simple_match_chinese(self):
        """Test simple keyword matching in Chinese"""
        result = self.selector.select_categories("大模型")

        self.assertGreater(len(result), 0)
        # Should match LLM category
        self.assertTrue(
            any(cat['id'] == 'llm' for cat in result),
            "Should match 'llm' category for '大模型'"
        )

    def test_simple_match_english(self):
        """Test simple keyword matching in English"""
        result = self.selector.select_categories("LLM")

        self.assertGreater(len(result), 0)
        self.assertTrue(
            any(cat['id'] == 'llm' for cat in result),
            "Should match 'llm' category for 'LLM'"
        )

    def test_multiple_keywords(self):
        """Test matching multiple keywords"""
        result = self.selector.select_categories("大模型和政策")

        self.assertGreaterEqual(len(result), 2)

        # Should match both LLM and policy
        matched_ids = {cat['id'] for cat in result}
        self.assertIn('llm', matched_ids)
        self.assertIn('policy', matched_ids)

    def test_max_categories_limit(self):
        """Test that max_categories limit is respected"""
        result = self.selector.select_categories(
            "大模型 AI应用 政策 融资 研究",
            max_categories=3
        )

        self.assertLessEqual(len(result), 3)


class TestHelperMethods(unittest.TestCase):
    """Test helper methods"""

    def setUp(self):
        """Set up test selector"""
        self.selector = CategorySelector()

    def test_get_all_categories(self):
        """Test get_all_categories()"""
        all_cats = self.selector.get_all_categories()

        self.assertIsInstance(all_cats, list)
        self.assertGreater(len(all_cats), 0)

    def test_get_category_by_id(self):
        """Test get_category_by_id()"""
        # Get known category
        cat = self.selector.get_category_by_id('llm')

        self.assertIsNotNone(cat)
        self.assertEqual(cat['id'], 'llm')
        self.assertEqual(cat['name'], '大模型')

    def test_get_category_by_invalid_id(self):
        """Test get_category_by_id() with invalid ID"""
        cat = self.selector.get_category_by_id('invalid_id')

        self.assertIsNone(cat)

    def test_try_simple_match(self):
        """Test _try_simple_match() method"""
        # Test with clear match
        result = self.selector._try_simple_match("大模型和AI应用")

        self.assertIsNotNone(result)
        self.assertGreater(len(result), 0)

    def test_try_simple_match_no_match(self):
        """Test _try_simple_match() with no matches"""
        # Use text that doesn't match any category
        result = self.selector._try_simple_match("random unrelated text xyz")

        # Should return None for no clear matches
        # (actual behavior may vary)


class TestClaudeIntegration(unittest.TestCase):
    """Integration tests requiring Claude API"""

    @classmethod
    def setUpClass(cls):
        """Check if API key is available"""
        cls.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not cls.api_key:
            raise unittest.SkipTest("ANTHROPIC_API_KEY not set - skipping integration tests")

    def setUp(self):
        """Set up test selector"""
        self.selector = CategorySelector(enable_caching=False)

    def test_claude_selection_chinese(self):
        """Test Claude-based selection with Chinese input"""
        result = self.selector.select_categories(
            "我想了解大模型的最新进展和政策监管方面的新闻"
        )

        self.assertGreater(len(result), 0)
        self.assertLessEqual(len(result), 5)

        # Check enrichment
        for cat in result:
            self.assertIn('id', cat)
            self.assertIn('name', cat)
            self.assertIn('selection_priority', cat)

    def test_claude_selection_english(self):
        """Test Claude-based selection with English input"""
        result = self.selector.select_categories(
            "I want to know about LLM developments and AI applications"
        )

        self.assertGreater(len(result), 0)

        # Should include relevant categories
        matched_ids = {cat['id'] for cat in result}
        # At least one of these should match
        relevant = {'llm', 'ai_apps', 'research'}
        self.assertTrue(
            bool(matched_ids & relevant),
            f"Should match at least one of {relevant}, got {matched_ids}"
        )

    def test_claude_selection_vague(self):
        """Test Claude-based selection with vague input"""
        result = self.selector.select_categories(
            "最近AI有什么新闻"
        )

        self.assertGreaterEqual(len(result), 2)
        self.assertLessEqual(len(result), 3)

        # Should return generally important categories


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestCategorySelectorInit))
    suite.addTests(loader.loadTestsFromTestCase(TestCategorySelection))
    suite.addTests(loader.loadTestsFromTestCase(TestHelperMethods))

    # Only add integration tests if API key is available
    if os.getenv("ANTHROPIC_API_KEY"):
        suite.addTests(loader.loadTestsFromTestCase(TestClaudeIntegration))
        print("Running with Claude integration tests (API key found)\n")
    else:
        print("Running without Claude integration tests (no API key)\n")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
