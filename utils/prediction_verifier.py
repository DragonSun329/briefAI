"""
Prediction Verification Engine (PVE) - Core Data Model & Evaluation Logic.

Part of briefAI Gravity Engine v2.8: Evidence-Based Belief Updates.

This module:
1. Stores predictions from hypothesis engine
2. Tracks prediction lifecycle
3. Evaluates predictions against observed data
4. Produces verdicts (verified_true, verified_false, inconclusive, data_missing)
5. Generates graded evidence for belief updates (v1.0)

Pipeline:
    Hypothesis Created → Observation Window Opens → Data Collected → 
    Outcome Evaluation → Prediction Verdict + Evidence → Belief Update

No LLM calls. Fully deterministic evaluation.
"""

import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_PREDICTIONS_DIR = Path(__file__).parent.parent / "data" / "predictions"
DEFAULT_RECORDS_FILE = "prediction_records.jsonl"

# Experiment-aware mode
EXPERIMENT_AWARE = True  # Set to True to use experiment-isolated storage

# Direction evaluation thresholds
THRESHOLD_SIGNIFICANT_CHANGE = 0.15  # 15% change for verified_true/false
THRESHOLD_FLAT = 0.10                # 10% for flat direction
THRESHOLD_INCONCLUSIVE = 0.05        # 5% minimum for any verdict


# =============================================================================
# ENUMS
# =============================================================================

class PredictionStatus(str, Enum):
    """Prediction lifecycle status."""
    PENDING = "pending"
    EVALUATED = "evaluated"
    EXPIRED = "expired"


class PredictionVerdict(str, Enum):
    """Prediction outcome verdict."""
    VERIFIED_TRUE = "verified_true"
    VERIFIED_FALSE = "verified_false"
    INCONCLUSIVE = "inconclusive"
    DATA_MISSING = "data_missing"
    PENDING = "pending"


class ExpectedDirection(str, Enum):
    """Expected direction for metric change."""
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PredictionRecord:
    """
    A single prediction record for tracking and evaluation.
    
    Lifecycle:
    1. Created when hypothesis generated (status=pending, verdict=pending)
    2. Evaluated when window expires (status=evaluated, verdict=<result>)
    """
    # Identity
    prediction_id: str                       # Stable hash
    hypothesis_id: str                       # Parent hypothesis
    meta_id: str                             # Parent meta-signal
    
    # Prediction details
    entity: str                              # Primary entity (e.g., "nvidia")
    canonical_metric: str                    # Metric being tracked
    expected_direction: str                  # "up", "down", "flat"
    category: str                            # technical/financial/media/etc.
    description: str                         # Human-readable prediction
    
    # Timing
    window_days: int                         # Observation window
    created_at: str                          # ISO timestamp
    evaluation_due: str                      # ISO timestamp when to evaluate
    evaluated_at: Optional[str] = None       # ISO timestamp when evaluated
    
    # Status
    status: str = PredictionStatus.PENDING.value
    verdict: str = PredictionVerdict.PENDING.value
    
    # Observed data (populated at evaluation)
    observed_value_start: Optional[float] = None    # Baseline value
    observed_value_end: Optional[float] = None      # Current value
    percent_change: Optional[float] = None          # Calculated change
    
    # Confidence tracking
    confidence_at_prediction: float = 0.5           # Hypothesis confidence
    mechanism: str = ""                             # Mechanism that generated this
    
    # Calibration
    calibration_error: Optional[float] = None       # |confidence - actual|
    
    # Query trace (for debugging)
    observable_query: Dict[str, Any] = field(default_factory=dict)
    query_terms: Dict[str, Any] = field(default_factory=dict)
    
    # Experiment metadata (for isolation)
    experiment_id: Optional[str] = None     # e.g., "v2_1_forward_test"
    engine_version: Optional[str] = None    # e.g., "ENGINE_v2.1_DAY0"
    commit_hash: Optional[str] = None       # Git commit hash
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'PredictionRecord':
        """Deserialize from dict."""
        return cls(**d)
    
    def to_jsonl(self) -> str:
        """Serialize to JSONL line."""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_jsonl(cls, line: str) -> 'PredictionRecord':
        """Deserialize from JSONL line."""
        return cls.from_dict(json.loads(line))
    
    def is_due(self, now: datetime = None) -> bool:
        """Check if prediction is due for evaluation."""
        if now is None:
            now = datetime.now()
        due = datetime.fromisoformat(self.evaluation_due)
        return now >= due and self.status == PredictionStatus.PENDING.value


