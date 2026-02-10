# Frontend Trust Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the Streamlit bucket dashboard with confidence visual encoding, persistent alert cards with cooldowns, and an explainability drawer showing sparklines and top evidence.

**Architecture:** Add UI components that consume the new backend modules (alert_store, alert_explainer, historical_baselines, signal_metadata). Create helper functions for sparkline generation and confidence visualization. Integrate with existing `bucket_dashboard.py` by modifying `render_alerts_panel` and `render_bucket_detail` functions.

**Tech Stack:** Streamlit, Plotly (sparklines), Python dataclasses, SQLite (via alert_store)

---

## Task 1: Create Dashboard UI Helper Module

**Files:**
- Create: `utils/dashboard_helpers.py`
- Test: `tests/test_dashboard_helpers.py`

This module provides UI helper functions for confidence encoding, sparkline generation, and alert card rendering that will be used by the dashboard.

**Step 1: Write the failing test**

Create `tests/test_dashboard_helpers.py`:

```python
"""Tests for dashboard UI helpers."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.dashboard_helpers import (
    get_confidence_style,
    generate_sparkline_data,
    format_persistence_text,
    get_severity_config,
)


class TestConfidenceStyle:
    """Tests for confidence visual encoding."""

    def test_high_confidence(self):
        """High confidence (>0.8) returns solid style."""
        style = get_confidence_style(0.85)
        assert style["opacity"] == 1.0
        assert style["border_style"] == "solid"
        assert style["badge"] is None

    def test_medium_confidence(self):
        """Medium confidence (0.5-0.8) returns reduced opacity."""
        style = get_confidence_style(0.65)
        assert style["opacity"] == 0.7
        assert style["border_style"] == "solid"

    def test_low_confidence(self):
        """Low confidence (<0.5) returns dashed style."""
        style = get_confidence_style(0.35)
        assert style["opacity"] == 0.5
        assert style["border_style"] == "dashed"

    def test_missing_data(self):
        """Missing data (None) returns gray with badge."""
        style = get_confidence_style(None)
        assert style["color"] == "#9e9e9e"
        assert style["badge"] == "?"


class TestSparklineData:
    """Tests for sparkline generation."""

    def test_generate_sparkline_8_weeks(self):
        """Generate 8-week sparkline data."""
        history = [50, 55, 60, 65, 70, 72, 75, 78]
        result = generate_sparkline_data(history)
        assert len(result["values"]) == 8
        assert result["trend"] == "rising"
        assert result["delta"] == 28  # 78 - 50

    def test_empty_history(self):
        """Handle empty history gracefully."""
        result = generate_sparkline_data([])
        assert result["values"] == []
        assert result["trend"] == "stable"


class TestPersistenceText:
    """Tests for persistence duration formatting."""

    def test_one_week(self):
        """One week persistence."""
        assert format_persistence_text(1) == "1 week"

    def test_multiple_weeks(self):
        """Multiple weeks persistence."""
        assert format_persistence_text(3) == "3 weeks"

    def test_zero_weeks(self):
        """Zero weeks (new alert)."""
        assert format_persistence_text(0) == "New"


class TestSeverityConfig:
    """Tests for severity configuration."""

    def test_info_severity(self):
        """INFO severity config."""
        config = get_severity_config("INFO")
        assert config["icon"] == "info"
        assert config["cooldown_days"] == 3

    def test_warn_severity(self):
        """WARN severity config."""
        config = get_severity_config("WARN")
        assert config["icon"] == "warning"
        assert config["cooldown_days"] == 7

    def test_crit_severity(self):
        """CRIT severity config."""
        config = get_severity_config("CRIT")
        assert config["icon"] == "error"
        assert config["cooldown_days"] == 14


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_helpers.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'utils.dashboard_helpers'"

**Step 3: Write minimal implementation**

Create `utils/dashboard_helpers.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_helpers.py -v`
Expected: PASS (all tests green)

**Step 5: Commit**

```bash
git add utils/dashboard_helpers.py tests/test_dashboard_helpers.py
git commit -m "feat: add dashboard UI helper functions for confidence encoding"
```

---

## Task 2: Create Sparkline Chart Generator

**Files:**
- Modify: `utils/dashboard_helpers.py`
- Test: `tests/test_dashboard_helpers.py` (add tests)

Add a Plotly sparkline generator for 8-week signal history visualization.

**Step 1: Write the failing test**

Add to `tests/test_dashboard_helpers.py`:

```python
class TestSparklineChart:
    """Tests for Plotly sparkline generation."""

    def test_create_sparkline_figure(self):
        """Create a Plotly sparkline figure."""
        from utils.dashboard_helpers import create_sparkline_figure

        history = [50, 55, 60, 65, 70, 72, 75, 78]
        fig = create_sparkline_figure(history, "TMS")

        assert fig is not None
        assert len(fig.data) == 1  # One trace

    def test_sparkline_with_coverage(self):
        """Sparkline with coverage percentage."""
        from utils.dashboard_helpers import create_sparkline_figure

        history = [50, 55, 60, 65, 70, 72, 75, 78]
        fig = create_sparkline_figure(history, "TMS", coverage=0.92)

        # Should have coverage annotation
        assert fig is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_helpers.py::TestSparklineChart -v`
Expected: FAIL with "cannot import name 'create_sparkline_figure'"

**Step 3: Write minimal implementation**

Add to `utils/dashboard_helpers.py`:

```python
import plotly.graph_objects as go


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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_helpers.py::TestSparklineChart -v`
Expected: PASS

**Step 5: Commit**

```bash
git add utils/dashboard_helpers.py tests/test_dashboard_helpers.py
git commit -m "feat: add Plotly sparkline generator for signal history"
```

---

## Task 3: Create Enhanced Alert Card Component

**Files:**
- Create: `modules/components/alert_card.py`
- Test: `tests/test_alert_card.py`

Create a reusable Streamlit component for rendering enhanced alert cards with confidence bars, evidence counts, and action hints.

**Step 1: Write the failing test**

Create `tests/test_alert_card.py`:

```python
"""Tests for alert card component."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.components.alert_card import (
    AlertCardRenderer,
    build_alert_card_data,
)
from utils.alert_store import StoredAlert, AlertSeverity


class TestBuildAlertCardData:
    """Tests for building alert card data."""

    def test_build_from_stored_alert(self):
        """Build card data from StoredAlert."""
        alert = StoredAlert(
            alert_id="test-123",
            bucket_id="ai-agents",
            bucket_name="Agent Frameworks",
            alert_type="alpha_zone",
            severity="WARN",
            interpretation="opportunity",
            first_detected="2026-01-01",
            last_updated="2026-01-15",
            weeks_persistent=2,
            trigger_scores={"tms": 92, "ccs": 28},
            evidence_payload={
                "top_repos": [{"name": "langchain"}],
                "top_articles": [{"title": "Article 1"}, {"title": "Article 2"}],
                "top_entities": [{"name": "Company 1"}],
            },
        )

        card_data = build_alert_card_data(alert, confidence=0.87)

        assert card_data.bucket_name == "Agent Frameworks"
        assert card_data.alert_type == "alpha_zone"
        assert card_data.persistence_text == "2 weeks"
        assert card_data.confidence == 0.87


class TestAlertCardRenderer:
    """Tests for alert card rendering."""

    def test_render_returns_html(self):
        """Renderer produces HTML string."""
        from utils.dashboard_helpers import AlertCardData

        card_data = AlertCardData(
            bucket_name="RAG & Retrieval",
            alert_type="alpha_zone",
            alert_name="Alpha Zone (Hidden Gem)",
            severity="WARN",
            confidence=0.87,
            evidence_text="12 repos, 47 articles, 3 companies",
            persistence_text="3 weeks",
            action_hint="Monitor for capital inflow",
            trigger_scores={"tms": 92, "ccs": 25},
        )

        renderer = AlertCardRenderer()
        html = renderer.render_card_html(card_data)

        assert "RAG & Retrieval" in html
        assert "Alpha Zone" in html
        assert "87%" in html or "0.87" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_alert_card.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

Create directory and file:

```bash
mkdir -p modules/components
touch modules/components/__init__.py
```

Create `modules/components/alert_card.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_alert_card.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add modules/components/__init__.py modules/components/alert_card.py tests/test_alert_card.py
git commit -m "feat: add enhanced alert card component with confidence bars"
```

---

## Task 4: Create Bucket Explain Drawer Component

**Files:**
- Create: `modules/components/explain_drawer.py`
- Test: `tests/test_explain_drawer.py`

Create the explainability drawer showing sparklines, top entities, and data quality.

**Step 1: Write the failing test**

Create `tests/test_explain_drawer.py`:

```python
"""Tests for explain drawer component."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.components.explain_drawer import (
    ExplainDrawerData,
    build_explain_drawer_data,
)


