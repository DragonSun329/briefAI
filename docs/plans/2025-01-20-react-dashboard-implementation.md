# React Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Streamlit dashboard with React + FastAPI for proper sorting, filtering, and UX control.

**Architecture:** FastAPI backend wraps existing Python modules (CrossPipelineAnalyzer, SignalStore, generate_shortlist), serves JSON. React frontend handles all UI with client-side sorting/filtering/pagination.

**Tech Stack:** FastAPI, React + Vite, Recharts, TanStack Table, Tailwind CSS

---

## Task 1: FastAPI Backend Setup

**Files:**
- Create: `api/main.py`
- Create: `api/routers/__init__.py`
- Create: `api/requirements.txt`

**Step 1: Create api directory structure**

```bash
mkdir -p api/routers
```

**Step 2: Create requirements.txt**

Create `api/requirements.txt`:
```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pydantic>=2.0.0
python-multipart>=0.0.6
```

**Step 3: Create main.py with CORS and health check**

Create `api/main.py`:
```python
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


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
```

**Step 4: Test the server starts**

Run: `cd api && uvicorn main:app --reload --port 8000`
Expected: Server starts, `http://localhost:8000/api/health` returns `{"status":"ok"}`

**Step 5: Commit**

```bash
git add api/
git commit -m "feat: add FastAPI backend skeleton with health check"
```

---

## Task 2: Insights & Dates API Router

**Files:**
- Create: `api/routers/insights.py`
- Modify: `api/main.py` (add router import)

**Step 1: Create insights router**

Create `api/routers/insights.py`:
```python
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
```

**Step 2: Register router in main.py**

Add to `api/main.py` after the health check:
```python
from api.routers import insights

app.include_router(insights.router)
```

**Step 3: Test the endpoints**

Run server and test:
- `GET /api/dates` should return list of available dates
- `GET /api/insights?date=20260115` should return insights data

**Step 4: Commit**

```bash
git add api/
git commit -m "feat: add insights and dates API endpoints"
```

---

## Task 3: Articles API Router

**Files:**
- Create: `api/routers/articles.py`
- Modify: `api/main.py` (add router import)

**Step 1: Create articles router**

Create `api/routers/articles.py`:
```python
"""Articles API endpoints for news/product/investing pipelines."""

from typing import List, Dict, Any, Optional
from pathlib import Path

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

import sys
_app_dir = Path(__file__).parent.parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from utils.cross_pipeline_analyzer import CrossPipelineAnalyzer


router = APIRouter(prefix="/api", tags=["articles"])

_analyzer: Optional[CrossPipelineAnalyzer] = None


def get_analyzer() -> CrossPipelineAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = CrossPipelineAnalyzer()
    return _analyzer


class SearchableEntities(BaseModel):
    companies: List[str] = []
    models: List[str] = []
    people: List[str] = []


class Article(BaseModel):
    id: str
    title: str
    url: str
    source: str
    source_id: str
    weighted_score: float
    content: Optional[str] = None
    paraphrased_content: Optional[str] = None
    published_date: Optional[str] = None
    focus_tags: List[str] = []
    searchable_entities: SearchableEntities = SearchableEntities()


class ArticlesResponse(BaseModel):
    pipeline_id: str
    pipeline_name: str
    date: str
    articles: List[Article]
    total: int


@router.get("/articles/{pipeline}", response_model=ArticlesResponse)
def get_articles(
    pipeline: str,
    date: str = Query(..., description="Date in YYYYMMDD format"),
):
    """Get articles for a specific pipeline."""
    if pipeline not in ["news", "product", "investing"]:
        raise HTTPException(status_code=400, detail="Invalid pipeline. Use: news, product, investing")

    analyzer = get_analyzer()
    pipelines = analyzer.load_pipelines_for_date(date)

    if pipeline not in pipelines:
        return ArticlesResponse(
            pipeline_id=pipeline,
            pipeline_name=pipeline.title(),
            date=date,
            articles=[],
            total=0,
        )

    pdata = pipelines[pipeline]

    articles = []
    for a in pdata.articles:
        entities = a.get("searchable_entities", {})
        articles.append(Article(
            id=a.get("id", ""),
            title=a.get("title", ""),
            url=a.get("url", ""),
            source=a.get("source", ""),
            source_id=a.get("source_id", ""),
            weighted_score=a.get("weighted_score", 0),
            content=a.get("content"),
            paraphrased_content=a.get("paraphrased_content"),
            published_date=a.get("published_date"),
            focus_tags=a.get("focus_tags", []),
            searchable_entities=SearchableEntities(
                companies=entities.get("companies", []),
                models=entities.get("models", []),
                people=entities.get("people", []),
            ),
        ))

    return ArticlesResponse(
        pipeline_id=pipeline,
        pipeline_name=pdata.pipeline_name,
        date=date,
        articles=articles,
        total=len(articles),
    )
```

**Step 2: Register router in main.py**

Add to `api/main.py`:
```python
from api.routers import articles

app.include_router(articles.router)
```

**Step 3: Test endpoint**

Run: `GET /api/articles/news?date=20260115`
Expected: List of news articles with full details

**Step 4: Commit**

```bash
git add api/
git commit -m "feat: add articles API endpoint for all pipelines"
```

---

## Task 4: Companies (Shortlist) API Router

**Files:**
- Create: `api/routers/companies.py`
- Modify: `api/main.py`

**Step 1: Create companies router**

