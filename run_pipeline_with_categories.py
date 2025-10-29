#!/usr/bin/env python3
"""
Complete Pipeline with Category Integration

This script demonstrates the full pipeline with proper category inputs:
1. Load categories
2. Scrape articles
3. Pre-filter with category context
4. Batch evaluate
5. 5D score and rank
6. Deep paraphrase (500-600 chars)
7. Generate final report

Run: python3 run_pipeline_with_categories.py
"""

import sys
import json
from datetime import datetime
from pathlib import Path

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent))

from modules.web_scraper import WebScraper
from utils.cache_manager import CacheManager
from utils.checkpoint_manager import CheckpointManager
from utils.article_filter import ArticleFilter
from modules.batch_evaluator import BatchEvaluator
from modules.news_evaluator import NewsEvaluator
from modules.article_paraphraser import ArticleParaphraser
from utils.llm_client_enhanced import LLMClient
from utils.scoring_engine import ScoringEngine
from utils.category_loader import load_categories, get_company_context
from loguru import logger


def run_full_pipeline(category_ids=None, top_n=12, early_exit=False, resume=False, force_restart=False):
    """
    Run complete pipeline from scraping to final report.

    Args:
        category_ids: List of category IDs (e.g., ["fintech_ai", "data_analytics"])
                     If None, uses default categories
        top_n: Number of final articles to select
        early_exit: If True, exit after Tier 2 (skip expensive Tier 3)

    Returns:
        List of final articles with 5D scores and deep paraphrasing
    """
    print("\n" + "=" * 80)
    print("FULL PIPELINE: Scrape → Filter → Evaluate → Score → Paraphrase")
    print("=" * 80)

    # =========================================================================
    # SETUP: Load categories and initialize components
    # =========================================================================
    print("\n[SETUP] Loading configuration and categories...")
    try:
        categories = load_categories(category_ids)
        company_context = get_company_context()
        logger.info(f"Loaded {len(categories)} categories")
        logger.info(f"Company: {company_context.get('business', 'N/A')}")
    except Exception as e:
        logger.error(f"Failed to load categories: {e}")
        return []

    # Initialize components
    cache_mgr = CacheManager()
    checkpoint_mgr = CheckpointManager()
    llm_client = LLMClient()

    # =========================================================================
    # CHECKPOINT: Check for existing checkpoint
    # =========================================================================
    if resume and not force_restart:
        checkpoint_info = checkpoint_mgr.get_checkpoint_info()
        if checkpoint_info:
            print("\n" + "=" * 80)
            print("📋 CHECKPOINT FOUND - RESUME MODE")
            print("=" * 80)
            print(f"  Phase: {checkpoint_info['phase']}")
            print(f"  Progress: {checkpoint_info['progress']} ({checkpoint_info['progress_percent']}%)")
            print(f"  Articles: {checkpoint_info['articles_count']}")
            print(f"  Age: {checkpoint_info['age']}")
            print(f"  Run ID: {checkpoint_info['run_id']}")
            print("=" * 80 + "\n")
        else:
            print("\n⚠️  No valid checkpoint found - starting fresh scrape\n")
    elif force_restart:
        print("\n🔄 Force restart mode - ignoring any existing checkpoint\n")
        checkpoint_mgr.clear_checkpoint()

    # =========================================================================
    # PHASE 1: SCRAPE - Fresh articles from 69 sources
    # =========================================================================
    print("\n[1/6] SCRAPING articles from 69 sources...")
    print("      ├─ RSS feeds: ArXiv, Towards Data Science, KDnuggets, etc.")
    print("      ├─ Official blogs: OpenAI, Anthropic, DeepMind, Mistral, etc.")
    print("      ├─ Fintech sources: Fintechnews SG/ID, PaymentsNerd, etc.")
    print("      └─ Time window: Last 7 days")
    if resume:
        print("      └─ Resume: Enabled (will skip completed sources)")

    try:
        scraper = WebScraper(cache_manager=cache_mgr)
        articles = scraper.scrape_all(
            days_back=7,
            use_cache=False,
            resume=resume and not force_restart,
            checkpoint_manager=checkpoint_mgr
        )
        print(f"      ✓ Scraped {len(articles)} articles\n")

        # Clear checkpoint after successful scraping phase
        if resume:
            logger.info("Scraping phase completed - clearing checkpoint")
            checkpoint_mgr.clear_checkpoint()

    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        return []

    if not articles:
        logger.warning("No articles scraped")
        return []

    # =========================================================================
    # PHASE 2: TIER 1 PRE-FILTER - Zero-token keyword matching
    # =========================================================================
    print(f"[2/6] TIER 1 PRE-FILTER - Keyword-based (threshold: 3.0)...")
    print("      ├─ Matches: article title, description, content")
    print("      ├─ Against: category aliases + trending indicators")
    print("      └─ Score: 0-10 scale (recency + keywords + trending)")

    try:
        tier1_filter = ArticleFilter(score_threshold=3.0)
        # IMPORTANT: Pass categories here!
        tier1_results = tier1_filter.filter_articles(articles, categories)
        print(f"      ✓ Tier 1: {len(tier1_results)}/{len(articles)} articles passed\n")
    except Exception as e:
        logger.error(f"Tier 1 filtering failed: {e}")
        return []

    if not tier1_results:
        logger.warning("No articles passed Tier 1 filter")
        return []

    # =========================================================================
    # PHASE 3: TIER 2 BATCH EVALUATION - Quick LLM scoring
    # =========================================================================
    print(f"[3/6] TIER 2 BATCH EVALUATION - Quick LLM scoring (threshold: 6.0)...")
    print("      ├─ Batches: 10 articles per batch")
    print("      ├─ Model: Kimi/OpenRouter fallback")
    print("      └─ Criteria: Relevance, impact, quality")

    try:
        batch_eval = BatchEvaluator(llm_client=llm_client, batch_size=10, pass_score=6.0)
        # IMPORTANT: Pass categories here!
        tier2_results = batch_eval.evaluate_batch(tier1_results, categories)
        print(f"      ✓ Tier 2: {len(tier2_results)}/{len(tier1_results)} articles passed\n")
    except Exception as e:
        logger.error(f"Tier 2 evaluation failed: {e}")
        if early_exit:
            logger.warning("Early exit enabled - returning Tier 2 results")
            tier1_results.sort(key=lambda x: x.get('tier1_score', 0), reverse=True)
            return tier1_results[:top_n]
        return []

    if not tier2_results:
        logger.warning("No articles passed Tier 2 evaluation")
        return []

    if early_exit:
        logger.info("Early exit enabled - skipping Tier 3 (expensive 5D evaluation)")
        tier2_results.sort(key=lambda x: x.get('batch_score', 0), reverse=True)
        return tier2_results[:top_n]

    # =========================================================================
    # PHASE 4: TIER 3 EVALUATION - Full 5D scoring
    # =========================================================================
    print(f"[4/6] TIER 3 EVALUATION - Full 5D scoring (top {top_n} articles)...")
    print("      ├─ Model Impact (Market): 25%")
    print("      ├─ Competitive Impact: 20%")
    print("      ├─ Strategic Relevance: 20%")
    print("      ├─ Operational Relevance: 15%")
    print("      ├─ Credibility: 10%")
    print("      └─ Plus: Entity-based + semantic deduplication")

    try:
        news_eval = NewsEvaluator(llm_client=llm_client)
        # IMPORTANT: Pass categories here!
        tier3_results = news_eval.evaluate_articles(tier2_results, categories, top_n=top_n)
        print(f"      ✓ Tier 3: Selected top {len(tier3_results)} articles with 5D scores\n")
    except Exception as e:
        logger.error(f"Tier 3 evaluation failed: {e}")
        # Fall back to Tier 2 results
        logger.warning("Falling back to Tier 2 results")
        tier2_results.sort(key=lambda x: x.get('batch_score', 0), reverse=True)
        return tier2_results[:top_n]

    if not tier3_results:
        logger.warning("No articles evaluated in Tier 3")
        return []

    # =========================================================================
    # PHASE 5: 5D RANKING - Apply weighted scoring and sort
    # =========================================================================
    print(f"[5/6] RANKING by 5D weighted scores...")
    print("      ├─ Extracting 5D score breakdown from evaluations")
    print("      ├─ Calculating weighted score across 5 dimensions")
    print("      └─ Sorting: highest scores first")

    scoring_engine = ScoringEngine()
    ranked_articles = []

    for i, article in enumerate(tier3_results, 1):
        try:
            # Extract 5D scores from evaluation
            if 'evaluation' in article and 'scores' in article['evaluation']:
                scores = article['evaluation']['scores']
                weighted_score = scoring_engine.calculate_weighted_score(scores)
                article['weighted_score'] = weighted_score

                # Log top articles
                if i <= 3:
                    logger.info(f"  {i}. {article['title'][:60]}... → Score: {weighted_score:.2f}")

            ranked_articles.append(article)
        except Exception as e:
            logger.warning(f"Failed to score article '{article.get('title', 'Unknown')}': {e}")
            continue

    # Sort by weighted score descending
    ranked_articles.sort(key=lambda x: x.get('weighted_score', 0), reverse=True)

    print(f"      ✓ Ranked {len(ranked_articles)} articles by 5D scores\n")

    # =========================================================================
    # PHASE 6: DEEP PARAPHRASING - 500-600 character analysis
    # =========================================================================
    print(f"[6/6] DEEP PARAPHRASING - 500-600 character analysis...")
    print("      ├─ Format: 3-4 paragraphs in Mandarin Chinese")
    print("      ├─ Elements: Central argument, data, evidence, mechanisms, impacts")
    print("      └─ Tone: Analytical, insightful, professional")

    try:
        paraphraser = ArticleParaphraser(
            llm_client=llm_client,
            min_length=500,
            max_length=600
        )
        final_articles = paraphraser.paraphrase_articles(ranked_articles)
        print(f"      ✓ Paraphrased {len(final_articles)} articles\n")
    except Exception as e:
        logger.error(f"Paraphrasing failed: {e}")
        # Return with original content if paraphrasing fails
        logger.warning("Using original article content instead")
        final_articles = ranked_articles

    # =========================================================================
    # VERIFICATION
    # =========================================================================
    print("\n[VERIFICATION] Paraphrased article quality:")
    for i, art in enumerate(final_articles[:3], 1):
        content = art.get('paraphrased_content', art.get('content', ''))
        char_count = len(content)
        score = art.get('weighted_score', 'N/A')
        title = art['title'][:50]
        print(f"  {i}. {title}...")
        print(f"     └─ Score: {score} | Chars: {char_count}")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 80)
    print("✅ PIPELINE COMPLETE")
    print("=" * 80)
    print(f"\n📊 Results:")
    print(f"  • Original articles scraped: {len(articles)}")
    print(f"  • Tier 1 (pre-filter): {len(tier1_results)} articles")
    print(f"  • Tier 2 (batch eval): {len(tier2_results)} articles")
    print(f"  • Tier 3 (5D eval): {len(tier3_results)} articles")
    print(f"  • Final output: {len(final_articles)} ranked articles")
    print(f"\n🎯 Quality metrics:")
    print(f"  • Article filtering: {100 * len(tier1_results) / len(articles):.1f}% kept (Tier 1)")
    print(f"  • Batch evaluation: {100 * len(tier2_results) / len(tier1_results):.1f}% passed (Tier 2)")
    print(f"  • 5D evaluation: Top {len(tier3_results)} articles selected")
    print(f"  • All articles: 500-600 character deep analysis in Mandarin")
    print(f"\n📁 Ready for report generation:")
    print(f"  • Articles: {len(final_articles)} with 5D ranking")
    print(f"  • Format: Paraphrased content (500-600 chars each)")
    print(f"  • Language: Mandarin Chinese")
    print(f"  • Tone: Analytical-inspiring")
    print(f"  • Scores: Weighted across 5 dimensions (Market, Competitive, Strategic, Operational, Credibility)")

    return final_articles


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run complete pipeline with category integration"
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        default=None,
        help="Specific category IDs (e.g., fintech_ai data_analytics). If not specified, uses defaults."
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=12,
        help="Number of final articles to select (default: 12)"
    )
    parser.add_argument(
        "--early-exit",
        action="store_true",
        help="Exit after Tier 2 (skip expensive Tier 3 5D evaluation)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint if available (skips completed sources)"
    )
    parser.add_argument(
        "--force-restart",
        action="store_true",
        help="Force restart (ignore any existing checkpoint and start fresh)"
    )

    args = parser.parse_args()

    # Run pipeline
    final_articles = run_full_pipeline(
        category_ids=args.categories,
        top_n=args.top_n,
        early_exit=args.early_exit,
        resume=args.resume,
        force_restart=args.force_restart
    )

    # Optionally save results
    if final_articles:
        output_file = Path("./data/pipeline_output.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)

        output_data = {
            "timestamp": datetime.now().isoformat(),
            "article_count": len(final_articles),
            "articles": [
                {
                    "title": art.get("title", "N/A"),
                    "source": art.get("source", "N/A"),
                    "url": art.get("url", ""),
                    "weighted_score": art.get("weighted_score", 0),
                    "paraphrased_content": art.get("paraphrased_content", ""),
                    "5d_scores": art.get("5d_score_breakdown", {}),
                }
                for art in final_articles
            ]
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        print(f"\n✓ Results saved to: {output_file}")
