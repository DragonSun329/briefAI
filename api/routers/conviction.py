"""Conviction Scores API endpoints.

Provides access to adversarial analysis results from the Devil's Advocate workflow.
"""

import os
import sys
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

# Setup paths
_api_dir = Path(__file__).parent.parent
_app_dir = _api_dir.parent
_db_path = _app_dir / "data" / "trend_radar.db"

if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

router = APIRouter(prefix="/api/conviction", tags=["conviction"])


# --- Pydantic Models ---

class SignalBreakdown(BaseModel):
    technical_velocity: int
    commercial_maturity: int
    brand_safety: int


class Verdict(BaseModel):
    bull_thesis: Optional[str] = None
    bear_thesis: Optional[str] = None
    synthesis: Optional[str] = None
    key_uncertainty: Optional[str] = None


class ConvictionScore(BaseModel):
    id: int
    entity_name: str
    entity_type: str
    conviction_score: float
    conflict_intensity: str
    recommendation: str
    verdict: Verdict
    signal_breakdown: SignalBreakdown
    momentum_bonus: int
    risk_penalty: int
    analyzed_at: str
    llm_model: Optional[str] = None


class ConvictionListResponse(BaseModel):
    scores: List[ConvictionScore]
    total: int
    filters_applied: Dict[str, Any]


class AlertsResponse(BaseModel):
    alerts: List[ConvictionScore]
    total: int


class AnalyzeRequest(BaseModel):
    entity_name: str
    force_refresh: bool = False


class AnalyzeResponse(BaseModel):
    status: str
    message: str
    entity_name: str
    task_id: Optional[str] = None


# --- Helper Functions ---

def get_db_connection():
    """Get SQLite database connection."""
    return sqlite3.connect(str(_db_path))


def row_to_conviction_score(row: sqlite3.Row) -> ConvictionScore:
    """Convert database row to ConvictionScore model."""
    return ConvictionScore(
        id=row["id"],
        entity_name=row["entity_name"],
        entity_type=row["entity_type"],
        conviction_score=row["conviction_score"] or 0,
        conflict_intensity=row["conflict_intensity"] or "LOW",
        recommendation=row["recommendation"] or "IGNORE",
        verdict=Verdict(
            bull_thesis=row["bull_thesis"],
            bear_thesis=row["bear_thesis"],
            synthesis=row["synthesis"],
            key_uncertainty=row["key_uncertainty"]
        ),
        signal_breakdown=SignalBreakdown(
            technical_velocity=int(row["technical_velocity_score"] or 0),
            commercial_maturity=int(row["commercial_maturity_score"] or 0),
            brand_safety=int(row["brand_safety_score"] or 0)
        ),
        momentum_bonus=row["momentum_bonus"] or 0,
        risk_penalty=row["risk_penalty"] or 0,
        analyzed_at=row["analyzed_at"],
        llm_model=row["llm_model"]
    )


# --- API Endpoints ---

