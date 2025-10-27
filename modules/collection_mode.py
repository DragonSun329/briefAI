"""
Collection Mode Module - Fast daily article collection for weekly briefing

Optimized for daily runs (Monday-Friday) to accumulate articles throughout the week.
Skips expensive Tier 3 full evaluation, saving tokens for finalization day.

Process: Scrape → Tier 1 pre-filter → Tier 2 batch evaluation → Save to weekly checkpoint
Expected token cost: ~500 tokens/day (only Tier 2)
"""

from typing import List, Dict, Any, Optional
from loguru import logger

from utils.llm_client_enhanced import LLMClient
from utils.article_filter import ArticleFilter
from modules.batch_evaluator import BatchEvaluator
from utils.checkpoint_manager import CheckpointManager
from utils.weekly_utils import WeeklyUtils


class CollectionMode:
    """Fast daily article collection for weekly briefing system"""

    def __init__(
        self,
        llm_client: LLMClient = None,
        checkpoint_manager: Optional[CheckpointManager] = None
    ):
        """
        Initialize collection mode

        Args:
            llm_client: LLM client instance
            checkpoint_manager: Checkpoint manager instance
        """
        self.llm_client = llm_client or LLMClient()
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()

        # Initialize Tier 1 and Tier 2
        self.article_filter = ArticleFilter(score_threshold=3.0)
        self.batch_evaluator = BatchEvaluator(
            llm_client=self.llm_client,
            batch_size=10,
            pass_score=6.0,
            enable_checkpoint=False
        )

        logger.info("Collection mode initialized")

    def collect_articles(
        self,
        articles: List[Dict[str, Any]],
        categories: List[Dict[str, Any]],
        week_id: Optional[str] = None,
        day: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Run collection mode: fast Tier 1 + Tier 2 evaluation without Tier 3

        Args:
            articles: Scraped articles to collect
            categories: User's selected categories
            week_id: Week ID for checkpoint (defaults to current week)
            day: Day of week (defaults to today)

        Returns:
            Dictionary with collection results:
            {
                'week_id': str,
                'day': int,
                'scraped': int,
                'tier1_passed': int,
                'tier2_passed': int,
                'collected_articles': List[Dict],
                'collection_batch_id': str
            }
        """
        # Use current week/day if not specified
        if week_id is None:
            week_id = WeeklyUtils.get_current_week_id()
        if day is None:
            day = WeeklyUtils.get_current_day_of_week()

        logger.info(
            f"[COLLECTION MODE] Starting daily collection for {week_id} (Day {day})"
        )
        logger.info(f"[COLLECTION MODE] Processing {len(articles)} scraped articles")

        # Ensure weekly checkpoint exists and is loaded
        if not self.checkpoint_manager.load_weekly_checkpoint(week_id):
            self.checkpoint_manager.create_weekly_checkpoint(week_id)

        # Step 1: Tier 1 Pre-filter (0 tokens)
        logger.info("[COLLECTION] Running Tier 1 pre-filter...")
        tier1_articles = self.article_filter.filter_articles(articles, categories)
        logger.info(
            f"[COLLECTION] Tier 1 results: {len(tier1_articles)}/{len(articles)} articles passed "
            f"(threshold: {self.article_filter.score_threshold})"
        )

        # Step 2: Tier 2 Batch evaluation (lightweight LLM)
        logger.info(f"[COLLECTION] Running Tier 2 batch evaluation ({len(tier1_articles)} articles)...")
        tier2_articles = self.batch_evaluator.evaluate_batch(tier1_articles, categories)
        logger.info(
            f"[COLLECTION] Tier 2 results: {len(tier2_articles)}/{len(tier1_articles)} articles passed"
        )

        # Step 3: Save to weekly checkpoint
        self._save_collected_articles(tier2_articles, day)

        # Log collection status
        WeeklyUtils.log_collection_status(
            week_id,
            day,
            len(articles),
            len(tier2_articles)
        )

        # Get statistics
        stats = self.checkpoint_manager.get_weekly_stats()

        collection_batch_id = WeeklyUtils.get_collection_batch_id(week_id, day)

        return {
            'week_id': week_id,
            'day': day,
            'scraped': len(articles),
            'tier1_passed': len(tier1_articles),
            'tier2_passed': len(tier2_articles),
            'collected_articles': tier2_articles,
            'collection_batch_id': collection_batch_id,
            'checkpoint_stats': stats
        }

    def _save_collected_articles(
        self,
        articles: List[Dict[str, Any]],
        day: int
    ) -> None:
        """
        Save collected articles to weekly checkpoint

        Args:
            articles: Articles that passed Tier 2 evaluation
            day: Day of week
        """
        for article in articles:
            article_id = article.get('id')
            if not article_id:
                continue

            tier1_score = article.get('tier1_score')
            tier2_score = article.get('batch_eval_score', 0)
            tier2_reasoning = article.get('batch_eval_reasoning', '')

            self.checkpoint_manager.save_article_tier2_score(
                article_id=article_id,
                article_data={
                    'title': article.get('title'),
                    'url': article.get('url'),
                    'source': article.get('source'),
                    'content': article.get('content'),
                    'published_at': article.get('published_at'),
                    'description': article.get('description'),
                    'credibility_score': article.get('credibility_score')
                },
                tier2_score=tier2_score,
                tier2_reasoning=tier2_reasoning,
                tier1_score=tier1_score,
                day=day
            )

    def get_collection_summary(self, week_id: str) -> Dict[str, Any]:
        """
        Get summary of articles collected so far in the week

        Args:
            week_id: Week ID to get summary for

        Returns:
            Summary dictionary with collection stats
        """
        if not self.checkpoint_manager.load_weekly_checkpoint(week_id):
            logger.warning(f"No checkpoint found for {week_id}")
            return {}

        stats = self.checkpoint_manager.get_weekly_stats()
        articles = self.checkpoint_manager.processed_articles

        # Group by collection day
        by_day = {}
        for article_id, article_data in articles.items():
            day = article_data.get('collection_day', 0)
            if day not in by_day:
                by_day[day] = []
            by_day[day].append({
                'id': article_id,
                'title': article_data.get('article', {}).get('title'),
                'tier2_score': article_data.get('tier2_score', 0)
            })

        # Sort articles within each day by score
        for day in by_day:
            by_day[day].sort(key=lambda x: x['tier2_score'], reverse=True)

        return {
            'week_id': week_id,
            'total_articles': stats['total_articles'],
            'tier2_evaluated': stats['tier2_evaluated'],
            'by_collection_day': by_day,
            'checkpoint_file': stats['checkpoint_file']
        }

    def log_collection_day_summary(self, week_id: str, day: int) -> None:
        """
        Log summary of articles collected on a specific day

        Args:
            week_id: Week ID
            day: Day number (1-7)
        """
        if not self.checkpoint_manager.load_weekly_checkpoint(week_id):
            return

        day_name = WeeklyUtils.get_day_name(day)
        articles = self.checkpoint_manager.processed_articles

        # Filter articles collected on this day
        day_articles = [
            (article_id, article_data.get('tier2_score', 0))
            for article_id, article_data in articles.items()
            if article_data.get('collection_day') == day
        ]

        if day_articles:
            day_articles.sort(key=lambda x: x[1], reverse=True)
            logger.info(f"\n[COLLECTION SUMMARY] {day_name} (Day {day})")
            logger.info(f"[COLLECTION SUMMARY] {len(day_articles)} articles collected:")
            for article_id, score in day_articles[:5]:  # Show top 5
                article_data = articles[article_id]
                title = article_data.get('article', {}).get('title', 'N/A')[:60]
                logger.info(f"  [{score:.1f}] {title}...")