Create `api/routers/companies.py`:
```python
"""Companies/Shortlist API endpoints."""

import os
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

import sys
_app_dir = Path(__file__).parent.parent.parent
_trend_radar_path = _app_dir / ".worktrees" / "trend-radar"
_db_path = _trend_radar_path / "data" / "trend_radar.db"

os.environ["TREND_RADAR_DB_URL"] = f"sqlite:///{_db_path.as_posix()}"

if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))
if str(_trend_radar_path) not in sys.path:
    sys.path.append(str(_trend_radar_path))

from trend_radar.models import get_session
from trend_radar.shortlist import generate_shortlist


router = APIRouter(prefix="/api", tags=["companies"])


class CompanyEntry(BaseModel):
    id: int
    name: str
    category: str
    category_zh: str
    funding_stage: str
    funding_stage_zh: str
    description: Optional[str] = None
    sources: List[str]
    source_count: int
    rising_score: Optional[float] = None
    first_seen: Optional[str] = None
    website: Optional[str] = None
    total_funding: Optional[float] = None
    employee_count: Optional[str] = None
    cb_rank: Optional[int] = None
    estimated_revenue: Optional[str] = None
    founded_year: Optional[int] = None
    # Computed for frontend sorting
    funding_millions: float = 0
    revenue_millions: float = 0


class FiltersResponse(BaseModel):
    categories: List[dict]
    stages: List[dict]


class CompaniesResponse(BaseModel):
    companies: List[CompanyEntry]
    total: int
    categories_available: List[str]
    stages_available: List[str]
    generated_at: str


def parse_revenue_to_millions(revenue_str: Optional[str]) -> float:
    """Parse revenue string like '$10M to $50M' to numeric (upper bound in millions)."""
    if not revenue_str or revenue_str == '-':
        return 0
    import re
    matches = re.findall(r'\$?([\d.]+)\s*([BMK])?', revenue_str.upper())
    if not matches:
        return 0
    amount, multiplier = matches[-1]
    amount = float(amount)
    if multiplier == 'B':
        return amount * 1000
    elif multiplier == 'M':
        return amount
    elif multiplier == 'K':
        return amount / 1000
    return amount / 1_000_000


@router.get("/companies", response_model=CompaniesResponse)
def get_companies():
    """Get all companies for the shortlist table."""
    session = get_session()
    try:
        result = generate_shortlist(session, limit=1000)

        companies = []
        for entry in result.entries:
            first_seen_str = entry.first_seen.isoformat() if entry.first_seen else None
            funding_m = round(entry.total_funding / 1_000_000) if entry.total_funding else 0
            revenue_m = round(parse_revenue_to_millions(entry.estimated_revenue))

            companies.append(CompanyEntry(
                id=entry.id,
                name=entry.name,
                category=entry.category,
                category_zh=entry.category_zh,
                funding_stage=entry.funding_stage,
                funding_stage_zh=entry.funding_stage_zh,
                description=entry.description,
                sources=entry.sources,
                source_count=entry.source_count,
                rising_score=entry.rising_score,
                first_seen=first_seen_str,
                website=entry.website,
                total_funding=entry.total_funding,
                employee_count=entry.employee_count,
                cb_rank=entry.cb_rank,
                estimated_revenue=entry.estimated_revenue,
                founded_year=entry.founded_year,
                funding_millions=funding_m,
                revenue_millions=revenue_m,
            ))

        return CompaniesResponse(
            companies=companies,
            total=len(companies),
            categories_available=result.categories_available,
            stages_available=result.stages_available,
            generated_at=result.generated_at,
        )
    finally:
        session.close()


@router.get("/companies/filters", response_model=FiltersResponse)
def get_company_filters():
    """Get available filter options for companies."""
    from trend_radar.taxonomy import load_taxonomy

    taxonomy = load_taxonomy()

    return FiltersResponse(
        categories=[
            {"id": c["id"], "name_zh": c["name_zh"]}
            for c in taxonomy["categories"]
        ],
        stages=[
            {"id": s["id"], "name_zh": s["name_zh"]}
            for s in taxonomy["funding_stages"]
        ],
    )
```

**Step 2: Register router**

Add to `api/main.py`:
```python
from api.routers import companies

app.include_router(companies.router)
```

**Step 3: Test endpoint**

Run: `GET /api/companies`
Expected: All companies with numeric funding/revenue fields for sorting

**Step 4: Commit**

```bash
git add api/
git commit -m "feat: add companies API with numeric sort fields"
```

---

## Task 5: Signals API Router

**Files:**
- Create: `api/routers/signals.py`
- Modify: `api/main.py`

**Step 1: Create signals router**

Create `api/routers/signals.py`:
```python
"""Signal Radar API endpoints."""

from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel

import sys
_app_dir = Path(__file__).parent.parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from utils.signal_store import SignalStore


router = APIRouter(prefix="/api/signals", tags=["signals"])

_store: Optional[SignalStore] = None


def get_store() -> SignalStore:
    global _store
    if _store is None:
        _store = SignalStore()
    return _store


class SignalScore(BaseModel):
    category: str
    value: float
    confidence: float


class EntityProfile(BaseModel):
    entity_id: str
    name: str
    entity_type: str
    composite_score: float
    scores: List[SignalScore]


class DivergenceAlert(BaseModel):
    entity_id: str
    entity_name: str
    signal_a: str
    signal_b: str
    divergence_score: float
    interpretation: str
    detected_at: str


class SignalsStatsResponse(BaseModel):
    total_entities: int
    entities_by_type: Dict[str, int]
    total_observations: int
    active_divergences: int


@router.get("/entities", response_model=List[EntityProfile])
def get_top_entities(limit: int = Query(default=50, le=100)):
    """Get top entities by composite signal score."""
    store = get_store()
    profiles = store.get_top_profiles(limit=limit)

    result = []
    for p in profiles:
        scores = store.get_scores_for_entity(p.entity_id)
        result.append(EntityProfile(
            entity_id=p.entity_id,
            name=p.entity.name if p.entity else p.entity_id,
            entity_type=p.entity.entity_type.value if p.entity else "unknown",
            composite_score=p.composite_score,
            scores=[
                SignalScore(
                    category=s.category.value,
                    value=s.normalized_value,
                    confidence=s.confidence,
                )
                for s in scores
            ],
        ))

    return result


@router.get("/divergence", response_model=List[DivergenceAlert])
def get_divergences():
    """Get active signal divergences (opportunities/risks)."""
    store = get_store()
    divergences = store.get_active_divergences()

    return [
        DivergenceAlert(
            entity_id=d.entity_id,
            entity_name=d.entity.name if d.entity else d.entity_id,
            signal_a=d.signal_a.value,
            signal_b=d.signal_b.value,
            divergence_score=d.divergence_score,
            interpretation=d.interpretation.value,
            detected_at=d.detected_at.isoformat(),
        )
        for d in divergences
    ]


@router.get("/stats", response_model=SignalsStatsResponse)
def get_signals_stats():
    """Get signal store statistics."""
    store = get_store()
    stats = store.get_stats()

    return SignalsStatsResponse(
        total_entities=stats["total_entities"],
        entities_by_type=stats["entities_by_type"],
        total_observations=stats["total_observations"],
        active_divergences=stats["active_divergences"],
    )
```

**Step 2: Register router**

Add to `api/main.py`:
```python
from api.routers import signals

app.include_router(signals.router)
```

**Step 3: Test endpoints**

Run: `GET /api/signals/entities?limit=10`
Expected: Top 10 entities with signal scores

**Step 4: Commit**

```bash
git add api/
git commit -m "feat: add signals API for entity scores and divergences"
```

---

## Task 6: Buckets API Router

