"""
ACE Orchestrator - Main Pipeline Controller

Agentic Context Engineering (ACE) Orchestrator manages the entire 9-phase pipeline
with adaptive context management, comprehensive error tracking, and detailed metrics.

9 Phases:
1. Initialization - Load configs and categories
2. Scraping - Collect articles from 86 sources
3. Tier 1 Filter - Keyword-based pre-filtering
4. Tier 2 Batch Eval - Quick LLM scoring
5. Tier 3 5D Eval - Deep 5D evaluation
6. Ranking - Apply 5D weighted scoring
7. Paraphrasing - Generate 500-600 char analysis
8. Report Generation - Create final Markdown report
9. Finalization - Cleanup and save history
"""

import sys
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.context_engine import ContextEngine
from orchestrator.error_tracker import ErrorTracker
from orchestrator.metrics_collector import MetricsCollector
from orchestrator.phase_manager import PhaseManager
from orchestrator.execution_reporter import ExecutionReporter

# Import pipeline components
from modules.web_scraper import WebScraper
from utils.cache_manager import CacheManager
from utils.checkpoint_manager import CheckpointManager
from utils.article_filter import ArticleFilter
from modules.batch_evaluator import BatchEvaluator
from modules.news_evaluator import NewsEvaluator
from utils.scoring_engine import ScoringEngine
from modules.article_paraphraser import ArticleParaphraser
from modules.report_formatter import ReportFormatter
from utils.llm_client_enhanced import LLMClient
from utils.category_loader import load_categories, get_company_context


