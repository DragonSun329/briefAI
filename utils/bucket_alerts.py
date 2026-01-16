"""
Bucket Alert Detector

Detects divergence alerts when bucket subscores diverge significantly:
- Alpha Zone: High TMS, low CCS - hidden gem (devs love it, not funded yet)
- Hype Zone: High CCS, low TMS - vaporware (money chasing story, low adoption)
- Enterprise Pull: EIS offensive rising - incumbents moving, adoption wave coming
- Disruption Pressure: EIS defensive spiking - incumbents scared
- Rotation: TMS decelerating, CCS consolidating - market maturing
- Data Health: Coverage drop, scraper failure, stale data

Key principle: Low coverage = insufficient data = not a real "low" score.
"""

from datetime import date, datetime
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from .bucket_models import (
    BucketProfile, BucketAlert, AlertType, AlertInterpretation,
    AlertThresholds, WeeklySnapshot, AlertSeverity, AlertCause,
    SignalMetadata, MissingReason
)

# Coverage threshold below which a "low" score is not trustworthy
COVERAGE_THRESHOLD = 0.6


class BucketAlertDetector:
    """
    Detects divergence alerts for trend buckets.

    Alerts are triggered when subscores diverge significantly,
    indicating potential opportunities, risks, or market signals.
    """

    def __init__(self, thresholds: Optional[AlertThresholds] = None):
        """
        Initialize detector with alert thresholds.

        Args:
            thresholds: Custom thresholds. Uses defaults if None.
        """
        self.thresholds = thresholds or AlertThresholds()

        # Track alert history for persistence detection
        self._alert_history: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # {bucket_id: {alert_type: weeks_active}}

    def detect_alerts(
        self,
        profiles: List[BucketProfile],
        historical_profiles: Optional[Dict[str, List[BucketProfile]]] = None
    ) -> List[BucketAlert]:
        """
        Detect all alerts for a list of bucket profiles.

        Args:
            profiles: Current week's bucket profiles
            historical_profiles: Optional historical data for delta detection
                Dict mapping bucket_id to list of past profiles

        Returns:
            List of detected BucketAlert objects
        """
        alerts = []

        for profile in profiles:
            bucket_alerts = self._detect_for_bucket(profile, historical_profiles)
            alerts.extend(bucket_alerts)

        # Sort by divergence magnitude
        alerts.sort(key=lambda a: a.divergence_magnitude, reverse=True)

        return alerts

    def _detect_for_bucket(
        self,
        profile: BucketProfile,
        historical: Optional[Dict[str, List[BucketProfile]]] = None
    ) -> List[BucketAlert]:
        """Detect all alerts for a single bucket."""
        alerts = []

        # Get historical data for this bucket
        bucket_history = historical.get(profile.bucket_id, []) if historical else []

        # Alpha Zone
        alpha = self._check_alpha_zone(profile)
        if alpha:
            alerts.append(alpha)

        # Hype Zone
        hype = self._check_hype_zone(profile)
        if hype:
            alerts.append(hype)

        # Enterprise Pull
        enterprise = self._check_enterprise_pull(profile, bucket_history)
        if enterprise:
            alerts.append(enterprise)

        # Disruption Pressure
        disruption = self._check_disruption_pressure(profile)
        if disruption:
            alerts.append(disruption)

        # Rotation
        rotation = self._check_rotation(profile, bucket_history)
        if rotation:
            alerts.append(rotation)

        return alerts

    def _check_alpha_zone(self, profile: BucketProfile) -> Optional[BucketAlert]:
        """
        Check for Alpha Zone (Hidden Gems).

        Condition: High TMS (>90), Low CCS (<30)
        Interpretation: Developers love it but money hasn't arrived yet.
        """
        tms = profile.tms or 0
        ccs = profile.ccs or 0

        if tms >= self.thresholds.alpha_tms_min and ccs <= self.thresholds.alpha_ccs_max:
            # Track persistence
            self._alert_history[profile.bucket_id]["alpha_zone"] += 1
            weeks = self._alert_history[profile.bucket_id]["alpha_zone"]

            if weeks >= self.thresholds.alpha_weeks_required:
                return BucketAlert(
                    bucket_id=profile.bucket_id,
                    bucket_name=profile.bucket_name,
                    week_start=profile.week_start,
                    alert_type=AlertType.ALPHA_ZONE,
                    interpretation=AlertInterpretation.OPPORTUNITY,
                    trigger_scores={"tms": tms, "ccs": ccs},
                    threshold_used=f"TMS >= {self.thresholds.alpha_tms_min}, CCS <= {self.thresholds.alpha_ccs_max}",
                    divergence_magnitude=tms - ccs,
                    rationale=(
                        f"Strong technical momentum (TMS={tms:.0f}th percentile) without "
                        f"commensurate capital conviction (CCS={ccs:.0f}th percentile). "
                        "Developer adoption is outpacing investor attention - potential early opportunity."
                    ),
                    supporting_entities=profile.top_technical_entities,
                    first_detected=profile.week_start,
                    weeks_persistent=weeks,
                )
        else:
            # Reset persistence counter
            self._alert_history[profile.bucket_id]["alpha_zone"] = 0

        return None

    def _check_hype_zone(self, profile: BucketProfile) -> Optional[BucketAlert]:
        """
        Check for Hype Zone (Vaporware).

        Condition: High CCS (>90), Low TMS (<30)
        Interpretation: Money is chasing a story without real adoption.
        """
        tms = profile.tms or 0
        ccs = profile.ccs or 0

        if ccs >= self.thresholds.hype_ccs_min and tms <= self.thresholds.hype_tms_max:
            return BucketAlert(
                bucket_id=profile.bucket_id,
                bucket_name=profile.bucket_name,
                week_start=profile.week_start,
                alert_type=AlertType.HYPE_ZONE,
                interpretation=AlertInterpretation.RISK,
                trigger_scores={"tms": tms, "ccs": ccs},
                threshold_used=f"CCS >= {self.thresholds.hype_ccs_min}, TMS <= {self.thresholds.hype_tms_max}",
                divergence_magnitude=ccs - tms,
                rationale=(
                    f"High capital conviction (CCS={ccs:.0f}th percentile) without "
                    f"corresponding technical adoption (TMS={tms:.0f}th percentile). "
                    "Investment may be ahead of genuine developer/user adoption - hype risk."
                ),
                supporting_entities=profile.top_capital_entities,
                first_detected=profile.week_start,
                weeks_persistent=1,
            )

        return None

    def _check_enterprise_pull(
        self,
        profile: BucketProfile,
        history: List[BucketProfile]
    ) -> Optional[BucketAlert]:
        """
        Check for Enterprise Pull.

        Condition: EIS offensive rising fast with stable TMS
        Interpretation: Incumbents are moving - adoption wave coming.
        """
        eis_off = profile.eis_offensive or 0
        tms = profile.tms or 0

        # Need historical data to detect "rising"
        if not history:
            return None

        # Get last week's EIS offensive
        last_eis = None
        for past in sorted(history, key=lambda p: p.week_start, reverse=True):
            if past.eis_offensive is not None:
                last_eis = past.eis_offensive
                break

        if last_eis is None:
            return None

        eis_delta = eis_off - last_eis

        if eis_delta >= self.thresholds.enterprise_eis_delta_threshold and tms >= 40:
            return BucketAlert(
                bucket_id=profile.bucket_id,
                bucket_name=profile.bucket_name,
                week_start=profile.week_start,
                alert_type=AlertType.ENTERPRISE_PULL,
                interpretation=AlertInterpretation.OPPORTUNITY,
                trigger_scores={
                    "eis_offensive": eis_off,
                    "eis_delta": eis_delta,
                    "tms": tms
                },
                threshold_used=f"EIS_offensive delta >= {self.thresholds.enterprise_eis_delta_threshold}",
                divergence_magnitude=eis_delta,
                rationale=(
                    f"Enterprise offensive signals rising rapidly (+{eis_delta:.0f} percentile points). "
                    f"Current EIS={eis_off:.0f}th percentile with solid technical foundation (TMS={tms:.0f}). "
                    "Incumbents are adopting - enterprise wave may be forming."
                ),
                supporting_entities=profile.top_enterprise_entities,
                first_detected=profile.week_start,
                weeks_persistent=1,
            )

        return None

    def _check_disruption_pressure(self, profile: BucketProfile) -> Optional[BucketAlert]:
        """
        Check for Disruption Pressure.

        Condition: EIS defensive very high (>85)
        Interpretation: Incumbents are scared - risk language spiking.
        """
        eis_def = profile.eis_defensive or 0

        if eis_def >= self.thresholds.disruption_eis_defensive_min:
            return BucketAlert(
                bucket_id=profile.bucket_id,
                bucket_name=profile.bucket_name,
                week_start=profile.week_start,
                alert_type=AlertType.DISRUPTION_PRESSURE,
                interpretation=AlertInterpretation.SIGNAL,
                trigger_scores={"eis_defensive": eis_def},
                threshold_used=f"EIS_defensive >= {self.thresholds.disruption_eis_defensive_min}",
                divergence_magnitude=eis_def,
                rationale=(
                    f"Defensive enterprise signals at {eis_def:.0f}th percentile. "
                    "Incumbents are flagging this area in risk factors and competition sections. "
                    "High disruption pressure - good for challengers, risk for established players."
                ),
                supporting_entities=profile.top_enterprise_entities,
                first_detected=profile.week_start,
                weeks_persistent=1,
            )

        return None

    def _check_rotation(
        self,
        profile: BucketProfile,
        history: List[BucketProfile]
    ) -> Optional[BucketAlert]:
        """
        Check for Rotation/Maturation.

        Condition: TMS decelerating, CCS stable/consolidating
        Interpretation: Market is maturing, winners emerging.
        """
        tms = profile.tms or 0
        ccs = profile.ccs or 0

        if len(history) < 4:  # Need 4 weeks to detect trend
            return None

        # Calculate TMS trend over past 4 weeks
        recent_history = sorted(history, key=lambda p: p.week_start, reverse=True)[:4]
        tms_values = [p.tms for p in recent_history if p.tms is not None]

        if len(tms_values) < 4:
            return None

        # Check if TMS is declining (newer < older)
        tms_declining = all(
            tms_values[i] <= tms_values[i+1]
            for i in range(len(tms_values)-1)
        )

        # Check if CCS is stable (not volatile)
        ccs_values = [p.ccs for p in recent_history if p.ccs is not None]
        if len(ccs_values) >= 4:
            ccs_range = max(ccs_values) - min(ccs_values)
            ccs_stable = ccs_range < 20  # Less than 20 percentile points variance
        else:
            ccs_stable = False

        if tms_declining and ccs_stable and ccs > 50:
            return BucketAlert(
                bucket_id=profile.bucket_id,
                bucket_name=profile.bucket_name,
                week_start=profile.week_start,
                alert_type=AlertType.ROTATION,
                interpretation=AlertInterpretation.NEUTRAL,
                trigger_scores={"tms": tms, "ccs": ccs, "tms_trend": "declining"},
                threshold_used="TMS declining for 4+ weeks, CCS stable",
                divergence_magnitude=tms_values[-1] - tms,  # Total decline
                rationale=(
                    f"Technical momentum decelerating (TMS trend: {tms_values[-1]:.0f} -> {tms:.0f}) "
                    f"while capital remains stable (CCS={ccs:.0f}). "
                    "Market may be maturing - consolidation phase, winners emerging."
                ),
                supporting_entities=profile.top_capital_entities,
                first_detected=profile.week_start,
                weeks_persistent=4,
            )

        return None

    def get_alert_summary(self, alerts: List[BucketAlert]) -> Dict[str, Any]:
        """
        Generate summary statistics for alerts.
        """
        if not alerts:
            return {
                "total": 0,
                "opportunities": 0,
                "risks": 0,
                "signals": 0,
                "by_type": {},
            }

        by_interpretation = defaultdict(list)
        by_type = defaultdict(list)

        for alert in alerts:
            by_interpretation[alert.interpretation.value].append(alert)
            by_type[alert.alert_type.value].append(alert)

        return {
            "total": len(alerts),
            "opportunities": len(by_interpretation.get("opportunity", [])),
            "risks": len(by_interpretation.get("risk", [])),
            "signals": len(by_interpretation.get("signal", [])),
            "by_type": {k: len(v) for k, v in by_type.items()},
            "top_opportunities": [
                {"bucket": a.bucket_name, "type": a.alert_type.value, "magnitude": a.divergence_magnitude}
                for a in by_interpretation.get("opportunity", [])[:5]
            ],
            "top_risks": [
                {"bucket": a.bucket_name, "type": a.alert_type.value, "magnitude": a.divergence_magnitude}
                for a in by_interpretation.get("risk", [])[:5]
            ],
        }


