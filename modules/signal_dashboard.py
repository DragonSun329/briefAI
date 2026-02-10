"""
Signal Radar Dashboard Component

Streamlit component for the CEO Dashboard that displays:
- Entity signal heatmap (5 dimensions)
- Radar charts for entity profiles
- Divergence alerts (opportunities & risks)
- Top entities by composite score
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

# Import signal utilities
from utils.signal_store import SignalStore
from utils.signal_models import EntityType, SignalCategory, SignalProfile
from utils.divergence_detector import DivergenceDetector, detect_hype_cycle_position


def get_signal_store() -> SignalStore:
    """Get or create SignalStore instance."""
    db_path = Path(__file__).parent.parent / "data" / "signals.db"
    return SignalStore(str(db_path))


def render_signal_radar_tab(language: str = "en"):
    """
    Render the Signal Radar tab content.

    Args:
        language: Display language ("en" or "zh")
    """
    # Translations
    t = {
        "en": {
            "title": "Signal Radar",
            "subtitle": "Multi-dimensional AI entity analysis",
            "top_entities": "Top Entities by Composite Score",
            "divergence_alerts": "Signal Divergence Alerts",
            "opportunities": "Opportunities",
            "risks": "Risks",
            "entity_profile": "Entity Signal Profile",
            "select_entity": "Select entity to view profile",
            "no_data": "No signal data available. Run data integration first.",
            "technical": "Technical",
            "company": "Company",
            "financial": "Financial",
            "product": "Product",
            "media": "Media",
            "composite": "Composite",
            "hype_cycle": "Hype Cycle Position",
            "signal_heatmap": "Entity Signal Heatmap",
            "companies": "Companies",
            "technologies": "Technologies",
            "all_entities": "All Entities",
        },
        "zh": {
            "title": "信号雷达",
            "subtitle": "多维度AI实体分析",
            "top_entities": "综合得分Top实体",
            "divergence_alerts": "信号分歧警报",
            "opportunities": "机会",
            "risks": "风险",
            "entity_profile": "实体信号档案",
            "select_entity": "选择实体查看档案",
            "no_data": "无信号数据。请先运行数据整合。",
            "technical": "技术",
            "company": "公司",
            "financial": "财务",
            "product": "产品",
            "media": "媒体",
            "composite": "综合",
            "hype_cycle": "炒作周期位置",
            "signal_heatmap": "实体信号热力图",
            "companies": "公司",
            "technologies": "技术",
            "all_entities": "所有实体",
        },
    }

    labels = t.get(language, t["en"])

    # Get signal store
    store = get_signal_store()

    # Check if database exists and has data
    try:
        stats = store.get_stats()
    except:
        st.warning(labels["no_data"])
        return

    if stats.get("total_profiles", 0) == 0:
        st.warning(labels["no_data"])
        st.info("Run: `python -m utils.signal_integrator` to load data")
        return

    # Header
    st.header(f"📡 {labels['title']}")
    st.caption(labels["subtitle"])

    # Summary metrics row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label=f"🏢 {labels['companies']}",
            value=stats.get("entities_by_type", {}).get("company", 0)
        )

    with col2:
        st.metric(
            label=f"🔧 {labels['technologies']}",
            value=stats.get("entities_by_type", {}).get("technology", 0)
        )

    with col3:
        st.metric(
            label="📊 Profiles",
            value=stats.get("total_profiles", 0)
        )

    with col4:
        st.metric(
            label="⚠️ Divergences",
            value=stats.get("active_divergences", 0)
        )

    st.divider()

    # Layout: Top entities and Divergences side by side
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader(f"🏆 {labels['top_entities']}")

        # Entity type filter
        entity_filter = st.radio(
            "Filter by type",
            [labels["all_entities"], labels["companies"], labels["technologies"]],
            horizontal=True,
            key="entity_filter"
        )

        # Map filter to EntityType
        type_map = {
            labels["companies"]: EntityType.COMPANY,
            labels["technologies"]: EntityType.TECHNOLOGY,
        }
        selected_type = type_map.get(entity_filter)

        # Get top profiles
        profiles = store.get_top_profiles(limit=20, entity_type=selected_type)

        if profiles:
            render_entity_table(profiles, labels)
        else:
            st.info("No profiles available for this filter")

    with col_right:
        st.subheader(f"⚠️ {labels['divergence_alerts']}")
        render_divergence_alerts(store, labels)

    st.divider()

    # Entity Profile Detail Section
    st.subheader(f"🎯 {labels['entity_profile']}")

    # Get all entities for selection
    all_profiles = store.get_top_profiles(limit=100)
    entity_options = {p.entity_name: p for p in all_profiles}

    if entity_options:
        selected_name = st.selectbox(
            labels["select_entity"],
            options=list(entity_options.keys()),
            key="entity_selector"
        )

        if selected_name:
            selected_profile = entity_options[selected_name]
            render_entity_profile(selected_profile, labels)
    else:
        st.info(labels["no_data"])


def render_entity_table(profiles: List[SignalProfile], labels: Dict[str, str]):
    """Render entity ranking table with scores."""
    # Build dataframe
    data = []
    for profile in profiles:
        data.append({
            "Entity": profile.entity_name,
            "Type": profile.entity_type.value.title(),
            labels["technical"]: profile.technical_score or 0,
            labels["company"]: profile.company_score or 0,
            labels["financial"]: profile.financial_score or 0,
            labels["product"]: profile.product_score or 0,
            labels["media"]: profile.media_score or 0,
            labels["composite"]: profile.composite_score,
        })

    df = pd.DataFrame(data)

    # Style the dataframe with color gradient
    styled = df.style.background_gradient(
        subset=[labels["technical"], labels["company"], labels["financial"],
                labels["product"], labels["media"], labels["composite"]],
        cmap="RdYlGn",
        vmin=0,
        vmax=100
    ).format({
        labels["technical"]: "{:.0f}",
        labels["company"]: "{:.0f}",
        labels["financial"]: "{:.0f}",
        labels["product"]: "{:.0f}",
        labels["media"]: "{:.0f}",
        labels["composite"]: "{:.1f}",
    })

    st.dataframe(styled, hide_index=True, use_container_width=True)


def render_divergence_alerts(store: SignalStore, labels: Dict[str, str]):
    """Render divergence alerts section."""
    from utils.signal_models import DivergenceInterpretation

    # Get active divergences
    opportunities = store.get_active_divergences(
        interpretation=DivergenceInterpretation.OPPORTUNITY
    )[:5]

    risks = store.get_active_divergences(
        interpretation=DivergenceInterpretation.RISK
    )[:5]

    # Opportunities
    st.markdown(f"**🟢 {labels['opportunities']}**")
    if opportunities:
        for div in opportunities:
            with st.expander(f"📈 {div.entity_name}", expanded=False):
                st.caption(f"**{div.divergence_type.value}** | Magnitude: {div.divergence_magnitude:.0f}")
                st.write(div.interpretation_rationale)
    else:
        st.caption("No opportunities detected")

    st.markdown("---")

    # Risks
    st.markdown(f"**🔴 {labels['risks']}**")
    if risks:
        for div in risks:
            with st.expander(f"⚠️ {div.entity_name}", expanded=False):
                st.caption(f"**{div.divergence_type.value}** | Magnitude: {div.divergence_magnitude:.0f}")
                st.write(div.interpretation_rationale)
    else:
        st.caption("No risks detected")


def render_entity_profile(profile: SignalProfile, labels: Dict[str, str]):
    """Render detailed entity profile with radar chart."""
    col_chart, col_details = st.columns([2, 1])

    with col_chart:
        # Radar chart
        fig = create_radar_chart(profile, labels)
        st.plotly_chart(fig, use_container_width=True)

    with col_details:
        # Entity details
        st.markdown(f"### {profile.entity_name}")
        st.caption(f"Type: {profile.entity_type.value.title()}")

        st.markdown("**Scores**")
        scores = [
            (labels["technical"], profile.technical_score),
            (labels["company"], profile.company_score),
            (labels["financial"], profile.financial_score),
            (labels["product"], profile.product_score),
            (labels["media"], profile.media_score),
        ]

        for name, score in scores:
            if score is not None:
                # Progress bar visualization
                st.progress(score / 100, text=f"{name}: {score:.0f}")
            else:
                st.caption(f"{name}: N/A")

        st.markdown(f"**{labels['composite']}:** {profile.composite_score:.1f}")

        # Momentum if available
        if profile.momentum_7d is not None:
            delta_color = "green" if profile.momentum_7d > 0 else "red"
            st.markdown(f"**7-day momentum:** :{delta_color}[{profile.momentum_7d:+.1f}%]")

        # Hype cycle analysis
        st.markdown(f"**{labels['hype_cycle']}**")
        hype = detect_hype_cycle_position(profile)
        st.info(f"📍 {hype['phase']}\n\n{hype['description']}")


def create_radar_chart(profile: SignalProfile, labels: Dict[str, str]) -> go.Figure:
    """Create radar chart for entity profile."""
    categories = [
        labels["technical"],
        labels["company"],
        labels["financial"],
        labels["product"],
        labels["media"],
    ]

    values = [
        profile.technical_score or 0,
        profile.company_score or 0,
        profile.financial_score or 0,
        profile.product_score or 0,
        profile.media_score or 0,
    ]

    # Close the radar chart
    categories = categories + [categories[0]]
    values = values + [values[0]]

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        name=profile.entity_name,
        line_color='rgb(31, 119, 180)',
        fillcolor='rgba(31, 119, 180, 0.3)',
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickvals=[20, 40, 60, 80, 100],
            ),
        ),
        showlegend=False,
        title=f"Signal Profile: {profile.entity_name}",
        height=400,
        margin=dict(l=60, r=60, t=60, b=60),
    )

    return fig


def render_signal_heatmap(profiles: List[SignalProfile], labels: Dict[str, str]):
    """Render signal heatmap for multiple entities."""
    if not profiles:
        st.info("No profiles to display")
        return

    # Build data matrix
    entities = []
    technical = []
    company = []
    financial = []
    product = []
    media = []

    for p in profiles[:30]:  # Limit to top 30
        entities.append(p.entity_name)
        technical.append(p.technical_score or 0)
        company.append(p.company_score or 0)
        financial.append(p.financial_score or 0)
        product.append(p.product_score or 0)
        media.append(p.media_score or 0)

    # Create heatmap
    z = [technical, company, financial, product, media]
    y = [labels["technical"], labels["company"], labels["financial"],
         labels["product"], labels["media"]]

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=entities,
        y=y,
        colorscale='RdYlGn',
        zmin=0,
        zmax=100,
        text=[[f"{val:.0f}" for val in row] for row in z],
        texttemplate="%{text}",
        textfont={"size": 10},
        hovertemplate="Entity: %{x}<br>Signal: %{y}<br>Score: %{z:.0f}<extra></extra>",
    ))

    fig.update_layout(
        title=labels["signal_heatmap"],
        xaxis_title="Entity",
        yaxis_title="Signal Type",
        height=400,
        xaxis={'tickangle': 45},
    )

    st.plotly_chart(fig, use_container_width=True)


# Standalone test
if __name__ == "__main__":
    st.set_page_config(page_title="Signal Radar Test", layout="wide")
    render_signal_radar_tab("en")
