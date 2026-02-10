"""
Pipeline Orchestrator for Multi-Pipeline Execution

Coordinates multiple briefing pipelines (news, product, investing, china_ai)
with configurable parallel execution, cross-pipeline aggregation, and trend radar updates.
"""

import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger

# TEMPORARY: Patch for Python 3.14 spaCy incompatibility
try:
    import utils.entity_extractor_patch  # noqa: F401
except ImportError:
    pass

# Import core components
from utils.llm_client_enhanced import LLMClient
from utils.cache_manager import CacheManager
from utils.article_filter import ArticleFilter
from modules.category_selector import CategorySelector
from modules.web_scraper import WebScraper
from modules.batch_evaluator import BatchEvaluator
from modules.news_evaluator import NewsEvaluator
from modules.article_paraphraser import ArticleParaphraser
from modules.report_formatter import ReportFormatter


class PipelineStatus(Enum):
    """Status of a pipeline execution"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PipelineResult:
    """Result of a single pipeline execution"""
    pipeline_id: str
    status: PipelineStatus
    report_path: Optional[str] = None
    articles_scraped: int = 0
    articles_selected: int = 0
    execution_time: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class PipelineOrchestrator:
    """
    Orchestrates multiple independent pipelines for comprehensive AI coverage.

    Pipelines:
    - news: General AI industry news
    - product: AI products and tools discovery
    - investing: VC/funding intelligence
    - china_ai: Chinese AI ecosystem
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the orchestrator.

        Args:
            config_path: Path to pipelines.json (defaults to config/pipelines.json)
        """
        self.config_path = config_path or Path(__file__).parent.parent / "config" / "pipelines.json"
        self.config = self._load_config()

        # Shared resources (created once, shared across pipelines)
        self.llm_client = LLMClient()
        self.cache_manager = CacheManager()

        logger.info(f"PipelineOrchestrator initialized with {len(self.config.get('pipelines', {}))} pipelines")

    def _load_config(self) -> Dict[str, Any]:
        """Load pipeline configuration."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Pipeline config not found at {self.config_path}, using defaults")
            return self._default_config()
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in pipeline config: {e}")
            return self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        """Return default pipeline configuration."""
        return {
            "pipelines": {
                "news": {
                    "name": "AI Industry News",
                    "sources_file": "sources.json",
                    "categories_file": "categories.json",
                    "output_prefix": "ai_briefing",
                    "enabled": True
                }
            },
            "orchestrator": {
                "run_mode": "sequential",
                "parallel_limit": 2,
                "fail_strategy": "continue"
            }
        }

    def get_enabled_pipelines(self) -> List[str]:
        """Get list of enabled pipeline IDs."""
        pipelines = self.config.get('pipelines', {})
        return [pid for pid, pconfig in pipelines.items() if pconfig.get('enabled', True)]

    def run_all_pipelines(
        self,
        target_date: Optional[datetime] = None,
        days_back: int = 7,
        top_n: int = 10,
        pipelines: Optional[List[str]] = None
    ) -> Dict[str, PipelineResult]:
        """
        Run all enabled pipelines (or specified subset).

        Args:
            target_date: Target date for reports (defaults to today)
            days_back: Number of days to look back for articles
            top_n: Number of articles per pipeline report
            pipelines: Specific pipelines to run (defaults to all enabled)

        Returns:
            Dict mapping pipeline_id to PipelineResult
        """
        target_date = target_date or datetime.now()
        results: Dict[str, PipelineResult] = {}

        # Determine which pipelines to run
        if pipelines:
            pipeline_ids = [p for p in pipelines if p in self.config.get('pipelines', {})]
        else:
            pipeline_ids = self.get_enabled_pipelines()

        if not pipeline_ids:
            logger.warning("No pipelines to run")
            return results

        logger.info("=" * 60)
        logger.info("MULTI-PIPELINE ORCHESTRATOR")
        logger.info(f"Target date: {target_date.strftime('%Y-%m-%d')}")
        logger.info(f"Pipelines: {', '.join(pipeline_ids)}")
        logger.info("=" * 60)

        # Get orchestrator settings
        orch_config = self.config.get('orchestrator', {})
        run_mode = orch_config.get('run_mode', 'sequential')
        parallel_limit = orch_config.get('parallel_limit', 2)
        fail_strategy = orch_config.get('fail_strategy', 'continue')

        # Execute pipelines
        if run_mode == 'parallel' and len(pipeline_ids) > 1:
            results = self._run_parallel(
                pipeline_ids, target_date, days_back, top_n, parallel_limit
            )
        else:
            results = self._run_sequential(
                pipeline_ids, target_date, days_back, top_n, fail_strategy
            )

        # Aggregate trends if configured
        if self.config.get('trend_radar', {}).get('aggregate_from'):
            self._aggregate_trends(results, target_date)

        # Generate combined report if configured
        combined_config = orch_config.get('combined_report', {})
        if combined_config.get('enabled', False):
            self._generate_combined_report(results, target_date, combined_config)

        # Print summary
        self._print_summary(results)

        return results

    def _run_sequential(
        self,
        pipeline_ids: List[str],
        target_date: datetime,
        days_back: int,
        top_n: int,
        fail_strategy: str
    ) -> Dict[str, PipelineResult]:
        """Run pipelines sequentially."""
        results = {}

        for i, pipeline_id in enumerate(pipeline_ids, 1):
            logger.info(f"\n[{i}/{len(pipeline_ids)}] Running pipeline: {pipeline_id}")

            result = self._run_single_pipeline(
                pipeline_id, target_date, days_back, top_n
            )
            results[pipeline_id] = result

            # Check fail strategy
            if result.status == PipelineStatus.FAILED and fail_strategy == 'stop':
                logger.error(f"Pipeline {pipeline_id} failed, stopping execution")
                break

        return results

    def _run_parallel(
        self,
        pipeline_ids: List[str],
        target_date: datetime,
        days_back: int,
        top_n: int,
        parallel_limit: int
    ) -> Dict[str, PipelineResult]:
        """Run pipelines in parallel with thread pool."""
        results = {}

        with ThreadPoolExecutor(max_workers=parallel_limit) as executor:
            futures = {
                executor.submit(
                    self._run_single_pipeline, pid, target_date, days_back, top_n
                ): pid for pid in pipeline_ids
            }

            for future in as_completed(futures):
                pipeline_id = futures[future]
                try:
                    result = future.result()
                    results[pipeline_id] = result
                except Exception as e:
                    logger.error(f"Pipeline {pipeline_id} failed with exception: {e}")
                    results[pipeline_id] = PipelineResult(
                        pipeline_id=pipeline_id,
                        status=PipelineStatus.FAILED,
                        error=str(e)
                    )

        return results

    def _run_single_pipeline(
        self,
        pipeline_id: str,
        target_date: datetime,
        days_back: int,
        top_n: int
    ) -> PipelineResult:
        """
        Run a single pipeline.

        Args:
            pipeline_id: Pipeline identifier (news, product, investing, china_ai)
            target_date: Target date for the report
            days_back: Days to look back for articles
            top_n: Number of articles to include

        Returns:
            PipelineResult with execution details
        """
        start_time = datetime.now()
        pipeline_config = self.config['pipelines'].get(pipeline_id, {})

        try:
            logger.info(f"Starting pipeline: {pipeline_config.get('name', pipeline_id)}")

            # Load pipeline-specific configs
            config_dir = Path(__file__).parent.parent / "config"
            sources_file = config_dir / pipeline_config.get('sources_file', 'sources.json')
            categories_file = config_dir / pipeline_config.get('categories_file', 'categories.json')

            # Load categories
            with open(categories_file, 'r', encoding='utf-8') as f:
                cat_config = json.load(f)
                categories = cat_config.get('categories', [])
                default_cats = cat_config.get('default_categories', [])

            # Filter to default categories
            selected_categories = [c for c in categories if c['id'] in default_cats]
            if not selected_categories:
                selected_categories = categories[:4]  # Take first 4 if no defaults

            logger.info(f"Categories: {[c['name'] for c in selected_categories]}")

            # Initialize pipeline-specific components
            web_scraper = WebScraper(
                cache_manager=self.cache_manager,
                sources_config=str(sources_file)
            )

            # Use pipeline-specific threshold if set, otherwise fall back to env/default
            tier1_threshold = pipeline_config.get('tier1_threshold')
            if tier1_threshold is None:
                tier1_threshold = float(os.getenv('TIER1_SCORE_THRESHOLD', '3.0'))
            else:
                tier1_threshold = float(tier1_threshold)
                logger.info(f"Using pipeline-specific tier1_threshold: {tier1_threshold}")
            article_filter = ArticleFilter(score_threshold=tier1_threshold)

            batch_evaluator = BatchEvaluator(
                llm_client=self.llm_client,
                batch_size=5,  # Reduced for free model compatibility
                pass_score=6.0
            )

            news_evaluator = NewsEvaluator(llm_client=self.llm_client)
            paraphraser = ArticleParaphraser(llm_client=self.llm_client)

            # Use pipeline-specific output directory
            output_prefix = pipeline_config.get('output_prefix', 'briefing')
            formatter = ReportFormatter(
                llm_client=self.llm_client,
                output_dir=f"./data/reports"
            )

            # Step 1: Scrape articles
            logger.info("Scraping articles...")
            category_ids = [c['id'] for c in selected_categories]
            articles = web_scraper.scrape_all(
                categories=category_ids,
                days_back=days_back,
                use_cache=True
            )
            logger.info(f"Scraped {len(articles)} articles")

            if not articles:
                return PipelineResult(
                    pipeline_id=pipeline_id,
                    status=PipelineStatus.FAILED,
                    error="No articles scraped",
                    execution_time=(datetime.now() - start_time).total_seconds()
                )

            # Step 2: Tier 1 pre-filter
            logger.info("Tier 1: Pre-filtering...")
            tier1_articles = article_filter.filter_articles(
                articles=articles,
                categories=selected_categories
            )
            logger.info(f"Tier 1 passed: {len(tier1_articles)} articles")

            if not tier1_articles:
                return PipelineResult(
                    pipeline_id=pipeline_id,
                    status=PipelineStatus.FAILED,
                    articles_scraped=len(articles),
                    error="No articles passed Tier 1 filter",
                    execution_time=(datetime.now() - start_time).total_seconds()
                )

            # Step 3: Tier 2 batch evaluation
            logger.info("Tier 2: Batch evaluation...")
            tier2_articles = batch_evaluator.evaluate_batch(
                articles=tier1_articles,
                categories=selected_categories
            )

            if not tier2_articles:
                logger.warning("No articles passed Tier 2, using top Tier 1 articles")
                tier2_articles = tier1_articles[:top_n]

            logger.info(f"Tier 2 passed: {len(tier2_articles)} articles")

            # Step 4: Tier 3 full evaluation
            logger.info("Tier 3: Full evaluation...")
            evaluated_articles = news_evaluator.evaluate_articles(
                articles=tier2_articles,
                categories=selected_categories,
                top_n=top_n
            )
            logger.info(f"Selected top {len(evaluated_articles)} articles")

            if not evaluated_articles:
                return PipelineResult(
                    pipeline_id=pipeline_id,
                    status=PipelineStatus.FAILED,
                    articles_scraped=len(articles),
                    error="No articles passed Tier 3 evaluation",
                    execution_time=(datetime.now() - start_time).total_seconds()
                )

            # Step 5: Paraphrase
            logger.info("Paraphrasing articles...")
            paraphrased_articles = paraphraser.paraphrase_articles(
                articles=evaluated_articles
            )

            # Step 6: Generate report
            logger.info("Generating report...")
            report_period = target_date.strftime("%Y年%m月%d日")
            report_path = formatter.generate_report(
                articles=paraphrased_articles,
                categories=selected_categories,
                report_period=report_period,
                report_type="daily"
            )

            execution_time = (datetime.now() - start_time).total_seconds()

            logger.info(f"Pipeline {pipeline_id} completed in {execution_time:.1f}s")
            logger.info(f"Report: {report_path}")

            # Cache pipeline context for cross-pipeline analysis
            self._cache_pipeline_context(
                pipeline_id, target_date, paraphrased_articles, selected_categories
            )

            return PipelineResult(
                pipeline_id=pipeline_id,
                status=PipelineStatus.COMPLETED,
                report_path=report_path,
                articles_scraped=len(articles),
                articles_selected=len(evaluated_articles),
                execution_time=execution_time,
                metadata={
                    'tier1_passed': len(tier1_articles),
                    'tier2_passed': len(tier2_articles),
                    'categories': [c['name'] for c in selected_categories]
                }
            )

        except Exception as e:
            logger.error(f"Pipeline {pipeline_id} failed: {e}")
            import traceback
            traceback.print_exc()

            return PipelineResult(
                pipeline_id=pipeline_id,
                status=PipelineStatus.FAILED,
                error=str(e),
                execution_time=(datetime.now() - start_time).total_seconds()
            )

    def _cache_pipeline_context(
        self,
        pipeline_id: str,
        target_date: datetime,
        articles: List[Dict[str, Any]],
        categories: List[Dict[str, Any]]
    ):
        """Cache pipeline context for cross-pipeline analysis and API consumption."""
        cache_dir = Path(__file__).parent.parent / "data" / "cache" / "pipeline_contexts"
        cache_dir.mkdir(parents=True, exist_ok=True)

        date_str = target_date.strftime("%Y%m%d")
        cache_file = cache_dir / f"{pipeline_id}_{date_str}.json"

        # Build full article list for API
        full_articles = []
        for i, a in enumerate(articles, 1):
            full_articles.append({
                "id": f"{i:03d}",
                "title": a.get('title', ''),
                "url": a.get('url', ''),
                "source": a.get('source', ''),
                "source_id": a.get('source_id', ''),
                "weighted_score": a.get('total_score', 0) or a.get('weighted_score', 0),
                "content": a.get('content', ''),
                "paraphrased_content": a.get('paraphrased_content', ''),
                "published_date": a.get('published_at', '') or a.get('published_date', ''),
                "focus_tags": a.get('focus_tags', []),
                "searchable_entities": {
                    "companies": [e.get('name', '') for e in a.get('entities', []) if isinstance(e, dict) and e.get('type') == 'company'],
                    "models": [e.get('name', '') for e in a.get('entities', []) if isinstance(e, dict) and e.get('type') == 'model'],
                    "people": [e.get('name', '') for e in a.get('entities', []) if isinstance(e, dict) and e.get('type') == 'person'],
                }
            })

        context = {
            "pipeline_id": pipeline_id,
            "date": date_str,
            "article_count": len(articles),
            "categories": [c['id'] for c in categories],
            "entities": self._extract_entities(articles),
            "articles": full_articles,  # Full articles for API
            "top_articles": [
                {
                    "title": a.get('title', ''),
                    "source": a.get('source', ''),
                    "score": a.get('total_score', 0)
                }
                for a in articles[:5]
            ]
        }

        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(context, f, ensure_ascii=False, indent=2)

        logger.debug(f"Cached pipeline context: {cache_file}")

    def _extract_entities(self, articles: List[Dict[str, Any]]) -> List[str]:
        """Extract unique entities from articles."""
        entities = set()
        for article in articles:
            for entity in article.get('entities', []):
                if isinstance(entity, dict):
                    entities.add(entity.get('name', ''))
                elif isinstance(entity, str):
                    entities.add(entity)
        return list(entities)[:20]  # Top 20 entities

    def _aggregate_trends(
        self,
        results: Dict[str, PipelineResult],
        target_date: datetime
    ):
        """Aggregate trends across pipelines for trend radar."""
        logger.info("Aggregating cross-pipeline trends...")

        try:
            from utils.trend_aggregator import TrendAggregator

            aggregator = TrendAggregator()
            completed_pipelines = [
                pid for pid, r in results.items()
                if r.status == PipelineStatus.COMPLETED
            ]

            if completed_pipelines:
                aggregator.aggregate_trends(
                    pipeline_ids=completed_pipelines,
                    target_date=target_date
                )
                logger.info(f"Aggregated trends from {len(completed_pipelines)} pipelines")
        except ImportError:
            logger.debug("TrendAggregator not available, skipping trend aggregation")
        except Exception as e:
            logger.warning(f"Trend aggregation failed: {e}")

    def _generate_combined_report(
        self,
        results: Dict[str, PipelineResult],
        target_date: datetime,
        config: Dict[str, Any]
    ):
        """Generate a combined report from all pipeline results."""
        logger.info("Generating combined report...")

        try:
            sections = config.get('sections', [])
            output_prefix = config.get('output_prefix', 'combined_briefing')

            # Collect all report paths
            report_paths = []
            for section in sections:
                if section in results and results[section].report_path:
                    report_paths.append(results[section].report_path)

            if not report_paths:
                logger.warning("No reports to combine")
                return

            # Read and combine reports
            combined_content = []
            combined_content.append(f"# Combined AI Briefing - {target_date.strftime('%Y-%m-%d')}\n")
            combined_content.append(f"\n*Generated from {len(report_paths)} pipeline(s)*\n")
            combined_content.append("\n---\n")

            for report_path in report_paths:
                try:
                    with open(report_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        combined_content.append(f"\n{content}\n")
                        combined_content.append("\n---\n")
                except Exception as e:
                    logger.warning(f"Could not read report {report_path}: {e}")

            # Write combined report
            reports_dir = Path(__file__).parent.parent / "data" / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

            date_str = target_date.strftime("%Y%m%d")
            combined_path = reports_dir / f"{output_prefix}_{date_str}.md"

            with open(combined_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(combined_content))

            logger.info(f"Combined report: {combined_path}")

        except Exception as e:
            logger.warning(f"Combined report generation failed: {e}")

    def _print_summary(self, results: Dict[str, PipelineResult]):
        """Print execution summary."""
        logger.info("\n" + "=" * 60)
        logger.info("PIPELINE EXECUTION SUMMARY")
        logger.info("=" * 60)

        total_time = 0
        for pipeline_id, result in results.items():
            status_icon = "✅" if result.status == PipelineStatus.COMPLETED else "❌"
            logger.info(
                f"{status_icon} {pipeline_id}: {result.status.value} "
                f"({result.articles_selected}/{result.articles_scraped} articles, "
                f"{result.execution_time:.1f}s)"
            )
            if result.error:
                logger.info(f"   Error: {result.error}")
            total_time += result.execution_time

        completed = sum(1 for r in results.values() if r.status == PipelineStatus.COMPLETED)
        logger.info("-" * 60)
        logger.info(f"Completed: {completed}/{len(results)} pipelines")
        logger.info(f"Total time: {total_time:.1f}s")
        logger.info("=" * 60)

        # Print LLM stats
        logger.info("\n💰 LLM API Usage Statistics:")
        self.llm_client.print_stats()
