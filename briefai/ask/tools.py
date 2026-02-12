"""
Unified Tool Registry for Ask Mode.

Wraps existing briefAI artifacts with a deterministic, offline interface.
All tools return structured results; network access is prohibited.

Tools:
1. search_meta_signals(query, date_range) - Search synthesized meta-signals
2. search_signals(query, date_range) - Search raw signals
3. get_entity_profile(entity) - Get entity profile with scores
4. summarize_daily_brief(date) - Get daily brief summary
5. retrieve_evidence(entity, canonical_metric) - Get evidence for a metric
6. list_hypotheses(date) - List active hypotheses
7. get_forecast_snapshot(date) - Get forecast snapshot for a date
"""

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from loguru import logger

# Import briefAI utilities (must be installed)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.entity_store import EntityStore
from utils.meta_signal_engine import MATURITY_PRIORITY
from briefai.ask.models import SourceCategory, EvidenceLink, EvidenceRef


# =============================================================================
# DATA MISSING RESULT
# =============================================================================

@dataclass
class DataMissing:
    """
    Typed result indicating requested data does not exist.
    
    This is NOT an error - it's a valid response meaning
    the data hasn't been collected yet.
    """
    tool_name: str
    query: str
    reason: str
    suggestion: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def __str__(self) -> str:
        return f"DataMissing({self.tool_name}): {self.reason}"
    
    @property
    def is_missing(self) -> bool:
        return True


@dataclass
class ToolResult:
    """Standard wrapper for tool results."""
    success: bool
    data: Any
    source_category: SourceCategory
    evidence_links: List[EvidenceLink]
    summary: str
    evidence_refs: List[EvidenceRef] = None  # v1.1: grep-able citations
    as_of_date: Optional[str] = None         # v1.1: data freshness
    
    def __post_init__(self):
        if self.evidence_refs is None:
            self.evidence_refs = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data if not isinstance(self.data, DataMissing) else self.data.to_dict(),
            "source_category": self.source_category.value,
            "evidence_links": [el.to_dict() for el in self.evidence_links],
            "evidence_refs": [er.to_dict() for er in self.evidence_refs],
            "summary": self.summary,
            "as_of_date": self.as_of_date,
        }
    
    def get_citations(self) -> List[str]:
        """Get all citation strings for this result."""
        return [ref.to_citation() for ref in self.evidence_refs]
    
    @property
    def is_missing(self) -> bool:
        return isinstance(self.data, DataMissing)


# =============================================================================
# PATH UTILITIES
# =============================================================================

def get_data_path() -> Path:
    """Get the briefAI data directory."""
    return Path(__file__).parent.parent.parent / "data"


def get_experiment_path(experiment_id: str) -> Path:
    """Get the experiment-specific data path."""
    return get_data_path() / "public" / "experiments" / experiment_id


