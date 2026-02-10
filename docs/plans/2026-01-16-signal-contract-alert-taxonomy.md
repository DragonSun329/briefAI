# Signal Contract & Alert Cause Taxonomy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Lock down the signal contract (value/confidence/coverage/freshness/missing_reason) and add explicit alert cause taxonomy so the UI trust indicators are meaningful and low-coverage signals don't trigger false alerts.

**Architecture:** Extend `SignalMetadata` with strict schema validation, add `AlertCause` enum for cause taxonomy, update alert engine to ignore low-coverage "lows", and update UI to show "low because coverage is low" explicitly.

**Tech Stack:** Python dataclasses, Pydantic models, SQLite (via alert_store), Streamlit UI

---

## Task 1: Define Strict Signal Value Schema

**Files:**
- Modify: `utils/bucket_models.py:88-141` (SignalMetadata class)
- Test: `tests/test_signal_contract.py`

Extend `SignalMetadata` to enforce the strict contract and add `missing_reason`.

**Step 1: Write the failing test**

Create `tests/test_signal_contract.py`:

```python
"""Tests for signal contract enforcement."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.bucket_models import SignalMetadata, MissingReason, SignalQuality


class TestSignalMetadata:
    """Tests for SignalMetadata contract."""

    def test_complete_signal(self):
        """Complete signal with all fields."""
        meta = SignalMetadata(
            value=75.0,
            confidence=0.85,
            coverage=0.9,
            freshness_hours=24,
            sources=["github", "huggingface"],
        )
        assert meta.value == 75.0
        assert meta.is_valid is True
        assert meta.missing_reason is None
        assert meta.quality == SignalQuality.HIGH

    def test_low_coverage_signal(self):
        """Low coverage signal should be marked as insufficient."""
        meta = SignalMetadata(
            value=25.0,
            confidence=0.3,
            coverage=0.2,
            freshness_hours=48,
        )
        assert meta.is_valid is True
        assert meta.quality == SignalQuality.LOW
        assert meta.coverage < 0.6

    def test_missing_signal(self):
        """Missing signal should have missing_reason."""
        meta = SignalMetadata(
            value=None,
            missing_reason=MissingReason.NO_DATA,
        )
        assert meta.is_valid is False
        assert meta.missing_reason == MissingReason.NO_DATA

    def test_stale_signal(self):
        """Stale signal should be marked."""
        meta = SignalMetadata(
            value=50.0,
            confidence=0.7,
            coverage=0.8,
            freshness_hours=200,  # > 168 hours stale threshold
        )
        assert meta.is_stale is True
        assert meta.quality == SignalQuality.MEDIUM

    def test_contributors_tracked(self):
        """Contributors should be stored."""
        meta = SignalMetadata(
            value=80.0,
            confidence=0.9,
            coverage=0.95,
            freshness_hours=12,
            contributors=[
                {"entity": "langchain/langchain", "contribution": 0.3},
                {"entity": "vllm-project/vllm", "contribution": 0.25},
            ],
        )
        assert len(meta.contributors) == 2
        assert meta.contributors[0]["entity"] == "langchain/langchain"


class TestSignalQuality:
    """Tests for signal quality classification."""

    def test_high_quality(self):
        """High quality: confidence >= 0.8 AND coverage >= 0.6."""
        meta = SignalMetadata(value=50.0, confidence=0.85, coverage=0.75)
        assert meta.quality == SignalQuality.HIGH

    def test_medium_quality(self):
        """Medium quality: confidence >= 0.5 OR coverage >= 0.4."""
        meta = SignalMetadata(value=50.0, confidence=0.6, coverage=0.5)
        assert meta.quality == SignalQuality.MEDIUM

    def test_low_quality(self):
        """Low quality: confidence < 0.5 AND coverage < 0.4."""
        meta = SignalMetadata(value=50.0, confidence=0.3, coverage=0.2)
        assert meta.quality == SignalQuality.LOW

    def test_insufficient_coverage(self):
        """Insufficient coverage should flag as unreliable."""
        meta = SignalMetadata(value=15.0, confidence=0.3, coverage=0.15)
        assert meta.is_coverage_insufficient is True
        assert meta.get_display_reason() == "low coverage (15%)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_signal_contract.py -v`
Expected: FAIL with "cannot import name 'MissingReason'"

**Step 3: Write implementation**

Modify `utils/bucket_models.py` - add enums and extend SignalMetadata:

