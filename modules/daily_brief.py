"""
Daily Brief Generator v2 — Intelligence-First Daily Report

Orchestrates all briefAI agents to produce a daily intelligence brief:

1. News Pipeline → Top stories (existing)
2. Trend Detector → Emerging cross-source trends + stealth signals (NEW)
3. Narrative Tracker → Active narrative evolution (NEW)
4. Prediction Engine → Tracked predictions (NEW)
5. Alert Engine → Signal alerts (REFOCUSED)
6. Entity Store → Signal heatmap (NEW)

Output: Markdown report using report_template_v2.md
"""

import asyncio
import json
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Template
from loguru import logger

from utils.entity_store import EntityStore
from utils.market_context import MarketContext


class DailyBriefGenerator:
    """
    Generates the daily intelligence brief by running all agents
    and composing their outputs into a single report.

    Usage:
        gen = DailyBriefGenerator()
        report_path = await gen.generate()
    """

    def __init__(
        self,
        template_path: str = "./config/report_template_v2.md",
        output_dir: str = "./data/reports",
        llm_client=None,
    ):
        self.template_path = Path(template_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize LLM client with OpenRouter fallback
        if llm_client:
            self.llm_client = llm_client
        else:
            try:
                from utils.llm_client_enhanced import LLMClient
                self.llm_client = LLMClient(enable_provider_switching=True)
                logger.info("Initialized LLM client with provider switching enabled")
            except Exception as e:
                logger.warning(f"Could not initialize LLM client: {e}")
                self.llm_client = None
        
        self.entity_store = EntityStore()
        self.market_context = MarketContext()

        # Load template
        with open(self.template_path, "r", encoding="utf-8") as f:
            self.template = Template(f.read())

    async def generate(
        self,
        include_news: bool = True,
        include_trends: bool = True,
        include_narratives: bool = True,
        include_predictions: bool = True,
        include_alerts: bool = True,
        top_n_stories: int = 10,
        top_n_entities: int = 15,
    ) -> str:
        """
        Generate the daily intelligence brief.

        Returns: Path to generated report file.
        """
        start_time = time.time()
        report_date = date.today().isoformat()
        logger.info(f"Generating daily brief for {report_date}")

        # Run all data gathering in parallel where possible
        sections = await asyncio.gather(
            self._gather_news(top_n_stories) if include_news else _empty_dict(),
            self._gather_trends() if include_trends else _empty_dict(),
            self._gather_narratives() if include_narratives else _empty_dict(),
            self._gather_predictions() if include_predictions else _empty_dict(),
            self._gather_alerts() if include_alerts else _empty_dict(),
            self._gather_deep_research(),  # CellCog integration
            self._gather_action_predictions(),  # v3.0: Action-based predictions
            self._gather_market_movers(),  # Finnhub + correlator
            self._gather_podcast_insights(),  # Podcast transcripts
            return_exceptions=True,
        )

        # Unpack results (handle failures gracefully)
        news_data = _safe_result(sections[0], "news")
        trend_data = _safe_result(sections[1], "trends")
        narrative_data = _safe_result(sections[2], "narratives")
        prediction_data = _safe_result(sections[3], "predictions")
        alert_data = _safe_result(sections[4], "alerts")
        deep_research_data = _safe_result(sections[5], "deep_research")
        action_prediction_data = _safe_result(sections[6], "action_predictions")
        market_mover_data = _safe_result(sections[7], "market_movers")
        podcast_data = _safe_result(sections[8], "podcast_insights")

        # Gather entity heatmap (sync, fast)
        heatmap = self._build_heatmap(top_n_entities)
        
        # Get current experiment name (for report header)
        experiment_name = None
        try:
            from utils.experiment_manager import get_active_experiment
            exp = get_active_experiment()
            if exp:
                experiment_name = exp.experiment_id
        except Exception:
            pass

        # Generate executive summary
        exec_summary = await self._generate_executive_summary(
            news_data, trend_data, narrative_data, alert_data
        )

        # Compose template data
        template_data = {
            "report_date": report_date,
            "generation_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "experiment_name": experiment_name,
            "executive_summary": exec_summary,
            # Trends
            "emerging_trends": trend_data.get("trends", []),
            "stealth_signals": trend_data.get("stealth_signals", []),
            # News
            "articles_by_category": news_data.get("articles_by_category", {}),
            # Narratives
            "narratives": narrative_data.get("narratives", []),
            # Alerts
            "alerts": alert_data.get("alerts", []),
            # Predictions
            "predictions": prediction_data.get("predictions", []),
            # Action Predictions (v3.0)
            "action_predictions": action_prediction_data.get("action_predictions", []),
            # Heatmap
            "top_entities": heatmap,
            # Market Movers (Finnhub + correlator)
            "market_movers": market_mover_data if market_mover_data.get("correlations") else None,
            # Podcast Intelligence
            "podcast_insights": podcast_data.get("episodes", []),
            # Deep Research (CellCog)
            "deep_research": deep_research_data.get("reports", []),
            "insider_trades": deep_research_data.get("insider_trades", []),
            # Stats
            "total_articles_scraped": news_data.get("total_scraped", 0),
            "total_articles_included": news_data.get("total_included", 0),
            # Delta stats (novelty detection)
            "delta_stats": news_data.get("delta_stats", {}),
        }

        # Render
        report_content = self.template.render(**template_data)

        # Save
        filename = f"daily_brief_{report_date}.md"
        report_path = self.output_dir / filename

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        elapsed = time.time() - start_time
        logger.info(f"Daily brief generated in {elapsed:.1f}s: {report_path}")

        return str(report_path)

    # -------------------------------------------------------------------
    # Section generators
    # -------------------------------------------------------------------

    def _load_all_sources(self, data_dir: Path) -> List[Dict]:
        """
        Load articles from ALL scraped data sources with unified schema.
        Each article gets: title, url, source, summary, published_at,
        _raw_score (0-1 normalized), _source_type, _source_quality.
        """
        all_articles = []
        today_str = datetime.now().strftime("%Y-%m-%d")

        # Source configs: (glob_pattern, container_key, field_mapping, quality_weight)
        # quality_weight: how much we trust this source's editorial signal (0-1)
        source_configs = [
            # TechMeme (actual curated scrape) — highest editorial quality
            # Human-curated by Gabe Rivera, every story is editorially selected
            ("news_signals/techmeme_*.json", "ai_stories", {
                "score_field": "ai_relevance",
                "date_field": "scraped_at",
            }, "techmeme", 0.95),
            # RSS tech news feeds — broad, ai_relevance_score often inflated
            # (31% of articles scored 1.0 including irrelevant ones)
            ("news_signals/tech_news_*.json", "articles", {
                "score_field": "ai_relevance_score",
                "date_field": "published_at",
            }, "tech_rss", 0.60),
            # US tech news (Tavily) — broad, company-focused
            ("alternative_signals/us_tech_news_*.json", "_auto", {
                "score_field": "ai_relevance_score",
                "date_field": "published_date",
            }, "us_tech_news", 0.6),
            # News search (Tavily/SearXNG) — broad web search, scores often inflated
            ("alternative_signals/news_search_*.json", "articles", {
                "score_field": "score",  # use Tavily's relevance score, not keyword score
                "date_field": "published_date",
            }, "news_search", 0.55),
            # HackerNews — developer community signal (points = strong curation)
            ("alternative_signals/hackernews_*.json", "stories", {
                "score_field": "points",
                "score_normalize": "hn_points",  # special: normalize 0-2000 -> 0-1
                "date_field": "created_at",
                "title_field": "title",
            }, "hackernews", 0.95),
            # Blog RSS — curated tech blogs with LLM scoring
            ("alternative_signals/blog_signals_*.json", "posts", {
                "score_field": "llm_score",  # prefer LLM score over keyword score
                "score_fallback": "ai_relevance_score",
                "date_field": "published_at",
                "source_field": "blog",
            }, "blogs", 0.8),
            # Reddit — community signal (noisy but catches trends)
            ("alternative_signals/reddit_*.json", "posts", {
                "score_field": "score",
                "score_normalize": "reddit_score",  # special: normalize 0-5000 -> 0-1
                "date_field": "created_utc",
                "title_field": "title",
                "url_field": "url",
            }, "reddit", 0.5),
            # Newsletters — curated by humans, high signal
            ("newsletter_signals/newsletters_*.json", "posts", {
                "score_field": "influence_score",
                "score_normalize": "linear_100",  # 0-100 -> 0-1
                "date_field": "published_at",
            }, "newsletters", 0.75),
            # Podcasts — high-signal, long-form (credibility_score is 1-10)
            ("alternative_signals/podcasts_*.json", "_auto", {
                "score_field": "credibility_score",
                "score_normalize": "linear_10",  # 1-10 -> 0-1
                "date_field": "date",
                "source_field": "podcast_channel",
            }, "podcasts", 0.7),
            # ArXiv papers — research signal
            ("alternative_signals/arxiv_*.json", "papers", {
                "score_field": "ai_relevance_score",
                "date_field": "published_at",
            }, "arxiv", 0.4),
        ]

        for glob_pat, container_key, field_map, source_type, quality in source_configs:
            try:
                files = sorted(data_dir.glob(glob_pat), reverse=True)
                if not files:
                    continue
                with open(files[0], "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Extract items from container
                if container_key == "_auto":
                    items = data if isinstance(data, list) else data.get("articles", data.get("items", []))
                else:
                    items = data.get(container_key, []) if isinstance(data, dict) else data

                if not isinstance(items, list):
                    continue

                loaded = 0
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    title = item.get("title", item.get("headline", item.get("name", "")))
                    if not title:
                        continue

                    # Normalize score to 0-1
                    raw_score = item.get(field_map.get("score_field", "ai_relevance_score"), None)
                    if raw_score is None and "score_fallback" in field_map:
                        raw_score = item.get(field_map["score_fallback"], 0.5)
                    if raw_score is None:
                        raw_score = 0.5

                    norm_method = field_map.get("score_normalize", "linear_1")
                    if norm_method == "hn_points":
                        score = min(1.0, max(0, float(raw_score)) / 1500)
                    elif norm_method == "reddit_score":
                        score = min(1.0, max(0, float(raw_score)) / 3000)
                    elif norm_method == "linear_100":
                        score = min(1.0, max(0, float(raw_score)) / 100)
                    elif norm_method == "linear_10":
                        score = min(1.0, max(0, float(raw_score)) / 10)
                    else:  # linear_1 — already 0-1 (or close)
                        score = min(1.0, max(0, float(raw_score)))

                    # Build unified article
                    raw_date = item.get(field_map.get("date_field", "published_at"), "")
                    # Format human-readable date
                    readable_date = ""
                    try:
                        if isinstance(raw_date, (int, float)) and raw_date > 1e9:
                            readable_date = datetime.fromtimestamp(raw_date).strftime("%b %d, %Y")
                        elif isinstance(raw_date, str) and raw_date:
                            from dateutil.parser import parse as _parse_date
                            readable_date = _parse_date(raw_date).strftime("%b %d, %Y")
                    except Exception:
                        readable_date = str(raw_date)[:10] if raw_date else ""

                    article = {
                        "title": str(title).strip(),
                        "url": item.get("url", item.get("hn_url", "")),
                        "source": item.get(field_map.get("source_field", "source"), source_type),
                        "summary": item.get("summary", item.get("selftext", item.get("content", "")))[:300],
                        "published_at": raw_date,
                        "published_date": readable_date,
                        "ai_relevance_score": score,
                        "_raw_score": score,
                        "_source_type": source_type,
                        "_source_quality": quality,
                    }
                    # Carry over useful metadata
                    for extra in ["categories", "sentiment_keywords", "evaluation", "ticker",
                                  "podcast_channel", "duration_min", "num_comments", "points",
                                  "subreddit", "blog", "author", "related_count", "related"]:
                        if extra in item:
                            article[extra] = item[extra]

                    # Downgrade arxiv/academic papers that snuck into curated feeds
                    if source_type in ("techmeme", "us_tech_news"):
                        url = article.get("url", "")
                        title_lower = article["title"].lower()
                        is_paper = False
                        if "arxiv.org" in url:
                            is_paper = True
                        elif ":" in title_lower:
                            # Academic paper pattern: "Title Word: Subtitle with Technical Terms"
                            academic_kw = [
                                "neural", "transformer", "optimization", "quantiz",
                                "reinforcement", "adversarial", "topology", "forecasting",
                                "probabilistic", "causal", "graph", "convergence",
                                "multi-", "scalable", "efficient", "robust",
                                "attention", "embedding", "llm", "fine-tun",
                                "benchmark", "dataset", "framework", "architecture",
                                "personali", "decoding", "inference", "bilevel",
                                "cross-", "multi-material", "physics-inform",
                                "preserving", "leveraging", "bridging",
                            ]
                            # If title has colon AND 2+ academic keywords, it's likely a paper
                            matches = sum(1 for kw in academic_kw if kw in title_lower)
                            if matches >= 2:
                                is_paper = True
                        if is_paper:
                            article["_source_quality"] = 0.3
                            article["_source_type"] = "arxiv_via_" + source_type

                    all_articles.append(article)
                    loaded += 1

                logger.info(f"Loaded {loaded} items from {source_type} ({files[0].name})")
            except Exception as e:
                logger.warning(f"Failed to load {source_type}: {e}")

        return all_articles

    def _compute_cross_source_boost(self, articles: List[Dict]) -> Dict[str, float]:
        """
        Count how many different source types mention similar topics.
        Returns a title-key -> boost mapping (0-0.3).
        """
        from collections import defaultdict
        import re

        # Extract keywords from titles (simplified)
        def title_key(t: str) -> str:
            # Normalize: lowercase, strip punctuation, take first 6 significant words
            words = re.sub(r'[^\w\s]', '', t.lower()).split()
            # Remove common stop words
            stops = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'in', 'on', 'at', 'to',
                     'for', 'of', 'with', 'by', 'from', 'and', 'or', 'but', 'not', 'that',
                     'this', 'its', 'it', 'as', 'be', 'has', 'have', 'had', 'will', 'can',
                     'new', 'how', 'what', 'why', 'when', 'who'}
            sig = [w for w in words if w not in stops and len(w) > 2][:6]
            return ' '.join(sig)

        # Map topics -> set of source types
        topic_sources: Dict[str, set] = defaultdict(set)
        title_to_key: Dict[int, str] = {}

        for i, art in enumerate(articles):
            key = title_key(art.get("title", ""))
            if key:
                title_to_key[i] = key
                topic_sources[key].add(art.get("_source_type", ""))

        # Entity-level cross-source detection
        # Only count specific/distinctive entities (not generic ones like "AI", "LLM")
        generic_entities = {
            'the', 'this', 'that', 'with', 'from', 'have', 'will', 'been', 'more',
            'what', 'when', 'how', 'why', 'new', 'first', 'last', 'just', 'like',
            # Generic tech terms that appear in every source
            'model', 'models', 'learning', 'data', 'code', 'open', 'source',
            'agent', 'agents', 'based', 'using', 'large', 'language', 'neural',
            'deep', 'machine', 'training', 'inference', 'benchmark', 'scale',
            'reasoning', 'generation', 'transformer', 'attention', 'optimization',
            # Ubiquitous company names — appear in nearly every source, not a signal
            'openai', 'google', 'microsoft', 'anthropic', 'meta', 'nvidia',
            'amazon', 'apple', 'claude', 'gemini', 'chatgpt',
        }
        entity_sources: Dict[str, set] = defaultdict(set)
        for art in articles:
            src = art.get("_source_type", "")
            # Extract proper nouns / product names (capitalized, 4+ chars)
            entities = set(re.findall(r'\b[A-Z][a-zA-Z]{3,}\b', art.get("title", "")))
            for ent in entities:
                if ent.lower() not in generic_entities:
                    entity_sources[ent.lower()].add(src)

        # Count how many source types each entity appears in
        total_source_types = len(set(a.get("_source_type", "") for a in articles))
        # Entities in too many sources (>60% of all source types) are noise
        ubiquity_cutoff = max(4, int(total_source_types * 0.6))

        # Build boost map
        boost_map: Dict[int, float] = {}
        for i, art in enumerate(articles):
            boost = 0.0
            # Direct title-key match across sources (strongest signal)
            key = title_to_key.get(i, "")
            if key and len(topic_sources.get(key, set())) > 1:
                boost = min(0.25, (len(topic_sources[key]) - 1) * 0.12)
            # Distinctive entity overlap boost
            entities = set(re.findall(r'\b[A-Z][a-zA-Z]{3,}\b', art.get("title", "")))
            for ent in entities:
                if ent.lower() in generic_entities:
                    continue
                n_sources = len(entity_sources.get(ent.lower(), set()))
                # Must appear in 2+ sources but not be ubiquitous
                if 2 <= n_sources < ubiquity_cutoff:
                    ent_boost = min(0.20, (n_sources - 1) * 0.07)
                    boost = max(boost, ent_boost)
            boost_map[i] = boost

        return boost_map

    async def _gather_news(self, top_n: int) -> Dict[str, Any]:
        """
        Gather top stories from ALL scraped data sources.

        Loads articles from 9 source types (TechMeme, HackerNews, blogs,
        Reddit, newsletters, news search, US tech news, podcasts, arxiv),
        normalizes scores, applies cross-source boost, deduplicates, and
        selects the best stories via LLM evaluation.
        """
        result = {"articles_by_category": {}, "total_scraped": 0, "total_included": 0}

        try:
            data_dir = Path("data")

            # ---- Step 1: Load ALL sources ----
            all_articles = self._load_all_sources(data_dir)
            result["total_scraped"] = len(all_articles)
            logger.info(f"Loaded {len(all_articles)} total articles from all sources")

            if not all_articles:
                logger.warning("No scraped articles found for news evaluation")
                return result

            # ---- Step 2: Delta detection (skip duplicates from yesterday) ----
            try:
                from utils.delta_detector import DeltaDetector
                detector = DeltaDetector(similarity_threshold=0.75)

                recent_articles = []
                for days_back in range(1, 4):
                    check_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
                    for pattern in ["news_signals/*_{}.json", "alternative_signals/*_{}.json",
                                    "newsletter_signals/*_{}.json"]:
                        for rf in data_dir.glob(pattern.format(check_date)):
                            try:
                                with open(rf, encoding='utf-8') as f:
                                    rd = json.load(f)
                                    if isinstance(rd, dict):
                                        for key in ["articles", "stories", "posts", "papers"]:
                                            if key in rd:
                                                recent_articles.extend(rd[key])
                                                break
                                    elif isinstance(rd, list):
                                        recent_articles.extend(rd)
                            except Exception:
                                pass
                    if recent_articles:
                        break

                if recent_articles:
                    novel_articles, duplicate_articles = detector.find_novel_stories(
                        all_articles, recent_articles
                    )
                    result["delta_stats"] = {
                        "total": len(all_articles),
                        "novel": len(novel_articles),
                        "duplicates": len(duplicate_articles),
                        "novelty_rate": len(novel_articles) / max(1, len(all_articles))
                    }
                    for article in novel_articles:
                        article["_is_novel"] = True
                    all_articles = novel_articles + duplicate_articles
                    logger.info(f"Delta detection: {len(novel_articles)} novel, {len(duplicate_articles)} duplicates")
            except Exception as e:
                logger.warning(f"Delta detection skipped: {e}")

            # ---- Step 3: Cross-source boost ----
            cross_boost = self._compute_cross_source_boost(all_articles)

            # ---- Step 4: Unified scoring ----
            from datetime import datetime as dt
            now = dt.now()

            scored_articles = []
            for i, article in enumerate(all_articles):
                relevance = article.get("_raw_score", 0.5)
                quality = article.get("_source_quality", 0.5)

                # Recency — strongly penalize old news
                pub_date = article.get("published_at", "")
                try:
                    if pub_date:
                        if isinstance(pub_date, (int, float)):
                            # Unix timestamp (Reddit)
                            parsed = dt.fromtimestamp(pub_date)
                        else:
                            # Handle RFC 2822 dates (e.g., "Wed, 26 Feb 2026 ...")
                            date_str = str(pub_date)
                            try:
                                parsed = dt.fromisoformat(date_str.replace("Z", "+00:00").replace("+00:00", ""))
                            except ValueError:
                                from email.utils import parsedate_to_datetime
                                try:
                                    parsed = parsedate_to_datetime(date_str)
                                except Exception:
                                    from dateutil.parser import parse as _dp
                                    parsed = _dp(date_str)
                            parsed = parsed.replace(tzinfo=None)
                        hours_old = max(0, (now - parsed).total_seconds() / 3600)
                        # Aggressive decay: <24h=1.0, 24-48h=0.5, 48-72h=0.2, >72h=0.0
                        if hours_old <= 24:
                            recency = 1.0
                        elif hours_old <= 48:
                            recency = 0.5
                        elif hours_old <= 72:
                            recency = 0.2
                        else:
                            recency = 0.0
                    else:
                        recency = 0.2
                except Exception:
                    recency = 0.2

                novelty = 0.15 if article.get("_is_novel", False) else 0.0
                cross = cross_boost.get(i, 0.0)

                # Social proof boost: very high engagement = strong community curation
                social_proof = 0.0
                points = article.get("points", 0) or 0
                reddit_score = article.get("score") if article.get("_source_type") == "reddit" else 0
                if isinstance(reddit_score, (int, float)):
                    reddit_score = float(reddit_score)
                else:
                    reddit_score = 0
                if points >= 500:
                    social_proof = min(0.2, (points - 500) / 3000)  # 500->0, 2000->0.16
                elif reddit_score >= 1000:
                    social_proof = min(0.15, (reddit_score - 1000) / 10000)

                # TechMeme related_count boost: stories with many related articles
                # are editorially significant (TechMeme clusters related coverage)
                techmeme_boost = 0.0
                if article.get("_source_type") == "techmeme":
                    related = article.get("related_count", 0) or 0
                    if related >= 1:
                        # 1 related -> 0.10, 3+ -> 0.20, 5+ -> 0.30
                        techmeme_boost = min(0.30, related * 0.06)

                # Combined score: weighted blend
                # relevance*quality gives high-quality sources more weight
                # Recency is heavily weighted — stale news kills the brief
                combined = (relevance * quality * 0.3
                            + recency * 0.35
                            + quality * 0.10
                            + novelty
                            + cross
                            + social_proof
                            + techmeme_boost)

                article["_combined_score"] = combined
                article["_cross_source_boost"] = cross
                scored_articles.append(article)

            # Sort and take top candidates
            scored_articles.sort(key=lambda x: x.get("_combined_score", 0), reverse=True)

            # Cross-day dedup: load previous brief titles to avoid repeating stories
            import re
            prev_titles = set()
            try:
                from datetime import timedelta
                for days_back in range(1, 4):
                    prev_date = (date.today() - timedelta(days=days_back)).isoformat()
                    prev_file = reports_dir / f"daily_brief_{prev_date}.md"
                    if prev_file.exists():
                        content = prev_file.read_text(encoding="utf-8")
                        # Extract titles from markdown links: [Title](url)
                        for m in re.finditer(r'\[([^\]]{10,})\]\(http', content):
                            words = re.sub(r'[^\w\s]', '', m.group(1).lower()).split()
                            prev_titles.add(' '.join(words[:6]))
                if prev_titles:
                    logger.info(f"Cross-day dedup: loaded {len(prev_titles)} titles from previous briefs")
            except Exception as e:
                logger.warning(f"Cross-day dedup failed: {e}")

            # Deduplicate by similar titles (keep highest scored)
            seen_titles = set()
            deduped = []
            for art in scored_articles:
                # Dedup key: first 8 significant words lowercase
                words = re.sub(r'[^\w\s]', '', art.get("title", "").lower()).split()
                key = ' '.join(words[:8])
                short_key = ' '.join(words[:6])
                # Skip if seen in this batch OR in previous briefs
                if key in seen_titles:
                    continue
                if short_key in prev_titles:
                    continue
                seen_titles.add(key)
                deduped.append(art)
            scored_articles = deduped

            # Log top 5 for debugging
            for art in scored_articles[:5]:
                logger.info(
                    f"Top candidate: [{art.get('_source_type')}] "
                    f"score={art.get('_combined_score', 0):.3f} "
                    f"cross={art.get('_cross_source_boost', 0):.2f} "
                    f"title={art.get('title', '?')[:60]}"
                )

            # ---- Step 5: LLM evaluation on top candidates ----
            candidates = scored_articles[:min(40, len(scored_articles))]

            if self.llm_client and len(candidates) > top_n:
                evaluated = await self._evaluate_articles_batch(candidates, top_n)
                if evaluated:
                    result["articles_by_category"] = self._group_articles(evaluated)
                    result["total_included"] = len(evaluated)
                    return result

            # Fallback: just take top by score
            top_articles = candidates[:top_n]
            result["articles_by_category"] = self._group_articles(top_articles)
            result["total_included"] = len(top_articles)

        except Exception as e:
            logger.error(f"Failed to gather news: {e}")

        return result
    
    async def _evaluate_articles_batch(
        self, 
        articles: List[Dict], 
        top_n: int
    ) -> List[Dict]:
        """
        Lightweight LLM evaluation of article batch.
        Uses OpenRouter fallback if Kimi is rate-limited.
        """
        try:
            # Build evaluation prompt
            article_summaries = []
            for i, article in enumerate(articles[:30]):  # Top 30 candidates for LLM eval
                title = article.get("title", "No title")[:100]
                source = article.get("source", "Unknown")
                src_type = article.get("_source_type", "")
                summary = article.get("summary", "")[:150]
                # Add engagement signal for community-sourced articles
                engagement = ""
                pts = article.get("points", 0)
                if pts and int(pts) > 100:
                    engagement = f" [HN {pts} pts]"
                comments = article.get("num_comments", 0)
                if comments and int(comments) > 50:
                    engagement += f" [{comments} comments]"
                article_summaries.append(f"{i+1}. [{source}]{engagement} {title}\n   {summary}")
            
            prompt = f"""Evaluate these AI/tech news articles for a daily intelligence brief.
Score each 1-10 based on: Impact (industry significance), Novelty (new information), Actionability (investment/business relevance).

Articles:
{chr(10).join(article_summaries)}

Return JSON with article numbers and scores:
{{"scores": [{{"id": 1, "score": 8, "category": "Product Launch"}}, ...]}}

Only include articles scoring 6+. Categories: Product Launch, Funding, Partnership, Research, Regulation, Earnings, Other."""

            # Try to get evaluation from LLM
            from utils.llm_client_enhanced import LLMClient
            client = self.llm_client or LLMClient()
            
            response = client.chat_structured(
                system_prompt="You are an AI news analyst. Evaluate articles concisely. Return valid JSON only.",
                user_message=prompt,
                temperature=0.3,
                max_tokens=1000
            )
            
            if response and "scores" in response:
                # Map scores back to articles
                score_map = {s["id"]: s for s in response["scores"]}
                evaluated = []
                for i, article in enumerate(articles[:30]):
                    if (i + 1) in score_map:
                        score_data = score_map[i + 1]
                        article["evaluation"] = {
                            "score": score_data.get("score", 5),
                            "recommended_category": score_data.get("category", "General")
                        }
                        article["weighted_score"] = score_data.get("score", 5)
                        evaluated.append(article)
                
                # Sort by score and return top_n
                evaluated.sort(key=lambda x: x.get("weighted_score", 0), reverse=True)
                return evaluated[:top_n]
                
        except Exception as e:
            logger.warning(f"LLM evaluation failed, using pre-scored articles: {e}")
        
        # Fallback: return top articles without LLM evaluation
        return articles[:top_n]

    async def _gather_trends(self) -> Dict[str, Any]:
        """Run Trend Detector agent."""
        try:
            from agents.trend_detector import TrendDetectorAgent
            from agents.base import AgentInput

            agent = TrendDetectorAgent(llm_client=self.llm_client)
            input_data = AgentInput(
                entity_name="",
                context={"time_window_days": 14, "min_sources": 2},
            )
            output = await agent.run(input_data)

            if output.status == "completed" and output.data:
                data = output.data
                # Normalize trend format for template
                trends = []
                raw_trends = data.get("emerging_trends", [])
                if isinstance(raw_trends, list):
                    for t in raw_trends[:5]:
                        if isinstance(t, dict):
                            trends.append({
                                "name": t.get("trend_name") or t.get("entity", "Unknown"),
                                "score": t.get("emergence_score", 0),
                                "velocity": t.get("velocity_label") or t.get("velocity", "unknown"),
                                "source_count": t.get("source_diversity", 0),
                                "narrative": t.get("narrative", ""),
                                "evidence": t.get("evidence_chain", []),
                                "prediction": t.get("prediction", ""),
                            })

                stealth = []
                raw_stealth = data.get("stealth_signals", [])
                if isinstance(raw_stealth, list):
                    for s in raw_stealth[:5]:
                        if isinstance(s, dict):
                            stealth.append({
                                "entity": s.get("entity", "Unknown"),
                                "description": s.get("description", ""),
                            })

                return {"trends": trends, "stealth_signals": stealth}
        except Exception as e:
            logger.error(f"Trend detection failed: {e}")

        return {"trends": [], "stealth_signals": []}

    async def _gather_narratives(self) -> Dict[str, Any]:
        """Run Narrative Tracker agent."""
        try:
            from agents.narrative_tracker import NarrativeTrackerAgent
            from agents.base import AgentInput

            agent = NarrativeTrackerAgent(llm_client=self.llm_client)
            input_data = AgentInput(
                entity_name="auto",
                context={"topic": "auto", "time_window_days": 30},
            )
            output = await agent.run(input_data)

            if output.status == "completed" and output.data:
                data = output.data
                narratives = []
                raw = data.get("narratives", [])
                if isinstance(raw, list):
                    for n in raw[:5]:
                        if isinstance(n, dict):
                            narratives.append({
                                "name": n.get("name") or n.get("topic", "Unknown"),
                                "phase": n.get("phase", "unknown"),
                                "momentum": n.get("momentum", "unknown"),
                                "mentions_7d": n.get("mention_trend", {}).get("7d", 0),
                                "mentions_30d": n.get("mention_trend", {}).get("30d", 0),
                                "summary": n.get("outlook") or n.get("narrative", ""),
                                "inflection_points": n.get("inflection_points", []),
                                "outlook": n.get("outlook", ""),
                            })
                return {"narratives": narratives}
        except Exception as e:
            logger.error(f"Narrative tracking failed: {e}")

        return {"narratives": []}

    async def _gather_predictions(self) -> Dict[str, Any]:
        """Gather active predictions from predictions.db."""
        predictions = []
        try:
            import sqlite3
            pred_db = Path("data/predictions.db")
            if pred_db.exists():
                conn = sqlite3.connect(str(pred_db))
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT predicted_outcome, confidence, horizon_date, status, entity_name
                    FROM predictions
                    WHERE status = 'pending'
                    ORDER BY confidence DESC
                    LIMIT 10
                """)
                for row in cursor.fetchall():
                    predictions.append({
                        "statement": f"{row['entity_name']}: {row['predicted_outcome']}"[:120],
                        "confidence": int(float(row["confidence"]) * 100),
                        "check_date": (row["horizon_date"] or "")[:10],
                        "status": row["status"],
                    })
                conn.close()
        except Exception as e:
            logger.debug(f"Predictions lookup: {e}")

        return {"predictions": predictions}

    async def _gather_action_predictions(self) -> Dict[str, Any]:
        """Gather action-based predictions from latest hypotheses (v3.0)."""
        action_predictions = []
        try:
            # Load latest hypotheses file
            hypotheses_dir = Path("data/insights")
            today = date.today().isoformat()
            hypotheses_file = hypotheses_dir / f"hypotheses_{today}.json"
            
            if hypotheses_file.exists():
                with open(hypotheses_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Collect all action predictions from bundles
                for bundle in data.get('bundles', []):
                    action_bundle = bundle.get('action_bundle', {})
                    for ap in action_bundle.get('action_predictions', []):
                        action_predictions.append({
                            'entity': ap.get('entity', 'Unknown'),
                            'event_type': ap.get('event_type', ''),
                            'event_display_name': ap.get('event_display_name', ''),
                            'probability': ap.get('probability', 0),
                            'timeframe_days': ap.get('timeframe_days', 30),
                            'source_pressure': ap.get('source_pressure', ''),
                            'counterparty_type': ap.get('counterparty_type'),
                            'direction': ap.get('direction'),
                            'note': ap.get('note'),
                        })
                
                # Sort by probability and limit
                action_predictions.sort(key=lambda x: x['probability'], reverse=True)
                action_predictions = action_predictions[:10]
                
                logger.info(f"Loaded {len(action_predictions)} action predictions")
        except Exception as e:
            logger.debug(f"Action predictions lookup: {e}")
        
        return {"action_predictions": action_predictions}

    async def _gather_alerts(self) -> Dict[str, Any]:
        """Run intelligence alert scanner and gather results."""
        alerts = []
        try:
            from utils.intelligence_alerts import IntelligenceAlertScanner

            # Run scanner — generates new alerts from current signals
            scanner = IntelligenceAlertScanner(entity_store=self.entity_store)
            new_alerts = scanner.scan_all(top_n=50)

            # Also get recent alerts from DB (last 24h)
            recent = scanner.engine.get_recent_alerts(hours=24, limit=20)

            for alert in recent:
                alerts.append({
                    "type": alert.alert_type.value,
                    "severity": alert.severity.value,
                    "message": alert.message,
                })
        except Exception as e:
            logger.warning(f"Intelligence alert scan failed: {e}")
            # Fallback: try old alerts.db
            try:
                import sqlite3
                alert_db = Path("data/alerts.db")
                if alert_db.exists():
                    conn = sqlite3.connect(str(alert_db))
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute("""
                        SELECT alert_type, severity, message, entity_name
                        FROM alerts
                        WHERE first_detected >= datetime('now', '-24 hours')
                        ORDER BY severity DESC
                        LIMIT 10
                    """)
                    for row in cursor.fetchall():
                        alerts.append({
                            "type": row["alert_type"],
                            "severity": row["severity"],
                            "message": f"{row['entity_name']}: {row['message']}",
                        })
                    conn.close()
            except Exception:
                pass

        return {"alerts": alerts}

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def _build_heatmap(self, top_n: int) -> List[Dict[str, Any]]:
        """Build signal heatmap from top entities."""
        heatmap = []

        top = self.entity_store.list_top_entities(limit=top_n)

        # Collect all momentum values to compute relative ranking
        all_momentum = []
        entity_data = []
        for entity in top:
            profile = self.entity_store.get_signal_profile(entity.canonical_name)
            velocity = self.entity_store.get_mention_velocity(entity.canonical_name)

            composite = entity.composite_score
            media = profile.get("media_score") if profile else None
            momentum_7d = velocity.get("7d", 0)
            momentum_30d = velocity.get("30d", 0)
            sources = velocity.get("source_diversity_30d", 0)

            all_momentum.append(momentum_7d)
            entity_data.append({
                "name": entity.canonical_name,
                "composite": composite,
                "media": media,
                "momentum_7d": momentum_7d,
                "momentum_30d": momentum_30d,
                "sources": sources,
            })

        # Compute percentile-based trend labels
        if all_momentum:
            sorted_m = sorted(all_momentum)
            p75 = sorted_m[int(len(sorted_m) * 0.75)] if len(sorted_m) > 3 else max(sorted_m)
            p25 = sorted_m[int(len(sorted_m) * 0.25)] if len(sorted_m) > 3 else min(sorted_m)
            median = sorted_m[len(sorted_m) // 2]
        else:
            p75 = p25 = median = 0

        for ed in entity_data:
            m7 = ed["momentum_7d"]
            m30 = ed["momentum_30d"]
            sources = ed["sources"]

            # Trend based on relative position + source diversity
            if m7 > p75 and sources >= 3:
                trend = "🔥 surging"
            elif m7 > p75:
                trend = "📈 hot"
            elif m7 > median:
                trend = "📈 rising"
            elif m7 > p25:
                trend = "➡️ steady"
            elif m7 > 0:
                trend = "📉 cooling"
            else:
                trend = "⬜ quiet"

            heatmap.append({
                "name": ed["name"],
                "composite": f"{ed['composite']:.1f}" if ed['composite'] else "—",
                "media": f"{ed['media']:.1f}" if ed['media'] else "—",
                "momentum": m7,
                "source_count": sources,
                "trend": trend,
            })

        return heatmap

    def _group_articles(self, articles: List[Dict]) -> Dict[str, List[Dict]]:
        """Group articles by category."""
        grouped: Dict[str, List[Dict]] = {}
        for article in articles:
            category = "General"
            if "evaluation" in article:
                category = article["evaluation"].get("recommended_category", "General")
            grouped.setdefault(category, []).append(article)
        return grouped

    async def _generate_executive_summary(
        self,
        news: Dict,
        trends: Dict,
        narratives: Dict,
        alerts: Dict,
    ) -> str:
        """Generate executive summary using LLM or fallback to template."""
        # Build context for summary
        parts = []

        # Trend highlights
        trend_list = trends.get("trends", [])
        if trend_list:
            parts.append(f"**Emerging Trends:** {len(trend_list)} cross-source trends detected.")
            top_trend = trend_list[0]
            parts.append(
                f"Top emerging: **{top_trend.get('name', '?')}** "
                f"(score {top_trend.get('score', 0)}, {top_trend.get('velocity', '?')})."
            )

        # Stealth signals
        stealth = trends.get("stealth_signals", [])
        if stealth:
            parts.append(f"**Stealth Signals:** {len(stealth)} entities with non-news activity but zero media coverage.")

        # Narrative updates
        nar_list = narratives.get("narratives", [])
        if nar_list:
            accelerating = [n for n in nar_list if n.get("momentum") == "accelerating"]
            if accelerating:
                names = ", ".join(n["name"] for n in accelerating[:3])
                parts.append(f"**Accelerating Narratives:** {names}")

        # Alert count
        alert_list = alerts.get("alerts", [])
        if alert_list:
            critical = [a for a in alert_list if a.get("severity") in ("critical", "high")]
            if critical:
                parts.append(f"**⚠️ {len(critical)} high-priority alerts** in the last 24 hours.")

        # News count
        included = news.get("total_included", 0)
        if included:
            parts.append(f"**{included} top stories** selected from today's scrape.")

        if parts:
            return "\n\n".join(parts)

        return "No significant signals detected today."

    async def _gather_market_movers(self) -> Dict[str, Any]:
        """Gather Finnhub market data + news correlations."""
        result = {}
        today_str = date.today().isoformat()
        data_dir = Path("data")

        try:
            # Load Finnhub data for sector performance + TA
            finnhub_path = data_dir / "market_signals" / f"finnhub_{today_str}.json"
            finnhub_data = {}
            if finnhub_path.exists():
                with open(finnhub_path, "r", encoding="utf-8") as f:
                    finnhub_data = json.load(f)

            # Sector performance from Finnhub
            if finnhub_data.get("stocks"):
                sectors = {
                    "Big Tech": ['NVDA', 'MSFT', 'GOOGL', 'META', 'AMZN', 'AAPL'],
                    "Semis": ['AMD', 'INTC', 'AVGO', 'QCOM', 'ARM', 'TSM', 'ASML', 'MRVL'],
                    "AI Pure-play": ['AI', 'PLTR', 'PATH', 'SNOW', 'DDOG', 'CRWD', 'UPST'],
                    "Enterprise": ['CRM', 'ORCL', 'IBM', 'NOW', 'ADBE', 'WDAY'],
                }
                quote_map = {q["ticker"]: q for q in finnhub_data["stocks"]}
                sector_perf = {}
                for sector, tickers in sectors.items():
                    changes = [quote_map[t]["change_pct"] for t in tickers if t in quote_map]
                    if changes:
                        sector_perf[sector] = sum(changes) / len(changes)
                result["sector_performance"] = sector_perf

                # TA data keyed by ticker
                ta_map = finnhub_data.get("technical_analysis", {})
            else:
                ta_map = {}

            # Load correlations
            corr_path = data_dir / "market_correlations" / f"market_news_{today_str}.json"
            if corr_path.exists():
                with open(corr_path, "r", encoding="utf-8") as f:
                    corr_data = json.load(f)
                correlations = corr_data.get("correlations", [])
                # Enrich with TA from Finnhub
                for c in correlations:
                    ta = ta_map.get(c["ticker"])
                    if ta:
                        c["technical"] = {
                            "rsi": ta.get("rsi"),
                            "ta_signals": ta.get("ta_signals", []),
                        }
                result["correlations"] = correlations
                result["summary"] = corr_data.get("summary", {})
            else:
                result["correlations"] = []

        except Exception as e:
            logger.warning(f"Failed to gather market movers: {e}")
            result["correlations"] = []

        return result

    async def _gather_podcast_insights(self) -> Dict[str, Any]:
        """Gather podcast transcript insights."""
        result = {"episodes": []}
        today_str = date.today().isoformat()
        data_dir = Path("data/alternative_signals")

        try:
            podcast_path = data_dir / f"podcasts_{today_str}.json"
            if not podcast_path.exists():
                # Check yesterday
                yesterday = (date.today() - timedelta(days=1)).isoformat()
                podcast_path = data_dir / f"podcasts_{yesterday}.json"
            
            if podcast_path.exists():
                with open(podcast_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                episodes = data if isinstance(data, list) else data.get("episodes", [])
                # Sort by duration (longer = more substance)
                episodes.sort(key=lambda e: e.get("duration_min", 0), reverse=True)
                result["episodes"] = episodes
                logger.info(f"Loaded {len(episodes)} podcast episodes")
        except Exception as e:
            logger.warning(f"Failed to gather podcast insights: {e}")

        return result

    async def _gather_deep_research(self) -> Dict[str, Any]:
        """
        Gather CellCog deep research reports and OpenInsider signals.
        """
        result = {"reports": [], "insider_trades": []}
        today = date.today()
        today_str = today.isoformat()
        # Match today and recent dates (up to 2 days back for freshness)
        date_patterns = []
        for days_back in range(3):  # today, yesterday, day before
            d = today - timedelta(days=days_back)
            d_str = d.isoformat()
            date_patterns.append(d_str)                                    # 2026-02-14
            date_patterns.append(d_str.replace("-", ""))                   # 20260214
            date_patterns.append(d.strftime("%b_%d_%Y").lower())           # feb_14_2026
            date_patterns.append(f"{d.strftime('%b').lower()}_{d.day}_{d.year}")  # feb_14_2026
            # Note: intentionally NOT matching month-only patterns like "feb_2026"
            # to avoid loading stale reports from earlier in the month
        month_patterns = date_patterns  # keep variable name for downstream compat
        
        try:
            # Load CellCog research reports from ~/.cellcog/chats/
            # Only match files from recent dates (not stale month-wide patterns)
            cellcog_dir = Path.home() / ".cellcog" / "chats"
            if cellcog_dir.exists():
                for chat_dir in cellcog_dir.iterdir():
                    if chat_dir.is_dir():
                        for json_file in chat_dir.glob("*.json"):
                            try:
                                # Check if file matches recent date patterns
                                fname_lower = json_file.name.lower()
                                matches_recent = any(p in fname_lower for p in month_patterns)
                                if not matches_recent:
                                    continue
                                    
                                with open(json_file, "r", encoding="utf-8") as f:
                                    data = json.load(f)
                                    
                                if isinstance(data, dict) and "topic" in data:
                                    report = {
                                        "topic": data.get("topic", "Unknown"),
                                        "summary": data.get("summary", ""),
                                        "key_developments": data.get("key_developments", [])[:5],
                                        "investment_signals": data.get("investment_signals", [])[:5],
                                        "analyst_outlook": data.get("analyst_outlook", "")[:500],
                                    }
                                    result["reports"].append(report)
                                    logger.info(f"Loaded CellCog report: {data.get('topic', 'Unknown')[:50]}")
                            except Exception as e:
                                logger.debug(f"Could not parse {json_file}: {e}")
            
            # Load insider trading signals
            insider_dir = Path("data/insider_signals")
            if insider_dir.exists():
                insider_files = sorted(insider_dir.glob(f"insider_trades_{today}.json"), reverse=True)
                if insider_files:
                    with open(insider_files[0], "r", encoding="utf-8") as f:
                        data = json.load(f)
                        
                    signals = data.get("signals", [])
                    # Get top bullish signals (executives buying)
                    top_signals = [
                        s for s in signals 
                        if s.get("score", 0) >= 0.7 and s.get("trade_type") == "Purchase"
                    ][:10]
                    
                    result["insider_trades"] = top_signals
                    result["insider_summary"] = data.get("summary", {})
                    logger.info(f"Loaded {len(top_signals)} top insider signals")
                    
        except Exception as e:
            logger.error(f"Error gathering deep research: {e}")
        
        return result

    async def generate_and_get_content(self, **kwargs) -> str:
        """Generate brief and return content string (instead of file path)."""
        path = await self.generate(**kwargs)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _empty_dict():
    return {}


def _safe_result(result, section_name: str) -> Dict[str, Any]:
    """Handle exceptions from asyncio.gather."""
    if isinstance(result, Exception):
        logger.error(f"Section '{section_name}' failed: {result}")
        return {}
    return result if isinstance(result, dict) else {}