def validate_experiment_path(experiment_id: str) -> bool:
    """Check if experiment path exists."""
    return get_experiment_path(experiment_id).exists()


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def search_meta_signals(
    query: str,
    date_range: Optional[Tuple[str, str]] = None,
    experiment_id: Optional[str] = None,
) -> ToolResult:
    """
    Search synthesized meta-signals for concepts matching query.
    
    Args:
        query: Search query (concept name, entity, or keyword)
        date_range: Optional (start_date, end_date) in YYYY-MM-DD format
        experiment_id: Not used for meta-signals (shared across experiments)
    
    Returns:
        ToolResult with matching meta-signals
    """
    meta_signals_dir = get_data_path() / "meta_signals"
    
    if not meta_signals_dir.exists():
        return ToolResult(
            success=False,
            data=DataMissing(
                tool_name="search_meta_signals",
                query=query,
                reason="Meta-signals directory not found",
                suggestion="Run the daily pipeline to generate meta-signals",
            ),
            source_category=SourceCategory.META,
            evidence_links=[],
            summary="DataMissing: meta-signals directory not found",
        )
    
    # Determine date range
    if date_range:
        start_date, end_date = date_range
    else:
        # Default: last 7 days
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    # Find matching files
    matches = []
    evidence_links = []
    evidence_refs = []  # v1.1: grep-able citations
    latest_date = None
    query_lower = query.lower()
    
    for file_path in sorted(meta_signals_dir.glob("meta_signals_*.json")):
        # Extract date from filename
        file_date = file_path.stem.replace("meta_signals_", "")
        if not (start_date <= file_date <= end_date):
            continue
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for meta_signal in data.get("meta_signals", []):
                # Search in concept name, description, and supporting insights
                searchable = " ".join([
                    meta_signal.get("concept_name", ""),
                    meta_signal.get("description", ""),
                    " ".join(
                        ins.get("insight_text", "")
                        for ins in meta_signal.get("supporting_insights", [])
                    ),
                ]).lower()
                
                if query_lower in searchable:
                    meta_id = meta_signal.get("meta_id", "")
                    concept_name = meta_signal.get("concept_name", "")
                    
                    matches.append({
                        "date": file_date,
                        "meta_id": meta_id,
                        "concept_name": concept_name,
                        "description": meta_signal.get("description"),
                        "confidence": meta_signal.get("concept_confidence"),
                        "maturity_stage": meta_signal.get("maturity_stage"),
                        "entity_diversity": meta_signal.get("entity_diversity"),
                        "persistence_days": meta_signal.get("persistence_days"),
                        "validation_status": meta_signal.get("validation_status"),
                    })
                    
                    evidence_links.append(EvidenceLink(
                        source_type="meta_signal",
                        source_id=meta_id,
                        category=SourceCategory.META,
                        snippet=meta_signal.get("description", "")[:200],
                        confidence=meta_signal.get("concept_confidence", 0.5),
                    ))
                    
                    # v1.1: Add grep-able evidence ref
                    rel_path = f"data/meta_signals/{file_path.name}"
                    evidence_refs.append(EvidenceRef(
                        artifact_path=rel_path,
                        anchor=f"meta_id={meta_id}",
                        as_of_date=file_date,
                        relevance_hint=f"Meta-signal: {concept_name}",
                    ))
                    
                    # Track latest date
                    if latest_date is None or file_date > latest_date:
                        latest_date = file_date
                        
        except Exception as e:
            logger.debug(f"Error reading {file_path}: {e}")
            continue
    
    if not matches:
        return ToolResult(
            success=False,
            data=DataMissing(
                tool_name="search_meta_signals",
                query=query,
                reason=f"No meta-signals matching '{query}' in date range {start_date} to {end_date}",
                suggestion="Try a broader query or different date range",
            ),
            source_category=SourceCategory.META,
            evidence_links=[],
            evidence_refs=[],
            summary=f"DataMissing: no meta-signals for '{query}'",
        )
    
    return ToolResult(
        success=True,
        data=matches,
        source_category=SourceCategory.META,
        evidence_links=evidence_links,
        evidence_refs=evidence_refs,
        as_of_date=latest_date,
        summary=f"Found {len(matches)} meta-signals matching '{query}'",
    )


