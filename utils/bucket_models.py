"""
Bucket-Level Signal Models

Data models for trend bucket analysis. Key difference from entity-level:
- Scores are computed at the BUCKET level, not entity level
- Uses VELOCITY (week-over-week change) not absolute values
- Scores are PERCENTILES within each instrument

Four subscores per bucket:
1. TMS (Technical Momentum Score) - GitHub + HuggingFace velocity
2. CCS (Capital Conviction Score) - VC/Crunchbase deal velocity
3. EIS (Enterprise/Institutional Signal) - SEC EDGAR mentions
4. NAS (Narrative/Attention Score) - News/social (optional)
"""

from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional, Dict, Any, Literal, ClassVar
from enum import Enum
from pydantic import BaseModel, Field
import uuid


class LifecycleState(str, Enum):
    """Bucket lifecycle states based on signal patterns."""
    EMERGING = "emerging"           # High TMS, low CCS/EIS
    VALIDATING = "validating"       # TMS + CCS both high
    ESTABLISHING = "establishing"   # CCS + EIS high
    MAINSTREAM = "mainstream"       # All stable, consolidating


class HypeCyclePhase(str, Enum):
    """
    Gartner Hype Cycle phases for technology maturity positioning.

    Maps signal patterns to familiar business analyst framework:
    - Innovation Trigger: New tech emerges, high technical interest
    - Peak of Expectations: Hype maximized, capital floods in
    - Trough of Disillusionment: Reality check, interest wanes
    - Slope of Enlightenment: Practical applications emerge
    - Plateau of Productivity: Mainstream adoption, stable market
    """
    INNOVATION_TRIGGER = "innovation_trigger"
    PEAK_EXPECTATIONS = "peak_expectations"
    TROUGH_DISILLUSIONMENT = "trough_disillusionment"
    SLOPE_ENLIGHTENMENT = "slope_enlightenment"
    PLATEAU_PRODUCTIVITY = "plateau_productivity"
    UNKNOWN = "unknown"  # Insufficient data to determine phase


class CoverageBadge(str, Enum):
    """Data coverage quality badge for signal completeness."""
    FULL = "full"           # 6/6 signals have data
    GOOD = "good"           # 4-5/6 signals have data
    PARTIAL = "partial"     # 2-3/6 signals have data
    LOW = "low"             # 0-1/6 signals have data


class AlertType(str, Enum):
    """Types of divergence alerts."""
    ALPHA_ZONE = "alpha_zone"               # High TMS, low CCS - hidden gem
    HYPE_ZONE = "hype_zone"                 # High CCS, low TMS - vaporware
    ENTERPRISE_PULL = "enterprise_pull"     # EIS offensive rising
    DISRUPTION_PRESSURE = "disruption_pressure"  # EIS defensive spiking
    ROTATION = "rotation"                   # TMS decelerating, market maturing


class AlertInterpretation(str, Enum):
    """How to interpret an alert."""
    OPPORTUNITY = "opportunity"
    RISK = "risk"
    SIGNAL = "signal"
    NEUTRAL = "neutral"


class AlertSeverity(str, Enum):
    """Alert severity levels for graded alerting."""
    INFO = "info"           # Watch - early signal
    WARN = "warn"           # Divergence likely
    CRIT = "crit"           # Divergence + accelerating + persistent


class MissingReason(str, Enum):
    """Reason why a signal value is missing or unreliable."""
    NO_DATA = "no_data"
    SCRAPER_FAILURE = "scraper_failure"
    RATE_LIMITED = "rate_limited"
    STALE_DATA = "stale_data"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    PLACEHOLDER = "placeholder"


