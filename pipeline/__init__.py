"""
Pipeline orchestration module for multi-pipeline execution.

Supports running multiple independent pipelines (news, product, investing, china_ai)
with parallel execution, cross-pipeline aggregation, and trend radar updates.
"""

# TEMPORARY: Apply spaCy patch for Python 3.14 before importing orchestrator
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    import utils.entity_extractor_patch  # noqa: F401
except ImportError:
    pass

from pipeline.orchestrator import PipelineOrchestrator

# New pipeline interface (v2)
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

__all__ = [
    # Legacy orchestrator
    'PipelineOrchestrator',
    # New pipeline interface
    'BasePipeline',
    'EventType',
    'PipelineConfig',
    'PipelineEvent',
    'PipelineRegistry',
    'PipelineResult',
    'PipelineStatus',
    'StageResult',
    'RunStore',
]
