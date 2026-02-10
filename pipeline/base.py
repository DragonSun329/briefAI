"""
Base Pipeline Interface

Defines the contract that all briefAI pipelines must implement.
Enables standardized registration, execution, and monitoring across
news, product, investing, china_ai, and future pipelines.

Usage:
    from pipeline.base import BasePipeline, PipelineConfig, PipelineResult, PipelineEvent

    class MyPipeline(BasePipeline):
        @property
        def pipeline_id(self) -> str:
            return "my_pipeline"

        @property
        def display_name(self) -> str:
            return "My Custom Pipeline"

        async def run(self, config: PipelineConfig) -> PipelineResult:
            async for event in self._emit_progress("scraping", 0, 100):
                yield event
            # ... do work ...
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Callable
from loguru import logger


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PipelineStatus(str, Enum):
    """Status of a pipeline execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    """Types of events a pipeline can emit during execution."""
    PROGRESS = "progress"          # Step progress update
    LOG = "log"                    # Log message
    METRIC = "metric"              # Numeric metric (articles scraped, etc.)
    ARTICLE = "article"            # Individual article processed
    ERROR = "error"                # Non-fatal error
    STAGE_START = "stage_start"    # Pipeline stage started
    STAGE_END = "stage_end"        # Pipeline stage completed
    RESULT = "result"              # Final result


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PipelineConfig:
    """Configuration passed to a pipeline at execution time."""
    target_date: datetime = field(default_factory=datetime.now)
    days_back: int = 7
    top_n: int = 10
    categories: Optional[List[str]] = None
    dry_run: bool = False
    # Model override (if None, uses config/models.yaml)
    model_override: Optional[str] = None
    # Extra pipeline-specific params
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def date_str(self) -> str:
        return self.target_date.strftime("%Y-%m-%d")