```python
# Add after AlertSeverity enum (around line 82):

class MissingReason(str, Enum):
    """Reason why a signal value is missing or unreliable."""
    NO_DATA = "no_data"                     # No sources returned data
    SCRAPER_FAILURE = "scraper_failure"     # Scraper/API error
    RATE_LIMITED = "rate_limited"           # API rate limit hit
    STALE_DATA = "stale_data"               # Data too old to use
    INSUFFICIENT_COVERAGE = "insufficient_coverage"  # Coverage < threshold
    PLACEHOLDER = "placeholder"             # Inferred/estimated value


class SignalQuality(str, Enum):
    """Quality tier for signal reliability."""
    HIGH = "high"       # confidence >= 0.8 AND coverage >= 0.6
    MEDIUM = "medium"   # confidence >= 0.5 OR coverage >= 0.4
    LOW = "low"         # Below medium thresholds
    INVALID = "invalid" # Missing or unusable


# Modify SignalMetadata class (replace lines 88-141):

class SignalMetadata(BaseModel):
    """
    Per-signal metadata for robustness tracking.

    STRICT CONTRACT:
    - value: The score (0-100 percentile), or None if missing
    - confidence: 0-1, epistemic ("how sure are we this reflects reality?")
    - coverage: 0-1, "how much data did we actually see?"
    - freshness_hours: Age of data in hours
    - contributors: List of entities that contributed to this score
    - missing_reason: If value is None or unreliable, why?
    """
    # Core value
    value: Optional[float] = None
    raw_value: Optional[float] = None

    # Confidence (epistemic)
    confidence: float = 0.5

    # Coverage (how much data)
    coverage: float = 0.0
    entity_count: int = 0
    expected_baseline: int = 10

    # Freshness
    freshness_hours: float = 0.0
    last_updated: Optional[datetime] = None

    # Contributors (what entities drove this score)
    contributors: List[Dict[str, Any]] = Field(default_factory=list)

    # Missing reason (if value is None or unreliable)
    missing_reason: Optional[MissingReason] = None

    # Legacy fields (keep for compatibility)
    mapping_confidence: float = 0.8
    stability: float = 0.8
    ewma_value: Optional[float] = None
    raw_unsmoothed: Optional[float] = None
    is_smoothed: bool = False
    sources: List[str] = Field(default_factory=list)
    source_failures: List[str] = Field(default_factory=list)
    percentile_basis: int = 0

    # Thresholds (configurable)
    COVERAGE_THRESHOLD: ClassVar[float] = 0.6
    CONFIDENCE_HIGH: ClassVar[float] = 0.8
    CONFIDENCE_MEDIUM: ClassVar[float] = 0.5
    STALE_HOURS: ClassVar[float] = 168.0  # 7 days

    @property
    def is_valid(self) -> bool:
        """True if signal has a usable value."""
        return self.value is not None and self.missing_reason is None

    @property
    def is_stale(self) -> bool:
        """True if data is older than stale threshold."""
        return self.freshness_hours > self.STALE_HOURS

    @property
    def is_coverage_insufficient(self) -> bool:
        """True if coverage is below threshold for reliable scoring."""
        return self.coverage < self.COVERAGE_THRESHOLD

    @property
    def quality(self) -> SignalQuality:
        """Compute quality tier based on confidence and coverage."""
        if not self.is_valid:
            return SignalQuality.INVALID
        if self.confidence >= self.CONFIDENCE_HIGH and self.coverage >= self.COVERAGE_THRESHOLD:
            return SignalQuality.HIGH
        if self.confidence >= self.CONFIDENCE_MEDIUM or self.coverage >= 0.4:
            return SignalQuality.MEDIUM
        return SignalQuality.LOW

    def get_display_reason(self) -> Optional[str]:
        """Get human-readable reason for low quality or missing data."""
        if self.missing_reason:
            return {
                MissingReason.NO_DATA: "no data available",
                MissingReason.SCRAPER_FAILURE: "data source error",
                MissingReason.RATE_LIMITED: "API rate limited",
                MissingReason.STALE_DATA: "data too old",
                MissingReason.INSUFFICIENT_COVERAGE: f"low coverage ({self.coverage:.0%})",
                MissingReason.PLACEHOLDER: "estimated value",
            }.get(self.missing_reason, "unknown issue")
        if self.is_coverage_insufficient:
            return f"low coverage ({self.coverage:.0%})"
        if self.is_stale:
            return f"stale data ({self.freshness_hours:.0f}h old)"
        return None

    def compute_confidence(self) -> float:
        """Compute overall confidence from components."""
        coverage_factor = min(self.coverage, 1.0) * 0.4
        stability_factor = self.stability * 0.3
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_signal_contract.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add utils/bucket_models.py tests/test_signal_contract.py
git commit -m "feat: add strict signal contract with MissingReason and SignalQuality

- Add MissingReason enum for explicit missing data tracking
- Add SignalQuality enum (HIGH, MEDIUM, LOW, INVALID)
- Extend SignalMetadata with freshness_hours, contributors, missing_reason
- Add is_valid, is_stale, is_coverage_insufficient properties
- Add get_display_reason() for UI-friendly explanations
- Add COVERAGE_THRESHOLD constant (0.6)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Define Alert Cause Taxonomy

**Files:**
- Modify: `utils/bucket_models.py:60-75` (add AlertCause enum)
- Modify: `utils/bucket_models.py:525-627` (extend BucketAlert)
- Test: `tests/test_alert_taxonomy.py`

Add explicit cause taxonomy and tracking fields to alerts.

**Step 1: Write the failing test**

Create `tests/test_alert_taxonomy.py`:

```python
"""Tests for alert cause taxonomy."""

