"""
Alert Dashboard Module

Streamlit component for displaying and managing alerts.
Shows:
- Active alerts (unacknowledged)
- Alert history
- Alert statistics
- Rule management UI
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import json

from utils.alert_engine import (
    AlertEngine, Alert, AlertType, AlertSeverity, AlertCategory
)
from utils.alert_rules import (
    AlertRulesEngine, AlertRule, Condition, ConditionGroup, 
    Operator, LogicOp, create_rule_from_natural_language
)


# Color mappings
SEVERITY_COLORS = {
    "critical": "#9b59b6",
    "high": "#e74c3c",
    "medium": "#f39c12",
    "low": "#3498db",
}

CATEGORY_COLORS = {
    "opportunity": "#27ae60",
    "risk": "#e74c3c",
    "watch": "#f39c12",
    "informational": "#3498db",
}

SEVERITY_EMOJI = {
    "critical": "🚨",
    "high": "🔴",
    "medium": "⚠️",
    "low": "ℹ️",
}

CATEGORY_EMOJI = {
    "opportunity": "💡",
    "risk": "⚠️",
    "watch": "👀",
    "informational": "📋",
}


def init_session_state():
    """Initialize session state variables."""
    if "alert_engine" not in st.session_state:
        st.session_state.alert_engine = AlertEngine()
    
    if "rules_engine" not in st.session_state:
        st.session_state.rules_engine = AlertRulesEngine(
            alert_engine=st.session_state.alert_engine
        )


def render_alert_dashboard():
    """Main entry point for alert dashboard."""
    init_session_state()
    
    st.title("🔔 Alert Dashboard")
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Active Alerts",
        "📊 Statistics",
        "⚙️ Rules",
        "📜 History",
    ])
    
    with tab1:
        render_active_alerts()
    
    with tab2:
        render_statistics()
    
    with tab3:
        render_rules_management()
    
    with tab4:
        render_alert_history()


def render_active_alerts():
    """Render active alerts section."""
    engine = st.session_state.alert_engine
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        severity_filter = st.multiselect(
            "Severity",
            options=[s.value for s in AlertSeverity],
            default=None,
            key="severity_filter"
        )
    
    with col2:
        category_filter = st.multiselect(
            "Category",
            options=[c.value for c in AlertCategory],
            default=None,
            key="category_filter"
        )
    
    with col3:
        type_filter = st.multiselect(
            "Alert Type",
            options=[t.value for t in AlertType],
            default=None,
            key="type_filter"
        )
    
    # Get alerts
    alerts = engine.get_active_alerts(limit=100)
    
    # Apply filters
    if severity_filter:
        alerts = [a for a in alerts if a.severity.value in severity_filter]
    if category_filter:
        alerts = [a for a in alerts if a.category.value in category_filter]
    if type_filter:
        alerts = [a for a in alerts if a.alert_type.value in type_filter]
    
    # Summary
    st.markdown(f"**{len(alerts)} active alerts**")
    
    # Quick actions
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("✓ Acknowledge All", key="ack_all"):
            count = engine.acknowledge_all()
            st.success(f"Acknowledged {count} alerts")
            st.rerun()
    
    # Alert cards
    if not alerts:
        st.info("No active alerts. The system is running smoothly! 🎉")
    else:
        for alert in alerts:
            render_alert_card(alert, engine)


def render_alert_card(alert: Alert, engine: AlertEngine):
    """Render a single alert card."""
    severity_color = SEVERITY_COLORS.get(alert.severity.value, "#95a5a6")
    severity_emoji = SEVERITY_EMOJI.get(alert.severity.value, "")
    category_emoji = CATEGORY_EMOJI.get(alert.category.value, "")
    
    with st.container():
        # Create a styled card
        st.markdown(
            f"""
            <div style="
                border-left: 4px solid {severity_color};
                padding: 10px 15px;
                margin: 10px 0;
                background: rgba(0,0,0,0.05);
                border-radius: 0 5px 5px 0;
            ">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 1.1em; font-weight: bold;">
                        {severity_emoji} {alert.title}
                    </span>
                    <span style="color: #666; font-size: 0.9em;">
                        {alert.created_at.strftime('%Y-%m-%d %H:%M')}
                    </span>
                </div>
                <p style="margin: 8px 0;">{alert.message}</p>
                <div style="display: flex; gap: 15px; font-size: 0.85em; color: #666;">
                    <span>🏢 {alert.entity_name}</span>
                    <span>{category_emoji} {alert.category.value.title()}</span>
                    <span>📌 {alert.alert_type.value}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Action buttons
        col1, col2, col3 = st.columns([1, 1, 6])
        with col1:
            if st.button("✓ Ack", key=f"ack_{alert.id}"):
                engine.acknowledge_alert(alert.id)
                st.rerun()
        
        with col2:
            with st.expander("📊 Details"):
                st.json(alert.data)