class TestExplainDrawerData:
    """Tests for explain drawer data building."""

    def test_build_drawer_data(self):
        """Build drawer data from bucket profile."""
        # Mock profile-like dict
        profile = {
            "bucket_id": "ai-agents",
            "bucket_name": "Agent Frameworks",
            "tms": 85,
            "ccs": 42,
            "nas": 72,
            "eis_offensive": 61,
            "signal_confidence": 0.85,
            "top_technical_entities": ["langchain/langchain", "vllm-project/vllm"],
            "top_capital_entities": ["Pinecone"],
            "entity_count": 15,
        }

        signal_history = {
            "tms": [75, 78, 80, 82, 83, 84, 85, 85],
            "ccs": [35, 36, 38, 39, 40, 41, 42, 42],
        }

        drawer_data = build_explain_drawer_data(profile, signal_history)

        assert drawer_data.bucket_name == "Agent Frameworks"
        assert len(drawer_data.sparklines) >= 2
        assert drawer_data.data_quality_pct > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_explain_drawer.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

Create `modules/components/explain_drawer.py`:

```python
"""
Bucket Explain Drawer Component

Renders a detailed explainability view with:
- 8-week signal sparklines with coverage
- Top contributing entities (repos, companies)
- Active alert rationale
- Data quality indicator
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from utils.dashboard_helpers import (
    generate_sparkline_data,
    create_sparkline_figure,
    get_confidence_style,
)


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


@dataclass
class ExplainDrawerData:
    """Data for rendering the explain drawer."""
    bucket_id: str
    bucket_name: str

    # Sparklines
    sparklines: List[SparklineData] = field(default_factory=list)

    # Top entities
    top_repos: List[Dict[str, Any]] = field(default_factory=list)
    top_companies: List[Dict[str, Any]] = field(default_factory=list)

    # Alert info
    active_alert_type: Optional[str] = None
    alert_rationale: Optional[str] = None
    alert_first_detected: Optional[str] = None
    similar_past_alert: Optional[str] = None

    # Data quality
    data_quality_pct: float = 0.0
    signals_available: int = 0
    total_signals: int = 6
    last_updated: Optional[str] = None


SIGNAL_DISPLAY_NAMES = {
    "tms": "TMS (Technical)",
    "ccs": "CCS (Capital)",
    "nas": "NAS (Narrative)",
    "eis": "EIS (Enterprise)",
    "pms": "PMS (Market)",
    "css": "CSS (Crypto)",
}


def build_explain_drawer_data(
    profile: Dict[str, Any],
    signal_history: Dict[str, List[float]],
    alert_info: Optional[Dict[str, Any]] = None,
) -> ExplainDrawerData:
    """
    Build ExplainDrawerData from profile and history.

    Args:
        profile: Bucket profile dict or object
        signal_history: Dict mapping signal names to 8-week history
        alert_info: Optional alert information

    Returns:
        ExplainDrawerData ready for rendering
    """
    # Handle both dict and object
    if hasattr(profile, "__dict__"):
        profile = vars(profile)

    sparklines = []
    signals_available = 0

    # Build sparklines for each signal
    for signal_key in ["tms", "ccs", "nas", "eis"]:
        current = profile.get(signal_key) or profile.get(f"{signal_key}_offensive")
        history = signal_history.get(signal_key, [])

        if current is not None:
            signals_available += 1

            spark_data = generate_sparkline_data(history if history else [current])

            # Get coverage from metadata if available
            metadata = profile.get("signal_metadata", {}).get(signal_key, {})
            coverage = metadata.get("coverage", 0.5)

            sparklines.append(SparklineData(
                signal_name=signal_key,
                display_name=SIGNAL_DISPLAY_NAMES.get(signal_key, signal_key.upper()),
                current_value=current,
                delta=spark_data["delta"],
                coverage=coverage,
                history=history if history else [current],
                sparkline_chars=spark_data["sparkline_chars"],
                trend=spark_data["trend"],
            ))

    # Extract top entities
    top_repos = []
    for entity in profile.get("top_technical_entities", [])[:5]:
        if isinstance(entity, str):
            top_repos.append({"name": entity, "stars_delta": 0})
        else:
            top_repos.append(entity)

    top_companies = []
    for entity in profile.get("top_capital_entities", [])[:3]:
        if isinstance(entity, str):
            top_companies.append({"name": entity})
        else:
            top_companies.append(entity)

    # Data quality
    data_quality = signals_available / 6.0  # 6 total signals

    # Alert info
    active_alert_type = None
    alert_rationale = None
    if alert_info:
        active_alert_type = alert_info.get("alert_type")
        alert_rationale = alert_info.get("rationale")

    return ExplainDrawerData(
        bucket_id=profile.get("bucket_id", ""),
        bucket_name=profile.get("bucket_name", ""),
        sparklines=sparklines,
        top_repos=top_repos,
        top_companies=top_companies,
        active_alert_type=active_alert_type,
        alert_rationale=alert_rationale,
        data_quality_pct=data_quality,
        signals_available=signals_available,
        last_updated=profile.get("last_updated"),
    )


class ExplainDrawerRenderer:
    """Renders the explain drawer in Streamlit."""

    def render(self, data: ExplainDrawerData, st_container):
        """
        Render the explain drawer.

        Args:
            data: ExplainDrawerData instance
            st_container: Streamlit container (st or column)
        """
        import streamlit as st

        # Header
        st_container.markdown(f"### {data.bucket_name} - Deep Dive")

        # Sparklines section
        st_container.markdown("**8-Week Signal Sparklines:**")

        for spark in data.sparklines:
            col1, col2, col3 = st_container.columns([2, 3, 1])

            with col1:
                delta_str = f"{'↑' if spark.delta > 0 else '↓' if spark.delta < 0 else '→'}{abs(spark.delta):.0f}"
                st.markdown(f"**{spark.display_name}:** {spark.current_value:.0f} ({delta_str})")

            with col2:
                st.markdown(f"`{spark.sparkline_chars}`")

            with col3:
                st.markdown(f"Coverage: {spark.coverage:.0%}")

        st_container.divider()

        # Top entities
        col_left, col_right = st_container.columns(2)

        with col_left:
            st.markdown("**Top Repos:**")
            for repo in data.top_repos[:5]:
                name = repo.get("name", repo) if isinstance(repo, dict) else repo
                stars = repo.get("stars_delta", "") if isinstance(repo, dict) else ""
                stars_str = f" (⭐ +{stars})" if stars else ""
                st.markdown(f"• {name}{stars_str}")

        with col_right:
            st.markdown("**Top Companies:**")
            for company in data.top_companies[:3]:
                name = company.get("name", company) if isinstance(company, dict) else company
                funding = company.get("funding", "") if isinstance(company, dict) else ""
                funding_str = f" ({funding})" if funding else ""
                st.markdown(f"• {name}{funding_str}")

        st_container.divider()

        # Alert rationale if present
        if data.active_alert_type:
            st_container.markdown(f"**Active Alert:** {data.active_alert_type}")
            if data.alert_rationale:
                st_container.markdown(f"*Rationale:* {data.alert_rationale}")

        # Data quality footer
        quality_color = "#27ae60" if data.data_quality_pct > 0.8 else "#f39c12" if data.data_quality_pct > 0.5 else "#e74c3c"
        st_container.markdown(f"""
        **Data Quality:** {data.data_quality_pct:.0%} | {data.signals_available}/{data.total_signals} signals | {'Fresh' if data.last_updated else 'Unknown age'}
        """)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_explain_drawer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add modules/components/explain_drawer.py tests/test_explain_drawer.py
git commit -m "feat: add bucket explain drawer with sparklines and evidence"
```

