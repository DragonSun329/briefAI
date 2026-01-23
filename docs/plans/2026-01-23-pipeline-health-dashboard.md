# Pipeline Health Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a visibility-only dashboard showing pipeline status, data freshness, and system health.

**Architecture:** Status collector → API endpoint → React dashboard page

**Tech Stack:** Python, SQLite introspection, FastAPI, React

---

## Task 1: Create Pipeline Status Collector

**Files:**
- Create: `utils/pipeline_status.py`

**Steps:**

1. Create the status collector module:

```python
# utils/pipeline_status.py
"""Pipeline status collector for health dashboard."""

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import json


@dataclass
class ScraperStatus:
    """Status of a scraper."""
    name: str
    last_run: Optional[str]
    status: str  # fresh, stale, error, never_run
    record_count: int
    source_file: Optional[str]
    freshness_hours: int = 24  # How old before considered stale


@dataclass
class PipelineStatus:
    """Status of a pipeline."""
    name: str
    last_run: Optional[str]
    status: str  # done, stale, error, never_run
    output_count: int
    output_location: Optional[str]


@dataclass
class DatabaseStatus:
    """Status of a database."""
    name: str
    path: str
    size_mb: float
    record_count: int
    table_count: int
    health: str  # ok, warning, error


@dataclass
class CacheStatus:
    """Status of cache directory."""
    name: str
    path: str
    size_mb: float
    file_count: int
    oldest_file: Optional[str]
    newest_file: Optional[str]


@dataclass
class SystemHealth:
    """Overall system health summary."""
    scrapers: List[ScraperStatus]
    pipelines: List[PipelineStatus]
    databases: List[DatabaseStatus]
    caches: List[CacheStatus]
    healthy_count: int
    warning_count: int
    error_count: int
    overall_status: str  # healthy, degraded, critical
    checked_at: str


class PipelineStatusCollector:
    """Collect status from all system components."""

    # Scraper configurations: name -> (output_pattern, freshness_hours)
    SCRAPERS = {
        "jiqizhixin": ("data/cache/*jiqizhixin*.json", 24),
        "qbitai": ("data/cache/*qbitai*.json", 24),
        "github_trending": ("data/cache/*github*.json", 48),
        "huggingface": ("data/cache/*huggingface*.json", 48),
        "hackernews": ("data/cache/*hackernews*.json", 24),
        "reddit": ("data/cache/*reddit*.json", 24),
        "arxiv": ("data/cache/*arxiv*.json", 72),
        "techcrunch": ("data/cache/*techcrunch*.json", 24),
    }

    # Pipeline configurations: name -> (output_pattern, table_name)
    PIPELINES = {
        "trend_aggregate": ("data/cache/trend_aggregate/*.json", None),
        "article_contexts": ("data/cache/article_contexts/*.json", None),
        "conviction_analysis": (None, "conviction_scores"),
        "report_generation": ("data/reports/*.md", None),
    }

    # Database configurations
    DATABASES = [
        ("trend_radar.db", "data/trend_radar.db"),
        ("signals.db", "data/signals.db"),
        ("briefai.db", "data/briefai.db"),
        ("alerts.db", "data/alerts.db"),
    ]

    # Cache directories
    CACHES = [
        ("article_contexts", "data/cache/article_contexts"),
        ("pipeline_contexts", "data/cache/pipeline_contexts"),
        ("trend_aggregate", "data/cache/trend_aggregate"),
        ("wayback_cache", "data/wayback_cache"),
    ]

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(__file__).parent.parent

    def get_scraper_status(self) -> List[ScraperStatus]:
        """Get status of all scrapers."""
        statuses = []
        now = datetime.now()

        for name, (pattern, freshness_hours) in self.SCRAPERS.items():
            files = list(self.base_dir.glob(pattern))

            if not files:
                statuses.append(ScraperStatus(
                    name=name,
                    last_run=None,
                    status="never_run",
                    record_count=0,
                    source_file=None,
                    freshness_hours=freshness_hours,
                ))
                continue

            # Find most recent file
            latest_file = max(files, key=lambda f: f.stat().st_mtime)
            mtime = datetime.fromtimestamp(latest_file.stat().st_mtime)
            age_hours = (now - mtime).total_seconds() / 3600

            # Count records
            record_count = 0
            try:
                with open(latest_file, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        record_count = len(data)
                    elif isinstance(data, dict):
                        record_count = len(data.get("articles", data.get("items", data.get("results", [1]))))
            except:
                pass

            status = "fresh" if age_hours <= freshness_hours else "stale"

            statuses.append(ScraperStatus(
                name=name,
                last_run=mtime.isoformat(),
                status=status,
                record_count=record_count,
                source_file=str(latest_file.relative_to(self.base_dir)),
                freshness_hours=freshness_hours,
            ))

        return statuses

    def get_pipeline_status(self) -> List[PipelineStatus]:
        """Get status of all pipelines."""
        statuses = []
        now = datetime.now()

        for name, (pattern, table_name) in self.PIPELINES.items():
            if pattern:
                files = list(self.base_dir.glob(pattern))

                if not files:
                    statuses.append(PipelineStatus(
                        name=name,
                        last_run=None,
                        status="never_run",
                        output_count=0,
                        output_location=None,
                    ))
                    continue

                latest_file = max(files, key=lambda f: f.stat().st_mtime)
                mtime = datetime.fromtimestamp(latest_file.stat().st_mtime)
                age_hours = (now - mtime).total_seconds() / 3600

                statuses.append(PipelineStatus(
                    name=name,
                    last_run=mtime.isoformat(),
                    status="done" if age_hours <= 24 else "stale",
                    output_count=len(files),
                    output_location=str(latest_file.parent.relative_to(self.base_dir)),
                ))

            elif table_name:
                # Check database table
                db_path = self.base_dir / "data" / "trend_radar.db"
                if db_path.exists():
                    try:
                        conn = sqlite3.connect(str(db_path))
                        cursor = conn.cursor()
                        cursor.execute(f"SELECT COUNT(*), MAX(analyzed_at) FROM {table_name}")
                        count, last_run = cursor.fetchone()
                        conn.close()

                        statuses.append(PipelineStatus(
                            name=name,
                            last_run=last_run,
                            status="done" if count > 0 else "never_run",
                            output_count=count or 0,
                            output_location=table_name,
                        ))
                    except:
                        statuses.append(PipelineStatus(
                            name=name,
                            last_run=None,
                            status="error",
                            output_count=0,
                            output_location=table_name,
                        ))

        return statuses

    def get_database_status(self) -> List[DatabaseStatus]:
        """Get status of all databases."""
        statuses = []

        for name, rel_path in self.DATABASES:
            db_path = self.base_dir / rel_path

            if not db_path.exists():
                statuses.append(DatabaseStatus(
                    name=name,
                    path=rel_path,
                    size_mb=0,
                    record_count=0,
                    table_count=0,
                    health="error",
                ))
                continue

            try:
                size_mb = db_path.stat().st_size / (1024 * 1024)

                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()

                # Count tables
                cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                table_count = cursor.fetchone()[0]

                # Count total records across tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                record_count = 0
                for (table,) in tables:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        record_count += cursor.fetchone()[0]
                    except:
                        pass

                conn.close()

                statuses.append(DatabaseStatus(
                    name=name,
                    path=rel_path,
                    size_mb=round(size_mb, 2),
                    record_count=record_count,
                    table_count=table_count,
                    health="ok",
                ))

            except Exception as e:
                statuses.append(DatabaseStatus(
                    name=name,
                    path=rel_path,
                    size_mb=0,
                    record_count=0,
                    table_count=0,
                    health="error",
                ))

        return statuses

    def get_cache_status(self) -> List[CacheStatus]:
        """Get status of cache directories."""
        statuses = []

        for name, rel_path in self.CACHES:
            cache_path = self.base_dir / rel_path

            if not cache_path.exists():
                statuses.append(CacheStatus(
                    name=name,
                    path=rel_path,
                    size_mb=0,
                    file_count=0,
                    oldest_file=None,
                    newest_file=None,
                ))
                continue

            files = list(cache_path.glob("**/*"))
            files = [f for f in files if f.is_file()]

            if not files:
                statuses.append(CacheStatus(
                    name=name,
                    path=rel_path,
                    size_mb=0,
                    file_count=0,
                    oldest_file=None,
                    newest_file=None,
                ))
                continue

            total_size = sum(f.stat().st_size for f in files)
            oldest = min(files, key=lambda f: f.stat().st_mtime)
            newest = max(files, key=lambda f: f.stat().st_mtime)

            statuses.append(CacheStatus(
                name=name,
                path=rel_path,
                size_mb=round(total_size / (1024 * 1024), 2),
                file_count=len(files),
                oldest_file=datetime.fromtimestamp(oldest.stat().st_mtime).isoformat(),
                newest_file=datetime.fromtimestamp(newest.stat().st_mtime).isoformat(),
            ))

        return statuses

    def get_system_health(self) -> SystemHealth:
        """Get overall system health."""
        scrapers = self.get_scraper_status()
        pipelines = self.get_pipeline_status()
        databases = self.get_database_status()
        caches = self.get_cache_status()

        # Count health states
        healthy = 0
        warning = 0
        error = 0

        for s in scrapers:
            if s.status == "fresh":
                healthy += 1
            elif s.status == "stale":
                warning += 1
            else:
                error += 1

        for p in pipelines:
            if p.status == "done":
                healthy += 1
            elif p.status == "stale":
                warning += 1
            else:
                error += 1

        for d in databases:
            if d.health == "ok":
                healthy += 1
            elif d.health == "warning":
                warning += 1
            else:
                error += 1

        total = healthy + warning + error
        if error > total * 0.3:
            overall = "critical"
        elif warning > total * 0.3:
            overall = "degraded"
        else:
            overall = "healthy"

        return SystemHealth(
            scrapers=scrapers,
            pipelines=pipelines,
            databases=databases,
            caches=caches,
            healthy_count=healthy,
            warning_count=warning,
            error_count=error,
            overall_status=overall,
            checked_at=datetime.now().isoformat(),
        )
```