def render_statistics():
    """Render alert statistics."""
    engine = st.session_state.alert_engine
    stats = engine.get_stats()
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Active Alerts", stats.get("active_alerts", 0))
    with col2:
        st.metric("Last 24h", stats.get("alerts_24h", 0))
    with col3:
        st.metric("Acknowledged", stats.get("acknowledged_alerts", 0))
    with col4:
        st.metric("Total", stats.get("total_alerts", 0))
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("By Severity")
        severity_data = stats.get("by_severity", {})
        if severity_data:
            df = pd.DataFrame([
                {"Severity": k, "Count": v}
                for k, v in severity_data.items()
            ])
            fig = px.pie(
                df, 
                values="Count", 
                names="Severity",
                color="Severity",
                color_discrete_map=SEVERITY_COLORS,
            )
            fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No active alerts")
    
    with col2:
        st.subheader("By Category")
        category_data = stats.get("by_category", {})
        if category_data:
            df = pd.DataFrame([
                {"Category": k, "Count": v}
                for k, v in category_data.items()
            ])
            fig = px.pie(
                df, 
                values="Count", 
                names="Category",
                color="Category",
                color_discrete_map=CATEGORY_COLORS,
            )
            fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No active alerts")
    
    # Top entities
    st.subheader("Top Entities with Alerts")
    top_entities = stats.get("top_entities", [])
    if top_entities:
        df = pd.DataFrame(top_entities)
        fig = px.bar(
            df,
            x="entity",
            y="count",
            title="",
            color="count",
            color_continuous_scale="Reds",
        )
        fig.update_layout(
            xaxis_title="Entity",
            yaxis_title="Alert Count",
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No alert data available")


def render_rules_management():
    """Render rules management interface."""
    rules_engine = st.session_state.rules_engine
    
    # Add new rule section
    with st.expander("➕ Add New Rule", expanded=False):
        render_add_rule_form(rules_engine)
    
    # Existing rules
    st.subheader("Configured Rules")
    
    rules = list(rules_engine.rules.values())
    rules.sort(key=lambda r: (-r.priority, r.name))
    
    for rule in rules:
        render_rule_card(rule, rules_engine)


def render_add_rule_form(rules_engine: AlertRulesEngine):
    """Render form for adding a new rule."""
    st.markdown("### Quick Rule (Natural Language)")
    nl_input = st.text_input(
        "Describe your rule",
        placeholder="Alert when NVDA media_score > 8 AND momentum_7d > 20%",
        key="nl_rule_input"
    )
    
    if st.button("Create from Description", key="create_nl_rule"):
        if nl_input:
            rule = create_rule_from_natural_language(nl_input)
            if rule:
                rules_engine.add_rule(rule)
                st.success(f"Created rule: {rule.name}")
                st.rerun()
            else:
                st.error("Couldn't parse rule description. Try using explicit operators like >, <, >=.")
    
    st.markdown("---")
    st.markdown("### Manual Rule Configuration")
    
    col1, col2 = st.columns(2)
    
    with col1:
        rule_name = st.text_input("Rule Name", key="rule_name")
        rule_description = st.text_area("Description", key="rule_desc", height=100)
    
    with col2:
        rule_severity = st.selectbox(
            "Severity",
            options=[s.value for s in AlertSeverity],
            index=1,
            key="rule_severity"
        )
        rule_category = st.selectbox(
            "Category",
            options=[c.value for c in AlertCategory],
            key="rule_category"
        )
    
    st.markdown("**Conditions**")
    
    # Condition builder
    col1, col2, col3 = st.columns(3)
    
    with col1:
        signal = st.selectbox(
            "Signal",
            options=["tms", "ccs", "nas", "eis", "pms", "css", "momentum_7d", "momentum_30d", "divergence_score"],
            key="cond_signal"
        )
    
    with col2:
        operator = st.selectbox(
            "Operator",
            options=[">", ">=", "<", "<=", "==", "!="],
            key="cond_operator"
        )
    
    with col3:
        value = st.number_input("Value", value=50.0, step=5.0, key="cond_value")
    
    # Notification channels
    st.markdown("**Notification Channels**")
    channels = st.multiselect(
        "Channels",
        options=["file", "discord", "email", "slack", "desktop"],
        default=["file"],
        key="rule_channels"
    )
    
    # Save button
    if st.button("💾 Save Rule", key="save_manual_rule"):
        if rule_name:
            op_map = {
                ">": Operator.GT, ">=": Operator.GTE,
                "<": Operator.LT, "<=": Operator.LTE,
                "==": Operator.EQ, "!=": Operator.NEQ,
            }
            
            rule = AlertRule(
                id=rule_name.lower().replace(" ", "_")[:20],
                name=rule_name,
                description=rule_description,
                conditions=ConditionGroup(
                    conditions=[Condition(signal, op_map[operator], value)],
                    logic=LogicOp.AND,
                ),
                severity=AlertSeverity(rule_severity),
                category=AlertCategory(rule_category),
                channels=channels,
            )
            
            rules_engine.add_rule(rule)
            st.success(f"Created rule: {rule.name}")
            st.rerun()
        else:
            st.error("Rule name is required")


def render_rule_card(rule: AlertRule, rules_engine: AlertRulesEngine):
    """Render a single rule card."""
    severity_color = SEVERITY_COLORS.get(rule.severity.value, "#95a5a6")
    status_icon = "✅" if rule.enabled else "⏸️"
    
    with st.container():
        col1, col2, col3 = st.columns([6, 2, 2])
        
        with col1:
            st.markdown(
                f"""
                <div style="
                    border-left: 3px solid {severity_color};
                    padding: 8px 12px;
                    margin: 5px 0;
                ">
                    <strong>{status_icon} {rule.name}</strong>
                    <span style="color: #666; font-size: 0.9em; margin-left: 10px;">
                        [{rule.severity.value}]
                    </span>
                    <p style="margin: 5px 0; color: #666; font-size: 0.9em;">
                        {rule.description[:100]}...
                    </p>
                    <div style="font-size: 0.85em; color: #888;">
                        Conditions: {rule.conditions.describe()[:80]}
                        • Triggered: {rule.times_triggered} times
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        with col2:
            if st.button(
                "⏸️ Disable" if rule.enabled else "▶️ Enable",
                key=f"toggle_{rule.id}"
            ):
                rule.enabled = not rule.enabled
                rules_engine.update_rule(rule)
                st.rerun()
        
        with col3:
            if st.button("🗑️ Delete", key=f"delete_{rule.id}"):
                rules_engine.delete_rule(rule.id)
                st.rerun()


def render_alert_history():
    """Render alert history view."""
    engine = st.session_state.alert_engine
    
    # Time range filter
    col1, col2 = st.columns(2)
    with col1:
        hours = st.slider("Hours to show", min_value=1, max_value=168, value=24)
    
    with col2:
        include_ack = st.checkbox("Include acknowledged", value=True)
    
    # Get alerts
    alerts = engine.get_recent_alerts(hours=hours, limit=200)
    
    if not include_ack:
        alerts = [a for a in alerts if not a.acknowledged]
    
    st.markdown(f"**{len(alerts)} alerts in the last {hours} hours**")
    
    if not alerts:
        st.info("No alerts in this time period")
        return
    
    # Convert to DataFrame for display
    df = pd.DataFrame([
        {
            "Time": a.created_at.strftime("%Y-%m-%d %H:%M"),
            "Severity": a.severity.value,
            "Entity": a.entity_name,
            "Title": a.title[:50],
            "Type": a.alert_type.value,
            "Ack": "✓" if a.acknowledged else "",
        }
        for a in alerts
    ])
    
    # Style the dataframe
    def color_severity(val):
        colors = {
            "critical": "background-color: #9b59b6; color: white",
            "high": "background-color: #e74c3c; color: white",
            "medium": "background-color: #f39c12; color: black",
            "low": "background-color: #3498db; color: white",
        }
        return colors.get(val, "")
    
    styled_df = df.style.applymap(color_severity, subset=["Severity"])
    st.dataframe(styled_df, use_container_width=True, height=400)
    
    # Timeline visualization
    st.subheader("Alert Timeline")
    
    timeline_df = pd.DataFrame([
        {
            "time": a.created_at,
            "severity": a.severity.value,
            "entity": a.entity_name,
        }
        for a in alerts
    ])
    
    fig = px.scatter(
        timeline_df,
        x="time",
        y="entity",
        color="severity",
        color_discrete_map=SEVERITY_COLORS,
        title="",
    )
    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="Entity",
        height=300,
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)


# Standalone page entry point
if __name__ == "__main__":
    st.set_page_config(
        page_title="briefAI - Alerts",
        page_icon="🔔",
        layout="wide",
    )
    render_alert_dashboard()