---

## Task 5: Integrate Enhanced Alert Panel into Dashboard

**Files:**
- Modify: `modules/bucket_dashboard.py:1582-1620` (render_alerts_panel)
- Modify: `modules/bucket_dashboard.py:1622-1644` (_render_alert_card)

Update the existing alert panel to use persistent alerts with cooldowns and the new card component.

**Step 1: Write the failing test**

Add to existing test file or create `tests/test_bucket_dashboard_integration.py`:

```python
"""Integration tests for bucket dashboard with new components."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAlertPanelIntegration:
    """Tests for alert panel integration."""

    def test_import_new_components(self):
        """Dashboard imports new components successfully."""
        from modules.bucket_dashboard import render_alerts_panel
        from modules.components.alert_card import AlertCardRenderer

        assert render_alerts_panel is not None
        assert AlertCardRenderer is not None

    def test_alert_store_integration(self):
        """Alert store can be used in dashboard."""
        from utils.alert_store import AlertStore
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            store = AlertStore(db_path=Path(f.name))
            alerts = store.get_active_alerts()
            assert isinstance(alerts, list)
            store.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Step 2: Run test to verify baseline works**

Run: `pytest tests/test_bucket_dashboard_integration.py -v`
Expected: PASS (existing code should pass)

**Step 3: Modify render_alerts_panel function**

In `modules/bucket_dashboard.py`, replace lines 1582-1644 with:

```python
# Add imports at top of file (around line 30-40):
from utils.alert_store import AlertStore, StoredAlert, AlertSeverity
from modules.components.alert_card import AlertCardRenderer, build_alert_card_data


