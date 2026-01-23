"""FastAPI backend for briefAI dashboard."""

import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from api.routers import insights
from api.routers import articles
from api.routers import companies
from api.routers import signals
from api.routers import buckets
from api.routers import conviction
from api.routers import backtest
from api.routers import health

app.include_router(insights.router)
app.include_router(articles.router)
app.include_router(companies.router)
app.include_router(signals.router)
app.include_router(buckets.router)
app.include_router(conviction.router)
app.include_router(backtest.router)
app.include_router(health.router)


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# Serve React frontend in production
_frontend_dist = _api_dir.parent / "frontend" / "dist"

if _frontend_dist.exists():
    from fastapi.responses import FileResponse

    # Serve static assets
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA - all non-API routes go to index.html."""
        file_path = _frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist / "index.html")