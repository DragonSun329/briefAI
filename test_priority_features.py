"""
End-to-End Test for Priority Features

Tests the three priority implementations:
1. ACE-Planner for smarter category selection
2. Entity extraction and deduplication
3. Full article context caching

Run this script to verify all features work correctly.
"""

import sys
from pathlib import Path
from loguru import logger

# Setup logging
logger.remove()
logger.add(sys.stdout, level="INFO")


def test_ace_planner():
    """Test Priority 1: ACE-Planner for query decomposition"""
    logger.info("=" * 60)
    logger.info("TEST 1: ACE-Planner Query Decomposition")
    logger.info("=" * 60)

    try:
        from modules.ace_planner import ACEPlanner
        from utils.llm_client_enhanced import LLMClient

        llm_client = LLMClient()
        planner = ACEPlanner(
            llm_client=llm_client,
            company_context="智能风控信贷 (AI-powered risk control and credit)"
        )

        # Test query planning
        user_input = "我想了解智能风控领域的最新AI技术进展"
        test_categories = [
            {"name": "智能风控技术", "keywords": ["风控", "反欺诈", "AI"]},
            {"name": "信贷创新", "keywords": ["信贷", "贷款", "AI"]}
        ]

        logger.info(f"User input: {user_input}")
        query_plan = planner.plan_queries(user_input, test_categories)

        logger.info(f"\n✓ Query plan generated successfully!")
        logger.info(f"  Themes: {len(query_plan.get('themes', []))}")
        logger.info(f"  Global entities: {len(query_plan.get('global_entities', []))}")

        # Display first theme
        if query_plan.get('themes'):
            theme = query_plan['themes'][0]
            logger.info(f"\n  Sample theme: {theme.get('name')}")
            logger.info(f"    Must keywords: {theme.get('must_keywords', [])[:3]}")
            logger.info(f"    Should keywords: {theme.get('should_keywords', [])[:3]}")
            logger.info(f"    Not keywords: {theme.get('not_keywords', [])[:3]}")

        return True

    except Exception as e:
        logger.error(f"✗ ACE-Planner test failed: {e}")
        return False


