"""
Lead Time Tracker v1.0 - Measure Signal Earliness.

This proves the competitive advantage.

signal_lead_time = date_of_prediction - date_of_mainstream_news

If you can consistently show 7-21 days early detection,
you have something a VC, fund, or corporate strategy team will pay for.

Example:
    Enterprise adoption trend detected: Jan 18
    Major news coverage: Feb 3
    Lead time: 16 days
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"

# Keywords that indicate mainstream coverage
MAINSTREAM_KEYWORDS = [
    "announces", "announced", "reports", "reported",
    "confirms", "confirmed", "launches", "launched",
    "revenue", "earnings", "guidance", "forecast",
]


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class LeadTimeRecord:
    """Record of lead time for a prediction."""
    
    prediction_id: str
    hypothesis_id: str
    hypothesis_title: str
    concept_name: str
    
    # Dates
    prediction_date: str
    first_signal_date: str
    mainstream_coverage_date: Optional[str]
    
    # Lead time
    lead_time_days: Optional[int]
    
    # Evidence
    prediction_summary: str
    mainstream_headline: Optional[str]
    mainstream_source: Optional[str]
    
    # Status
    status: str = "pending"  # pending, confirmed, unconfirmed
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'LeadTimeRecord':
        return cls(**d)
    
    @property
    def has_lead_time(self) -> bool:
        return self.lead_time_days is not None
    
    @property
    def is_early(self) -> bool:
        """True if lead time is 7+ days."""
        return self.lead_time_days is not None and self.lead_time_days >= 7


@dataclass 
class LeadTimeSummary:
    """Summary of lead time performance."""
    
    generated_at: str
    period_days: int
    
    # Counts
    total_predictions: int
    confirmed_lead_times: int
    pending_confirmation: int
    
    # Lead time stats
    avg_lead_time_days: Optional[float]
    median_lead_time_days: Optional[float]
    max_lead_time_days: Optional[int]
    min_lead_time_days: Optional[int]
    
    # Distribution
    early_detections: int  # 7+ days
    moderate_detections: int  # 3-6 days
    late_detections: int  # 0-2 days
    
    # Best examples
    best_examples: List[LeadTimeRecord]
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["best_examples"] = [e.to_dict() for e in self.best_examples]
        return d
    
    def format_markdown(self) -> str:
        """Format summary as markdown."""
        lines = []
        
        lines.append("## Signal Lead Time")
        lines.append("")
        lines.append(f"*Measuring how early we detect trends vs mainstream coverage*")
        lines.append("")
        
        if self.confirmed_lead_times == 0:
            lines.append("*No lead time data available yet.*")
            lines.append("")
            return "\n".join(lines)
        
        # Summary stats
        lines.append("### Performance")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Confirmed Lead Times | {self.confirmed_lead_times} |")
        
        if self.avg_lead_time_days is not None:
            lines.append(f"| **Average Lead Time** | **{self.avg_lead_time_days:.1f} days** |")
        if self.median_lead_time_days is not None:
            lines.append(f"| Median Lead Time | {self.median_lead_time_days:.1f} days |")
        if self.max_lead_time_days is not None:
            lines.append(f"| Best Lead Time | {self.max_lead_time_days} days |")
        
        lines.append("")
        
        # Distribution
        if self.confirmed_lead_times > 0:
            lines.append("### Detection Timing")
            lines.append("")
            lines.append(f"- Early (7+ days): {self.early_detections}")
            lines.append(f"- Moderate (3-6 days): {self.moderate_detections}")
            lines.append(f"- Late (0-2 days): {self.late_detections}")
            lines.append("")
        
        # Best examples
        if self.best_examples:
            lines.append("### Best Examples")
            lines.append("")
            
            for example in self.best_examples[:5]:
                lines.append(f"**{example.hypothesis_title}**")
                lines.append(f"- Detected: {example.prediction_date}")
                if example.mainstream_coverage_date:
                    lines.append(f"- Mainstream: {example.mainstream_coverage_date}")
                lines.append(f"- **Lead Time: {example.lead_time_days} days**")
                if example.mainstream_headline:
                    lines.append(f"- Headline: *\"{example.mainstream_headline}\"*")
                lines.append("")
        
        return "\n".join(lines)


# =============================================================================
# LEAD TIME STORE
# =============================================================================

class LeadTimeStore:
    """Stores and manages lead time records."""
    
    def __init__(self, data_dir: Path = None):
        """Initialize store."""
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir) / "metrics"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.records_file = self.data_dir / "lead_time_records.jsonl"
    
    def save_record(self, record: LeadTimeRecord):
        """Append a record."""
        with open(self.records_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record.to_dict()) + '\n')
    
    def load_records(self) -> List[LeadTimeRecord]:
        """Load all records."""
        if not self.records_file.exists():
            return []
        
        records = []
        with open(self.records_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(LeadTimeRecord.from_dict(json.loads(line)))
                    except Exception:
                        pass
        
        return records
    
    def update_record(self, prediction_id: str, **updates):
        """Update a record by prediction_id."""
        records = self.load_records()
        
        updated = False
        for record in records:
            if record.prediction_id == prediction_id:
                for key, value in updates.items():
                    if hasattr(record, key):
                        setattr(record, key, value)
                updated = True
                break
        
        if updated:
            # Rewrite file
            with open(self.records_file, 'w', encoding='utf-8') as f:
                for record in records:
                    f.write(json.dumps(record.to_dict()) + '\n')
        
        return updated


# =============================================================================
# LEAD TIME TRACKER
# =============================================================================

class LeadTimeTracker:
    """
    Tracks and measures lead time for predictions.
    
    Lead time = prediction date - mainstream coverage date
    """
    
    def __init__(self, data_dir: Path = None):
        """Initialize tracker."""
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.store = LeadTimeStore(data_dir)
    
    def register_prediction(
        self,
        prediction_id: str,
        hypothesis_id: str,
        hypothesis_title: str,
        concept_name: str,
        prediction_date: str,
        prediction_summary: str,
    ) -> LeadTimeRecord:
        """
        Register a new prediction for lead time tracking.
        
        Args:
            prediction_id: ID of the prediction
            hypothesis_id: ID of the hypothesis
            hypothesis_title: Title of the hypothesis
            concept_name: Name of the concept
            prediction_date: When prediction was made
            prediction_summary: Summary of what was predicted
        
        Returns:
            LeadTimeRecord
        """
        record = LeadTimeRecord(
            prediction_id=prediction_id,
            hypothesis_id=hypothesis_id,
            hypothesis_title=hypothesis_title,
            concept_name=concept_name,
            prediction_date=prediction_date,
            first_signal_date=prediction_date,
            mainstream_coverage_date=None,
            lead_time_days=None,
            prediction_summary=prediction_summary,
            mainstream_headline=None,
            mainstream_source=None,
            status="pending",
        )
        
        self.store.save_record(record)
        
        return record
    
    def confirm_mainstream_coverage(
        self,
        prediction_id: str,
        coverage_date: str,
        headline: str,
        source: str,
    ) -> Optional[int]:
        """
        Confirm mainstream coverage and calculate lead time.
        
        Args:
            prediction_id: ID of the prediction
            coverage_date: When mainstream covered it
            headline: Headline of the coverage
            source: Source of the coverage
        
        Returns:
            Lead time in days, or None if not found
        """
        records = self.store.load_records()
        
        for record in records:
            if record.prediction_id == prediction_id:
                # Calculate lead time
                pred_date = datetime.strptime(record.prediction_date[:10], "%Y-%m-%d")
                cov_date = datetime.strptime(coverage_date[:10], "%Y-%m-%d")
                
                lead_time = (cov_date - pred_date).days
                
                # Update record
                self.store.update_record(
                    prediction_id,
                    mainstream_coverage_date=coverage_date,
                    mainstream_headline=headline,
                    mainstream_source=source,
                    lead_time_days=lead_time,
                    status="confirmed",
                )
                
                logger.info(
                    f"Confirmed lead time for {prediction_id}: {lead_time} days"
                )
                
                return lead_time
        
        return None
    
    def generate_summary(self, period_days: int = 90) -> LeadTimeSummary:
        """
        Generate lead time summary.
        
        Args:
            period_days: Period to analyze
        
        Returns:
            LeadTimeSummary
        """
        records = self.store.load_records()
        
        # Filter to confirmed records with lead time
        confirmed = [r for r in records if r.status == "confirmed" and r.lead_time_days is not None]
        pending = [r for r in records if r.status == "pending"]
        
        if not confirmed:
            return LeadTimeSummary(
                generated_at=datetime.now().isoformat(),
                period_days=period_days,
                total_predictions=len(records),
                confirmed_lead_times=0,
                pending_confirmation=len(pending),
                avg_lead_time_days=None,
                median_lead_time_days=None,
                max_lead_time_days=None,
                min_lead_time_days=None,
                early_detections=0,
                moderate_detections=0,
                late_detections=0,
                best_examples=[],
            )
        
        # Calculate stats
        lead_times = [r.lead_time_days for r in confirmed]
        lead_times_sorted = sorted(lead_times)
        
        avg_lt = sum(lead_times) / len(lead_times)
        median_lt = lead_times_sorted[len(lead_times_sorted) // 2]
        
        # Distribution
        early = sum(1 for lt in lead_times if lt >= 7)
        moderate = sum(1 for lt in lead_times if 3 <= lt < 7)
        late = sum(1 for lt in lead_times if lt < 3)
        
        # Best examples (highest lead time)
        best = sorted(confirmed, key=lambda r: r.lead_time_days or 0, reverse=True)[:5]
        
        return LeadTimeSummary(
            generated_at=datetime.now().isoformat(),
            period_days=period_days,
            total_predictions=len(records),
            confirmed_lead_times=len(confirmed),
            pending_confirmation=len(pending),
            avg_lead_time_days=round(avg_lt, 1),
            median_lead_time_days=round(median_lt, 1),
            max_lead_time_days=max(lead_times),
            min_lead_time_days=min(lead_times),
            early_detections=early,
            moderate_detections=moderate,
            late_detections=late,
            best_examples=best,
        )
    
    def auto_detect_coverage(
        self,
        news_articles: List[Dict],
        prediction_id: str = None,
    ) -> List[Tuple[str, str, str]]:
        """
        Automatically detect mainstream coverage from news articles.
        
        Args:
            news_articles: List of news article dicts
            prediction_id: Optional specific prediction to match
        
        Returns:
            List of (prediction_id, coverage_date, headline) matches
        """
        records = self.store.load_records()
        
        if prediction_id:
            records = [r for r in records if r.prediction_id == prediction_id]
        
        # Filter to pending
        pending = [r for r in records if r.status == "pending"]
        
        matches = []
        
        for record in pending:
            # Build keywords from prediction summary
            keywords = self._extract_keywords(record.prediction_summary)
            keywords.extend(self._extract_keywords(record.concept_name))
            
            for article in news_articles:
                headline = article.get("title", "").lower()
                content = article.get("content", "").lower()
                
                # Check for keyword matches
                match_count = sum(1 for kw in keywords if kw in headline or kw in content)
                
                if match_count >= 2:
                    matches.append((
                        record.prediction_id,
                        article.get("date", ""),
                        article.get("title", ""),
                    ))
                    break
        
        return matches
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        if not text:
            return []
        
        # Simple keyword extraction
        words = text.lower().split()
        
        # Filter out common words
        stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "is", "are", "was", "were"}
        
        return [w for w in words if len(w) > 3 and w not in stopwords]


# =============================================================================
# BRIEF SECTION GENERATOR
# =============================================================================

def generate_lead_time_section(summary: Optional[LeadTimeSummary]) -> str:
    """Generate the Lead Time section for the analyst brief."""
    if summary is None:
        lines = []
        lines.append("## Signal Lead Time")
        lines.append("")
        lines.append("*No lead time data available yet.*")
        lines.append("")
        return "\n".join(lines)
    
    return summary.format_markdown()


# =============================================================================
# TESTS
# =============================================================================

def _test_lead_time_calculation():
    """Test lead time calculation."""
    record = LeadTimeRecord(
        prediction_id="pred_001",
        hypothesis_id="hyp_001",
        hypothesis_title="Infrastructure Scaling",
        concept_name="NVIDIA Demand",
        prediction_date="2026-01-18",
        first_signal_date="2026-01-18",
        mainstream_coverage_date="2026-02-03",
        lead_time_days=16,
        prediction_summary="NVIDIA infrastructure demand increasing",
        mainstream_headline="NVIDIA Reports Record Datacenter Revenue",
        mainstream_source="Reuters",
        status="confirmed",
    )
    
    assert record.lead_time_days == 16
    assert record.is_early == True
    assert record.has_lead_time == True
    
    print("[PASS] _test_lead_time_calculation")


def _test_summary_generation():
    """Test summary generation."""
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = LeadTimeTracker(Path(tmpdir))
        
        # Register predictions
        tracker.register_prediction(
            prediction_id="pred_001",
            hypothesis_id="hyp_001",
            hypothesis_title="Enterprise AI Adoption",
            concept_name="AI Adoption",
            prediction_date="2026-01-10",
            prediction_summary="Enterprise AI adoption accelerating",
        )
        
        # Confirm coverage
        tracker.confirm_mainstream_coverage(
            prediction_id="pred_001",
            coverage_date="2026-01-25",
            headline="Fortune 500 AI Spending Surges",
            source="Bloomberg",
        )
        
        # Generate summary
        summary = tracker.generate_summary()
        
        assert summary.confirmed_lead_times == 1
        assert summary.avg_lead_time_days == 15
        assert len(summary.best_examples) == 1
        
        print("[PASS] _test_summary_generation")


def run_tests():
    """Run all tests."""
    print("\n=== LEAD TIME TRACKER TESTS ===\n")
    
    _test_lead_time_calculation()
    _test_summary_generation()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