import pytest
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.bucket_models import (
    BucketAlert,
    AlertType,
    AlertCause,
    AlertInterpretation,
    AlertSeverity,
)


class TestAlertCause:
    """Tests for alert cause enum."""

    def test_cause_values(self):
        """All cause types exist."""
        assert AlertCause.DIVERGENCE.value == "divergence"
        assert AlertCause.INFLECTION.value == "inflection"
        assert AlertCause.REGIME_SHIFT.value == "regime_shift"
        assert AlertCause.DATA_HEALTH.value == "data_health"


class TestAlertWithCause:
    """Tests for alerts with cause tracking."""

    def test_alert_with_cause(self):
        """Alert stores cause and features used."""
        alert = BucketAlert(
            bucket_id="ai-agents",
            bucket_name="Agent Frameworks",
            week_start=date(2026, 1, 13),
            alert_type=AlertType.ALPHA_ZONE,
            interpretation=AlertInterpretation.OPPORTUNITY,
            cause=AlertCause.DIVERGENCE,
            trigger_rule_id="alpha_zone_v1",
            features_used=["tms_percentile", "ccs_percentile", "tms_coverage"],
            why_now="TMS crossed p90 AND CCS < p30 AND coverage > 0.7",
            trigger_scores={"tms": 92, "ccs": 28},
            threshold_used="TMS >= 90, CCS <= 30",
            divergence_magnitude=64,
            rationale="High technical momentum with low capital conviction",
            first_detected=date(2026, 1, 6),
        )

        assert alert.cause == AlertCause.DIVERGENCE
        assert alert.trigger_rule_id == "alpha_zone_v1"
        assert "tms_percentile" in alert.features_used
        assert "p90" in alert.why_now

    def test_data_health_alert(self):
        """Data health alerts track source failures."""
        alert = BucketAlert(
            bucket_id="ai-agents",
            bucket_name="Agent Frameworks",
            week_start=date(2026, 1, 13),
            alert_type=AlertType.DATA_HEALTH,
            interpretation=AlertInterpretation.SIGNAL,
            cause=AlertCause.DATA_HEALTH,
            trigger_rule_id="coverage_drop",
            features_used=["tms_coverage", "github_api_status"],
            why_now="TMS coverage dropped from 0.9 to 0.3 due to GitHub API failure",
            trigger_scores={"tms_coverage": 0.3, "tms_coverage_prev": 0.9},
            threshold_used="coverage_delta > 0.5",
            divergence_magnitude=0,
            rationale="GitHub API returning 503 errors",
            first_detected=date(2026, 1, 13),
        )

        assert alert.cause == AlertCause.DATA_HEALTH
        assert "coverage dropped" in alert.why_now

    def test_inflection_alert(self):
        """Inflection alerts track velocity changes."""
        alert = BucketAlert(
            bucket_id="ai-coding",
            bucket_name="AI Coding Tools",
            week_start=date(2026, 1, 13),
            alert_type=AlertType.ROTATION,
            interpretation=AlertInterpretation.SIGNAL,
            cause=AlertCause.INFLECTION,
            trigger_rule_id="velocity_flip",
            features_used=["tms_velocity_4w", "tms_acceleration"],
            why_now="TMS 4-week velocity flipped from +12 to -8 (deceleration)",
            trigger_scores={"tms_velocity_4w": -8, "tms_velocity_prev": 12},
            threshold_used="velocity_sign_change AND magnitude > 5",
            divergence_magnitude=20,
            rationale="Technical momentum decelerating after rapid growth",
            first_detected=date(2026, 1, 13),
        )

        assert alert.cause == AlertCause.INFLECTION
        assert "velocity flipped" in alert.why_now


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_alert_taxonomy.py -v`
Expected: FAIL with "cannot import name 'AlertCause'"

**Step 3: Write implementation**

Modify `utils/bucket_models.py`:

```python
# Add after AlertInterpretation enum (around line 75):

