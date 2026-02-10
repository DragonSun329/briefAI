"""
Enhanced Signal Metadata Module

Provides robust signal metadata tracking with confidence, coverage,
freshness, and historical context for the Trend Intelligence Platform.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from enum import Enum
import math


class SignalType(str, Enum):
    """Signal type identifiers."""
    TMS = "tms"           # Technical Momentum
    CCS = "ccs"           # Capital Conviction
    EIS_OFF = "eis_offensive"
    EIS_DEF = "eis_defensive"
    NAS = "nas"           # Narrative Attention
    PMS = "pms"           # Public Market Signal
    CSS = "css"           # Crypto Sentiment Signal


@dataclass
class SignalSource:
    """Individual data source contribution."""
    source_name: str           # e.g., "github", "hackernews", "polymarket"
    source_type: str           # e.g., "technical", "sentiment", "financial"
    entity_count: int          # Entities from this source
    raw_contribution: float    # Raw value contribution
    last_updated: datetime
    is_healthy: bool = True    # Source health status


@dataclass
class EnhancedSignalMetadata:
    """
    Complete signal metadata with all robustness fields.

    This is the core data structure for tracking signal quality,
    confidence, and lineage throughout the pipeline.
    """
    signal_name: str                    # tms, ccs, nas, etc.
    bucket_id: str                      # Which bucket this belongs to
    value: Optional[float] = None       # 0-100 percentile (None if missing)
    raw_value: Optional[float] = None   # Pre-percentile value

    # Robustness metrics (all 0-1 scale)
    confidence: float = 0.0             # Composite confidence score
    coverage: float = 0.0               # entity_count / expected_baseline
    freshness: float = 1.0              # Decays with age
    stability: float = 0.5              # Week-over-week consistency

    # Source tracking
    source_count: int = 0               # Number of distinct sources
    sources: List[SignalSource] = field(default_factory=list)
    entity_count: int = 0               # Total entities contributing

    # Smoothing (for volatile signals like NAS/CSS)
    ewma_value: Optional[float] = None  # Exponentially weighted moving average
    ewma_alpha: float = 0.3             # Smoothing factor
    raw_history: List[float] = field(default_factory=list)  # Last N raw values

    # Historical context
    percentile_12w: Optional[float] = None  # Percentile vs 12-week baseline
    percentile_26w: Optional[float] = None  # Percentile vs 26-week baseline
    z_score: Optional[float] = None         # Std devs from historical mean
    historical_mean: Optional[float] = None
    historical_std: Optional[float] = None

    # Velocity/trends
    delta_wow: Optional[float] = None   # Week-over-week change
    delta_4w: Optional[float] = None    # 4-week change
    trend_direction: str = "stable"     # rising, falling, stable

    # Timestamps
    last_updated: datetime = field(default_factory=datetime.now)
    data_age_hours: float = 0.0

    def compute_confidence(self) -> float:
        """
        Compute composite confidence score from components.

        Formula: 0.35×coverage + 0.25×freshness + 0.25×stability + 0.15×source_diversity
        """
        # Source diversity: more sources = higher confidence
        source_diversity = min(1.0, self.source_count / 4)  # Cap at 4 sources

        self.confidence = (
            0.35 * self.coverage +
            0.25 * self.freshness +
            0.25 * self.stability +
            0.15 * source_diversity
        )
        return self.confidence

    def compute_freshness(self, half_life_hours: float = 48.0) -> float:
        """
        Compute freshness score with exponential decay.

        Args:
            half_life_hours: Hours until freshness = 0.5

        Returns:
            Freshness score 0-1
        """
        if not self.sources:
            self.freshness = 0.0
            return 0.0

        # Use most recent source update
        latest = max(s.last_updated for s in self.sources)
        age_hours = (datetime.now() - latest).total_seconds() / 3600
        self.data_age_hours = age_hours

        # Exponential decay: f(t) = exp(-t * ln(2) / half_life)
        decay_constant = math.log(2) / half_life_hours
        self.freshness = math.exp(-age_hours * decay_constant)

        return self.freshness

    def update_ewma(self, new_value: float, alpha: Optional[float] = None) -> float:
        """
        Update exponentially weighted moving average.

        Args:
            new_value: New raw signal value
            alpha: Smoothing factor (0-1, higher = more reactive)

        Returns:
            Updated EWMA value
        """
        if alpha is not None:
            self.ewma_alpha = alpha

        # Keep history for debugging/visualization
        self.raw_history.append(new_value)
        if len(self.raw_history) > 52:  # Keep 1 year max
            self.raw_history = self.raw_history[-52:]

        if self.ewma_value is None:
            self.ewma_value = new_value
        else:
            self.ewma_value = (
                self.ewma_alpha * new_value +
                (1 - self.ewma_alpha) * self.ewma_value
            )

        return self.ewma_value

    def compute_stability(self, recent_values: List[float], window: int = 4) -> float:
        """
        Compute stability from recent value variance.

        Low variance = high stability.

        Args:
            recent_values: Last N values (typically weeks)
            window: Number of periods to consider

        Returns:
            Stability score 0-1
        """
        if len(recent_values) < 2:
            self.stability = 0.5  # Neutral if not enough data
            return self.stability

        values = recent_values[-window:]

        # Compute coefficient of variation
        mean = sum(values) / len(values)
        if mean == 0:
            self.stability = 0.5
            return self.stability

        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = variance ** 0.5
        cv = std / mean if mean != 0 else 0

        # Convert to 0-1 stability score (lower CV = higher stability)
        # CV of 0.5 = stability 0.5, CV of 0 = stability 1.0
        self.stability = max(0, min(1, 1 - cv))

        return self.stability

    def compute_z_score(self, current: float, mean: float, std: float) -> float:
        """
        Compute z-score relative to historical distribution.

        Args:
            current: Current signal value
            mean: Historical mean
            std: Historical standard deviation

        Returns:
            Z-score (number of std devs from mean)
        """
        if std == 0 or std is None:
            self.z_score = 0.0
            return 0.0

        self.historical_mean = mean
        self.historical_std = std
        self.z_score = (current - mean) / std

        return self.z_score

    def compute_trend_direction(self, threshold: float = 5.0) -> str:
        """
        Determine trend direction from recent deltas.

        Args:
            threshold: Minimum change to count as rising/falling

        Returns:
            "rising", "falling", or "stable"
        """
        if self.delta_wow is None:
            self.trend_direction = "stable"
        elif self.delta_wow > threshold:
            self.trend_direction = "rising"
        elif self.delta_wow < -threshold:
            self.trend_direction = "falling"
        else:
            self.trend_direction = "stable"

        return self.trend_direction

    def is_reliable(self, min_confidence: float = 0.5) -> bool:
        """Check if signal meets minimum reliability threshold."""
        return self.confidence >= min_confidence and self.value is not None

    def is_actionable(self, min_confidence: float = 0.6, max_z_score: float = 3.0) -> bool:
        """
        Check if signal is reliable enough for decision-making.

        Requires sufficient confidence and not an extreme outlier.
        """
        if not self.is_reliable(min_confidence):
            return False

        if self.z_score is not None and abs(self.z_score) > max_z_score:
            return False  # Extreme outlier, may be data error

        return True

    def get_quality_badge(self) -> str:
        """Get human-readable quality assessment."""
        if self.value is None:
            return "NO_DATA"
        elif self.confidence >= 0.8:
            return "HIGH"
        elif self.confidence >= 0.5:
            return "MEDIUM"
        elif self.confidence >= 0.3:
            return "LOW"
        else:
            return "VERY_LOW"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "signal_name": self.signal_name,
            "bucket_id": self.bucket_id,
            "value": self.value,
            "raw_value": self.raw_value,
            "confidence": round(self.confidence, 3),
            "coverage": round(self.coverage, 3),
            "freshness": round(self.freshness, 3),
            "stability": round(self.stability, 3),
            "source_count": self.source_count,
            "entity_count": self.entity_count,
            "ewma_value": round(self.ewma_value, 2) if self.ewma_value else None,
            "percentile_12w": self.percentile_12w,
            "percentile_26w": self.percentile_26w,
            "z_score": round(self.z_score, 2) if self.z_score else None,
            "delta_wow": self.delta_wow,
            "delta_4w": self.delta_4w,
            "trend_direction": self.trend_direction,
            "quality_badge": self.get_quality_badge(),
            "last_updated": self.last_updated.isoformat(),
            "data_age_hours": round(self.data_age_hours, 1),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnhancedSignalMetadata":
        """Create from dictionary."""
        metadata = cls(
            signal_name=data["signal_name"],
            bucket_id=data["bucket_id"],
            value=data.get("value"),
            raw_value=data.get("raw_value"),
            confidence=data.get("confidence", 0),
            coverage=data.get("coverage", 0),
            freshness=data.get("freshness", 1),
            stability=data.get("stability", 0.5),
            source_count=data.get("source_count", 0),
            entity_count=data.get("entity_count", 0),
            ewma_value=data.get("ewma_value"),
            percentile_12w=data.get("percentile_12w"),
            percentile_26w=data.get("percentile_26w"),
            z_score=data.get("z_score"),
            delta_wow=data.get("delta_wow"),
            delta_4w=data.get("delta_4w"),
            trend_direction=data.get("trend_direction", "stable"),
        )

        if "last_updated" in data:
            metadata.last_updated = datetime.fromisoformat(data["last_updated"])

        return metadata


@dataclass
class BucketSignalBundle:
    """
    Container for all signals of a bucket with aggregate quality metrics.
    """
    bucket_id: str
    bucket_name: str
    week_id: str

    # Individual signal metadata
    tms: Optional[EnhancedSignalMetadata] = None
    ccs: Optional[EnhancedSignalMetadata] = None
    eis_offensive: Optional[EnhancedSignalMetadata] = None
    eis_defensive: Optional[EnhancedSignalMetadata] = None
    nas: Optional[EnhancedSignalMetadata] = None
    pms: Optional[EnhancedSignalMetadata] = None
    css: Optional[EnhancedSignalMetadata] = None

    # Aggregate metrics
    overall_confidence: float = 0.0
    overall_coverage: float = 0.0
    signal_count: int = 0
    healthy_signal_count: int = 0

    def compute_aggregates(self) -> None:
        """Compute aggregate metrics across all signals."""
        signals = [self.tms, self.ccs, self.eis_offensive, self.eis_defensive,
                   self.nas, self.pms, self.css]

        present = [s for s in signals if s is not None and s.value is not None]
        self.signal_count = len(present)

        if not present:
            self.overall_confidence = 0.0
            self.overall_coverage = 0.0
            return

        # Weighted average confidence (weight by coverage)
        total_coverage = sum(s.coverage for s in present)
        if total_coverage > 0:
            self.overall_confidence = sum(
                s.confidence * s.coverage for s in present
            ) / total_coverage
        else:
            self.overall_confidence = sum(s.confidence for s in present) / len(present)

        self.overall_coverage = total_coverage / len(signals)  # Out of 7 possible
        self.healthy_signal_count = sum(1 for s in present if s.is_reliable())

    def get_coverage_badge(self) -> str:
        """Get coverage quality badge."""
        if self.signal_count >= 6:
            return "FULL"
        elif self.signal_count >= 4:
            return "GOOD"
        elif self.signal_count >= 2:
            return "PARTIAL"
        else:
            return "LOW"

    def get_missing_signals(self) -> List[str]:
        """List signals with no data."""
        missing = []
        signal_map = {
            "tms": self.tms,
            "ccs": self.ccs,
            "eis_offensive": self.eis_offensive,
            "eis_defensive": self.eis_defensive,
            "nas": self.nas,
            "pms": self.pms,
            "css": self.css,
        }

        for name, signal in signal_map.items():
            if signal is None or signal.value is None:
                missing.append(name)

        return missing

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "bucket_id": self.bucket_id,
            "bucket_name": self.bucket_name,
            "week_id": self.week_id,
            "signals": {
                "tms": self.tms.to_dict() if self.tms else None,
                "ccs": self.ccs.to_dict() if self.ccs else None,
                "eis_offensive": self.eis_offensive.to_dict() if self.eis_offensive else None,
                "eis_defensive": self.eis_defensive.to_dict() if self.eis_defensive else None,
                "nas": self.nas.to_dict() if self.nas else None,
                "pms": self.pms.to_dict() if self.pms else None,
                "css": self.css.to_dict() if self.css else None,
            },
            "overall_confidence": round(self.overall_confidence, 3),
            "overall_coverage": round(self.overall_coverage, 3),
            "signal_count": self.signal_count,
            "healthy_signal_count": self.healthy_signal_count,
            "coverage_badge": self.get_coverage_badge(),
            "missing_signals": self.get_missing_signals(),
        }