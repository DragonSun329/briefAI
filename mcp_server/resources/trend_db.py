"""
Trend Database Resources

Provides read-only access to trend_radar.db data.
"""

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

DB_PATH = Path(__file__).parent.parent.parent / "data" / "trend_radar.db"


def register(mcp: "FastMCP"):
    """Register trend database resources with MCP server."""

    @mcp.resource("trend://latest")
    def get_latest_trends() -> str:
        """Get latest trending entities from trend_radar.db.

        Returns top 20 entities sorted by momentum score.
        """
        if not DB_PATH.exists():
            return json.dumps({"error": "Database not found", "entities": []})

        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # Try trend_signals table first
        try:
            cursor.execute("""
                SELECT entity_name, momentum_score, article_count
                FROM trend_signals
                ORDER BY momentum_score DESC
                LIMIT 20
            """)
            results = cursor.fetchall()
        except sqlite3.OperationalError:
            # Fall back to entity_mentions if trend_signals doesn't exist
            try:
                cursor.execute("""
                    SELECT entity_name, COUNT(*) as mentions, COUNT(DISTINCT article_id) as articles
                    FROM entity_mentions
                    WHERE mentioned_at > datetime('now', '-7 days')
                    GROUP BY entity_name
                    ORDER BY mentions DESC
                    LIMIT 20
                """)
                results = cursor.fetchall()
            except sqlite3.OperationalError:
                results = []

        conn.close()

        return json.dumps([
            {"entity": r[0], "momentum": r[1], "articles": r[2]}
            for r in results
        ])

    @mcp.resource("trend://entity/{name}")
    def get_entity_trends(name: str) -> str:
        """Get 7-day trend history for a specific entity.

        Args:
            name: Entity name to look up
        """
        if not DB_PATH.exists():
            return json.dumps({"error": "Database not found", "history": []})

        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT date, momentum_score, article_count, source
                FROM trend_signals
                WHERE entity_name = ?
                AND date > date('now', '-7 days')
                ORDER BY date DESC
            """, (name,))
            results = cursor.fetchall()
        except sqlite3.OperationalError:
            results = []

        conn.close()

        return json.dumps({
            "entity": name,
            "history": [
                {"date": r[0], "momentum": r[1], "articles": r[2], "source": r[3]}
                for r in results
            ]
        })

    @mcp.resource("conviction://scores")
    def get_conviction_scores() -> str:
        """Get latest conviction scores from Devil's Advocate analysis."""
        if not DB_PATH.exists():
            return json.dumps({"error": "Database not found", "scores": []})

        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    entity_name,
                    entity_type,
                    conviction_score,
                    conflict_intensity,
                    recommendation,
                    bull_thesis,
                    bear_thesis,
                    synthesis,
                    analyzed_at
                FROM conviction_scores
                WHERE analyzed_at = (
                    SELECT MAX(analyzed_at)
                    FROM conviction_scores cs2
                    WHERE cs2.entity_name = conviction_scores.entity_name
                )
                ORDER BY conviction_score DESC
                LIMIT 20
            """)
            results = cursor.fetchall()
        except sqlite3.OperationalError:
            results = []

        conn.close()

        return json.dumps({
            "scores": [
                {
                    "entity": r[0],
                    "entity_type": r[1],
                    "conviction": r[2],
                    "conflict_intensity": r[3],
                    "recommendation": r[4],
                    "bull_thesis": r[5],
                    "bear_thesis": r[6],
                    "synthesis": r[7],
                    "analyzed_at": r[8]
                }
                for r in results
            ]
        })