def search_signals(
    query: str,
    date_range: Optional[Tuple[str, str]] = None,
    signal_types: Optional[List[str]] = None,
) -> ToolResult:
    """
    Search raw signals from various pipelines.
    
    Args:
        query: Search query
        date_range: Optional (start_date, end_date)
        signal_types: Optional list of signal types to search
    
    Returns:
        ToolResult with matching signals
    """
    data_path = get_data_path()
    
    # Signal directories to search
    signal_dirs = signal_types or [
        "news_signals",
        "financial_signals",
        "social_signals",
        "product_signals",
        "paper_signals",
    ]
    
    # Determine date range
    if date_range:
        start_date, end_date = date_range
    else:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    matches = []
    evidence_links = []
    evidence_refs = []  # v1.1: grep-able citations
    latest_date = None
    query_lower = query.lower()
    
    for signal_type in signal_dirs:
        signal_dir = data_path / signal_type
        if not signal_dir.exists():
            continue
        
        # Map signal type to source category
        category_map = {
            "news_signals": SourceCategory.MEDIA,
            "financial_signals": SourceCategory.FINANCIAL,
            "social_signals": SourceCategory.SOCIAL,
            "product_signals": SourceCategory.PRODUCT,
            "paper_signals": SourceCategory.TECHNICAL,
        }
        category = category_map.get(signal_type, SourceCategory.UNKNOWN)
        
        for file_path in sorted(signal_dir.glob("*.json")):
            # Try to extract date from filename
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", file_path.name)
            file_date = date_match.group(1) if date_match else None
            if file_date:
                if not (start_date <= file_date <= end_date):
                    continue
            
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Handle both list and dict formats
                signals = data if isinstance(data, list) else data.get("signals", data.get("items", []))
                
                for idx, signal in enumerate(signals if isinstance(signals, list) else []):
                    # Search in relevant fields
                    searchable = " ".join([
                        str(signal.get("title", "")),
                        str(signal.get("name", "")),
                        str(signal.get("entity", "")),
                        str(signal.get("description", "")),
                        str(signal.get("summary", "")),
                    ]).lower()
                    
                    if query_lower in searchable:
                        signal_id = signal.get("id", f"idx_{idx}")
                        signal_title = str(signal.get("title", signal.get("name", "")))
                        
                        signal_entry = {
                            "type": signal_type,
                            "source_file": file_path.name,
                            "date": file_date,
                        }
                        # Include key fields
                        for key in ["title", "name", "entity", "description", "score", "confidence"]:
                            if key in signal:
                                signal_entry[key] = signal[key]
                        
                        matches.append(signal_entry)
                        
                        evidence_links.append(EvidenceLink(
                            source_type=signal_type,
                            source_id=signal_id,
                            category=category,
                            snippet=signal_title[:200],
                            confidence=signal.get("confidence", 0.7),
                        ))
                        
                        # v1.1: Add grep-able evidence ref
                        rel_path = f"data/{signal_type}/{file_path.name}"
                        evidence_refs.append(EvidenceRef(
                            artifact_path=rel_path,
                            anchor=f"id={signal_id}",
                            as_of_date=file_date,
                            relevance_hint=f"{signal_type}: {signal_title[:50]}",
                        ))
                        
                        # Track latest date
                        if file_date and (latest_date is None or file_date > latest_date):
                            latest_date = file_date
                            
            except Exception as e:
                logger.debug(f"Error reading {file_path}: {e}")
                continue
    
    if not matches:
        return ToolResult(
            success=False,
            data=DataMissing(
                tool_name="search_signals",
                query=query,
                reason=f"No signals matching '{query}' in searched directories",
                suggestion="Try searching in meta-signals or with a different query",
            ),
            source_category=SourceCategory.UNKNOWN,
            evidence_links=[],
            evidence_refs=[],
            summary=f"DataMissing: no signals for '{query}'",
        )
    
    return ToolResult(
        success=True,
        data=matches[:50],  # Limit results
        source_category=SourceCategory.UNKNOWN,  # Mixed
        evidence_links=evidence_links[:20],
        evidence_refs=evidence_refs[:20],
        as_of_date=latest_date,
        summary=f"Found {len(matches)} signals matching '{query}'",
    )


def get_entity_profile(entity: str) -> ToolResult:
    """
    Get entity profile with signal scores and mentions.
    
    Args:
        entity: Entity name to look up
    
    Returns:
        ToolResult with entity profile
    """
    try:
        store = EntityStore()
        entity_obj = store.find(entity)
        
        if not entity_obj:
            return ToolResult(
                success=False,
                data=DataMissing(
                    tool_name="get_entity_profile",
                    query=entity,
                    reason=f"Entity '{entity}' not found in store",
                    suggestion="Try a different name or alias",
                ),
                source_category=SourceCategory.COMPANY,
                evidence_links=[],
                summary=f"DataMissing: entity '{entity}' not found",
            )
        
        # Get velocity metrics
        velocity = store.get_mention_velocity(entity)
        
        # Get signal profile
        signal_profile = store.get_signal_profile(entity)
        
        profile_data = {
            "entity": entity_obj.to_dict(),
            "velocity": velocity,
            "signal_profile": signal_profile,
        }
        
        evidence_links = [EvidenceLink(
            source_type="entity_profile",
            source_id=entity_obj.id,
            category=SourceCategory.COMPANY,
            snippet=f"{entity_obj.canonical_name}: {velocity.get('7d', 0)} mentions (7d)",
            confidence=0.9,
        )]
        
        # v1.1: Add evidence refs
        evidence_refs = [EvidenceRef(
            artifact_path="data/signals.db",
            anchor=f"entity={entity_obj.canonical_name}",
            as_of_date=datetime.now().strftime("%Y-%m-%d"),
            relevance_hint=f"Entity profile: {entity_obj.canonical_name}",
        )]
        
        return ToolResult(
            success=True,
            data=profile_data,
            source_category=SourceCategory.COMPANY,
            evidence_links=evidence_links,
            evidence_refs=evidence_refs,
            as_of_date=datetime.now().strftime("%Y-%m-%d"),
            summary=f"Entity profile for '{entity}': {velocity.get('7d', 0)} mentions (7d), score={signal_profile.get('composite_score') if signal_profile else 'N/A'}",
        )
        
    except Exception as e:
        logger.error(f"Error getting entity profile: {e}")
        return ToolResult(
            success=False,
            data=DataMissing(
                tool_name="get_entity_profile",
                query=entity,
                reason=f"Error looking up entity: {e}",
            ),
            source_category=SourceCategory.COMPANY,
            evidence_links=[],
            summary=f"Error: {e}",
        )