def build_weekly_snapshot(
    profiles: List[BucketProfile],
    alerts: List[BucketAlert],
    week_start: date
) -> WeeklySnapshot:
    """
    Build a complete weekly snapshot from profiles and alerts.
    """
    from datetime import timedelta

    week_end = week_start + timedelta(days=6)

    # Sort profiles by heat
    sorted_profiles = sorted(profiles, key=lambda p: p.heat_score, reverse=True)
    top_heating = [p.bucket_id for p in sorted_profiles[:10]]

    # Count alerts
    opportunities = sum(1 for a in alerts if a.interpretation == AlertInterpretation.OPPORTUNITY)
    risks = sum(1 for a in alerts if a.interpretation == AlertInterpretation.RISK)

    return WeeklySnapshot(
        week_start=week_start,
        week_end=week_end,
        bucket_profiles=profiles,
        alerts=alerts,
        top_heating=top_heating,
        total_buckets_scored=len(profiles),
        total_alerts_fired=len(alerts),
        opportunities_count=opportunities,
        risks_count=risks,
    )


# =============================================================================
# Coverage-Aware Alert Functions
# =============================================================================

def should_trigger_alert(
    profile: BucketProfile,
    alert_type: AlertType,
    coverage_threshold: float = COVERAGE_THRESHOLD,
) -> Tuple[bool, str]:
    """
    Check if an alert should trigger, accounting for coverage.

    Key principle: Low coverage = insufficient data = not a real "low" score.
    A "low" CCS score with 15% coverage means we simply don't have enough
    data to know the true CCS - it's NOT a reliable signal for Alpha Zone.

    Args:
        profile: The bucket profile to check
        alert_type: Type of alert to check for
        coverage_threshold: Minimum coverage required (default 0.6)

    Returns:
        (should_trigger: bool, reason: str)
    """
    meta = profile.signal_metadata or {}

    if alert_type == AlertType.ALPHA_ZONE:
        # Alpha Zone: High TMS (>= 90), Low CCS (<= 30)
        tms = profile.tms
        ccs = profile.ccs
        tms_meta = SignalMetadata(**meta.get("tms", {})) if meta.get("tms") else SignalMetadata()
        ccs_meta = SignalMetadata(**meta.get("ccs", {})) if meta.get("ccs") else SignalMetadata()

        if tms is None or tms < 90:
            return False, "TMS not in alpha zone range"
        if ccs is None or ccs > 30:
            return False, "CCS not in alpha zone range"

        # CRITICAL: Check coverage on the "low" signal
        # A low CCS with low coverage is NOT a reliable "low" - we just don't have data
        if ccs_meta.coverage < coverage_threshold:
            return False, f"CCS has insufficient coverage ({ccs_meta.coverage:.0%})"

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

        # Low TMS with low coverage is NOT reliably low
        if tms_meta.coverage < coverage_threshold:
            return False, f"TMS has insufficient coverage ({tms_meta.coverage:.0%})"

        return True, f"Hype zone detected: NAS={nas}, TMS={tms}"

    return False, "Unknown alert type"