**Files:**
- Create: `api/routers/buckets.py`
- Modify: `api/main.py`

**Step 1: Create buckets router**

Create `api/routers/buckets.py`:
```python
"""Bucket Radar API endpoints."""

import json
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import sys
_app_dir = Path(__file__).parent.parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from utils.bucket_alerts import BucketAlertDetector
from utils.bucket_models import BucketProfile, BucketAlert


router = APIRouter(prefix="/api/buckets", tags=["buckets"])

BUCKET_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "cache" / "bucket_profiles.json"


class BucketProfileOut(BaseModel):
    bucket_id: str
    bucket_name: str
    week_start: str
    tms: float
    ccs: float
    eis_offensive: Optional[float] = None
    eis_defensive: Optional[float] = None
    nas: float
    pms: Optional[float] = None
    css: Optional[float] = None
    heat_score: float
    lifecycle_state: str
    hype_cycle_phase: str
    top_technical_entities: List[str]
    top_capital_entities: List[str]
    entity_count: int
    github_repos: int
    hf_models: int
    article_count: int


class BucketAlertOut(BaseModel):
    bucket_id: str
    bucket_name: str
    alert_type: str
    severity: str
    message: str
    tms: float
    ccs: float


class BucketsResponse(BaseModel):
    profiles: List[BucketProfileOut]
    generated_at: str
    week_start: str


def load_bucket_data() -> Dict[str, Any]:
    """Load bucket profiles from cache."""
    if not BUCKET_CACHE_PATH.exists():
        return {}

    with open(BUCKET_CACHE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("bucket_profiles", {})


@router.get("", response_model=BucketsResponse)
def get_all_buckets():
    """Get all bucket profiles for the radar chart."""
    data = load_bucket_data()

    if not data:
        return BucketsResponse(profiles=[], generated_at="", week_start="")

    profiles = []
    for p in data.get("profiles", []):
        profiles.append(BucketProfileOut(
            bucket_id=p["bucket_id"],
            bucket_name=p["bucket_name"],
            week_start=p["week_start"],
            tms=p.get("tms", 0),
            ccs=p.get("ccs", 0),
            eis_offensive=p.get("eis_offensive"),
            eis_defensive=p.get("eis_defensive"),
            nas=p.get("nas", 0),
            pms=p.get("pms"),
            css=p.get("css"),
            heat_score=p.get("heat_score", 0),
            lifecycle_state=p.get("lifecycle_state", "unknown"),
            hype_cycle_phase=p.get("hype_cycle_phase", "unknown"),
            top_technical_entities=p.get("top_technical_entities", []),
            top_capital_entities=p.get("top_capital_entities", []),
            entity_count=p.get("entity_count", 0),
            github_repos=p.get("github_repos", 0),
            hf_models=p.get("hf_models", 0),
            article_count=p.get("article_count", 0),
        ))

    return BucketsResponse(
        profiles=profiles,
        generated_at=data.get("generated_at", ""),
        week_start=data.get("week_start", ""),
    )


@router.get("/{bucket_id}", response_model=BucketProfileOut)
def get_bucket(bucket_id: str):
    """Get a single bucket by ID."""
    data = load_bucket_data()

    for p in data.get("profiles", []):
        if p["bucket_id"] == bucket_id:
            return BucketProfileOut(**p)

    raise HTTPException(status_code=404, detail=f"Bucket {bucket_id} not found")


@router.get("/alerts/active", response_model=List[BucketAlertOut])
def get_bucket_alerts():
    """Get active bucket alerts (divergences)."""
    data = load_bucket_data()

    if not data:
        return []

    # Convert profiles to BucketProfile objects for alert detection
    profiles = []
    for p in data.get("profiles", []):
        try:
            profile = BucketProfile(
                bucket_id=p["bucket_id"],
                bucket_name=p["bucket_name"],
                week_start=p["week_start"],
                tms=p.get("tms", 0),
                ccs=p.get("ccs", 0),
                nas=p.get("nas", 0),
                heat_score=p.get("heat_score", 0),
            )
            profiles.append(profile)
        except Exception:
            continue

    detector = BucketAlertDetector()
    alerts = detector.detect_alerts(profiles)

    return [
        BucketAlertOut(
            bucket_id=a.bucket_id,
            bucket_name=a.bucket_name,
            alert_type=a.alert_type,
            severity=a.severity,
            message=a.message,
            tms=a.tms,
            ccs=a.ccs,
        )
        for a in alerts
    ]
```

**Step 2: Register router**

Add to `api/main.py`:
```python
from api.routers import buckets

app.include_router(buckets.router)
```

**Step 3: Test endpoints**

Run: `GET /api/buckets`
Expected: All bucket profiles with scores

**Step 4: Commit**

```bash
git add api/
git commit -m "feat: add buckets API for trend radar data"
```

---

## Task 7: React Frontend Setup

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/App.jsx`
- Create: `frontend/src/index.css`

**Step 1: Initialize frontend directory**

```bash
mkdir -p frontend/src
```

**Step 2: Create package.json**

Create `frontend/package.json`:
```json
{
  "name": "briefai-dashboard",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.21.0",
    "@tanstack/react-table": "^8.11.0",
    "recharts": "^2.10.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.2.0",
    "vite": "^5.0.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.32",
    "autoprefixer": "^10.4.16"
  }
}
```

**Step 3: Create vite.config.js**

Create `frontend/vite.config.js`:
```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

**Step 4: Create tailwind.config.js**

Create `frontend/tailwind.config.js`:
```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

**Step 5: Create postcss.config.js**

Create `frontend/postcss.config.js`:
```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

**Step 6: Create index.html**

Create `frontend/index.html`:
```html
<!DOCTYPE html>
<html lang="zh">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>CEO智能仪表板</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

**Step 7: Create src/index.css**

Create `frontend/src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
}
```

**Step 8: Create src/main.jsx**

Create `frontend/src/main.jsx`:
```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

**Step 9: Create src/App.jsx (basic shell)**