def summarize_daily_brief(date: str) -> ToolResult:
    """
    Get daily brief summary for a specific date.
    
    Args:
        date: Date in YYYY-MM-DD format
    
    Returns:
        ToolResult with brief summaries
    """
    briefs_dir = get_data_path() / "briefs"
    
    if not briefs_dir.exists():
        return ToolResult(
            success=False,
            data=DataMissing(
                tool_name="summarize_daily_brief",
                query=date,
                reason="Briefs directory not found",
            ),
            source_category=SourceCategory.MEDIA,
            evidence_links=[],
            summary="DataMissing: briefs directory not found",
        )
    
    # Find briefs for the date
    briefs_found = []
    evidence_links = []
    evidence_refs = []  # v1.1
    
    for brief_type in ["analyst_brief", "investor_brief", "strategy_brief"]:
        brief_file = briefs_dir / f"{brief_type}_{date}.md"
        if brief_file.exists():
            try:
                content = brief_file.read_text(encoding="utf-8")
                lines = content.split('\n')
                line_count = len(lines)
                
                # Extract first 500 chars as summary
                briefs_found.append({
                    "type": brief_type,
                    "date": date,
                    "preview": content[:500] + "..." if len(content) > 500 else content,
                    "length_chars": len(content),
                    "line_count": line_count,
                })
                
                evidence_links.append(EvidenceLink(
                    source_type="daily_brief",
                    source_id=f"{brief_type}_{date}",
                    category=SourceCategory.MEDIA,
                    snippet=content[:200],
                    confidence=0.9,
                ))
                
                # v1.1: Add grep-able citation with line range
                evidence_refs.append(EvidenceRef(
                    artifact_path=f"data/briefs/{brief_type}_{date}.md",
                    anchor=f"L1-L{min(50, line_count)}",
                    as_of_date=date,
                    relevance_hint=f"Daily brief: {brief_type}",
                ))
            except Exception as e:
                logger.debug(f"Error reading brief: {e}")
    
    if not briefs_found:
        return ToolResult(
            success=False,
            data=DataMissing(
                tool_name="summarize_daily_brief",
                query=date,
                reason=f"No briefs found for {date}",
                suggestion="Try a different date or check if pipeline ran",
            ),
            source_category=SourceCategory.MEDIA,
            evidence_links=[],
            evidence_refs=[],
            summary=f"DataMissing: no briefs for {date}",
        )
    
    return ToolResult(
        success=True,
        data=briefs_found,
        source_category=SourceCategory.MEDIA,
        evidence_links=evidence_links,
        evidence_refs=evidence_refs,
        as_of_date=date,
        summary=f"Found {len(briefs_found)} briefs for {date}",
    )