class SignalQuality(str, Enum):
    """Quality tier for signal reliability."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INVALID = "invalid"


# =============================================================================
# Signal Confidence & Coverage Model
# =============================================================================

class SignalMetadata(BaseModel):
    """
    Per-signal metadata for robustness tracking.

    Tracks coverage, confidence, and smoothing for each signal.

    Signal Contract:
    - value: The score (None if missing)
    - confidence: How reliable is this value (0-1)
    - coverage: Data completeness (0-1)
    - freshness_hours: How old is this data
    - contributors: Which entities drove this score
    - missing_reason: Why is value None (if applicable)
    """
    # Class-level thresholds
    COVERAGE_THRESHOLD: ClassVar[float] = 0.6  # Below this, signal is unreliable
    STALE_HOURS: ClassVar[float] = 168.0       # 7 days = stale

    value: Optional[float] = None          # The actual score (0-100 percentile)
    raw_value: Optional[float] = None      # Pre-percentile raw value

    # Coverage: how many entities observed vs expected baseline
    coverage: float = 0.0                  # 0-1, where 1 = full expected coverage
    entity_count: int = 0                  # Actual entities observed
    expected_baseline: int = 10            # Expected entities for full coverage

    # Confidence: coverage × stability × mapping_confidence
    confidence: float = 0.5                # 0-1, overall signal confidence
    mapping_confidence: float = 0.8        # How well entities map to this bucket
    stability: float = 0.8                 # Low if high week-over-week variance

    # Freshness tracking
    freshness_hours: float = 0.0           # Hours since last data update

    # Smoothing (for NAS/CSS volatility reduction)
    ewma_value: Optional[float] = None     # EWMA-smoothed value (alpha=0.35)
    raw_unsmoothed: Optional[float] = None # Pre-smoothing value
    is_smoothed: bool = False              # Whether EWMA was applied

    # Source info
    sources: List[str] = Field(default_factory=list)  # e.g., ["github", "huggingface"]
    source_failures: List[str] = Field(default_factory=list)  # Failed sources

    # Contributors tracking (entities that contributed to this signal)
    contributors: List[Dict[str, Any]] = Field(default_factory=list)
    # Structure: [{"entity": "langchain/langchain", "contribution": 0.3}, ...]

    # Missing data tracking
    missing_reason: Optional[MissingReason] = None  # Why value is None

    # Percentile computation basis
    percentile_basis: int = 0              # How many buckets in the percentile comparison

    @property
    def is_valid(self) -> bool:
        """True if signal has a value (not missing)."""
        return self.value is not None

    @property
    def is_stale(self) -> bool:
        """True if data is older than STALE_HOURS threshold."""
        return self.freshness_hours > self.STALE_HOURS

    @property
    def is_coverage_insufficient(self) -> bool:
        """True if coverage is below the minimum threshold."""
        return self.coverage < self.COVERAGE_THRESHOLD

    @property
    def quality(self) -> SignalQuality:
        """
        Compute signal quality tier based on confidence and coverage.

        Quality tiers:
        - HIGH: confidence >= 0.8 AND coverage >= 0.6
        - MEDIUM: confidence >= 0.5 OR coverage >= 0.4
        - LOW: confidence < 0.5 AND coverage < 0.4
        - INVALID: value is None
        """
        if self.value is None:
            return SignalQuality.INVALID

        # High quality: both confidence and coverage are good
        if self.confidence >= 0.8 and self.coverage >= 0.6:
            return SignalQuality.HIGH

        # Medium quality: at least one metric is acceptable
        if self.confidence >= 0.5 or self.coverage >= 0.4:
            return SignalQuality.MEDIUM

        # Low quality: both metrics are poor
        return SignalQuality.LOW

    def get_display_reason(self) -> str:
        """Get a human-readable reason for signal quality issues."""
        if self.value is None and self.missing_reason:
            reason_map = {
                MissingReason.NO_DATA: "no data available",
                MissingReason.SCRAPER_FAILURE: "data collection failed",
                MissingReason.RATE_LIMITED: "API rate limited",
                MissingReason.STALE_DATA: "data too old",
                MissingReason.INSUFFICIENT_COVERAGE: "insufficient data points",
                MissingReason.PLACEHOLDER: "placeholder value",
            }
            return reason_map.get(self.missing_reason, "unknown reason")

        if self.is_coverage_insufficient:
            coverage_pct = int(self.coverage * 100)
            return f"low coverage ({coverage_pct}%)"

        if self.is_stale:
            return f"stale data ({int(self.freshness_hours)}h old)"

        if self.confidence < 0.5:
            return f"low confidence ({int(self.confidence * 100)}%)"

        return "valid"

    def compute_confidence(self) -> float:
        """Compute overall confidence from components."""
        # Coverage contribution (0-0.4)
        coverage_factor = min(self.coverage, 1.0) * 0.4

        # Stability contribution (0-0.3)
        stability_factor = self.stability * 0.3

        # Mapping contribution (0-0.3)
        mapping_factor = self.mapping_confidence * 0.3

        self.confidence = coverage_factor + stability_factor + mapping_factor
        return self.confidence

    def get_confidence_label(self) -> str:
        """Get human-readable confidence label."""
        if self.confidence >= 0.7:
            return "high"
        elif self.confidence >= 0.4:
            return "medium"
        else:
            return "low"


# =============================================================================
# Confidence Interval Model
# =============================================================================

class ConfidenceInterval(BaseModel):
    """
    Confidence interval for a signal score.

    Provides low/mid/high bounds for percentile scores to communicate
    uncertainty to business analysts making investment decisions.
    """
    low: float = 50.0       # 5th percentile estimate (lower bound)
    mid: float = 50.0       # Point estimate (observed value)
    high: float = 50.0      # 95th percentile estimate (upper bound)
    variance: float = 10.0  # Overall estimated variance

    # Variance components (for transparency)
    coverage_variance: float = 0.0   # From entity count vs expected baseline
    source_variance: float = 0.0     # From diversity across data sources
    temporal_variance: float = 0.0   # From week-over-week volatility

    @property
    def range(self) -> float:
        """Width of the confidence interval."""
        return self.high - self.low

    @property
    def is_wide(self) -> bool:
        """True if interval is too wide to be actionable (>30 points)."""
        return self.range > 30

    @property
    def is_reliable(self) -> bool:
        """True if interval is narrow enough for confident decisions (<15 points)."""
        return self.range < 15


# =============================================================================
# Investment Thesis (5T) Model
# =============================================================================

class FiveTScore(BaseModel):
    """
    Investment Thesis 5T scoring model.

    Provides structured scoring across five dimensions commonly used
    by VC/investment analysts:
    - Team: Quality of founders, key hires, prior exits
    - Technology: Technical momentum and innovation signals
    - Market: Market size, growth potential, attention
    - Timing: Is it the right time? Lifecycle position
    - Traction: Revenue proxies, adoption signals, enterprise interest
    """
    # Scores (0-100 percentile)
    team: float = 50.0
    technology: float = 50.0
    market: float = 50.0
    timing: float = 50.0
    traction: float = 50.0

    # Per-dimension confidence (0-1)
    team_confidence: float = 0.5
    technology_confidence: float = 0.5
    market_confidence: float = 0.5
    timing_confidence: float = 0.5
    traction_confidence: float = 0.5

    # Evidence for each dimension (for explainability)
    team_evidence: List[str] = Field(default_factory=list)
    technology_evidence: List[str] = Field(default_factory=list)
    market_evidence: List[str] = Field(default_factory=list)
    timing_evidence: List[str] = Field(default_factory=list)
    traction_evidence: List[str] = Field(default_factory=list)

    @property
    def composite(self) -> float:
        """Weighted composite score (equal weights by default)."""
        return (self.team + self.technology + self.market +
                self.timing + self.traction) / 5.0

    @property
    def overall_confidence(self) -> float:
        """Average confidence across all dimensions."""
        return (self.team_confidence + self.technology_confidence +
                self.market_confidence + self.timing_confidence +
                self.traction_confidence) / 5.0

    def get_strongest_dimension(self) -> str:
        """Return the highest-scoring dimension."""
        scores = {
            "team": self.team,
            "technology": self.technology,
            "market": self.market,
            "timing": self.timing,
            "traction": self.traction,
        }
        return max(scores, key=scores.get)

    def get_weakest_dimension(self) -> str:
        """Return the lowest-scoring dimension."""
        scores = {
            "team": self.team,
            "technology": self.technology,
            "market": self.market,
            "timing": self.timing,
            "traction": self.traction,
        }
        return min(scores, key=scores.get)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "team": self.team,
            "technology": self.technology,
            "market": self.market,
            "timing": self.timing,
            "traction": self.traction,
            "composite": self.composite,
            "overall_confidence": self.overall_confidence,
            "strongest": self.get_strongest_dimension(),
            "weakest": self.get_weakest_dimension(),
        }


# =============================================================================
# Data Coverage Model
# =============================================================================

class DataCoverage(BaseModel):
    """
    Tracks data coverage for a bucket profile.

    Provides transparency about which signals have actual data vs
    which are missing/imputed, displayed as coverage badges in UI.
    """
    # Per-signal coverage flags
    has_tms: bool = False
    has_ccs: bool = False
    has_eis: bool = False
    has_nas: bool = False
    has_pms: bool = False
    has_css: bool = False

    # Source details for each signal
    tms_sources: List[str] = Field(default_factory=list)
    ccs_sources: List[str] = Field(default_factory=list)
    eis_sources: List[str] = Field(default_factory=list)
    nas_sources: List[str] = Field(default_factory=list)

    @property
    def signal_count(self) -> int:
        """Count of signals with actual data."""
        return sum([
            self.has_tms, self.has_ccs, self.has_eis,
            self.has_nas, self.has_pms, self.has_css
        ])

    @property
    def coverage_score(self) -> float:
        """Coverage score as percentage (0-100)."""
        return (self.signal_count / 6) * 100

    @property
    def badge(self) -> CoverageBadge:
        """Get coverage badge based on signal count."""
        if self.signal_count >= 6:
            return CoverageBadge.FULL
        elif self.signal_count >= 4:
            return CoverageBadge.GOOD
        elif self.signal_count >= 2:
            return CoverageBadge.PARTIAL
        else:
            return CoverageBadge.LOW

    def get_missing_signals(self) -> List[str]:
        """Return list of missing signal names."""
        missing = []
        if not self.has_tms: missing.append("TMS")
        if not self.has_ccs: missing.append("CCS")
        if not self.has_eis: missing.append("EIS")
        if not self.has_nas: missing.append("NAS")
        if not self.has_pms: missing.append("PMS")
        if not self.has_css: missing.append("CSS")
        return missing

    def get_available_signals(self) -> List[str]:
        """Return list of available signal names."""
        available = []
        if self.has_tms: available.append("TMS")
        if self.has_ccs: available.append("CCS")
        if self.has_eis: available.append("EIS")
        if self.has_nas: available.append("NAS")
        if self.has_pms: available.append("PMS")
        if self.has_css: available.append("CSS")
        return available


# =============================================================================
# Bucket-Level Models
# =============================================================================

class BucketObservation(BaseModel):
    """
    Weekly observation for a trend bucket from a specific instrument.

    This captures the raw velocity metrics for one week.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    bucket_id: str
    instrument: Literal["technical", "capital", "enterprise", "narrative"]
    week_start: date                  # Monday of the observation week
    week_end: date                    # Sunday of the observation week

    # Raw velocity metrics (instrument-specific)
    raw_metrics: Dict[str, Any] = Field(default_factory=dict)
    # Technical: {"star_velocity": 1500, "fork_velocity": 200, "download_velocity": 50000}
    # Capital: {"deal_count": 5, "smart_money_count": 3, "new_company_count": 2}
    # Enterprise: {"offensive_mentions": 15, "defensive_mentions": 8}
    # Narrative: {"article_count": 50, "sentiment_avg": 0.7}

    # Computed velocity (primary metric for scoring)
    primary_velocity: float = 0.0     # Main velocity measure for this instrument
    velocity_delta_wow: Optional[float] = None  # Week-over-week change

    # Entity contributions (which entities drove this bucket's score)
    contributing_entities: List[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)


