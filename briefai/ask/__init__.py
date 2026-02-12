"""
briefAI Ask Mode - Dexter-style interactive research.

An agentic loop for answering questions using local pipeline artifacts.
Deterministic, offline, experiment-isolated.

v1.1 adds:
- Freshness banner (data recency indicator)
- Evidence citations (grep-able artifact references)
- Intent router (reduces tool thrash)

v1.2 adds:
- Reflection self-check loop (validate -> repair -> final)
- Daily diff mode ("what changed today?")
- Stable evidence anchors (no fragile line numbers)
"""

from .engine import AskEngine
from .models import AskLogEntry, ToolCallRecord, MeasurableCheck, EvidenceRef
from .tools import ToolRegistry, DataMissing
from .scratchpad import Scratchpad
from .quality_gates import QualityGates
from .freshness import get_latest_artifact_dates, FreshnessSummary
from .intent_router import route_intent, IntentPlan, Intent
from .reflection import validate_answer, ValidationReport, ValidationStatus
from .evidence_anchor import (
    generate_evidence_ref,
    StableEvidenceRef,
    generate_evidence_appendix,
    extract_citations_from_answer,
)
from .diff_tool import get_daily_diff, DiffResult

__all__ = [
    # Core
    "AskEngine",
    "AskLogEntry",
    "ToolCallRecord",
    "MeasurableCheck",
    "ToolRegistry",
    "DataMissing",
    "Scratchpad",
    "QualityGates",
    # v1.1: Freshness
    "get_latest_artifact_dates",
    "FreshnessSummary",
    # v1.1: Citations
    "EvidenceRef",
    # v1.1: Intent routing
    "route_intent",
    "IntentPlan",
    "Intent",
    # v1.2: Reflection
    "validate_answer",
    "ValidationReport",
    "ValidationStatus",
    # v1.2: Stable evidence
    "generate_evidence_ref",
    "StableEvidenceRef",
    "generate_evidence_appendix",
    "extract_citations_from_answer",
    # v1.2: Daily diff
    "get_daily_diff",
    "DiffResult",
]
