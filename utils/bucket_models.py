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
from typing import List, Optional, Dict, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field
import uuid


class LifecycleState(str, Enum):
    """Bucket lifecycle states based on signal patterns."""
    EMERGING = "emerging"           # High TMS, low CCS/EIS
    VALIDATING = "validating"       # TMS + CCS both high
    ESTABLISHING = "establishing"   # CCS + EIS high
    MAINSTREAM = "mainstream"       # All stable, consolidating


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

    created_at: datetime = Field(default_factory=datetime.utcnow)

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

    # Which scores triggered the alert
    trigger_scores: Dict[str, float]  # {"tms": 92, "ccs": 25}
    threshold_used: str               # Description of condition

    # Magnitude of divergence
    divergence_magnitude: float       # Difference between high/low scores

    # Evidence
    rationale: str
    supporting_entities: List[str] = Field(default_factory=list)
    evidence_snippets: List[str] = Field(default_factory=list)

    # Persistence
    first_detected: date
    weeks_persistent: int = 1
    resolved_at: Optional[date] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)


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
