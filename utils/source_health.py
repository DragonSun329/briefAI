"""
Source Health Monitoring Module

Tracks health metrics for data scrapers/sources with:
- Success/failure rate tracking
- Circuit breaker for failing sources
- Automatic retry with backoff
- Dashboard-ready health status
"""

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from enum import Enum
import time


class SourceStatus(str, Enum):
    """Health status of a data source."""
    HEALTHY = "healthy"           # Operating normally
    DEGRADED = "degraded"         # Some failures, still usable
    UNHEALTHY = "unhealthy"       # High failure rate
    CIRCUIT_OPEN = "circuit_open" # Circuit breaker tripped
    UNKNOWN = "unknown"           # No recent data


@dataclass
class SourceHealthConfig:
    """Configuration for source health monitoring."""
    # Failure thresholds
    failure_threshold: int = 3         # Consecutive failures to trip circuit
    degraded_threshold: float = 0.7    # Success rate for degraded status
    healthy_threshold: float = 0.9     # Success rate for healthy status

    # Circuit breaker
    circuit_timeout_minutes: int = 30  # How long circuit stays open
    half_open_requests: int = 2        # Requests to allow in half-open state

    # Retry configuration
    max_retries: int = 3
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    backoff_multiplier: float = 2.0

    # Monitoring window
    health_window_hours: int = 24      # Window for health calculations


@dataclass
class SourceMetrics:
    """Metrics for a single data source."""
    source_name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    consecutive_failures: int = 0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    last_error: Optional[str] = None
    avg_latency_ms: float = 0.0
    circuit_opened_at: Optional[datetime] = None
    status: SourceStatus = SourceStatus.UNKNOWN

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    @property
    def is_circuit_open(self) -> bool:
        """Check if circuit breaker is currently open."""
        return self.status == SourceStatus.CIRCUIT_OPEN

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_name": self.source_name,
            "status": self.status.value,
            "success_rate": round(self.success_rate, 3),
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "consecutive_failures": self.consecutive_failures,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
            "last_error": self.last_error,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "circuit_opened_at": self.circuit_opened_at.isoformat() if self.circuit_opened_at else None,
        }


# Backwards compatibility alias
SourceHealthRecord = SourceMetrics


