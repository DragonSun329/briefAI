"""
Trend Detector Agent — Cross-Source Emerging Trend Detection

The core differentiator of briefAI. Detects emerging trends BEFORE they're
obvious by cross-referencing signals across multiple source types.

Key insight: A GitHub repo trending alone means nothing. A GitHub repo trending
+ arxiv paper + 3 news articles + hiring signals = something real is happening.

Bloomberg cannot do this. ValueCell cannot do this. This is our moat.
"""

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from agents.base import AgentCard, AgentInput, AgentOutput, BaseAgent
from utils.entity_store import EntityStore, EntityMention


# ---------------------------------------------------------------------------
# Scoring models
# ---------------------------------------------------------------------------

# Source types and their signal weights
SOURCE_WEIGHTS = {
    "news": 1.0,           # News articles (baseline)
    "github": 1.2,         # GitHub activity (leading indicator)
    "huggingface": 1.2,    # HuggingFace models/datasets
    "arxiv": 1.3,          # Research papers (earliest signal)
    "reddit": 0.8,         # Reddit discussion
    "hackernews": 0.9,     # HN discussion (higher quality)
    "prediction_market": 1.1,  # Prediction markets
    "hiring": 1.4,         # Job postings (resource commitment = high signal)
    "patent": 1.5,         # Patent filings (strategic intent = highest signal)
    "podcast": 0.7,        # Podcasts
    "newsletter": 0.9,     # Newsletters
    "policy": 1.3,         # Policy/regulation
    "earnings": 1.1,       # Earnings mentions
    "social": 0.6,         # General social media
    "product_hunt": 0.8,   # Product launches
}

# Minimum source types to consider a "real" cross-source trend
MIN_SOURCE_DIVERSITY = 2


SYSTEM_PROMPT = """You are an AI trend intelligence analyst. Your job is to identify EMERGING trends
from cross-source signal data — trends that are forming but haven't yet become mainstream news.

You receive structured signal clusters with:
- Entity/topic name
- Source diversity (how many different source types mention it)
- Mention velocity (acceleration over time windows)
- Sentiment distribution across sources
- Novelty (how new is this entity to our radar)

For each emerging trend, provide:
1. **Trend Name**: Clear, descriptive label
2. **Evidence Chain**: Which sources, in what order, with what signals
3. **Emergence Score**: 0-100 (how strong is the cross-source pattern)
4. **Velocity**: accelerating / steady / decelerating
5. **Prediction**: What happens next if this trend continues
6. **Time Horizon**: When will this become mainstream (days/weeks/months)

Output as a JSON object with key "emerging_trends":
{
  "emerging_trends": [
    {
      "trend_name": "Trend Name",
      "entities": ["Entity1", "Entity2"],
      "evidence_chain": [
        {"source_type": "arxiv", "signal": "3 papers published in 2 weeks", "date": "YYYY-MM-DD"},
        {"source_type": "github", "signal": "new repo 500 stars in 3 days", "date": "YYYY-MM-DD"},
        {"source_type": "news", "signal": "TechCrunch coverage", "date": "YYYY-MM-DD"}
      ],
      "emergence_score": 82,
      "source_diversity": 4,
      "velocity": "accelerating",
      "prediction": "What happens next",
      "time_horizon": "1-2 weeks to mainstream",
      "narrative": "Brief narrative of this trend"
    }
  ]
}

IMPORTANT: Use actual dates from the signal data, not the placeholder YYYY-MM-DD format.

Keep it concise — max 5 trends, max 3 evidence items per trend.

Focus on CROSS-SOURCE PATTERNS. Single-source trends are noise. Multi-source convergence is signal."""