2. Commit: `feat: add pipeline status collector`

---

## Task 2: Create Pipeline Health API Endpoint

**Files:**
- Create: `api/routers/health.py`
- Modify: `api/main.py`

**Steps:**

1. Create health API router:

```python
# api/routers/health.py
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
```

2. Register router in `api/main.py`:

```python
from api.routers import health
app.include_router(health.router)
```

3. Commit: `feat: add pipeline health API endpoints`

---

## Task 3: Create Pipeline Health Dashboard Page

**Files:**
- Create: `frontend/src/pages/PipelineHealth.jsx`
- Modify: `frontend/src/App.jsx`

**Steps:**

1. Create the dashboard page:

```jsx
// frontend/src/pages/PipelineHealth.jsx
import { useApi } from '../hooks/useApi'

function StatusBadge({ status }) {
  const colors = {
    fresh: 'bg-green-100 text-green-800',
    done: 'bg-green-100 text-green-800',
    ok: 'bg-green-100 text-green-800',
    stale: 'bg-yellow-100 text-yellow-800',
    warning: 'bg-yellow-100 text-yellow-800',
    error: 'bg-red-100 text-red-800',
    never_run: 'bg-gray-100 text-gray-800',
  }

  const icons = {
    fresh: '✓',
    done: '✓',
    ok: '✓',
    stale: '⚠',
    warning: '⚠',
    error: '✗',
    never_run: '○',
  }

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${colors[status] || colors.error}`}>
      {icons[status] || '?'} {status}
    </span>
  )
}

