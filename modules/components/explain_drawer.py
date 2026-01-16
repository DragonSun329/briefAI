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