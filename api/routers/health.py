"""Pipeline health API endpoints."""

from pathlib import Path
import sys

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

_app_dir = Path(__file__).parent.parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from utils.pipeline_status import PipelineStatusCollector


router = APIRouter(prefix="/api/health", tags=["health"])


class ScraperStatusOut(BaseModel):
    name: str
    last_run: Optional[str]
    status: str
    record_count: int
    source_file: Optional[str]
    freshness_hours: int


class PipelineStatusOut(BaseModel):
    name: str
    last_run: Optional[str]
    status: str
    output_count: int
    output_location: Optional[str]


class DatabaseStatusOut(BaseModel):
    name: str
    path: str
    size_mb: float
    record_count: int
    table_count: int
    health: str


class CacheStatusOut(BaseModel):
    name: str
    path: str
    size_mb: float
    file_count: int
    oldest_file: Optional[str]
    newest_file: Optional[str]


class SystemHealthOut(BaseModel):
    scrapers: List[ScraperStatusOut]
    pipelines: List[PipelineStatusOut]
    databases: List[DatabaseStatusOut]
    caches: List[CacheStatusOut]
    healthy_count: int
    warning_count: int
    error_count: int
    overall_status: str
    checked_at: str


@router.get("/pipeline-status", response_model=SystemHealthOut)
def get_pipeline_status():
    """Get full system health status."""
    collector = PipelineStatusCollector()
    health = collector.get_system_health()

    return SystemHealthOut(
        scrapers=[ScraperStatusOut(**s.__dict__) for s in health.scrapers],
        pipelines=[PipelineStatusOut(**p.__dict__) for p in health.pipelines],
        databases=[DatabaseStatusOut(**d.__dict__) for d in health.databases],
        caches=[CacheStatusOut(**c.__dict__) for c in health.caches],
        healthy_count=health.healthy_count,
        warning_count=health.warning_count,
        error_count=health.error_count,
        overall_status=health.overall_status,
        checked_at=health.checked_at,
    )


@router.get("/scrapers")
def get_scraper_status():
    """Get scraper status only."""
    collector = PipelineStatusCollector()
    return {"scrapers": [s.__dict__ for s in collector.get_scraper_status()]}


@router.get("/databases")
def get_database_status():
    """Get database status only."""
    collector = PipelineStatusCollector()
    return {"databases": [d.__dict__ for d in collector.get_database_status()]}


@router.get("/caches")
def get_cache_status():
    """Get cache status only."""
    collector = PipelineStatusCollector()
    return {"caches": [c.__dict__ for c in collector.get_cache_status()]}