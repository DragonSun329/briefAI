"""
Daily Brief API Router

Endpoint to generate and retrieve the daily intelligence brief.
"""

from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from loguru import logger
from pydantic import BaseModel


router = APIRouter(prefix="/api/v1/brief", tags=["daily_brief"])


class BriefRequest(BaseModel):
    """Configuration for daily brief generation."""
    include_news: bool = True
    include_trends: bool = True
    include_narratives: bool = True
    include_predictions: bool = True
    include_alerts: bool = True
    top_stories: int = 10
    top_entities: int = 15


@router.post("/generate")
async def generate_daily_brief(req: BriefRequest = BriefRequest()):
    """
    Generate today's daily intelligence brief.

    Runs all agents (trend detector, narrative tracker, etc.) and
    composes output into a structured markdown report.

    Returns the report content as markdown.
    """
    try:
        from modules.daily_brief import DailyBriefGenerator

        gen = DailyBriefGenerator()
        content = await gen.generate_and_get_content(
            include_news=req.include_news,
            include_trends=req.include_trends,
            include_narratives=req.include_narratives,
            include_predictions=req.include_predictions,
            include_alerts=req.include_alerts,
            top_n_stories=req.top_stories,
            top_n_entities=req.top_entities,
        )
        return PlainTextResponse(content, media_type="text/markdown")
    except Exception as e:
        logger.error(f"Daily brief generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest")
async def get_latest_brief():
    """
    Get the most recent daily brief (from file cache).
    Does NOT regenerate — returns the last generated report.
    """
    reports_dir = Path("data/reports")
    if not reports_dir.exists():
        raise HTTPException(status_code=404, detail="No reports directory")

    # Find most recent daily_brief file
    briefs = sorted(reports_dir.glob("daily_brief_*.md"), reverse=True)
    if not briefs:
        # Fall back to any briefing file
        briefs = sorted(reports_dir.glob("*briefing*.md"), reverse=True)

    if not briefs:
        raise HTTPException(status_code=404, detail="No brief found. Generate one first via POST /api/v1/brief/generate")

    with open(briefs[0], "r", encoding="utf-8") as f:
        content = f.read()

    return PlainTextResponse(content, media_type="text/markdown")


@router.get("/history")
async def list_brief_history(limit: int = 10):
    """List recent daily briefs."""
    reports_dir = Path("data/reports")
    if not reports_dir.exists():
        return {"briefs": []}

    briefs = sorted(reports_dir.glob("daily_brief_*.md"), reverse=True)[:limit]
    return {
        "briefs": [
            {
                "filename": b.name,
                "date": b.stem.replace("daily_brief_", ""),
                "size_kb": round(b.stat().st_size / 1024, 1),
            }
            for b in briefs
        ]
    }


@router.post("/scan-alerts")
async def scan_intelligence_alerts(top_n: int = 50):
    """
    Run intelligence alert scanner against top entities.

    Detects: stealth signals, trend emergence, momentum anomalies,
    source divergence.
    """
    try:
        from utils.intelligence_alerts import IntelligenceAlertScanner

        scanner = IntelligenceAlertScanner()
        new_alerts = scanner.scan_all(top_n=top_n)

        return {
            "new_alerts": len(new_alerts),
            "alerts": [a.to_dict() for a in new_alerts],
            "stats": scanner.engine.get_stats(),
        }
    except Exception as e:
        logger.error(f"Intelligence scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
