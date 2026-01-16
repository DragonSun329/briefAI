"""
Dashboard UI Helper Functions

Provides helper functions for:
- Confidence visual encoding (opacity, border style)
- Sparkline data generation
- Alert card formatting
- Persistence text formatting
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass

import plotly.graph_objects as go


# Confidence thresholds from signal_config.json
CONFIDENCE_THRESHOLDS = {
    "high": 0.8,
    "medium": 0.5,
    "low": 0.3,
}

# Severity configurations
SEVERITY_CONFIGS = {
    "INFO": {
        "icon": "info",
        "color": "#2196F3",
        "bg_color": "rgba(33, 150, 243, 0.1)",
        "cooldown_days": 3,
    },
    "WARN": {
        "icon": "warning",
        "color": "#FF9800",
        "bg_color": "rgba(255, 152, 0, 0.1)",
        "cooldown_days": 7,
    },
    "CRIT": {
        "icon": "error",
        "color": "#F44336",
        "bg_color": "rgba(244, 67, 54, 0.1)",
        "cooldown_days": 14,
    },
}


def get_confidence_style(confidence: Optional[float]) -> Dict[str, Any]:
    """
    Get visual style based on confidence level.

    Args:
        confidence: Confidence value 0-1, or None for missing data

    Returns:
        Dict with opacity, border_style, color, badge keys
    """
    if confidence is None:
        return {
            "opacity": 0.5,
            "border_style": "dashed",
            "color": "#9e9e9e",
            "badge": "?",
            "label": "missing",
        }

    if confidence >= CONFIDENCE_THRESHOLDS["high"]:
        return {
            "opacity": 1.0,
            "border_style": "solid",
            "color": "#27ae60",
            "badge": None,
            "label": "high",
        }
    elif confidence >= CONFIDENCE_THRESHOLDS["medium"]:
        return {
            "opacity": 0.7,
            "border_style": "solid",
            "color": "#f39c12",
            "badge": None,
            "label": "medium",
        }
    else:
        return {
            "opacity": 0.5,
            "border_style": "dashed",
            "color": "#e74c3c",
            "badge": None,
            "label": "low",
        }


def generate_sparkline_data(history: List[float]) -> Dict[str, Any]:
    """
    Generate sparkline data from historical values.

    Args:
        history: List of historical values (oldest first)

    Returns:
        Dict with values, trend, delta, min, max
    """
    if not history:
        return {
            "values": [],
            "trend": "stable",
            "delta": 0,
            "min": 0,
            "max": 0,
            "sparkline_chars": "",
        }

    delta = history[-1] - history[0] if len(history) > 1 else 0

    # Determine trend
    if delta > 5:
        trend = "rising"
    elif delta < -5:
        trend = "falling"
    else:
        trend = "stable"

    # Generate ASCII sparkline characters
    sparkline_chars = _generate_sparkline_ascii(history)

    return {
        "values": history,
        "trend": trend,
        "delta": delta,
        "min": min(history),
        "max": max(history),
        "sparkline_chars": sparkline_chars,
    }


def _generate_sparkline_ascii(values: List[float]) -> str:
    """Generate ASCII sparkline from values."""
    if not values:
        return ""

    # Sparkline characters from lowest to highest
    chars = "▁▂▃▄▅▆▇█"

    min_val = min(values)
    max_val = max(values)
    range_val = max_val - min_val

    if range_val == 0:
        return chars[4] * len(values)  # All middle

    result = []
    for v in values:
        normalized = (v - min_val) / range_val
        index = int(normalized * (len(chars) - 1))
        result.append(chars[index])

    return "".join(result)


def format_persistence_text(weeks: int) -> str:
    """
    Format persistence duration text.

    Args:
        weeks: Number of weeks persistent

    Returns:
        Formatted string like "3 weeks" or "New"
    """
    if weeks == 0:
        return "New"
    elif weeks == 1:
        return "1 week"
    else:
        return f"{weeks} weeks"


def get_severity_config(severity: str) -> Dict[str, Any]:
    """
    Get configuration for a severity level.

    Args:
        severity: Severity string (INFO, WARN, CRIT)

    Returns:
        Config dict with icon, color, bg_color, cooldown_days
    """
    return SEVERITY_CONFIGS.get(severity.upper(), SEVERITY_CONFIGS["INFO"])


def format_evidence_count(
    repos: int = 0,
    articles: int = 0,
    companies: int = 0
) -> str:
    """
    Format evidence count for display.

    Args:
        repos: Number of repos
        articles: Number of articles
        companies: Number of companies

    Returns:
        Formatted string like "12 repos, 47 articles, 3 companies"
    """
    parts = []
    if repos > 0:
        parts.append(f"{repos} repo{'s' if repos != 1 else ''}")
    if articles > 0:
        parts.append(f"{articles} article{'s' if articles != 1 else ''}")
    if companies > 0:
        parts.append(f"{companies} compan{'ies' if companies != 1 else 'y'}")

    return ", ".join(parts) if parts else "No evidence"


def get_action_hint(alert_type: str) -> str:
    """
    Get action hint for an alert type.

    Args:
        alert_type: Alert type string

    Returns:
        Action hint text
    """
    hints = {
        "alpha_zone": "Monitor for capital inflow signals in coming weeks",
        "hype_zone": "Exercise caution - sentiment may not match substance",
        "enterprise_breakout": "Strong enterprise signal - consider deep dive",
        "disruption_signal": "Early-stage trend - monitor for enterprise adoption",
        "rotation_signal": "Capital may be rotating - watch for momentum recovery",
    }
    return hints.get(alert_type, "Monitor this trend")


@dataclass
class AlertCardData:
    """Data structure for rendering an alert card."""
    bucket_name: str
    alert_type: str
    alert_name: str
    severity: str
    confidence: float
    evidence_text: str
    persistence_text: str
    action_hint: str
    trigger_scores: Dict[str, float]

    # Style properties (computed)
    severity_icon: str = ""
    severity_color: str = ""
    confidence_style: Dict[str, Any] = None

    def __post_init__(self):
        sev_config = get_severity_config(self.severity)
        self.severity_icon = sev_config["icon"]
        self.severity_color = sev_config["color"]
        self.confidence_style = get_confidence_style(self.confidence)


def create_sparkline_figure(
    history: List[float],
    signal_name: str,
    coverage: Optional[float] = None,
    height: int = 60,
    width: int = 150,
) -> go.Figure:
    """
    Create a Plotly sparkline figure.

    Args:
        history: List of values (oldest to newest)
        signal_name: Signal name for label
        coverage: Optional coverage percentage (0-1)
        height: Figure height in pixels
        width: Figure width in pixels

    Returns:
        Plotly Figure object
    """
    if not history:
        # Return empty figure
        fig = go.Figure()
        fig.add_annotation(text="No data", x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=height, width=width, margin=dict(l=0, r=0, t=0, b=0))
        return fig

    # Determine color based on trend
    delta = history[-1] - history[0] if len(history) > 1 else 0
    if delta > 5:
        color = "#27ae60"  # Green for rising
    elif delta < -5:
        color = "#e74c3c"  # Red for falling
    else:
        color = "#3498db"  # Blue for stable

    fig = go.Figure()

    # Add line trace
    fig.add_trace(go.Scatter(
        y=history,
        mode="lines",
        line=dict(color=color, width=2),
        fill="tozeroy",
        fillcolor=f"rgba{tuple(list(int(color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + [0.2])}",
        hoverinfo="skip",
    ))

    # Current value annotation
    current = history[-1]
    delta_text = f"{'↑' if delta > 0 else '↓' if delta < 0 else '→'}{abs(delta):.0f}"

    fig.add_annotation(
        x=len(history) - 1,
        y=current,
        text=f"{current:.0f} {delta_text}",
        showarrow=False,
        font=dict(size=10, color=color),
        xanchor="left",
        xshift=5,
    )

    # Coverage annotation if provided
    if coverage is not None:
        fig.add_annotation(
            x=0,
            y=max(history),
            text=f"{coverage:.0%}",
            showarrow=False,
            font=dict(size=8, color="#666"),
            xanchor="left",
            yanchor="top",
        )

    fig.update_layout(
        height=height,
        width=width,
        margin=dict(l=5, r=40, t=5, b=5),
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    return fig