Create `frontend/src/App.jsx`:
```jsx
import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'

function App() {
  const [dates, setDates] = useState([])
  const [selectedDate, setSelectedDate] = useState('')

  useEffect(() => {
    fetch('/api/dates')
      .then(res => res.json())
      .then(data => {
        setDates(data.dates)
        if (data.latest) setSelectedDate(data.latest)
      })
  }, [])

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        {/* Header */}
        <header className="bg-white shadow-sm border-b">
          <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
            <h1 className="text-2xl font-bold text-blue-600">CEO智能仪表板</h1>
            <select
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="border rounded px-3 py-2"
            >
              {dates.map(d => (
                <option key={d} value={d}>
                  {d.slice(0,4)}-{d.slice(4,6)}-{d.slice(6,8)}
                </option>
              ))}
            </select>
          </div>
        </header>

        {/* Navigation */}
        <nav className="bg-white border-b">
          <div className="max-w-7xl mx-auto px-4">
            <div className="flex space-x-8">
              {[
                { path: '/', label: '洞察', icon: '🔥' },
                { path: '/news', label: 'AI新闻', icon: '📰' },
                { path: '/product', label: '产品', icon: '🚀' },
                { path: '/investing', label: '投资', icon: '💰' },
                { path: '/shortlist', label: 'AI速查', icon: '🏢' },
                { path: '/signals', label: '信号雷达', icon: '📡' },
                { path: '/buckets', label: '趋势桶雷达', icon: '🎯' },
              ].map(({ path, label, icon }) => (
                <NavLink
                  key={path}
                  to={path}
                  className={({ isActive }) =>
                    `py-4 px-1 border-b-2 font-medium ${
                      isActive
                        ? 'border-blue-500 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    }`
                  }
                >
                  {icon} {label}
                </NavLink>
              ))}
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className="max-w-7xl mx-auto px-4 py-6">
          <Routes>
            <Route path="/" element={<div>洞察页面 - 开发中</div>} />
            <Route path="/news" element={<div>新闻页面 - 开发中</div>} />
            <Route path="/product" element={<div>产品页面 - 开发中</div>} />
            <Route path="/investing" element={<div>投资页面 - 开发中</div>} />
            <Route path="/shortlist" element={<div>速查页面 - 开发中</div>} />
            <Route path="/signals" element={<div>信号雷达 - 开发中</div>} />
            <Route path="/buckets" element={<div>趋势桶雷达 - 开发中</div>} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
```

**Step 10: Install dependencies and test**

```bash
cd frontend && npm install && npm run dev
```

Expected: Frontend runs on http://localhost:5173 with navigation tabs

**Step 11: Commit**

```bash
git add frontend/
git commit -m "feat: add React frontend shell with navigation"
```

---

## Task 8: useApi Hook

**Files:**
- Create: `frontend/src/hooks/useApi.js`

**Step 1: Create the hook**

Create `frontend/src/hooks/useApi.js`:
```javascript
import { useState, useEffect, useCallback } from 'react'

/**
 * Custom hook for API calls with loading/error states.
 *
 * @param {string} url - API endpoint
 * @param {object} options - Optional fetch options
 * @returns {{ data, loading, error, refetch }}
 */