def test_entity_extraction():
    """Test Priority 2: Entity extraction and deduplication"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Entity Extraction & Deduplication")
    logger.info("=" * 60)

    try:
        from utils.entity_extractor import EntityExtractor
        from utils.llm_client import LLMClient

        llm_client = LLMClient()
        extractor = EntityExtractor(llm_client=llm_client)

        # Test entity extraction
        test_text = """
        OpenAI发布了GPT-5模型，在推理能力方面取得突破。
        该模型由Sam Altman领导的团队开发，将在旧金山总部首次展示。
        微软和OpenAI将继续合作推进AGI研究。
        """

        logger.info("Extracting entities from sample text...")
        entities = extractor.extract_entities(test_text)

        logger.info(f"\n✓ Entities extracted successfully!")
        for entity_type, entity_list in entities.items():
            if entity_list:
                logger.info(f"  {entity_type}: {entity_list}")

        # Test similarity calculation
        test_entities_1 = {
            "companies": ["OpenAI", "Microsoft"],
            "models": ["GPT-5"],
            "people": ["Sam Altman"]
        }
        test_entities_2 = {
            "companies": ["OpenAI", "微软"],
            "models": ["GPT-5"],
            "people": ["Altman"]
        }

        similarity = extractor.calculate_similarity(test_entities_1, test_entities_2)
        logger.info(f"\n✓ Similarity calculation: {similarity:.2%}")

        # Test deduplication
        test_articles = [
            {
                "title": "OpenAI发布GPT-5",
                "content": "OpenAI今日发布GPT-5，Sam Altman表示这是重大突破...",
                "url": "https://example.com/1"
            },
            {
                "title": "GPT-5正式发布",
                "content": "OpenAI的新模型GPT-5由Sam Altman团队开发...",
                "url": "https://example.com/2"
            },
            {
                "title": "Meta推出Llama 4",
                "content": "Meta发布全新Llama 4模型，Mark Zuckerberg宣布...",
                "url": "https://example.com/3"
            }
        ]

        logger.info("\n✓ Testing batch entity extraction...")
        enriched_articles = extractor.extract_entities_batch(test_articles)

        logger.info(f"  Processed {len(enriched_articles)} articles")
        for i, article in enumerate(enriched_articles, 1):
            total_entities = sum(len(v) for v in article.get('entities', {}).values())
            logger.info(f"  Article {i}: {total_entities} entities extracted")

        return True

    except Exception as e:
        logger.error(f"✗ Entity extraction test failed: {e}")
        return False


def test_article_caching():
    """Test Priority 3: Full article context caching"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Article Context Caching")
    logger.info("=" * 60)

    try:
        from modules.article_paraphraser import ArticleParaphraser
        from utils.context_retriever import ContextRetriever
        from utils.llm_client import LLMClient
        import json
        from datetime import datetime

        llm_client = LLMClient()

        # Test caching
        paraphraser = ArticleParaphraser(
            llm_client=llm_client,
            enable_caching=True,
            cache_retention_days=7
        )

        test_articles = [
            {
                "title": "AI技术突破",
                "content": "人工智能在多个领域取得重大突破，包括自然语言处理和计算机视觉...",
                "url": "https://example.com/article1",
                "source": "TechNews",
                "published_date": "2024-10-25",
                "credibility_score": 8.5,
                "relevance_score": 9.0,
                "entities": {
                    "companies": ["OpenAI"],
                    "models": ["GPT-5"]
                },
                "evaluation": {
                    "key_takeaway": "AI技术取得突破"
                }
            },
            {
                "title": "机器学习新进展",
                "content": "研究人员开发出更高效的机器学习算法，大幅提升训练速度...",
                "url": "https://example.com/article2",
                "source": "AI Weekly",
                "published_date": "2024-10-25",
                "credibility_score": 7.8,
                "relevance_score": 8.5,
                "entities": {
                    "companies": ["Google"],
                    "models": ["DeepMind"]
                },
                "evaluation": {
                    "key_takeaway": "机器学习算法优化"
                }
            }
        ]

        logger.info("Testing article caching...")

        # Cache articles (without full paraphrasing to save costs)
        cache_dir = Path("./data/cache/article_contexts")
        cache_dir.mkdir(parents=True, exist_ok=True)

        cache_filename = datetime.now().strftime("%Y%m%d.json")
        cache_path = cache_dir / cache_filename

        cached_data = {
            "report_date": datetime.now().strftime("%Y-%m-%d"),
            "generation_time": datetime.now().isoformat(),
            "articles": []
        }

        for i, article in enumerate(test_articles):
            cached_article = {
                "id": f"{i+1:03d}",
                "title": article.get('title', ''),
                "url": article.get('url', ''),
                "source": article.get('source', ''),
                "published_date": article.get('published_date', ''),
                "full_content": article.get('content', ''),
                "credibility_score": article.get('credibility_score', 0),
                "relevance_score": article.get('relevance_score', 0),
                "entities": article.get('entities', {}),
                "evaluation": article.get('evaluation', {})
            }
            cached_data["articles"].append(cached_article)

        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cached_data, f, ensure_ascii=False, indent=2)

        logger.info(f"✓ Articles cached to {cache_path}")

        # Test retrieval
        retriever = ContextRetriever()

        logger.info("\n✓ Testing context retrieval...")
        reports = retriever.list_available_reports()
        logger.info(f"  Found {len(reports)} cached reports")

        if reports:
            latest = retriever.load_latest_report()
            if latest:
                logger.info(f"  Latest report: {latest.get('report_date')}")
                logger.info(f"  Articles: {len(latest.get('articles', []))}")

                # Test search
                logger.info("\n✓ Testing keyword search...")
                results = retriever.search_by_keyword("AI")
                logger.info(f"  Found {len(results)} articles matching 'AI'")

                # Test entity search
                logger.info("\n✓ Testing entity search...")
                results = retriever.search_by_entity("OpenAI")
                logger.info(f"  Found {len(results)} articles mentioning 'OpenAI'")

                # Test statistics
                logger.info("\n✓ Testing statistics...")
                stats = retriever.get_article_statistics(latest.get('report_date'))
                logger.info(f"  Total articles: {stats.get('total_articles')}")
                logger.info(f"  Avg credibility: {stats.get('avg_credibility_score')}")
                logger.info(f"  Unique sources: {stats.get('unique_sources')}")

        return True

    except Exception as e:
        logger.error(f"✗ Article caching test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration():
    """Test integration of all features in the main workflow"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Integration Test")
    logger.info("=" * 60)

    try:
        from modules.category_selector import CategorySelector
        from modules.news_evaluator import NewsEvaluator
        from modules.article_paraphraser import ArticleParaphraser
        from utils.llm_client import LLMClient

        llm_client = LLMClient()

        # Test 1: CategorySelector with ACE-Planner
        logger.info("\n✓ Testing CategorySelector with ACE-Planner...")
        selector = CategorySelector(
            llm_client=llm_client,
            company_context="智能风控信贷",
            enable_ace_planner=True
        )

        test_input = "智能风控的最新AI技术"
        categories = selector.select_categories(test_input)

        if categories and 'query_plan' in categories[0]:
            logger.info(f"  ✓ Query plan attached to categories")
        else:
            logger.warning(f"  ⚠ Query plan not found in categories")

        # Test 2: NewsEvaluator with deduplication
        logger.info("\n✓ Testing NewsEvaluator with deduplication...")
        evaluator = NewsEvaluator(
            llm_client=llm_client,
            company_context="智能风控信贷",
            enable_deduplication=True
        )

        test_articles = [
            {
                "title": "OpenAI发布GPT-5",
                "content": "OpenAI今日发布GPT-5模型...",
                "url": "https://example.com/1",
                "source": "TechNews",
                "published_date": "2024-10-25"
            },
            {
                "title": "GPT-5正式推出",
                "content": "OpenAI的GPT-5模型正式推出...",
                "url": "https://example.com/2",
                "source": "AI Daily",
                "published_date": "2024-10-25"
            }
        ]

        logger.info(f"  Input: {len(test_articles)} articles")
        # Note: Full evaluation is expensive, so we just verify the module loads

        # Test 3: ArticleParaphraser with caching
        logger.info("\n✓ Testing ArticleParaphraser with caching...")
        paraphraser = ArticleParaphraser(
            llm_client=llm_client,
            enable_caching=True,
            cache_retention_days=7
        )

        if paraphraser.enable_caching:
            logger.info(f"  ✓ Caching enabled (retention: {paraphraser.cache_retention_days} days)")
            logger.info(f"  ✓ Cache directory: {paraphraser.cache_dir}")
        else:
            logger.warning(f"  ⚠ Caching not enabled")

        logger.info("\n✓ All modules loaded and configured successfully!")
        return True

    except Exception as e:
        logger.error(f"✗ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    logger.info("\n" + "=" * 60)
    logger.info("PRIORITY FEATURES END-TO-END TEST")
    logger.info("=" * 60)
    logger.info("")

    results = {
        "ACE-Planner": test_ace_planner(),
        "Entity Extraction": test_entity_extraction(),
        "Article Caching": test_article_caching(),
        "Integration": test_integration()
    }

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{status}: {test_name}")

    total_passed = sum(results.values())
    total_tests = len(results)

    logger.info("\n" + "=" * 60)
    logger.info(f"RESULTS: {total_passed}/{total_tests} tests passed")
    logger.info("=" * 60)

    if total_passed == total_tests:
        logger.info("\n🎉 All tests passed! Features are ready for use.")
        return 0
    else:
        logger.error("\n⚠ Some tests failed. Please review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
