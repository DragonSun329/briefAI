"""
Intelligence Alert Scanner — v2 Alert Generation

Scans entity signals via EntityStore and generates intelligence-focused alerts:

1. STEALTH_SIGNAL: Entity has hiring/patent/GitHub activity but zero news
2. TREND_EMERGENCE: Entity crosses source diversity threshold (new cross-source pattern)
3. SOURCE_DIVERGENCE: Different source types have conflicting sentiment
4. MOMENTUM anomalies: Sudden acceleration or deceleration in mention velocity

This replaces the price-based and TA-based alert patterns from v1.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger

from utils.alert_engine import (
    AlertEngine,
    AlertType,
    AlertSeverity,
    AlertCategory,
    Alert,
)
from utils.entity_store import EntityStore


class IntelligenceAlertScanner:
    """
    Scans entity signals and generates intelligence-focused alerts.

    Usage:
        scanner = IntelligenceAlertScanner()
        alerts = scanner.scan_all()
    """

    def __init__(
        self,
        alert_engine: Optional[AlertEngine] = None,
        entity_store: Optional[EntityStore] = None,
    ):
        self.engine = alert_engine or AlertEngine()
        self.store = entity_store or EntityStore()

    def scan_all(self, top_n: int = 100) -> List[Alert]:
        """
        Run all intelligence scans against top entities.

        Returns list of newly generated alerts.
        """
        alerts: List[Alert] = []

        top_entities = self.store.list_top_entities(limit=top_n)
        entity_names = [e.canonical_name for e in top_entities]

        logger.info(f"Intelligence scan: checking {len(entity_names)} entities")

        for name in entity_names:
            alerts.extend(self._scan_entity(name))

        logger.info(f"Intelligence scan complete: {len(alerts)} new alerts")
        return alerts

    def scan_entity(self, entity_name: str) -> List[Alert]:
        """Scan a single entity for intelligence alerts."""
        return self._scan_entity(entity_name)

    # -------------------------------------------------------------------
    # Individual scanners
    # -------------------------------------------------------------------

    def _scan_entity(self, name: str) -> List[Alert]:
        """Run all checks on a single entity."""
        alerts: List[Alert] = []

        try:
            velocity = self.store.get_mention_velocity(name)
            diversity = self.store.get_source_diversity(name, days=14)
            entity = self.store.find(name)

            entity_id = entity.id if entity else name.lower().replace(" ", "_")

            # 1. Stealth signal check
            stealth = self._check_stealth(name, entity_id, velocity, diversity)
            if stealth:
                alerts.append(stealth)

            # 2. Trend emergence check
            emergence = self._check_trend_emergence(name, entity_id, velocity, diversity)
            if emergence:
                alerts.append(emergence)

            # 3. Momentum anomaly check
            momentum = self._check_momentum_anomaly(name, entity_id, velocity)
            if momentum:
                alerts.append(momentum)

            # 4. Source divergence check
            divergence = self._check_source_divergence(name, entity_id, diversity)
            if divergence:
                alerts.append(divergence)

        except Exception as e:
            logger.debug(f"Intelligence scan failed for {name}: {e}")

        return alerts

    def _check_stealth(
        self,
        name: str,
        entity_id: str,
        velocity: Dict[str, Any],
        diversity: Dict[str, int],
    ) -> Optional[Alert]:
        """
        STEALTH SIGNAL: Entity has non-news signals but zero news coverage.

        This is the killer feature — hiring/patent/GitHub activity that
        media hasn't picked up yet.
        """
        if not diversity:
            return None

        has_news = diversity.get("news", 0) > 0
        if has_news:
            return None  # Not stealth if there's news

        # High-value non-news sources
        high_value = {
            "hiring": diversity.get("hiring", 0),
            "patent": diversity.get("patent", 0),
            "github": diversity.get("github", 0),
            "arxiv": diversity.get("arxiv", 0),
            "huggingface": diversity.get("huggingface", 0),
        }
        active_high_value = {k: v for k, v in high_value.items() if v > 0}

        if len(active_high_value) < 1:
            return None

        total_signals = sum(active_high_value.values())
        if total_signals < 2:
            return None  # Need at least 2 non-news signals

        # Build description
        parts = []
        for source, count in sorted(active_high_value.items(), key=lambda x: x[1], reverse=True):
            parts.append(f"{count} {source}")
        signal_desc = ", ".join(parts)

        severity = AlertSeverity.HIGH if len(active_high_value) >= 2 else AlertSeverity.MEDIUM

        return self.engine.create_alert(
            alert_type=AlertType.STEALTH_SIGNAL,
            entity_id=entity_id,
            entity_name=name,
            severity=severity,
            title=f"Stealth Signal: {name}",
            message=f"{name} has {signal_desc} but zero news coverage in the last 14 days. Potential early signal.",
            data={
                "signal_sources": active_high_value,
                "total_non_news_signals": total_signals,
                "news_count": 0,
            },
            category=AlertCategory.OPPORTUNITY,
            rule_id="intelligence_stealth",
            expires_hours=72,
        )

    def _check_trend_emergence(
        self,
        name: str,
        entity_id: str,
        velocity: Dict[str, Any],
        diversity: Dict[str, int],
    ) -> Optional[Alert]:
        """
        TREND EMERGENCE: Entity crosses source diversity threshold.

        New cross-source pattern = multiple independent source types
        talking about the same entity, especially if it's new or accelerating.
        """
        source_count_14d = velocity.get("source_diversity_30d", 0)  # Using 30d for broader window
        source_count_7d = velocity.get("source_diversity_7d", 0)

        # Need at least 3 source types in 30d to be interesting
        if source_count_14d < 3:
            return None

        # Extra interesting if sources are growing
        is_growing = source_count_7d >= source_count_14d - 1

        # Check if accelerating
        if not velocity.get("accelerating"):
            return None  # Only alert on accelerating entities

        total_mentions = velocity.get("30d", 0)

        severity = AlertSeverity.HIGH if source_count_14d >= 4 else AlertSeverity.MEDIUM

        return self.engine.create_alert(
            alert_type=AlertType.TREND_EMERGENCE,
            entity_id=entity_id,
            entity_name=name,
            severity=severity,
            title=f"Trend Emergence: {name}",
            message=(
                f"{name} is being discussed across {source_count_14d} source types "
                f"({', '.join(velocity.get('source_types_30d', []))}) "
                f"with {total_mentions} total mentions and accelerating velocity."
            ),
            data={
                "source_diversity": source_count_14d,
                "source_types": velocity.get("source_types_30d", []),
                "total_mentions_30d": total_mentions,
                "mentions_7d": velocity.get("7d", 0),
                "accelerating": True,
            },
            category=AlertCategory.WATCH,
            rule_id="intelligence_trend_emergence",
            expires_hours=48,
        )

    def _check_momentum_anomaly(
        self,
        name: str,
        entity_id: str,
        velocity: Dict[str, Any],
    ) -> Optional[Alert]:
        """
        MOMENTUM ANOMALY: Sudden spike or crash in mention velocity.

        If 7d mentions are 3x+ the weekly average, something's happening.
        If 7d mentions are <25% of weekly average, something stopped.
        """
        weekly_avg = velocity.get("weekly_avg", 0)
        mentions_7d = velocity.get("7d", 0)

        if weekly_avg < 5:
            return None  # Too low volume to detect anomalies

        ratio = mentions_7d / weekly_avg if weekly_avg > 0 else 0

        if ratio >= 3.0:
            # Spike
            severity = AlertSeverity.HIGH if ratio >= 5.0 else AlertSeverity.MEDIUM
            return self.engine.create_alert(
                alert_type=AlertType.ANOMALY,
                entity_id=entity_id,
                entity_name=name,
                severity=severity,
                title=f"Mention Spike: {name}",
                message=(
                    f"{name} has {mentions_7d} mentions in the last 7 days — "
                    f"{ratio:.1f}x the weekly average of {weekly_avg:.1f}. "
                    f"Something significant may be happening."
                ),
                data={
                    "mentions_7d": mentions_7d,
                    "weekly_avg": weekly_avg,
                    "spike_ratio": round(ratio, 2),
                    "direction": "spike",
                },
                category=AlertCategory.WATCH,
                rule_id="intelligence_momentum_spike",
                expires_hours=24,
            )

        elif ratio <= 0.25 and weekly_avg >= 10:
            # Crash — only alert for entities that normally have decent volume
            return self.engine.create_alert(
                alert_type=AlertType.ANOMALY,
                entity_id=entity_id,
                entity_name=name,
                severity=AlertSeverity.LOW,
                title=f"Mention Drop: {name}",
                message=(
                    f"{name} has only {mentions_7d} mentions in the last 7 days — "
                    f"down from a weekly average of {weekly_avg:.1f}. "
                    f"Activity has significantly decreased."
                ),
                data={
                    "mentions_7d": mentions_7d,
                    "weekly_avg": weekly_avg,
                    "drop_ratio": round(ratio, 2),
                    "direction": "drop",
                },
                category=AlertCategory.INFORMATIONAL,
                rule_id="intelligence_momentum_drop",
                expires_hours=48,
            )

        return None

    def _check_source_divergence(
        self,
        name: str,
        entity_id: str,
        diversity: Dict[str, int],
    ) -> Optional[Alert]:
        """
        SOURCE DIVERGENCE: When one source type dominates overwhelmingly.

        e.g., Reddit mentions are 10x news mentions — crowd sentiment may
        not match professional coverage.
        """
        if len(diversity) < 2:
            return None

        total = sum(diversity.values())
        if total < 10:
            return None  # Not enough data

        # Find dominant source
        sorted_sources = sorted(diversity.items(), key=lambda x: x[1], reverse=True)
        top_source, top_count = sorted_sources[0]
        second_source, second_count = sorted_sources[1]

        dominance_ratio = top_count / total

        # Alert if one source has >80% of mentions
        if dominance_ratio < 0.8:
            return None

        # Don't alert if the dominant source is "news" (that's normal)
        if top_source == "news":
            return None

        return self.engine.create_alert(
            alert_type=AlertType.SOURCE_DIVERGENCE,
            entity_id=entity_id,
            entity_name=name,
            severity=AlertSeverity.MEDIUM,
            title=f"Source Imbalance: {name}",
            message=(
                f"{name}: {top_source} accounts for {dominance_ratio:.0%} of mentions "
                f"({top_count}/{total}). Professional news coverage is disproportionately low. "
                f"Community sentiment may not match mainstream narrative."
            ),
            data={
                "dominant_source": top_source,
                "dominant_count": top_count,
                "total_mentions": total,
                "dominance_pct": round(dominance_ratio * 100, 1),
                "source_breakdown": diversity,
            },
            category=AlertCategory.WATCH,
            rule_id="intelligence_source_divergence",
            expires_hours=72,
        )