def render_alerts_panel(alerts: List[BucketAlert], labels: Dict[str, str]):
    """
    Render enhanced divergence alerts panel with persistent storage.

    Features:
    - Confidence progress bars
    - Evidence counts
    - Persistence duration
    - Cooldown enforcement
    - Action hints
    """
    if not alerts:
        st.info("No divergence alerts detected this week")
        return

    # Initialize alert store for persistence tracking
    alert_store = AlertStore()
    renderer = AlertCardRenderer()

    # Group by interpretation
    opportunities = [a for a in alerts if a.interpretation == AlertInterpretation.OPPORTUNITY]
    risks = [a for a in alerts if a.interpretation == AlertInterpretation.RISK]
    signals = [a for a in alerts if a.interpretation in (AlertInterpretation.SIGNAL, AlertInterpretation.NEUTRAL)]

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Opportunities", len(opportunities), delta=None)
    with col2:
        st.metric("Risks", len(risks), delta=None)
    with col3:
        st.metric("Signals", len(signals), delta=None)

    st.divider()

    # Opportunities
    st.markdown(f"### {labels['opportunities']}")
    if opportunities:
        for alert in opportunities[:5]:
            _render_enhanced_alert_card(alert, renderer, alert_store)
    else:
        st.caption("No opportunity alerts")

    st.divider()

    # Risks
    st.markdown(f"### {labels['risks']}")
    if risks:
        for alert in risks[:5]:
            _render_enhanced_alert_card(alert, renderer, alert_store)
    else:
        st.caption("No risk alerts")

    st.divider()

    # Signals
    st.markdown(f"### {labels['signals']}")
    if signals:
        for alert in signals[:5]:
            _render_enhanced_alert_card(alert, renderer, alert_store)
    else:
        st.caption("No signal alerts")

    alert_store.close()