def check_data_health_alert(
    profile: BucketProfile,
    previous_coverage: Dict[str, float],
) -> Optional[BucketAlert]:
    """
    Check for data health issues (coverage drops, scraper failures).

    Triggers DATA_HEALTH alert when:
    - Coverage drops by more than 50% from previous period
    - Signal has a missing_reason indicating scraper failure

    Args:
        profile: Current bucket profile
        previous_coverage: Dict of signal -> previous coverage value
            e.g., {"tms": 0.9, "ccs": 0.8}

    Returns:
        BucketAlert with DATA_HEALTH type if issues found, None otherwise
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


if __name__ == "__main__":
    # Test the alert detector
    print("=" * 60)
    print("BUCKET ALERT DETECTOR TEST")
    print("=" * 60)

    from datetime import date

    detector = BucketAlertDetector()

    # Create test profiles with different patterns
    test_profiles = [
        BucketProfile(
            bucket_id="alpha-test",
            bucket_name="Alpha Zone Test",
            week_start=date.today(),
            tms=92,
            ccs=25,
            eis_offensive=40,
            eis_defensive=30,
        ),
        BucketProfile(
            bucket_id="hype-test",
            bucket_name="Hype Zone Test",
            week_start=date.today(),
            tms=20,
            ccs=95,
            eis_offensive=50,
            eis_defensive=30,
        ),
        BucketProfile(
            bucket_id="disruption-test",
            bucket_name="Disruption Test",
            week_start=date.today(),
            tms=60,
            ccs=60,
            eis_offensive=50,
            eis_defensive=90,
        ),
    ]

    # First detection (alpha needs 2 weeks)
    alerts1 = detector.detect_alerts(test_profiles)
    print(f"First week: {len(alerts1)} alerts")

    # Second detection (alpha should now trigger)
    alerts2 = detector.detect_alerts(test_profiles)
    print(f"Second week: {len(alerts2)} alerts")

    for alert in alerts2:
        print(f"\n  {alert.alert_type.value}: {alert.bucket_name}")
        print(f"    Interpretation: {alert.interpretation.value}")
        print(f"    Magnitude: {alert.divergence_magnitude:.0f}")
        print(f"    Rationale: {alert.rationale[:100]}...")