export function useApi(url, options = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchData = useCallback(async () => {
    if (!url) {
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)

    try {
      const res = await fetch(url, options)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }
      const json = await res.json()
      setData(json)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [url, JSON.stringify(options)])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return { data, loading, error, refetch: fetchData }
}

/**
 * Lazy API hook - doesn't fetch on mount.
 */
export function useLazyApi() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const fetch = useCallback(async (url, options = {}) => {
    setLoading(true)
    setError(null)

    try {
      const res = await window.fetch(url, options)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }
      const json = await res.json()
      setData(json)
      return json
    } catch (err) {
      setError(err.message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  return { data, loading, error, fetch }
}
```

**Step 2: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat: add useApi hook for data fetching"
```

---

## Task 9: StatCard Component

**Files:**
- Create: `frontend/src/components/StatCard.jsx`

**Step 1: Create the component**

Create `frontend/src/components/StatCard.jsx`:
```jsx
/**
 * Stat card for displaying metric values.
 */
export default function StatCard({ icon, label, value, color = 'blue' }) {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    orange: 'bg-orange-50 text-orange-600',
    purple: 'bg-purple-50 text-purple-600',
  }

  return (
    <div className={`rounded-lg p-4 ${colorClasses[color]}`}>
      <div className="flex items-center gap-2 text-sm font-medium mb-1">
        <span>{icon}</span>
        <span>{label}</span>
      </div>
      <div className="text-3xl font-bold">{value}</div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/
git commit -m "feat: add StatCard component"
```

---

## Task 10: ArticleCard Component

**Files:**
- Create: `frontend/src/components/ArticleCard.jsx`

**Step 1: Create the component**

Create `frontend/src/components/ArticleCard.jsx`:
```jsx
import { useState } from 'react'

/**
 * Article card with expandable summary.
 */
export default function ArticleCard({ article, pipeline }) {
  const [expanded, setExpanded] = useState(false)

  const { title, url, source, weighted_score, paraphrased_content, content, focus_tags } = article

  const summary = paraphrased_content || content || ''
  const truncated = summary.length > 200 ? summary.slice(0, 200) + '...' : summary

  const scoreColor = weighted_score >= 8 ? 'bg-green-500' : weighted_score >= 6 ? 'bg-orange-500' : 'bg-red-500'

  const pipelineColors = {
    news: 'border-l-blue-500',
    product: 'border-l-green-500',
    investing: 'border-l-orange-500',
  }

  return (
    <div className={`bg-white rounded-lg shadow-sm border-l-4 ${pipelineColors[pipeline] || 'border-l-gray-300'} p-4 mb-3`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-semibold text-gray-900 hover:text-blue-600 line-clamp-2"
        >
          {title}
        </a>
        <span className={`${scoreColor} text-white text-xs px-2 py-1 rounded-full whitespace-nowrap`}>
          {weighted_score.toFixed(1)}
        </span>
      </div>

      <div className="text-sm text-gray-500 mb-2">
        来源: {source}
      </div>

      {focus_tags?.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {focus_tags.slice(0, 5).map(tag => (
            <span key={tag} className="bg-gray-100 text-gray-600 text-xs px-2 py-0.5 rounded">
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="text-sm text-gray-700">
        {expanded ? summary : truncated}
        {summary.length > 200 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="ml-1 text-blue-600 hover:underline"
          >
            {expanded ? '收起' : '展开'}
          </button>
        )}
      </div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/
git commit -m "feat: add ArticleCard component"
```

---

## Task 11: CompanyTable Component (TanStack Table)

**Files:**
- Create: `frontend/src/components/CompanyTable.jsx`

**Step 1: Create the sortable table component**

Create `frontend/src/components/CompanyTable.jsx`:
```jsx
import { useMemo, useState } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  flexRender,
} from '@tanstack/react-table'

/**
 * Format funding amount for display.
 */
function formatFunding(millions) {
  if (!millions || millions === 0) return '-'
  if (millions >= 1000) return `$${(millions / 1000).toFixed(1)}B`
  return `$${millions}M`
}

/**
 * Sortable company table with TanStack Table.
 */
export default function CompanyTable({ companies, categories, stages }) {
  const [sorting, setSorting] = useState([])
  const [globalFilter, setGlobalFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [stageFilter, setStageFilter] = useState('')

  const columns = useMemo(() => [
    {
      accessorKey: 'name',
      header: '公司',
      cell: ({ row }) => (
        <div>
          <div className="font-medium">{row.original.name}</div>
          {row.original.website && (
            <a
              href={row.original.website}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-600 hover:underline"
            >
              网站
            </a>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'category_zh',
      header: '类别',
      cell: ({ getValue }) => (
        <span className="bg-blue-50 text-blue-700 text-xs px-2 py-1 rounded">
          {getValue()}
        </span>
      ),
    },
    {
      accessorKey: 'funding_stage_zh',
      header: '阶段',
      cell: ({ getValue }) => (
        <span className="bg-gray-100 text-gray-700 text-xs px-2 py-1 rounded">
          {getValue()}
        </span>
      ),
    },
    {
      accessorKey: 'funding_millions',
      header: '融资 $M',
      cell: ({ getValue }) => formatFunding(getValue()),
      sortDescFirst: true,
    },
    {
      accessorKey: 'revenue_millions',
      header: '营收 $M',
      cell: ({ getValue }) => formatFunding(getValue()),
      sortDescFirst: true,
    },
    {
      accessorKey: 'founded_year',
      header: '成立',
      cell: ({ getValue }) => getValue() || '-',
    },
    {
      accessorKey: 'cb_rank',
      header: 'CB排名',
      cell: ({ getValue }) => {
        const val = getValue()
        return val && val < 999999 ? val.toLocaleString() : '-'
      },
    },
    {
      accessorKey: 'source_count',
      header: '来源数',
      sortDescFirst: true,
    },
  ], [])

  const filteredData = useMemo(() => {
    let data = companies
    if (categoryFilter) {
      data = data.filter(c => c.category === categoryFilter)
    }
    if (stageFilter) {
      data = data.filter(c => c.funding_stage === stageFilter)
    }
    return data
  }, [companies, categoryFilter, stageFilter])

  const table = useReactTable({
    data: filteredData,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 50 } },
  })

  return (
    <div>
      {/* Filters */}
      <div className="flex flex-wrap gap-4 mb-4">
        <input
          type="text"
          placeholder="搜索公司..."
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          className="border rounded px-3 py-2 w-64"
        />
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="border rounded px-3 py-2"
        >
          <option value="">全部类别</option>
          {categories.map(c => (
            <option key={c.id} value={c.id}>{c.name_zh}</option>
          ))}
        </select>
        <select
          value={stageFilter}
          onChange={(e) => setStageFilter(e.target.value)}
          className="border rounded px-3 py-2"
        >
          <option value="">全部阶段</option>
          {stages.map(s => (
            <option key={s.id} value={s.id}>{s.name_zh}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="overflow-x-auto bg-white rounded-lg shadow">
        <table className="w-full">
          <thead className="bg-gray-50 border-b">
            {table.getHeaderGroups().map(hg => (
              <tr key={hg.id}>
                {hg.headers.map(header => (
                  <th
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler()}
                    className="px-4 py-3 text-left text-sm font-semibold text-gray-700 cursor-pointer hover:bg-gray-100"
                  >
                    <div className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {{
                        asc: ' ↑',
                        desc: ' ↓',
                      }[header.column.getIsSorted()] ?? ''}
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map(row => (
              <tr key={row.id} className="border-b hover:bg-gray-50">
                {row.getVisibleCells().map(cell => (
                  <td key={cell.id} className="px-4 py-3 text-sm">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between mt-4">
        <div className="text-sm text-gray-600">
          显示 {table.getRowModel().rows.length} / {filteredData.length} 条
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
            className="px-3 py-1 border rounded disabled:opacity-50"
          >
            上一页
          </button>
          <span className="px-3 py-1">
            第 {table.getState().pagination.pageIndex + 1} / {table.getPageCount()} 页
          </span>
          <button
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
            className="px-3 py-1 border rounded disabled:opacity-50"
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/
git commit -m "feat: add CompanyTable with TanStack Table sorting"
```

---

## Task 12: BubbleChart Component

**Files:**
- Create: `frontend/src/components/BubbleChart.jsx`

**Step 1: Create the component**

Create `frontend/src/components/BubbleChart.jsx`:
```jsx
import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

/**
 * Bubble chart for entity visualization across pipelines.
 */
export default function BubbleChart({ data }) {
  if (!data || data.length === 0) {
    return <div className="text-gray-500 text-center py-8">暂无数据</div>
  }

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const d = payload[0].payload
      return (
        <div className="bg-white shadow-lg rounded-lg p-3 border">
          <div className="font-semibold">{d.name}</div>
          <div className="text-sm text-gray-600">{d.entity_type}</div>
          <div className="text-sm mt-1">
            <span className="text-gray-500">管道数:</span> {d.x}
          </div>
          <div className="text-sm">
            <span className="text-gray-500">总提及:</span> {d.y}
          </div>
          {d.pipeline_breakdown && (
            <div className="text-xs mt-2 text-gray-500">
              {Object.entries(d.pipeline_breakdown).map(([k, v]) => (
                <div key={k}>{k}: {v}</div>
              ))}
            </div>
          )}
        </div>
      )
    }
    return null
  }

  return (
    <ResponsiveContainer width="100%" height={400}>
      <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
        <XAxis
          type="number"
          dataKey="x"
          name="管道数"
          domain={[0, 4]}
          tickCount={4}
          label={{ value: '出现管道数', position: 'bottom', offset: 0 }}
        />
        <YAxis
          type="number"
          dataKey="y"
          name="提及次数"
          label={{ value: '总提及次数', angle: -90, position: 'left' }}
        />
        <ZAxis
          type="number"
          dataKey="size"
          range={[100, 1000]}
        />
        <Tooltip content={<CustomTooltip />} />
        <Scatter data={data}>
          {data.map((entry, idx) => (
            <Cell key={idx} fill={entry.color || '#8884d8'} />
          ))}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/
git commit -m "feat: add BubbleChart component with Recharts"
```

---

## Task 13: Insights Page

**Files:**
- Create: `frontend/src/pages/Insights.jsx`
- Modify: `frontend/src/App.jsx`

**Step 1: Create Insights page**

Create `frontend/src/pages/Insights.jsx`:
```jsx
import { useApi } from '../hooks/useApi'
import StatCard from '../components/StatCard'
import BubbleChart from '../components/BubbleChart'

export default function Insights({ date }) {
  const { data, loading, error } = useApi(date ? `/api/insights?date=${date}` : null)

  if (loading) return <div className="text-center py-8">加载中...</div>
  if (error) return <div className="text-red-500 py-8">错误: {error}</div>
  if (!data) return null

  const { summary, bubble_data, hot_entities } = data

  return (
    <div>
      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard
          icon="📰"
          label="AI新闻"
          value={summary.pipeline_counts.news}
          color="blue"
        />
        <StatCard
          icon="🚀"
          label="产品"
          value={summary.pipeline_counts.product}
          color="green"
        />
        <StatCard
          icon="💰"
          label="投资"
          value={summary.pipeline_counts.investing}
          color="orange"
        />
        <StatCard
          icon="🔗"
          label="跨管道实体"
          value={summary.cross_pipeline_entities}
          color="purple"
        />
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-5 gap-6">
        {/* Bubble Chart */}
        <div className="col-span-3 bg-white rounded-lg shadow p-4">
          <h2 className="text-lg font-semibold mb-4">实体跨管道分布</h2>
          <BubbleChart data={bubble_data} />
        </div>

        {/* Hot Entities */}
        <div className="col-span-2 bg-white rounded-lg shadow p-4">
          <h2 className="text-lg font-semibold mb-4">热门实体</h2>
          <div className="space-y-2">
            {hot_entities.map((e, idx) => (
              <div
                key={e.entity_name}
                className="flex items-center justify-between p-2 bg-gray-50 rounded"
              >
                <div>
                  <span className="text-gray-400 text-sm mr-2">#{idx + 1}</span>
                  <span className="font-medium">{e.entity_name}</span>
                  <span className="text-xs text-gray-500 ml-2">({e.entity_type})</span>
                </div>
                <div className="text-sm">
                  <span className="text-blue-600 font-semibold">{e.total_mentions}</span>
                  <span className="text-gray-400 ml-1">次</span>
                  <span className="text-gray-300 mx-1">|</span>
                  <span className="text-green-600">{e.pipeline_count}</span>
                  <span className="text-gray-400 ml-1">管道</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
```

**Step 2: Update App.jsx to use Insights**

Update `frontend/src/App.jsx`:
```jsx
import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Insights from './pages/Insights'

function App() {
  const [dates, setDates] = useState([])
  const [selectedDate, setSelectedDate] = useState('')

  useEffect(() => {
    fetch('/api/dates')
      .then(res => res.json())
      .then(data => {
        setDates(data.dates)
        if (data.latest) setSelectedDate(data.latest)
      })
  }, [])

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        {/* Header */}
        <header className="bg-white shadow-sm border-b">
          <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
            <h1 className="text-2xl font-bold text-blue-600">CEO智能仪表板</h1>
            <select
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="border rounded px-3 py-2"
            >
              {dates.map(d => (
                <option key={d} value={d}>
                  {d.slice(0,4)}-{d.slice(4,6)}-{d.slice(6,8)}
                </option>
              ))}
            </select>
          </div>
        </header>

        {/* Navigation */}
        <nav className="bg-white border-b">
          <div className="max-w-7xl mx-auto px-4">
            <div className="flex space-x-8">
              {[
                { path: '/', label: '洞察', icon: '🔥' },
                { path: '/news', label: 'AI新闻', icon: '📰' },
                { path: '/product', label: '产品', icon: '🚀' },
                { path: '/investing', label: '投资', icon: '💰' },
                { path: '/shortlist', label: 'AI速查', icon: '🏢' },
                { path: '/signals', label: '信号雷达', icon: '📡' },
                { path: '/buckets', label: '趋势桶雷达', icon: '🎯' },
              ].map(({ path, label, icon }) => (
                <NavLink
                  key={path}
                  to={path}
                  className={({ isActive }) =>
                    `py-4 px-1 border-b-2 font-medium ${
                      isActive
                        ? 'border-blue-500 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    }`
                  }
                >
                  {icon} {label}
                </NavLink>
              ))}
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className="max-w-7xl mx-auto px-4 py-6">
          <Routes>
            <Route path="/" element={<Insights date={selectedDate} />} />
            <Route path="/news" element={<div>新闻页面 - 开发中</div>} />
            <Route path="/product" element={<div>产品页面 - 开发中</div>} />
            <Route path="/investing" element={<div>投资页面 - 开发中</div>} />
            <Route path="/shortlist" element={<div>速查页面 - 开发中</div>} />
            <Route path="/signals" element={<div>信号雷达 - 开发中</div>} />
            <Route path="/buckets" element={<div>趋势桶雷达 - 开发中</div>} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