def _render_enhanced_alert_card(
    alert: BucketAlert,
    renderer: AlertCardRenderer,
    alert_store: AlertStore
):
    """Render a single enhanced alert card."""
    # Check for stored alert data
    stored = alert_store.get_alert_by_bucket_type(alert.bucket_id, alert.alert_type.value)

    # Build card data
    if stored:
        # Use stored alert with persistence info
        weeks_persistent = stored.weeks_persistent
        evidence_payload = stored.evidence_payload or {}
    else:
        weeks_persistent = 1
        evidence_payload = {
            "top_repos": [],
            "top_articles": [],
            "top_entities": [{"name": e} for e in (alert.supporting_entities or [])[:3]],
        }

    # Create a temporary StoredAlert for the renderer
    temp_stored = StoredAlert(
        alert_id=f"{alert.bucket_id}-{alert.alert_type.value}",
        bucket_id=alert.bucket_id,
        bucket_name=alert.bucket_name,
        alert_type=alert.alert_type.value,
        severity="WARN" if alert.interpretation == AlertInterpretation.OPPORTUNITY else "INFO",
        interpretation=alert.interpretation.value,
        first_detected=str(date.today()),
        last_updated=str(datetime.now()),
        weeks_persistent=weeks_persistent,
        trigger_scores={
            "tms": getattr(alert, "tms", 0) or 0,
            "ccs": getattr(alert, "ccs", 0) or 0,
        },
        evidence_payload=evidence_payload,
        rationale=alert.rationale,
    )

    card_data = build_alert_card_data(temp_stored, confidence=0.75)

    # Render with expander for details
    with st.expander(f"{card_data.bucket_name} - {card_data.alert_name}", expanded=False):
        st.markdown(renderer.render_card_html(card_data), unsafe_allow_html=True)

        # Action buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Explain", key=f"explain_{alert.bucket_id}_{alert.alert_type.value}"):
                st.session_state[f"show_explain_{alert.bucket_id}"] = True
        with col2:
            if st.button("Dismiss 7d", key=f"dismiss_{alert.bucket_id}_{alert.alert_type.value}"):
                st.info("Alert dismissed for 7 days")
        with col3:
            if st.button("Watch", key=f"watch_{alert.bucket_id}_{alert.alert_type.value}"):
                st.success("Added to watchlist")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_bucket_dashboard_integration.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add modules/bucket_dashboard.py tests/test_bucket_dashboard_integration.py