def retrieve_evidence(
    entity: str,
    canonical_metric: str,
    experiment_id: Optional[str] = None,
) -> ToolResult:
    """
    Retrieve evidence for a specific metric and entity.
    
    Args:
        entity: Entity name
        canonical_metric: Metric name (e.g., "article_count", "github_stars")
        experiment_id: Optional experiment to search
    
    Returns:
        ToolResult with evidence observations
    """
    # This tool searches the evidence ledger
    evidence_dir = get_data_path() / "evidence"
    
    if not evidence_dir.exists():
        evidence_dir = get_data_path() / "predictions"  # Fallback
    
    if not evidence_dir.exists():
        return ToolResult(
            success=False,
            data=DataMissing(
                tool_name="retrieve_evidence",
                query=f"{entity}:{canonical_metric}",
                reason="Evidence directory not found",
            ),
            source_category=SourceCategory.UNKNOWN,
            evidence_links=[],
            summary="DataMissing: evidence directory not found",
        )
    
    # Search through evidence files
    matches = []
    entity_lower = entity.lower()
    metric_lower = canonical_metric.lower()
    
    for file_path in evidence_dir.glob("*.json*"):
        try:
            if file_path.suffix == ".jsonl":
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        record = json.loads(line)
                        if (entity_lower in str(record.get("entity", "")).lower() and
                            metric_lower in str(record.get("canonical_metric", "")).lower()):
                            matches.append(record)
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                records = data if isinstance(data, list) else [data]
                for record in records:
                    if (entity_lower in str(record.get("entity", "")).lower() and
                        metric_lower in str(record.get("canonical_metric", "")).lower()):
                        matches.append(record)
        except Exception as e:
            logger.debug(f"Error reading evidence file: {e}")
    
    if not matches:
        return ToolResult(
            success=False,
            data=DataMissing(
                tool_name="retrieve_evidence",
                query=f"{entity}:{canonical_metric}",
                reason=f"No evidence found for {entity} / {canonical_metric}",
            ),
            source_category=SourceCategory.UNKNOWN,
            evidence_links=[],
            evidence_refs=[],
            summary=f"DataMissing: no evidence for {entity}/{canonical_metric}",
        )
    
    # v1.1: Add evidence refs
    evidence_refs = [EvidenceRef(
        artifact_path="data/evidence/",
        anchor=f"entity={entity}&metric={canonical_metric}",
        as_of_date=datetime.now().strftime("%Y-%m-%d"),
        relevance_hint=f"Evidence for {entity}/{canonical_metric}",
    )]
    
    return ToolResult(
        success=True,
        data=matches[:20],
        source_category=SourceCategory.UNKNOWN,
        evidence_links=[
            EvidenceLink(
                source_type="evidence",
                source_id=f"{entity}:{canonical_metric}",
                category=SourceCategory.UNKNOWN,
                snippet=str(matches[0])[:200] if matches else "",
            )
        ],
        evidence_refs=evidence_refs,
        summary=f"Found {len(matches)} evidence records for {entity}/{canonical_metric}",
    )


def list_hypotheses(date: str, experiment_id: Optional[str] = None) -> ToolResult:
    """
    List active hypotheses for a date.
    
    Args:
        date: Date in YYYY-MM-DD format
        experiment_id: Optional experiment filter
    
    Returns:
        ToolResult with hypotheses
    """
    hypotheses_dir = get_data_path() / "hypotheses"
    
    if not hypotheses_dir.exists():
        return ToolResult(
            success=False,
            data=DataMissing(
                tool_name="list_hypotheses",
                query=date,
                reason="Hypotheses directory not found",
            ),
            source_category=SourceCategory.META,
            evidence_links=[],
            summary="DataMissing: hypotheses directory not found",
        )
    
    # Find hypothesis files
    matches = []
    evidence_refs = []  # v1.1
    for file_path in sorted(hypotheses_dir.glob("*.json")):
        if date in file_path.name:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                matches.append({
                    "file": file_path.name,
                    "data": data,
                })
                # v1.1: Add evidence ref
                evidence_refs.append(EvidenceRef(
                    artifact_path=f"data/hypotheses/{file_path.name}",
                    anchor="hypotheses",
                    as_of_date=date,
                    relevance_hint=f"Hypotheses for {date}",
                ))
            except Exception as e:
                logger.debug(f"Error reading hypothesis file: {e}")
    
    if not matches:
        return ToolResult(
            success=False,
            data=DataMissing(
                tool_name="list_hypotheses",
                query=date,
                reason=f"No hypotheses found for {date}",
            ),
            source_category=SourceCategory.META,
            evidence_links=[],
            evidence_refs=[],
            summary=f"DataMissing: no hypotheses for {date}",
        )
    
    return ToolResult(
        success=True,
        data=matches,
        source_category=SourceCategory.META,
        evidence_links=[],
        evidence_refs=evidence_refs,
        as_of_date=date,
        summary=f"Found {len(matches)} hypothesis files for {date}",
    )


