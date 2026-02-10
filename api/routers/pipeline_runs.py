"""
Pipeline Runs API Router

Provides:
- POST /api/v1/pipelines/run       — trigger a pipeline run with SSE streaming
- GET  /api/v1/pipelines/runs       — list past runs
- GET  /api/v1/pipelines/runs/{id}  — get a specific run
- GET  /api/v1/pipelines/stats      — aggregate run stats
- GET  /api/v1/pipelines            — list registered pipelines

SSE streaming lets the React dashboard show live progress:
  "Scraping TechCrunch... 12/40 sources done... Scoring articles..."
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

# Ensure project root is on path
_app_dir = Path(__file__).parent.parent.parent.resolve()
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from pipeline.base import (
    BasePipeline,
    EventType,
    PipelineConfig,
    PipelineEvent,
    PipelineRegistry,
    PipelineResult,
    PipelineStatus,
)
from pipeline.run_store import RunStore

router = APIRouter(prefix="/api/v1/pipelines", tags=["pipelines"])

# ---------------------------------------------------------------------------
# Shared state (initialized on startup)
# ---------------------------------------------------------------------------

_registry = PipelineRegistry()
_store = RunStore()
_active_runs: dict[str, bool] = {}  # run_id -> is_running


def get_registry() -> PipelineRegistry:
    """Get or initialize the pipeline registry."""
    if len(_registry) == 0:
        _register_defaults()
    return _registry


def _register_defaults():
    """Register the built-in pipelines."""
    try:
        from pipeline.news_pipeline import NewsPipeline

        _registry.register(NewsPipeline())
    except Exception as e:
        logger.warning(f"Failed to register NewsPipeline: {e}")

    # Future: register product, investing, china_ai pipelines here


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    pipeline_id: str = "news"
    days_back: int = 7
    top_n: int = 10
    categories: Optional[list[str]] = None
    dry_run: bool = False


class RunSummary(BaseModel):
    run_id: str
    pipeline_id: str
    status: str
    started_at: float
    execution_time: Optional[float] = None
    articles_scraped: int = 0
    articles_selected: int = 0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_pipelines():
    """List all registered pipelines."""
    registry = get_registry()
    return {
        "pipelines": [
            {
                "id": p.pipeline_id,
                "name": p.display_name,
                "sources": len(p.get_sources()),
                "default_categories": p.get_default_categories(),
            }
            for p in registry.all()
        ]
    }


@router.post("/run")
async def trigger_run(req: RunRequest):
    """
    Trigger a pipeline run and stream progress via SSE.

    Returns: text/event-stream with JSON events.

    Event types:
    - stage_start: A pipeline stage began
    - stage_end: A stage completed with metrics
    - progress: Incremental progress within a stage
    - log: Informational message
    - metric: A numeric metric (e.g., articles_scraped=150)
    - error: A non-fatal error
    - result: The final PipelineResult (last event)

    Example event:
        data: {"event":"stage_end","pipeline":"news","stage":"scrape","message":"Scraped 150 articles","data":{"items_out":150}}
    """
    registry = get_registry()
    pipeline = registry.get(req.pipeline_id)

    if not pipeline:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline '{req.pipeline_id}' not found. Available: {registry.ids()}",
        )

    config = PipelineConfig(
        target_date=datetime.now(),
        days_back=req.days_back,
        top_n=req.top_n,
        categories=req.categories,
        dry_run=req.dry_run,
    )

    run_id = _store.create_run(
        pipeline_id=req.pipeline_id,
        config={
            "days_back": req.days_back,
            "top_n": req.top_n,
            "categories": req.categories,
            "dry_run": req.dry_run,
        },
    )

    async def event_stream():
        _active_runs[run_id] = True

        # Send run_id as first event so client can track
        yield _sse({"event": "run_started", "run_id": run_id, "pipeline": req.pipeline_id})

        try:
            async for event in pipeline.run(config):
                # Persist event
                _store.log_event(run_id, event)

                # Stream to client
                yield _sse(event.to_dict())

                # If this is the final result, persist it
                if event.event_type == EventType.RESULT:
                    result_data = event.data.get("result", {})
                    result = PipelineResult(
                        pipeline_id=req.pipeline_id,
                        status=PipelineStatus(result_data.get("status", "completed")),
                        report_path=result_data.get("report_path"),
                        articles_scraped=result_data.get("articles_scraped", 0),
                        articles_selected=result_data.get("articles_selected", 0),
                        execution_time=result_data.get("execution_time", 0),
                        error=result_data.get("error"),
                        metadata=result_data.get("metadata", {}),
                    )
                    _store.complete_run(run_id, result)

                # Yield control to event loop
                await asyncio.sleep(0)

        except Exception as e:
            logger.error(f"Pipeline run {run_id} failed: {e}")
            _store.fail_run(run_id, str(e))
            yield _sse({"event": "error", "run_id": run_id, "message": str(e)})

        finally:
            _active_runs.pop(run_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Run-ID": run_id,
        },
    )


@router.get("/runs")
async def list_runs(
    pipeline_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List past pipeline runs."""
    runs = _store.list_runs(
        pipeline_id=pipeline_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {"runs": runs, "count": len(runs)}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, include_events: bool = False):
    """Get details of a specific run."""
    run = _store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if include_events:
        run["events"] = _store.get_events(run_id)

    run["is_active"] = run_id in _active_runs
    return run


@router.get("/stats")
async def pipeline_stats(
    pipeline_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
):
    """Get aggregate statistics for pipeline runs."""
    return _store.get_stats(pipeline_id=pipeline_id, days=days)


@router.get("/active")
async def active_runs():
    """List currently running pipelines."""
    return {
        "active": list(_active_runs.keys()),
        "count": len(_active_runs),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse(data: dict) -> str:
    """Format a dict as an SSE event."""
    return f"data: {json.dumps(data, default=str)}\n\n"