class BucketScore(BaseModel):
    """
    Percentile score for a bucket on one instrument for one week.

    Percentile is computed across ALL buckets for that week.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    bucket_id: str
    instrument: Literal["technical", "capital", "enterprise", "narrative"]
    week_start: date

    # Percentile score (0-100, where 100 = top bucket)
    percentile: float

    # Raw score before percentile conversion
    raw_score: float

    # Velocity metrics
    velocity: float
    velocity_delta_wow: Optional[float] = None  # WoW change
    velocity_delta_mom: Optional[float] = None  # MoM change (4-week)

    created_at: datetime = Field(default_factory=datetime.utcnow)


class BucketProfile(BaseModel):
    """
    Complete signal profile for a trend bucket at a point in time.

    Contains all four subscores and derived insights.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    bucket_id: str
    bucket_name: str
    week_start: date

    # Four subscores (percentiles 0-100)
    tms: Optional[float] = None       # Technical Momentum Score
    ccs: Optional[float] = None       # Capital Conviction Score
    eis_offensive: Optional[float] = None  # Enterprise Institutional (offensive)
    eis_defensive: Optional[float] = None  # Enterprise Institutional (defensive)
    nas: Optional[float] = None       # Narrative/Attention Score

    # Financial signals (from financial_signals.py)
    pms: Optional[float] = None       # Public Market Signal
    css: Optional[float] = None       # Crypto Sentiment Signal

    # Combined EIS for convenience
    @property
    def eis(self) -> Optional[float]:
        if self.eis_offensive is None and self.eis_defensive is None:
            return None
        off = self.eis_offensive or 0
        defe = self.eis_defensive or 0
        return max(off, defe)

    # Composite heat score (configurable weights)
    heat_score: float = 0.0           # 0.5*TMS + 0.3*CCS + 0.2*EIS_off

    # Velocity/momentum (week-over-week)
    tms_delta_wow: Optional[float] = None
    ccs_delta_wow: Optional[float] = None
    heat_delta_wow: Optional[float] = None

    # 4-week momentum (for motion vectors)
    tms_delta_4w: Optional[float] = None   # 4-week TMS change
    ccs_delta_4w: Optional[float] = None   # 4-week CCS change
    velocity_accelerating: bool = False    # Is momentum increasing?

    # Lifecycle state
    lifecycle_state: LifecycleState = LifecycleState.EMERGING
    lifecycle_confidence: float = 0.5

    # Confidence and variance for uncertainty visualization
    signal_confidence: float = 0.8    # Overall confidence in scores (0-1)
    internal_variance: float = 10.0   # Variance within bucket (internal segmentation)

    # Entity count for this bucket
    entity_count: int = 0

    # Data freshness
    data_freshness: Dict[str, datetime] = Field(default_factory=dict)

    # Top entities driving this bucket
    top_technical_entities: List[str] = Field(default_factory=list)
    top_capital_entities: List[str] = Field(default_factory=list)
    top_enterprise_entities: List[str] = Field(default_factory=list)

    # === Signal Metadata (robustness tracking) ===
    # Per-signal confidence and coverage for transparency
    signal_metadata: Dict[str, Any] = Field(default_factory=dict)
    # Structure: {
    #   "tms": {"value": 92, "confidence": 0.85, "coverage": 0.72, "sources": ["github", "huggingface"]},
    #   "ccs": {"value": 45, "confidence": 0.65, "coverage": 0.50, "sources": ["crunchbase"]},
    #   ...
    # }

    # Data integrity issues (for banner display)
    data_issues: List[str] = Field(default_factory=list)
    # e.g., ["GitHub API rate limit hit", "SEC parser failed for 2 filings"]

    # === Business Analyst Frameworks ===

    # Gartner Hype Cycle positioning
    hype_cycle_phase: HypeCyclePhase = HypeCyclePhase.UNKNOWN
    hype_cycle_confidence: float = 0.5
    hype_cycle_rationale: str = ""

    # Investment Thesis 5T scoring
    five_t_score: Optional[FiveTScore] = None

    # Confidence intervals for key signals
    confidence_intervals: Dict[str, ConfidenceInterval] = Field(default_factory=dict)
    # Structure: {"tms": ConfidenceInterval(...), "ccs": ConfidenceInterval(...)}

    # Data coverage tracking
    data_coverage: Optional[DataCoverage] = None

    # Source credibility metrics
    source_credibility: float = 0.5  # Overall credibility (0-1)
    source_credibility_by_signal: Dict[str, float] = Field(default_factory=dict)
    # Structure: {"tms": 0.6, "ccs": 0.85, "nas": 0.72}

    created_at: datetime = Field(default_factory=datetime.utcnow)

    def get_signal_confidence(self, signal_name: str) -> float:
        """Get confidence for a specific signal."""
        meta = self.signal_metadata.get(signal_name, {})
        return meta.get("confidence", 0.5)

    def get_overall_confidence(self) -> float:
        """Compute overall profile confidence from all signals."""
        confidences = []
        for signal in ["tms", "ccs", "nas", "eis"]:
            meta = self.signal_metadata.get(signal, {})
            if meta.get("value") is not None:
                confidences.append(meta.get("confidence", 0.5))
        return sum(confidences) / len(confidences) if confidences else 0.5

    def get_radar_data(self) -> Dict[str, float]:
        """Get data for radar/quadrant visualization."""
        return {
            "tms": self.tms or 0,
            "ccs": self.ccs or 0,
            "eis_offensive": self.eis_offensive or 0,
            "eis_defensive": self.eis_defensive or 0,
            "nas": self.nas or 0,
            "pms": self.pms or 0,
            "css": self.css or 0,
        }