git commit -m "feat: integrate enhanced alert cards with persistence into dashboard"
```

---

## Task 6: Integrate Explain Drawer into Bucket Detail View

**Files:**
- Modify: `modules/bucket_dashboard.py:1650-1800` (render_bucket_detail)

Add the explainability drawer to the bucket detail view.

**Step 1: Add import at top of bucket_dashboard.py**

```python
from modules.components.explain_drawer import ExplainDrawerRenderer, build_explain_drawer_data
```

**Step 2: Modify render_bucket_detail function**

Find the existing explainability section (around line 1783-1799) and replace with:

```python
    # === EXPLAINABILITY DRAWER (ENHANCED) ===
    with st.expander("📊 **Evidence & Explainability**", expanded=False):
        # Build drawer data
        signal_history = {}  # TODO: Load from historical_baselines if available

        # Try to get historical data
        try:
            from utils.historical_baselines import HistoricalBaselineCalculator
            baseline_calc = HistoricalBaselineCalculator()

            for signal in ["tms", "ccs", "nas", "eis"]:
                history = baseline_calc.get_signal_history(profile.bucket_id, signal, weeks=8)
                if history:
                    signal_history[signal] = history
        except Exception:
            pass  # Gracefully handle missing historical data

        # Get alert info if present
        alert_info = None
        if alerts:
            bucket_alerts = [a for a in alerts if a.bucket_id == profile.bucket_id]
            if bucket_alerts:
                alert_info = {
                    "alert_type": bucket_alerts[0].alert_type.value,
                    "rationale": bucket_alerts[0].rationale,
                }

        # Build and render drawer
        profile_dict = {
            "bucket_id": profile.bucket_id,
            "bucket_name": profile.bucket_name,
            "tms": profile.tms,
            "ccs": profile.ccs,
            "nas": profile.nas,
            "eis_offensive": profile.eis_offensive,
            "signal_confidence": profile.signal_confidence,
            "signal_metadata": getattr(profile, "signal_metadata", {}),
            "top_technical_entities": profile.top_technical_entities,
            "top_capital_entities": profile.top_capital_entities,
        }

        drawer_data = build_explain_drawer_data(profile_dict, signal_history, alert_info)
        drawer_renderer = ExplainDrawerRenderer()
        drawer_renderer.render(drawer_data, st)
```

**Step 3: Commit**

```bash
git add modules/bucket_dashboard.py
git commit -m "feat: integrate explain drawer into bucket detail view"
```

---

## Task 7: Add Confidence Visual Encoding to Quadrant Chart

**Files:**
- Modify: `modules/bucket_dashboard.py:710-800` (create_enhanced_quadrant)

Update the quadrant chart to use confidence-based visual encoding.

**Step 1: Add confidence-based marker styling**

In `create_enhanced_quadrant`, modify the marker creation section to include confidence styling:

```python
    # Inside the loop for plotting profiles, update marker style based on confidence:

    for p in full_data:
        # Get confidence style
        from utils.dashboard_helpers import get_confidence_style
        conf_style = get_confidence_style(p.signal_confidence)

        # Marker opacity based on confidence
        marker_opacity = conf_style["opacity"]

        # Border style: solid for high confidence, dashed for low
        if conf_style["border_style"] == "dashed":
            marker_line = dict(width=2, color="white", dash="dot")
        else:
            marker_line = dict(width=1, color="white")

        # Add "?" badge annotation for missing data
        if conf_style["badge"]:
            fig.add_annotation(
                x=p.tms,
                y=p.ccs,
                text="?",
                font=dict(size=12, color="#666"),
                showarrow=False,
                yshift=15,
            )
