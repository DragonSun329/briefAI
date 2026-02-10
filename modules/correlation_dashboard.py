"""
Correlation Dashboard - Streamlit Components

Visualization components for cross-entity correlation analysis:
- Interactive correlation heatmap
- Time series of rolling correlations
- Network graph of entity relationships
- Lead-lag waterfall chart
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, date, timedelta
import json

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

# Import correlation utilities
from utils.correlation_analysis import (
    CorrelationAnalyzer, 
    SECTOR_DEFINITIONS,
    EntityCorrelation,
    LeadLagRelationship
)
from utils.rolling_correlations import (
    RollingCorrelationTracker,
    CorrelationRegimeChange,
    CorrelationDivergenceAlert
)


def get_correlation_analyzer() -> CorrelationAnalyzer:
    """Get or create CorrelationAnalyzer instance."""
    return CorrelationAnalyzer()


def get_rolling_tracker() -> RollingCorrelationTracker:
    """Get or create RollingCorrelationTracker instance."""
    return RollingCorrelationTracker()


# =============================================================================
# Translation Support
# =============================================================================

TRANSLATIONS = {
    "en": {
        "title": "Correlation Analysis",
        "subtitle": "Cross-entity signal relationships",
        "entity_matrix": "Entity Correlation Matrix",
        "sector_heatmap": "Sector Correlation Heatmap",
        "rolling_correlations": "Rolling Correlations",
        "lead_lag": "Lead-Lag Relationships",
        "regime_changes": "Regime Changes",
        "divergence_alerts": "Divergence Alerts",
        "network_graph": "Entity Relationship Network",
        "select_entities": "Select Entities",
        "select_signal": "Signal Type",
        "select_window": "Window (days)",
        "no_data": "No correlation data available. Run correlation analysis first.",
        "correlation": "Correlation",
        "leader": "Leader",
        "follower": "Follower",
        "lag_days": "Lag (days)",
        "confidence": "Confidence",
        "predictive_power": "Predictive Power",
        "critical": "Critical",
        "warning": "Warning",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "refresh": "Refresh Analysis",
    },
    "zh": {
        "title": "相关性分析",
        "subtitle": "跨实体信号关系",
        "entity_matrix": "实体相关性矩阵",
        "sector_heatmap": "行业相关性热力图",
        "rolling_correlations": "滚动相关性",
        "lead_lag": "领先-滞后关系",
        "regime_changes": "制度变化",
        "divergence_alerts": "分歧警报",
        "network_graph": "实体关系网络",
        "select_entities": "选择实体",
        "select_signal": "信号类型",
        "select_window": "窗口（天）",
        "no_data": "无相关性数据。请先运行相关性分析。",
        "correlation": "相关性",
        "leader": "领先者",
        "follower": "跟随者",
        "lag_days": "滞后（天）",
        "confidence": "置信度",
        "predictive_power": "预测能力",
        "critical": "严重",
        "warning": "警告",
        "high": "高",
        "medium": "中",
        "low": "低",
        "refresh": "刷新分析",
    },
}


# =============================================================================
# Visualization Components
# =============================================================================

def render_correlation_heatmap(
    corr_matrix: pd.DataFrame,
    title: str = "Entity Correlation Matrix",
    height: int = 600
) -> go.Figure:
    """
    Render interactive correlation heatmap.
    
    Args:
        corr_matrix: Correlation matrix DataFrame
        title: Chart title
        height: Chart height
        
    Returns:
        Plotly Figure
    """
    if corr_matrix.empty:
        return None
    
    # Create heatmap
    fig = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=corr_matrix.columns.tolist(),
        y=corr_matrix.index.tolist(),
        colorscale=[
            [0, '#d32f2f'],      # Strong negative (red)
            [0.25, '#ff8a65'],   # Weak negative (light red)
            [0.5, '#ffffff'],    # Zero (white)
            [0.75, '#66bb6a'],   # Weak positive (light green)
            [1, '#2e7d32'],      # Strong positive (green)
        ],
        zmid=0,
        zmin=-1,
        zmax=1,
        text=[[f'{val:.2f}' for val in row] for row in corr_matrix.values],
        texttemplate='%{text}',
        textfont={"size": 10},
        hovertemplate='%{x} vs %{y}<br>Correlation: %{z:.3f}<extra></extra>',
    ))
    
    fig.update_layout(
        title=title,
        height=height,
        xaxis_title="Entity",
        yaxis_title="Entity",
        xaxis={'side': 'bottom', 'tickangle': 45},
        yaxis={'autorange': 'reversed'},
        margin=dict(l=100, r=20, t=50, b=100),
    )
    
    return fig


def render_sector_heatmap(
    sector_matrix: pd.DataFrame,
    title: str = "Sector Correlation Heatmap",
    height: int = 500
) -> go.Figure:
    """
    Render sector correlation heatmap with sector descriptions.
    """
    if sector_matrix.empty:
        return None
    
    # Map sector IDs to readable names
    sector_names = {
        "ai_infrastructure": "AI Infrastructure",
        "ai_hyperscalers": "Hyperscalers",
        "ai_applications": "AI Applications",
        "ai_pure_play": "Pure-Play AI",
        "ai_security": "AI Security",
        "ai_data": "AI Data",
        "ai_robotics": "AI Robotics",
    }
    
    # Rename columns and index
    display_matrix = sector_matrix.copy()
    display_matrix.columns = [sector_names.get(c, c) for c in display_matrix.columns]
    display_matrix.index = [sector_names.get(i, i) for i in display_matrix.index]
    
    fig = go.Figure(data=go.Heatmap(
        z=display_matrix.values,
        x=display_matrix.columns.tolist(),
        y=display_matrix.index.tolist(),
        colorscale='RdYlGn',
        zmid=0,
        zmin=-1,
        zmax=1,
        text=[[f'{val:.2f}' for val in row] for row in display_matrix.values],
        texttemplate='%{text}',
        textfont={"size": 12},
        hovertemplate='%{x} vs %{y}<br>Correlation: %{z:.3f}<extra></extra>',
    ))
    
    fig.update_layout(
        title=title,
        height=height,
        xaxis={'side': 'bottom', 'tickangle': 45},
        yaxis={'autorange': 'reversed'},
        margin=dict(l=150, r=20, t=50, b=150),
    )
    
    return fig


def render_rolling_correlation_chart(
    entity_a: str,
    entity_b: str,
    window_days: int = 30,
    history_days: int = 180,
    height: int = 400
) -> go.Figure:
    """
    Render time series chart of rolling correlations.
    """
    tracker = get_rolling_tracker()
    
    # Get or calculate rolling correlations
    df = tracker.get_rolling_correlation_history(
        entity_a, entity_b, "composite", window_days, history_days
    )
    
    if df.empty:
        # Try calculating if not in database
        correlations = tracker.calculate_rolling_correlation_series(
            entity_a, entity_b, "composite", window_days, history_days
        )
        if correlations:
            df = pd.DataFrame([
                {"date": c.date, "correlation": c.correlation}
                for c in correlations
            ])
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
    
    if df.empty:
        return None
    
    fig = go.Figure()
    
    # Main correlation line
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['correlation'],
        mode='lines',
        name=f'{window_days}d Rolling Correlation',
        line=dict(color='#2196F3', width=2),
        fill='tozeroy',
        fillcolor='rgba(33, 150, 243, 0.1)',
    ))
    
    # Add threshold lines
    fig.add_hline(y=0.5, line_dash="dash", line_color="green", 
                  annotation_text="Strong Positive (0.5)")
    fig.add_hline(y=-0.5, line_dash="dash", line_color="red",
                  annotation_text="Strong Negative (-0.5)")
    fig.add_hline(y=0, line_dash="dot", line_color="gray")
    
    fig.update_layout(
        title=f"Rolling Correlation: {entity_a.upper()} vs {entity_b.upper()}",
        height=height,
        xaxis_title="Date",
        yaxis_title="Correlation",
        yaxis=dict(range=[-1.1, 1.1]),
        hovermode='x unified',
    )
    
    return fig


def render_multi_window_correlation_chart(
    entity_a: str,
    entity_b: str,
    history_days: int = 180,
    height: int = 450
) -> go.Figure:
    """
    Render correlation chart with multiple window sizes.
    Shows 7-day, 30-day, and 90-day rolling correlations.
    """
    tracker = get_rolling_tracker()
    
    windows = [7, 30, 90]
    colors = ['#FF5722', '#2196F3', '#4CAF50']
    names = ['7-day', '30-day', '90-day']
    
    fig = go.Figure()
    
    for window, color, name in zip(windows, colors, names):
        correlations = tracker.calculate_rolling_correlation_series(
            entity_a, entity_b, "composite", window, history_days
        )
        
        if correlations:
            dates = [c.date for c in correlations]
            values = [c.correlation for c in correlations]
            
            fig.add_trace(go.Scatter(
                x=dates,
                y=values,
                mode='lines',
                name=name,
                line=dict(color=color, width=2 if window == 30 else 1),
            ))
    
    if not fig.data:
        return None
    
    fig.add_hline(y=0, line_dash="dot", line_color="gray")
    
    fig.update_layout(
        title=f"Multi-Window Correlation: {entity_a.upper()} vs {entity_b.upper()}",
        height=height,
        xaxis_title="Date",
        yaxis_title="Correlation",
        yaxis=dict(range=[-1.1, 1.1]),
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
    )
    
    return fig


def render_lead_lag_waterfall(
    relationships: List[LeadLagRelationship],
    height: int = 500
) -> go.Figure:
    """
    Render waterfall chart showing lead-lag relationships.
    """
    if not relationships:
        return None
    
    # Sort by predictive power
    sorted_rels = sorted(relationships, key=lambda x: x.predictive_power, reverse=True)[:15]
    
    labels = [f"{r.leader_entity.upper()} → {r.follower_entity.upper()}" for r in sorted_rels]
    lags = [r.optimal_lag_days for r in sorted_rels]
    powers = [r.predictive_power for r in sorted_rels]
    confidences = [r.confidence for r in sorted_rels]
    
    # Color by confidence
    colors = ['#2e7d32' if c == 'high' else '#1976d2' if c == 'medium' else '#757575' 
              for c in confidences]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=labels,
        y=lags,
        marker_color=colors,
        text=[f'{l}d<br>PP:{p:.2f}' for l, p in zip(lags, powers)],
        textposition='outside',
        hovertemplate='%{x}<br>Lag: %{y} days<extra></extra>',
    ))
    
    fig.update_layout(
        title="Lead-Lag Relationships (Signal Propagation)",
        height=height,
        xaxis_title="Entity Pair (Leader → Follower)",
        yaxis_title="Lag (Days)",
        xaxis={'tickangle': 45},
        showlegend=False,
    )
    
    # Add legend annotations
    fig.add_annotation(
        text="🟢 High Confidence  🔵 Medium  ⚪ Low",
        xref="paper", yref="paper",
        x=0.5, y=1.1,
        showarrow=False,
        font=dict(size=10),
    )
    
    return fig


def render_entity_network_graph(
    correlations: List[EntityCorrelation],
    min_correlation: float = 0.3,
    height: int = 600
) -> go.Figure:
    """
    Render network graph showing entity relationships.
    
    Nodes are entities, edges are correlations.
    Edge color and thickness represent correlation strength/direction.
    """
    if not correlations:
        return None
    
    # Filter significant correlations
    filtered = [c for c in correlations if abs(c.correlation) >= min_correlation]
    
    if not filtered:
        return None
    
    # Build node list
    entities = set()
    for c in filtered:
        entities.add(c.entity_a)
        entities.add(c.entity_b)
    
    entities = list(entities)
    entity_to_idx = {e: i for i, e in enumerate(entities)}
    
    # Position nodes in a circle
    n = len(entities)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    node_x = np.cos(angles) * 10
    node_y = np.sin(angles) * 10
    
    fig = go.Figure()
    
    # Add edges (correlations)
    for corr in filtered:
        i = entity_to_idx[corr.entity_a]
        j = entity_to_idx[corr.entity_b]
        
        # Color: green for positive, red for negative
        if corr.correlation > 0:
            color = f'rgba(46, 125, 50, {min(abs(corr.correlation), 1)})'
        else:
            color = f'rgba(211, 47, 47, {min(abs(corr.correlation), 1)})'
        
        width = 1 + abs(corr.correlation) * 3
        
        fig.add_trace(go.Scatter(
            x=[node_x[i], node_x[j]],
            y=[node_y[i], node_y[j]],
            mode='lines',
            line=dict(color=color, width=width),
            hoverinfo='text',
            text=f"{corr.entity_a} ↔ {corr.entity_b}: {corr.correlation:.2f}",
            showlegend=False,
        ))
    
    # Add nodes
    fig.add_trace(go.Scatter(
        x=node_x,
        y=node_y,
        mode='markers+text',
        marker=dict(size=30, color='#1976d2', line=dict(width=2, color='white')),
        text=[e.upper()[:6] for e in entities],
        textposition='middle center',
        textfont=dict(color='white', size=8),
        hovertext=entities,
        hoverinfo='text',
        showlegend=False,
    ))
    
    fig.update_layout(
        title="Entity Relationship Network",
        height=height,
        showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor='white',
    )
    
    # Add legend annotation
    fig.add_annotation(
        text="🟢 Positive Correlation  🔴 Negative Correlation<br>Line thickness = correlation strength",
        xref="paper", yref="paper",
        x=0.5, y=-0.1,
        showarrow=False,
        font=dict(size=10),
    )
    
    return fig


def render_regime_change_table(
    changes: List[CorrelationRegimeChange],
    language: str = "en"
) -> None:
    """Render regime changes as a styled table."""
    labels = TRANSLATIONS.get(language, TRANSLATIONS["en"])
    
    if not changes:
        st.info("No recent regime changes detected.")
        return
    
    for change in changes:
        # Determine icon and color
        if change.change_type == "reversal":
            icon, color = "🔄", "red"
        elif change.change_type == "breakdown":
            icon, color = "💔", "orange"
        else:
            icon, color = "🔗", "green"
        
        with st.container():
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown(f"**{icon} {change.entity_a.upper()} ↔ {change.entity_b.upper()}**")
                st.caption(f"{change.change_type.title()} | {change.detected_date}")
                st.markdown(f"_{change.actionable_insight}_")
            
            with col2:
                delta = change.current_correlation - change.previous_correlation
                st.metric(
                    "Correlation",
                    f"{change.current_correlation:.2f}",
                    f"{delta:+.2f}",
                    delta_color="inverse" if change.change_type == "breakdown" else "normal"
                )
            
            st.divider()


def render_divergence_alerts(
    alerts: List[CorrelationDivergenceAlert],
    language: str = "en"
) -> None:
    """Render divergence alerts with severity indicators."""
    labels = TRANSLATIONS.get(language, TRANSLATIONS["en"])
    
    if not alerts:
        st.success("✅ No active divergence alerts.")
        return
    
    # Group by alert level
    critical = [a for a in alerts if a.alert_level == "critical"]
    warnings = [a for a in alerts if a.alert_level == "warning"]
    
    if critical:
        st.error(f"🚨 {len(critical)} Critical Alerts")
        for alert in critical:
            with st.expander(f"{alert.entity_a.upper()} ↔ {alert.entity_b.upper()}", expanded=True):
                st.markdown(alert.alert_message)
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Historical", f"{alert.historical_correlation:.2f}")
                col2.metric("Recent", f"{alert.recent_correlation:.2f}")
                col3.metric("Divergence", f"{alert.divergence_magnitude:.2f}")
    
    if warnings:
        st.warning(f"⚠️ {len(warnings)} Warning Alerts")
        for alert in warnings:
            with st.expander(f"{alert.entity_a.upper()} ↔ {alert.entity_b.upper()}"):
                st.markdown(alert.alert_message)
                
                col1, col2 = st.columns(2)
                col1.metric("Historical", f"{alert.historical_correlation:.2f}")
                col2.metric("Recent", f"{alert.recent_correlation:.2f}")


# =============================================================================
# Main Dashboard Component
# =============================================================================

def render_correlation_tab(language: str = "en"):
    """
    Render the full Correlation Analysis tab.
    
    Args:
        language: Display language ("en" or "zh")
    """
    labels = TRANSLATIONS.get(language, TRANSLATIONS["en"])
    
    st.header(labels["title"])
    st.caption(labels["subtitle"])
    
    # Initialize analyzers
    analyzer = get_correlation_analyzer()
    tracker = get_rolling_tracker()
    
    # Sidebar controls
    with st.sidebar:
        st.subheader("⚙️ Analysis Settings")
        
        signal_type = st.selectbox(
            labels["select_signal"],
            options=["composite", "media", "financial", "technical", "product"],
            index=0
        )
        
        window_days = st.selectbox(
            labels["select_window"],
            options=[7, 30, 90],
            index=1
        )
        
        if st.button(labels["refresh"], type="primary"):
            st.cache_data.clear()
            st.rerun()
    
    # Main content tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        f"📊 {labels['entity_matrix']}",
        f"📈 {labels['rolling_correlations']}",
        f"🔗 {labels['lead_lag']}",
        f"⚠️ {labels['divergence_alerts']}",
    ])
    
    # Tab 1: Entity Correlation Matrix
    with tab1:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader(labels["entity_matrix"])
            
            # Get correlation matrix
            matrix = analyzer.get_full_correlation_matrix(signal_type)
            
            if matrix.empty:
                st.info(labels["no_data"])
            else:
                fig = render_correlation_heatmap(matrix, title="")
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Show top correlations
                    st.subheader("Top Correlations")
                    top_corrs = []
                    for i in range(len(matrix.index)):
                        for j in range(i+1, len(matrix.columns)):
                            top_corrs.append({
                                "Pair": f"{matrix.index[i]} ↔ {matrix.columns[j]}",
                                "Correlation": matrix.iloc[i, j]
                            })
                    
                    top_df = pd.DataFrame(top_corrs)
                    top_df = top_df.reindex(top_df['Correlation'].abs().sort_values(ascending=False).index)
                    st.dataframe(top_df.head(10), use_container_width=True)
        
        with col2:
            st.subheader(labels["sector_heatmap"])
            
            sector_matrix = analyzer.get_sector_heatmap()
            
            if sector_matrix.empty:
                st.info("Run sector correlation analysis first.")
            else:
                fig = render_sector_heatmap(sector_matrix, title="", height=400)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
    
    # Tab 2: Rolling Correlations
    with tab2:
        st.subheader(labels["rolling_correlations"])
        
        col1, col2 = st.columns(2)
        
        with col1:
            entity_a = st.text_input("Entity A", value="nvidia", key="roll_entity_a")
        with col2:
            entity_b = st.text_input("Entity B", value="amd", key="roll_entity_b")
        
        if entity_a and entity_b:
            # Multi-window chart
            fig = render_multi_window_correlation_chart(
                entity_a.lower(), entity_b.lower(), 
                history_days=180
            )
            
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning(f"No data available for {entity_a} vs {entity_b}")
            
            # Regime change detection
            st.subheader(labels["regime_changes"])
            
            changes = tracker.detect_regime_changes(
                entity_a.lower(), entity_b.lower(), 
                signal_type, window_days
            )
            
            if changes:
                render_regime_change_table(changes, language)
            else:
                st.success("No regime changes detected for this pair.")
    
    # Tab 3: Lead-Lag Relationships
    with tab3:
        st.subheader(labels["lead_lag"])
        
        # Get all lead-lag relationships
        relationships = analyzer.get_all_lead_lag_relationships(
            min_predictive_power=0.05,
            min_confidence="low"
        )
        
        if relationships:
            # Waterfall chart
            fig = render_lead_lag_waterfall(relationships)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            
            # Detailed table
            st.subheader("Lead-Lag Details")
            
            df = pd.DataFrame([
                {
                    labels["leader"]: r.leader_entity.upper(),
                    labels["follower"]: r.follower_entity.upper(),
                    labels["lag_days"]: r.optimal_lag_days,
                    labels["correlation"]: f"{r.correlation_at_lag:.2f}",
                    labels["predictive_power"]: f"{r.predictive_power:.2f}",
                    labels["confidence"]: r.confidence.title(),
                }
                for r in relationships
            ])
            
            st.dataframe(df, use_container_width=True)
            
            # Network visualization
            st.subheader(labels["network_graph"])
            
            # Convert to EntityCorrelation for network graph
            entity_corrs = []
            for r in relationships:
                entity_corrs.append(EntityCorrelation(
                    entity_a=r.leader_entity,
                    entity_b=r.follower_entity,
                    signal_type=r.signal_type,
                    correlation=r.correlation_at_lag,
                    sample_size=0,
                    window_days=30
                ))
            
            fig = render_entity_network_graph(entity_corrs, min_correlation=0.2)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No lead-lag relationships found. Run analysis first.")
    
    # Tab 4: Divergence Alerts
    with tab4:
        st.subheader(labels["divergence_alerts"])
        
        # Get active alerts
        alerts = tracker.get_active_divergence_alerts()
        
        render_divergence_alerts(alerts, language)
        
        # Recent regime changes
        st.subheader(f"📊 Recent {labels['regime_changes']}")
        
        recent_changes = tracker.get_recent_regime_changes(days=14)
        
        if recent_changes:
            render_regime_change_table(recent_changes, language)
        else:
            st.info("No recent regime changes detected.")


def render_correlation_widget(
    entity_id: str,
    language: str = "en"
) -> None:
    """
    Render a compact correlation widget for a single entity.
    
    Useful for embedding in entity detail pages.
    """
    labels = TRANSLATIONS.get(language, TRANSLATIONS["en"])
    analyzer = get_correlation_analyzer()
    
    # Get correlations for this entity
    correlations = analyzer.get_entity_correlations(entity_id, min_correlation=0.3)
    
    if not correlations:
        st.caption("No significant correlations found.")
        return
    
    st.subheader(f"🔗 Correlated Entities")
    
    for corr in correlations[:5]:
        other = corr.entity_b if corr.entity_a == entity_id else corr.entity_a
        
        color = "green" if corr.correlation > 0 else "red"
        icon = "📈" if corr.correlation > 0 else "📉"
        
        col1, col2 = st.columns([3, 1])
        col1.markdown(f"{icon} **{other.upper()}**")
        col2.markdown(f":{color}[{corr.correlation:.2f}]")
    
    # Lead-lag info
    lead_lag = analyzer.get_lead_lag_for_entity(entity_id)
    
    if lead_lag["as_leader"]:
        st.caption(f"⏩ Leads: {', '.join([r.follower_entity.upper() for r in lead_lag['as_leader'][:3]])}")
    
    if lead_lag["as_follower"]:
        st.caption(f"⏪ Follows: {', '.join([r.leader_entity.upper() for r in lead_lag['as_follower'][:3]])}")


if __name__ == "__main__":
    # Standalone test
    st.set_page_config(page_title="Correlation Dashboard", layout="wide")
    render_correlation_tab("en")
