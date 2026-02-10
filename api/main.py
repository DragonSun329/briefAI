"""FastAPI backend for briefAI dashboard.

Enhanced API with:
- REST API v1 with pagination, filtering, sorting
- API key authentication with tiered rate limiting
- Bulk export (CSV, JSON, Parquet)
- WebSocket real-time feeds
- SQL-like query builder
"""

import os
import sys
import time
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

# Setup paths
_api_dir = Path(__file__).parent.resolve()
_app_dir = _api_dir.parent
_trend_radar_path = _app_dir / ".worktrees" / "trend-radar"
_db_path = _trend_radar_path / "data" / "trend_radar.db"

# Configure environment before imports
os.environ["TREND_RADAR_DB_URL"] = f"sqlite:///{_db_path.as_posix()}"

if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))
if str(_trend_radar_path) not in sys.path:
    sys.path.append(str(_trend_radar_path))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    yield


app = FastAPI(
    title="briefAI Dashboard API",
    description="""
## briefAI - Bloomberg Terminal for AI Trends

A comprehensive API for AI industry signal analysis and trend tracking.

### Features
- **Signal Analysis**: Multi-dimensional scoring (technical, company, financial, product, media)
- **Divergence Detection**: Identify opportunities and risks from signal disagreements
- **Real-time Updates**: WebSocket feeds for live data
- **Bulk Export**: CSV, JSON, Parquet exports for quant workflows
- **Query Builder**: SQL-like queries for power users (premium)

### Authentication
Most endpoints are publicly accessible. For higher rate limits and premium features,
pass an API key via `X-API-Key` header or `api_key` query parameter.

### Rate Limits
- Free: 100 requests/minute
- Premium: 1000 requests/minute
- Enterprise: 5000 requests/minute
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"],
)


# Request timing middleware
@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    """Add X-Response-Time header to all responses."""
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    response.headers["X-Response-Time"] = f"{process_time:.2f}ms"
    
    # Add rate limit headers if available
    if hasattr(request.state, "rate_limit_remaining"):
        response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)
        response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)
    
    return response


# =============================================================================
# Original Routers (existing functionality)
# =============================================================================
from api.routers import insights
from api.routers import articles
from api.routers import companies
from api.routers import signals
from api.routers import buckets
from api.routers import conviction
from api.routers import backtest
from api.routers import health
from api.routers import research
from api.routers import validation

app.include_router(insights.router)
app.include_router(articles.router)
app.include_router(companies.router)
app.include_router(signals.router)
app.include_router(buckets.router)
app.include_router(conviction.router)
app.include_router(backtest.router)
app.include_router(health.router)
app.include_router(research.router)
app.include_router(validation.router)
app.include_router(validation.predictions_router, prefix="/api/predictions", tags=["predictions"])


# =============================================================================
# New API v1 Routers (enhanced functionality)
# =============================================================================
from api.routers import v1
from api.routers import export
from api.routers import correlations
from api.routers import verticals
from api.routers import pipeline_runs
from api.routers import agents as agents_router
from api.routers import orchestrator as orchestrator_router
from api.routers import daily_brief as daily_brief_router

app.include_router(v1.router)
app.include_router(export.router)
app.include_router(correlations.router)
app.include_router(verticals.router)
app.include_router(pipeline_runs.router)
app.include_router(agents_router.router)
app.include_router(orchestrator_router.router)
app.include_router(daily_brief_router.router)


# =============================================================================
# WebSocket Endpoint
# =============================================================================
from api.websocket import websocket_endpoint, manager

@app.websocket("/ws")
async def websocket_route(
    websocket: WebSocket,
    api_key: str = Query(None),
):
    """
    WebSocket endpoint for real-time updates.
    
    Connect with optional API key for authenticated access:
    ws://localhost:8000/ws?api_key=your_key
    
    Protocol:
    - Subscribe: {"type": "subscribe", "subscription_type": "entity", "target": "openai"}
    - Unsubscribe: {"type": "unsubscribe", "subscription_type": "entity", "target": "openai"}
    - Ping: {"type": "ping"}
    
    Subscription types:
    - all: Receive all updates
    - entity: Updates for specific entity
    - category: Updates for signal category
    - divergence: Divergence alerts only
    """
    await websocket_endpoint(websocket, api_key)


@app.get("/ws/stats")
async def websocket_stats():
    """Get WebSocket connection statistics."""
    return manager.get_stats()


# =============================================================================
# Health & Info Endpoints
# =============================================================================

@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/info")
def api_info():
    """API information and available endpoints."""
    return {
        "name": "briefAI API",
        "version": "1.0.0",
        "description": "Bloomberg Terminal for AI Trends",
        "endpoints": {
            "docs": "/api/docs",
            "openapi": "/api/openapi.json",
            "health": "/api/health",
            "websocket": "/ws",
            "v1": {
                "signals": "/api/v1/signals/{entity_id}/history",
                "entities": "/api/v1/entities/search",
                "divergences": "/api/v1/divergences/active",
                "events": "/api/v1/events/{entity_id}",
                "query": "/api/v1/query",
                "export": "/api/v1/export/*",
            },
            "pipelines": {
                "list": "GET /api/v1/pipelines",
                "run": "POST /api/v1/pipelines/run (SSE stream)",
                "runs": "GET /api/v1/pipelines/runs",
                "run_detail": "GET /api/v1/pipelines/runs/{run_id}",
                "stats": "GET /api/v1/pipelines/stats",
                "active": "GET /api/v1/pipelines/active",
            },
            "agents": {
                "list": "GET /api/v1/agents",
                "detail": "GET /api/v1/agents/{agent_id}",
                "run": "POST /api/v1/agents/{agent_id}/run",
            },
            "orchestrator": {
                "query": "POST /api/v1/orchestrator/query (SSE stream)",
                "agents": "GET /api/v1/orchestrator/agents",
                "conversation": "GET /api/v1/orchestrator/conversations/{id}",
            },
        },
        "authentication": {
            "header": "X-API-Key",
            "query_param": "api_key",
            "tiers": ["free", "premium", "enterprise"],
        },
    }


# Serve React frontend in production
_frontend_dist = _api_dir.parent / "frontend" / "dist"

if _frontend_dist.exists():
    from fastapi.responses import FileResponse

    # Serve static assets
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA - all non-API routes go to index.html."""
        # Don't serve SPA for API or WS routes
        if full_path.startswith("api/") or full_path.startswith("ws"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        
        file_path = _frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist / "index.html")