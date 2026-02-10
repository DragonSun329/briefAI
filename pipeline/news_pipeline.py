"""
News Pipeline — reference implementation of BasePipeline.

Wraps the existing scrape → filter → evaluate → paraphrase → format flow
as a proper BasePipeline subclass with streaming events.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from loguru import logger

from pipeline.base import (
    BasePipeline,
    EventType,
    PipelineConfig,
    PipelineEvent,
    PipelineResult,
    PipelineStatus,
    StageResult,
)


class NewsPipeline(BasePipeline):
    """
    General AI industry news pipeline.

    Stages: scrape → tier1_filter → tier2_batch → tier3_evaluate → paraphrase → format
    """

    def __init__(
        self,
        sources_file: str = "sources.json",
        categories_file: str = "categories.json",
        output_prefix: str = "ai_briefing",
        llm_client=None,
        cache_manager=None,
        pipeline_config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self._sources_file = sources_file
        self._categories_file = categories_file
        self._output_prefix = output_prefix
        self._pipeline_config = pipeline_config or {}

        # Lazy-init shared resources (passed or created on first run)
        self._llm_client = llm_client
        self._cache_manager = cache_manager

    @property
    def pipeline_id(self) -> str:
        return "news"

    @property
    def display_name(self) -> str:
        return "AI Industry News"

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    async def run(self, config: PipelineConfig) -> AsyncGenerator[PipelineEvent, None]:
        start_time = time.time()
        stages: List[StageResult] = []
        config_dir = Path(__file__).parent.parent / "config"

        # Ensure shared resources
        self._ensure_resources()

        # Load categories
        categories_path = config_dir / self._categories_file
        with open(categories_path, "r", encoding="utf-8") as f:
            cat_config = json.load(f)
        all_categories = cat_config.get("categories", [])
        default_ids = cat_config.get("default_categories", [])

        if config.categories:
            selected = [c for c in all_categories if c["id"] in config.categories]
        else:
            selected = [c for c in all_categories if c["id"] in default_ids]
        if not selected:
            selected = all_categories[:4]

        yield self._log(f"Categories: {[c['name'] for c in selected]}")

        # ---- Stage 1: Scrape ----
        yield self._stage_start("scrape", "Scraping articles from sources...")
        stage_t0 = time.time()
        self._check_cancelled()

        from modules.web_scraper import WebScraper

        scraper = WebScraper(
            cache_manager=self._cache_manager,
            sources_config=str(config_dir / self._sources_file),
        )
        category_ids = [c["id"] for c in selected]
        articles = scraper.scrape_all(
            categories=category_ids,
            days_back=config.days_back,
            use_cache=True,
        )
        stage_dur = time.time() - stage_t0
        stages.append(StageResult("scrape", PipelineStatus.COMPLETED, 0, len(articles), stage_dur))
        yield self._stage_end("scrape", 0, len(articles), stage_dur, f"Scraped {len(articles)} articles")
        yield self._metric("articles_scraped", len(articles), "scrape")

        if not articles:
            result = PipelineResult(
                pipeline_id=self.pipeline_id,
                status=PipelineStatus.FAILED,
                error="No articles scraped",
                execution_time=time.time() - start_time,
                stages=stages,
            )
            yield self._result(result)
            return

        # ---- Stage 2: Tier 1 filter ----
        yield self._stage_start("tier1_filter", "Pre-filtering articles...")
        stage_t0 = time.time()
        self._check_cancelled()

        from utils.article_filter import ArticleFilter

        threshold = self._pipeline_config.get("tier1_threshold", 3.0)
        article_filter = ArticleFilter(score_threshold=float(threshold))
        tier1 = article_filter.filter_articles(articles=articles, categories=selected)
        stage_dur = time.time() - stage_t0
        stages.append(StageResult("tier1_filter", PipelineStatus.COMPLETED, len(articles), len(tier1), stage_dur))
        yield self._stage_end("tier1_filter", len(articles), len(tier1), stage_dur)
        yield self._metric("tier1_passed", len(tier1), "tier1_filter")

        if not tier1:
            result = PipelineResult(
                pipeline_id=self.pipeline_id,
                status=PipelineStatus.FAILED,
                articles_scraped=len(articles),
                error="No articles passed Tier 1 filter",
                execution_time=time.time() - start_time,
                stages=stages,
            )
            yield self._result(result)
            return

        # ---- Stage 3: Tier 2 batch evaluation ----
        yield self._stage_start("tier2_batch", "Batch evaluating articles...")
        stage_t0 = time.time()
        self._check_cancelled()

        from modules.batch_evaluator import BatchEvaluator

        batch_eval = BatchEvaluator(llm_client=self._llm_client, batch_size=5, pass_score=6.0)
        tier2 = batch_eval.evaluate_batch(articles=tier1, categories=selected)
        if not tier2:
            logger.warning("No articles passed Tier 2, using top Tier 1")
            tier2 = tier1[: config.top_n]
        stage_dur = time.time() - stage_t0
        stages.append(StageResult("tier2_batch", PipelineStatus.COMPLETED, len(tier1), len(tier2), stage_dur))
        yield self._stage_end("tier2_batch", len(tier1), len(tier2), stage_dur)

        # ---- Stage 4: Tier 3 full evaluation ----
        yield self._stage_start("tier3_evaluate", "Full evaluation...")
        stage_t0 = time.time()
        self._check_cancelled()

        from modules.news_evaluator import NewsEvaluator

        evaluator = NewsEvaluator(llm_client=self._llm_client)
        evaluated = evaluator.evaluate_articles(articles=tier2, categories=selected, top_n=config.top_n)
        stage_dur = time.time() - stage_t0
        stages.append(StageResult("tier3_evaluate", PipelineStatus.COMPLETED, len(tier2), len(evaluated), stage_dur))
        yield self._stage_end("tier3_evaluate", len(tier2), len(evaluated), stage_dur)

        if not evaluated:
            result = PipelineResult(
                pipeline_id=self.pipeline_id,
                status=PipelineStatus.FAILED,
                articles_scraped=len(articles),
                error="No articles passed Tier 3 evaluation",
                execution_time=time.time() - start_time,
                stages=stages,
            )
            yield self._result(result)
            return

        # ---- Stage 5: Paraphrase ----
        yield self._stage_start("paraphrase", "Paraphrasing selected articles...")
        stage_t0 = time.time()
        self._check_cancelled()

        from modules.article_paraphraser import ArticleParaphraser

        paraphraser = ArticleParaphraser(llm_client=self._llm_client)
        paraphrased = paraphraser.paraphrase_articles(articles=evaluated)
        stage_dur = time.time() - stage_t0
        stages.append(StageResult("paraphrase", PipelineStatus.COMPLETED, len(evaluated), len(paraphrased), stage_dur))
        yield self._stage_end("paraphrase", len(evaluated), len(paraphrased), stage_dur)

        # ---- Stage 6: Format report ----
        yield self._stage_start("format", "Generating report...")
        stage_t0 = time.time()
        self._check_cancelled()

        from modules.report_formatter import ReportFormatter

        formatter = ReportFormatter(llm_client=self._llm_client, output_dir="./data/reports")
        report_period = config.target_date.strftime("%Y年%m月%d日")
        report_path = formatter.generate_report(
            articles=paraphrased,
            categories=selected,
            report_period=report_period,
            report_type="daily",
        )
        stage_dur = time.time() - stage_t0
        stages.append(StageResult("format", PipelineStatus.COMPLETED, len(paraphrased), 1, stage_dur))
        yield self._stage_end("format", len(paraphrased), 1, stage_dur, f"Report: {report_path}")

        # ---- Done ----
        total_time = time.time() - start_time
        result = PipelineResult(
            pipeline_id=self.pipeline_id,
            status=PipelineStatus.COMPLETED,
            report_path=report_path,
            articles_scraped=len(articles),
            articles_selected=len(evaluated),
            execution_time=total_time,
            stages=stages,
            metadata={
                "tier1_passed": len(tier1),
                "tier2_passed": len(tier2),
                "categories": [c["name"] for c in selected],
            },
        )
        yield self._result(result)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_resources(self):
        """Lazily initialize shared resources if not provided."""
        if self._llm_client is None:
            from utils.llm_client_enhanced import LLMClient
            self._llm_client = LLMClient()

        if self._cache_manager is None:
            from utils.cache_manager import CacheManager
            self._cache_manager = CacheManager()