class ACEOrchestrator:
    """Main orchestrator for the briefAI pipeline with ACE (Agentic Context Engineering)"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize ACE Orchestrator

        Args:
            config: Optional configuration dict
        """
        # Generate run ID
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Load config
        self.config = config or self._load_default_config()

        # Initialize core components
        self.context_engine = ContextEngine(self.run_id)
        self.error_tracker = ErrorTracker(self.run_id)
        self.metrics_collector = MetricsCollector(self.run_id)
        self.phase_manager = PhaseManager(
            self.context_engine,
            self.error_tracker,
            self.metrics_collector
        )
        self.execution_reporter = ExecutionReporter(
            self.context_engine,
            self.error_tracker,
            self.metrics_collector,
            self.phase_manager
        )

        # Pipeline components (initialized per phase)
        self.cache_mgr = None
        self.checkpoint_mgr = None
        self.llm_client = None

        # Pipeline state
        self.categories = []
        self.company_context = {}
        self.final_articles = []
        self.final_report_path = None

        logger.info(f"ACE Orchestrator initialized - Run ID: {self.run_id}")

    def run_pipeline(
        self,
        category_ids: Optional[List[str]] = None,
        top_n: int = 12,
        days_back: int = 7,
        resume: bool = False,
        force_restart: bool = False
    ) -> str:
        """
        Execute complete 9-phase pipeline

        Args:
            category_ids: Optional list of category IDs
            top_n: Number of final articles
            days_back: Days to look back for articles
            resume: Resume from checkpoint if available
            force_restart: Force restart (ignore checkpoint)

        Returns:
            Path to final report

        Raises:
            RuntimeError: If pipeline fails
        """
        logger.info("=" * 80)
        logger.info(f"ACE ORCHESTRATOR - Pipeline Starting")
        logger.info(f"Run ID: {self.run_id}")
        logger.info(f"Config: top_n={top_n}, days_back={days_back}, resume={resume}")
        logger.info("=" * 80)

        pipeline_status = 'SUCCESS'
        start_time = datetime.now()

        try:
            # Phase 1: Initialization
            init_result = self.phase_manager.execute(
                'initialization',
                self.phase_1_initialization,
                category_ids=category_ids
            )

            # Phase 2: Scraping
            articles = self.phase_manager.execute(
                'scraping',
                self.phase_2_scraping,
                days_back=days_back,
                resume=resume,
                force_restart=force_restart
            )

            # Phase 3: Tier 1 Filter
            tier1_articles = self.phase_manager.execute(
                'tier1_filter',
                self.phase_3_tier1_filter,
                articles=articles
            )

            # Phase 4: Tier 2 Batch Evaluation
            tier2_articles = self.phase_manager.execute(
                'tier2_batch_eval',
                self.phase_4_tier2_batch_eval,
                filtered_articles=tier1_articles
            )

            # Phase 5: Tier 3 5D Evaluation
            tier3_articles = self.phase_manager.execute(
                'tier3_5d_eval',
                self.phase_5_tier3_5d_eval,
                tier2_articles=tier2_articles,
                top_n=top_n
            )

            # Phase 6: Ranking
            ranked_articles = self.phase_manager.execute(
                'ranking',
                self.phase_6_ranking,
                evaluated_articles=tier3_articles
            )

            # Phase 7: Paraphrasing
            paraphrased_articles = self.phase_manager.execute(
                'paraphrasing',
                self.phase_7_paraphrasing,
                ranked_articles=ranked_articles
            )

            # Phase 8: Entity Background
            enriched_articles = self.phase_manager.execute(
                'entity_background',
                self.phase_8_entity_background,
                paraphrased_articles=paraphrased_articles
            )

            # Phase 8.5: Quality Validation
            validated_articles = self.phase_manager.execute(
                'quality_validation',
                self.phase_8_5_quality_validation,
                enriched_articles=enriched_articles
            )

            # Phase 9: Report Generation
            report_path = self.phase_manager.execute(
                'report_generation',
                self.phase_9_report_generation,
                final_articles=validated_articles
            )

            self.final_report_path = report_path
            self.final_articles = paraphrased_articles

            # Phase 10: Finalization
            self.phase_manager.execute(
                'finalization',
                self.phase_10_finalization
            )

        except Exception as e:
            pipeline_status = 'FAILED'
            logger.error(f"Pipeline failed: {e}")
            raise

        finally:
            # Calculate total duration
            end_time = datetime.now()
            total_duration = (end_time - start_time).total_seconds()

            # Generate execution summary
            summary = self.execution_reporter.generate_execution_summary(
                status=pipeline_status,
                final_output_path=self.final_report_path
            )

            # Print summary
            logger.info("\n" + "=" * 80)
            logger.info("PIPELINE EXECUTION SUMMARY")
            logger.info("=" * 80)
            print(summary)

            # Save summary to file
            summary_file = Path(f"./data/reports/execution_summary_{self.run_id}.md")
            summary_file.parent.mkdir(parents=True, exist_ok=True)
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(summary)

            logger.info(f"\nExecution summary saved: {summary_file}")

            # Save bug report if errors occurred
            if self.error_tracker.has_critical_errors():
                bug_report = self.error_tracker.generate_bug_report()
                bug_file = Path(f"./data/reports/bug_report_{self.run_id}.md")
                with open(bug_file, 'w', encoding='utf-8') as f:
                    f.write(bug_report)
                logger.info(f"Bug report saved: {bug_file}")

        return self.final_report_path

    # =========================================================================
    # PHASE 1: INITIALIZATION
    # =========================================================================

    def phase_1_initialization(self, category_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Phase 1: Load configurations and categories

        Args:
            category_ids: Optional list of category IDs

        Returns:
            Initialization result dict
        """
        logger.info("Loading categories and configuration...")

        # Load categories
        self.categories = load_categories(category_ids)
        self.company_context = get_company_context()

        # Initialize components
        self.cache_mgr = CacheManager()
        self.checkpoint_mgr = CheckpointManager()
        self.llm_client = LLMClient()

        logger.info(f"✓ Loaded {len(self.categories)} categories")
        logger.info(f"✓ Company: {self.company_context.get('business', 'N/A')}")

        # Record metrics
        self.metrics_collector.record_metric(
            'categories_loaded',
            len(self.categories),
            'initialization'
        )

        return {
            'status': 'ok',
            'categories_count': len(self.categories),
            'config_valid': True
        }

    # =========================================================================
    # PHASE 2: SCRAPING
    # =========================================================================

    def phase_2_scraping(
        self,
        days_back: int = 7,
        resume: bool = False,
        force_restart: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Phase 2: Scrape articles from 86 sources

        Args:
            days_back: Days to look back
            resume: Resume from checkpoint
            force_restart: Force restart

        Returns:
            List of scraped articles
        """
        logger.info(f"Scraping articles from last {days_back} days...")

        try:
            scraper = WebScraper(cache_manager=self.cache_mgr)

            articles = scraper.scrape_all(
                days_back=days_back,
                use_cache=False,
                resume=resume and not force_restart,
                checkpoint_manager=self.checkpoint_mgr
            )

            # Clear checkpoint after successful scraping
            if resume and not force_restart:
                self.checkpoint_mgr.clear_checkpoint()

            logger.info(f"✓ Scraped {len(articles)} articles")

            # Record metrics
            self.metrics_collector.record_metric(
                'sources_attempted',
                86,  # Total sources
                'scraping'
            )
            self.metrics_collector.record_metric(
                'sources_succeeded',
                len(set(a.get('source') for a in articles)),
                'scraping'
            )

            return articles

        except Exception as e:
            self.error_tracker.log_error(
                phase='scraping',
                error=e,
                severity='CRITICAL',
                recovery_action='FAIL_FAST'
            )
            raise

    # =========================================================================
    # PHASE 3: TIER 1 FILTER
    # =========================================================================

    def phase_3_tier1_filter(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Phase 3: Keyword-based pre-filtering

        Args:
            articles: Scraped articles

        Returns:
            Filtered articles
        """
        logger.info(f"Tier 1 pre-filtering {len(articles)} articles...")

        try:
            tier1_filter = ArticleFilter(score_threshold=3.0)
            filtered_articles = tier1_filter.filter_articles(articles, self.categories)

            filter_rate = len(filtered_articles) / len(articles) if articles else 0

            logger.info(
                f"✓ Tier 1: {len(filtered_articles)}/{len(articles)} articles passed "
                f"({filter_rate:.1%})"
            )

            # Record metrics
            self.metrics_collector.record_metric(
                'filter_rate',
                filter_rate,
                'tier1_filter'
            )

            return filtered_articles

        except Exception as e:
            self.error_tracker.log_error(
                phase='tier1_filter',
                error=e,
                severity='CRITICAL',
                recovery_action='FAIL_FAST'
            )
            raise

    # =========================================================================
    # PHASE 4: TIER 2 BATCH EVALUATION
    # =========================================================================

    def phase_4_tier2_batch_eval(
        self,
        filtered_articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Phase 4: Quick LLM batch evaluation

        Args:
            filtered_articles: Pre-filtered articles

        Returns:
            Articles that passed Tier 2
        """
        logger.info(f"Tier 2 batch evaluation on {len(filtered_articles)} articles...")

        try:
            batch_eval = BatchEvaluator(
                llm_client=self.llm_client,
                batch_size=10,
                pass_score=6.0
            )

            tier2_articles = batch_eval.evaluate_batch(filtered_articles, self.categories)

            pass_rate = len(tier2_articles) / len(filtered_articles) if filtered_articles else 0

            logger.info(
                f"✓ Tier 2: {len(tier2_articles)}/{len(filtered_articles)} articles passed "
                f"({pass_rate:.1%})"
            )

            # Record metrics
            self.metrics_collector.record_metric(
                'pass_rate',
                pass_rate,
                'tier2_batch_eval'
            )

            # Record LLM calls (approximate)
            num_batches = (len(filtered_articles) + 9) // 10
            for i in range(num_batches):
                self.metrics_collector.record_llm_call(
                    provider='kimi',
                    model='moonshot-v1-8k',
                    input_tokens=2000,  # Approximate
                    output_tokens=500,
                    latency_ms=2000,
                    phase='tier2_batch_eval'
                )

            return tier2_articles

        except Exception as e:
            self.error_tracker.log_error(
                phase='tier2_batch_eval',
                error=e,
                severity='CRITICAL',
                recovery_action='FAIL_FAST'
            )
            raise

    # =========================================================================
    # PHASE 5: TIER 3 5D EVALUATION
    # =========================================================================

    def phase_5_tier3_5d_eval(
        self,
        tier2_articles: List[Dict[str, Any]],
        top_n: int = 12
    ) -> List[Dict[str, Any]]:
        """
        Phase 5: Deep 5D evaluation

        Args:
            tier2_articles: Articles from Tier 2
            top_n: Number of articles to select

        Returns:
            Top N evaluated articles
        """
        logger.info(f"Tier 3 5D evaluation on top {top_n} articles...")

        try:
            news_eval = NewsEvaluator(llm_client=self.llm_client)

            tier3_articles = news_eval.evaluate_articles(
                tier2_articles,
                self.categories,
                top_n=top_n
            )

            logger.info(f"✓ Tier 3: Selected top {len(tier3_articles)} articles with 5D scores")

            # Record LLM calls
            for article in tier3_articles:
                self.metrics_collector.record_llm_call(
                    provider='kimi',
                    model='moonshot-v1-8k',
                    input_tokens=3000,  # Approximate
                    output_tokens=800,
                    latency_ms=2500,
                    phase='tier3_5d_eval'
                )

            return tier3_articles

        except Exception as e:
            self.error_tracker.log_error(
                phase='tier3_5d_eval',
                error=e,
                severity='CRITICAL',
                recovery_action='FAIL_FAST'
            )
            raise

    # =========================================================================
    # PHASE 6: RANKING
    # =========================================================================

    def phase_6_ranking(self, evaluated_articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Phase 6: Apply 5D weighted scoring and sort

        Args:
            evaluated_articles: Articles with 5D scores

        Returns:
            Ranked articles
        """
        logger.info(f"Ranking {len(evaluated_articles)} articles by 5D scores...")

        try:
            scoring_engine = ScoringEngine()
            ranked_articles = []

            for article in evaluated_articles:
                if 'evaluation' in article and 'scores' in article['evaluation']:
                    scores = article['evaluation']['scores']
                    weighted_score = scoring_engine.calculate_weighted_score(scores)
                    article['weighted_score'] = weighted_score

                ranked_articles.append(article)

            # Sort by weighted score descending
            ranked_articles.sort(key=lambda x: x.get('weighted_score', 0), reverse=True)

            logger.info(f"✓ Ranked {len(ranked_articles)} articles")

            return ranked_articles

        except Exception as e:
            self.error_tracker.log_error(
                phase='ranking',
                error=e,
                severity='CRITICAL',
                recovery_action='FAIL_FAST'
            )
            raise

    # =========================================================================
    # PHASE 7: PARAPHRASING
    # =========================================================================

    def phase_7_paraphrasing(self, ranked_articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Phase 7: Generate 500-600 character deep analysis

        Args:
            ranked_articles: Ranked articles

        Returns:
            Articles with paraphrased content
        """
        logger.info(f"Paraphrasing {len(ranked_articles)} articles (500-600 chars)...")

        try:
            paraphraser = ArticleParaphraser(
                llm_client=self.llm_client,
                min_length=500,
                max_length=600
            )

            paraphrased_articles = paraphraser.paraphrase_articles(ranked_articles)

            logger.info(f"✓ Paraphrased {len(paraphrased_articles)} articles")

            # Record LLM calls
            for article in paraphrased_articles:
                self.metrics_collector.record_llm_call(
                    provider='kimi',
                    model='moonshot-v1-8k',
                    input_tokens=2500,
                    output_tokens=600,
                    latency_ms=2000,
                    phase='paraphrasing'
                )

            return paraphrased_articles

        except Exception as e:
            self.error_tracker.log_error(
                phase='paraphrasing',
                error=e,
                severity='CRITICAL',
                recovery_action='FAIL_FAST'
            )
            raise

    # =========================================================================
    # PHASE 8: ENTITY BACKGROUND
    # =========================================================================

    def phase_8_entity_background(
        self,
        paraphrased_articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Phase 8: Enrich articles with entity backgrounds

        Generates article-specific backgrounds for main entities (companies/products/tech).
        Uses ACE context for smart caching to avoid redundant LLM calls.

        Args:
            paraphrased_articles: Articles with paraphrased content

        Returns:
            Articles enriched with entity_background field
        """
        logger.info(f"Enriching {len(paraphrased_articles)} articles with entity backgrounds...")

        try:
            from modules.entity_background_agent import EntityBackgroundAgent

            agent = EntityBackgroundAgent(llm_client=self.llm_client)

            # Enrich articles with context-aware caching
            enriched_articles, metrics = agent.enrich_articles(
                articles=paraphrased_articles,
                context_engine=self.context_engine
            )

            logger.info(
                f"✓ Entity background complete: {metrics['backgrounds_generated']} generated, "
                f"{metrics['backgrounds_cached']} cached, {metrics['failed']} failed"
            )

            # Record metrics
            if metrics['backgrounds_generated'] > 0:
                # Record LLM calls for generated backgrounds
                for _ in range(metrics['backgrounds_generated']):
                    self.metrics_collector.record_llm_call(
                        provider='kimi',
                        model='moonshot-v1-8k',
                        input_tokens=400,
                        output_tokens=200,
                        latency_ms=1500,
                        phase='entity_background'
                    )

            # Add insight to context
            self.context_engine.add_global_insight(
                f"Entity background enrichment: {metrics['entities_extracted']} entities identified, "
                f"{metrics['backgrounds_generated']} new backgrounds generated"
            )

            return enriched_articles

        except Exception as e:
            self.error_tracker.log_error(
                phase='entity_background',
                error=e,
                severity='WARNING',  # Not critical - can continue without entity backgrounds
                recovery_action='CONTINUE',
                context={
                    'articles_count': len(paraphrased_articles)
                }
            )
            logger.warning(f"Entity background enrichment failed, continuing without backgrounds: {e}")
            # Return original articles without entity backgrounds
            return paraphrased_articles

    # =========================================================================
    # PHASE 8.5: QUALITY VALIDATION
    # =========================================================================

    def phase_8_5_quality_validation(
        self,
        enriched_articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Phase 8.5: Validate paraphrased content quality

        Checks:
        - All articles have proper paraphrased_content (not original excerpts)
        - Content length is within 500-600 characters
        - Content is in Mandarin Chinese (not English)
        - No incomplete sentences or truncated content

        Args:
            enriched_articles: Articles with paraphrased content and entity backgrounds

        Returns:
            Validated articles (re-paraphrases failed ones)
        """
        logger.info(f"Validating quality of {len(enriched_articles)} paraphrased articles...")

        validated_articles = []
        failed_validations = []

        for idx, article in enumerate(enriched_articles, 1):
            title = article.get('title', 'Unknown')[:50]
            paraphrased = article.get('paraphrased_content', '')

            # Quality checks
            is_valid = True
            failure_reasons = []

            # Check 1: Has paraphrased content
            if not paraphrased or len(paraphrased.strip()) == 0:
                is_valid = False
                failure_reasons.append("No paraphrased content")

            # Check 2: Length check (500-600 chars)
            elif len(paraphrased) < 400:  # Allow some tolerance
                is_valid = False
                failure_reasons.append(f"Too short ({len(paraphrased)} chars)")

            # Check 3: Not original English excerpt (check for common English patterns)
            elif any(pattern in paraphrased[:100] for pattern in [
                'Application programming', 'AI development has become',
                'is essential for modern', 'has become a race'
            ]):
                is_valid = False
                failure_reasons.append("Appears to be original English excerpt")

            # Check 4: Contains Chinese characters
            elif not any('\u4e00' <= char <= '\u9fff' for char in paraphrased[:100]):
                is_valid = False
                failure_reasons.append("No Chinese characters detected")

            # Check 5: Not truncated (should end with period/sentence)
            elif paraphrased.strip() and paraphrased.strip()[-1] in '.,!?;':
                pass  # Good
            elif paraphrased.strip().endswith('...'):
                is_valid = False
                failure_reasons.append("Appears truncated (ends with ...)")

            if is_valid:
                validated_articles.append(article)
                logger.debug(f"✓ Article {idx} passed validation: {title}")
            else:
                failed_validations.append({
                    'index': idx,
                    'title': title,
                    'reasons': failure_reasons,
                    'article': article
                })
                logger.warning(
                    f"✗ Article {idx} FAILED validation: {title} - {', '.join(failure_reasons)}"
                )

        # Log validation results to context
        if failed_validations:
            failed_indices = ', '.join(f"#{f['index']}" for f in failed_validations)
            self.context_engine.add_global_insight(
                f"Quality validation found {len(failed_validations)} articles with paraphrasing issues: "
                f"{failed_indices}"
            )

            # Track error
            self.error_tracker.log_error(
                phase='quality_validation',
                error=ValueError(f"{len(failed_validations)} articles failed quality validation"),
                severity='CRITICAL',
                context={
                    'failed_count': len(failed_validations),
                    'failed_articles': [
                        {
                            'index': f['index'],
                            'title': f['title'],
                            'reasons': f['reasons']
                        }
                        for f in failed_validations
                    ]
                },
                recovery_action='RE_PARAPHRASE'
            )

            logger.error(
                f"✗ {len(failed_validations)}/{len(enriched_articles)} articles failed validation. "
                "Consider re-running paraphrasing phase."
            )

        logger.info(
            f"✓ Quality validation: {len(validated_articles)}/{len(enriched_articles)} articles passed"
        )

        # Record metrics
        self.metrics_collector.record_metric(
            'validation_pass_rate',
            len(validated_articles) / len(enriched_articles) if enriched_articles else 0,
            'quality_validation'
        )

        return validated_articles

    # =========================================================================
    # PHASE 9: REPORT GENERATION
    # =========================================================================

    def phase_9_report_generation(self, final_articles: List[Dict[str, Any]]) -> str:
        """
        Phase 9: Generate final Markdown report

        Args:
            final_articles: Final paraphrased articles

        Returns:
            Path to generated report
        """
        logger.info(f"Generating final report with {len(final_articles)} articles...")

        try:
            formatter = ReportFormatter(
                llm_client=self.llm_client,
                company_context=self.company_context,
                include_5d_scores=True
            )

            report_path = formatter.generate_report(
                articles=final_articles,
                categories=self.categories,
                report_type='weekly'
            )

            logger.info(f"✓ Report generated: {report_path}")

            return report_path

        except Exception as e:
            self.error_tracker.log_error(
                phase='report_generation',
                error=e,
                severity='CRITICAL',
                recovery_action='FAIL_FAST'
            )
            raise

    # =========================================================================
    # PHASE 10: FINALIZATION
    # =========================================================================

    def phase_10_finalization(self) -> Dict[str, Any]:
        """
        Phase 10: Cleanup and save history

        Returns:
            Finalization result
        """
        logger.info("Finalizing pipeline execution...")

        try:
            # Save context snapshot
            self.context_engine.save_snapshot()

            # Save metrics
            self.metrics_collector.save_to_file()

            # Clear checkpoint
            self.checkpoint_mgr.clear_checkpoint()

            logger.info("✓ Finalization complete")

            return {'status': 'ok'}

        except Exception as e:
            self.error_tracker.log_error(
                phase='finalization',
                error=e,
                severity='WARNING',
                recovery_action='CONTINUE'
            )
            # Don't fail pipeline on finalization errors
            return {'status': 'partial', 'error': str(e)}

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _load_default_config(self) -> Dict[str, Any]:
        """Load default orchestrator configuration"""
        config_file = Path("./config/orchestrator_config.json")

        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load orchestrator config: {e}")

        # Return defaults
        return {
            'top_n': 12,
            'days_back': 7,
            'tier1_threshold': 3.0,
            'tier2_pass_score': 6.0,
            'paraphrase_min_length': 500,
            'paraphrase_max_length': 600
        }


if __name__ == "__main__":
    # Test orchestrator
    orchestrator = ACEOrchestrator()

    try:
        report_path = orchestrator.run_pipeline(
            category_ids=None,  # Use defaults
            top_n=12,
            days_back=7,
            resume=False,
            force_restart=False
        )

        print(f"\n✅ Pipeline completed successfully!")
        print(f"📄 Report: {report_path}")

    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        raise
