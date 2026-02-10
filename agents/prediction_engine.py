"""
Prediction Engine Agent — Falsifiable Event Predictions

Makes explicit, trackable predictions about future events based on
signal patterns. NOT price predictions — event predictions:

- "OpenAI will announce GPT-5 within 30 days" (confidence: 0.7)
- "NVIDIA earnings will beat consensus" (hiring + patent signals)
- "This startup will raise Series B within 90 days" (hiring surge + job posts)

Tracks accuracy over time for calibration. The goal is to get better
at prediction by measuring and learning from outcomes.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from agents.base import AgentCard, AgentInput, AgentOutput, BaseAgent
from utils.entity_store import EntityStore


# ---------------------------------------------------------------------------
# Prediction models
# ---------------------------------------------------------------------------

PREDICTION_TYPES = {
    "product_launch": "New product/model announcement",
    "fundraising": "Funding round (seed, A, B, etc.)",
    "acquisition": "M&A activity",
    "partnership": "Strategic partnership/deal",
    "earnings_beat": "Earnings beat consensus",
    "earnings_miss": "Earnings miss consensus",
    "policy_change": "Regulatory/policy change",
    "talent_move": "Key executive hire/departure",
    "market_shift": "Significant market position change",
    "tech_breakthrough": "Technical milestone/breakthrough",
    "expansion": "Geographic or product expansion",
    "contraction": "Layoffs, shutdowns, pivots",
}

# Signal patterns that historically precede certain events
SIGNAL_PATTERNS = {
    "product_launch": {
        "indicators": ["arxiv_papers_increase", "github_activity_spike", "hiring_ml_engineers", "conference_talks"],
        "typical_lead_time_days": 30,
    },
    "fundraising": {
        "indicators": ["hiring_surge", "job_posts_senior_roles", "linkedin_growth", "product_launch_recent"],
        "typical_lead_time_days": 60,
    },
    "acquisition": {
        "indicators": ["hiring_freeze", "executive_departures", "patent_transfers", "news_speculation"],
        "typical_lead_time_days": 45,
    },
    "expansion": {
        "indicators": ["hiring_new_geo", "job_posts_increase", "partnership_signals", "patent_filings"],
        "typical_lead_time_days": 90,
    },
}


SYSTEM_PROMPT = """You are a prediction analyst. You make explicit, falsifiable predictions about
future AI industry events based on signal data.

RULES:
1. Every prediction MUST be falsifiable — it must be possible to check if it came true
2. Every prediction MUST have a time horizon (when to check)
3. Every prediction MUST have a confidence level (0.0-1.0)
4. Predictions are about EVENTS, not prices (no stock price predictions)
5. Be specific: "Company X will announce Y by date Z" not "something might happen"

You receive signal data for an entity/topic. Based on the patterns, generate predictions.

Output JSON:
{
  "entity": "实体名称",
  "predictions": [
    {
      "prediction_id": "uuid",
      "statement": "Specific, falsifiable prediction statement",
      "prediction_type": "product_launch|fundraising|acquisition|...",
      "confidence": 0.7,
      "horizon_days": 30,
      "check_date": "2024-03-15",
      "evidence": [
        {"signal": "what signal supports this", "weight": "how much it matters", "source": "where from"}
      ],
      "counter_evidence": ["what could prove this wrong"],
      "base_rate": "how often this type of event happens (if known)",
      "reasoning": "step-by-step logic for this prediction"
    }
  ],
  "calibration_notes": "meta-notes on confidence calibration"
}