@dataclass
class PipelineEvent:
    """An event emitted during pipeline execution for streaming/monitoring."""
    event_type: EventType
    pipeline_id: str
    timestamp: float = field(default_factory=time.time)
    stage: Optional[str] = None
    message: Optional[str] = None
    progress: Optional[float] = None      # 0.0 - 1.0
    current: Optional[int] = None
    total: Optional[int] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for SSE/WebSocket transport."""
        d = {
            "event": self.event_type.value,
            "pipeline": self.pipeline_id,
            "timestamp": self.timestamp,
        }
        if self.stage:
            d["stage"] = self.stage
        if self.message:
            d["message"] = self.message
        if self.progress is not None:
            d["progress"] = round(self.progress, 3)
        if self.current is not None:
            d["current"] = self.current
        if self.total is not None:
            d["total"] = self.total
        if self.data:
            d["data"] = self.data
        return d


@dataclass
class StageResult:
    """Result of a single pipeline stage."""
    stage: str
    status: PipelineStatus
    items_in: int = 0
    items_out: int = 0
    duration_s: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Final result of a pipeline execution."""
    pipeline_id: str
    status: PipelineStatus
    report_path: Optional[str] = None
    articles_scraped: int = 0
    articles_selected: int = 0
    execution_time: float = 0.0
    error: Optional[str] = None
    stages: List[StageResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "status": self.status.value,
            "report_path": self.report_path,
            "articles_scraped": self.articles_scraped,
            "articles_selected": self.articles_selected,
            "execution_time": round(self.execution_time, 2),
            "error": self.error,
            "stages": [
                {
                    "stage": s.stage,
                    "status": s.status.value,
                    "items_in": s.items_in,
                    "items_out": s.items_out,
                    "duration_s": round(s.duration_s, 2),
                    "error": s.error,
                }
                for s in self.stages
            ],
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Base Pipeline
# ---------------------------------------------------------------------------

class BasePipeline(ABC):
    """
    Abstract base class for all briefAI pipelines.

    Subclasses must implement:
        - pipeline_id (property): unique string identifier
        - display_name (property): human-readable name
        - run(config): async generator yielding PipelineEvents, returns PipelineResult

    Provides helper methods for emitting events and tracking stages.
    """

    def __init__(self):
        self._event_listeners: List[Callable[[PipelineEvent], None]] = []
        self._cancelled = False

    # ---- Abstract interface ----

    @property
    @abstractmethod
    def pipeline_id(self) -> str:
        """Unique identifier for this pipeline (e.g., 'news', 'investing')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g., 'AI Industry News')."""
        ...

    @abstractmethod
    async def run(self, config: PipelineConfig) -> AsyncGenerator[PipelineEvent, None]:
        """
        Execute the pipeline, yielding events as work progresses.

        The last yielded event should be of type RESULT with the PipelineResult
        in event.data["result"].

        Args:
            config: Execution configuration.

        Yields:
            PipelineEvent: Progress, log, metric, and result events.
        """
        ...

    # ---- Optional overrides ----

    def get_sources(self) -> List[Dict[str, Any]]:
        """Return the list of sources this pipeline scrapes from. Override in subclass."""
        return []

    def get_default_categories(self) -> List[str]:
        """Return default category IDs. Override in subclass."""
        return []

    # ---- Event helpers ----

    def _event(self, event_type: EventType, **kwargs) -> PipelineEvent:
        """Create a PipelineEvent with this pipeline's ID."""
        return PipelineEvent(
            event_type=event_type,
            pipeline_id=self.pipeline_id,
            **kwargs,
        )

    def _progress(
        self,
        stage: str,
        current: int,
        total: int,
        message: Optional[str] = None,
    ) -> PipelineEvent:
        """Create a progress event."""
        progress = current / total if total > 0 else 0.0
        return self._event(
            EventType.PROGRESS,
            stage=stage,
            current=current,
            total=total,
            progress=progress,
            message=message or f"{stage}: {current}/{total}",
        )

    def _stage_start(self, stage: str, message: Optional[str] = None) -> PipelineEvent:
        """Emit a stage start event."""
        return self._event(
            EventType.STAGE_START,
            stage=stage,
            message=message or f"Starting {stage}...",
        )

    def _stage_end(
        self,
        stage: str,
        items_in: int = 0,
        items_out: int = 0,
        duration_s: float = 0.0,
        message: Optional[str] = None,
    ) -> PipelineEvent:
        """Emit a stage end event."""
        return self._event(
            EventType.STAGE_END,
            stage=stage,
            message=message or f"{stage} complete: {items_out} items",
            data={
                "items_in": items_in,
                "items_out": items_out,
                "duration_s": round(duration_s, 2),
            },
        )

    def _log(self, message: str, stage: Optional[str] = None) -> PipelineEvent:
        """Emit a log event."""
        return self._event(EventType.LOG, message=message, stage=stage)

    def _metric(self, name: str, value: Any, stage: Optional[str] = None) -> PipelineEvent:
        """Emit a metric event."""
        return self._event(
            EventType.METRIC,
            stage=stage,
            message=f"{name}: {value}",
            data={"metric_name": name, "metric_value": value},
        )

    def _error(self, message: str, stage: Optional[str] = None) -> PipelineEvent:
        """Emit a non-fatal error event."""
        return self._event(EventType.ERROR, message=message, stage=stage)

    def _result(self, result: PipelineResult) -> PipelineEvent:
        """Emit the final result event."""
        return self._event(
            EventType.RESULT,
            message=f"Pipeline {self.pipeline_id} {result.status.value}",
            data={"result": result.to_dict()},
        )

    # ---- Cancellation ----

    def cancel(self):
        """Request cancellation of the running pipeline."""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def _check_cancelled(self):
        """Raise if cancellation was requested."""
        if self._cancelled:
            raise PipelineCancelled(self.pipeline_id)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class PipelineRegistry:
    """
    Registry for pipeline implementations.

    Usage:
        registry = PipelineRegistry()
        registry.register(NewsPipeline())
        registry.register(InvestingPipeline())

        # Get a specific pipeline
        news = registry.get("news")

        # List all
        for p in registry.all():
            print(p.pipeline_id, p.display_name)
    """

    def __init__(self):
        self._pipelines: Dict[str, BasePipeline] = {}

    def register(self, pipeline: BasePipeline) -> None:
        """Register a pipeline instance."""
        if pipeline.pipeline_id in self._pipelines:
            logger.warning(f"Overwriting registered pipeline: {pipeline.pipeline_id}")
        self._pipelines[pipeline.pipeline_id] = pipeline
        logger.info(f"Registered pipeline: {pipeline.pipeline_id} ({pipeline.display_name})")

    def get(self, pipeline_id: str) -> Optional[BasePipeline]:
        """Get a pipeline by ID."""
        return self._pipelines.get(pipeline_id)

    def all(self) -> List[BasePipeline]:
        """Get all registered pipelines."""
        return list(self._pipelines.values())

    def ids(self) -> List[str]:
        """Get all registered pipeline IDs."""
        return list(self._pipelines.keys())

    def __contains__(self, pipeline_id: str) -> bool:
        return pipeline_id in self._pipelines

    def __len__(self) -> int:
        return len(self._pipelines)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PipelineCancelled(Exception):
    """Raised when a pipeline is cancelled during execution."""
    def __init__(self, pipeline_id: str):
        self.pipeline_id = pipeline_id
        super().__init__(f"Pipeline {pipeline_id} was cancelled")


class PipelineError(Exception):
    """Base exception for pipeline errors."""
    def __init__(self, pipeline_id: str, stage: str, message: str):
        self.pipeline_id = pipeline_id
        self.stage = stage
        super().__init__(f"[{pipeline_id}/{stage}] {message}")