class SourceHealthMonitor:
    """
    Monitors health of data sources with circuit breaker pattern.

    Features:
    - Track success/failure per source
    - Automatic circuit breaker
    - Retry with exponential backoff
    - Health dashboard data
    """

    def __init__(self, config: SourceHealthConfig = None,
                 db_path: Path = None):
        """
        Initialize health monitor.

        Args:
            config: Health monitoring configuration
            db_path: Path to SQLite database
        """
        self.config = config or SourceHealthConfig()
        self.db_path = db_path or Path("data/source_health.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

        # In-memory metrics cache
        self._metrics_cache: Dict[str, SourceMetrics] = {}

    def _create_tables(self) -> None:
        """Create database tables."""
        cursor = self.conn.cursor()

        # Source metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS source_metrics (
                source_name TEXT PRIMARY KEY,
                total_requests INTEGER DEFAULT 0,
                successful_requests INTEGER DEFAULT 0,
                failed_requests INTEGER DEFAULT 0,
                consecutive_failures INTEGER DEFAULT 0,
                last_success TEXT,
                last_failure TEXT,
                last_error TEXT,
                avg_latency_ms REAL DEFAULT 0,
                circuit_opened_at TEXT,
                status TEXT DEFAULT 'unknown'
            )
        """)

        # Request log for detailed history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS request_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                success INTEGER NOT NULL,
                latency_ms REAL,
                error_message TEXT,
                response_size INTEGER
            )
        """)

        # Index for efficient queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_request_log_source_time
            ON request_log(source_name, timestamp)
        """)

        self.conn.commit()

    def get_metrics(self, source_name: str) -> SourceMetrics:
        """Get current metrics for a source."""
        if source_name in self._metrics_cache:
            return self._metrics_cache[source_name]

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM source_metrics WHERE source_name = ?",
            (source_name,)
        )
        row = cursor.fetchone()

        if row:
            metrics = SourceMetrics(
                source_name=source_name,
                total_requests=row["total_requests"],
                successful_requests=row["successful_requests"],
                failed_requests=row["failed_requests"],
                consecutive_failures=row["consecutive_failures"],
                last_success=datetime.fromisoformat(row["last_success"]) if row["last_success"] else None,
                last_failure=datetime.fromisoformat(row["last_failure"]) if row["last_failure"] else None,
                last_error=row["last_error"],
                avg_latency_ms=row["avg_latency_ms"],
                circuit_opened_at=datetime.fromisoformat(row["circuit_opened_at"]) if row["circuit_opened_at"] else None,
                status=SourceStatus(row["status"]) if row["status"] else SourceStatus.UNKNOWN,
            )
        else:
            metrics = SourceMetrics(source_name=source_name)

        self._metrics_cache[source_name] = metrics
        return metrics

    def record_success(self, source_name: str, latency_ms: float = None,
                       response_size: int = None) -> SourceMetrics:
        """
        Record a successful request.

        Args:
            source_name: Source identifier
            latency_ms: Request latency in milliseconds
            response_size: Response size in bytes

        Returns:
            Updated metrics
        """
        metrics = self.get_metrics(source_name)

        metrics.total_requests += 1
        metrics.successful_requests += 1
        metrics.consecutive_failures = 0
        metrics.last_success = datetime.now()

        # Update average latency
        if latency_ms is not None:
            if metrics.successful_requests == 1:
                metrics.avg_latency_ms = latency_ms
            else:
                # Exponential moving average
                alpha = 0.2
                metrics.avg_latency_ms = (
                    alpha * latency_ms +
                    (1 - alpha) * metrics.avg_latency_ms
                )

        # Update status
        metrics.status = self._compute_status(metrics)

        # Reset circuit if it was open
        if metrics.circuit_opened_at:
            metrics.circuit_opened_at = None

        # Persist
        self._save_metrics(metrics)
        self._log_request(source_name, True, latency_ms, None, response_size)

        return metrics

    def record_failure(self, source_name: str, error: str = None,
                       latency_ms: float = None) -> SourceMetrics:
        """
        Record a failed request.

        Args:
            source_name: Source identifier
            error: Error message
            latency_ms: Request latency before failure

        Returns:
            Updated metrics
        """
        metrics = self.get_metrics(source_name)

        metrics.total_requests += 1
        metrics.failed_requests += 1
        metrics.consecutive_failures += 1
        metrics.last_failure = datetime.now()
        metrics.last_error = error

        # Check if circuit should open
        if metrics.consecutive_failures >= self.config.failure_threshold:
            metrics.status = SourceStatus.CIRCUIT_OPEN
            metrics.circuit_opened_at = datetime.now()
        else:
            metrics.status = self._compute_status(metrics)

        # Persist
        self._save_metrics(metrics)
        self._log_request(source_name, False, latency_ms, error, None)

        return metrics

    def _compute_status(self, metrics: SourceMetrics) -> SourceStatus:
        """Compute health status from metrics."""
        # Check circuit breaker first
        if metrics.circuit_opened_at:
            timeout = timedelta(minutes=self.config.circuit_timeout_minutes)
            if datetime.now() - metrics.circuit_opened_at < timeout:
                return SourceStatus.CIRCUIT_OPEN

        if metrics.total_requests == 0:
            return SourceStatus.UNKNOWN

        rate = metrics.success_rate

        if rate >= self.config.healthy_threshold:
            return SourceStatus.HEALTHY
        elif rate >= self.config.degraded_threshold:
            return SourceStatus.DEGRADED
        else:
            return SourceStatus.UNHEALTHY

    def _save_metrics(self, metrics: SourceMetrics) -> None:
        """Save metrics to database."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO source_metrics (
                source_name, total_requests, successful_requests,
                failed_requests, consecutive_failures, last_success,
                last_failure, last_error, avg_latency_ms,
                circuit_opened_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            metrics.source_name,
            metrics.total_requests,
            metrics.successful_requests,
            metrics.failed_requests,
            metrics.consecutive_failures,
            metrics.last_success.isoformat() if metrics.last_success else None,
            metrics.last_failure.isoformat() if metrics.last_failure else None,
            metrics.last_error,
            metrics.avg_latency_ms,
            metrics.circuit_opened_at.isoformat() if metrics.circuit_opened_at else None,
            metrics.status.value,
        ))
        self.conn.commit()

    def _log_request(self, source_name: str, success: bool,
                     latency_ms: float = None, error: str = None,
                     response_size: int = None) -> None:
        """Log request to history."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO request_log (
                source_name, timestamp, success, latency_ms,
                error_message, response_size
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            source_name,
            datetime.now().isoformat(),
            1 if success else 0,
            latency_ms,
            error,
            response_size,
        ))
        self.conn.commit()

    def is_source_available(self, source_name: str) -> bool:
        """
        Check if source is available for requests.

        Respects circuit breaker status.
        """
        metrics = self.get_metrics(source_name)

        if metrics.status == SourceStatus.CIRCUIT_OPEN:
            # Check if timeout has passed (half-open state)
            if metrics.circuit_opened_at:
                timeout = timedelta(minutes=self.config.circuit_timeout_minutes)
                if datetime.now() - metrics.circuit_opened_at >= timeout:
                    return True  # Allow one request to test
            return False

        return True

    def get_retry_delay(self, source_name: str, attempt: int) -> float:
        """
        Get retry delay with exponential backoff.

        Args:
            source_name: Source identifier
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds before next retry
        """
        delay = self.config.base_backoff_seconds * (
            self.config.backoff_multiplier ** attempt
        )
        return min(delay, self.config.max_backoff_seconds)

    def get_all_source_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all tracked sources."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM source_metrics")

        results = {}
        for row in cursor.fetchall():
            source_name = row["source_name"]
            metrics = SourceMetrics(
                source_name=source_name,
                total_requests=row["total_requests"],
                successful_requests=row["successful_requests"],
                failed_requests=row["failed_requests"],
                consecutive_failures=row["consecutive_failures"],
                last_success=datetime.fromisoformat(row["last_success"]) if row["last_success"] else None,
                last_failure=datetime.fromisoformat(row["last_failure"]) if row["last_failure"] else None,
                last_error=row["last_error"],
                avg_latency_ms=row["avg_latency_ms"],
                circuit_opened_at=datetime.fromisoformat(row["circuit_opened_at"]) if row["circuit_opened_at"] else None,
                status=SourceStatus(row["status"]) if row["status"] else SourceStatus.UNKNOWN,
            )
            # Recompute status in case timeout expired
            metrics.status = self._compute_status(metrics)
            results[source_name] = metrics.to_dict()

        return results

    def get_health_summary(self) -> Dict[str, Any]:
        """Get aggregate health summary."""
        all_status = self.get_all_source_status()

        healthy = sum(1 for s in all_status.values() if s["status"] == "healthy")
        degraded = sum(1 for s in all_status.values() if s["status"] == "degraded")
        unhealthy = sum(1 for s in all_status.values() if s["status"] == "unhealthy")
        circuit_open = sum(1 for s in all_status.values() if s["status"] == "circuit_open")

        total = len(all_status)
        overall_health = healthy / total if total > 0 else 0

        return {
            "total_sources": total,
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "circuit_open": circuit_open,
            "overall_health": round(overall_health, 2),
            "status": "healthy" if overall_health >= 0.8 else "degraded" if overall_health >= 0.5 else "unhealthy",
            "sources": all_status,
        }

    def get_recent_errors(self, source_name: str = None,
                          hours: int = 24, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent error logs."""
        cursor = self.conn.cursor()
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        if source_name:
            cursor.execute("""
                SELECT * FROM request_log
                WHERE source_name = ? AND success = 0 AND timestamp > ?
                ORDER BY timestamp DESC LIMIT ?
            """, (source_name, cutoff, limit))
        else:
            cursor.execute("""
                SELECT * FROM request_log
                WHERE success = 0 AND timestamp > ?
                ORDER BY timestamp DESC LIMIT ?
            """, (cutoff, limit))

        return [
            {
                "source_name": row["source_name"],
                "timestamp": row["timestamp"],
                "error": row["error_message"],
                "latency_ms": row["latency_ms"],
            }
            for row in cursor.fetchall()
        ]

    def reset_circuit(self, source_name: str) -> None:
        """Manually reset circuit breaker for a source."""
        metrics = self.get_metrics(source_name)
        metrics.circuit_opened_at = None
        metrics.consecutive_failures = 0
        metrics.status = self._compute_status(metrics)
        self._save_metrics(metrics)

    def cleanup_old_logs(self, days: int = 30) -> int:
        """Remove old request logs."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM request_log WHERE timestamp < ?", (cutoff,))
        deleted = cursor.rowcount
        self.conn.commit()
        return deleted

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()


class HealthAwareRequester:
    """
    Wrapper for making health-aware requests with automatic retry.

    Example usage:
        monitor = SourceHealthMonitor()
        requester = HealthAwareRequester(monitor)

        result = requester.request(
            "my_scraper",
            lambda: requests.get("https://api.example.com/data")
        )
    """

    def __init__(self, monitor: SourceHealthMonitor):
        """Initialize with health monitor."""
        self.monitor = monitor

    def request(self, source_name: str, request_func,
                max_retries: int = None) -> Any:
        """
        Execute request with health monitoring and retry.

        Args:
            source_name: Source identifier for tracking
            request_func: Function to execute (should return response)
            max_retries: Override for max retries

        Returns:
            Response from request_func

        Raises:
            Exception: If all retries exhausted
        """
        if not self.monitor.is_source_available(source_name):
            raise Exception(f"Source {source_name} is unavailable (circuit open)")

        retries = max_retries or self.monitor.config.max_retries
        last_error = None

        for attempt in range(retries + 1):
            if attempt > 0:
                delay = self.monitor.get_retry_delay(source_name, attempt - 1)
                time.sleep(delay)

            start_time = time.time()
            try:
                result = request_func()
                latency_ms = (time.time() - start_time) * 1000

                self.monitor.record_success(
                    source_name,
                    latency_ms=latency_ms,
                )
                return result

            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                last_error = str(e)

                self.monitor.record_failure(
                    source_name,
                    error=last_error,
                    latency_ms=latency_ms,
                )

                if not self.monitor.is_source_available(source_name):
                    raise Exception(f"Source {source_name} circuit opened after failure: {last_error}")

        raise Exception(f"Source {source_name} failed after {retries + 1} attempts: {last_error}")