def get_forecast_snapshot(date: str, experiment_id: str) -> ToolResult:
    """
    Get forecast snapshot for a date.
    
    Args:
        date: Date in YYYY-MM-DD format
        experiment_id: Experiment ID
    
    Returns:
        ToolResult with forecast snapshot
    """
    exp_path = get_experiment_path(experiment_id)
    snapshot_file = exp_path / f"daily_snapshot_{date}.json"
    
    if not snapshot_file.exists():
        return ToolResult(
            success=False,
            data=DataMissing(
                tool_name="get_forecast_snapshot",
                query=f"{experiment_id}:{date}",
                reason=f"No snapshot for {date} in experiment {experiment_id}",
                suggestion="Check if the forecast was generated for this date",
            ),
            source_category=SourceCategory.META,
            evidence_links=[],
            evidence_refs=[],
            summary=f"DataMissing: no snapshot for {date}",
        )
    
    try:
        with open(snapshot_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # v1.1: Add evidence ref
        rel_path = f"data/public/experiments/{experiment_id}/daily_snapshot_{date}.json"
        evidence_refs = [EvidenceRef(
            artifact_path=rel_path,
            anchor="predictions",
            as_of_date=date,
            relevance_hint=f"Forecast snapshot: {data.get('prediction_count', 0)} predictions",
        )]
        
        return ToolResult(
            success=True,
            data=data,
            source_category=SourceCategory.META,
            evidence_links=[
                EvidenceLink(
                    source_type="forecast_snapshot",
                    source_id=f"{experiment_id}:{date}",
                    category=SourceCategory.META,
                    snippet=f"Snapshot with {data.get('prediction_count', 0)} predictions",
                )
            ],
            evidence_refs=evidence_refs,
            as_of_date=date,
            summary=f"Forecast snapshot for {date}: {data.get('prediction_count', 0)} predictions",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            data=DataMissing(
                tool_name="get_forecast_snapshot",
                query=f"{experiment_id}:{date}",
                reason=f"Error reading snapshot: {e}",
            ),
            source_category=SourceCategory.META,
            evidence_links=[],
            evidence_refs=[],
            summary=f"Error reading snapshot: {e}",
        )


# =============================================================================
# v1.2: DAILY DIFF TOOL
# =============================================================================

def get_daily_diff_tool(
    experiment_id: str,
    today_date: Optional[str] = None,
    previous_date: Optional[str] = None,
) -> ToolResult:
    """
    Get daily diff showing what changed between two dates.
    
    v1.2 tool for "what changed today?" queries.
    
    Args:
        experiment_id: Experiment ID
        today_date: Current date (defaults to today)
        previous_date: Previous date (defaults to yesterday)
    
    Returns:
        ToolResult with structured diff
    """
    from briefai.ask.diff_tool import get_daily_diff, DiffResult
    from briefai.ask.evidence_anchor import generate_evidence_ref, StableEvidenceRef
    
    # Default to today
    if today_date is None:
        today_date = datetime.now().strftime("%Y-%m-%d")
    
    # Get the diff
    diff_result = get_daily_diff(experiment_id, today_date, previous_date)
    
    # Build evidence refs from diff
    evidence_refs = []
    evidence_links = []
    
    # Meta-signals evidence
    if diff_result.new_signals or diff_result.strengthened:
        meta_path = f"data/meta_signals/meta_signals_{today_date}.json"
        for signal in diff_result.new_signals[:3]:
            ref = StableEvidenceRef(
                artifact_path=meta_path,
                anchor_type=AnchorType.META_ID if hasattr(locals(), 'AnchorType') else "meta_id",
                anchor_value=signal.signal_id,
                as_of_date=today_date,
                relevance_hint=f"New signal: {signal.name}",
            )
            # Convert to EvidenceRef for compatibility
            from briefai.ask.models import EvidenceRef as ModelEvidenceRef
            evidence_refs.append(ModelEvidenceRef(
                artifact_path=meta_path,
                anchor=f"meta_id={signal.signal_id}",
                as_of_date=today_date,
                relevance_hint=f"New signal: {signal.name}",
            ))
            evidence_links.append(EvidenceLink(
                source_type="meta_signal",
                source_id=signal.signal_id,
                category=SourceCategory.META,
                snippet=f"{signal.change_type}: {signal.name}",
            ))
    
    # Predictions evidence
    if diff_result.new_predictions:
        snapshot_path = f"data/public/experiments/{experiment_id}/daily_snapshot_{today_date}.json"
        for pred in diff_result.new_predictions[:3]:
            from briefai.ask.models import EvidenceRef as ModelEvidenceRef
            evidence_refs.append(ModelEvidenceRef(
                artifact_path=snapshot_path,
                anchor=f"prediction_id={pred.prediction_id}",
                as_of_date=today_date,
                relevance_hint=f"New prediction: {pred.entity}/{pred.metric}",
            ))
    
    if not diff_result.total_changes:
        return ToolResult(
            success=True,
            data=diff_result.to_dict(),
            source_category=SourceCategory.META,
            evidence_links=evidence_links,
            evidence_refs=evidence_refs,
            as_of_date=today_date,
            summary=f"No significant changes between {diff_result.previous_date} and {today_date}",
        )
    
    return ToolResult(
        success=True,
        data=diff_result.to_dict(),
        source_category=SourceCategory.META,
        evidence_links=evidence_links,
        evidence_refs=evidence_refs,
        as_of_date=today_date,
        summary=f"Found {diff_result.total_changes} changes: {len(diff_result.new_signals)} new signals, {len(diff_result.strengthened)} strengthened, {len(diff_result.new_predictions)} new predictions",
    )


# =============================================================================
# TOOL REGISTRY
# =============================================================================

@dataclass
class ToolSpec:
    """Specification for a registered tool."""
    name: str
    description: str
    parameters: Dict[str, Dict[str, Any]]  # name -> {type, required, description}
    function: Callable
    category: SourceCategory


class ToolRegistry:
    """
    Central registry of all available tools.
    
    Provides:
    - Tool discovery (list_tools, get_tool)
    - Tool execution with validation
    - Tool documentation for LLM context
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}
        self._register_default_tools()
    
    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        
        self.register(ToolSpec(
            name="search_meta_signals",
            description="Search synthesized meta-signals (high-level trends) for concepts matching a query. Returns trend names, confidence, maturity stage, and supporting signals.",
            parameters={
                "query": {"type": "string", "required": True, "description": "Search query (concept, entity, or keyword)"},
                "date_range": {"type": "tuple[string, string]", "required": False, "description": "Optional (start_date, end_date) in YYYY-MM-DD format"},
            },
            function=search_meta_signals,
            category=SourceCategory.META,
        ))
        
        self.register(ToolSpec(
            name="search_signals",
            description="Search raw signals from various pipelines (news, financial, social, product, papers). Returns individual signal observations.",
            parameters={
                "query": {"type": "string", "required": True, "description": "Search query"},
                "date_range": {"type": "tuple[string, string]", "required": False, "description": "Optional date range"},
                "signal_types": {"type": "list[string]", "required": False, "description": "Signal types to search (news_signals, financial_signals, etc.)"},
            },
            function=search_signals,
            category=SourceCategory.UNKNOWN,
        ))
        
        self.register(ToolSpec(
            name="get_entity_profile",
            description="Get entity profile with signal scores, mention velocity, and cross-source metrics. Use for company/project analysis.",
            parameters={
                "entity": {"type": "string", "required": True, "description": "Entity name (company, project, model)"},
            },
            function=get_entity_profile,
            category=SourceCategory.COMPANY,
        ))
        
        self.register(ToolSpec(
            name="summarize_daily_brief",
            description="Get daily brief summaries (analyst, investor, strategy) for a specific date.",
            parameters={
                "date": {"type": "string", "required": True, "description": "Date in YYYY-MM-DD format"},
            },
            function=summarize_daily_brief,
            category=SourceCategory.MEDIA,
        ))
        
        self.register(ToolSpec(
            name="retrieve_evidence",
            description="Retrieve evidence observations for a specific metric and entity. Use for verifying predictions.",
            parameters={
                "entity": {"type": "string", "required": True, "description": "Entity name"},
                "canonical_metric": {"type": "string", "required": True, "description": "Metric name (article_count, github_stars, etc.)"},
            },
            function=retrieve_evidence,
            category=SourceCategory.UNKNOWN,
        ))
        
        self.register(ToolSpec(
            name="list_hypotheses",
            description="List active hypotheses being tracked for a date.",
            parameters={
                "date": {"type": "string", "required": True, "description": "Date in YYYY-MM-DD format"},
            },
            function=list_hypotheses,
            category=SourceCategory.META,
        ))
        
        self.register(ToolSpec(
            name="get_forecast_snapshot",
            description="Get the frozen forecast snapshot for a specific date and experiment.",
            parameters={
                "date": {"type": "string", "required": True, "description": "Date in YYYY-MM-DD format"},
                "experiment_id": {"type": "string", "required": True, "description": "Experiment ID"},
            },
            function=get_forecast_snapshot,
            category=SourceCategory.META,
        ))
        
        # v1.2: Daily diff tool
        self.register(ToolSpec(
            name="get_daily_diff",
            description="Get daily diff showing what changed between two dates. Use for 'what changed today?' queries. Returns new signals, disappeared signals, strengthened/weakened signals, and prediction changes.",
            parameters={
                "experiment_id": {"type": "string", "required": True, "description": "Experiment ID"},
                "today_date": {"type": "string", "required": False, "description": "Current date (defaults to today)"},
                "previous_date": {"type": "string", "required": False, "description": "Previous date (defaults to yesterday)"},
            },
            function=get_daily_diff_tool,
            category=SourceCategory.META,
        ))
    
    def register(self, spec: ToolSpec) -> None:
        """Register a tool."""
        self._tools[spec.name] = spec
        logger.debug(f"Registered tool: {spec.name}")
    
    def get(self, name: str) -> Optional[ToolSpec]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())
    
    def get_tool_docs(self) -> str:
        """Generate tool documentation for LLM context."""
        docs = ["# Available Tools\n"]
        
        for name, spec in sorted(self._tools.items()):
            docs.append(f"\n## {name}")
            docs.append(f"{spec.description}\n")
            docs.append("Parameters:")
            for param_name, param_info in spec.parameters.items():
                req = "required" if param_info.get("required") else "optional"
                docs.append(f"  - {param_name} ({param_info['type']}, {req}): {param_info.get('description', '')}")
        
        return "\n".join(docs)
    
    def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> ToolResult:
        """
        Execute a tool with validation.
        
        Args:
            tool_name: Name of tool to execute
            arguments: Tool arguments
        
        Returns:
            ToolResult
        """
        spec = self._tools.get(tool_name)
        
        if not spec:
            return ToolResult(
                success=False,
                data=DataMissing(
                    tool_name=tool_name,
                    query=str(arguments),
                    reason=f"Unknown tool: {tool_name}",
                    suggestion=f"Available tools: {', '.join(self.list_tools())}",
                ),
                source_category=SourceCategory.UNKNOWN,
                evidence_links=[],
                summary=f"Error: unknown tool '{tool_name}'",
            )
        
        # Validate required parameters
        for param_name, param_info in spec.parameters.items():
            if param_info.get("required") and param_name not in arguments:
                return ToolResult(
                    success=False,
                    data=DataMissing(
                        tool_name=tool_name,
                        query=str(arguments),
                        reason=f"Missing required parameter: {param_name}",
                    ),
                    source_category=spec.category,
                    evidence_links=[],
                    summary=f"Error: missing parameter '{param_name}'",
                )
        
        # Execute
        try:
            result = spec.function(**arguments)
            if isinstance(result, ToolResult):
                return result
            else:
                # Wrap raw result
                return ToolResult(
                    success=True,
                    data=result,
                    source_category=spec.category,
                    evidence_links=[],
                    summary=f"Tool {tool_name} completed",
                )
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return ToolResult(
                success=False,
                data=DataMissing(
                    tool_name=tool_name,
                    query=str(arguments),
                    reason=f"Execution error: {e}",
                ),
                source_category=spec.category,
                evidence_links=[],
                summary=f"Error: {e}",
            )