```

**Step 3: Test the insights page**

Run both servers, navigate to http://localhost:5173
Expected: Insights page shows stats, bubble chart, and hot entities

**Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat: add Insights page with stats and bubble chart"
```

---

## Task 14: Articles Page

**Files:**
- Create: `frontend/src/pages/Articles.jsx`
- Modify: `frontend/src/App.jsx`

**Step 1: Create Articles page**

Create `frontend/src/pages/Articles.jsx`:
```jsx
import { useApi } from '../hooks/useApi'
import ArticleCard from '../components/ArticleCard'
import { useState } from 'react'

export default function Articles({ date, pipeline }) {
  const [searchTerm, setSearchTerm] = useState('')
  const { data, loading, error } = useApi(
    date ? `/api/articles/${pipeline}?date=${date}` : null
  )

  if (loading) return <div className="text-center py-8">加载中...</div>
  if (error) return <div className="text-red-500 py-8">错误: {error}</div>
  if (!data) return null

  const filteredArticles = data.articles.filter(a =>
    a.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    a.source.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const pipelineNames = {
    news: 'AI新闻',
    product: '产品',
    investing: '投资',
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold">
          {pipelineNames[pipeline]} ({data.total} 篇)
        </h2>
        <input
          type="text"
          placeholder="搜索文章..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="border rounded px-3 py-2 w-64"
        />
      </div>

      <div className="space-y-2">
        {filteredArticles.map(article => (
          <ArticleCard
            key={article.id}
            article={article}
            pipeline={pipeline}
          />
        ))}
      </div>

      {filteredArticles.length === 0 && (
        <div className="text-center text-gray-500 py-8">
          没有找到匹配的文章
        </div>
      )}
    </div>
  )
}
```

**Step 2: Update App.jsx**