class AlertCause(str, Enum):
    """Root cause category for why an alert was triggered."""
    DIVERGENCE = "divergence"       # High/low signal divergence (e.g., TMS high, CCS low)
    INFLECTION = "inflection"       # Velocity/acceleration sign change
    REGIME_SHIFT = "regime_shift"   # Macro regime change affecting multiple buckets
    DATA_HEALTH = "data_health"     # Coverage drop, scraper failure, stale data


# Add to AlertType enum (after existing types):
    DATA_HEALTH = "data_health"     # Pipeline/data quality issue


# Modify BucketAlert class (add these fields after severity):

class BucketAlert(BaseModel):
    """
    Divergence alert for a trend bucket.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    bucket_id: str
    bucket_name: str
    week_start: date

    # Alert details
    alert_type: AlertType
    interpretation: AlertInterpretation
    severity: AlertSeverity = AlertSeverity.INFO

    # NEW: Cause taxonomy
    cause: AlertCause = AlertCause.DIVERGENCE
    trigger_rule_id: str = ""                    # e.g., "alpha_zone_v1"
    features_used: List[str] = Field(default_factory=list)  # ["tms_percentile", "ccs_percentile"]
    why_now: str = ""                            # "TMS crossed p90 AND CCS < p30"

    # Trigger details
    trigger_scores: Dict[str, float]
    threshold_used: str
    divergence_magnitude: float
    z_score: Optional[float] = None
    velocity_percentile: Optional[float] = None

    # Evidence
    rationale: str
    supporting_entities: List[str] = Field(default_factory=list)
    evidence_snippets: List[str] = Field(default_factory=list)
    evidence_count: int = 0

    # Signal confidence
    signal_confidence: float = 0.8

    # NEW: Coverage tracking for filtering
    min_signal_coverage: float = 1.0  # Minimum coverage of signals that triggered alert

    # Action hint
    action_hint: Optional[str] = None

    # Persistence
    first_detected: date
    weeks_persistent: int = 1
    resolved_at: Optional[date] = None

    # Cooldown
    last_shown: Optional[date] = None
    cooldown_days: int = 7
    previous_severity: Optional[AlertSeverity] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)

    def is_coverage_valid(self, threshold: float = 0.6) -> bool:
        """Check if alert has sufficient coverage to be actionable."""
        return self.min_signal_coverage >= threshold

    # ... rest of existing methods unchanged
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_alert_taxonomy.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add utils/bucket_models.py tests/test_alert_taxonomy.py
git commit -m "feat: add alert cause taxonomy with trigger tracking

- Add AlertCause enum: DIVERGENCE, INFLECTION, REGIME_SHIFT, DATA_HEALTH
- Add DATA_HEALTH alert type for pipeline issues
- Add trigger_rule_id, features_used, why_now to BucketAlert
- Add min_signal_coverage for filtering low-coverage alerts
- Add is_coverage_valid() method

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Update Alert Engine to Ignore Low-Coverage Alerts

**Files:**
- Modify: `utils/bucket_alerts.py` (alert generation logic)
- Test: `tests/test_alert_coverage_filter.py`

Add coverage validation to alert generation so low-coverage "lows" don't trigger false alerts.

**Step 1: Write the failing test**

Create `tests/test_alert_coverage_filter.py`:

```python
"""Tests for alert coverage filtering."""

import pytest
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.bucket_models import BucketProfile, SignalMetadata, AlertType


class TestAlertCoverageFiltering:
    """Tests for filtering alerts by coverage."""

    def test_low_coverage_low_value_not_alert(self):
        """Low value with low coverage should NOT trigger alpha_zone alert."""
        # Create profile with low CCS but low coverage
        profile = BucketProfile(
            bucket_id="test-bucket",
            bucket_name="Test Bucket",
            week_start=date(2026, 1, 13),
            tms=92,  # High TMS
            ccs=15,  # Low CCS - but...
            signal_metadata={
                "tms": SignalMetadata(
                    value=92,
                    confidence=0.9,
                    coverage=0.8,  # Good coverage
                ).model_dump(),
                "ccs": SignalMetadata(
                    value=15,
                    confidence=0.2,
                    coverage=0.15,  # LOW coverage - not reliable!
                ).model_dump(),
            },
        )

        # When coverage is below threshold, the "low" value is not trustworthy
        from utils.bucket_alerts import should_trigger_alert, COVERAGE_THRESHOLD

        should_alert, reason = should_trigger_alert(
            profile,
            AlertType.ALPHA_ZONE,
            coverage_threshold=COVERAGE_THRESHOLD,
        )

        assert should_alert is False
        assert "insufficient coverage" in reason.lower()

    def test_good_coverage_triggers_alert(self):
        """Proper coverage should allow alert to trigger."""
        profile = BucketProfile(
            bucket_id="test-bucket",
            bucket_name="Test Bucket",
            week_start=date(2026, 1, 13),
            tms=92,
            ccs=25,
            signal_metadata={
                "tms": SignalMetadata(value=92, confidence=0.9, coverage=0.85).model_dump(),
                "ccs": SignalMetadata(value=25, confidence=0.7, coverage=0.7).model_dump(),
            },
        )

        from utils.bucket_alerts import should_trigger_alert

        should_alert, reason = should_trigger_alert(profile, AlertType.ALPHA_ZONE)

        assert should_alert is True
        assert "alpha zone" in reason.lower()

    def test_data_health_alert_on_coverage_drop(self):
        """Coverage drop should trigger DATA_HEALTH alert."""
        profile = BucketProfile(
            bucket_id="test-bucket",
            bucket_name="Test Bucket",
            week_start=date(2026, 1, 13),
            tms=None,  # Missing
            ccs=50,
            signal_metadata={
                "tms": SignalMetadata(
                    value=None,
                    coverage=0.1,
                    missing_reason="scraper_failure",
                ).model_dump(),
            },
        )

        from utils.bucket_alerts import check_data_health_alert

        alert = check_data_health_alert(profile, previous_coverage={"tms": 0.9})

        assert alert is not None
        assert alert.alert_type == AlertType.DATA_HEALTH
        assert "coverage" in alert.why_now.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_alert_coverage_filter.py -v`
Expected: FAIL with "cannot import name 'should_trigger_alert'"

**Step 3: Write implementation**

First, check if `utils/bucket_alerts.py` exists. If it does, modify it. If not, create it.

Add to `utils/bucket_alerts.py`:

```python
"""
Bucket alert generation with coverage validation.

