"""
Finalization Mode Module - Week consolidation and full evaluation

Runs once at end of week (Friday evening or Saturday) to:
1. Load all articles collected during Days 1-6
2. Deduplicate by content and entity similarity
3. Re-rank by combined score (tier2_score + recency + trending)
4. Run expensive Tier 3 full evaluation on top candidates only
5. Select final 10-15 articles for weekly report

Expected token cost: ~15,000 tokens (Tier 3 evaluation of 30 candidates)
Total weekly cost: 3,000 (collection) + 15,000 (finalization) = 18,000 tokens (90% savings!)
"""

from typing import List, Dict, Any, Optional, Tuple
from loguru import logger

from utils.llm_client_enhanced import LLMClient
from modules.news_evaluator import NewsEvaluator
from modules.collection_mode import CollectionMode
from utils.checkpoint_manager import CheckpointManager
from utils.deduplication_utils import DeduplicationUtils
from utils.weekly_utils import WeeklyUtils


class FinalizationMode:
    """Week consolidation and full Tier 3 evaluation"""

    def __init__(
        self,
        llm_client: LLMClient = None,
        news_evaluator: NewsEvaluator = None,
        checkpoint_manager: Optional[CheckpointManager] = None,
        collection_mode: Optional['CollectionMode'] = None
    ):
        """
        Initialize finalization mode

        Args:
            llm_client: LLM client instance
            news_evaluator: News evaluator instance (for Tier 3)
            checkpoint_manager: Checkpoint manager instance
            collection_mode: Collection mode instance (for backfilling)
        """
        self.llm_client = llm_client or LLMClient()
        self.news_evaluator = news_evaluator
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.collection_mode = collection_mode

        logger.info("Finalization mode initialized")

    def finalize_weekly_articles(
        self,
        week_id: Optional[str] = None,
        categories: Optional[List[Dict[str, Any]]] = None,
        top_n: int = 15
    ) -> Dict[str, Any]:
        """
        Finalize weekly article collection: deduplicate, re-rank, and full evaluate

        Args:
            week_id: Week ID to finalize (defaults to current week)
            categories: User's selected categories (for Tier 3 evaluation)
            top_n: Number of articles to return in final report

        Returns:
            Dictionary with finalization results
        """
        if week_id is None:
            week_id = WeeklyUtils.get_current_week_id()

        logger.info(f"[FINALIZATION MODE] Starting week finalization for {week_id}")

        # Step 1: Load weekly checkpoint
        if not self.checkpoint_manager.load_weekly_checkpoint(week_id):
            logger.error(f"[FINALIZATION] No checkpoint found for {week_id}")
            return {'error': f'No checkpoint found for {week_id}'}

        articles = self.checkpoint_manager.processed_articles
        logger.info(
            f"[FINALIZATION] Loaded {len(articles)} articles from week {week_id}"
        )

        # Step 2: Deduplicate articles
        logger.info(f"[FINALIZATION] Deduplicating {len(articles)} articles...")
        deduped_articles, removed_count = DeduplicationUtils.deduplicate_articles(
            articles,
            strategy="combined"
        )
        logger.info(
            f"[FINALIZATION] After deduplication: {len(deduped_articles)} articles "
            f"(removed {removed_count} duplicates)"
        )

        # Step 3: Re-rank by combined score
        logger.info(f"[FINALIZATION] Re-ranking {len(deduped_articles)} articles...")
        ranked_articles = DeduplicationUtils.rank_by_combined_score(deduped_articles)
        logger.info(f"[FINALIZATION] Top candidates by combined score:")
        for article_id, _, score in ranked_articles[:5]:
            article_data = deduped_articles[article_id]
            title = article_data.get('article', {}).get('title', 'N/A')[:60]
            logger.info(f"  [{score:.2f}] {title}...")

        # Step 4: Select top candidates for Tier 3 evaluation
        # Tier 3 will evaluate up to 30 candidates
        tier3_candidates = ranked_articles[:30]
        logger.info(
            f"[FINALIZATION] Running Tier 3 full evaluation on {len(tier3_candidates)} candidates..."
        )

        # Convert to article list format for Tier 3 evaluator
        candidate_articles = []
        for article_id, article_data, combined_score in tier3_candidates:
            article = article_data.get('article', {}).copy()
            article['id'] = article_id
            article['combined_score'] = combined_score
            article['tier2_score'] = article_data.get('tier2_score', 0)
            candidate_articles.append(article)

        # Step 5: Run Tier 3 full evaluation
        if self.news_evaluator and categories:
            evaluated_articles = self.news_evaluator.evaluate_articles(
                candidate_articles,
                categories,
                top_n=top_n
            )
            logger.info(
                f"[FINALIZATION] Tier 3 evaluation complete: {len(evaluated_articles)}/{len(tier3_candidates)} "
                f"articles selected for final report"
            )
        else:
            logger.warning(
                "[FINALIZATION] News evaluator not available, using combined score ranking"
            )
            evaluated_articles = [
                {**article, 'final_score': article.get('combined_score', 0)}
                for article in candidate_articles[:top_n]
            ]

        # Step 6: Save Tier 3 scores to checkpoint
        for article in evaluated_articles:
            article_id = article.get('id')
            if article_id:
                self.checkpoint_manager.save_article_tier3_score(
                    article_id=article_id,
                    scores={
                        'impact': article.get('scores', {}).get('impact', 0),
                        'relevance': article.get('scores', {}).get('relevance', 0),
                        'recency': article.get('scores', {}).get('recency', 0),
                        'credibility': article.get('scores', {}).get('credibility', 0),
                        'overall': article.get('overall_score', 0)
                    },
                    takeaway=article.get('takeaway', ''),
                    provider_used='finalization'
                )

        # Log finalization summary
        WeeklyUtils.log_finalization_status(
            week_id,
            len(deduped_articles),
            len(evaluated_articles),
            len(evaluated_articles)
        )

        stats = self.checkpoint_manager.get_weekly_stats()

        return {
            'week_id': week_id,
            'total_collected': len(articles),
            'after_deduplication': len(deduped_articles),
            'tier3_candidates': len(tier3_candidates),
            'final_articles': evaluated_articles,
            'final_count': len(evaluated_articles),
            'checkpoint_stats': stats,
            'finalization_batch_id': WeeklyUtils.get_finalization_batch_id(week_id)
        }

    def get_finalization_candidates(
        self,
        week_id: Optional[str] = None,
        limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get top candidates that will be evaluated in Tier 3

        Args:
            week_id: Week ID (defaults to current week)
            limit: Maximum candidates to return

        Returns:
            List of articles with combined scores
        """
        if week_id is None:
            week_id = WeeklyUtils.get_current_week_id()

        if not self.checkpoint_manager.load_weekly_checkpoint(week_id):
            logger.warning(f"No checkpoint found for {week_id}")
            return []

        articles = self.checkpoint_manager.processed_articles

        # Deduplicate first
        deduped_articles, _ = DeduplicationUtils.deduplicate_articles(articles)

        # Rank by combined score
        ranked = DeduplicationUtils.rank_by_combined_score(deduped_articles)

        # Return top candidates
        candidates = []
        for article_id, article_data, combined_score in ranked[:limit]:
            candidates.append({
                'id': article_id,
                'title': article_data.get('article', {}).get('title'),
                'source': article_data.get('article', {}).get('source'),
                'tier1_score': article_data.get('tier1_score'),
                'tier2_score': article_data.get('tier2_score'),
                'combined_score': combined_score,
                'collection_day': article_data.get('collection_day')
            })

        return candidates

    def log_finalization_preview(self, week_id: Optional[str] = None) -> None:
        """
        Log preview of what will be finalized this week

        Args:
            week_id: Week ID (defaults to current week)
        """
        if week_id is None:
            week_id = WeeklyUtils.get_current_week_id()

        candidates = self.get_finalization_candidates(week_id, limit=10)

        logger.info(f"\n[FINALIZATION PREVIEW] Top 10 candidates for {week_id}:")
        for i, candidate in enumerate(candidates, 1):
            logger.info(
                f"  {i}. [{candidate['combined_score']:.2f}] {candidate['title'][:60]}... "
                f"(Day {candidate['collection_day']}, Score: {candidate['tier2_score']:.1f})"
            )

    def finalize_early_report(
        self,
        week_id: Optional[str] = None,
        categories: Optional[List[Dict[str, Any]]] = None,
        top_n: int = 15,
        enable_backfill: bool = True,
        min_articles_per_day: int = 5
    ) -> Dict[str, Any]:
        """
        Generate early report (Friday) with automatic backfilling of missing days

        This method:
        1. Detects which collection days have missing/low articles
        2. Auto-runs collection for missing days if backfill enabled
        3. Loads all collected articles (7 days worth)
        4. Deduplicates and re-ranks
        5. Runs Tier 3 evaluation
        6. Generates final report

        Args:
            week_id: Week ID to finalize (defaults to current week)
            categories: User's selected categories (for Tier 3)
            top_n: Number of articles in final report
            enable_backfill: Whether to auto-collect missing days
            min_articles_per_day: Minimum articles expected per day

        Returns:
            Dictionary with early report results
        """
        if week_id is None:
            week_id = WeeklyUtils.get_current_week_id()

        logger.info("=" * 60)
        logger.info("Starting EARLY Report Generation (Friday)")
        logger.info("MODE: EARLY FINALIZATION (with automatic backfill)")
        logger.info("=" * 60)

        logger.info(f"Week ID: {week_id}")
        week_range = WeeklyUtils.format_week_range(week_id)
        logger.info(f"Week date range: {week_range}")

        try:
            # Step 1: Check for missing collection days
            logger.info("\n[EARLY REPORT] Step 1: Checking for missing collection days...")
            missing_days, low_days, total_articles = WeeklyUtils.detect_missing_collection_days(
                week_id,
                checkpoint_manager=self.checkpoint_manager,
                min_articles_per_day=min_articles_per_day
            )

            backfilled_days = []

            # Step 2: Backfill missing days if enabled
            if enable_backfill and (missing_days or low_days):
                logger.info(f"\n[EARLY REPORT] Step 2: Backfilling {len(missing_days)} missing days...")
                backfilled_days = self._backfill_missing_days(
                    week_id=week_id,
                    missing_days=missing_days,
                    categories=categories
                )
                logger.info(
                    f"[EARLY REPORT] Backfill complete: Collected articles for {len(backfilled_days)} days"
                )
            else:
                logger.info(
                    f"[EARLY REPORT] Step 2: Backfill {'disabled' if not enable_backfill else 'not needed'}"
                )

            # Step 3: Run standard finalization with collected articles
            logger.info("\n[EARLY REPORT] Step 3: Running finalization (dedup + Tier 3)...")
            result = self.finalize_weekly_articles(
                week_id=week_id,
                categories=categories,
                top_n=top_n
            )

            if 'error' in result:
                return result

            # Step 4: Add early report metadata
            final_articles = result.get('final_articles', [])

            logger.info("\n" + "=" * 60)
            logger.info(f"✅ Early report generated successfully!")
            logger.info(f"📊 Data coverage: {len(backfilled_days)} days backfilled")
            logger.info(f"📊 Total articles: {result['total_collected']}")
            logger.info(f"📊 Final articles: {len(final_articles)}")
            logger.info("=" * 60)

            # Log completion
            WeeklyUtils.log_early_report_complete(
                week_id,
                result['total_collected'],
                len(final_articles),
                backfilled_days
            )

            result['early_report'] = True
            result['backfilled_days'] = backfilled_days
            result['report_type'] = 'Early Report (Friday)'

            return result

        except Exception as e:
            logger.error(f"❌ Error in early report generation: {e}")
            raise

    def _backfill_missing_days(
        self,
        week_id: str,
        missing_days: List[int],
        categories: Optional[List[Dict[str, Any]]] = None
    ) -> List[int]:
        """
        Backfill articles for missing collection days

        Args:
            week_id: Week ID
            missing_days: List of days (1-7) that need backfilling
            categories: Categories to use for collection

        Returns:
            List of days that were successfully backfilled
        """
        if not self.collection_mode:
            logger.warning("[EARLY REPORT] Collection mode not available, cannot backfill")
            return []

        backfilled_days = []

        for day in missing_days:
            try:
                day_name = WeeklyUtils.get_day_name(day)
                logger.info(f"[EARLY REPORT] Backfilling {day_name} (Day {day})...")

                # Run collection for this day
                result = self.collection_mode.collect_articles(
                    articles=[],  # Will scrape in collect_articles
                    categories=categories or [],
                    week_id=week_id,
                    day=day
                )

                if result.get('tier2_passed', 0) > 0:
                    backfilled_days.append(day)
                    logger.info(
                        f"[EARLY REPORT] Backfilled {day_name}: {result['tier2_passed']} articles"
                    )
                else:
                    logger.warning(f"[EARLY REPORT] Backfill for {day_name} returned 0 articles")

            except Exception as e:
                logger.warning(f"[EARLY REPORT] Error backfilling {day_name}: {e}")
                continue

        return backfilled_days