# =============================================================================
# PREDICTION ID GENERATION
# =============================================================================

def generate_prediction_id(
    hypothesis_id: str,
    entity: str,
    canonical_metric: str,
    category: str,
    created_at: str,
) -> str:
    """
    Generate stable prediction ID from key components.
    
    Args:
        hypothesis_id: Parent hypothesis ID
        entity: Primary entity
        canonical_metric: Metric being tracked
        category: Prediction category
        created_at: Creation timestamp
    
    Returns:
        16-char hex hash
    """
    source = f"{hypothesis_id}|{entity}|{canonical_metric}|{category}|{created_at}"
    return hashlib.sha256(source.encode()).hexdigest()[:16]


# =============================================================================
# PREDICTION EVALUATION
# =============================================================================

def calculate_percent_change(start: float, end: float) -> Optional[float]:
    """
    Calculate percent change between two values.
    
    Args:
        start: Baseline value
        end: Current value
    
    Returns:
        Percent change as decimal (0.15 = 15%), or None if start is 0
    """
    if start == 0:
        if end > 0:
            return 1.0  # 100% increase from zero
        return None
    return (end - start) / abs(start)


def evaluate_direction(
    expected: str,
    percent_change: float,
) -> str:
    """
    Evaluate prediction verdict based on expected direction and observed change.
    
    Args:
        expected: Expected direction ("up", "down", "flat")
        percent_change: Observed percent change
    
    Returns:
        PredictionVerdict value
    """
    # Normalize expected direction
    expected_lower = expected.lower()
    
    # Check for significant change
    if expected_lower in ['up', 'increase']:
        if percent_change >= THRESHOLD_SIGNIFICANT_CHANGE:
            return PredictionVerdict.VERIFIED_TRUE.value
        elif percent_change <= -THRESHOLD_SIGNIFICANT_CHANGE:
            return PredictionVerdict.VERIFIED_FALSE.value
        elif abs(percent_change) < THRESHOLD_INCONCLUSIVE:
            return PredictionVerdict.INCONCLUSIVE.value
        else:
            return PredictionVerdict.INCONCLUSIVE.value
    
    elif expected_lower in ['down', 'decrease']:
        if percent_change <= -THRESHOLD_SIGNIFICANT_CHANGE:
            return PredictionVerdict.VERIFIED_TRUE.value
        elif percent_change >= THRESHOLD_SIGNIFICANT_CHANGE:
            return PredictionVerdict.VERIFIED_FALSE.value
        elif abs(percent_change) < THRESHOLD_INCONCLUSIVE:
            return PredictionVerdict.INCONCLUSIVE.value
        else:
            return PredictionVerdict.INCONCLUSIVE.value
    
    elif expected_lower == 'flat':
        if abs(percent_change) < THRESHOLD_FLAT:
            return PredictionVerdict.VERIFIED_TRUE.value
        else:
            return PredictionVerdict.VERIFIED_FALSE.value
    
    # Unknown direction
    return PredictionVerdict.INCONCLUSIVE.value


def evaluate_prediction(
    record: PredictionRecord,
    observed_start: Optional[float],
    observed_end: Optional[float],
) -> PredictionRecord:
    """
    Evaluate a prediction record against observed data.
    
    Args:
        record: The prediction record to evaluate
        observed_start: Baseline metric value at prediction creation
        observed_end: Current metric value at evaluation time
    
    Returns:
        Updated PredictionRecord with verdict and observation data
    """
    now = datetime.now()
    
    # Update evaluation timestamp
    record.evaluated_at = now.isoformat()
    record.status = PredictionStatus.EVALUATED.value
    
    # Handle missing data
    if observed_start is None or observed_end is None:
        record.verdict = PredictionVerdict.DATA_MISSING.value
        record.observed_value_start = observed_start
        record.observed_value_end = observed_end
        record.percent_change = None
        record.calibration_error = None
        logger.warning(f"Data missing for prediction {record.prediction_id}")
        return record
    
    # Calculate percent change
    percent_change = calculate_percent_change(observed_start, observed_end)
    
    if percent_change is None:
        record.verdict = PredictionVerdict.DATA_MISSING.value
        record.observed_value_start = observed_start
        record.observed_value_end = observed_end
        record.percent_change = None
        record.calibration_error = None
        return record
    
    # Store observations
    record.observed_value_start = observed_start
    record.observed_value_end = observed_end
    record.percent_change = round(percent_change, 4)
    
    # Determine verdict
    record.verdict = evaluate_direction(record.expected_direction, percent_change)
    
    # Calculate calibration error
    # For verified_true, actual = 1.0; for verified_false, actual = 0.0
    if record.verdict == PredictionVerdict.VERIFIED_TRUE.value:
        actual = 1.0
    elif record.verdict == PredictionVerdict.VERIFIED_FALSE.value:
        actual = 0.0
    else:
        actual = 0.5  # Inconclusive
    
    record.calibration_error = round(abs(record.confidence_at_prediction - actual), 4)
    
    logger.info(
        f"Evaluated prediction {record.prediction_id}: "
        f"{record.verdict} ({record.percent_change:.1%} change)"
    )
    
    return record