Key principle: Low coverage = insufficient data = not a real "low" score.
"""

from typing import Tuple, Optional, Dict, Any
from datetime import date

from utils.bucket_models import (
    BucketProfile,
    BucketAlert,
    AlertType,
    AlertCause,
    AlertInterpretation,
    AlertSeverity,
    SignalMetadata,
    MissingReason,
)

# Coverage threshold below which a "low" score is not trustworthy
COVERAGE_THRESHOLD = 0.6


def should_trigger_alert(
    profile: BucketProfile,
    alert_type: AlertType,
    coverage_threshold: float = COVERAGE_THRESHOLD,
) -> Tuple[bool, str]:
    """
    Check if an alert should trigger, accounting for coverage.

    Returns:
        (should_trigger: bool, reason: str)
    """
    # Get signal metadata
    meta = profile.signal_metadata or {}

    if alert_type == AlertType.ALPHA_ZONE:
        # Alpha Zone: High TMS (>= 90), Low CCS (<= 30)
        tms = profile.tms
        ccs = profile.ccs
        tms_meta = SignalMetadata(**meta.get("tms", {})) if meta.get("tms") else SignalMetadata()
        ccs_meta = SignalMetadata(**meta.get("ccs", {})) if meta.get("ccs") else SignalMetadata()

        # Check thresholds
        if tms is None or tms < 90:
            return False, "TMS not in alpha zone range"
        if ccs is None or ccs > 30:
            return False, "CCS not in alpha zone range"

        # CRITICAL: Check coverage on the "low" signal
        # A low CCS with low coverage is NOT a reliable signal
        if ccs_meta.coverage < coverage_threshold:
            return False, f"CCS has insufficient coverage ({ccs_meta.coverage:.0%})"

        # Also check TMS coverage for completeness
        if tms_meta.coverage < coverage_threshold:
            return False, f"TMS has insufficient coverage ({tms_meta.coverage:.0%})"

        return True, f"Alpha zone detected: TMS={tms}, CCS={ccs}"

    elif alert_type == AlertType.HYPE_ZONE:
        # Hype Zone: High NAS (>= 85), Low TMS (<= 40)
        nas = profile.nas
        tms = profile.tms
        nas_meta = SignalMetadata(**meta.get("nas", {})) if meta.get("nas") else SignalMetadata()
        tms_meta = SignalMetadata(**meta.get("tms", {})) if meta.get("tms") else SignalMetadata()

        if nas is None or nas < 85:
            return False, "NAS not in hype zone range"
        if tms is None or tms > 40:
            return False, "TMS not in hype zone range"

        # Check coverage on the "low" signal (TMS)
        if tms_meta.coverage < coverage_threshold:
            return False, f"TMS has insufficient coverage ({tms_meta.coverage:.0%})"

        return True, f"Hype zone detected: NAS={nas}, TMS={tms}"

    # Add other alert types...

    return False, "Unknown alert type"


def check_data_health_alert(
    profile: BucketProfile,
    previous_coverage: Dict[str, float],
) -> Optional[BucketAlert]:
    """
    Check for data health issues (coverage drops, scraper failures).

    Args:
        profile: Current bucket profile
        previous_coverage: Coverage values from previous week

    Returns:
        BucketAlert if data health issue detected, None otherwise
    """
    meta = profile.signal_metadata or {}
    issues = []
    features_used = []

    for signal in ["tms", "ccs", "nas", "eis"]:
        signal_meta = meta.get(signal, {})
        if isinstance(signal_meta, dict):
            signal_meta = SignalMetadata(**signal_meta)
        else:
            continue

        current_cov = signal_meta.coverage
        prev_cov = previous_coverage.get(signal, 0.0)

        # Check for coverage drop > 50%
        if prev_cov > 0.5 and current_cov < prev_cov * 0.5:
            issues.append(f"{signal.upper()} coverage dropped from {prev_cov:.0%} to {current_cov:.0%}")
            features_used.append(f"{signal}_coverage")

        # Check for missing reason
        if signal_meta.missing_reason:
            issues.append(f"{signal.upper()}: {signal_meta.missing_reason}")
            features_used.append(f"{signal}_missing_reason")

    if not issues:
        return None

    return BucketAlert(
        bucket_id=profile.bucket_id,
        bucket_name=profile.bucket_name,
        week_start=profile.week_start,
        alert_type=AlertType.DATA_HEALTH,
        interpretation=AlertInterpretation.SIGNAL,
        severity=AlertSeverity.WARN,
        cause=AlertCause.DATA_HEALTH,
        trigger_rule_id="coverage_drop",
        features_used=features_used,
        why_now="; ".join(issues),
        trigger_scores={f"{s}_coverage": previous_coverage.get(s, 0) for s in ["tms", "ccs", "nas", "eis"]},
        threshold_used="coverage_delta > 50%",
        divergence_magnitude=0,
        rationale=f"Data quality issue: {'; '.join(issues)}",
        first_detected=profile.week_start,
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_alert_coverage_filter.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add utils/bucket_alerts.py tests/test_alert_coverage_filter.py
git commit -m "feat: add coverage validation to alert engine

- Add should_trigger_alert() with coverage threshold check
- Low coverage 'lows' no longer trigger false alerts
- Add check_data_health_alert() for pipeline issues
- Add COVERAGE_THRESHOLD constant (0.6)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Update UI to Show Coverage Explanation

**Files:**
- Modify: `modules/components/explain_drawer.py` (add coverage warning)
- Modify: `utils/dashboard_helpers.py` (add coverage badge helper)
- Test: `tests/test_coverage_ui.py`

Update the UI to explicitly show "low because coverage is low" instead of treating it as a real low score.

**Step 1: Write the failing test**

Create `tests/test_coverage_ui.py`:

```python
"""Tests for coverage-aware UI helpers."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.dashboard_helpers import get_signal_display_info, CoverageWarning


