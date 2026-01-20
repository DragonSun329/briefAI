"""FastAPI backend for briefAI dashboard."""

import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}