function OverallHealth({ data }) {
  const colors = {
    healthy: 'text-green-600',
    degraded: 'text-yellow-600',
    critical: 'text-red-600',
  }

  return (
    <div className="bg-white rounded-lg border p-6 mb-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">System Health</h2>
          <p className="text-sm text-gray-500">Last checked: {new Date(data.checked_at).toLocaleString()}</p>
        </div>
        <div className={`text-3xl font-bold ${colors[data.overall_status]}`}>
          {data.overall_status.toUpperCase()}
        </div>
      </div>
      <div className="grid grid-cols-3 gap-4 mt-4">
        <div className="text-center">
          <div className="text-2xl font-bold text-green-600">{data.healthy_count}</div>
          <div className="text-sm text-gray-500">Healthy</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-yellow-600">{data.warning_count}</div>
          <div className="text-sm text-gray-500">Warning</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-red-600">{data.error_count}</div>
          <div className="text-sm text-gray-500">Error</div>
        </div>
      </div>
    </div>
  )
}

function ScrapersTable({ scrapers }) {
  return (
    <div className="bg-white rounded-lg border mb-6">
      <div className="px-4 py-3 border-b bg-gray-50">
        <h3 className="font-semibold">Scrapers</h3>
      </div>
      <table className="w-full">
        <thead className="bg-gray-50 text-sm">
          <tr>
            <th className="px-4 py-2 text-left">Name</th>
            <th className="px-4 py-2 text-left">Last Run</th>
            <th className="px-4 py-2 text-center">Status</th>
            <th className="px-4 py-2 text-right">Records</th>
          </tr>
        </thead>
        <tbody className="text-sm">
          {scrapers.map((s, i) => (
            <tr key={i} className="border-t">
              <td className="px-4 py-3 font-medium">{s.name}</td>
              <td className="px-4 py-3 text-gray-600">
                {s.last_run ? new Date(s.last_run).toLocaleString() : 'Never'}
              </td>
              <td className="px-4 py-3 text-center">
                <StatusBadge status={s.status} />
              </td>
              <td className="px-4 py-3 text-right">{s.record_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PipelinesTable({ pipelines }) {
  return (
    <div className="bg-white rounded-lg border mb-6">
      <div className="px-4 py-3 border-b bg-gray-50">
        <h3 className="font-semibold">Pipelines</h3>
      </div>
      <table className="w-full">
        <thead className="bg-gray-50 text-sm">
          <tr>
            <th className="px-4 py-2 text-left">Name</th>
            <th className="px-4 py-2 text-left">Last Run</th>
            <th className="px-4 py-2 text-center">Status</th>
            <th className="px-4 py-2 text-right">Outputs</th>
          </tr>
        </thead>
        <tbody className="text-sm">
          {pipelines.map((p, i) => (
            <tr key={i} className="border-t">
              <td className="px-4 py-3 font-medium">{p.name}</td>
              <td className="px-4 py-3 text-gray-600">
                {p.last_run ? new Date(p.last_run).toLocaleString() : 'Never'}
              </td>
              <td className="px-4 py-3 text-center">
                <StatusBadge status={p.status} />
              </td>
              <td className="px-4 py-3 text-right">{p.output_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DatabasesTable({ databases }) {
  return (
    <div className="bg-white rounded-lg border mb-6">
      <div className="px-4 py-3 border-b bg-gray-50">
        <h3 className="font-semibold">Databases</h3>
      </div>
      <table className="w-full">
        <thead className="bg-gray-50 text-sm">
          <tr>
            <th className="px-4 py-2 text-left">Name</th>
            <th className="px-4 py-2 text-right">Size</th>
            <th className="px-4 py-2 text-right">Records</th>
            <th className="px-4 py-2 text-right">Tables</th>
            <th className="px-4 py-2 text-center">Health</th>
          </tr>
        </thead>
        <tbody className="text-sm">
          {databases.map((d, i) => (
            <tr key={i} className="border-t">
              <td className="px-4 py-3 font-medium">{d.name}</td>
              <td className="px-4 py-3 text-right">{d.size_mb.toFixed(1)} MB</td>
              <td className="px-4 py-3 text-right">{d.record_count.toLocaleString()}</td>
              <td className="px-4 py-3 text-right">{d.table_count}</td>
              <td className="px-4 py-3 text-center">
                <StatusBadge status={d.health} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CachesTable({ caches }) {
  return (
    <div className="bg-white rounded-lg border mb-6">
      <div className="px-4 py-3 border-b bg-gray-50">
        <h3 className="font-semibold">Caches</h3>
      </div>
      <table className="w-full">
        <thead className="bg-gray-50 text-sm">
          <tr>
            <th className="px-4 py-2 text-left">Name</th>
            <th className="px-4 py-2 text-right">Size</th>
            <th className="px-4 py-2 text-right">Files</th>
            <th className="px-4 py-2 text-left">Newest</th>
          </tr>
        </thead>
        <tbody className="text-sm">
          {caches.map((c, i) => (
            <tr key={i} className="border-t">
              <td className="px-4 py-3 font-medium">{c.name}</td>
              <td className="px-4 py-3 text-right">{c.size_mb.toFixed(1)} MB</td>
              <td className="px-4 py-3 text-right">{c.file_count}</td>
              <td className="px-4 py-3 text-gray-600">
                {c.newest_file ? new Date(c.newest_file).toLocaleString() : 'N/A'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function PipelineHealth() {
  const { data, loading, error, refetch } = useApi('/api/health/pipeline-status')

  if (loading) return <div className="text-center py-8">Loading system health...</div>
  if (error) return <div className="text-center py-8 text-red-600">Error loading health status</div>
  if (!data) return null

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">Pipeline Health</h2>
        <button
          onClick={refetch}
          className="px-3 py-1 bg-blue-500 text-white rounded text-sm hover:bg-blue-600"
        >
          Refresh
        </button>
      </div>

      <OverallHealth data={data} />
      <ScrapersTable scrapers={data.scrapers} />
      <PipelinesTable pipelines={data.pipelines} />
      <DatabasesTable databases={data.databases} />
      <CachesTable caches={data.caches} />
    </div>
  )
}
```

2. Add route to `App.jsx`:

```jsx
import PipelineHealth from './pages/PipelineHealth'

// In routes array
{ path: '/health', label: 'Health', icon: '🩺' },

// In Routes
<Route path="/health" element={<PipelineHealth />} />
```

3. Commit: `feat: add pipeline health dashboard page`

---

## Task 4: Integration Test

**Steps:**

1. Test status collector:
```bash
python -c "
from utils.pipeline_status import PipelineStatusCollector
collector = PipelineStatusCollector()
health = collector.get_system_health()
print(f'Overall: {health.overall_status}')
print(f'Healthy: {health.healthy_count}, Warning: {health.warning_count}, Error: {health.error_count}')
for s in health.scrapers:
    print(f'  {s.name}: {s.status}')
"
```

2. Test API endpoint:
```bash
curl http://localhost:8008/api/health/pipeline-status
```

3. Test frontend at http://localhost:5173/health

4. Commit: `test: verify pipeline health dashboard`

---

## Verification

After completing all tasks:

1. **Status Collector**: Correctly identifies fresh/stale/error states
2. **API**: `/api/health/pipeline-status` returns full system health
3. **Dashboard**: Shows scrapers, pipelines, databases, caches
4. **Refresh**: Button updates status in real-time

---

## Future Enhancements

1. **Auto-refresh**: Poll status every 60 seconds
2. **Notifications**: Alert when status changes from healthy to degraded
3. **Run buttons**: Add ability to trigger individual scrapers/pipelines
4. **History**: Track status changes over time