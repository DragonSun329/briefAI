"""
Quick Code Structure Validation Test

Tests that all new modules can be imported and have the expected methods.
This test does NOT make LLM API calls, so it's fast and free.
"""

import sys
from pathlib import Path


def test_imports():
    """Test that all modules can be imported"""
    print("=" * 60)
    print("TEST 1: Module Imports")
    print("=" * 60)

    errors = []

    try:
        from modules.ace_planner import ACEPlanner
        print("✓ modules.ace_planner imported successfully")
    except Exception as e:
        errors.append(f"ace_planner: {e}")
        print(f"✗ modules.ace_planner failed: {e}")

    try:
        from utils.entity_extractor import EntityExtractor
        print("✓ utils.entity_extractor imported successfully")
    except Exception as e:
        errors.append(f"entity_extractor: {e}")
        print(f"✗ utils.entity_extractor failed: {e}")

    try:
        from utils.context_retriever import ContextRetriever
        print("✓ utils.context_retriever imported successfully")
    except Exception as e:
        errors.append(f"context_retriever: {e}")
        print(f"✗ utils.context_retriever failed: {e}")

    try:
        from modules.article_paraphraser import ArticleParaphraser
        print("✓ modules.article_paraphraser imported successfully")
    except Exception as e:
        errors.append(f"article_paraphraser: {e}")
        print(f"✗ modules.article_paraphraser failed: {e}")

    try:
        from modules.category_selector import CategorySelector
        print("✓ modules.category_selector imported successfully")
    except Exception as e:
        errors.append(f"category_selector: {e}")
        print(f"✗ modules.category_selector failed: {e}")

    try:
        from modules.news_evaluator import NewsEvaluator
        print("✓ modules.news_evaluator imported successfully")
    except Exception as e:
        errors.append(f"news_evaluator: {e}")
        print(f"✗ modules.news_evaluator failed: {e}")

    return len(errors) == 0, errors


def test_class_methods():
    """Test that classes have expected methods"""
    print("\n" + "=" * 60)
    print("TEST 2: Class Method Validation")
    print("=" * 60)

    errors = []

    try:
        from modules.ace_planner import ACEPlanner
        required_methods = ['plan_queries', '_build_planning_prompt', '_validate_plan']
        for method in required_methods:
            if hasattr(ACEPlanner, method):
                print(f"✓ ACEPlanner.{method} exists")
            else:
                errors.append(f"ACEPlanner.{method} missing")
                print(f"✗ ACEPlanner.{method} missing")
    except Exception as e:
        errors.append(f"ACEPlanner validation: {e}")

    try:
        from utils.entity_extractor import EntityExtractor
        required_methods = ['extract_entities', 'normalize_entity', 'calculate_similarity', 'extract_entities_batch']
        for method in required_methods:
            if hasattr(EntityExtractor, method):
                print(f"✓ EntityExtractor.{method} exists")
            else:
                errors.append(f"EntityExtractor.{method} missing")
                print(f"✗ EntityExtractor.{method} missing")
    except Exception as e:
        errors.append(f"EntityExtractor validation: {e}")

    try:
        from utils.context_retriever import ContextRetriever
        required_methods = [
            'list_available_reports',
            'load_report_by_date',
            'load_latest_report',
            'get_article_by_id',
            'search_by_keyword',
            'search_by_entity',
            'get_article_statistics'
        ]
        for method in required_methods:
            if hasattr(ContextRetriever, method):
                print(f"✓ ContextRetriever.{method} exists")
            else:
                errors.append(f"ContextRetriever.{method} missing")
                print(f"✗ ContextRetriever.{method} missing")
    except Exception as e:
        errors.append(f"ContextRetriever validation: {e}")

    try:
        from modules.article_paraphraser import ArticleParaphraser
        required_methods = ['paraphrase_articles', '_cache_articles', '_cleanup_old_caches']
        for method in required_methods:
            if hasattr(ArticleParaphraser, method):
                print(f"✓ ArticleParaphraser.{method} exists")
            else:
                errors.append(f"ArticleParaphraser.{method} missing")
                print(f"✗ ArticleParaphraser.{method} missing")
    except Exception as e:
        errors.append(f"ArticleParaphraser validation: {e}")

    return len(errors) == 0, errors