class BucketAlert(BaseModel):
    """
    Divergence alert for a trend bucket.

    Alerts are triggered when subscores diverge significantly.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    bucket_id: str
    bucket_name: str
    week_start: date

    # Alert details
    alert_type: AlertType
    interpretation: AlertInterpretation
    severity: AlertSeverity = AlertSeverity.INFO  # Graded severity

    # Which scores triggered the alert
    trigger_scores: Dict[str, float]  # {"tms": 92, "ccs": 25}
    threshold_used: str               # Description of condition

    # Magnitude of divergence
    divergence_magnitude: float       # Difference between high/low scores

    # Z-score based detection (change-based, not threshold-based)
    z_score: Optional[float] = None   # How many std devs from baseline
    velocity_percentile: Optional[float] = None  # Where is velocity vs history

    # Evidence
    rationale: str
    supporting_entities: List[str] = Field(default_factory=list)
    evidence_snippets: List[str] = Field(default_factory=list)
    evidence_count: int = 0           # Number of supporting data points

    # Signal confidence (affects severity)
    signal_confidence: float = 0.8    # Confidence in triggering signals

    # Suggested action
    action_hint: Optional[str] = None  # e.g., "investigate keywords: 'Blackwell supply'"

    # Persistence
    first_detected: date
    weeks_persistent: int = 1
    resolved_at: Optional[date] = None

    # Cooldown tracking (prevent alert spam)
    last_shown: Optional[date] = None  # When was this alert last displayed
    cooldown_days: int = 7             # Don't re-show for N days unless severity increases
    previous_severity: Optional[AlertSeverity] = None  # Track if severity changed

    created_at: datetime = Field(default_factory=datetime.utcnow)

    def should_show(self, today: date) -> bool:
        """Check if alert should be shown based on cooldown."""
        if self.last_shown is None:
            return True
        days_since = (today - self.last_shown).days
        # Show if cooldown expired OR severity increased
        if days_since >= self.cooldown_days:
            return True
        if self.previous_severity and self.severity.value > self.previous_severity.value:
            return True  # Severity escalated
        return False

    def compute_severity(self) -> AlertSeverity:
        """Compute severity based on magnitude, persistence, and confidence."""
        score = 0

        # Magnitude contribution (0-3 points)
        if self.divergence_magnitude >= 60:
            score += 3
        elif self.divergence_magnitude >= 40:
            score += 2
        elif self.divergence_magnitude >= 20:
            score += 1

        # Persistence contribution (0-2 points)
        if self.weeks_persistent >= 3:
            score += 2
        elif self.weeks_persistent >= 2:
            score += 1

        # Confidence contribution (0-2 points)
        if self.signal_confidence >= 0.8:
            score += 2
        elif self.signal_confidence >= 0.6:
            score += 1

        # Z-score contribution (0-2 points)
        if self.z_score is not None:
            if abs(self.z_score) >= 2.5:
                score += 2
            elif abs(self.z_score) >= 2.0:
                score += 1

        # Map to severity
        if score >= 6:
            self.severity = AlertSeverity.CRIT
        elif score >= 3:
            self.severity = AlertSeverity.WARN
        else:
            self.severity = AlertSeverity.INFO

        return self.severity


# =============================================================================
# Entity-to-Bucket Mapping
# =============================================================================

class EntityBucketMapping(BaseModel):
    """
    Maps an entity to its trend bucket(s).

    Entities can belong to multiple buckets with different confidence levels.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_id: str
    entity_name: str
    entity_type: Literal["repo", "model", "company", "issuer", "space"]

    # Bucket assignments
    bucket_mappings: List[Dict[str, Any]] = Field(default_factory=list)
    # [{"bucket_id": "rag-retrieval", "confidence": 0.9, "reason": "keyword"}]

    primary_bucket_id: Optional[str] = None  # Highest confidence bucket

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Weekly Snapshot
# =============================================================================

