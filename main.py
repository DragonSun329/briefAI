#!/usr/bin/env python3
"""
AI Industry Weekly Briefing Agent - Main Orchestrator

Coordinates all modules to generate weekly AI industry briefings.
Run: python main.py --interactive
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.llm_client_enhanced import LLMClient
from utils.cache_manager import CacheManager
from utils.checkpoint_manager import CheckpointManager
from utils.article_filter import ArticleFilter
from utils.logger import setup_logger
from utils.weekly_utils import WeeklyUtils
from utils.scoring_engine import ScoringEngine
from utils.report_archiver import ReportArchiver
from modules.category_selector import CategorySelector
from modules.web_scraper import WebScraper
from modules.batch_evaluator import BatchEvaluator
from modules.news_evaluator import NewsEvaluator
from modules.article_paraphraser import ArticleParaphraser
from modules.report_formatter import ReportFormatter
from modules.collection_mode import CollectionMode
from modules.finalization_mode import FinalizationMode

# Load environment variables
load_dotenv()


class BriefingAgent:
    """Main orchestrator for the AI briefing workflow"""

    def __init__(self):
        """Initialize all components"""
        logger.info("Initializing AI Briefing Agent...")

        # Initialize shared resources
        self.llm_client = LLMClient()
        self.cache_manager = CacheManager()
        self.checkpoint_manager = CheckpointManager()

        # Initialize modules
        self.category_selector = CategorySelector(llm_client=self.llm_client)
        self.web_scraper = WebScraper(cache_manager=self.cache_manager)

        # Tier 1: Pre-filter
        tier1_threshold = float(os.getenv('TIER1_SCORE_THRESHOLD', '3.0'))
        self.article_filter = ArticleFilter(score_threshold=tier1_threshold)

        # Tier 2: Batch evaluate (increased batch size from 10 to 15 for 15% speed improvement)
        tier2_batch_size = int(os.getenv('TIER2_BATCH_SIZE', '15'))
        tier2_pass_score = float(os.getenv('TIER2_PASS_SCORE', '6.0'))
        self.batch_evaluator = BatchEvaluator(
            llm_client=self.llm_client,
            batch_size=tier2_batch_size,
            pass_score=tier2_pass_score
        )

        # Tier 3: Full evaluation
        self.news_evaluator = NewsEvaluator(llm_client=self.llm_client)
        self.article_paraphraser = ArticleParaphraser(llm_client=self.llm_client)
        self.report_formatter = ReportFormatter(llm_client=self.llm_client)

        # Weekly collection modes
        self.collection_mode = CollectionMode(
            llm_client=self.llm_client,
            checkpoint_manager=self.checkpoint_manager
        )
        self.finalization_mode = FinalizationMode(
            llm_client=self.llm_client,
            news_evaluator=self.news_evaluator,
            checkpoint_manager=self.checkpoint_manager,
            collection_mode=self.collection_mode
        )

        logger.info("All modules initialized successfully")

    def run(
        self,
        user_input: str = None,
        use_defaults: bool = False,
        days_back: int = 7,
        top_n: int = 10,
        use_cache: bool = True,
        resume: bool = False,
        batch_id: str = None
    ) -> str:
        """
        Run the full briefing workflow

        Args:
            user_input: User's category preferences (e.g., "我想了解大模型和AI应用")
            use_defaults: Use default categories
            days_back: Number of days to look back for articles
            top_n: Number of articles to include in report (default: 10 = top 7 by score + top 3 by novelty)
            use_cache: Use cached data when available
            resume: Resume from last checkpoint
            batch_id: Specific batch ID to resume (auto-detected if not provided)

        Returns:
            Path to generated report
        """
        logger.info("=" * 60)
        logger.info("Starting AI Weekly Briefing Generation")
        if resume:
            logger.info("MODE: RESUME FROM CHECKPOINT")
        logger.info("=" * 60)

        try:
            # Step 1: Select Categories
            logger.info("\n[1/5] Selecting categories...")
            categories = self.category_selector.select_categories(
                user_input=user_input,
                use_defaults=use_defaults
            )
            selected_names = [cat['name'] for cat in categories]
            logger.info(f"Selected categories: {', '.join(selected_names)}")

            # Step 2: Scrape Articles
            logger.info("\n[2/5] Scraping articles...")
            category_ids = [cat['id'] for cat in categories]

            # Extract query plan if available (from ACE-Planner)
            query_plan = categories[0].get('query_plan') if categories else None

            articles = self.web_scraper.scrape_all(
                categories=category_ids,
                days_back=days_back,
                use_cache=use_cache,
                query_plan=query_plan
            )
            logger.info(f"Scraped {len(articles)} articles")

            if not articles:
                logger.error("No articles found! Check your sources configuration.")
                return None

            # Step 3a: Tier 1 Pre-filter (fast, 0 tokens) with caching for same-day reruns
            logger.info("\n[3a/5] TIER 1: Pre-filtering articles...")

            # Try to load cached Tier 1 results (for same-day reruns)
            from datetime import datetime as dt
            today = dt.now().strftime("%Y-%m-%d")
            category_ids_str = "_".join(sorted([cat['id'] for cat in categories]))
            tier1_cache_key = f"tier1_filter_{today}_{category_ids_str}"

            cached_tier1 = self.cache_manager.get(tier1_cache_key, max_age_hours=24)
            if cached_tier1:
                logger.info(f"Using cached Tier 1 results ({len(cached_tier1)} articles)")
                tier1_articles = cached_tier1
            else:
                tier1_articles = self.article_filter.filter_articles(
                    articles=articles,
                    categories=categories
                )
                # Cache the Tier 1 results for potential same-day reruns
                if tier1_articles:
                    self.cache_manager.set(tier1_cache_key, tier1_articles)

            if not tier1_articles:
                logger.error("No articles passed Tier 1 pre-filter!")
                return None

            # Step 3b: Tier 2 Batch evaluation (lightweight LLM)
            logger.info("\n[3b/5] TIER 2: Batch evaluating articles...")
            tier2_articles = self.batch_evaluator.evaluate_batch(
                articles=tier1_articles,
                categories=categories
            )

            if not tier2_articles:
                logger.warning("No articles passed Tier 2 batch eval, using top from Tier 1")
                tier2_articles = tier1_articles[:top_n]

            # Step 3c: Tier 3 Full evaluation (detailed analysis)
            logger.info("\n[3c/5] TIER 3: Full article evaluation...")
            evaluated_articles = self.news_evaluator.evaluate_articles(
                articles=tier2_articles,
                categories=categories,
                top_n=top_n
            )
            logger.info(f"Selected top {len(evaluated_articles)} articles after full evaluation")

            if not evaluated_articles:
                logger.error("No articles passed Tier 3 full evaluation!")
                return None

            # Step 4: Paraphrase Articles
            logger.info("\n[4/5] Paraphrasing articles...")
            paraphrased_articles = self.article_paraphraser.paraphrase_articles(
                articles=evaluated_articles
            )
            logger.info("Paraphrasing complete")

            # Step 5: Generate Report
            logger.info("\n[5/5] Generating final report...")
            report_path = self.report_formatter.generate_report(
                articles=paraphrased_articles,
                categories=categories
            )

            logger.info("=" * 60)
            logger.info(f"✅ Report generated successfully!")
            logger.info(f"📄 Location: {report_path}")
            logger.info("=" * 60)

            # Print cost statistics
            logger.info("\n💰 LLM API Usage Statistics:")
            self.llm_client.print_stats()

            return report_path

        except Exception as e:
            logger.error(f"❌ Error generating report: {e}")
            raise

    def run_collection_mode(
        self,
        user_input: str = None,
        use_defaults: bool = False,
        days_back: int = 7,
        week_id: str = None,
        day: int = None
    ) -> Dict[str, Any]:
        """
        Run in collection mode (Days 1-6): Fast Tier 1 + Tier 2 without expensive Tier 3

        Args:
            user_input: User's category preferences
            use_defaults: Use default categories
            days_back: Number of days to look back
            week_id: Week ID for checkpoint (auto-detected if None)
            day: Day number (auto-detected if None)

        Returns:
            Collection results dictionary
        """
        logger.info("=" * 60)
        logger.info("Starting Daily Article Collection")
        logger.info("MODE: COLLECTION (Tier 1 + Tier 2 only, no Tier 3)")
        logger.info("=" * 60)

        try:
            # Auto-detect week ID and day if not provided
            if week_id is None:
                week_id = WeeklyUtils.get_current_week_id()
            if day is None:
                day = WeeklyUtils.get_current_day_of_week()

            logger.info(f"Week ID: {week_id} | Day: {WeeklyUtils.get_day_name(day)} ({day})")

            # Step 1: Select Categories
            logger.info("\n[1/3] Selecting categories...")
            categories = self.category_selector.select_categories(
                user_input=user_input,
                use_defaults=use_defaults
            )
            selected_names = [cat['name'] for cat in categories]
            logger.info(f"Selected categories: {', '.join(selected_names)}")

            # Step 2: Scrape Articles
            logger.info("\n[2/3] Scraping articles...")
            category_ids = [cat['id'] for cat in categories]
            articles = self.web_scraper.scrape_all(
                categories=category_ids,
                days_back=days_back,
                use_cache=True
            )
            logger.info(f"Scraped {len(articles)} articles")

            if not articles:
                logger.error("No articles found!")
                return {'error': 'No articles scraped'}

            # Step 3: Run Collection Mode (Tier 1 + Tier 2)
            logger.info("\n[3/3] Running Tier 1 + Tier 2 collection...")
            result = self.collection_mode.collect_articles(
                articles=articles,
                categories=categories,
                week_id=week_id,
                day=day
            )

            logger.info("\n" + "=" * 60)
            logger.info(f"✅ Daily collection complete!")
            logger.info(f"📊 Articles collected: {result['tier2_passed']}")
            logger.info(f"💾 Saved to: {result['checkpoint_stats']['checkpoint_file']}")
            logger.info("=" * 60)

            # Print API stats
            logger.info("\n💰 LLM API Usage Statistics:")
            self.llm_client.print_stats()

            return result

        except Exception as e:
            logger.error(f"❌ Error in collection mode: {e}")
            raise

    def run_finalization_mode(
        self,
        week_id: str = None,
        user_input: str = None,
        use_defaults: bool = False,
        top_n: int = 15
    ) -> Dict[str, Any]:
        """
        Run in finalization mode (Day 7): Deduplicate + re-rank + Tier 3 evaluation

        Args:
            week_id: Week ID to finalize (auto-detected if None)
            user_input: User's category preferences (for Tier 3)
            use_defaults: Use default categories
            top_n: Number of articles in final report

        Returns:
            Finalization results dictionary
        """
        logger.info("=" * 60)
        logger.info("Starting Weekly Finalization")
        logger.info("MODE: FINALIZATION (Dedup + Re-rank + Tier 3)")
        logger.info("=" * 60)

        try:
            # Auto-detect week ID if not provided
            if week_id is None:
                week_id = WeeklyUtils.get_current_week_id()

            logger.info(f"Finalizing week: {week_id}")
            week_range = WeeklyUtils.format_week_range(week_id)
            logger.info(f"Week date range: {week_range}")

            # Step 1: Select Categories (for Tier 3 evaluation)
            logger.info("\n[1/2] Selecting categories...")
            categories = self.category_selector.select_categories(
                user_input=user_input,
                use_defaults=use_defaults
            )
            selected_names = [cat['name'] for cat in categories]
            logger.info(f"Selected categories: {', '.join(selected_names)}")

            # Step 2: Finalize Weekly Articles
            logger.info("\n[2/2] Running finalization (dedup + tier 3)...")
            result = self.finalization_mode.finalize_weekly_articles(
                week_id=week_id,
                categories=categories,
                top_n=top_n
            )

            if 'error' in result:
                logger.error(f"Finalization failed: {result['error']}")
                return result

            final_articles = result.get('final_articles', [])

            # Step 3: Paraphrase final articles
            logger.info(f"\n[3/3] Paraphrasing {len(final_articles)} final articles...")
            paraphrased_articles = self.article_paraphraser.paraphrase_articles(
                articles=final_articles
            )
            logger.info("Paraphrasing complete")

            # Step 4: Generate Report
            logger.info("\nGenerating final report...")
            report_path = self.report_formatter.generate_report(
                articles=paraphrased_articles,
                categories=categories
            )

            logger.info("\n" + "=" * 60)
            logger.info(f"✅ Weekly report generated successfully!")
            logger.info(f"📄 Location: {report_path}")
            logger.info(f"📊 Final articles: {len(final_articles)}")
            logger.info("=" * 60)

            # Print API stats
            logger.info("\n💰 LLM API Usage Statistics:")
            self.llm_client.print_stats()

            result['report_path'] = report_path
            result['paraphrased_articles'] = paraphrased_articles

            return result

        except Exception as e:
            logger.error(f"❌ Error in finalization mode: {e}")
            raise

    def run_early_report_mode(
        self,
        week_id: str = None,
        user_input: str = None,
        use_defaults: bool = False,
        top_n: int = 15,
        enable_backfill: bool = True
    ) -> Dict[str, Any]:
        """
        Run in early report mode (Friday): Auto-backfill missing days + finalize

        Args:
            week_id: Week ID to finalize (auto-detected if None)
            user_input: User's category preferences
            use_defaults: Use default categories
            top_n: Number of articles in final report
            enable_backfill: Whether to auto-collect missing days

        Returns:
            Early report results dictionary
        """
        logger.info("=" * 60)
        logger.info("Starting EARLY Report Mode (Friday with Auto-Backfill)")
        logger.info("MODE: EARLY FINALIZATION (backfills missing days, then finalizes)")
        logger.info("=" * 60)

        try:
            # Auto-detect week ID if not provided
            if week_id is None:
                week_id = WeeklyUtils.get_current_week_id()

            logger.info(f"Week ID: {week_id}")

            # Step 1: Select Categories (for Tier 3 and backfill collection)
            logger.info("\n[1/2] Selecting categories...")
            categories = self.category_selector.select_categories(
                user_input=user_input,
                use_defaults=use_defaults
            )
            selected_names = [cat['name'] for cat in categories]
            logger.info(f"Selected categories: {', '.join(selected_names)}")

            # Step 2: Run early finalization with backfill
            logger.info("\n[2/2] Running early finalization (backfill + dedup + Tier 3)...")
            result = self.finalization_mode.finalize_early_report(
                week_id=week_id,
                categories=categories,
                top_n=top_n,
                enable_backfill=enable_backfill,
                min_articles_per_day=5
            )

            if 'error' in result:
                logger.error(f"Early finalization failed: {result['error']}")
                return result

            final_articles = result.get('final_articles', [])

            # Step 3: Paraphrase final articles
            logger.info(f"\n[3/3] Paraphrasing {len(final_articles)} final articles...")
            paraphrased_articles = self.article_paraphraser.paraphrase_articles(
                articles=final_articles
            )
            logger.info("Paraphrasing complete")

            # Step 4: Generate Report
            logger.info("\nGenerating final early report...")
            report_path = self.report_formatter.generate_report(
                articles=paraphrased_articles,
                categories=categories
            )

            logger.info("\n" + "=" * 60)
            logger.info(f"✅ Early report generated successfully!")
            logger.info(f"📄 Location: {report_path}")
            logger.info(f"📊 Final articles: {len(final_articles)}")
            logger.info(f"📊 Backfilled days: {len(result.get('backfilled_days', []))}")
            logger.info("=" * 60)

            # Print API stats
            logger.info("\n💰 LLM API Usage Statistics:")
            self.llm_client.print_stats()

            result['report_path'] = report_path
            result['paraphrased_articles'] = paraphrased_articles

            return result

        except Exception as e:
            logger.error(f"❌ Error in early report mode: {e}")
            raise

    def generate_daily_report(
        self,
        user_input: str = None,
        use_defaults: bool = False,
        top_n: int = 15
    ) -> Dict[str, Any]:
        """
        Generate daily report from previous day's articles

        Args:
            user_input: User's category preferences
            use_defaults: Use default categories
            top_n: Number of articles in daily report

        Returns:
            Daily report generation results
        """
        logger.info("=" * 60)
        logger.info("Generating Daily Report")
        logger.info("=" * 60)

        try:
            # Get yesterday's date for checkpoint loading
            from datetime import timedelta
            yesterday = datetime.now() - timedelta(days=1)

            # Auto-detect week ID
            week_id = WeeklyUtils.get_current_week_id()
            logger.info(f"Loading articles from week: {week_id}")

            # Step 1: Select Categories
            logger.info("\n[1/3] Selecting categories...")
            categories = self.category_selector.select_categories(
                user_input=user_input,
                use_defaults=use_defaults
            )
            selected_names = [cat['name'] for cat in categories]
            logger.info(f"Selected categories: {', '.join(selected_names)}")

            # Step 2: Load weekly checkpoint and get yesterday's articles
            logger.info(f"\n[2/3] Loading yesterday's articles from checkpoint...")
            if not self.checkpoint_manager.load_weekly_checkpoint(week_id):
                logger.error(f"No checkpoint found for {week_id}")
                return {'error': f'No checkpoint found for {week_id}'}

            all_articles = self.checkpoint_manager.processed_articles
            logger.info(f"Loaded {len(all_articles)} total articles from week {week_id}")

            # Filter to yesterday's articles only
            yesterday_str = yesterday.strftime('%Y-%m-%d')
            yesterday_articles = [
                a for a in all_articles
                if a.get('published_date', '').startswith(yesterday_str)
            ]
            logger.info(f"Found {len(yesterday_articles)} articles from {yesterday_str}")

            if not yesterday_articles:
                logger.warning(f"No articles found for {yesterday_str}")
                return {'error': f'No articles found for {yesterday_str}'}

            # Step 3: Tier 3 Evaluation - Apply 5D scoring
            logger.info(f"\n[3/3] Running Tier 3 evaluation (5D scoring)...")
            evaluated_articles = self.news_evaluator.evaluate_articles(
                articles=yesterday_articles,
                categories=categories,
                top_n=top_n
            )
            logger.info(f"Evaluated {len(evaluated_articles)} articles with 5D scoring")

            # Step 4: Generate Daily Report with 5D scores
            logger.info("\nGenerating daily report with 5D scores...")
            report_formatter = ReportFormatter(include_5d_scores=True)
            report_path = report_formatter.generate_report(
                articles=evaluated_articles,
                categories=categories,
                report_type="daily"
            )

            logger.info("\n" + "=" * 60)
            logger.info(f"✅ Daily report generated successfully!")
            logger.info(f"📄 Location: {report_path}")
            logger.info(f"📊 Articles: {len(evaluated_articles)}")
            logger.info(f"📅 Date: {yesterday_str}")
            logger.info("=" * 60)

            # Print API stats
            logger.info("\n💰 LLM API Usage Statistics:")
            self.llm_client.print_stats()

            return {
                'report_path': report_path,
                'article_count': len(evaluated_articles),
                'report_date': yesterday_str
            }

        except Exception as e:
            logger.error(f"❌ Error generating daily report: {e}")
            return {'error': str(e)}

    def generate_weekly_report(
        self,
        week_id: str = None,
        user_input: str = None,
        use_defaults: bool = False,
        top_n: int = 15
    ) -> Dict[str, Any]:
        """
        Generate weekly report from 7 days of articles with 5D scoring

        Args:
            week_id: Week ID to finalize (auto-detected if None)
            user_input: User's category preferences
            use_defaults: Use default categories
            top_n: Number of articles in weekly report

        Returns:
            Weekly report generation results
        """
        logger.info("=" * 60)
        logger.info("Generating Weekly Report")
        logger.info("=" * 60)

        try:
            # Auto-detect week ID if not provided
            if week_id is None:
                week_id = WeeklyUtils.get_current_week_id()

            logger.info(f"Finalizing week: {week_id}")
            week_range = WeeklyUtils.format_week_range(week_id)
            logger.info(f"Week date range: {week_range}")

            # Step 1: Select Categories
            logger.info("\n[1/3] Selecting categories...")
            categories = self.category_selector.select_categories(
                user_input=user_input,
                use_defaults=use_defaults
            )
            selected_names = [cat['name'] for cat in categories]
            logger.info(f"Selected categories: {', '.join(selected_names)}")

            # Step 2: Load weekly checkpoint and run Tier 3 evaluation
            logger.info(f"\n[2/3] Loading weekly checkpoint and evaluating articles...")
            if not self.checkpoint_manager.load_weekly_checkpoint(week_id):
                logger.error(f"No checkpoint found for {week_id}")
                return {'error': f'No checkpoint found for {week_id}'}

            articles = self.checkpoint_manager.processed_articles
            logger.info(f"Loaded {len(articles)} articles from week {week_id}")

            # Run full 5D evaluation on all articles
            evaluated_articles = self.news_evaluator.evaluate_articles(
                articles=articles,
                categories=categories,
                top_n=top_n
            )
            logger.info(f"Evaluated {len(evaluated_articles)} articles with 5D scoring")

            # Step 3: Generate Weekly Report with 5D scores and insights
            logger.info("\n[3/3] Generating weekly report with insights...")
            report_formatter = ReportFormatter(include_5d_scores=True)
            report_path = report_formatter.generate_report(
                articles=evaluated_articles,
                categories=categories,
                report_type="weekly",
                week_id=week_id
            )

            logger.info(f"Weekly report generated: {report_path}")

            # Step 4: Archive previous week's daily reports
            logger.info("\nArchiving previous week's daily reports...")
            from datetime import timedelta
            previous_week_num = int(week_id.split('_')[2]) - 1
            if previous_week_num > 0:
                previous_week_id = f"week_{week_id.split('_')[1]}_{previous_week_num:02d}"
                archiver = ReportArchiver()
                archive_result = archiver.archive_week_daily_reports(previous_week_id)
                logger.info(f"Archived {archive_result['archived_count']} daily reports")

            logger.info("\n" + "=" * 60)
            logger.info(f"✅ Weekly report generated successfully!")
            logger.info(f"📄 Location: {report_path}")
            logger.info(f"📊 Articles: {len(evaluated_articles)}")
            logger.info(f"📅 Week: {week_range}")
            logger.info("=" * 60)

            # Print API stats
            logger.info("\n💰 LLM API Usage Statistics:")
            self.llm_client.print_stats()

            return {
                'report_path': report_path,
                'article_count': len(evaluated_articles),
                'week_id': week_id,
                'week_range': week_range
            }

        except Exception as e:
            logger.error(f"❌ Error generating weekly report: {e}")
            return {'error': str(e)}


def interactive_mode():
    """Run in interactive mode, prompting user for preferences"""
    print("\n" + "=" * 60)
    print("AI Industry Weekly Briefing Agent")
    print("=" * 60)

    # Load available categories
    categories_file = Path("./config/categories.json")
    try:
        with open(categories_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            available_categories = config.get('categories', [])
            default_categories = config.get('default_categories', [])
    except Exception as e:
        logger.error(f"Failed to load categories: {e}")
        available_categories = []
        default_categories = []

    # Ask for category selection
    print("\n请选择您想关注的AI领域:")
    print("\n可选分类:")
    for i, cat in enumerate(available_categories, 1):
        print(f"  {i}. {cat['name']}")
    print(f"  {len(available_categories) + 1}. 使用默认分类 ({', '.join([c['name'] for c in available_categories if c['id'] in default_categories])})")
    print(f"  {len(available_categories) + 2}. 自定义输入")

    print("\n请输入选项编号，多个选项用逗号分隔 (例如: 1,2,3)")
    print("或直接按Enter使用默认分类")

    selection = input("\n> ").strip()

    # Parse selection
    user_input = None
    use_defaults = False

    if not selection:
        # Empty input = use defaults
        use_defaults = True
    else:
        try:
            # Parse comma-separated numbers
            choices = [int(x.strip()) for x in selection.split(',')]

            # Check if "use defaults" was selected
            if len(available_categories) + 1 in choices:
                use_defaults = True
            # Check if "custom input" was selected
            elif len(available_categories) + 2 in choices:
                print("\n请输入您想关注的领域 (自然语言):")
                print("(例如: 我想了解智能风控和数据分析)")
                user_input = input("\n> ").strip()
            else:
                # Build natural language input from selected categories
                selected_names = []
                for choice in choices:
                    if 1 <= choice <= len(available_categories):
                        selected_names.append(available_categories[choice - 1]['name'])

                if selected_names:
                    user_input = "我想了解" + "、".join(selected_names)
                else:
                    print("\n⚠️  无效选择，使用默认分类")
                    use_defaults = True

        except ValueError:
            print("\n⚠️  输入格式错误，使用默认分类")
            use_defaults = True

    # Ask for time range
    print("\n查看过去几天的新闻？(默认: 7天)")
    days_input = input("> ").strip()
    days_back = int(days_input) if days_input.isdigit() else 7

    # Ask for number of articles
    print("\n报告中包含多少篇文章？(默认: 15篇)")
    articles_input = input("> ").strip()
    top_n = int(articles_input) if articles_input.isdigit() else 15

    print("\n开始生成报告...\n")

    # Run the agent
    agent = BriefingAgent()
    report_path = agent.run(
        user_input=user_input,
        use_defaults=use_defaults,
        days_back=days_back,
        top_n=top_n
    )

    if report_path:
        print(f"\n✅ 报告已生成: {report_path}")
        print(f"\n您可以用任何Markdown阅读器打开查看")
    else:
        print("\n❌ 报告生成失败，请检查日志")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="AI Industry Weekly Briefing Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (recommended for first use)
  python main.py --interactive

  # Standard full workflow (all 3 tiers)
  python main.py --defaults

  # Specify categories
  python main.py --input "我想了解金融科技AI和数据分析"

  # Custom time range and article count
  python main.py --defaults --days 3 --top 10

  # Weekly Collection Mode (Days 1-6)
  python main.py --defaults --collect

  # Weekly Collection with specific day
  python main.py --defaults --collect --day 3

  # Weekly Finalization Mode (Day 7)
  python main.py --defaults --finalize

  # Finalize specific week
  python main.py --defaults --finalize --week week_2025_43

  # Early Report (Friday with auto-backfill of missing days)
  python main.py --defaults --finalize --early

  # Early Report without backfill (use only collected articles)
  python main.py --defaults --finalize --early --no-backfill

  # Disable cache (force fresh scraping)
  python main.py --defaults --no-cache
        """
    )

    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Run in interactive mode'
    )

    parser.add_argument(
        '--input',
        type=str,
        help='Category preferences in natural language'
    )

    parser.add_argument(
        '--defaults', '-d',
        action='store_true',
        help='Use default categories'
    )

    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days to look back (default: 7)'
    )

    parser.add_argument(
        '--top',
        type=int,
        default=15,
        help='Number of articles in report (default: 15)'
    )

    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Disable cache, force fresh scraping'
    )

    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level (default: INFO)'
    )

    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume from last checkpoint (continue processing where it stopped)'
    )

    parser.add_argument(
        '--batch-id',
        type=str,
        help='Specific batch ID to resume (auto-detected if not provided)'
    )

    parser.add_argument(
        '--collect',
        action='store_true',
        help='Run in collection mode (Days 1-6): Fast Tier 1+2 collection without Tier 3'
    )

    parser.add_argument(
        '--finalize',
        action='store_true',
        help='Run in finalization mode (Day 7): Deduplicate, re-rank, and Tier 3 evaluation'
    )

    parser.add_argument(
        '--week',
        type=str,
        help='Week ID for collection/finalization (auto-detected if not provided)'
    )

    parser.add_argument(
        '--day',
        type=int,
        help='Day number for collection (auto-detected if not provided)'
    )

    parser.add_argument(
        '--early',
        action='store_true',
        help='Generate early report (Friday) with automatic backfill of missing days'
    )

    parser.add_argument(
        '--no-backfill',
        action='store_true',
        help='Disable automatic backfilling of missing collection days (only use collected articles)'
    )

    parser.add_argument(
        '--weekly',
        action='store_true',
        help='Generate weekly report (7-day combined) instead of daily report'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logger(log_level=args.log_level)

    # Check API key
    if not os.getenv('MOONSHOT_API_KEY'):
        logger.error("MOONSHOT_API_KEY not found in environment!")
        logger.error("Please set it in .env file or environment variables")
        sys.exit(1)

    # Run in appropriate mode
    agent = BriefingAgent()

    if args.interactive:
        interactive_mode()
    elif args.collect:
        # Collection mode (Days 1-6)
        if not args.defaults and not args.input:
            logger.error("Please specify --input or --defaults for collection mode")
            sys.exit(1)

        result = agent.run_collection_mode(
            user_input=args.input,
            use_defaults=args.defaults,
            days_back=args.days,
            week_id=args.week if hasattr(args, 'week') else None,
            day=args.day if hasattr(args, 'day') else None
        )

        if 'error' in result:
            logger.error(f"Collection failed: {result['error']}")
            sys.exit(1)

    elif args.finalize:
        # Finalization mode: Daily, Weekly, or Early Report
        if not args.defaults and not args.input:
            logger.error("Please specify --input or --defaults for finalization mode")
            sys.exit(1)

        # Determine which finalization type to run
        is_weekly = args.weekly if hasattr(args, 'weekly') else False
        is_early = args.early if hasattr(args, 'early') else False

        if is_weekly:
            # Weekly report mode: Combine 7 days with 5D scoring + insights + archive
            logger.info("Running weekly report generation with 5D scoring...")
            result = agent.generate_weekly_report(
                week_id=args.week if hasattr(args, 'week') else None,
                user_input=args.input,
                use_defaults=args.defaults,
                top_n=args.top
            )
        elif is_early:
            # Early report mode with auto-backfill (legacy)
            enable_backfill = not (args.no_backfill if hasattr(args, 'no_backfill') else False)

            result = agent.run_early_report_mode(
                week_id=args.week if hasattr(args, 'week') else None,
                user_input=args.input,
                use_defaults=args.defaults,
                top_n=args.top,
                enable_backfill=enable_backfill
            )
        else:
            # Daily report mode: Yesterday's articles with 5D scoring
            logger.info("Running daily report generation with 5D scoring...")
            result = agent.generate_daily_report(
                user_input=args.input,
                use_defaults=args.defaults,
                top_n=args.top
            )

        if 'error' in result:
            logger.error(f"Finalization failed: {result['error']}")
            sys.exit(1)

    else:
        # Default mode: Full workflow (all 3 tiers)
        if not args.defaults and not args.input:
            logger.error("Please specify --input or --defaults (or use --interactive)")
            parser.print_help()
            sys.exit(1)

        report_path = agent.run(
            user_input=args.input,
            use_defaults=args.defaults,
            days_back=args.days,
            top_n=args.top,
            use_cache=not args.no_cache,
            resume=args.resume,
            batch_id=args.batch_id if hasattr(args, 'batch_id') else None
        )

        if not report_path:
            sys.exit(1)


if __name__ == "__main__":
    main()