def evaluate_prediction_with_evidence(
    record: PredictionRecord,
    observed_start: Optional[float],
    observed_end: Optional[float],
) -> Tuple['PredictionRecord', 'Any']:
    """
    Evaluate a prediction and generate evidence for belief updates.
    
    This is the v1.0 Evidence Engine integration point.
    Returns both the evaluated record AND an EvidenceResult.
    
    Args:
        record: The prediction record to evaluate
        observed_start: Baseline metric value
        observed_end: Current metric value
    
    Returns:
        Tuple of (evaluated PredictionRecord, EvidenceResult)
    """
    # First, do standard evaluation
    evaluated_record = evaluate_prediction(record, observed_start, observed_end)
    
    # Then generate evidence
    try:
        from utils.evidence_engine import EvidenceGenerator
        
        generator = EvidenceGenerator()
        evidence = generator.generate_from_prediction_record(
            record=record.to_dict(),
            baseline=observed_start,
            current=observed_end,
        )
        
        return evaluated_record, evidence
        
    except ImportError:
        # Evidence engine not available, return None
        logger.debug("Evidence engine not available")
        return evaluated_record, None
    except Exception as e:
        logger.warning(f"Failed to generate evidence: {e}")
        return evaluated_record, None


# =============================================================================
# PREDICTION STORE
# =============================================================================