class TrendDetectorAgent(BaseAgent):
    """
    Cross-source pattern detection for emerging AI trends.

    Data flow:
      1. Pull recent signals from all source types (7d/14d/30d windows)
      2. Group by entity (using entity mentions in trend_radar.db)
      3. For each entity cluster, compute:
         - Source diversity score (how many different source types)
         - Velocity (acceleration of mentions over time)
         - Sentiment divergence (are different sources disagreeing?)
         - Novelty (is this entity new to our radar?)
      4. Filter by minimum source diversity
      5. Rank by composite "emergence score"
      6. LLM generates narrative for top-N emerging trends
    """

    def __init__(self, llm_client=None, db_path: str = "data/trend_radar.db"):
        super().__init__(llm_client)
        self.db_path = Path(db_path)
        self.entity_store = EntityStore()

    @property
    def card(self) -> AgentCard:
        return AgentCard(
            agent_id="trend_detector",
            name="Trend Detector",
            description="Cross-source emerging trend detection — finds patterns across news, GitHub, arxiv, hiring, patents before they're mainstream",
            input_schema={
                "time_window_days": "int (default 14)",
                "sector_filter": "str (optional)",
                "entity_filter": "str (optional)",
                "min_sources": "int (default 2)",
            },
            output_schema={
                "emerging_trends": "list",
                "stealth_signals": "list",
                "trend_count": "int",
            },
            capabilities=[
                "cross_source_correlation",
                "early_signal_detection",
                "trend_velocity_tracking",
                "stealth_signal_detection",
            ],
            model_task="deep_research",
        )

    async def run(self, input: AgentInput) -> AgentOutput:
        """Run trend detection."""
        ctx = input.context or {}
        time_window = int(ctx.get("time_window_days", 14))
        sector_filter = ctx.get("sector_filter")
        entity_filter = ctx.get("entity_filter", input.entity_name)
        min_sources = int(ctx.get("min_sources", MIN_SOURCE_DIVERSITY))

        # Step 1: Gather cross-source signals
        signal_clusters = self._gather_signal_clusters(
            time_window_days=time_window,
            sector_filter=sector_filter,
            entity_filter=entity_filter,
        )

        if not signal_clusters:
            return AgentOutput(
                agent_id="trend_detector",
                status="completed",
                data={"emerging_trends": [], "message": "No cross-source patterns detected in time window"},
            )

        # Step 2: Score and rank
        scored = self._score_clusters(signal_clusters, min_sources=min_sources)

        # Step 3: Detect stealth signals (non-news signals without news coverage)
        stealth = self._detect_stealth_signals(signal_clusters)

        # Step 4: LLM narrative generation for top trends
        try:
            prompt = self._build_prompt(scored[:10], stealth[:5])
            result = self._query_llm(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=8192,
                temperature=0.3,
            )
            # Handle array response (LLM returned [...] instead of {"emerging_trends": [...]})
            if isinstance(result, list):
                result = {"emerging_trends": result}
            # Check if LLM actually returned useful data
            if isinstance(result, dict) and result.get("emerging_trends"):
                result["stealth_signals"] = stealth
                return AgentOutput(agent_id="trend_detector", status="completed", data=result)
            else:
                logger.warning(f"Trend detector LLM returned empty/invalid result, using raw data")
                raise ValueError("Empty LLM result")
        except Exception as e:
            logger.warning(f"Trend detector LLM unavailable ({e}), using raw scored data")
            # Build structured trends from raw scored data (no LLM needed)
            raw_trends = []
            for s in scored[:10]:
                raw_trends.append({
                    "trend_name": s.get("entity", "Unknown"),
                    "entity": s.get("entity", "Unknown"),
                    "emergence_score": round(s.get("emergence_score", 0), 1),
                    "source_diversity": s.get("source_diversity", 0),
                    "velocity": s.get("velocity_label", "unknown"),
                    "velocity_label": s.get("velocity_label", "unknown"),
                    "narrative": f"Detected across {s.get('source_diversity', 0)} source types with {s.get('total_mentions', 0)} total mentions",
                    "evidence_chain": [
                        f"{src}" for src in s.get("source_types", [])
                    ][:5],
                    "prediction": "",
                })
            return AgentOutput(
                agent_id="trend_detector",
                status="completed",
                data={
                    "emerging_trends": raw_trends,
                    "stealth_signals": stealth,
                    "note": "Raw signal data (LLM narrative unavailable)",
                },
            )

    # -----------------------------------------------------------------------
    # Signal gathering
    # -----------------------------------------------------------------------

    def _gather_signal_clusters(
        self,
        time_window_days: int = 14,
        sector_filter: Optional[str] = None,
        entity_filter: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Pull mentions from both DBs via EntityStore, grouped by entity.

        Returns: {entity_name: {sources: {source_type: [mentions]}, first_seen: ..., ...}}
        """
        clusters: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "sources": defaultdict(list),
            "first_seen": None,
            "total_mentions": 0,
            "sentiments": [],
        })

        try:
            # If specific entity, just get that one
            if entity_filter:
                entities_to_check = [entity_filter]
            else:
                # Get top entities by composite score
                top = self.entity_store.list_top_entities(limit=100)
                entities_to_check = [e.canonical_name for e in top]

            for entity_name in entities_to_check:
                mentions = self.entity_store.get_mentions(entity_name, days=time_window_days)

                for m in mentions:
                    source = m.source_type
                    clusters[entity_name]["sources"][source].append({
                        "title": m.title or m.source_name,
                        "date": m.date,
                        "url": m.url,
                        "score": m.score,
                    })
                    clusters[entity_name]["total_mentions"] += 1

                    if clusters[entity_name]["first_seen"] is None or (
                        m.date and m.date < clusters[entity_name]["first_seen"]
                    ):
                        clusters[entity_name]["first_seen"] = m.date

        except Exception as e:
            logger.error(f"Failed to gather signal clusters: {e}")

        # Filter out entities with no mentions
        return {k: v for k, v in clusters.items() if v["total_mentions"] > 0}

    def _categorize_source(self, source: str) -> str:
        """Map raw source strings to source categories."""
        source_lower = source.lower()
        mappings = {
            "github": "github",
            "huggingface": "huggingface",
            "hf": "huggingface",
            "arxiv": "arxiv",
            "reddit": "reddit",
            "hackernews": "hackernews",
            "hn": "hackernews",
            "hacker_news": "hackernews",
            "polymarket": "prediction_market",
            "metaculus": "prediction_market",
            "manifold": "prediction_market",
            "patent": "patent",
            "hiring": "hiring",
            "job": "hiring",
            "linkedin": "hiring",
            "policy": "policy",
            "regulation": "policy",
            "earnings": "earnings",
            "podcast": "podcast",
            "newsletter": "newsletter",
            "substack": "newsletter",
            "product_hunt": "product_hunt",
            "twitter": "social",
            "threads": "social",
        }
        for key, category in mappings.items():
            if key in source_lower:
                return category
        return "news"  # Default: treat unknown sources as news

    # -----------------------------------------------------------------------
    # Scoring
    # -----------------------------------------------------------------------

    def _score_clusters(
        self, clusters: Dict[str, Dict], min_sources: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Score and rank entity clusters by emergence potential.

        Composite score = source_diversity * velocity * weighted_mentions * novelty_bonus
        """
        scored = []

        for entity, data in clusters.items():
            source_types = list(data["sources"].keys())
            source_diversity = len(source_types)

            if source_diversity < min_sources:
                continue

            # Weighted mention count
            weighted_mentions = 0
            for source_type, mentions in data["sources"].items():
                weight = SOURCE_WEIGHTS.get(source_type, 1.0)
                weighted_mentions += len(mentions) * weight

            # Velocity: ratio of recent (3d) vs older mentions
            recent_cutoff = (datetime.now() - timedelta(days=3)).isoformat()
            recent_count = sum(
                1 for src_mentions in data["sources"].values()
                for m in src_mentions
                if m.get("date") and m["date"] >= recent_cutoff
            )
            total = data["total_mentions"]
            velocity = recent_count / max(total, 1)  # 0-1, higher = more recent activity

            # Novelty bonus: entities first seen recently get a boost
            novelty = 1.0
            if data["first_seen"]:
                try:
                    first = datetime.fromisoformat(data["first_seen"])
                    days_known = (datetime.now() - first).days
                    if days_known <= 7:
                        novelty = 1.5  # New entity bonus
                    elif days_known <= 14:
                        novelty = 1.2
                except (ValueError, TypeError):
                    pass

            # Composite emergence score (0-100)
            # Use log scale for mentions to avoid mega-entities dominating
            import math
            mention_signal = math.log2(max(weighted_mentions, 1)) * 5  # log2(500)*5 = ~45
            diversity_signal = source_diversity * 12                     # 5 types * 12 = 60
            velocity_signal = velocity * 25                              # 0-25

            raw_score = (
                diversity_signal
                + mention_signal
                + velocity_signal
            ) * novelty

            emergence_score = min(100, int(raw_score))

            # Stealth detection: non-news signals without news coverage
            has_news = "news" in source_types
            non_news_sources = [s for s in source_types if s != "news"]
            is_stealth = not has_news and len(non_news_sources) >= 2

            scored.append({
                "entity": entity,
                "emergence_score": emergence_score,
                "source_diversity": source_diversity,
                "source_types": source_types,
                "total_mentions": total,
                "weighted_mentions": round(weighted_mentions, 1),
                "velocity": round(velocity, 2),
                "velocity_label": "accelerating" if velocity > 0.5 else "steady" if velocity > 0.2 else "fading",
                "novelty": novelty,
                "is_stealth": is_stealth,
                "first_seen": data["first_seen"],
                "top_signals": self._get_top_signals(data["sources"]),
            })

        scored.sort(key=lambda x: x["emergence_score"], reverse=True)
        return scored

    def _get_top_signals(self, sources: Dict[str, list], top_n: int = 5) -> List[Dict]:
        """Get the top N signals across all sources, weighted by source importance."""
        all_signals = []
        for source_type, mentions in sources.items():
            weight = SOURCE_WEIGHTS.get(source_type, 1.0)
            for m in mentions:
                all_signals.append({
                    "source_type": source_type,
                    "title": m.get("title", ""),
                    "date": m.get("date", ""),
                    "weight": weight,
                })
        all_signals.sort(key=lambda x: x["weight"], reverse=True)
        return all_signals[:top_n]

    # -----------------------------------------------------------------------
    # Stealth signal detection
    # -----------------------------------------------------------------------

    def _detect_stealth_signals(self, clusters: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Find entities with non-news signals but NO news coverage.

        These are the most valuable signals: resource commitments (hiring, patents)
        that haven't been covered by media yet.
        """
        stealth = []

        for entity, data in clusters.items():
            source_types = set(data["sources"].keys())
            has_news = "news" in source_types

            if has_news:
                continue  # Not stealth if there's news coverage

            # High-value non-news signals
            high_value_sources = source_types & {"hiring", "patent", "github", "arxiv", "huggingface"}
            if len(high_value_sources) >= 1 and data["total_mentions"] >= 2:
                stealth.append({
                    "entity": entity,
                    "signal_sources": list(source_types),
                    "high_value_sources": list(high_value_sources),
                    "total_mentions": data["total_mentions"],
                    "description": self._describe_stealth(entity, data["sources"]),
                })

        stealth.sort(key=lambda x: len(x["high_value_sources"]), reverse=True)
        return stealth

    def _describe_stealth(self, entity: str, sources: Dict[str, list]) -> str:
        """Generate a human-readable description of stealth signals."""
        parts = []
        for source_type, mentions in sources.items():
            count = len(mentions)
            if source_type == "hiring":
                parts.append(f"{count} job posting{'s' if count > 1 else ''}")
            elif source_type == "patent":
                parts.append(f"{count} patent filing{'s' if count > 1 else ''}")
            elif source_type == "github":
                parts.append(f"{count} GitHub signal{'s' if count > 1 else ''}")
            elif source_type == "arxiv":
                parts.append(f"{count} research paper{'s' if count > 1 else ''}")
            else:
                parts.append(f"{count} {source_type} mention{'s' if count > 1 else ''}")

        return f"{entity}: {', '.join(parts)} — zero news coverage"

    # -----------------------------------------------------------------------
    # Prompt builder
    # -----------------------------------------------------------------------

    def _build_prompt(self, scored: List[Dict], stealth: List[Dict]) -> str:
        """Build LLM prompt from scored clusters and stealth signals."""
        today = datetime.now().strftime("%Y-%m-%d")
        prompt_parts = [f"## Emerging Signal Clusters (ranked by emergence score)\n"]
        prompt_parts.append(f"**Analysis Date: {today}**\n")
        prompt_parts.append("Use actual dates from the signal data in evidence chains, not placeholder dates.\n")

        for i, item in enumerate(scored[:15]):
            prompt_parts.append(
                f"\n### {i+1}. {item['entity']} (score: {item['emergence_score']})\n"
                f"- Source diversity: {item['source_diversity']} types ({', '.join(item['source_types'])})\n"
                f"- Velocity: {item['velocity_label']} ({item['velocity']:.0%} recent)\n"
                f"- Total mentions: {item['total_mentions']} (weighted: {item['weighted_mentions']})\n"
                f"- Novelty: {'NEW' if item['novelty'] > 1 else 'established'}\n"
                f"- Stealth: {'YES' if item['is_stealth'] else 'no'}\n"
                f"- Top signals:"
            )
            for sig in item.get("top_signals", [])[:3]:
                prompt_parts.append(f"  - [{sig['source_type']}] {sig['title'][:100]}")

        if stealth:
            prompt_parts.append("\n\n## Stealth Signals (no news coverage)\n")
            for s in stealth[:10]:
                prompt_parts.append(f"- {s['description']}")

        prompt_parts.append(
            "\n\nAnalyze these signal clusters. Identify the top emerging trends, "
            "explain the evidence chain for each, and make predictions about what happens next."
        )

        return "\n".join(prompt_parts)