Update the routes in `frontend/src/App.jsx`:
```jsx
import Articles from './pages/Articles'

// ... inside Routes:
<Route path="/news" element={<Articles date={selectedDate} pipeline="news" />} />
<Route path="/product" element={<Articles date={selectedDate} pipeline="product" />} />
<Route path="/investing" element={<Articles date={selectedDate} pipeline="investing" />} />
```

**Step 3: Test**

Navigate to news/product/investing tabs
Expected: Articles display with search working

**Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat: add Articles page for all pipelines"
```

---

## Task 15: Shortlist Page

**Files:**
- Create: `frontend/src/pages/Shortlist.jsx`
- Modify: `frontend/src/App.jsx`

**Step 1: Create Shortlist page**

Create `frontend/src/pages/Shortlist.jsx`:
```jsx
import { useApi } from '../hooks/useApi'
import CompanyTable from '../components/CompanyTable'

export default function Shortlist() {
  const { data: companiesData, loading: loadingCompanies } = useApi('/api/companies')
  const { data: filtersData, loading: loadingFilters } = useApi('/api/companies/filters')

  if (loadingCompanies || loadingFilters) {
    return <div className="text-center py-8">加载中...</div>
  }

  if (!companiesData || !filtersData) {
    return <div className="text-red-500 py-8">无法加载数据</div>
  }

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-xl font-semibold">AI速查</h2>
        <p className="text-gray-600 text-sm">
          来自顶级VC投资组合的AI公司 ({companiesData.total} 家)
        </p>
      </div>

      <CompanyTable
        companies={companiesData.companies}
        categories={filtersData.categories}
        stages={filtersData.stages}
      />
    </div>
  )
}
```

**Step 2: Update App.jsx**

```jsx
import Shortlist from './pages/Shortlist'

// ... inside Routes:
<Route path="/shortlist" element={<Shortlist />} />
```

**Step 3: Test**

Navigate to AI速查 tab
Expected: Sortable table with proper numeric sorting

**Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat: add Shortlist page with sortable table"
```

---

## Task 16: SignalRadar Page

**Files:**
- Create: `frontend/src/pages/SignalRadar.jsx`
- Create: `frontend/src/components/RadarChart.jsx`
- Modify: `frontend/src/App.jsx`

**Step 1: Create RadarChart component**

Create `frontend/src/components/RadarChart.jsx`:
```jsx
import { Radar, RadarChart as RechartsRadar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts'

export default function RadarChart({ scores }) {
  if (!scores || scores.length === 0) return null

  const data = scores.map(s => ({
    category: s.category,
    value: s.value * 100,
  }))

  return (
    <ResponsiveContainer width="100%" height={200}>
      <RechartsRadar data={data}>
        <PolarGrid />
        <PolarAngleAxis dataKey="category" tick={{ fontSize: 10 }} />
        <PolarRadiusAxis angle={30} domain={[0, 100]} />
        <Radar
          dataKey="value"
          stroke="#3b82f6"
          fill="#3b82f6"
          fillOpacity={0.3}
        />
      </RechartsRadar>
    </ResponsiveContainer>
  )
}
```

**Step 2: Create SignalRadar page**

Create `frontend/src/pages/SignalRadar.jsx`:
```jsx
import { useApi } from '../hooks/useApi'
import RadarChart from '../components/RadarChart'

export default function SignalRadar() {
  const { data: entities, loading: loadingEntities } = useApi('/api/signals/entities?limit=20')
  const { data: divergences, loading: loadingDivergences } = useApi('/api/signals/divergence')

  if (loadingEntities || loadingDivergences) {
    return <div className="text-center py-8">加载中...</div>
  }

  const opportunities = divergences?.filter(d => d.interpretation === 'opportunity') || []
  const risks = divergences?.filter(d => d.interpretation === 'risk') || []

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">信号雷达</h2>

      <div className="grid grid-cols-2 gap-6 mb-6">
        {/* Opportunities */}
        <div className="bg-green-50 rounded-lg p-4">
          <h3 className="font-semibold text-green-700 mb-3">机会信号 ({opportunities.length})</h3>
          <div className="space-y-2">
            {opportunities.slice(0, 5).map(d => (
              <div key={d.entity_id} className="bg-white p-2 rounded shadow-sm">
                <div className="font-medium">{d.entity_name}</div>
                <div className="text-xs text-gray-600">
                  {d.signal_a} vs {d.signal_b}: {d.divergence_score.toFixed(2)}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Risks */}
        <div className="bg-red-50 rounded-lg p-4">
          <h3 className="font-semibold text-red-700 mb-3">风险信号 ({risks.length})</h3>
          <div className="space-y-2">
            {risks.slice(0, 5).map(d => (
              <div key={d.entity_id} className="bg-white p-2 rounded shadow-sm">
                <div className="font-medium">{d.entity_name}</div>
                <div className="text-xs text-gray-600">
                  {d.signal_a} vs {d.signal_b}: {d.divergence_score.toFixed(2)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Top Entities */}
      <h3 className="font-semibold mb-3">综合评分最高实体</h3>
      <div className="grid grid-cols-4 gap-4">
        {entities?.slice(0, 8).map(e => (
          <div key={e.entity_id} className="bg-white rounded-lg shadow p-4">
            <div className="font-semibold mb-1">{e.name}</div>
            <div className="text-xs text-gray-500 mb-2">{e.entity_type}</div>
            <div className="text-2xl font-bold text-blue-600 mb-2">
              {(e.composite_score * 100).toFixed(0)}
            </div>
            <RadarChart scores={e.scores} />
          </div>
        ))}
      </div>
    </div>
  )
}
```

**Step 3: Update App.jsx**

```jsx
import SignalRadar from './pages/SignalRadar'

// ... inside Routes:
<Route path="/signals" element={<SignalRadar />} />
```

**Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat: add SignalRadar page with entity scores"
```

---

## Task 17: BucketRadar Page

**Files:**
- Create: `frontend/src/pages/BucketRadar.jsx`
- Modify: `frontend/src/App.jsx`

**Step 1: Create BucketRadar page**

Create `frontend/src/pages/BucketRadar.jsx`:
```jsx
import { useApi } from '../hooks/useApi'
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts'

const LIFECYCLE_COLORS = {
  EMERGING: '#22c55e',
  VALIDATING: '#3b82f6',
  ESTABLISHING: '#f59e0b',
  MAINSTREAM: '#6b7280',
}

