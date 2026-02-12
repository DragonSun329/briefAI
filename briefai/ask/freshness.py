"""
Freshness Banner - Data recency indicator for Ask Mode.

Scans local artifacts to determine the latest available data dates
and generates a freshness banner for answer transparency.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger


def _utc_now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# =============================================================================
# MODELS
# =============================================================================

@dataclass
class ArtifactFreshness:
    """Freshness info for a single artifact type."""
    artifact_type: str
    latest_date: Optional[str] = None
    file_count: int = 0
    sample_files: List[str] = field(default_factory=list)
    
    @property
    def has_data(self) -> bool:
        return self.latest_date is not None


@dataclass
class FreshnessSummary:
    """Overall freshness summary across all artifact types."""
    experiment_id: str
    overall_latest: Optional[str] = None
    artifacts: Dict[str, ArtifactFreshness] = field(default_factory=dict)
    scan_timestamp: str = field(default_factory=_utc_now_iso)
    
    def get_staleness_days(self) -> Optional[int]:
        """Calculate days since latest artifact."""
        if not self.overall_latest:
            return None
        try:
            latest_date = datetime.strptime(self.overall_latest, "%Y-%m-%d")
            today = datetime.now()
            delta = today - latest_date
            return delta.days
        except ValueError:
            return None
    
    def get_staleness_label(self) -> str:
        """Get human-readable staleness status."""
        days = self.get_staleness_days()
        if days is None:
            return "unknown"
        elif days == 0:
            return "fresh (today)"
        elif days == 1:
            return "fresh (yesterday)"
        elif days <= 3:
            return f"recent ({days} days)"
        else:
            return f"⚠️ stale ({days} days old)"
    
    def to_banner(self) -> str:
        """Generate the freshness banner string with staleness warning."""
        latest = self.overall_latest or "no data"
        staleness = self.get_staleness_label()
        
        lines = [
            "📌 Data scope: local briefAI artifacts only",
            f"Latest available: {latest}",
            f"Experiment: {self.experiment_id}",
            f"Staleness: {staleness}",
        ]
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict:
        return {
            "experiment_id": self.experiment_id,
            "overall_latest": self.overall_latest,
            "artifacts": {k: {
                "artifact_type": v.artifact_type,
                "latest_date": v.latest_date,
                "file_count": v.file_count,
            } for k, v in self.artifacts.items()},
            "scan_timestamp": self.scan_timestamp,
        }


# =============================================================================
# PATH HELPERS
# =============================================================================

def get_data_path() -> Path:
    """Get the briefAI data directory."""
    return Path(__file__).parent.parent.parent / "data"


def get_experiment_path(experiment_id: str) -> Path:
    """Get experiment-specific path."""
    return get_data_path() / "public" / "experiments" / experiment_id


# =============================================================================
# DATE EXTRACTION
# =============================================================================

DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


def extract_date_from_filename(filename: str) -> Optional[str]:
    """Extract YYYY-MM-DD date from filename."""
    match = DATE_PATTERN.search(filename)
    return match.group(1) if match else None


def find_latest_date(dates: List[str]) -> Optional[str]:
    """Find the latest date from a list of date strings."""
    valid_dates = [d for d in dates if d]
    return max(valid_dates) if valid_dates else None


# =============================================================================
# ARTIFACT SCANNERS
# =============================================================================

def scan_reports(data_path: Path) -> ArtifactFreshness:
    """Scan data/reports/ for daily briefs."""
    reports_dir = data_path / "reports"
    result = ArtifactFreshness(artifact_type="daily_brief")
    
    if not reports_dir.exists():
        # Also check data/briefs/ as alternative location
        reports_dir = data_path / "briefs"
    
    if not reports_dir.exists():
        return result
    
    dates = []
    files = []
    
    for pattern in ["daily_brief_*.md", "analyst_brief_*.md", "investor_brief_*.md", "strategy_brief_*.md"]:
        for file_path in reports_dir.glob(pattern):
            date = extract_date_from_filename(file_path.name)
            if date:
                dates.append(date)
                files.append(file_path.name)
    
    result.latest_date = find_latest_date(dates)
    result.file_count = len(files)
    result.sample_files = sorted(files)[-3:]  # Last 3
    
    return result


def scan_experiment_snapshots(experiment_path: Path) -> ArtifactFreshness:
    """Scan experiment folder for daily snapshots."""
    result = ArtifactFreshness(artifact_type="daily_snapshot")
    
    if not experiment_path.exists():
        return result
    
    dates = []
    files = []
    
    for file_path in experiment_path.glob("daily_snapshot_*.json"):
        date = extract_date_from_filename(file_path.name)
        if date:
            dates.append(date)
            files.append(file_path.name)
    
    result.latest_date = find_latest_date(dates)
    result.file_count = len(files)
    result.sample_files = sorted(files)[-3:]
    
    return result


def scan_run_metadata(experiment_path: Path) -> ArtifactFreshness:
    """Scan experiment folder for run metadata."""
    result = ArtifactFreshness(artifact_type="run_metadata")
    
    if not experiment_path.exists():
        return result
    
    dates = []
    files = []
    
    for file_path in experiment_path.glob("run_metadata_*.json"):
        date = extract_date_from_filename(file_path.name)
        if date:
            dates.append(date)
            files.append(file_path.name)
    
    result.latest_date = find_latest_date(dates)
    result.file_count = len(files)
    result.sample_files = sorted(files)[-3:]
    
    return result


def scan_meta_signals(data_path: Path) -> ArtifactFreshness:
    """Scan data/meta_signals/ for meta-signal files."""
    meta_dir = data_path / "meta_signals"
    result = ArtifactFreshness(artifact_type="meta_signals")
    
    if not meta_dir.exists():
        return result
    
    dates = []
    files = []
    
    for file_path in meta_dir.glob("meta_signals_*.json"):
        date = extract_date_from_filename(file_path.name)
        if date:
            dates.append(date)
            files.append(file_path.name)
    
    result.latest_date = find_latest_date(dates)
    result.file_count = len(files)
    result.sample_files = sorted(files)[-3:]
    
    return result


def scan_news_signals(data_path: Path) -> ArtifactFreshness:
    """Scan data/news_signals/ for news signal files."""
    news_dir = data_path / "news_signals"
    result = ArtifactFreshness(artifact_type="news_signals")
    
    if not news_dir.exists():
        return result
    
    dates = []
    files = []
    
    for file_path in news_dir.glob("*.json"):
        date = extract_date_from_filename(file_path.name)
        if date:
            dates.append(date)
            files.append(file_path.name)
    
    result.latest_date = find_latest_date(dates)
    result.file_count = len(files)
    result.sample_files = sorted(files)[-3:]
    
    return result


# =============================================================================
# MAIN API
# =============================================================================

def get_latest_artifact_dates(experiment_id: str) -> FreshnessSummary:
    """
    Scan all artifact locations and return freshness summary.
    
    Scans:
    - data/reports/ or data/briefs/ (daily briefs)
    - data/public/experiments/{experiment_id}/ (snapshots, metadata)
    - data/meta_signals/ (meta-signals)
    - data/news_signals/ (news signals)
    
    Args:
        experiment_id: Experiment identifier
    
    Returns:
        FreshnessSummary with latest dates per artifact type
    """
    data_path = get_data_path()
    experiment_path = get_experiment_path(experiment_id)
    
    summary = FreshnessSummary(experiment_id=experiment_id)
    
    # Scan all artifact types
    summary.artifacts["daily_brief"] = scan_reports(data_path)
    summary.artifacts["daily_snapshot"] = scan_experiment_snapshots(experiment_path)
    summary.artifacts["run_metadata"] = scan_run_metadata(experiment_path)
    summary.artifacts["meta_signals"] = scan_meta_signals(data_path)
    summary.artifacts["news_signals"] = scan_news_signals(data_path)
    
    # Calculate overall latest
    all_dates = [
        artifact.latest_date
        for artifact in summary.artifacts.values()
        if artifact.latest_date
    ]
    summary.overall_latest = find_latest_date(all_dates)
    
    logger.debug(f"Freshness scan: {summary.to_dict()}")
    
    return summary


def generate_freshness_banner(experiment_id: str) -> str:
    """
    Generate a freshness banner for the given experiment.
    
    Returns a single-line banner suitable for prepending to answers.
    """
    summary = get_latest_artifact_dates(experiment_id)
    return summary.to_banner()


# =============================================================================
# TOOL INTEGRATION
# =============================================================================

def get_artifact_as_of_date(artifact_path: Path) -> Optional[str]:
    """
    Extract as-of date from an artifact path.
    
    Used by tools to annotate results with their data freshness.
    """
    return extract_date_from_filename(artifact_path.name)
