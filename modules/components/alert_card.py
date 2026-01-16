"""
Enhanced Alert Card Component

Renders alert cards with:
- Severity indicator (icon + color)
- Confidence progress bar
- Evidence counts
- Persistence duration
- Action hints
- Dismiss/Watch buttons
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List

from utils.dashboard_helpers import (
    AlertCardData,
    get_confidence_style,
    get_severity_config,
    format_evidence_count,
    format_persistence_text,
    get_action_hint,
)


# Alert type display names
ALERT_TYPE_NAMES = {
    "alpha_zone": "Alpha Zone (Hidden Gem)",
    "hype_zone": "Hype Zone",
    "enterprise_breakout": "Enterprise Breakout",
    "disruption_signal": "Disruption Signal",
    "rotation_signal": "Rotation Signal",
}

# Interpretation to category
INTERPRETATION_CATEGORIES = {
    "opportunity": "OPPORTUNITY",
    "risk": "CAUTION",
    "signal": "WATCH",
    "neutral": "MONITOR",
}


def build_alert_card_data(
    alert,  # StoredAlert
    confidence: float = 0.5,
) -> AlertCardData:
    """
    Build AlertCardData from a StoredAlert.

    Args:
        alert: StoredAlert instance
        confidence: Overall confidence score

    Returns:
        AlertCardData ready for rendering
    """
    # Extract evidence counts
    evidence = alert.evidence_payload or {}
    repos = len(evidence.get("top_repos", []))
    articles = len(evidence.get("top_articles", []))
    companies = len(evidence.get("top_entities", []))

    evidence_text = format_evidence_count(repos, articles, companies)
    persistence_text = format_persistence_text(alert.weeks_persistent)
    action_hint = get_action_hint(alert.alert_type)
    alert_name = ALERT_TYPE_NAMES.get(alert.alert_type, alert.alert_type)

    return AlertCardData(
        bucket_name=alert.bucket_name,
        alert_type=alert.alert_type,
        alert_name=alert_name,
        severity=alert.severity.upper() if isinstance(alert.severity, str) else alert.severity.value.upper(),
        confidence=confidence,
        evidence_text=evidence_text,
        persistence_text=persistence_text,
        action_hint=action_hint,
        trigger_scores=alert.trigger_scores or {},
    )


class AlertCardRenderer:
    """Renders alert cards as HTML for Streamlit."""

    def render_card_html(self, card: AlertCardData) -> str:
        """
        Render an alert card as HTML.

        Args:
            card: AlertCardData instance

        Returns:
            HTML string for st.markdown(unsafe_allow_html=True)
        """
        sev_config = get_severity_config(card.severity)
        conf_style = get_confidence_style(card.confidence)

        # Confidence bar width
        conf_width = int(card.confidence * 100)
        conf_pct = f"{card.confidence:.0%}"

        # Build trigger rules text
        trigger_text = " | ".join(
            f"{k.upper()}: {v:.0f}" for k, v in card.trigger_scores.items()
        )

        html = f"""
        <div style="
            border: 2px {conf_style['border_style']} {sev_config['color']};
            border-radius: 8px;
            padding: 12px;
            margin: 8px 0;
            background: {sev_config['bg_color']};
            opacity: {conf_style['opacity']};
        ">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="
                        background: {sev_config['color']};
                        color: white;
                        padding: 2px 8px;
                        border-radius: 4px;
                        font-size: 0.8em;
                        margin-right: 8px;
                    ">{card.severity}</span>
                    <strong>{card.alert_name}</strong>
                </div>
                <span style="color: #666; font-size: 0.9em;">
                    Persistent: {card.persistence_text}
                </span>
            </div>

            <div style="margin: 8px 0;">
                <strong>Bucket:</strong> {card.bucket_name}
            </div>

            <div style="margin: 8px 0;">
                <strong>Confidence:</strong> {conf_pct}
                <div style="
                    background: #e0e0e0;
                    border-radius: 4px;
                    height: 8px;
                    margin-top: 4px;
                ">
                    <div style="
                        background: {conf_style['color']};
                        width: {conf_width}%;
                        height: 100%;
                        border-radius: 4px;
                    "></div>
                </div>
            </div>

            <div style="margin: 8px 0; font-size: 0.9em; color: #666;">
                <strong>Evidence:</strong> {card.evidence_text}
            </div>

            <div style="margin: 8px 0; font-size: 0.9em; color: #666;">
                <strong>Triggers:</strong> {trigger_text}
            </div>

            <div style="
                margin-top: 12px;
                padding-top: 8px;
                border-top: 1px solid #ddd;
                font-size: 0.85em;
                color: #555;
            ">
                <strong>Action:</strong> {card.action_hint}
            </div>
        </div>
        """

        return html

    def render_compact_card_html(self, card: AlertCardData) -> str:
        """Render a compact version of the alert card."""
        sev_config = get_severity_config(card.severity)

        return f"""
        <div style="
            display: flex;
            align-items: center;
            padding: 8px;
            border-left: 4px solid {sev_config['color']};
            background: {sev_config['bg_color']};
            margin: 4px 0;
        ">
            <span style="margin-right: 8px;">{card.bucket_name}</span>
            <span style="color: #666; font-size: 0.85em;">{card.alert_name}</span>
            <span style="margin-left: auto; color: {sev_config['color']};">{card.confidence:.0%}</span>
        </div>
        """