class WeeklySnapshot(BaseModel):
    """
    Complete weekly snapshot of all bucket profiles.

    This is the main output artifact - "what's the state of AI trends this week?"
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    week_start: date
    week_end: date

    # All bucket profiles for this week
    bucket_profiles: List[BucketProfile] = Field(default_factory=list)

    # Active alerts
    alerts: List[BucketAlert] = Field(default_factory=list)

    # Top heating buckets
    top_heating: List[str] = Field(default_factory=list)  # bucket_ids by heat

    # Lifecycle transitions this week
    lifecycle_transitions: List[Dict[str, Any]] = Field(default_factory=list)
    # [{"bucket_id": "rag-retrieval", "from": "emerging", "to": "validating"}]

    # Summary stats
    total_buckets_scored: int = 0
    total_alerts_fired: int = 0
    opportunities_count: int = 0
    risks_count: int = 0

    created_at: datetime = Field(default_factory=datetime.utcnow)

    def get_bucket_profile(self, bucket_id: str) -> Optional[BucketProfile]:
        """Get profile for a specific bucket."""
        for profile in self.bucket_profiles:
            if profile.bucket_id == bucket_id:
                return profile
        return None

    def get_alerts_for_bucket(self, bucket_id: str) -> List[BucketAlert]:
        """Get alerts for a specific bucket."""
        return [a for a in self.alerts if a.bucket_id == bucket_id]


# =============================================================================
# Configuration Models
# =============================================================================

class HeatWeights(BaseModel):
    """Weights for computing composite heat score."""
    tms: float = 0.5
    ccs: float = 0.3
    eis_offensive: float = 0.2

    def compute_heat(self, profile: BucketProfile) -> float:
        """Compute heat score from profile."""
        tms = profile.tms or 0
        ccs = profile.ccs or 0
        eis = profile.eis_offensive or 0

        return (
            self.tms * tms +
            self.ccs * ccs +
            self.eis_offensive * eis
        )


class LifecycleRules(BaseModel):
    """Rules for lifecycle state transitions."""
    # Emerging -> Validating
    emerging_to_validating_tms_threshold: float = 85
    emerging_to_validating_ccs_threshold: float = 50
    emerging_to_validating_weeks: int = 3

    # Validating -> Establishing
    validating_to_establishing_eis_offensive: float = 60
    validating_to_establishing_eis_defensive: float = 80

    # Establishing -> Mainstream
    establishing_to_mainstream_eis_stable_weeks: int = 4


class AlertThresholds(BaseModel):
    """Thresholds for alert detection."""
    # Alpha Zone
    alpha_tms_min: float = 90
    alpha_ccs_max: float = 30
    alpha_weeks_required: int = 2

    # Hype Zone
    hype_ccs_min: float = 90
    hype_tms_max: float = 30

    # Enterprise Pull
    enterprise_eis_delta_threshold: float = 20  # EIS_offensive delta

    # Disruption Pressure
    disruption_eis_defensive_min: float = 85


class BucketAnalysisConfig(BaseModel):
    """Master configuration for bucket analysis."""
    heat_weights: HeatWeights = Field(default_factory=HeatWeights)
    lifecycle_rules: LifecycleRules = Field(default_factory=LifecycleRules)
    alert_thresholds: AlertThresholds = Field(default_factory=AlertThresholds)

    # Time settings
    weeks_of_history: int = 12        # How many weeks to keep
    min_entities_for_score: int = 3   # Min entities to score a bucket


# =============================================================================
# Helper Functions
# =============================================================================

def get_week_bounds(ref_date: date) -> tuple:
    """Get Monday and Sunday for the week containing ref_date."""
    # Monday is 0, Sunday is 6
    monday = ref_date - timedelta(days=ref_date.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def compute_percentile(value: float, all_values: List[float]) -> float:
    """
    Compute percentile of value within all_values.

    Returns 0-100 where 100 means value is highest.
    """
    if not all_values:
        return 50.0

    sorted_values = sorted(all_values)
    n = len(sorted_values)

    # Count how many values are below
    below = sum(1 for v in sorted_values if v < value)

    percentile = (below / n) * 100
    return round(percentile, 1)


from datetime import timedelta
