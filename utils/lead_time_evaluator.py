"""
Lead-Time Evaluator - Measure Prediction Earliness.

Part of briefAI Validation & Public Credibility Layer.

After predictions are evaluated by prediction_verifier, compute:
    lead_time = date_of_real_world_event - date_prediction_generated

Aggregate metrics:
- Average lead time
- Median lead time
- % of predictions confirmed before media coverage

Output:
    data/metrics/lead_time_report.json
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median, mean

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
LEAD_TIME_REPORT_FILE = "lead_time_report.json"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class LeadTimeEntry:
    """Lead time measurement for a single prediction."""
    
    hypothesis_id: str
    prediction_id: str
    
    # Event identification
    event_detected: str
    concept_name: str
    mechanism: str
    
    # Dates
    prediction_date: str
    confirmation_date: str
    
    # Lead time
    lead_time_days: int
    
    # Context
    predicted_signal: str
    actual_outcome: str
    confidence_at_prediction: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'LeadTimeEntry':
        return cls(**d)


@dataclass
class LeadTimeReport:
    """Aggregate lead time report."""
    
    generated_at: str
    period_start: str
    period_end: str
    
    # Sample size
    total_evaluated: int
    with_lead_time: int
    
    # Aggregate metrics
    average_lead_time_days: Optional[float]
    median_lead_time_days: Optional[float]
    min_lead_time_days: Optional[int]
    max_lead_time_days: Optional[int]
    
    # Distribution
    lead_time_7_plus_days: int
    lead_time_14_plus_days: int
    lead_time_21_plus_days: int
    
    # Percentage confirmed before media
    pct_early_detection: float
    
    # By mechanism
    by_mechanism: Dict[str, Dict[str, Any]]
    
    # Individual entries
    entries: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def format_markdown(self) -> str:
        """Format report as markdown."""
        lines = []
        
        lines.append("## Lead Time Report")
        lines.append("")
        lines.append(f"*Generated: {self.generated_at}*")
        lines.append(f"*Period: {self.period_start} to {self.period_end}*")
        lines.append("")
        
        # Summary
        lines.append("### Summary")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Predictions Evaluated | {self.total_evaluated} |")
        lines.append(f"| With Lead Time Data | {self.with_lead_time} |")
        
        if self.average_lead_time_days is not None:
            lines.append(f"| **Average Lead Time** | **{self.average_lead_time_days:.1f} days** |")
            lines.append(f"| Median Lead Time | {self.median_lead_time_days:.1f} days |")
            lines.append(f"| Best Lead Time | {self.max_lead_time_days} days |")
        
        lines.append(f"| Early Detection Rate | {self.pct_early_detection:.0%} |")
        lines.append("")
        
        # Distribution
        if self.with_lead_time > 0:
            lines.append("### Lead Time Distribution")
            lines.append("")
            lines.append(f"- 7+ days: {self.lead_time_7_plus_days} ({self.lead_time_7_plus_days/self.with_lead_time:.0%})")
            lines.append(f"- 14+ days: {self.lead_time_14_plus_days} ({self.lead_time_14_plus_days/self.with_lead_time:.0%})")
            lines.append(f"- 21+ days: {self.lead_time_21_plus_days} ({self.lead_time_21_plus_days/self.with_lead_time:.0%})")
            lines.append("")
        
        # By mechanism
        if self.by_mechanism:
            lines.append("### By Mechanism")
            lines.append("")
            lines.append("| Mechanism | Avg Lead Time | Count |")
            lines.append("|-----------|--------------|-------|")
            
            for mechanism, data in sorted(
                self.by_mechanism.items(),
                key=lambda x: x[1].get("avg_lead_time", 0),
                reverse=True,
            ):
                avg = data.get("avg_lead_time", 0)
                count = data.get("count", 0)
                lines.append(f"| {mechanism} | {avg:.1f} days | {count} |")
            
            lines.append("")
        
        return "\n".join(lines)


# =============================================================================
# LEAD TIME EVALUATOR
# =============================================================================

class LeadTimeEvaluator:
    """
    Evaluates lead time for verified predictions.
    
    Lead time = confirmation_date - prediction_date
    """
    
    def __init__(self, data_dir: Path = None):
        """
        Initialize evaluator.
        
        Args:
            data_dir: Base data directory
        """
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.metrics_dir = self.data_dir / "metrics"
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        
        self.report_file = self.metrics_dir / LEAD_TIME_REPORT_FILE
    
    def compute_lead_times(
        self,
        predictions: List[Dict[str, Any]],
    ) -> List[LeadTimeEntry]:
        """
        Compute lead times for evaluated predictions.
        
        Args:
            predictions: List of evaluated prediction records
        
        Returns:
            List of LeadTimeEntry objects
        """
        entries = []
        
        for pred in predictions:
            # Only process verified predictions
            if pred.get("verdict") not in ["verified_true", "verified_false"]:
                continue
            
            # Get dates
            created_at = pred.get("created_at", "")
            evaluated_at = pred.get("evaluated_at", "")
            
            if not created_at or not evaluated_at:
                continue
            
            try:
                # Parse dates
                pred_date = datetime.fromisoformat(created_at.split("T")[0])
                conf_date = datetime.fromisoformat(evaluated_at.split("T")[0])
                
                # Calculate lead time
                lead_time = (conf_date - pred_date).days
                
                # Only positive lead times make sense
                if lead_time < 0:
                    continue
                
                entry = LeadTimeEntry(
                    hypothesis_id=pred.get("hypothesis_id", ""),
                    prediction_id=pred.get("prediction_id", ""),
                    event_detected=pred.get("description", ""),
                    concept_name=pred.get("concept_name", ""),
                    mechanism=pred.get("mechanism", "unknown"),
                    prediction_date=created_at[:10],
                    confirmation_date=evaluated_at[:10],
                    lead_time_days=lead_time,
                    predicted_signal=pred.get("canonical_metric", ""),
                    actual_outcome=pred.get("verdict", ""),
                    confidence_at_prediction=pred.get("confidence_at_prediction", 0.5),
                )
                
                entries.append(entry)
                
            except Exception as e:
                logger.warning(f"Failed to compute lead time for {pred.get('prediction_id')}: {e}")
        
        return entries
    
    def generate_report(
        self,
        predictions: List[Dict[str, Any]],
        period_start: str = None,
        period_end: str = None,
    ) -> LeadTimeReport:
        """
        Generate comprehensive lead time report.
        
        Args:
            predictions: List of evaluated prediction records
            period_start: Start of period (optional)
            period_end: End of period (optional)
        
        Returns:
            LeadTimeReport
        """
        # Compute lead times
        entries = self.compute_lead_times(predictions)
        
        # Get dates
        if period_start is None and entries:
            period_start = min(e.prediction_date for e in entries)
        if period_end is None and entries:
            period_end = max(e.confirmation_date for e in entries)
        
        period_start = period_start or datetime.now().strftime("%Y-%m-%d")
        period_end = period_end or datetime.now().strftime("%Y-%m-%d")
        
        # Calculate aggregates
        lead_times = [e.lead_time_days for e in entries]
        
        if lead_times:
            avg_lt = round(mean(lead_times), 1)
            med_lt = round(median(lead_times), 1)
            min_lt = min(lead_times)
            max_lt = max(lead_times)
        else:
            avg_lt = None
            med_lt = None
            min_lt = None
            max_lt = None
        
        # Distribution
        lt_7_plus = sum(1 for lt in lead_times if lt >= 7)
        lt_14_plus = sum(1 for lt in lead_times if lt >= 14)
        lt_21_plus = sum(1 for lt in lead_times if lt >= 21)
        
        # Early detection rate (7+ days)
        pct_early = lt_7_plus / len(entries) if entries else 0.0
        
        # By mechanism
        by_mechanism = {}
        mechanism_entries: Dict[str, List[int]] = {}
        
        for entry in entries:
            mech = entry.mechanism
            if mech not in mechanism_entries:
                mechanism_entries[mech] = []
            mechanism_entries[mech].append(entry.lead_time_days)
        
        for mech, lts in mechanism_entries.items():
            by_mechanism[mech] = {
                "avg_lead_time": round(mean(lts), 1),
                "median_lead_time": round(median(lts), 1),
                "count": len(lts),
            }
        
        report = LeadTimeReport(
            generated_at=datetime.now().isoformat(),
            period_start=period_start,
            period_end=period_end,
            total_evaluated=len(predictions),
            with_lead_time=len(entries),
            average_lead_time_days=avg_lt,
            median_lead_time_days=med_lt,
            min_lead_time_days=min_lt,
            max_lead_time_days=max_lt,
            lead_time_7_plus_days=lt_7_plus,
            lead_time_14_plus_days=lt_14_plus,
            lead_time_21_plus_days=lt_21_plus,
            pct_early_detection=round(pct_early, 4),
            by_mechanism=by_mechanism,
            entries=[e.to_dict() for e in entries],
        )
        
        return report
    
    def save_report(self, report: LeadTimeReport) -> Path:
        """Save report to file."""
        with open(self.report_file, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved lead time report to {self.report_file}")
        return self.report_file
    
    def load_report(self) -> Optional[LeadTimeReport]:
        """Load existing report."""
        if not self.report_file.exists():
            return None
        
        try:
            with open(self.report_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Reconstruct entries as dicts (not dataclass)
            return LeadTimeReport(
                generated_at=data["generated_at"],
                period_start=data["period_start"],
                period_end=data["period_end"],
                total_evaluated=data["total_evaluated"],
                with_lead_time=data["with_lead_time"],
                average_lead_time_days=data.get("average_lead_time_days"),
                median_lead_time_days=data.get("median_lead_time_days"),
                min_lead_time_days=data.get("min_lead_time_days"),
                max_lead_time_days=data.get("max_lead_time_days"),
                lead_time_7_plus_days=data["lead_time_7_plus_days"],
                lead_time_14_plus_days=data["lead_time_14_plus_days"],
                lead_time_21_plus_days=data["lead_time_21_plus_days"],
                pct_early_detection=data["pct_early_detection"],
                by_mechanism=data["by_mechanism"],
                entries=data["entries"],
            )
        except Exception as e:
            logger.warning(f"Failed to load lead time report: {e}")
            return None
    
    def evaluate_from_store(self) -> LeadTimeReport:
        """
        Evaluate lead times from the prediction store.
        
        Returns:
            LeadTimeReport
        """
        predictions_file = self.data_dir / "predictions" / "prediction_records.jsonl"
        
        if not predictions_file.exists():
            logger.warning("No prediction records found")
            return self.generate_report([])
        
        # Load predictions
        predictions = []
        with open(predictions_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        predictions.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        
        # Filter to evaluated only
        evaluated = [p for p in predictions if p.get("status") == "evaluated"]
        
        return self.generate_report(evaluated)


# =============================================================================
# TESTS
# =============================================================================

def _test_lead_time_computation():
    """Test lead time computation."""
    evaluator = LeadTimeEvaluator()
    
    predictions = [
        {
            "prediction_id": "pred_001",
            "hypothesis_id": "hyp_001",
            "created_at": "2026-01-10T10:00:00",
            "evaluated_at": "2026-01-25T10:00:00",
            "verdict": "verified_true",
            "mechanism": "infra_scaling",
        },
        {
            "prediction_id": "pred_002",
            "hypothesis_id": "hyp_002",
            "created_at": "2026-01-15T10:00:00",
            "evaluated_at": "2026-01-22T10:00:00",
            "verdict": "verified_true",
            "mechanism": "enterprise_adoption",
        },
    ]
    
    entries = evaluator.compute_lead_times(predictions)
    
    assert len(entries) == 2
    assert entries[0].lead_time_days == 15
    assert entries[1].lead_time_days == 7
    
    print("[PASS] _test_lead_time_computation")


def _test_report_generation():
    """Test report generation."""
    evaluator = LeadTimeEvaluator()
    
    predictions = [
        {
            "prediction_id": "pred_001",
            "hypothesis_id": "hyp_001",
            "created_at": "2026-01-01",
            "evaluated_at": "2026-01-16",
            "verdict": "verified_true",
            "mechanism": "infra_scaling",
        },
        {
            "prediction_id": "pred_002",
            "hypothesis_id": "hyp_002",
            "created_at": "2026-01-05",
            "evaluated_at": "2026-01-10",
            "verdict": "verified_true",
            "mechanism": "enterprise_adoption",
        },
        {
            "prediction_id": "pred_003",
            "hypothesis_id": "hyp_003",
            "created_at": "2026-01-10",
            "evaluated_at": "2026-02-01",
            "verdict": "verified_true",
            "mechanism": "infra_scaling",
        },
    ]
    
    report = evaluator.generate_report(predictions)
    
    assert report.with_lead_time == 3
    assert report.average_lead_time_days is not None
    assert report.lead_time_7_plus_days >= 2
    
    print("[PASS] _test_report_generation")


def run_tests():
    """Run all tests."""
    print("\n=== LEAD TIME EVALUATOR TESTS ===\n")
    
    _test_lead_time_computation()
    _test_report_generation()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
