"""
Narrative Tracker Agent — Story Evolution Over Time

Tracks how narratives (themes, storylines) evolve across weeks and months.

Examples:
- "AI regulation in China": policy drafts → public comment → enforcement
- "OpenAI vs open-source": competitive dynamics, shifting sentiment
- "China chip independence": sanctions → domestic alternatives → breakthroughs

Uses event store + entity mentions to build narrative timelines with
momentum, inflection points, and sentiment arcs.
"""

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from agents.base import AgentCard, AgentInput, AgentOutput, BaseAgent
from utils.entity_store import EntityStore


SYSTEM_PROMPT = """You are a narrative intelligence analyst. You track how stories and themes
evolve over time — not individual articles, but the arc of a narrative.

You receive timeline data for active narratives/themes, including:
- Key events in chronological order
- Sentiment shifts over time
- Mention volume trends
- Related entities involved

For each narrative, analyze:
1. **Narrative Name**: Clear label for the storyline
2. **Phase**: emerging | developing | peak | fading | dormant
3. **Timeline**: Key events that shaped this narrative
4. **Sentiment Arc**: How opinion has shifted (e.g., "optimistic → cautious → mixed")
5. **Momentum**: accelerating | steady | decelerating | stalled
6. **Key Players**: Entities most involved in this narrative
7. **Inflection Points**: Moments where the narrative direction changed
8. **Outlook**: What happens next in this story
9. **Connections**: Links to other active narratives

Output as JSON:
{
  "narratives": [
    {
      "name": "叙事名称",
      "phase": "developing",
      "timeline": [
        {"date": "2024-01-10", "event": "事件描述", "impact": "high", "sentiment_shift": "+0.2"}
      ],
      "sentiment_arc": "optimistic → cautious",
      "current_sentiment": 0.6,
      "momentum": "accelerating",
      "mention_trend": {"7d": 45, "14d": 80, "30d": 120},
      "key_players": ["实体1", "实体2"],
      "inflection_points": ["关键转折点1"],
      "outlook": "预测未来发展",
      "connected_narratives": ["相关叙事"],
      "narrative_score": 75
    }
  ],
  "narrative_map": "简要描述各叙事之间的关系"
}

Focus on the EVOLUTION of stories, not individual data points. What changed? Why? What's next?"""


