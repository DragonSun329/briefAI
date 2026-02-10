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
            return_exceptions=True,
        )

        # Unpack results (handle failures gracefully)
        news_data = _safe_result(sections[0], "news")
        trend_data = _safe_result(sections[1], "trends")
        narrative_data = _safe_result(sections[2], "narratives")
        prediction_data = _safe_result(sections[3], "predictions")
        alert_data = _safe_result(sections[4], "alerts")
        deep_research_data = _safe_result(sections[5], "deep_research")

        # Gather entity heatmap (sync, fast)
        heatmap = self._build_heatmap(top_n_entities)

        # Generate executive summary
        exec_summary = await self._generate_executive_summary(
            news_data, trend_data, narrative_data, alert_data
        )

        # Compose template data
        template_data = {
            "report_date": report_date,
            "generation_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
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
            # Heatmap
            "top_entities": heatmap,
            # Deep Research (CellCog)
            "deep_research": deep_research_data.get("reports", []),
            "insider_trades": deep_research_data.get("insider_trades", []),
            # Stats
            "total_articles_scraped": news_data.get("total_scraped", 0),
            "total_articles_included": news_data.get("total_included", 0),
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

    async def _gather_news(self, top_n: int) -> Dict[str, Any]:
        """
        Gather top stories from scraped news data.
        
        Loads recent scraped articles and evaluates them using LLM.
        Falls back to OpenRouter if Kimi is rate-limited.
        """
        result = {"articles_by_category": {}, "total_scraped": 0, "total_included": 0}
        
        try:
            # Load most recent scraped news
            all_articles = []
            data_dir = Path("data")
            
            # Check news_signals (RSS feeds, newsletters)
            news_files = sorted(data_dir.glob("news_signals/tech_news_*.json"), reverse=True)
            if news_files:
                with open(news_files[0], "r", encoding="utf-8") as f:
                    data = json.load(f)
                    articles = data.get("articles", [])
                    all_articles.extend(articles)
                    logger.info(f"Loaded {len(articles)} articles from {news_files[0].name}")
            
            # Check alternative_signals for US tech news
            us_news_files = sorted(data_dir.glob("alternative_signals/us_tech_news_*.json"), reverse=True)
            if us_news_files:
                with open(us_news_files[0], "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # This file has a different structure - list of article dicts
                    if isinstance(data, list):
                        all_articles.extend(data)
                    elif isinstance(data, dict) and "articles" in data:
                        all_articles.extend(data["articles"])
                    logger.info(f"Loaded articles from {us_news_files[0].name}")
            
            result["total_scraped"] = len(all_articles)
            
            if not all_articles:
                logger.warning("No scraped articles found for news evaluation")
                return result
            
            # Pre-filter by AI relevance score if available
            scored_articles = []
            for article in all_articles:
                score = article.get("ai_relevance_score", 0.5)
                if score >= 0.3:  # Basic relevance threshold
                    article["_relevance"] = score
                    scored_articles.append(article)
            
            # Sort by relevance and recency
            from datetime import datetime as dt
            now = dt.now()
            for article in scored_articles:
                pub_date = article.get("published_at", "")
                try:
                    if pub_date:
                        parsed = dt.fromisoformat(pub_date.replace("Z", "+00:00").replace("+00:00", ""))
                        hours_old = (now - parsed.replace(tzinfo=None)).total_seconds() / 3600
                        recency_boost = max(0, 1 - (hours_old / 72))  # Decay over 72h
                    else:
                        recency_boost = 0.5
                except:
                    recency_boost = 0.5
                article["_combined_score"] = article["_relevance"] * 0.6 + recency_boost * 0.4
            
            # Sort by combined score
            scored_articles.sort(key=lambda x: x.get("_combined_score", 0), reverse=True)
            
            # Take top candidates for LLM evaluation (if we have an LLM client)
            candidates = scored_articles[:min(30, len(scored_articles))]
            
            if self.llm_client and len(candidates) > top_n:
                # Run lightweight batch evaluation
                evaluated = await self._evaluate_articles_batch(candidates, top_n)
                if evaluated:
                    result["articles_by_category"] = self._group_articles(evaluated)
                    result["total_included"] = len(evaluated)
                    return result
            
            # Fallback: just take top by score without LLM
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
            for i, article in enumerate(articles[:20]):  # Limit to 20 for token efficiency
                title = article.get("title", "No title")[:100]
                source = article.get("source", "Unknown")
                summary = article.get("summary", "")[:150]
                article_summaries.append(f"{i+1}. [{source}] {title}\n   {summary}")
            
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
                for i, article in enumerate(articles[:20]):
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

    async def _gather_deep_research(self) -> Dict[str, Any]:
        """
        Gather CellCog deep research reports and OpenInsider signals.
        """
        result = {"reports": [], "insider_trades": []}
        today = date.today()
        today_str = today.isoformat()
        # Also match patterns like "feb_2026" or "feb_9_2026"
        month_patterns = [
            today.strftime("%b_%Y").lower(),  # feb_2026
            today.strftime("%b_%d_%Y").lower(),  # feb_09_2026
            f"{today.strftime('%b').lower()}_{today.day}_{today.year}",  # feb_9_2026
            today_str,  # 2026-02-09
            today_str.replace("-", ""),  # 20260209
        ]
        
        try:
            # Load CellCog research reports
            cellcog_dir = Path.home() / ".cellcog" / "chats"
            if cellcog_dir.exists():
                for chat_dir in cellcog_dir.iterdir():
                    if chat_dir.is_dir():
                        for json_file in chat_dir.glob("*.json"):
                            try:
                                # Check if file matches any of today's patterns
                                fname_lower = json_file.name.lower()
                                matches_today = any(p in fname_lower for p in month_patterns)
                                if not matches_today:
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