Aim for 3-5 predictions per entity. Mix high-confidence near-term and lower-confidence longer-term.
Be honest about uncertainty. A well-calibrated 0.3 confidence is more useful than overconfident 0.9."""


class PredictionEngineAgent(BaseAgent):
    """
    Makes and tracks falsifiable event predictions.

    Flow:
      1. Gather all signals for entity/topic
      2. Match against known signal patterns
      3. Generate predictions via LLM with structured evidence
      4. Store in predictions.db for later verification
      5. Periodically auto-verify and update calibration
    """

    def __init__(
        self,
        llm_client=None,
        db_path: str = "data/trend_radar.db",
        predictions_db: str = "data/predictions.db",
    ):
        super().__init__(llm_client)
        self.db_path = Path(db_path)
        self.predictions_db = Path(predictions_db)
        self.entity_store = EntityStore()
        self._ensure_predictions_schema()

    @property
    def card(self) -> AgentCard:
        return AgentCard(
            agent_id="prediction",
            name="Prediction Engine",
            description="Makes falsifiable event predictions (not price predictions) with tracked accuracy",
            input_schema={
                "entity_name": "str",
                "include_calibration": "bool (show historical accuracy)",
            },
            output_schema={
                "predictions": "list",
                "calibration": "dict (if requested)",
            },
            capabilities=[
                "event_prediction",
                "pattern_matching",
                "calibration_tracking",
                "falsifiable_forecasting",
            ],
            model_task="deep_research",
        )

    async def run(self, input: AgentInput) -> AgentOutput:
        """Generate predictions for an entity."""
        entity = input.entity_name
        ctx = input.context or {}
        include_calibration = ctx.get("include_calibration", False)

        # Step 1: Gather signals
        signals = self._gather_entity_signals(entity)

        # Step 2: Check for matching signal patterns
        pattern_matches = self._match_patterns(signals)

        # Step 3: Get calibration data if requested
        calibration = self._get_calibration() if include_calibration else None

        # Step 4: LLM prediction generation
        try:
            prompt = self._build_prompt(entity, signals, pattern_matches, calibration)
            result = self._query_llm(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.4,  # Slightly higher for creative predictions
            )

            # Step 5: Store predictions
            if isinstance(result, dict) and "predictions" in result:
                self._store_predictions(entity, result["predictions"])

            if calibration:
                if isinstance(result, dict):
                    result["calibration"] = calibration

            return AgentOutput(agent_id="prediction", status="completed", data=result)
        except Exception as e:
            logger.error(f"Prediction engine LLM failed: {e}")
            return AgentOutput(
                agent_id="prediction",
                status="completed",
                data={
                    "entity": entity,
                    "predictions": [],
                    "pattern_matches": pattern_matches,
                    "note": "LLM unavailable — showing raw pattern matches only",
                },
            )

    # -----------------------------------------------------------------------
    # Signal gathering
    # -----------------------------------------------------------------------

    def _gather_entity_signals(self, entity: str) -> Dict[str, Any]:
        """Gather all available signals for an entity via EntityStore."""
        signals = {
            "entity": entity,
            "news": [],
            "github": [],
            "hiring": [],
            "patent": [],
            "other": [],
            "mention_velocity": {},
        }

        try:
            # Get mentions from unified entity store (both DBs)
            mentions = self.entity_store.get_mentions(entity, days=30)

            for m in mentions:
                entry = {
                    "title": m.title or m.source_name,
                    "source": m.source_name,
                    "date": m.date,
                    "score": m.score,
                }
                if m.source_type == "github":
                    signals["github"].append(entry)
                elif m.source_type == "hiring":
                    signals["hiring"].append(entry)
                elif m.source_type == "patent":
                    signals["patent"].append(entry)
                elif m.source_type in ("news", "hackernews", "newsletter"):
                    signals["news"].append(entry)
                else:
                    signals["other"].append(entry)

            # Mention velocity from entity store
            signals["mention_velocity"] = self.entity_store.get_mention_velocity(entity)

        except Exception as e:
            logger.error(f"Signal gathering failed for {entity}: {e}")

        return signals

    # -----------------------------------------------------------------------
    # Pattern matching
    # -----------------------------------------------------------------------

    def _match_patterns(self, signals: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Match current signals against known pre-event patterns."""
        matches = []

        for event_type, pattern in SIGNAL_PATTERNS.items():
            score = 0
            matched_indicators = []

            # Check each indicator
            if "arxiv_papers_increase" in pattern["indicators"] and len(signals.get("github", [])) > 2:
                score += 1
                matched_indicators.append("research/code activity")

            if "hiring_surge" in pattern["indicators"] and len(signals.get("hiring", [])) > 3:
                score += 2  # Hiring is high-signal
                matched_indicators.append("hiring activity")

            if "patent_filings" in pattern["indicators"] and len(signals.get("patent", [])) > 0:
                score += 2
                matched_indicators.append("patent filings")

            if "github_activity_spike" in pattern["indicators"] and len(signals.get("github", [])) > 2:
                score += 1
                matched_indicators.append("github activity")

            velocity = signals.get("mention_velocity", {})
            if velocity.get("accelerating"):
                score += 1
                matched_indicators.append("accelerating mentions")

            if score >= 2:
                matches.append({
                    "event_type": event_type,
                    "description": PREDICTION_TYPES.get(event_type, event_type),
                    "pattern_match_score": score,
                    "matched_indicators": matched_indicators,
                    "typical_lead_time_days": pattern["typical_lead_time_days"],
                })

        matches.sort(key=lambda x: x["pattern_match_score"], reverse=True)
        return matches

    # -----------------------------------------------------------------------
    # Prediction storage & calibration
    # -----------------------------------------------------------------------

    def _ensure_predictions_schema(self):
        """Create predictions table if not exists."""
        try:
            self.predictions_db.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.predictions_db))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id TEXT PRIMARY KEY,
                    entity TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    prediction_type TEXT,
                    confidence REAL,
                    horizon_days INTEGER,
                    check_date TEXT,
                    evidence TEXT,
                    status TEXT DEFAULT 'pending',
                    outcome TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    resolved_at TEXT
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Predictions schema setup: {e}")

    def _store_predictions(self, entity: str, predictions: List[Dict]):
        """Store predictions for later verification."""
        try:
            conn = sqlite3.connect(str(self.predictions_db))
            for pred in predictions:
                pred_id = pred.get("prediction_id", str(uuid.uuid4()))
                conn.execute("""
                    INSERT OR REPLACE INTO predictions
                    (id, entity, statement, prediction_type, confidence, horizon_days, check_date, evidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    pred_id,
                    entity,
                    pred.get("statement", ""),
                    pred.get("prediction_type", ""),
                    pred.get("confidence", 0.5),
                    pred.get("horizon_days", 30),
                    pred.get("check_date", ""),
                    json.dumps(pred.get("evidence", []), ensure_ascii=False),
                ])
            conn.commit()
            conn.close()
            logger.info(f"Stored {len(predictions)} predictions for {entity}")
        except Exception as e:
            logger.error(f"Failed to store predictions: {e}")

    def _get_calibration(self) -> Dict[str, Any]:
        """Get prediction accuracy calibration data."""
        calibration = {
            "total_predictions": 0,
            "resolved": 0,
            "correct": 0,
            "accuracy": None,
            "by_type": {},
            "by_confidence_bucket": {},
        }

        try:
            conn = sqlite3.connect(str(self.predictions_db))
            conn.row_factory = sqlite3.Row

            # Overall stats
            cursor = conn.execute("SELECT COUNT(*) as total FROM predictions")
            calibration["total_predictions"] = cursor.fetchone()["total"]

            cursor = conn.execute("SELECT COUNT(*) as resolved FROM predictions WHERE status != 'pending'")
            calibration["resolved"] = cursor.fetchone()["resolved"]

            cursor = conn.execute("SELECT COUNT(*) as correct FROM predictions WHERE outcome = 'correct'")
            calibration["correct"] = cursor.fetchone()["correct"]

            if calibration["resolved"] > 0:
                calibration["accuracy"] = round(calibration["correct"] / calibration["resolved"], 3)

            # By type
            cursor = conn.execute("""
                SELECT prediction_type,
                    COUNT(*) as total,
                    SUM(CASE WHEN outcome = 'correct' THEN 1 ELSE 0 END) as correct
                FROM predictions
                WHERE status != 'pending'
                GROUP BY prediction_type
            """)
            for row in cursor.fetchall():
                calibration["by_type"][row["prediction_type"]] = {
                    "total": row["total"],
                    "correct": row["correct"],
                    "accuracy": round(row["correct"] / row["total"], 3) if row["total"] > 0 else None,
                }

            conn.close()
        except Exception as e:
            logger.debug(f"Calibration fetch failed: {e}")

        return calibration

    # -----------------------------------------------------------------------
    # Prompt builder
    # -----------------------------------------------------------------------

    def _build_prompt(
        self,
        entity: str,
        signals: Dict[str, Any],
        pattern_matches: List[Dict],
        calibration: Optional[Dict] = None,
    ) -> str:
        """Build LLM prompt for prediction generation."""
        parts = [f"## Entity: {entity}\n"]

        # Signal summary
        parts.append("### Available Signals\n")
        parts.append(f"- News articles (30d): {len(signals.get('news', []))}")
        parts.append(f"- GitHub signals: {len(signals.get('github', []))}")
        parts.append(f"- Hiring signals: {len(signals.get('hiring', []))}")
        parts.append(f"- Patent signals: {len(signals.get('patent', []))}")

        velocity = signals.get("mention_velocity", {})
        parts.append(f"- Mention velocity: {velocity.get('7d', 0)} (7d), {velocity.get('30d', 0)} (30d)")
        parts.append(f"- Accelerating: {'YES' if velocity.get('accelerating') else 'no'}")

        # Top recent signals
        all_items = signals.get("news", [])[:5] + signals.get("github", [])[:3] + signals.get("hiring", [])[:3]
        if all_items:
            parts.append("\n### Recent Key Signals")
            for item in all_items[:8]:
                parts.append(f"- [{item.get('date', '?')[:10]}] [{item.get('source', '?')}] {item.get('title', '')[:100]}")

        # Pattern matches
        if pattern_matches:
            parts.append("\n### Pattern Matches (known pre-event patterns)")
            for pm in pattern_matches:
                parts.append(
                    f"- **{pm['event_type']}** (score: {pm['pattern_match_score']}): "
                    f"{', '.join(pm['matched_indicators'])} "
                    f"(typical lead: {pm['typical_lead_time_days']}d)"
                )

        # Calibration context
        if calibration and calibration.get("resolved", 0) > 0:
            parts.append(
                f"\n### Calibration Context\n"
                f"Historical accuracy: {calibration['correct']}/{calibration['resolved']} "
                f"({calibration.get('accuracy', 'N/A')}). "
                f"Adjust confidence levels based on track record."
            )

        parts.append(
            "\n\nBased on these signals, generate 3-5 specific, falsifiable predictions. "
            "Each must have a clear check date and confidence level."
        )

        return "\n".join(parts)
