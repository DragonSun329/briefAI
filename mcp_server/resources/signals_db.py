"""
Signals Database Resources

Read-only access to signal profiles, scores, and divergences from signals.db.
"""

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

DB_PATH = Path(__file__).parent.parent.parent / "data" / "signals.db"


def _get_connection():
    """Get database connection, return None if db doesn't exist."""
    if not DB_PATH.exists():
        return None
    return sqlite3.connect(str(DB_PATH))


def register(mcp: "FastMCP"):
    """Register signals database resources with MCP server."""

    @mcp.resource("signals://profiles/latest")
    def get_latest_profiles() -> str:
        """Get latest signal profiles for all entities.

        Returns aggregated scores across technical, company, financial,
        product, and media categories.
        """
        conn = _get_connection()
        if not conn:
            return json.dumps({"error": "signals.db not found", "profiles": []})

        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    entity_name, entity_type, composite_score,
                    technical_score, company_score, financial_score,
                    product_score, media_score, momentum_7d, momentum_30d,
                    data_freshness, as_of
                FROM signal_profiles
                WHERE as_of = (SELECT MAX(as_of) FROM signal_profiles)
                ORDER BY composite_score DESC
                LIMIT 50
            """)
            results = cursor.fetchall()
            conn.close()

            return json.dumps([
                {
                    "entity": r[0],
                    "type": r[1],
                    "composite": r[2],
                    "technical": r[3],
                    "company": r[4],
                    "financial": r[5],
                    "product": r[6],
                    "media": r[7],
                    "momentum_7d": r[8],
                    "momentum_30d": r[9],
                    "freshness": r[10],
                    "as_of": r[11]
                }
                for r in results
            ])
        except Exception as e:
            logger.error(f"Error reading signal profiles: {e}")
            return json.dumps({"error": str(e), "profiles": []})

    @mcp.resource("signals://profile/{entity_name}")
    def get_entity_profile(entity_name: str) -> str:
        """Get detailed signal profile for a specific entity.

        Includes all category scores, confidence levels, and top signals.
        """
        conn = _get_connection()
        if not conn:
            return json.dumps({"error": "signals.db not found"})

        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    entity_name, entity_type, as_of,
                    technical_score, technical_confidence,
                    company_score, company_confidence,
                    financial_score, financial_confidence,
                    product_score, product_confidence,
                    media_score, media_confidence,
                    composite_score, momentum_7d, momentum_30d,
                    data_freshness, top_signals
                FROM signal_profiles
                WHERE entity_name LIKE ?
                ORDER BY as_of DESC
                LIMIT 1
            """, (f"%{entity_name}%",))
            row = cursor.fetchone()
            conn.close()

            if not row:
                return json.dumps({"error": f"No profile found for '{entity_name}'"})

            top_signals = []
            if row[17]:
                try:
                    top_signals = json.loads(row[17])
                except json.JSONDecodeError:
                    pass

            return json.dumps({
                "entity": row[0],
                "type": row[1],
                "as_of": row[2],
                "scores": {
                    "technical": {"score": row[3], "confidence": row[4]},
                    "company": {"score": row[5], "confidence": row[6]},
                    "financial": {"score": row[7], "confidence": row[8]},
                    "product": {"score": row[9], "confidence": row[10]},
                    "media": {"score": row[11], "confidence": row[12]},
                    "composite": row[13]
                },
                "momentum": {"7d": row[14], "30d": row[15]},
                "freshness": row[16],
                "top_signals": top_signals
            })
        except Exception as e:
            logger.error(f"Error reading entity profile: {e}")
            return json.dumps({"error": str(e)})

    @mcp.resource("signals://divergences")
    def get_active_divergences() -> str:
        """Get all active (unresolved) signal divergences.

        Divergences indicate entities where different signal categories
        tell conflicting stories (e.g., high technical but low financial).
        """
        conn = _get_connection()
        if not conn:
            return json.dumps({"error": "signals.db not found", "divergences": []})

        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    entity_name, divergence_type,
                    high_signal_category, high_signal_score,
                    low_signal_category, low_signal_score,
                    divergence_magnitude, confidence,
                    interpretation, detected_at
                FROM signal_divergences
                WHERE resolved_at IS NULL
                ORDER BY divergence_magnitude DESC
                LIMIT 30
            """)
            results = cursor.fetchall()
            conn.close()

            return json.dumps([
                {
                    "entity": r[0],
                    "type": r[1],
                    "high": {"category": r[2], "score": r[3]},
                    "low": {"category": r[4], "score": r[5]},
                    "magnitude": r[6],
                    "confidence": r[7],
                    "interpretation": r[8],
                    "detected_at": r[9]
                }
                for r in results
            ])
        except Exception as e:
            logger.error(f"Error reading divergences: {e}")
            return json.dumps({"error": str(e), "divergences": []})

    @mcp.resource("signals://financial/{ticker}")
    def get_financial_signals(ticker: str) -> str:
        """Get financial signal scores for a ticker/entity.

        Returns PMS (Prediction Market Sentiment), CSS (Crowd Sentiment Score),
        MRS (Market Reality Score) if available.
        """
        conn = _get_connection()
        if not conn:
            return json.dumps({"error": "signals.db not found"})

        try:
            cursor = conn.cursor()
            # Get entity ID first
            cursor.execute("""
                SELECT id FROM entities
                WHERE name LIKE ? OR aliases LIKE ?
            """, (f"%{ticker}%", f"%{ticker}%"))
            entity_row = cursor.fetchone()

            if not entity_row:
                return json.dumps({"error": f"Entity not found: {ticker}"})

            entity_id = entity_row[0]

            # Get latest financial scores
            cursor.execute("""
                SELECT
                    category, score, percentile,
                    score_delta_7d, score_delta_30d,
                    period_end
                FROM signal_scores
                WHERE entity_id = ?
                AND category IN ('PMS', 'CSS', 'MRS', 'financial', 'prediction_market')
                ORDER BY period_end DESC
            """, (entity_id,))
            results = cursor.fetchall()
            conn.close()

            if not results:
                return json.dumps({
                    "ticker": ticker,
                    "message": "No financial signals found",
                    "signals": []
                })

            return json.dumps({
                "ticker": ticker,
                "signals": [
                    {
                        "category": r[0],
                        "score": r[1],
                        "percentile": r[2],
                        "delta_7d": r[3],
                        "delta_30d": r[4],
                        "as_of": r[5]
                    }
                    for r in results
                ]
            })
        except Exception as e:
            logger.error(f"Error reading financial signals: {e}")
            return json.dumps({"error": str(e)})

    @mcp.resource("signals://sources")
    def get_signal_sources() -> str:
        """Get list of all configured signal sources and their status."""
        conn = _get_connection()
        if not conn:
            return json.dumps({"error": "signals.db not found", "sources": []})

        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    name, category, url, update_frequency,
                    latency_hours, confidence_base, enabled
                FROM signal_sources
                ORDER BY category, name
            """)
            results = cursor.fetchall()
            conn.close()

            return json.dumps([
                {
                    "name": r[0],
                    "category": r[1],
                    "url": r[2],
                    "frequency": r[3],
                    "latency_hours": r[4],
                    "base_confidence": r[5],
                    "enabled": bool(r[6])
                }
                for r in results
            ])
        except Exception as e:
            logger.error(f"Error reading signal sources: {e}")
            return json.dumps({"error": str(e), "sources": []})