class NarrativeTrackerAgent(BaseAgent):
    """
    Tracks narrative evolution over time.

    Unlike the Trend Detector (which finds emerging patterns), the Narrative
    Tracker follows established stories and detects momentum shifts,
    inflection points, and sentiment arcs.
    """

    def __init__(self, llm_client=None, db_path: str = "data/trend_radar.db"):
        super().__init__(llm_client)
        self.db_path = Path(db_path)
        self.entity_store = EntityStore()

    @property
    def card(self) -> AgentCard:
        return AgentCard(
            agent_id="narrative_tracker",
            name="Narrative Tracker",
            description="Tracks how stories evolve over weeks/months — momentum, inflection points, sentiment arcs",
            input_schema={
                "topic": "str (narrative topic or 'auto' for auto-detection)",
                "time_window_days": "int (default 30)",
            },
            output_schema={
                "narratives": "list",
                "narrative_map": "str",
            },
            capabilities=[
                "narrative_detection",
                "timeline_construction",
                "sentiment_evolution",
                "narrative_momentum",
                "inflection_detection",
            ],
            model_task="deep_research",
        )

    async def run(self, input: AgentInput) -> AgentOutput:
        """Run narrative tracking."""
        ctx = input.context or {}
        topic = ctx.get("topic") or ctx.get("query") or input.entity_name
        time_window = int(ctx.get("time_window_days", 30))

        # Step 1: Gather timeline data
        if topic and topic.lower() != "auto":
            timelines = self._gather_topic_timeline(topic, time_window)
        else:
            timelines = self._gather_active_narratives(time_window)

        if not timelines:
            return AgentOutput(
                agent_id="narrative_tracker",
                status="completed",
                data={"narratives": [], "message": "No active narratives found in time window"},
            )

        # Step 2: Compute momentum and sentiment arcs
        analyzed = self._analyze_narratives(timelines, time_window)

        # Step 3: LLM narrative synthesis
        try:
            prompt = self._build_prompt(analyzed)
            result = self._query_llm(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.3,
            )
            return AgentOutput(agent_id="narrative_tracker", status="completed", data=result)
        except Exception as e:
            logger.error(f"Narrative tracker LLM failed: {e}")
            return AgentOutput(
                agent_id="narrative_tracker",
                status="completed",
                data={"narratives": analyzed[:10], "note": "Raw data (LLM unavailable)"},
            )

    # -----------------------------------------------------------------------
    # Data gathering
    # -----------------------------------------------------------------------

    def _gather_topic_timeline(self, topic: str, days: int) -> List[Dict[str, Any]]:
        """Gather timeline events for a specific topic/narrative using EntityStore."""
        events = []

        try:
            mentions = self.entity_store.get_mentions(topic, days=days)

            for m in mentions:
                events.append({
                    "title": m.title or m.source_name,
                    "source": m.source_name,
                    "date": m.date,
                    "url": m.url,
                    "score": m.score,
                })
        except Exception as e:
            logger.error(f"Timeline gathering failed: {e}")

        # Sort chronologically
        events.sort(key=lambda e: e.get("date") or "", reverse=False)

        return [{"topic": topic, "events": events, "event_count": len(events)}]

    def _gather_active_narratives(self, days: int) -> List[Dict[str, Any]]:
        """Auto-detect active narratives using EntityStore mention data."""
        narratives = []

        try:
            # Get top entities by composite score
            top = self.entity_store.list_top_entities(limit=20)

            for entity in top:
                name = entity.canonical_name
                mentions = self.entity_store.get_mentions(name, days=days)

                if len(mentions) < 3:
                    continue

                # Build event list from mentions
                events = []
                for m in mentions[:15]:  # Cap per entity
                    events.append({
                        "title": m.title or m.source_name,
                        "source": m.source_name,
                        "date": m.date,
                        "score": m.score,
                    })

                narratives.append({
                    "topic": name,
                    "events": events,
                    "event_count": len(mentions),
                })

        except Exception as e:
            logger.error(f"Active narrative detection failed: {e}")

        return narratives

    # -----------------------------------------------------------------------
    # Analysis
    # -----------------------------------------------------------------------

    def _analyze_narratives(self, timelines: List[Dict], time_window: int) -> List[Dict[str, Any]]:
        """Compute momentum, sentiment arcs, and phase for each narrative."""
        analyzed = []

        for timeline in timelines:
            topic = timeline["topic"]
            events = timeline["events"]

            if not events:
                continue

            # Mention volume by time window
            now = datetime.now()
            mentions_7d = sum(
                1 for e in events
                if e.get("date") and self._parse_date(e["date"]) >= now - timedelta(days=7)
            )
            mentions_14d = sum(
                1 for e in events
                if e.get("date") and self._parse_date(e["date"]) >= now - timedelta(days=14)
            )
            mentions_30d = len(events)

            # Momentum: compare recent vs older
            if mentions_14d > 0:
                first_half = mentions_14d - mentions_7d
                momentum = "accelerating" if mentions_7d > first_half * 1.5 else \
                           "steady" if mentions_7d >= first_half * 0.7 else \
                           "decelerating"
            else:
                momentum = "stalled"

            # Phase detection
            if mentions_30d <= 3:
                phase = "emerging"
            elif momentum == "accelerating":
                phase = "developing" if mentions_30d < 15 else "peak"
            elif momentum == "decelerating":
                phase = "fading"
            elif momentum == "stalled":
                phase = "dormant"
            else:
                phase = "developing"

            # Score (0-100)
            score = min(100, int(
                mentions_30d * 3
                + mentions_7d * 10
                + (20 if momentum == "accelerating" else 10 if momentum == "steady" else 0)
            ))

            analyzed.append({
                "topic": topic,
                "phase": phase,
                "momentum": momentum,
                "mention_trend": {"7d": mentions_7d, "14d": mentions_14d, "30d": mentions_30d},
                "narrative_score": score,
                "event_count": len(events),
                "key_events": events[:10],  # Top 10 for prompt
                "first_event_date": events[0].get("date") if events else None,
                "latest_event_date": events[-1].get("date") if events else None,
            })

        analyzed.sort(key=lambda x: x["narrative_score"], reverse=True)
        return analyzed

    def _parse_date(self, date_str: str) -> datetime:
        """Parse various date formats, always returns naive datetime."""
        try:
            dt = datetime.fromisoformat(date_str)
            # Strip timezone info to avoid naive/aware comparison issues
            return dt.replace(tzinfo=None)
        except (ValueError, TypeError):
            try:
                return datetime.strptime(date_str[:10], "%Y-%m-%d")
            except (ValueError, TypeError):
                return datetime.min

    # -----------------------------------------------------------------------
    # Prompt builder
    # -----------------------------------------------------------------------

    def _build_prompt(self, analyzed: List[Dict]) -> str:
        """Build LLM prompt from analyzed narrative data."""
        parts = ["## Active Narratives (ranked by narrative score)\n"]

        for i, nar in enumerate(analyzed[:10]):
            parts.append(
                f"\n### {i+1}. {nar['topic']} (score: {nar['narrative_score']}, phase: {nar['phase']})\n"
                f"- Momentum: {nar['momentum']}\n"
                f"- Mentions: 7d={nar['mention_trend']['7d']}, 14d={nar['mention_trend']['14d']}, 30d={nar['mention_trend']['30d']}\n"
                f"- Timeline span: {nar['first_event_date']} → {nar['latest_event_date']}\n"
                f"- Key events:"
            )
            for ev in nar.get("key_events", [])[:5]:
                parts.append(f"  - [{ev.get('date', '?')[:10]}] {ev.get('title', '')[:100]}")

        parts.append(
            "\n\nFor each narrative, analyze the evolution arc: what changed, where are we now, "
            "and what happens next. Identify connections between narratives."
        )

        return "\n".join(parts)
