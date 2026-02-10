"""Tests for the pipeline base interface and run store."""

import asyncio
import time
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.base import (
    BasePipeline,
    EventType,
    PipelineConfig,
    PipelineEvent,
    PipelineRegistry,
    PipelineResult,
    PipelineStatus,
    StageResult,
)
from pipeline.run_store import RunStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class MockPipeline(BasePipeline):
    """A minimal pipeline for testing."""

    @property
    def pipeline_id(self) -> str:
        return "mock"

    @property
    def display_name(self) -> str:
        return "Mock Pipeline"

    async def run(self, config: PipelineConfig):
        yield self._stage_start("fetch", "Fetching data...")
        yield self._progress("fetch", 5, 10)
        yield self._progress("fetch", 10, 10)
        yield self._stage_end("fetch", 0, 10, 1.5)

        yield self._stage_start("process")
        yield self._metric("quality_score", 8.5, "process")
        yield self._stage_end("process", 10, 3, 0.5)

        result = PipelineResult(
            pipeline_id=self.pipeline_id,
            status=PipelineStatus.COMPLETED,
            articles_scraped=10,
            articles_selected=3,
            execution_time=2.0,
            stages=[
                StageResult("fetch", PipelineStatus.COMPLETED, 0, 10, 1.5),
                StageResult("process", PipelineStatus.COMPLETED, 10, 3, 0.5),
            ],
        )
        yield self._result(result)


# ---------------------------------------------------------------------------
# Tests: BasePipeline
# ---------------------------------------------------------------------------

def test_pipeline_properties():
    p = MockPipeline()
    assert p.pipeline_id == "mock"
    assert p.display_name == "Mock Pipeline"


@pytest.mark.asyncio
async def test_pipeline_run_yields_events():
    p = MockPipeline()
    config = PipelineConfig()
    events = []

    async for event in p.run(config):
        events.append(event)

    assert len(events) == 8  # 2 stage_starts + 2 progress + 1 metric + 2 stage_ends + 1 result
    assert events[0].event_type == EventType.STAGE_START
    assert events[0].stage == "fetch"
    assert events[1].event_type == EventType.PROGRESS
    assert events[1].progress == 0.5
    assert events[2].progress == 1.0
    assert events[3].event_type == EventType.STAGE_END
    assert events[-1].event_type == EventType.RESULT


@pytest.mark.asyncio
async def test_pipeline_events_serialize():
    p = MockPipeline()
    config = PipelineConfig()

    async for event in p.run(config):
        d = event.to_dict()
        assert "event" in d
        assert "pipeline" in d
        assert d["pipeline"] == "mock"


def test_pipeline_cancellation():
    p = MockPipeline()
    assert not p.is_cancelled
    p.cancel()
    assert p.is_cancelled


# ---------------------------------------------------------------------------
# Tests: PipelineRegistry
# ---------------------------------------------------------------------------

def test_registry():
    reg = PipelineRegistry()
    p = MockPipeline()
    reg.register(p)

    assert "mock" in reg
    assert len(reg) == 1
    assert reg.get("mock") is p
    assert reg.ids() == ["mock"]
    assert reg.all() == [p]
    assert reg.get("nonexistent") is None


# ---------------------------------------------------------------------------
# Tests: RunStore
# ---------------------------------------------------------------------------

def test_run_store_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_runs.db"
        store = RunStore(str(db_path))

        # Create
        run_id = store.create_run("mock", {"top_n": 5})
        assert run_id

        # Query
        run = store.get_run(run_id)
        assert run is not None
        assert run["pipeline_id"] == "mock"
        assert run["status"] == "running"
        assert run["config"]["top_n"] == 5

        # Complete
        result = PipelineResult(
            pipeline_id="mock",
            status=PipelineStatus.COMPLETED,
            articles_scraped=50,
            articles_selected=10,
            execution_time=5.5,
            stages=[
                StageResult("fetch", PipelineStatus.COMPLETED, 0, 50, 3.0),
                StageResult("eval", PipelineStatus.COMPLETED, 50, 10, 2.5),
            ],
        )
        store.complete_run(run_id, result)

        run = store.get_run(run_id)
        assert run["status"] == "completed"
        assert run["articles_scraped"] == 50
        assert len(run["stages"]) == 2

        # List
        runs = store.list_runs(pipeline_id="mock")
        assert len(runs) == 1

        # Stats
        stats = store.get_stats()
        assert stats["total_runs"] == 1
        assert stats["completed"] == 1


def test_run_store_events():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_runs.db"
        store = RunStore(str(db_path))

        run_id = store.create_run("mock")

        event = PipelineEvent(
            event_type=EventType.PROGRESS,
            pipeline_id="mock",
            stage="fetch",
            progress=0.5,
            message="50% done",
        )
        store.log_event(run_id, event)

        events = store.get_events(run_id)
        assert len(events) == 1
        assert events[0]["event_type"] == "progress"
        assert events[0]["stage"] == "fetch"


def test_run_store_fail():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_runs.db"
        store = RunStore(str(db_path))

        run_id = store.create_run("mock")
        store.fail_run(run_id, "Connection timeout")

        run = store.get_run(run_id)
        assert run["status"] == "failed"
        assert run["error"] == "Connection timeout"
