"""
Evidence Engine v1.0 - Graded Evidence from Prediction Observations.

Part of briefAI Gravity Engine v2.8: Evidence-Based Belief Updates.

This module converts binary prediction verdicts into graded evidence
that accumulates over time to update hypothesis beliefs.

Key Concepts:
- Evidence Direction: SUPPORT, CONTRADICT, NEUTRAL, DATA_MISSING
- Evidence Score: -1.0 to +1.0 graded support/contradiction
- Effect Size: Normalized magnitude of observed change
- Weight: Importance of metric × source reliability

Evidence accumulates across observations to update posterior confidence.

No LLM calls. Deterministic scoring.
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from enum import Enum

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "evidence_weights.json"

# Default thresholds
DEFAULT_SIGNIFICANT_CHANGE = 0.15
DEFAULT_SATURATION_POINT = 0.30


# =============================================================================
# ENUMS
# =============================================================================

class EvidenceDirection(Enum):
    """Direction of evidence relative to hypothesis."""
    SUPPORT = "support"
    CONTRADICT = "contradict"
    NEUTRAL = "neutral"
    DATA_MISSING = "data_missing"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class EvidenceResult:
    """
    Evidence produced from evaluating a single prediction.
    
    Represents graded support/contradiction for a hypothesis
    based on observed metric changes.
    """
    # Links
    prediction_id: str
    hypothesis_id: str
    meta_id: str
    
    # What was measured
    entity: str
    canonical_metric: str
    category: str
    expected_direction: str
    
    # Evidence assessment
    direction: str  # EvidenceDirection value
    evidence_score: float  # -1.0 to +1.0
    effect_size: float  # Normalized magnitude
    weight: float  # Importance of this evidence
    
    # Raw observations
    baseline_value: Optional[float] = None
    current_value: Optional[float] = None
    percent_change: Optional[float] = None
    
    # Metadata
    observed_at: str = ""
    notes: str = ""
    
    def __post_init__(self):
        if not self.observed_at:
            self.observed_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'EvidenceResult':
        return cls(**d)
    
    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_jsonl(cls, line: str) -> 'EvidenceResult':
        return cls.from_dict(json.loads(line))
    
    @property
    def weighted_score(self) -> float:
        """Evidence score weighted by importance."""
        return self.evidence_score * self.weight
    
    @property
    def is_informative(self) -> bool:
        """True if evidence provides signal (not neutral/missing)."""
        return self.direction in [
            EvidenceDirection.SUPPORT.value,
            EvidenceDirection.CONTRADICT.value,
        ]


# =============================================================================
# EVIDENCE WEIGHTS
# =============================================================================

class EvidenceWeights:
    """
    Loads and provides evidence weights from configuration.
    
    Weights determine how strongly each metric type and source
    influences belief updates.
    """
    
    def __init__(self, config_path: Path = None):
        """Initialize with config file."""
        if config_path is None:
            config_path = DEFAULT_CONFIG_PATH
        
        self.config_path = Path(config_path)
        self._load_config()
    
    def _load_config(self):
        """Load weights from config file."""
        if not self.config_path.exists():
            logger.warning(f"Evidence weights not found: {self.config_path}")
            self._set_defaults()
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            self.metric_weights = config.get('canonical_metric_weights', {})
            self.source_reliability = config.get('source_reliability', {})
            self.thresholds = config.get('direction_thresholds', {})
            self.update_params = config.get('update_parameters', {})
            self.safety_caps = config.get('safety_caps', {})
            
            logger.debug(f"Loaded evidence weights from {self.config_path}")
            
        except Exception as e:
            logger.warning(f"Failed to load evidence weights: {e}")
            self._set_defaults()
    
    def _set_defaults(self):
        """Set default weights if config unavailable."""
        self.metric_weights = {}
        self.source_reliability = {}
        self.thresholds = {
            'significant_change': DEFAULT_SIGNIFICANT_CHANGE,
            'saturation_point': DEFAULT_SATURATION_POINT,
        }
        self.update_params = {
            'learning_rate': 0.35,
            'min_confidence': 0.05,
            'max_confidence': 0.98,
        }
        self.safety_caps = {
            'review_required': 0.60,
            'weakly_validated': 0.75,
            'default': 0.95,
        }
    
    def get_metric_weight(self, metric: str) -> float:
        """Get weight for a canonical metric."""
        # Remove leading underscore from doc fields
        weights = {k: v for k, v in self.metric_weights.items() if not k.startswith('_')}
        return weights.get(metric, 0.50)  # Default to medium weight
    
    def get_source_reliability(self, source: str) -> float:
        """Get reliability multiplier for a source."""
        reliability = {k: v for k, v in self.source_reliability.items() if not k.startswith('_')}
        return reliability.get(source, 0.50)  # Default to medium reliability
    
    def get_combined_weight(self, metric: str, source: str = None) -> float:
        """
        Get combined weight for a metric observation.
        
        Combined weight = metric_weight × source_reliability
        """
        metric_weight = self.get_metric_weight(metric)
        
        if source:
            source_reliability = self.get_source_reliability(source)
            return metric_weight * source_reliability
        
        return metric_weight
    
    @property
    def significant_change_threshold(self) -> float:
        return self.thresholds.get('significant_change', DEFAULT_SIGNIFICANT_CHANGE)
    
    @property
    def saturation_point(self) -> float:
        return self.thresholds.get('saturation_point', DEFAULT_SATURATION_POINT)
    
    @property
    def learning_rate(self) -> float:
        return self.update_params.get('learning_rate', 0.35)
    
    def get_safety_cap(self, quality: str) -> float:
        """Get maximum confidence cap for hypothesis quality."""
        return self.safety_caps.get(quality, self.safety_caps.get('default', 0.95))


# =============================================================================
# EVIDENCE SCORING
# =============================================================================

def calculate_evidence_direction(
    expected_direction: str,
    percent_change: float,
    threshold: float = DEFAULT_SIGNIFICANT_CHANGE,
) -> EvidenceDirection:
    """
    Determine evidence direction based on expected vs actual change.
    
    Args:
        expected_direction: 'up', 'down', or 'flat'
        percent_change: Observed change as decimal (0.15 = 15%)
        threshold: Significance threshold (default 15%)
    
    Returns:
        EvidenceDirection enum value
    """
    if percent_change is None:
        return EvidenceDirection.DATA_MISSING
    
    if expected_direction == 'up':
        if percent_change >= threshold:
            return EvidenceDirection.SUPPORT
        elif percent_change <= -threshold:
            return EvidenceDirection.CONTRADICT
        else:
            return EvidenceDirection.NEUTRAL
    
    elif expected_direction == 'down':
        if percent_change <= -threshold:
            return EvidenceDirection.SUPPORT
        elif percent_change >= threshold:
            return EvidenceDirection.CONTRADICT
        else:
            return EvidenceDirection.NEUTRAL
    
    elif expected_direction == 'flat':
        if abs(percent_change) <= threshold:
            return EvidenceDirection.SUPPORT
        else:
            return EvidenceDirection.CONTRADICT
    
    # Unknown direction
    return EvidenceDirection.NEUTRAL


def calculate_evidence_score(
    direction: EvidenceDirection,
    percent_change: float,
    saturation_point: float = DEFAULT_SATURATION_POINT,
) -> float:
    """
    Calculate graded evidence score from -1.0 to +1.0.
    
    Large movements saturate at the saturation point (default 30%).
    
    Args:
        direction: Evidence direction
        percent_change: Observed change as decimal
        saturation_point: Change at which score saturates
    
    Returns:
        Evidence score: +1.0 (strong support) to -1.0 (strong contradiction)
    """
    if percent_change is None:
        return 0.0
    
    if direction == EvidenceDirection.NEUTRAL:
        return 0.0
    
    if direction == EvidenceDirection.DATA_MISSING:
        return 0.0
    
    # Calculate magnitude (saturates at saturation_point)
    magnitude = min(1.0, abs(percent_change) / saturation_point)
    
    # Apply sign based on direction
    if direction == EvidenceDirection.SUPPORT:
        return magnitude
    elif direction == EvidenceDirection.CONTRADICT:
        return -magnitude
    
    return 0.0


def calculate_effect_size(
    baseline: float,
    current: float,
) -> float:
    """
    Calculate normalized effect size.
    
    Effect size is the absolute percent change, useful for
    understanding magnitude regardless of direction.
    
    Args:
        baseline: Baseline value
        current: Current value
    
    Returns:
        Effect size as positive decimal
    """
    if baseline is None or current is None:
        return 0.0
    
    if baseline == 0:
        if current == 0:
            return 0.0
        return 1.0  # Max effect if going from 0 to non-zero
    
    return abs((current - baseline) / abs(baseline))


# =============================================================================
# EVIDENCE GENERATOR
# =============================================================================

class EvidenceGenerator:
    """
    Generates EvidenceResults from prediction evaluations.
    
    Converts raw metric observations into graded evidence
    with proper scoring and weighting.
    """
    
    def __init__(self, weights: EvidenceWeights = None):
        """Initialize with weights configuration."""
        if weights is None:
            weights = EvidenceWeights()
        self.weights = weights
    
    def generate_evidence(
        self,
        prediction_id: str,
        hypothesis_id: str,
        meta_id: str,
        entity: str,
        canonical_metric: str,
        category: str,
        expected_direction: str,
        baseline: Optional[float],
        current: Optional[float],
        source: str = None,
    ) -> EvidenceResult:
        """
        Generate evidence from a prediction observation.
        
        Args:
            prediction_id: ID of the prediction
            hypothesis_id: ID of the parent hypothesis
            meta_id: ID of the meta-signal
            entity: Entity being observed
            canonical_metric: Metric type
            category: Signal category
            expected_direction: Expected change direction
            baseline: Baseline value
            current: Current observed value
            source: Data source (for reliability weighting)
        
        Returns:
            EvidenceResult with scored evidence
        """
        # Handle missing data
        if baseline is None or current is None:
            return EvidenceResult(
                prediction_id=prediction_id,
                hypothesis_id=hypothesis_id,
                meta_id=meta_id,
                entity=entity,
                canonical_metric=canonical_metric,
                category=category,
                expected_direction=expected_direction,
                direction=EvidenceDirection.DATA_MISSING.value,
                evidence_score=0.0,
                effect_size=0.0,
                weight=0.0,
                baseline_value=baseline,
                current_value=current,
                percent_change=None,
                notes="data_missing",
            )
        
        # Calculate percent change
        if baseline == 0:
            if current == 0:
                percent_change = 0.0
            else:
                percent_change = 1.0 if current > 0 else -1.0
        else:
            percent_change = (current - baseline) / abs(baseline)
        
        # Determine direction
        direction = calculate_evidence_direction(
            expected_direction,
            percent_change,
            self.weights.significant_change_threshold,
        )
        
        # Calculate evidence score
        evidence_score = calculate_evidence_score(
            direction,
            percent_change,
            self.weights.saturation_point,
        )
        
        # Calculate effect size
        effect_size = calculate_effect_size(baseline, current)
        
        # Get weight
        weight = self.weights.get_combined_weight(canonical_metric, source)
        
        # Build notes
        notes_parts = []
        if direction == EvidenceDirection.SUPPORT:
            notes_parts.append("supports_hypothesis")
        elif direction == EvidenceDirection.CONTRADICT:
            notes_parts.append("contradicts_hypothesis")
        elif direction == EvidenceDirection.NEUTRAL:
            notes_parts.append("within_noise_band")
        
        if effect_size > 0.5:
            notes_parts.append("large_effect")
        elif effect_size > 0.3:
            notes_parts.append("moderate_effect")
        
        return EvidenceResult(
            prediction_id=prediction_id,
            hypothesis_id=hypothesis_id,
            meta_id=meta_id,
            entity=entity,
            canonical_metric=canonical_metric,
            category=category,
            expected_direction=expected_direction,
            direction=direction.value,
            evidence_score=round(evidence_score, 4),
            effect_size=round(effect_size, 4),
            weight=round(weight, 4),
            baseline_value=baseline,
            current_value=current,
            percent_change=round(percent_change, 4),
            notes=";".join(notes_parts),
        )
    
    def generate_from_prediction_record(
        self,
        record: Dict[str, Any],
        baseline: Optional[float],
        current: Optional[float],
    ) -> EvidenceResult:
        """
        Generate evidence from a PredictionRecord dict.
        
        Args:
            record: PredictionRecord as dict
            baseline: Baseline value
            current: Current value
        
        Returns:
            EvidenceResult
        """
        # Extract source from observable query if available
        source = None
        obs_query = record.get('observable_query', {})
        if obs_query:
            source = obs_query.get('source')
        
        return self.generate_evidence(
            prediction_id=record.get('prediction_id', ''),
            hypothesis_id=record.get('hypothesis_id', ''),
            meta_id=record.get('meta_id', ''),
            entity=record.get('entity', ''),
            canonical_metric=record.get('canonical_metric', ''),
            category=record.get('category', ''),
            expected_direction=record.get('expected_direction', 'up'),
            baseline=baseline,
            current=current,
            source=source,
        )


# =============================================================================
# EVIDENCE STORE
# =============================================================================

class EvidenceStore:
    """
    Persists evidence results to JSONL files.
    
    Uses daily files for evidence log (append-only audit trail).
    """
    
    def __init__(self, data_dir: Path = None):
        """Initialize evidence store."""
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data" / "predictions"
        
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"EvidenceStore initialized at {self.data_dir}")
    
    def _get_daily_file(self, date: str = None) -> Path:
        """Get path to daily evidence file."""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        return self.data_dir / f"evidence_{date}.jsonl"
    
    def save_evidence(self, evidence: EvidenceResult, date: str = None):
        """Append evidence to daily file."""
        file_path = self._get_daily_file(date)
        
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(evidence.to_jsonl() + '\n')
        
        logger.debug(f"Saved evidence {evidence.prediction_id}")
    
    def save_evidence_batch(self, results: List[EvidenceResult], date: str = None):
        """Append batch of evidence to daily file."""
        if not results:
            return
        
        file_path = self._get_daily_file(date)
        
        with open(file_path, 'a', encoding='utf-8') as f:
            for evidence in results:
                f.write(evidence.to_jsonl() + '\n')
        
        logger.debug(f"Saved {len(results)} evidence results")
    
    def load_daily_evidence(self, date: str = None) -> List[EvidenceResult]:
        """Load all evidence from a daily file."""
        file_path = self._get_daily_file(date)
        
        if not file_path.exists():
            return []
        
        results = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        results.append(EvidenceResult.from_jsonl(line))
                    except Exception as e:
                        logger.warning(f"Failed to parse evidence line: {e}")
        
        return results
    
    def load_evidence_for_hypothesis(
        self,
        hypothesis_id: str,
        days_back: int = 30,
    ) -> List[EvidenceResult]:
        """Load all evidence for a hypothesis across multiple days."""
        from datetime import timedelta
        
        results = []
        now = datetime.now()
        
        for i in range(days_back):
            date = (now - timedelta(days=i)).strftime('%Y-%m-%d')
            daily = self.load_daily_evidence(date)
            results.extend([e for e in daily if e.hypothesis_id == hypothesis_id])
        
        return results


# =============================================================================
# TESTS
# =============================================================================

def _test_evidence_direction():
    """Test evidence direction calculation."""
    # Up expected
    assert calculate_evidence_direction('up', 0.20) == EvidenceDirection.SUPPORT
    assert calculate_evidence_direction('up', -0.20) == EvidenceDirection.CONTRADICT
    assert calculate_evidence_direction('up', 0.10) == EvidenceDirection.NEUTRAL
    
    # Down expected
    assert calculate_evidence_direction('down', -0.20) == EvidenceDirection.SUPPORT
    assert calculate_evidence_direction('down', 0.20) == EvidenceDirection.CONTRADICT
    
    # Flat expected
    assert calculate_evidence_direction('flat', 0.05) == EvidenceDirection.SUPPORT
    assert calculate_evidence_direction('flat', 0.25) == EvidenceDirection.CONTRADICT
    
    # Missing data
    assert calculate_evidence_direction('up', None) == EvidenceDirection.DATA_MISSING
    
    print("[PASS] _test_evidence_direction")


def _test_evidence_score():
    """Test evidence score calculation."""
    # Support saturates at 30%
    score = calculate_evidence_score(EvidenceDirection.SUPPORT, 0.15)
    assert score == 0.5  # 15% / 30% = 0.5
    
    score = calculate_evidence_score(EvidenceDirection.SUPPORT, 0.30)
    assert score == 1.0  # saturated
    
    score = calculate_evidence_score(EvidenceDirection.SUPPORT, 0.45)
    assert score == 1.0  # still saturated
    
    # Contradict is negative
    score = calculate_evidence_score(EvidenceDirection.CONTRADICT, 0.15)
    assert score == -0.5
    
    # Neutral is zero
    score = calculate_evidence_score(EvidenceDirection.NEUTRAL, 0.10)
    assert score == 0.0
    
    print("[PASS] _test_evidence_score")


def _test_evidence_generator():
    """Test evidence generation."""
    gen = EvidenceGenerator()
    
    # Generate support evidence
    evidence = gen.generate_evidence(
        prediction_id='pred_001',
        hypothesis_id='hyp_001',
        meta_id='meta_001',
        entity='nvidia',
        canonical_metric='filing_mentions',
        category='financial',
        expected_direction='up',
        baseline=100,
        current=125,
        source='sec',
    )
    
    assert evidence.direction == EvidenceDirection.SUPPORT.value
    assert evidence.evidence_score > 0
    assert evidence.percent_change == 0.25
    assert evidence.weight > 0.8  # SEC + filing_mentions = high weight
    
    print("[PASS] _test_evidence_generator")


def run_tests():
    """Run all evidence engine tests."""
    print("\n=== EVIDENCE ENGINE TESTS ===\n")
    
    _test_evidence_direction()
    _test_evidence_score()
    _test_evidence_generator()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
