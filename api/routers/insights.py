"""Insights and dates API endpoints."""

from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel

# Import CrossPipelineAnalyzer
import sys
_app_dir = Path(__file__).parent.parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from utils.cross_pipeline_analyzer import CrossPipelineAnalyzer


router = APIRouter(prefix="/api", tags=["insights"])

# Shared analyzer instance
_analyzer: Optional[CrossPipelineAnalyzer] = None


def get_analyzer() -> CrossPipelineAnalyzer:
    """Get or create analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = CrossPipelineAnalyzer()
    return _analyzer


class DateResponse(BaseModel):
    dates: List[str]
    latest: Optional[str]


class PipelineStats(BaseModel):
    news: int
    product: int
    investing: int


class TopEntity(BaseModel):
    name: str
    mentions: int
    pipelines: int


class SummaryStats(BaseModel):
    total_articles: int
    pipeline_counts: PipelineStats
    cross_pipeline_entities: int
    total_entities: int
    top_entity: Optional[TopEntity]


class BubbleDataPoint(BaseModel):
    name: str
    entity_type: str
    x: int
    y: int
    size: float
    color: str
    dominant_pipeline: str
    hover: str
    pipeline_breakdown: Dict[str, int]


class HotEntity(BaseModel):
    entity_name: str
    entity_type: str
    total_mentions: int
    pipeline_count: int
    pipeline_mentions: Dict[str, int]


class InsightsResponse(BaseModel):
    summary: SummaryStats
    bubble_data: List[BubbleDataPoint]
    hot_entities: List[HotEntity]


@router.get("/dates", response_model=DateResponse)
def get_available_dates():
    """Get available dates for the date picker."""
    analyzer = get_analyzer()
    dates = analyzer.get_available_dates()
    return DateResponse(
        dates=dates,
        latest=dates[0] if dates else None
    )


@router.get("/insights", response_model=InsightsResponse)
def get_insights(date: str = Query(..., description="Date in YYYYMMDD format")):
    """Get insights data: summary stats, bubble chart, hot entities."""
    analyzer = get_analyzer()
    analyzer.load_pipelines_for_date(date)

    stats = analyzer.get_summary_stats()
    bubble_data = analyzer.get_bubble_chart_data()
    hot_entities = analyzer.get_hot_entities(10)

    return InsightsResponse(
        summary=SummaryStats(
            total_articles=stats["total_articles"],
            pipeline_counts=PipelineStats(**stats["pipeline_counts"]),
            cross_pipeline_entities=stats["cross_pipeline_entities"],
            total_entities=stats["total_entities"],
            top_entity=TopEntity(**stats["top_entity"]) if stats.get("top_entity") else None,
        ),
        bubble_data=[BubbleDataPoint(**d) for d in bubble_data],
        hot_entities=[
            HotEntity(
                entity_name=e.entity_name,
                entity_type=e.entity_type,
                total_mentions=e.total_mentions,
                pipeline_count=e.pipeline_count,
                pipeline_mentions=e.pipeline_mentions,
            )
            for e in hot_entities
        ],
    )