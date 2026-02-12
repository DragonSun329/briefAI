"""
Daily Diff Tool for Ask Mode v1.2.

Compares artifacts between two dates to answer "What changed today?"

Compares:
A) meta_signals
B) daily_brief top narratives
C) active predictions

Returns structured diff result.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger


# =============================================================================
# DIFF RESULT TYPES
# =============================================================================

@dataclass
class SignalChange:
    """A changed signal."""
    signal_id: str
    name: str
    change_type: str  # "new", "disappeared", "strengthened", "weakened"
    previous_value: Optional[float] = None
    current_value: Optional[float] = None
    delta: Optional[float] = None
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict:
        return {
            "signal_id": self.signal_id,
            "name": self.name,
            "change_type": self.change_type,
            "previous_value": self.previous_value,
            "current_value": self.current_value,
            "delta": self.delta,
            "details": self.details,
        }


@dataclass
class PredictionChange:
    """A changed prediction."""
    prediction_id: str
    entity: str
    metric: str
    change_type: str  # "new", "resolved", "updated"
    previous_status: Optional[str] = None
    current_status: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict:
        return {
            "prediction_id": self.prediction_id,
            "entity": self.entity,
            "metric": self.metric,
            "change_type": self.change_type,
            "previous_status": self.previous_status,
            "current_status": self.current_status,
            "details": self.details,
        }


@dataclass
class DiffResult:
    """Complete diff result between two dates."""
    today_date: str
    previous_date: str
    experiment_id: str
    
    # Meta-signal changes
    new_signals: List[SignalChange] = field(default_factory=list)
    disappeared_signals: List[SignalChange] = field(default_factory=list)
    strengthened: List[SignalChange] = field(default_factory=list)
    weakened: List[SignalChange] = field(default_factory=list)
    
    # Prediction changes
    new_predictions: List[PredictionChange] = field(default_factory=list)
    resolved_predictions: List[PredictionChange] = field(default_factory=list)
    
    # Narrative changes (from briefs)
    new_narratives: List[str] = field(default_factory=list)
    dropped_narratives: List[str] = field(default_factory=list)
    
    # Summary stats
    total_changes: int = 0
    
    def __post_init__(self):
        self._update_total()
    
    def _update_total(self):
        self.total_changes = (
            len(self.new_signals) +
            len(self.disappeared_signals) +
            len(self.strengthened) +
            len(self.weakened) +
            len(self.new_predictions) +
            len(self.resolved_predictions) +
            len(self.new_narratives) +
            len(self.dropped_narratives)
        )
    
    def to_dict(self) -> Dict:
        return {
            "today_date": self.today_date,
            "previous_date": self.previous_date,
            "experiment_id": self.experiment_id,
            "new_signals": [s.to_dict() for s in self.new_signals],
            "disappeared_signals": [s.to_dict() for s in self.disappeared_signals],
            "strengthened": [s.to_dict() for s in self.strengthened],
            "weakened": [s.to_dict() for s in self.weakened],
            "new_predictions": [p.to_dict() for p in self.new_predictions],
            "resolved_predictions": [p.to_dict() for p in self.resolved_predictions],
            "new_narratives": self.new_narratives,
            "dropped_narratives": self.dropped_narratives,
            "total_changes": self.total_changes,
        }
    
    def to_summary(self) -> str:
        """Generate a human-readable summary."""
        lines = [
            f"## Daily Diff: {self.previous_date} → {self.today_date}",
            "",
        ]
        
        if self.new_signals:
            lines.append(f"**{len(self.new_signals)} new signals emerged**")
            for s in self.new_signals[:3]:
                lines.append(f"  - {s.name}")
            if len(self.new_signals) > 3:
                lines.append(f"  - ... and {len(self.new_signals) - 3} more")
            lines.append("")
        
        if self.disappeared_signals:
            lines.append(f"**{len(self.disappeared_signals)} signals disappeared**")
            for s in self.disappeared_signals[:3]:
                lines.append(f"  - {s.name}")
            lines.append("")
        
        if self.strengthened:
            lines.append(f"**{len(self.strengthened)} signals strengthened**")
            for s in self.strengthened[:3]:
                delta = f" (+{s.delta:.2f})" if s.delta else ""
                lines.append(f"  - {s.name}{delta}")
            lines.append("")
        
        if self.weakened:
            lines.append(f"**{len(self.weakened)} signals weakened**")
            for s in self.weakened[:3]:
                delta = f" ({s.delta:.2f})" if s.delta else ""
                lines.append(f"  - {s.name}{delta}")
            lines.append("")
        
        if self.new_predictions:
            lines.append(f"**{len(self.new_predictions)} new predictions**")
            for p in self.new_predictions[:3]:
                lines.append(f"  - {p.entity}: {p.metric}")
            lines.append("")
        
        if self.resolved_predictions:
            lines.append(f"**{len(self.resolved_predictions)} predictions resolved**")
            for p in self.resolved_predictions[:3]:
                lines.append(f"  - {p.entity}: {p.metric} ({p.current_status})")
            lines.append("")
        
        if not self.total_changes:
            lines.append("*No significant changes detected.*")
        
        return "\n".join(lines)


# =============================================================================
# PATH HELPERS
# =============================================================================

def get_data_path() -> Path:
    """Get briefAI data directory."""
    return Path(__file__).parent.parent.parent / "data"


def get_experiment_path(experiment_id: str) -> Path:
    """Get experiment-specific path."""
    return get_data_path() / "public" / "experiments" / experiment_id


# =============================================================================
# DIFF FUNCTIONS
# =============================================================================

def load_meta_signals(date: str) -> Dict[str, Dict]:
    """Load meta-signals for a date, keyed by meta_id."""
    meta_file = get_data_path() / "meta_signals" / f"meta_signals_{date}.json"
    
    if not meta_file.exists():
        return {}
    
    try:
        with open(meta_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        signals = {}
        for signal in data.get("meta_signals", []):
            meta_id = signal.get("meta_id", "")
            if meta_id:
                signals[meta_id] = signal
        
        return signals
    except Exception as e:
        logger.debug(f"Error loading meta_signals for {date}: {e}")
        return {}


def diff_meta_signals(
    today_signals: Dict[str, Dict],
    previous_signals: Dict[str, Dict],
) -> Tuple[List[SignalChange], List[SignalChange], List[SignalChange], List[SignalChange]]:
    """
    Compare meta-signals between two dates.
    
    Returns: (new, disappeared, strengthened, weakened)
    """
    new_signals = []
    disappeared_signals = []
    strengthened = []
    weakened = []
    
    today_ids = set(today_signals.keys())
    prev_ids = set(previous_signals.keys())
    
    # New signals
    for meta_id in today_ids - prev_ids:
        signal = today_signals[meta_id]
        new_signals.append(SignalChange(
            signal_id=meta_id,
            name=signal.get("concept_name", "Unknown"),
            change_type="new",
            current_value=signal.get("concept_confidence"),
            details={"maturity": signal.get("maturity_stage")},
        ))
    
    # Disappeared signals
    for meta_id in prev_ids - today_ids:
        signal = previous_signals[meta_id]
        disappeared_signals.append(SignalChange(
            signal_id=meta_id,
            name=signal.get("concept_name", "Unknown"),
            change_type="disappeared",
            previous_value=signal.get("concept_confidence"),
        ))
    
    # Changed signals (in both)
    for meta_id in today_ids & prev_ids:
        today = today_signals[meta_id]
        prev = previous_signals[meta_id]
        
        today_conf = today.get("concept_confidence", 0) or 0
        prev_conf = prev.get("concept_confidence", 0) or 0
        
        delta = today_conf - prev_conf
        
        # Significant change threshold: 0.05 (5%)
        if delta > 0.05:
            strengthened.append(SignalChange(
                signal_id=meta_id,
                name=today.get("concept_name", "Unknown"),
                change_type="strengthened",
                previous_value=prev_conf,
                current_value=today_conf,
                delta=delta,
            ))
        elif delta < -0.05:
            weakened.append(SignalChange(
                signal_id=meta_id,
                name=today.get("concept_name", "Unknown"),
                change_type="weakened",
                previous_value=prev_conf,
                current_value=today_conf,
                delta=delta,
            ))
    
    return new_signals, disappeared_signals, strengthened, weakened


def load_predictions(experiment_id: str, date: str) -> Dict[str, Dict]:
    """Load predictions from daily snapshot, keyed by a composite id."""
    snapshot_file = get_experiment_path(experiment_id) / f"daily_snapshot_{date}.json"
    
    if not snapshot_file.exists():
        return {}
    
    try:
        with open(snapshot_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        predictions = {}
        for pred in data.get("predictions", []):
            # Create composite ID from hypothesis + metric
            pred_id = f"{pred.get('hypothesis_id', '')}:{pred.get('canonical_metric', '')}"
            predictions[pred_id] = pred
        
        return predictions
    except Exception as e:
        logger.debug(f"Error loading predictions for {date}: {e}")
        return {}


def diff_predictions(
    today_preds: Dict[str, Dict],
    previous_preds: Dict[str, Dict],
) -> Tuple[List[PredictionChange], List[PredictionChange]]:
    """
    Compare predictions between two dates.
    
    Returns: (new_predictions, resolved_predictions)
    """
    new_predictions = []
    resolved_predictions = []
    
    today_ids = set(today_preds.keys())
    prev_ids = set(previous_preds.keys())
    
    # New predictions
    for pred_id in today_ids - prev_ids:
        pred = today_preds[pred_id]
        new_predictions.append(PredictionChange(
            prediction_id=pred_id,
            entity=pred.get("concept_name", "Unknown"),
            metric=pred.get("canonical_metric", "unknown"),
            change_type="new",
            current_status="active",
            details={
                "direction": pred.get("expected_direction"),
                "confidence": pred.get("confidence"),
            },
        ))
    
    # Resolved (disappeared) predictions
    for pred_id in prev_ids - today_ids:
        pred = previous_preds[pred_id]
        resolved_predictions.append(PredictionChange(
            prediction_id=pred_id,
            entity=pred.get("concept_name", "Unknown"),
            metric=pred.get("canonical_metric", "unknown"),
            change_type="resolved",
            previous_status="active",
            current_status="resolved",
        ))
    
    return new_predictions, resolved_predictions


def extract_brief_narratives(date: str) -> List[str]:
    """Extract top narratives from daily brief."""
    briefs_dir = get_data_path() / "briefs"
    
    for brief_type in ["analyst_brief", "investor_brief", "strategy_brief"]:
        brief_file = briefs_dir / f"{brief_type}_{date}.md"
        if brief_file.exists():
            try:
                content = brief_file.read_text(encoding='utf-8')
                
                # Extract bullet points from top sections
                narratives = []
                
                # Find key sections
                sections = re.findall(
                    r"##\s+(?:Key|Top|Main|Summary)[^\n]*\n(.*?)(?=\n##|\Z)",
                    content,
                    re.IGNORECASE | re.DOTALL
                )
                
                for section in sections:
                    bullets = re.findall(r"[-•*]\s*(.+?)(?=\n[-•*]|\n\n|\Z)", section)
                    narratives.extend([b.strip()[:100] for b in bullets[:5]])
                
                return narratives[:10]  # Limit to 10
            except Exception as e:
                logger.debug(f"Error extracting narratives: {e}")
    
    return []


def diff_narratives(
    today_narratives: List[str],
    previous_narratives: List[str],
) -> Tuple[List[str], List[str]]:
    """
    Compare narratives between two dates using fuzzy matching.
    
    Returns: (new_narratives, dropped_narratives)
    """
    # Simple string containment check
    # A narrative is "same" if >50% words overlap
    
    def get_words(text: str) -> Set[str]:
        return set(re.findall(r'\w+', text.lower()))
    
    def similar(t1: str, t2: str) -> bool:
        w1, w2 = get_words(t1), get_words(t2)
        if not w1 or not w2:
            return False
        overlap = len(w1 & w2) / max(len(w1), len(w2))
        return overlap > 0.5
    
    new_narratives = []
    dropped_narratives = []
    
    # Find new narratives
    for today in today_narratives:
        is_new = not any(similar(today, prev) for prev in previous_narratives)
        if is_new:
            new_narratives.append(today)
    
    # Find dropped narratives
    for prev in previous_narratives:
        is_dropped = not any(similar(prev, today) for today in today_narratives)
        if is_dropped:
            dropped_narratives.append(prev)
    
    return new_narratives, dropped_narratives


# =============================================================================
# MAIN API
# =============================================================================

def get_daily_diff(
    experiment_id: str,
    today_date: str,
    previous_date: Optional[str] = None,
) -> DiffResult:
    """
    Get comprehensive diff between two dates.
    
    Args:
        experiment_id: Experiment ID
        today_date: Current date (YYYY-MM-DD)
        previous_date: Previous date to compare (defaults to yesterday)
    
    Returns:
        DiffResult with all changes
    """
    # Default to yesterday
    if previous_date is None:
        today = datetime.strptime(today_date, "%Y-%m-%d")
        yesterday = today - timedelta(days=1)
        previous_date = yesterday.strftime("%Y-%m-%d")
    
    result = DiffResult(
        today_date=today_date,
        previous_date=previous_date,
        experiment_id=experiment_id,
    )
    
    # Diff meta-signals
    today_signals = load_meta_signals(today_date)
    prev_signals = load_meta_signals(previous_date)
    
    (
        result.new_signals,
        result.disappeared_signals,
        result.strengthened,
        result.weakened,
    ) = diff_meta_signals(today_signals, prev_signals)
    
    # Diff predictions
    today_preds = load_predictions(experiment_id, today_date)
    prev_preds = load_predictions(experiment_id, previous_date)
    
    (
        result.new_predictions,
        result.resolved_predictions,
    ) = diff_predictions(today_preds, prev_preds)
    
    # Diff narratives
    today_narratives = extract_brief_narratives(today_date)
    prev_narratives = extract_brief_narratives(previous_date)
    
    (
        result.new_narratives,
        result.dropped_narratives,
    ) = diff_narratives(today_narratives, prev_narratives)
    
    # Update total
    result._update_total()
    
    logger.debug(f"Daily diff {previous_date}→{today_date}: {result.total_changes} changes")
    
    return result


def get_previous_date(reference_date: str, days_back: int = 1) -> str:
    """Get a date N days before reference date."""
    ref = datetime.strptime(reference_date, "%Y-%m-%d")
    prev = ref - timedelta(days=days_back)
    return prev.strftime("%Y-%m-%d")