```

**Step 2: Commit**

```bash
git add modules/bucket_dashboard.py
git commit -m "feat: add confidence visual encoding to quadrant chart"
```

---

## Task 8: Add Historical Baseline Context to Signals

**Files:**
- Modify: `modules/bucket_dashboard.py:1728-1770` (signal scores section)

Add 12w/26w percentile context to signal display.

**Step 1: Modify the signal display section**

Update the signal scores display to show historical percentiles:

```python
        # === SIGNAL SCORES WITH HISTORICAL CONTEXT ===
        st.markdown("**Subscores** (with confidence & historical context)")

        # Try to load historical baselines
        baseline_calc = None
        try:
            from utils.historical_baselines import HistoricalBaselineCalculator
            baseline_calc = HistoricalBaselineCalculator()
        except Exception:
            pass

        signal_data = [
            ("tms", labels["tms"], profile.tms, "Technical"),
            ("ccs", labels["ccs"], profile.ccs, "Capital"),
            ("eis", labels["eis_off"], profile.eis_offensive, "Enterprise"),
            ("nas", labels["nas"], profile.nas, "Narrative"),
        ]

        for signal_key, name, score, signal_type in signal_data:
            if score is not None:
                # Get confidence from metadata
                meta = profile.signal_metadata.get(signal_key, {})
                confidence = meta.get("confidence", profile.signal_confidence)

                # Get historical percentile
                percentile_12w = None
                percentile_26w = None
                if baseline_calc:
                    try:
                        percentile_12w = baseline_calc.compute_historical_percentile(
                            profile.bucket_id, signal_key, score, window_weeks=12
                        )
                        percentile_26w = baseline_calc.compute_historical_percentile(
                            profile.bucket_id, signal_key, score, window_weeks=26
                        )
                    except Exception:
                        pass

                # Color code confidence
                conf_style = get_confidence_style(confidence)

                # Build percentile text
                percentile_text = ""
                if percentile_12w is not None:
                    percentile_text = f" | 12w: p{percentile_12w:.0f}"
                if percentile_26w is not None:
                    percentile_text += f" | 26w: p{percentile_26w:.0f}"

                st.markdown(
                    f"**{name}:** {score:.0f} "
                    f"<span style='color:{conf_style['color']}; font-size:0.8em;'>({conf_style['label']} conf){percentile_text}</span>",
                    unsafe_allow_html=True
                )
                st.progress(score / 100)
            else:
                st.caption(f"{name}: N/A (no data)")
```

**Step 2: Commit**

```bash
git add modules/bucket_dashboard.py
git commit -m "feat: add historical baseline percentiles to signal display"
```

---

## Task 9: Run Full Integration Test

**Files:**
- Test: Run full test suite

**Step 1: Run all tests**

```bash
pytest tests/ -v --tb=short
```

Expected: All tests pass

**Step 2: Manual smoke test**

```bash
cd c:\Users\admin\briefAI
streamlit run app.py
```

Navigate to the Trend Bucket Radar tab and verify:
- [ ] Alert cards show confidence bars
- [ ] Alert cards show evidence counts
- [ ] Alert cards show persistence duration
- [ ] Bucket detail shows sparklines in explain drawer
- [ ] Quadrant chart markers have confidence-based opacity
- [ ] Signal scores show historical percentiles

**Step 3: Final commit**

```bash
git add -A
git commit -m "test: verify full frontend trust enhancement integration"
```

---

## Summary

| Task | Component | Key Changes |
|------|-----------|-------------|
| 1 | `utils/dashboard_helpers.py` | Confidence encoding, sparkline generation |
| 2 | `utils/dashboard_helpers.py` | Plotly sparkline figures |
| 3 | `modules/components/alert_card.py` | Enhanced alert card with HTML rendering |
| 4 | `modules/components/explain_drawer.py` | Bucket explain drawer with sparklines |
| 5 | `modules/bucket_dashboard.py` | Integrate alert cards into panel |
| 6 | `modules/bucket_dashboard.py` | Integrate explain drawer into detail view |
| 7 | `modules/bucket_dashboard.py` | Confidence visual encoding in quadrant |
| 8 | `modules/bucket_dashboard.py` | Historical percentiles in signals |
| 9 | Full integration | Test suite verification |