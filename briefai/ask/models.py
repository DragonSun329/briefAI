"""
Data models for Ask Mode.

Defines the structures for ask logs, tool calls, and measurable checks.
All models are serializable to JSONL for the append-only ask log.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from enum import Enum


def _utc_now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class SourceCategory(str, Enum):
    """Categories of evidence sources for diversity checking."""
    FINANCIAL = "financial"
    TECHNICAL = "technical"
    MEDIA = "media"
    SOCIAL = "social"
    PRODUCT = "product"
    COMPANY = "company"
    META = "meta"  # Meta-signals
    UNKNOWN = "unknown"


@dataclass
class MeasurableCheck:
    """
    A measurable prediction extracted from the answer.
    
    Every strong conclusion must have at least 2 of these.
    """
    metric: str                      # e.g., "github_stars", "article_count"
    entity: str                      # e.g., "OpenAI", "LangChain"
    direction: str                   # "up", "down", "flat"
    window_days: int                 # Evaluation window
    baseline_date: Optional[str] = None
    baseline_value: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MeasurableCheck":
        return cls(**d)


@dataclass
class EvidenceLink:
    """Reference to evidence used in the answer."""
    source_type: str                 # "meta_signal", "signal", "entity_profile", "brief"
    source_id: str                   # ID or date
    category: SourceCategory = SourceCategory.UNKNOWN
    snippet: Optional[str] = None    # Brief excerpt
    confidence: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EvidenceLink":
        d = d.copy()
        if "category" in d:
            d["category"] = SourceCategory(d["category"])
        return cls(**d)


@dataclass
class EvidenceRef:
    """
    Machine-readable evidence citation for grep-able artifact references.
    
    Format: [evidence: <artifact_path>#<anchor>]
    
    Examples:
    - [evidence: data/briefs/analyst_brief_2026-02-11.md#L120-L140]
    - [evidence: data/public/experiments/v2_2_forward_test/daily_snapshot_2026-02-11.json#meta_id=abc123]
    - [evidence: data/meta_signals/meta_signals_2026-02-11.json#concept=AI_Pricing]
    """
    artifact_path: str               # Relative path from data/
    anchor: str                      # Line range, ID, or key
    as_of_date: Optional[str] = None # Data freshness date
    relevance_hint: Optional[str] = None  # Why this evidence is relevant
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EvidenceRef":
        return cls(**d)
    
    def to_citation(self) -> str:
        """Generate the grep-able citation string."""
        return f"[evidence: {self.artifact_path}#{self.anchor}]"
    
    @classmethod
    def from_citation(cls, citation: str) -> Optional["EvidenceRef"]:
        """Parse a citation string back into EvidenceRef."""
        import re
        match = re.match(r"\[evidence:\s*([^#]+)#([^\]]+)\]", citation)
        if match:
            return cls(artifact_path=match.group(1).strip(), anchor=match.group(2).strip())
        return None
    
    def __str__(self) -> str:
        return self.to_citation()


@dataclass
class ToolCallRecord:
    """Record of a single tool invocation."""
    tool_name: str
    arguments: Dict[str, Any]
    result_summary: str              # Truncated/summarized result
    result_type: str                 # "success", "data_missing", "error"
    duration_ms: Optional[int] = None
    timestamp: str = field(default_factory=_utc_now_iso)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ToolCallRecord":
        return cls(**d)


@dataclass
class AskLogEntry:
    """
    Complete log entry for a single ask invocation.
    
    Written to: data/public/experiments/{experiment_id}/ask_logs/ask_history.jsonl
    """
    # Input
    question: str
    experiment_id: str
    
    # Agentic loop trace
    plan: str                        # Initial plan from LLM
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    tool_results_summaries: List[str] = field(default_factory=list)
    
    # Output
    evidence_links: List[EvidenceLink] = field(default_factory=list)
    measurable_checks: List[MeasurableCheck] = field(default_factory=list)
    final_answer: str = ""
    
    # Quality assessment
    confidence_level: str = "low"    # "low", "medium", "high", "insufficient"
    review_required: bool = False
    quality_notes: List[str] = field(default_factory=list)
    
    # Metadata
    commit_hash: str = "unknown"
    engine_tag: Optional[str] = None
    timestamp_utc: str = field(default_factory=_utc_now_iso)
    duration_ms: Optional[int] = None
    
    # Loop stats
    loop_iterations: int = 0
    loop_warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        d = {
            "question": self.question,
            "experiment_id": self.experiment_id,
            "plan": self.plan,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "tool_results_summaries": self.tool_results_summaries,
            "evidence_links": [el.to_dict() for el in self.evidence_links],
            "measurable_checks": [mc.to_dict() for mc in self.measurable_checks],
            "final_answer": self.final_answer,
            "confidence_level": self.confidence_level,
            "review_required": self.review_required,
            "quality_notes": self.quality_notes,
            "commit_hash": self.commit_hash,
            "engine_tag": self.engine_tag,
            "timestamp_utc": self.timestamp_utc,
            "duration_ms": self.duration_ms,
            "loop_iterations": self.loop_iterations,
            "loop_warnings": self.loop_warnings,
        }
        return d
    
    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AskLogEntry":
        d = d.copy()
        if "tool_calls" in d:
            d["tool_calls"] = [ToolCallRecord.from_dict(tc) for tc in d["tool_calls"]]
        if "evidence_links" in d:
            d["evidence_links"] = [EvidenceLink.from_dict(el) for el in d["evidence_links"]]
        if "measurable_checks" in d:
            d["measurable_checks"] = [MeasurableCheck.from_dict(mc) for mc in d["measurable_checks"]]
        return cls(**d)
    
    @classmethod
    def from_jsonl(cls, line: str) -> "AskLogEntry":
        return cls.from_dict(json.loads(line))
    
    def get_source_categories(self) -> List[SourceCategory]:
        """Get unique source categories from evidence."""
        return list(set(el.category for el in self.evidence_links))