def test_feature_flags():
    """Test that new feature flags work"""
    print("\n" + "=" * 60)
    print("TEST 3: Feature Flag Validation")
    print("=" * 60)

    errors = []

    try:
        from modules.category_selector import CategorySelector
        # Test that enable_ace_planner parameter exists
        import inspect
        sig = inspect.signature(CategorySelector.__init__)
        if 'enable_ace_planner' in sig.parameters:
            print("✓ CategorySelector has enable_ace_planner parameter")
        else:
            errors.append("CategorySelector missing enable_ace_planner parameter")
            print("✗ CategorySelector missing enable_ace_planner parameter")
    except Exception as e:
        errors.append(f"CategorySelector flag check: {e}")

    try:
        from modules.news_evaluator import NewsEvaluator
        import inspect
        sig = inspect.signature(NewsEvaluator.__init__)
        if 'enable_deduplication' in sig.parameters:
            print("✓ NewsEvaluator has enable_deduplication parameter")
        else:
            errors.append("NewsEvaluator missing enable_deduplication parameter")
            print("✗ NewsEvaluator missing enable_deduplication parameter")
    except Exception as e:
        errors.append(f"NewsEvaluator flag check: {e}")

    try:
        from modules.article_paraphraser import ArticleParaphraser
        import inspect
        sig = inspect.signature(ArticleParaphraser.__init__)
        if 'enable_caching' in sig.parameters and 'cache_retention_days' in sig.parameters:
            print("✓ ArticleParaphraser has enable_caching and cache_retention_days parameters")
        else:
            errors.append("ArticleParaphraser missing caching parameters")
            print("✗ ArticleParaphraser missing caching parameters")
    except Exception as e:
        errors.append(f"ArticleParaphraser flag check: {e}")

    return len(errors) == 0, errors


def test_context_retriever_basic():
    """Test ContextRetriever basic functionality without LLM"""
    print("\n" + "=" * 60)
    print("TEST 4: ContextRetriever Basic Functions")
    print("=" * 60)

    errors = []

    try:
        from utils.context_retriever import ContextRetriever

        # Test initialization
        retriever = ContextRetriever()
        print("✓ ContextRetriever initialized successfully")

        # Test list_available_reports (should return empty list if no caches)
        reports = retriever.list_available_reports()
        print(f"✓ list_available_reports() returned {len(reports)} reports")

        # If there are reports, test loading
        if reports:
            latest = retriever.load_latest_report()
            if latest:
                print(f"✓ load_latest_report() succeeded")
                stats = retriever.get_article_statistics(latest.get('report_date'))
                print(f"✓ get_article_statistics() succeeded")
            else:
                print("⚠ load_latest_report() returned None")
        else:
            print("ℹ No cached reports to test")

    except Exception as e:
        errors.append(f"ContextRetriever test: {e}")
        print(f"✗ ContextRetriever test failed: {e}")

    return len(errors) == 0, errors


def main():
    """Run all validation tests"""
    print("\n" + "=" * 60)
    print("CODE STRUCTURE VALIDATION TEST")
    print("Testing Priority Features Implementation")
    print("=" * 60)
    print()

    results = {}

    # Test 1: Imports
    passed, errors = test_imports()
    results['Imports'] = passed
    if errors:
        print(f"\nImport errors: {errors}")

    # Test 2: Class methods
    passed, errors = test_class_methods()
    results['Class Methods'] = passed
    if errors:
        print(f"\nMethod errors: {errors}")

    # Test 3: Feature flags
    passed, errors = test_feature_flags()
    results['Feature Flags'] = passed
    if errors:
        print(f"\nFeature flag errors: {errors}")

    # Test 4: Basic functionality
    passed, errors = test_context_retriever_basic()
    results['Context Retriever'] = passed
    if errors:
        print(f"\nContext retriever errors: {errors}")

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    total_passed = sum(results.values())
    total_tests = len(results)

    print("\n" + "=" * 60)
    print(f"RESULTS: {total_passed}/{total_tests} tests passed")
    print("=" * 60)

    if total_passed == total_tests:
        print("\n✅ All structure validation tests passed!")
        print("The code is properly structured and ready for runtime testing.")
        return 0
    else:
        print("\n⚠ Some validation tests failed.")
        print("Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
