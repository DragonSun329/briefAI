"""
Alert Explainer Module

Generates explainability payloads for alerts, including:
- Why the alert fired (trigger conditions)
- Top contributing evidence (entities, articles, repos)
- Historical context (similar past alerts)
- Confidence breakdown
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import json


@dataclass
class TriggerRule:
    """A single trigger condition that fired."""
    condition: str          # e.g., "TMS >= 90"
    expected: str           # e.g., ">= 90"
    actual: float           # e.g., 92
    met: bool = True        # Whether condition was met


@dataclass
class EvidenceEntity:
    """Entity contributing to the alert."""
    name: str
    entity_type: str        # company, model, repo, etc.
    contribution_score: float
    signal_type: str        # Which signal it contributes to
    url: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceArticle:
    """Article supporting the alert."""
    title: str
    source: str
    published_date: str
    relevance_score: float
    url: Optional[str] = None
    sentiment: Optional[str] = None
    key_entities: List[str] = field(default_factory=list)


@dataclass
class EvidenceRepo:
    """GitHub repo supporting the alert."""
    name: str
    full_name: str
    stars: int
    stars_delta: int        # Change in period
    forks: int
    url: str
    language: Optional[str] = None


@dataclass
class SimilarPastAlert:
    """Historical alert of similar type."""
    bucket_name: str
    alert_type: str
    detected_date: str
    resolved_date: Optional[str] = None
    outcome: Optional[str] = None  # What happened after alert
    weeks_to_resolution: Optional[int] = None


@dataclass
class ConfidenceFactor:
    """Component of confidence score."""
    name: str               # e.g., "coverage", "freshness"
    value: float            # 0-1
    weight: float           # Weight in composite
    contribution: float     # value × weight
    description: str


@dataclass
class AlertExplanation:
    """
    Complete explainability payload for an alert.

    Answers:
    - Why did this alert fire?
    - What evidence supports it?
    - How confident are we?
    - What typically happens next?
    """
    alert_id: str
    bucket_id: str
    bucket_name: str
    alert_type: str
    interpretation: str     # opportunity, risk, signal

    # Trigger conditions
    trigger_rules: List[TriggerRule] = field(default_factory=list)
    trigger_summary: str = ""

    # Evidence
    top_entities: List[EvidenceEntity] = field(default_factory=list)
    top_articles: List[EvidenceArticle] = field(default_factory=list)
    top_repos: List[EvidenceRepo] = field(default_factory=list)
    evidence_count: Dict[str, int] = field(default_factory=dict)

    # Historical context
    similar_past_alerts: List[SimilarPastAlert] = field(default_factory=list)
    typical_resolution: str = ""
    typical_timeline: str = ""

    # Confidence
    confidence_factors: List[ConfidenceFactor] = field(default_factory=list)
    overall_confidence: float = 0.0
    confidence_badge: str = "MEDIUM"

    # Action hints
    action_hints: List[str] = field(default_factory=list)
    watch_signals: List[str] = field(default_factory=list)

    # Metadata
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "alert_id": self.alert_id,
            "bucket_id": self.bucket_id,
            "bucket_name": self.bucket_name,
            "alert_type": self.alert_type,
            "interpretation": self.interpretation,
            "trigger_rules": [
                {"condition": r.condition, "expected": r.expected,
                 "actual": r.actual, "met": r.met}
                for r in self.trigger_rules
            ],
            "trigger_summary": self.trigger_summary,
            "top_entities": [
                {"name": e.name, "type": e.entity_type,
                 "contribution": e.contribution_score, "signal": e.signal_type,
                 "url": e.url, "metrics": e.metrics}
                for e in self.top_entities
            ],
            "top_articles": [
                {"title": a.title, "source": a.source, "date": a.published_date,
                 "relevance": a.relevance_score, "url": a.url}
                for a in self.top_articles
            ],
            "top_repos": [
                {"name": r.name, "stars": r.stars, "stars_delta": r.stars_delta,
                 "url": r.url}
                for r in self.top_repos
            ],
            "evidence_count": self.evidence_count,
            "similar_past_alerts": [
                {"bucket": s.bucket_name, "type": s.alert_type,
                 "detected": s.detected_date, "outcome": s.outcome}
                for s in self.similar_past_alerts
            ],
            "typical_resolution": self.typical_resolution,
            "typical_timeline": self.typical_timeline,
            "confidence_factors": [
                {"name": f.name, "value": f.value, "weight": f.weight,
                 "contribution": f.contribution, "description": f.description}
                for f in self.confidence_factors
            ],
            "overall_confidence": self.overall_confidence,
            "confidence_badge": self.confidence_badge,
            "action_hints": self.action_hints,
            "watch_signals": self.watch_signals,
            "generated_at": self.generated_at,
        }


# Alert type configurations
ALERT_CONFIGS = {
    "alpha_zone": {
        "name": "Alpha Zone (Hidden Gem)",
        "trigger_description": "Strong technical adoption without capital attention",
        "rules": [
            ("TMS", ">=", 90),
            ("CCS", "<=", 30),
        ],
        "persistence_required": 2,
        "typical_resolution": "Capital typically follows technical momentum in 4-8 weeks",
        "typical_timeline": "Monitor for 4-8 weeks",
        "action_hints": [
            "Monitor for VC deal announcements",
            "Track GitHub star velocity for continued momentum",
            "Watch for enterprise adoption signals (EIS)",
        ],
        "watch_signals": ["ccs", "eis_offensive"],
    },
    "hype_zone": {
        "name": "Hype Zone (Vaporware Risk)",
        "trigger_description": "High capital conviction without technical validation",
        "rules": [
            ("CCS", ">=", 90),
            ("TMS", "<=", 30),
        ],
        "persistence_required": 1,
        "typical_resolution": "Correction typically occurs within 3-6 months if technical traction doesn't follow",
        "typical_timeline": "Re-evaluate in 4-6 weeks",
        "action_hints": [
            "Verify actual product development progress",
            "Look for technical metrics to validate funding",
            "Monitor for negative press or pivots",
        ],
        "watch_signals": ["tms", "nas"],
    },
    "enterprise_pull": {
        "name": "Enterprise Pull",
        "trigger_description": "Incumbents showing offensive interest with technical support",
        "rules": [
            ("EIS_offensive_delta", ">=", 20),
            ("TMS", ">=", 40),
        ],
        "persistence_required": 1,
        "typical_resolution": "Enterprise adoption typically accelerates over 2-4 quarters",
        "typical_timeline": "Long-term bullish signal",
        "action_hints": [
            "Track specific enterprise mentions in SEC filings",
            "Monitor partnership announcements",
            "Watch for M&A activity in space",
        ],
        "watch_signals": ["eis_offensive", "ccs"],
    },
    "disruption_pressure": {
        "name": "Disruption Pressure",
        "trigger_description": "Incumbents expressing defensive concerns",
        "rules": [
            ("EIS_defensive", ">=", 85),
        ],
        "persistence_required": 2,
        "typical_resolution": "High defensive language often precedes market shifts",
        "typical_timeline": "Monitor competitive dynamics",
        "action_hints": [
            "Analyze specific risk factors mentioned",
            "Look for defensive acquisitions",
            "Track regulatory discussions",
        ],
        "watch_signals": ["eis_defensive", "ccs"],
    },
    "rotation": {
        "name": "Market Rotation",
        "trigger_description": "Technical momentum declining while capital stable",
        "rules": [
            ("TMS_trend", "==", "declining_4w"),
            ("CCS_range", "<=", 20),
        ],
        "persistence_required": 4,
        "typical_resolution": "Market typically consolidates around winners",
        "typical_timeline": "Natural market cycle",
        "action_hints": [
            "Identify leading players",
            "Watch for consolidation/M&A",
            "Monitor for new entrant disruption",
        ],
        "watch_signals": ["tms", "ccs"],
    },
}


class AlertExplainerService:
    """
    Service for generating alert explanations.

    Integrates with:
    - BucketProfile for signal values
    - AlertStore for historical alerts
    - Article/entity data for evidence
    """

    def __init__(self, data_dir: Path = None):
        """Initialize explainer service."""
        self.data_dir = data_dir or Path("data")

    def generate_explanation(self, alert_id: str, bucket_id: str,
                             bucket_name: str, alert_type: str,
                             trigger_scores: Dict[str, float],
                             bucket_data: Dict[str, Any] = None) -> AlertExplanation:
        """
        Generate complete explanation for an alert.

        Args:
            alert_id: Alert identifier
            bucket_id: Bucket identifier
            bucket_name: Human-readable bucket name
            alert_type: Type of alert
            trigger_scores: Scores that triggered the alert
            bucket_data: Full bucket profile data (optional)

        Returns:
            Complete AlertExplanation
        """
        config = ALERT_CONFIGS.get(alert_type, {})

        explanation = AlertExplanation(
            alert_id=alert_id,
            bucket_id=bucket_id,
            bucket_name=bucket_name,
            alert_type=alert_type,
            interpretation=self._get_interpretation(alert_type),
        )

        # Build trigger rules
        explanation.trigger_rules = self._build_trigger_rules(
            alert_type, trigger_scores
        )
        explanation.trigger_summary = config.get(
            "trigger_description",
            "Alert conditions met"
        )

        # Gather evidence
        if bucket_data:
            explanation.top_entities = self._extract_top_entities(bucket_data)
            explanation.top_repos = self._extract_top_repos(bucket_data)
            explanation.top_articles = self._extract_top_articles(bucket_data)

        explanation.evidence_count = {
            "entities": len(explanation.top_entities),
            "repos": len(explanation.top_repos),
            "articles": len(explanation.top_articles),
        }

        # Historical context
        explanation.similar_past_alerts = self._find_similar_past_alerts(alert_type)
        explanation.typical_resolution = config.get("typical_resolution", "")
        explanation.typical_timeline = config.get("typical_timeline", "")

        # Confidence
        explanation.confidence_factors = self._compute_confidence_factors(
            trigger_scores, bucket_data
        )
        explanation.overall_confidence = sum(
            f.contribution for f in explanation.confidence_factors
        )
        explanation.confidence_badge = self._get_confidence_badge(
            explanation.overall_confidence
        )

        # Action hints
        explanation.action_hints = config.get("action_hints", [])
        explanation.watch_signals = config.get("watch_signals", [])

        return explanation

    def _get_interpretation(self, alert_type: str) -> str:
        """Get interpretation for alert type."""
        interpretations = {
            "alpha_zone": "opportunity",
            "hype_zone": "risk",
            "enterprise_pull": "opportunity",
            "disruption_pressure": "signal",
            "rotation": "neutral",
        }
        return interpretations.get(alert_type, "signal")

    def _build_trigger_rules(self, alert_type: str,
                             trigger_scores: Dict[str, float]) -> List[TriggerRule]:
        """Build list of trigger conditions."""
        config = ALERT_CONFIGS.get(alert_type, {})
        rules = []

        for signal, operator, threshold in config.get("rules", []):
            signal_lower = signal.lower()
            actual = trigger_scores.get(signal_lower, trigger_scores.get(signal, 0))

            if operator == ">=":
                met = actual >= threshold
                expected = f">= {threshold}"
            elif operator == "<=":
                met = actual <= threshold
                expected = f"<= {threshold}"
            elif operator == "==":
                met = str(actual) == str(threshold)
                expected = f"== {threshold}"
            else:
                met = True
                expected = str(threshold)

            rules.append(TriggerRule(
                condition=f"{signal} {expected}",
                expected=expected,
                actual=actual,
                met=met,
            ))

        return rules

    def _extract_top_entities(self, bucket_data: Dict) -> List[EvidenceEntity]:
        """Extract top entities from bucket data."""
        entities = []

        # Technical entities (repos)
        for repo in bucket_data.get("top_technical_entities", [])[:3]:
            if isinstance(repo, str):
                entities.append(EvidenceEntity(
                    name=repo,
                    entity_type="repository",
                    contribution_score=0.8,
                    signal_type="tms",
                ))
            elif isinstance(repo, dict):
                entities.append(EvidenceEntity(
                    name=repo.get("name", "Unknown"),
                    entity_type="repository",
                    contribution_score=repo.get("score", 0.8),
                    signal_type="tms",
                    url=repo.get("url"),
                    metrics=repo.get("metrics", {}),
                ))

        # Capital entities (companies)
        for company in bucket_data.get("top_capital_entities", [])[:3]:
            if isinstance(company, str):
                entities.append(EvidenceEntity(
                    name=company,
                    entity_type="company",
                    contribution_score=0.7,
                    signal_type="ccs",
                ))
            elif isinstance(company, dict):
                entities.append(EvidenceEntity(
                    name=company.get("name", "Unknown"),
                    entity_type="company",
                    contribution_score=company.get("score", 0.7),
                    signal_type="ccs",
                    url=company.get("url"),
                    metrics=company.get("metrics", {}),
                ))

        return entities

    def _extract_top_repos(self, bucket_data: Dict) -> List[EvidenceRepo]:
        """Extract top repos from bucket data."""
        repos = []

        for repo in bucket_data.get("top_technical_entities", [])[:5]:
            if isinstance(repo, dict):
                repos.append(EvidenceRepo(
                    name=repo.get("name", "Unknown"),
                    full_name=repo.get("full_name", repo.get("name", "")),
                    stars=repo.get("stars", 0),
                    stars_delta=repo.get("stars_delta", repo.get("stars_week", 0)),
                    forks=repo.get("forks", 0),
                    url=repo.get("url", f"https://github.com/{repo.get('full_name', '')}"),
                    language=repo.get("language"),
                ))
            elif isinstance(repo, str):
                repos.append(EvidenceRepo(
                    name=repo,
                    full_name=repo,
                    stars=0,
                    stars_delta=0,
                    forks=0,
                    url=f"https://github.com/{repo}",
                ))

        return repos

    def _extract_top_articles(self, bucket_data: Dict) -> List[EvidenceArticle]:
        """Extract top articles from bucket data."""
        articles = []

        for article in bucket_data.get("top_articles", [])[:5]:
            if isinstance(article, dict):
                articles.append(EvidenceArticle(
                    title=article.get("title", "Unknown"),
                    source=article.get("source", "Unknown"),
                    published_date=article.get("published_date", ""),
                    relevance_score=article.get("relevance", 0.7),
                    url=article.get("url"),
                    sentiment=article.get("sentiment"),
                    key_entities=article.get("entities", []),
                ))

        return articles

    def _find_similar_past_alerts(self, alert_type: str) -> List[SimilarPastAlert]:
        """Find similar past alerts from history."""
        # This would query AlertStore in production
        # For now, return example data
        examples = {
            "alpha_zone": [
                SimilarPastAlert(
                    bucket_name="AI Coding",
                    alert_type="alpha_zone",
                    detected_date="2024-01-15",
                    resolved_date="2024-03-01",
                    outcome="Capital arrived 6 weeks later (Cursor funding)",
                    weeks_to_resolution=6,
                ),
            ],
            "hype_zone": [
                SimilarPastAlert(
                    bucket_name="Web3 AI",
                    alert_type="hype_zone",
                    detected_date="2023-06-01",
                    resolved_date="2023-10-01",
                    outcome="Correction as technical metrics didn't materialize",
                    weeks_to_resolution=17,
                ),
            ],
        }
        return examples.get(alert_type, [])

    def _compute_confidence_factors(self, trigger_scores: Dict,
                                     bucket_data: Dict = None) -> List[ConfidenceFactor]:
        """Compute confidence factor breakdown."""
        factors = []

        # Coverage factor
        coverage = bucket_data.get("overall_coverage", 0.7) if bucket_data else 0.7
        factors.append(ConfidenceFactor(
            name="coverage",
            value=coverage,
            weight=0.35,
            contribution=coverage * 0.35,
            description=f"Signal coverage: {coverage*100:.0f}% of expected data sources",
        ))

        # Freshness factor
        freshness = bucket_data.get("freshness", 0.9) if bucket_data else 0.9
        factors.append(ConfidenceFactor(
            name="freshness",
            value=freshness,
            weight=0.25,
            contribution=freshness * 0.25,
            description=f"Data freshness: {freshness*100:.0f}%",
        ))

        # Signal strength factor (how far beyond threshold)
        signal_strength = min(1.0, 0.5 + len([s for s in trigger_scores.values() if s > 70]) * 0.1)
        factors.append(ConfidenceFactor(
            name="signal_strength",
            value=signal_strength,
            weight=0.25,
            contribution=signal_strength * 0.25,
            description=f"Signal strength: {signal_strength*100:.0f}%",
        ))

        # Source diversity factor
        source_count = bucket_data.get("source_count", 3) if bucket_data else 3
        source_diversity = min(1.0, source_count / 5)
        factors.append(ConfidenceFactor(
            name="source_diversity",
            value=source_diversity,
            weight=0.15,
            contribution=source_diversity * 0.15,
            description=f"Source diversity: {source_count} sources",
        ))

        return factors

    def _get_confidence_badge(self, confidence: float) -> str:
        """Get confidence badge from score."""
        if confidence >= 0.8:
            return "HIGH"
        elif confidence >= 0.5:
            return "MEDIUM"
        elif confidence >= 0.3:
            return "LOW"
        else:
            return "VERY_LOW"

    def generate_alert_card_html(self, explanation: AlertExplanation) -> str:
        """Generate HTML for alert card display."""
        severity_colors = {
            "opportunity": "#22c55e",  # green
            "risk": "#ef4444",         # red
            "signal": "#f97316",       # orange
            "neutral": "#6b7280",      # gray
        }

        color = severity_colors.get(explanation.interpretation, "#6b7280")
        confidence_pct = int(explanation.overall_confidence * 100)
        confidence_bars = "█" * (confidence_pct // 10) + "░" * (10 - confidence_pct // 10)

        rules_html = "\n".join(
            f"• {r.condition} (actual: {r.actual:.0f}) {'✓' if r.met else '✗'}"
            for r in explanation.trigger_rules
        )

        return f"""
<div style="border-left: 4px solid {color}; padding: 12px; margin: 8px 0; background: #1a1a2e;">
  <h4 style="margin: 0; color: {color};">{ALERT_CONFIGS.get(explanation.alert_type, {}).get('name', explanation.alert_type)}</h4>
  <p style="color: #888; margin: 4px 0;">Bucket: {explanation.bucket_name}</p>
  <hr style="border-color: #333;">
  <p><strong>Trigger Conditions:</strong></p>
  <pre style="color: #aaa; font-size: 12px;">{rules_html}</pre>
  <p><strong>Confidence:</strong> {confidence_pct}% {confidence_bars}</p>
  <p><strong>Evidence:</strong> {explanation.evidence_count.get('entities', 0)} entities, {explanation.evidence_count.get('repos', 0)} repos</p>
  <p style="color: #888; font-size: 12px;">{explanation.typical_resolution}</p>
</div>
"""