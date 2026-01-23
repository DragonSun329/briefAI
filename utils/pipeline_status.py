"""Pipeline status collector for health dashboard."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
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
            except Exception:
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
                    except Exception:
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
                        cursor.execute(f"SELECT COUNT(*) FROM \"{table}\"")
                        record_count += cursor.fetchone()[0]
                    except Exception:
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

            except Exception:
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
        if total == 0:
            overall = "critical"
        elif error > total * 0.3:
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


if __name__ == "__main__":
    collector = PipelineStatusCollector()
    health = collector.get_system_health()
    print(f"Overall: {health.overall_status}")
    print(f"Healthy: {health.healthy_count}, Warning: {health.warning_count}, Error: {health.error_count}")
    print("\nScrapers:")
    for s in health.scrapers:
        print(f"  {s.name}: {s.status} ({s.record_count} records)")
    print("\nPipelines:")
    for p in health.pipelines:
        print(f"  {p.name}: {p.status} ({p.output_count} outputs)")
    print("\nDatabases:")
    for d in health.databases:
        print(f"  {d.name}: {d.health} ({d.size_mb:.1f} MB, {d.record_count} records)")