export default function BucketRadar() {
  const { data: bucketsData, loading: loadingBuckets } = useApi('/api/buckets')
  const { data: alerts, loading: loadingAlerts } = useApi('/api/buckets/alerts/active')

  if (loadingBuckets || loadingAlerts) {
    return <div className="text-center py-8">加载中...</div>
  }

  if (!bucketsData || !bucketsData.profiles) {
    return <div className="text-gray-500 py-8">暂无趋势桶数据</div>
  }

  const scatterData = bucketsData.profiles.map(p => ({
    ...p,
    x: p.tms,
    y: p.ccs,
  }))

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const p = payload[0].payload
      return (
        <div className="bg-white shadow-lg rounded-lg p-3 border">
          <div className="font-semibold">{p.bucket_name}</div>
          <div className="text-sm text-gray-600">{p.lifecycle_state}</div>
          <div className="text-xs mt-1">
            <div>TMS: {p.tms.toFixed(1)}</div>
            <div>CCS: {p.ccs.toFixed(1)}</div>
            <div>NAS: {p.nas.toFixed(1)}</div>
            <div>Heat: {p.heat_score.toFixed(1)}</div>
          </div>
        </div>
      )
    }
    return null
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">趋势桶雷达</h2>

      <div className="grid grid-cols-3 gap-6">
        {/* Quadrant Chart */}
        <div className="col-span-2 bg-white rounded-lg shadow p-4">
          <h3 className="font-semibold mb-3">技术动量 vs 资本共识</h3>
          <ResponsiveContainer width="100%" height={400}>
            <ScatterChart margin={{ top: 20, right: 20, bottom: 40, left: 40 }}>
              <XAxis
                type="number"
                dataKey="x"
                domain={[0, 100]}
                label={{ value: 'TMS (技术动量)', position: 'bottom' }}
              />
              <YAxis
                type="number"
                dataKey="y"
                domain={[0, 100]}
                label={{ value: 'CCS (资本共识)', angle: -90, position: 'left' }}
              />
              <ReferenceLine x={50} stroke="#ccc" strokeDasharray="3 3" />
              <ReferenceLine y={50} stroke="#ccc" strokeDasharray="3 3" />
              <Tooltip content={<CustomTooltip />} />
              <Scatter data={scatterData}>
                {scatterData.map((entry, idx) => (
                  <Cell
                    key={idx}
                    fill={LIFECYCLE_COLORS[entry.lifecycle_state] || '#999'}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-4 mt-2 text-xs">
            {Object.entries(LIFECYCLE_COLORS).map(([state, color]) => (
              <div key={state} className="flex items-center gap-1">
                <div className="w-3 h-3 rounded-full" style={{ background: color }} />
                <span>{state}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Alerts */}
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-semibold mb-3">活跃警报</h3>
          <div className="space-y-2">
            {alerts?.slice(0, 10).map((a, idx) => (
              <div
                key={idx}
                className={`p-2 rounded text-sm ${
                  a.severity === 'high' ? 'bg-red-50 border-l-2 border-red-500' :
                  a.severity === 'medium' ? 'bg-yellow-50 border-l-2 border-yellow-500' :
                  'bg-blue-50 border-l-2 border-blue-500'
                }`}
              >
                <div className="font-medium">{a.bucket_name}</div>
                <div className="text-xs text-gray-600">{a.alert_type}</div>
                <div className="text-xs text-gray-500 mt-1">{a.message}</div>
              </div>
            ))}
            {(!alerts || alerts.length === 0) && (
              <div className="text-gray-500 text-sm">无活跃警报</div>
            )}
          </div>
        </div>
      </div>

      {/* Bucket List */}
      <div className="mt-6 bg-white rounded-lg shadow p-4">
        <h3 className="font-semibold mb-3">所有趋势桶</h3>
        <div className="grid grid-cols-4 gap-4">
          {bucketsData.profiles.map(p => (
            <div
              key={p.bucket_id}
              className="border rounded-lg p-3 hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-2 mb-2">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ background: LIFECYCLE_COLORS[p.lifecycle_state] || '#999' }}
                />
                <span className="font-medium">{p.bucket_name}</span>
              </div>
              <div className="grid grid-cols-2 gap-1 text-xs text-gray-600">
                <div>TMS: {p.tms.toFixed(0)}</div>
                <div>CCS: {p.ccs.toFixed(0)}</div>
                <div>NAS: {p.nas.toFixed(0)}</div>
                <div>Heat: {p.heat_score.toFixed(0)}</div>
              </div>
              <div className="text-xs text-gray-400 mt-1">
                {p.entity_count} 实体 | {p.article_count} 文章
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
```

**Step 2: Update App.jsx**

```jsx
import BucketRadar from './pages/BucketRadar'

// ... inside Routes:
<Route path="/buckets" element={<BucketRadar />} />
```

**Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat: add BucketRadar page with quadrant chart"
```

---

## Task 18: Production Build & Static Serving

**Files:**
- Modify: `api/main.py`

**Step 1: Add static file serving to FastAPI**

Update `api/main.py` to serve built React files:
```python
# At the end of main.py, after all routers:

# Serve React frontend in production
_frontend_dist = _api_dir.parent / "frontend" / "dist"

if _frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA."""
        file_path = _frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist / "index.html")

    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="assets")
```

**Step 2: Build frontend**

```bash
cd frontend && npm run build
```

**Step 3: Test production mode**

```bash
cd api && uvicorn main:app --port 8000
```

Navigate to http://localhost:8000
Expected: Full React app served from FastAPI

**Step 4: Commit**

```bash
git add api/ frontend/dist/
git commit -m "feat: add production build with static serving"
```

---

## Task 19: Final Integration Test

**Step 1: Start both servers**

```bash
# Terminal 1
cd api && uvicorn main:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

**Step 2: Verify all tabs work**

- [ ] 洞察 - Stats, bubble chart, hot entities
- [ ] AI新闻 - Articles with search
- [ ] 产品 - Articles with search
- [ ] 投资 - Articles with search
- [ ] AI速查 - Sortable table, filters, pagination
- [ ] 信号雷达 - Entity scores, divergences
- [ ] 趋势桶雷达 - Quadrant chart, alerts

**Step 3: Test sorting on AI速查**

- Click "融资 $M" header - should sort by numeric value (billions > millions)
- Click "CB排名" header - should sort properly with missing values at end
- All sorting applies to ALL data, not just visible page

**Step 4: Final commit**

```bash
git add .
git commit -m "feat: complete React dashboard with full feature parity"
```

---

## Running

**Development:**
```bash
# Terminal 1: API
cd api && uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

**Production:**
```bash
cd frontend && npm run build
cd ../api && uvicorn main:app --port 8000
```

Single process, single port (8000).