class TestSignalDisplayInfo:
    """Tests for signal display with coverage context."""

    def test_high_coverage_signal(self):
        """High coverage signal displays normally."""
        info = get_signal_display_info(
            value=85,
            confidence=0.9,
            coverage=0.8,
        )
        assert info.display_value == "85"
        assert info.warning is None
        assert info.is_reliable is True

    def test_low_coverage_low_value(self):
        """Low coverage with low value shows warning."""
        info = get_signal_display_info(
            value=25,
            confidence=0.3,
            coverage=0.2,
        )
        assert info.display_value == "25"
        assert info.warning == CoverageWarning.INSUFFICIENT_COVERAGE
        assert info.warning_text == "Low due to insufficient data (20% coverage)"
        assert info.is_reliable is False

    def test_missing_signal(self):
        """Missing signal shows N/A with reason."""
        info = get_signal_display_info(
            value=None,
            confidence=0.0,
            coverage=0.0,
            missing_reason="scraper_failure",
        )
        assert info.display_value == "N/A"
        assert info.warning == CoverageWarning.NO_DATA
        assert "data source error" in info.warning_text.lower()


class TestCoverageBadge:
    """Tests for coverage badge display."""

    def test_full_coverage_badge(self):
        """Full coverage gets green badge."""
        from utils.dashboard_helpers import get_coverage_badge
        badge = get_coverage_badge(0.9)
        assert badge["label"] == "GOOD"
        assert badge["color"] == "#27ae60"

    def test_low_coverage_badge(self):
        """Low coverage gets red badge with warning."""
        from utils.dashboard_helpers import get_coverage_badge
        badge = get_coverage_badge(0.2)
        assert badge["label"] == "LOW"
        assert badge["color"] == "#e74c3c"
        assert badge["show_warning"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_coverage_ui.py -v`
Expected: FAIL with "cannot import name 'get_signal_display_info'"

**Step 3: Write implementation**

Add to `utils/dashboard_helpers.py`:

```python
# Add after existing imports:
from enum import Enum
from dataclasses import dataclass


class CoverageWarning(str, Enum):
    """Warning types for coverage issues."""
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    STALE_DATA = "stale_data"
    NO_DATA = "no_data"
    SCRAPER_FAILURE = "scraper_failure"


@dataclass
class SignalDisplayInfo:
    """Display information for a signal with coverage context."""
    display_value: str
    is_reliable: bool
    warning: Optional[CoverageWarning] = None
    warning_text: Optional[str] = None
    coverage_pct: float = 0.0
    confidence_label: str = "unknown"


def get_signal_display_info(
    value: Optional[float],
    confidence: float,
    coverage: float,
    missing_reason: Optional[str] = None,
    coverage_threshold: float = 0.6,
) -> SignalDisplayInfo:
    """
    Get display info for a signal value with coverage context.

    Key behavior: Low value + low coverage = "low due to insufficient data"
    """
    # Handle missing values
    if value is None:
        warning = CoverageWarning.NO_DATA
        if missing_reason == "scraper_failure":
            warning = CoverageWarning.SCRAPER_FAILURE
            warning_text = "Data source error"
        else:
            warning_text = "No data available"

        return SignalDisplayInfo(
            display_value="N/A",
            is_reliable=False,
            warning=warning,
            warning_text=warning_text,
            coverage_pct=coverage,
            confidence_label="none",
        )

    # Check coverage
    is_reliable = coverage >= coverage_threshold
    warning = None
    warning_text = None

    if not is_reliable:
        warning = CoverageWarning.INSUFFICIENT_COVERAGE
        warning_text = f"Low due to insufficient data ({coverage:.0%} coverage)"

    # Confidence label
    if confidence >= 0.7:
        conf_label = "high"
    elif confidence >= 0.4:
        conf_label = "medium"
    else:
        conf_label = "low"

    return SignalDisplayInfo(
        display_value=f"{value:.0f}",
        is_reliable=is_reliable,
        warning=warning,
        warning_text=warning_text,
        coverage_pct=coverage,
        confidence_label=conf_label,
    )


def get_coverage_badge(coverage: float) -> Dict[str, Any]:
    """
    Get badge display info for coverage level.
    """
    if coverage >= 0.8:
        return {
            "label": "GOOD",
            "color": "#27ae60",
            "bg_color": "rgba(39, 174, 96, 0.1)",
            "show_warning": False,
        }
    elif coverage >= 0.6:
        return {
            "label": "OK",
            "color": "#f39c12",
            "bg_color": "rgba(243, 156, 18, 0.1)",
            "show_warning": False,
        }
    else:
        return {
            "label": "LOW",
            "color": "#e74c3c",
            "bg_color": "rgba(231, 76, 60, 0.1)",
            "show_warning": True,
        }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_coverage_ui.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add utils/dashboard_helpers.py tests/test_coverage_ui.py
git commit -m "feat: add coverage-aware signal display helpers

- Add CoverageWarning enum for warning types
- Add SignalDisplayInfo dataclass for display context
- Add get_signal_display_info() with coverage validation
- Add get_coverage_badge() for coverage badges
- Low value + low coverage now explicitly shows warning

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Update Explain Drawer to Show Coverage Warnings

**Files:**
- Modify: `modules/components/explain_drawer.py` (show coverage warnings)
- Test: Add test to `tests/test_explain_drawer.py`

Update the explain drawer to display coverage warnings for low-coverage signals.

**Step 1: Write the failing test**

Add to `tests/test_explain_drawer.py`:

```python
class TestCoverageWarnings:
    """Tests for coverage warning display."""

    def test_low_coverage_warning_displayed(self):
        """Low coverage signals show warning."""
        profile = {
            "bucket_id": "test",
            "bucket_name": "Test",
            "tms": 25,  # Low value
            "signal_metadata": {
                "tms": {
                    "value": 25,
                    "coverage": 0.15,  # Low coverage
                    "confidence": 0.2,
                }
            }
        }

        drawer_data = build_explain_drawer_data(profile, {})

        # The sparkline should have a warning
        tms_spark = next((s for s in drawer_data.sparklines if s.signal_name == "tms"), None)
        assert tms_spark is not None
        assert tms_spark.coverage_warning is not None
        assert "insufficient" in tms_spark.coverage_warning.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_explain_drawer.py::TestCoverageWarnings -v`
Expected: FAIL with "AttributeError: 'SparklineData' object has no attribute 'coverage_warning'"

**Step 3: Modify SparklineData and build function**

In `modules/components/explain_drawer.py`:

```python
@dataclass
class SparklineData:
    """Data for a single signal sparkline."""
    signal_name: str
    display_name: str
    current_value: float
    delta: float
    coverage: float
    history: List[float]
    sparkline_chars: str
    trend: str
    # NEW: Coverage warning
    coverage_warning: Optional[str] = None
    is_reliable: bool = True


# In build_explain_drawer_data, modify the sparkline creation:

            # Check if coverage is sufficient
            coverage_warning = None
            is_reliable = True
            if coverage < 0.6:
                coverage_warning = f"Insufficient data ({coverage:.0%} coverage)"
                is_reliable = False

            sparklines.append(SparklineData(
                signal_name=signal_key,
                display_name=SIGNAL_DISPLAY_NAMES.get(signal_key, signal_key.upper()),
                current_value=current,
                delta=spark_data["delta"],
                coverage=coverage,
                history=history if history else [current],
                sparkline_chars=spark_data["sparkline_chars"],
                trend=spark_data["trend"],
                coverage_warning=coverage_warning,
                is_reliable=is_reliable,
            ))
```

**Step 4: Update renderer to show warning**

In `ExplainDrawerRenderer.render()`:

```python
            with col1:
                delta_str = f"{'↑' if spark.delta > 0 else '↓' if spark.delta < 0 else '→'}{abs(spark.delta):.0f}"
                # Show warning if coverage is low
                if spark.coverage_warning:
                    st.markdown(
                        f"**{spark.display_name}:** {spark.current_value:.0f} ({delta_str}) "
                        f"⚠️ <span style='color:#e74c3c; font-size:0.8em;'>{spark.coverage_warning}</span>",
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(f"**{spark.display_name}:** {spark.current_value:.0f} ({delta_str})")
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_explain_drawer.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add modules/components/explain_drawer.py tests/test_explain_drawer.py
git commit -m "feat: add coverage warnings to explain drawer

- Add coverage_warning and is_reliable to SparklineData
- Show warning when coverage < 0.6 threshold
- Display warning inline with signal name

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Run Full Integration Test

**Files:**
- Run all new tests
- Verify existing tests still pass

**Step 1: Run all new tests**

```bash
pytest tests/test_signal_contract.py tests/test_alert_taxonomy.py tests/test_alert_coverage_filter.py tests/test_coverage_ui.py tests/test_explain_drawer.py -v
```

Expected: All tests PASS

**Step 2: Run existing tests to verify no regressions**

```bash
pytest tests/test_dashboard_helpers.py tests/test_alert_card.py tests/test_bucket_dashboard_integration.py tests/test_events.py -v
```

Expected: All tests PASS

**Step 3: Commit final integration**

```bash
git add .
git commit -m "test: verify signal contract and alert taxonomy integration

All tests passing:
- Signal contract tests
- Alert taxonomy tests
- Coverage filtering tests
- Coverage UI tests
- Explain drawer tests
- Existing dashboard tests

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

This plan implements:

1. **Strict Signal Contract** - Every signal has value, confidence, coverage, freshness, contributors, missing_reason
2. **Alert Cause Taxonomy** - DIVERGENCE, INFLECTION, REGIME_SHIFT, DATA_HEALTH with trigger_rule_id, features_used, why_now
3. **Coverage Validation** - Alert engine ignores low-coverage "lows" (coverage < 0.6)
4. **UI Explanation** - Dashboard shows "low because coverage is low" explicitly

Key behavior change: **A low CCS with 15% coverage no longer triggers an Alpha Zone alert** because we can't trust the "low" value. Instead, it would trigger a DATA_HEALTH alert if coverage dropped significantly.