class PredictionStore:
    """
    Persistent store for prediction records.
    
    Uses JSONL format for append-friendly storage.
    Supports experiment-aware storage isolation.
    """
    
    def __init__(self, data_dir: Path = None, experiment_id: str = None):
        """
        Initialize prediction store.
        
        Args:
            data_dir: Override data directory
            experiment_id: Optional experiment ID for isolated storage
        """
        self.experiment_id = experiment_id
        self.experiment_context = None
        
        # Try to use experiment-aware storage
        if EXPERIMENT_AWARE and data_dir is None:
            try:
                from utils.experiment_manager import (
                    get_experiment_context,
                    get_ledger_path,
                )
                self.experiment_context = get_experiment_context(experiment_id)
                # Store predictions alongside the forecast ledger
                ledger_path = get_ledger_path(experiment_id)
                data_dir = ledger_path / "predictions"
                self.experiment_id = self.experiment_context.experiment.experiment_id
            except Exception as e:
                logger.debug(f"Experiment manager not available, using default: {e}")
        
        if data_dir is None:
            data_dir = DEFAULT_PREDICTIONS_DIR
        
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.records_file = self.data_dir / DEFAULT_RECORDS_FILE
        
        logger.debug(f"PredictionStore initialized at {self.data_dir}")
    
    def save_record(self, record: PredictionRecord) -> None:
        """Append a single record to the store."""
        # Add experiment metadata if available
        if self.experiment_context:
            record.experiment_id = self.experiment_id
            record.engine_version = self.experiment_context.experiment.engine_tag
            record.commit_hash = self.experiment_context.commit_hash
        
        with open(self.records_file, 'a', encoding='utf-8') as f:
            f.write(record.to_jsonl() + '\n')
        logger.debug(f"Saved prediction {record.prediction_id}")
    
    def save_records(self, records: List[PredictionRecord]) -> None:
        """Append multiple records to the store."""
        with open(self.records_file, 'a', encoding='utf-8') as f:
            for record in records:
                f.write(record.to_jsonl() + '\n')
        logger.debug(f"Saved {len(records)} predictions")
    
    def load_all_records(self) -> List[PredictionRecord]:
        """Load all records from the store."""
        if not self.records_file.exists():
            return []
        
        records = []
        with open(self.records_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(PredictionRecord.from_jsonl(line))
                    except Exception as e:
                        logger.warning(f"Failed to parse record: {e}")
        
        return records
    
    def load_pending_records(self) -> List[PredictionRecord]:
        """Load only pending records."""
        all_records = self.load_all_records()
        return [r for r in all_records if r.status == PredictionStatus.PENDING.value]
    
    def load_due_records(self, now: datetime = None) -> List[PredictionRecord]:
        """Load records that are due for evaluation."""
        if now is None:
            now = datetime.now()
        
        pending = self.load_pending_records()
        return [r for r in pending if r.is_due(now)]
    
    def update_record(self, record: PredictionRecord) -> None:
        """
        Update a record in the store.
        
        This rewrites the entire file (not efficient for large files,
        but simple and correct for our use case).
        """
        all_records = self.load_all_records()
        
        # Find and replace
        updated = False
        for i, r in enumerate(all_records):
            if r.prediction_id == record.prediction_id:
                all_records[i] = record
                updated = True
                break
        
        if not updated:
            all_records.append(record)
        
        # Rewrite file
        with open(self.records_file, 'w', encoding='utf-8') as f:
            for r in all_records:
                f.write(r.to_jsonl() + '\n')
        
        logger.debug(f"Updated prediction {record.prediction_id}")
    
    def get_records_by_hypothesis(self, hypothesis_id: str) -> List[PredictionRecord]:
        """Get all records for a specific hypothesis."""
        all_records = self.load_all_records()
        return [r for r in all_records if r.hypothesis_id == hypothesis_id]
    
    def get_records_by_meta(self, meta_id: str) -> List[PredictionRecord]:
        """Get all records for a specific meta-signal."""
        all_records = self.load_all_records()
        return [r for r in all_records if r.meta_id == meta_id]
    
    def get_evaluated_records(self) -> List[PredictionRecord]:
        """Get all evaluated records."""
        all_records = self.load_all_records()
        return [r for r in all_records if r.status == PredictionStatus.EVALUATED.value]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get summary statistics for the store."""
        all_records = self.load_all_records()
        
        if not all_records:
            return {
                'total': 0,
                'pending': 0,
                'evaluated': 0,
                'verdicts': {},
            }
        
        pending = sum(1 for r in all_records if r.status == PredictionStatus.PENDING.value)
        evaluated = sum(1 for r in all_records if r.status == PredictionStatus.EVALUATED.value)
        
        verdicts = {}
        for r in all_records:
            verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
        
        return {
            'total': len(all_records),
            'pending': pending,
            'evaluated': evaluated,
            'verdicts': verdicts,
        }


# =============================================================================
# PREDICTION REGISTRATION
# =============================================================================

def create_prediction_from_signal(
    predicted_signal: Dict[str, Any],
    hypothesis: Dict[str, Any],
    meta_id: str,
) -> PredictionRecord:
    """
    Create a PredictionRecord from a PredictedSignal.
    
    Args:
        predicted_signal: Dict from hypothesis.predicted_next_signals
        hypothesis: Parent hypothesis dict
        meta_id: Parent meta-signal ID
    
    Returns:
        PredictionRecord ready for storage
    """
    now = datetime.now()
    
    # Extract observable query details
    obs_query = predicted_signal.get('observable_query', {})
    query_terms = obs_query.get('query_terms', {})
    
    # Get primary entity from query terms or fallback
    entity = query_terms.get('primary_entity', '')
    if not entity:
        entity = query_terms.get('concept_entity', '')
    if not entity:
        entities = query_terms.get('entities', [])
        entity = entities[0] if entities else 'unknown'
    
    # Calculate evaluation due date
    window_days = predicted_signal.get('expected_timeframe_days', 14)
    evaluation_due = now + timedelta(days=window_days)
    
    # Get expected direction
    expected_direction = obs_query.get('expected_direction', 'up')
    if not expected_direction:
        expected_direction = predicted_signal.get('direction', 'up')
    
    # Generate prediction ID
    created_at = now.isoformat()
    prediction_id = generate_prediction_id(
        hypothesis_id=hypothesis.get('hypothesis_id', ''),
        entity=entity,
        canonical_metric=predicted_signal.get('canonical_metric', 'unknown'),
        category=predicted_signal.get('category', 'unknown'),
        created_at=created_at,
    )
    
    return PredictionRecord(
        prediction_id=prediction_id,
        hypothesis_id=hypothesis.get('hypothesis_id', ''),
        meta_id=meta_id,
        entity=entity,
        canonical_metric=predicted_signal.get('canonical_metric', 'unknown'),
        expected_direction=expected_direction,
        category=predicted_signal.get('category', 'unknown'),
        description=predicted_signal.get('description', ''),
        window_days=window_days,
        created_at=created_at,
        evaluation_due=evaluation_due.isoformat(),
        confidence_at_prediction=hypothesis.get('confidence', 0.5),
        mechanism=hypothesis.get('mechanism', ''),
        observable_query=obs_query,
        query_terms=query_terms,
    )


def register_predictions_from_bundle(
    bundle: Dict[str, Any],
    store: PredictionStore = None,
) -> List[PredictionRecord]:
    """
    Register all predictions from a hypothesis bundle.
    
    Args:
        bundle: MetaHypothesisBundle dict
        store: PredictionStore instance (creates default if None)
    
    Returns:
        List of created PredictionRecord objects
    """
    if store is None:
        store = PredictionStore()
    
    records = []
    meta_id = bundle.get('meta_id', '')
    
    for hypothesis in bundle.get('hypotheses', []):
        for signal in hypothesis.get('predicted_next_signals', []):
            # Only register measurable predictions
            if not signal.get('measurable', True):
                continue
            
            record = create_prediction_from_signal(
                predicted_signal=signal,
                hypothesis=hypothesis,
                meta_id=meta_id,
            )
            records.append(record)
    
    if records:
        store.save_records(records)
        logger.info(f"Registered {len(records)} predictions from bundle {meta_id}")
    
    return records


# =============================================================================
# CLI HELPERS
# =============================================================================

def print_prediction_summary(record: PredictionRecord) -> None:
    """Print a human-readable prediction summary."""
    verdict_emoji = {
        PredictionVerdict.VERIFIED_TRUE.value: "[TRUE]",
        PredictionVerdict.VERIFIED_FALSE.value: "[FALSE]",
        PredictionVerdict.INCONCLUSIVE.value: "[?]",
        PredictionVerdict.DATA_MISSING.value: "[NO DATA]",
        PredictionVerdict.PENDING.value: "[PENDING]",
    }
    
    emoji = verdict_emoji.get(record.verdict, "[?]")
    
    change_str = ""
    if record.percent_change is not None:
        sign = "+" if record.percent_change >= 0 else ""
        change_str = f" ({sign}{record.percent_change:.1%})"
    
    print(f"{emoji} {record.description[:60]}...{change_str}")
    print(f"    Entity: {record.entity} | Metric: {record.canonical_metric}")
    print(f"    Window: {record.window_days}d | Confidence: {record.confidence_at_prediction:.0%}")


# =============================================================================
# TESTS
# =============================================================================

def _test_evaluate_direction():
    """Test direction evaluation logic."""
    # Up direction tests
    assert evaluate_direction('up', 0.20) == PredictionVerdict.VERIFIED_TRUE.value
    assert evaluate_direction('up', -0.20) == PredictionVerdict.VERIFIED_FALSE.value
    assert evaluate_direction('up', 0.10) == PredictionVerdict.INCONCLUSIVE.value
    
    # Down direction tests
    assert evaluate_direction('down', -0.20) == PredictionVerdict.VERIFIED_TRUE.value
    assert evaluate_direction('down', 0.20) == PredictionVerdict.VERIFIED_FALSE.value
    assert evaluate_direction('down', -0.05) == PredictionVerdict.INCONCLUSIVE.value
    
    # Flat direction tests
    assert evaluate_direction('flat', 0.05) == PredictionVerdict.VERIFIED_TRUE.value
    assert evaluate_direction('flat', 0.20) == PredictionVerdict.VERIFIED_FALSE.value
    
    print("[PASS] _test_evaluate_direction")


def _test_percent_change():
    """Test percent change calculation."""
    assert calculate_percent_change(100, 115) == 0.15
    assert calculate_percent_change(100, 85) == -0.15
    assert calculate_percent_change(100, 100) == 0.0
    assert calculate_percent_change(0, 10) == 1.0
    assert calculate_percent_change(0, 0) is None
    
    print("[PASS] _test_percent_change")


def _test_prediction_id():
    """Test prediction ID generation."""
    id1 = generate_prediction_id("hyp1", "nvidia", "article_count", "media", "2026-02-10")
    id2 = generate_prediction_id("hyp1", "nvidia", "article_count", "media", "2026-02-10")
    id3 = generate_prediction_id("hyp2", "nvidia", "article_count", "media", "2026-02-10")
    
    assert id1 == id2  # Same inputs = same ID
    assert id1 != id3  # Different hypothesis = different ID
    assert len(id1) == 16
    
    print("[PASS] _test_prediction_id")


def run_tests():
    """Run all verifier tests."""
    print("\n=== PREDICTION VERIFIER TESTS ===\n")
    
    _test_evaluate_direction()
    _test_percent_change()
    _test_prediction_id()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