@router.get("/scores", response_model=ConvictionListResponse)
def get_conviction_scores(
    min_conviction: Optional[float] = None,
    max_conviction: Optional[float] = None,
    conflict: Optional[str] = None,
    recommendation: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """
    Get all conviction scores, sortable and filterable.

    Query params:
    - min_conviction: Minimum conviction score (0-100)
    - max_conviction: Maximum conviction score (0-100)
    - conflict: Filter by conflict intensity (HIGH, MEDIUM, LOW)
    - recommendation: Filter by recommendation (ALERT, INVESTIGATE, MONITOR, IGNORE)
    - entity_type: Filter by entity type (OSS_PROJECT, COMMERCIAL_SAAS)
    - limit: Max results (default 50)
    - offset: Pagination offset
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Build query with filters
    where_clauses = []
    params = []

    if min_conviction is not None:
        where_clauses.append("conviction_score >= ?")
        params.append(min_conviction)

    if max_conviction is not None:
        where_clauses.append("conviction_score <= ?")
        params.append(max_conviction)

    if conflict:
        where_clauses.append("conflict_intensity = ?")
        params.append(conflict.upper())

    if recommendation:
        where_clauses.append("recommendation = ?")
        params.append(recommendation.upper())

    if entity_type:
        where_clauses.append("entity_type = ?")
        params.append(entity_type.upper())

    # Only get latest analysis per entity
    base_query = """
        SELECT * FROM conviction_scores
        WHERE analyzed_at = (
            SELECT MAX(analyzed_at)
            FROM conviction_scores cs2
            WHERE cs2.entity_name = conviction_scores.entity_name
        )
    """

    if where_clauses:
        base_query += " AND " + " AND ".join(where_clauses)

    # Count total
    count_query = f"SELECT COUNT(*) FROM ({base_query})"
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]

    # Get paginated results
    query = f"{base_query} ORDER BY conviction_score DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor.execute(query, params)

    scores = [row_to_conviction_score(row) for row in cursor.fetchall()]
    conn.close()

    return ConvictionListResponse(
        scores=scores,
        total=total,
        filters_applied={
            "min_conviction": min_conviction,
            "max_conviction": max_conviction,
            "conflict": conflict,
            "recommendation": recommendation,
            "entity_type": entity_type
        }
    )


@router.get("/scores/{entity_name}", response_model=ConvictionScore)
def get_entity_conviction(entity_name: str):
    """Get full conviction analysis for a specific entity."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM conviction_scores
        WHERE entity_name = ?
        ORDER BY analyzed_at DESC
        LIMIT 1
    """, (entity_name,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"No conviction score found for '{entity_name}'")

    return row_to_conviction_score(row)


@router.get("/alerts", response_model=AlertsResponse)
def get_alerts():
    """Get entities with ALERT or INVESTIGATE recommendation."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM conviction_scores
        WHERE recommendation IN ('ALERT', 'INVESTIGATE')
        AND analyzed_at = (
            SELECT MAX(analyzed_at)
            FROM conviction_scores cs2
            WHERE cs2.entity_name = conviction_scores.entity_name
        )
        ORDER BY
            CASE recommendation WHEN 'ALERT' THEN 1 ELSE 2 END,
            conviction_score DESC
    """)

    alerts = [row_to_conviction_score(row) for row in cursor.fetchall()]
    conn.close()

    return AlertsResponse(alerts=alerts, total=len(alerts))


@router.get("/leaderboard")
def get_leaderboard(limit: int = 20):
    """Get top entities by conviction score."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            entity_name,
            entity_type,
            conviction_score,
            conflict_intensity,
            recommendation,
            technical_velocity_score,
            commercial_maturity_score,
            synthesis,
            analyzed_at
        FROM conviction_scores
        WHERE analyzed_at = (
            SELECT MAX(analyzed_at)
            FROM conviction_scores cs2
            WHERE cs2.entity_name = conviction_scores.entity_name
        )
        ORDER BY conviction_score DESC
        LIMIT ?
    """, (limit,))

    results = []
    for row in cursor.fetchall():
        results.append({
            "entity_name": row["entity_name"],
            "entity_type": row["entity_type"],
            "conviction_score": row["conviction_score"],
            "conflict_intensity": row["conflict_intensity"],
            "recommendation": row["recommendation"],
            "technical_velocity": row["technical_velocity_score"],
            "commercial_maturity": row["commercial_maturity_score"],
            "synthesis": row["synthesis"],
            "analyzed_at": row["analyzed_at"]
        })

    conn.close()
    return {"leaderboard": results, "total": len(results)}


def run_analysis_background(entity_name: str):
    """Background task to run adversarial analysis."""
    try:
        from agents.pipeline import AdversarialPipeline
        pipeline = AdversarialPipeline(db_path=str(_db_path))
        result = pipeline.analyze_entity(entity_name)
        pipeline.store_result(result)
    except Exception as e:
        print(f"Background analysis failed for {entity_name}: {e}")


@router.post("/analyze", response_model=AnalyzeResponse)
def trigger_analysis(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """
    Trigger adversarial analysis for a specific entity.

    The analysis runs in the background and results are stored in the database.
    Use GET /api/conviction/scores/{entity_name} to retrieve results.
    """
    entity_name = request.entity_name

    # Check if recent analysis exists (within last hour)
    if not request.force_refresh:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT analyzed_at FROM conviction_scores
            WHERE entity_name = ?
            AND analyzed_at > datetime('now', '-1 hour')
            ORDER BY analyzed_at DESC
            LIMIT 1
        """, (entity_name,))
        recent = cursor.fetchone()
        conn.close()

        if recent:
            return AnalyzeResponse(
                status="cached",
                message=f"Recent analysis exists from {recent['analyzed_at']}. Use force_refresh=true to re-analyze.",
                entity_name=entity_name
            )

    # Queue background analysis
    background_tasks.add_task(run_analysis_background, entity_name)

    return AnalyzeResponse(
        status="queued",
        message=f"Analysis queued for '{entity_name}'. Results will be available shortly.",
        entity_name=entity_name
    )


@router.get("/stats")
def get_conviction_stats():
    """Get aggregate statistics about conviction scores."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Count by recommendation
    cursor.execute("""
        SELECT recommendation, COUNT(*) as count
        FROM conviction_scores
        WHERE analyzed_at = (
            SELECT MAX(analyzed_at)
            FROM conviction_scores cs2
            WHERE cs2.entity_name = conviction_scores.entity_name
        )
        GROUP BY recommendation
    """)
    by_recommendation = {row[0]: row[1] for row in cursor.fetchall()}

    # Count by entity type
    cursor.execute("""
        SELECT entity_type, COUNT(*) as count
        FROM conviction_scores
        WHERE analyzed_at = (
            SELECT MAX(analyzed_at)
            FROM conviction_scores cs2
            WHERE cs2.entity_name = conviction_scores.entity_name
        )
        GROUP BY entity_type
    """)
    by_type = {row[0]: row[1] for row in cursor.fetchall()}

    # Average scores
    cursor.execute("""
        SELECT
            AVG(conviction_score) as avg_conviction,
            AVG(technical_velocity_score) as avg_technical,
            AVG(commercial_maturity_score) as avg_commercial,
            COUNT(DISTINCT entity_name) as total_entities
        FROM conviction_scores
        WHERE analyzed_at = (
            SELECT MAX(analyzed_at)
            FROM conviction_scores cs2
            WHERE cs2.entity_name = conviction_scores.entity_name
        )
    """)
    row = cursor.fetchone()

    conn.close()

    return {
        "total_entities": row[3] or 0,
        "average_conviction": round(row[0] or 0, 1),
        "average_technical_velocity": round(row[1] or 0, 1),
        "average_commercial_maturity": round(row[2] or 0, 1),
        "by_recommendation": by_recommendation,
        "by_entity_type": by_type
    }
