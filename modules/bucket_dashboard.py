"""
Bucket Trend Dashboard Component

Streamlit component for bucket-level AI trend analysis with:
- Radar Quadrant: TMS vs CCS scatter plot with lifecycle state coloring
- Heatmap Timeline: Bucket scores over time
- Alert Dashboard: Divergence alerts (Alpha/Hype/Enterprise zones)
- Bucket Detail View: Drill-down into individual buckets

Enhanced Features (v2):
- PMS/CSS financial signal rings on markers
- NAS heatmap background overlay
- Alert badges on bubbles
- Cluster grouping for related buckets
- Click-to-drill-down interaction
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta
import json

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

# Import bucket utilities
from utils.bucket_models import (
    BucketProfile, BucketAlert, WeeklySnapshot,
    LifecycleState, AlertType, AlertInterpretation,
    HypeCyclePhase, FiveTScore, ConfidenceInterval, DataCoverage, CoverageBadge
)
from utils.bucket_alerts import BucketAlertDetector, build_weekly_snapshot
from utils.bucket_scorers import BucketAggregator
from utils.bucket_tagger import BucketTagger

# Import alert store and card components for enhanced alert panel
from utils.alert_store import AlertStore, StoredAlert, AlertSeverity
from modules.components.alert_card import AlertCardRenderer, build_alert_card_data
from utils.dashboard_helpers import AlertCardData, format_persistence_text, get_severity_config

# Import explainability drawer for enhanced evidence display
from modules.components.explain_drawer import ExplainDrawerRenderer, build_explain_drawer_data


# =============================================================================
# HYPE CYCLE VISUALIZATION CONSTANTS
# =============================================================================

HYPE_CYCLE_POSITIONS = {
    HypeCyclePhase.INNOVATION_TRIGGER: (10, 30),
    HypeCyclePhase.PEAK_EXPECTATIONS: (30, 95),
    HypeCyclePhase.TROUGH_DISILLUSIONMENT: (50, 25),
    HypeCyclePhase.SLOPE_ENLIGHTENMENT: (70, 55),
    HypeCyclePhase.PLATEAU_PRODUCTIVITY: (90, 70),
    HypeCyclePhase.UNKNOWN: (50, 50),
}

HYPE_CYCLE_LABELS = {
    HypeCyclePhase.INNOVATION_TRIGGER: "Innovation Trigger",
    HypeCyclePhase.PEAK_EXPECTATIONS: "Peak of Inflated Expectations",
    HypeCyclePhase.TROUGH_DISILLUSIONMENT: "Trough of Disillusionment",
    HypeCyclePhase.SLOPE_ENLIGHTENMENT: "Slope of Enlightenment",
    HypeCyclePhase.PLATEAU_PRODUCTIVITY: "Plateau of Productivity",
    HypeCyclePhase.UNKNOWN: "Unknown",
}

HYPE_CYCLE_COLORS = {
    HypeCyclePhase.INNOVATION_TRIGGER: "#3498db",      # Blue
    HypeCyclePhase.PEAK_EXPECTATIONS: "#e74c3c",       # Red
    HypeCyclePhase.TROUGH_DISILLUSIONMENT: "#95a5a6",  # Gray
    HypeCyclePhase.SLOPE_ENLIGHTENMENT: "#f39c12",     # Orange
    HypeCyclePhase.PLATEAU_PRODUCTIVITY: "#27ae60",    # Green
    HypeCyclePhase.UNKNOWN: "#bdc3c7",                 # Light gray
}

COVERAGE_BADGE_ICONS = {
    CoverageBadge.FULL: ("check-circle", "#27ae60"),      # Green
    CoverageBadge.GOOD: ("check", "#f1c40f"),             # Yellow
    CoverageBadge.PARTIAL: ("alert-triangle", "#e67e22"), # Orange
    CoverageBadge.LOW: ("x-circle", "#e74c3c"),           # Red
}


# =============================================================================
# BUCKET CLUSTERS (for visual grouping)
# =============================================================================

BUCKET_CLUSTERS = {
    "Foundation & Models": ["llm-foundation", "vision-multimodal", "speech-audio", "open-source-ai"],
    "Infrastructure": ["ai-infrastructure", "ai-chips", "llm-inference", "ai-data", "ai-observability"],
    "Agents & Orchestration": ["agent-orchestration", "rag-retrieval", "fine-tuning", "synthetic-data"],
    "Applications": ["code-ai", "ai-customer", "ai-creative", "ai-search"],
    "Verticals": ["ai-healthcare", "ai-finance", "ai-enterprise", "ai-legal", "ai-education", "ai-defense"],
    "Assistants": ["ai-consumer-assistants", "ai-embedded-assistants"],
    "Research & Frontier": ["robotics-embodied", "autonomous-vehicles", "ai-science", "ai-climate", "ai-gaming"],  # Renamed from "Emerging" to avoid confusion with lifecycle state
    "Security & Safety": ["ai-security"],
}

# Reverse lookup: bucket_id -> cluster_name
BUCKET_TO_CLUSTER = {}
for cluster_name, bucket_ids in BUCKET_CLUSTERS.items():
    for bid in bucket_ids:
        BUCKET_TO_CLUSTER[bid] = cluster_name

CLUSTER_COLORS = {
    "Foundation & Models": "#e74c3c",     # Red
    "Infrastructure": "#3498db",          # Blue
    "Agents & Orchestration": "#9b59b6",  # Purple
    "Applications": "#2ecc71",            # Green
    "Verticals": "#f39c12",               # Orange
    "Assistants": "#1abc9c",              # Teal
    "Research & Frontier": "#e91e63",     # Pink (renamed from "Emerging")
    "Security & Safety": "#607d8b",       # Gray-blue
}


# =============================================================================
# LIFECYCLE STATE COLORS AND LABELS
# =============================================================================

LIFECYCLE_COLORS = {
    LifecycleState.EMERGING: "#3498db",      # Blue
    LifecycleState.VALIDATING: "#2ecc71",    # Green
    LifecycleState.ESTABLISHING: "#9b59b6",  # Purple
    LifecycleState.MAINSTREAM: "#95a5a6",    # Gray
}

LIFECYCLE_LABELS = {
    "en": {
        LifecycleState.EMERGING: "Emerging",
        LifecycleState.VALIDATING: "Validating",
        LifecycleState.ESTABLISHING: "Establishing",
        LifecycleState.MAINSTREAM: "Mainstream",
    },
    "zh": {
        LifecycleState.EMERGING: "萌芽期",
        LifecycleState.VALIDATING: "验证期",
        LifecycleState.ESTABLISHING: "建立期",
        LifecycleState.MAINSTREAM: "成熟期",
    },
}

ALERT_ICONS = {
    AlertType.ALPHA_ZONE: "diamond",       # Hidden gem
    AlertType.HYPE_ZONE: "triangle-up",    # Vaporware warning
    AlertType.ENTERPRISE_PULL: "star",     # Enterprise adoption
    AlertType.DISRUPTION_PRESSURE: "x",    # Disruption
    AlertType.ROTATION: "circle",          # Market maturation
}

ALERT_COLORS = {
    AlertInterpretation.OPPORTUNITY: "#27ae60",  # Green
    AlertInterpretation.RISK: "#e74c3c",         # Red
    AlertInterpretation.SIGNAL: "#f39c12",       # Orange
    AlertInterpretation.NEUTRAL: "#7f8c8d",      # Gray
}


# =============================================================================
# TRANSLATIONS
# =============================================================================

TRANSLATIONS = {
    "en": {
        "title": "Trend Bucket Radar",
        "subtitle": "AI trend themes analyzed by momentum, capital, and enterprise signals",
        "quadrant_title": "Tech vs Capital Quadrant",
        "quadrant_desc": "X-axis: Technical Momentum (TMS), Y-axis: Capital Conviction (CCS)",
        "heatmap_title": "Bucket Heatmap Timeline",
        "heatmap_desc": "Heat scores over time by bucket",
        "alerts_title": "Divergence Alerts",
        "opportunities": "Opportunities",
        "risks": "Risks",
        "signals": "Signals",
        "bucket_detail": "Bucket Detail",
        "select_bucket": "Select bucket to view details",
        "no_data": "No bucket data available. Run bucket scoring first.",
        "tms": "Technical Momentum",
        "ccs": "Capital Conviction",
        "eis_off": "Enterprise Offensive",
        "eis_def": "Enterprise Defensive",
        "nas": "Narrative Attention",
        "heat": "Heat Score",
        "lifecycle": "Lifecycle",
        "top_entities": "Top Entities",
        "alpha_zone": "Alpha Zone (Hidden Gems)",
        "hype_zone": "Hype Zone (Vaporware)",
        "enterprise_pull": "Enterprise Pull",
        "disruption_pressure": "Disruption Pressure",
        "rotation": "Rotation/Maturation",
        "buckets_count": "Buckets Analyzed",
        "alerts_count": "Active Alerts",
        "avg_heat": "Avg Heat Score",
    },
    "zh": {
        "title": "趋势桶雷达",
        "subtitle": "基于动量、资本和企业信号的AI趋势主题分析",
        "quadrant_title": "技术vs资本象限图",
        "quadrant_desc": "X轴: 技术动量 (TMS), Y轴: 资本信念 (CCS)",
        "heatmap_title": "桶热力图时间线",
        "heatmap_desc": "各桶随时间的热度分数",
        "alerts_title": "分歧警报",
        "opportunities": "机会",
        "risks": "风险",
        "signals": "信号",
        "bucket_detail": "桶详情",
        "select_bucket": "选择桶查看详情",
        "no_data": "无桶数据。请先运行桶评分。",
        "tms": "技术动量",
        "ccs": "资本信念",
        "eis_off": "企业进攻",
        "eis_def": "企业防守",
        "nas": "叙事关注",
        "heat": "热度分数",
        "lifecycle": "生命周期",
        "top_entities": "主要实体",
        "alpha_zone": "阿尔法区 (隐藏宝石)",
        "hype_zone": "炒作区 (虚火)",
        "enterprise_pull": "企业牵引",
        "disruption_pressure": "颠覆压力",
        "rotation": "轮动/成熟",
        "buckets_count": "分析桶数",
        "alerts_count": "活跃警报",
        "avg_heat": "平均热度",
    },
}


def get_labels(language: str = "en") -> Dict[str, str]:
    """Get translation labels for the given language."""
    return TRANSLATIONS.get(language, TRANSLATIONS["en"])


# =============================================================================
# DATA LOADING (MOCK FOR NOW - WILL CONNECT TO REAL DATA)
# =============================================================================

def load_bucket_profiles(week_start: Optional[date] = None) -> List[BucketProfile]:
    """
    Load bucket profiles from storage.

    For now, generates sample data. Will connect to real scoring pipeline.
    """
    # Try to load from cached data
    cache_path = Path(__file__).parent.parent / "data" / "cache" / "bucket_profiles.json"

    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            profiles = []
            for item in data.get("profiles", []):
                # Check coverage flags to distinguish "no data" from "zero value"
                has_tms = item.get("has_tms_data", item.get("tms") is not None)
                has_ccs = item.get("has_ccs_data", item.get("ccs") is not None)
                has_nas = item.get("has_nas_data", item.get("nas") is not None)
                has_eis = item.get("has_eis_data", item.get("eis_offensive") is not None)

                # Compute signal confidence based on data coverage
                coverage_count = sum([has_tms, has_ccs, has_nas, has_eis])
                signal_confidence = 0.4 + (coverage_count / 4.0) * 0.5  # 0.4 to 0.9

                # Parse hype cycle phase from string
                hype_phase_str = item.get("hype_cycle_phase", "unknown")
                try:
                    hype_phase = HypeCyclePhase(hype_phase_str)
                except ValueError:
                    hype_phase = HypeCyclePhase.UNKNOWN

                profile = BucketProfile(
                    bucket_id=item["bucket_id"],
                    bucket_name=item["bucket_name"],
                    week_start=datetime.fromisoformat(item["week_start"]).date() if isinstance(item["week_start"], str) else item["week_start"],
                    tms=item.get("tms") if has_tms else None,
                    ccs=item.get("ccs") if has_ccs else None,
                    eis_offensive=item.get("eis_offensive") if has_eis else None,
                    eis_defensive=item.get("eis_defensive") if has_eis else None,
                    nas=item.get("nas") if has_nas else None,
                    heat_score=item.get("heat_score", 50.0),
                    lifecycle_state=LifecycleState(item.get("lifecycle_state", "emerging")),
                    hype_cycle_phase=hype_phase,
                    hype_cycle_confidence=item.get("hype_cycle_confidence", 0.5),
                    hype_cycle_rationale=item.get("hype_cycle_rationale", ""),
                    top_technical_entities=item.get("top_technical_entities", []),
                    top_capital_entities=item.get("top_capital_entities", []),
                    top_enterprise_entities=item.get("top_enterprise_entities", []),
                    entity_count=item.get("entity_count", 0),
                    signal_confidence=signal_confidence,
                    internal_variance=15 if coverage_count < 2 else 10,  # Higher variance for low-coverage
                )
                profiles.append(profile)

            return profiles
        except Exception as e:
            st.warning(f"Could not load cached profiles: {e}")

    # Generate sample data for demonstration
    return _generate_sample_profiles(week_start)


def _generate_sample_profiles(week_start: Optional[date] = None) -> List[BucketProfile]:
    """Generate sample bucket profiles for demonstration."""
    if week_start is None:
        week_start = date.today() - timedelta(days=date.today().weekday())

    # Sample bucket data with realistic distributions
    # Added: confidence (0-1), variance, and motion vectors (tms_d4w, ccs_d4w = 4-week delta)
    # Motion interpretation: positive = moving right/up, negative = moving left/down
    sample_buckets = [
        # Alpha Zone candidates (high TMS, low CCS) - RAG moving UP (capital catching up)
        {"id": "rag-retrieval", "name": "RAG & Retrieval", "tms": 92, "ccs": 28, "eis_off": 45, "eis_def": 35, "nas": 55,
         "confidence": 0.85, "variance": 8, "tms_d4w": 3, "ccs_d4w": 12, "accel": True},
        {"id": "fine-tuning", "name": "Fine-tuning & Training", "tms": 88, "ccs": 32, "eis_off": 40, "eis_def": 30, "nas": 48,
         "confidence": 0.80, "variance": 10, "tms_d4w": -2, "ccs_d4w": 8, "accel": False},

        # Consumer AI Assistants - moving DOWN-LEFT (hype fading, no tech traction)
        {"id": "ai-consumer-assistants", "name": "Consumer AI Assistants", "tms": 22, "ccs": 88, "eis_off": 48, "eis_def": 35, "nas": 92,
         "confidence": 0.75, "variance": 15, "tms_d4w": -5, "ccs_d4w": -8, "accel": False},
        # Embedded Assistants - moving UP-RIGHT (real adoption + capital)
        {"id": "ai-embedded-assistants", "name": "Embedded & Vertical Assistants", "tms": 68, "ccs": 72, "eis_off": 78, "eis_def": 42, "nas": 65,
         "confidence": 0.82, "variance": 12, "tms_d4w": 6, "ccs_d4w": 8, "accel": True},

        # Balanced / Validating - Agent frameworks clustering then splitting
        {"id": "agent-orchestration", "name": "Agent Frameworks", "tms": 85, "ccs": 78, "eis_off": 62, "eis_def": 45, "nas": 88,
         "confidence": 0.88, "variance": 10, "tms_d4w": 4, "ccs_d4w": 5, "accel": True},
        {"id": "llm-inference", "name": "LLM Serving & Inference", "tms": 78, "ccs": 72, "eis_off": 70, "eis_def": 52, "nas": 65,
         "confidence": 0.85, "variance": 8, "tms_d4w": 2, "ccs_d4w": 3, "accel": False},
        {"id": "code-ai", "name": "AI for Code", "tms": 82, "ccs": 85, "eis_off": 75, "eis_def": 48, "nas": 92,
         "confidence": 0.90, "variance": 6, "tms_d4w": 5, "ccs_d4w": 7, "accel": True},

        # Enterprise - moving UP (CCS rising without TMS change)
        {"id": "ai-enterprise", "name": "Enterprise AI", "tms": 52, "ccs": 78, "eis_off": 88, "eis_def": 58, "nas": 62,
         "confidence": 0.78, "variance": 14, "tms_d4w": 0, "ccs_d4w": 10, "accel": True},

        # Disruption Pressure
        {"id": "ai-customer", "name": "AI Customer Experience", "tms": 48, "ccs": 55, "eis_off": 45, "eis_def": 92, "nas": 58,
         "confidence": 0.80, "variance": 10, "tms_d4w": -3, "ccs_d4w": 2, "accel": False},

        # Foundation Models - drifting LEFT (technical novelty decay)
        {"id": "llm-foundation", "name": "Foundation Models", "tms": 45, "ccs": 88, "eis_off": 85, "eis_def": 78, "nas": 95,
         "confidence": 0.92, "variance": 5, "tms_d4w": -8, "ccs_d4w": 2, "accel": False},
        {"id": "vision-multimodal", "name": "Vision & Multimodal", "tms": 55, "ccs": 65, "eis_off": 72, "eis_def": 65, "nas": 72,
         "confidence": 0.85, "variance": 8, "tms_d4w": -3, "ccs_d4w": 4, "accel": False},

        # Emerging - Robotics moving UP-RIGHT
        {"id": "robotics-embodied", "name": "Robotics & Embodied AI", "tms": 75, "ccs": 45, "eis_off": 35, "eis_def": 25, "nas": 68,
         "confidence": 0.72, "variance": 18, "tms_d4w": 8, "ccs_d4w": 12, "accel": True},
        {"id": "ai-science", "name": "AI for Science", "tms": 82, "ccs": 38, "eis_off": 28, "eis_def": 22, "nas": 45,
         "confidence": 0.70, "variance": 15, "tms_d4w": 5, "ccs_d4w": 6, "accel": True},

        # Synthetic Data - moving RIGHT (TMS rising, CCS stable)
        {"id": "synthetic-data", "name": "Synthetic Data & Eval", "tms": 82, "ccs": 45, "eis_off": 42, "eis_def": 35, "nas": 48,
         "confidence": 0.68, "variance": 18, "tms_d4w": 10, "ccs_d4w": 2, "accel": True},

        # Security - moving UP-RIGHT diagonally
        {"id": "ai-security", "name": "AI Security & Safety", "tms": 68, "ccs": 58, "eis_off": 62, "eis_def": 75, "nas": 78,
         "confidence": 0.82, "variance": 12, "tms_d4w": 6, "ccs_d4w": 8, "accel": True},
        {"id": "ai-observability", "name": "AI Observability", "tms": 78, "ccs": 42, "eis_off": 55, "eis_def": 38, "nas": 42,
         "confidence": 0.75, "variance": 12, "tms_d4w": 4, "ccs_d4w": 5, "accel": False},
        {"id": "speech-audio", "name": "Speech & Audio AI", "tms": 62, "ccs": 58, "eis_off": 52, "eis_def": 45, "nas": 55,
         "confidence": 0.80, "variance": 10, "tms_d4w": 0, "ccs_d4w": 3, "accel": False},

        # Healthcare - moving UP (CCS rising as adoption becomes inevitable)
        {"id": "ai-healthcare", "name": "AI for Healthcare", "tms": 55, "ccs": 78, "eis_off": 72, "eis_def": 58, "nas": 62,
         "confidence": 0.75, "variance": 16, "tms_d4w": 2, "ccs_d4w": 10, "accel": True},

        {"id": "ai-finance", "name": "AI for Finance", "tms": 52, "ccs": 78, "eis_off": 82, "eis_def": 68, "nas": 58,
         "confidence": 0.82, "variance": 10, "tms_d4w": -2, "ccs_d4w": 4, "accel": False},
        {"id": "ai-data", "name": "AI Data Infrastructure", "tms": 72, "ccs": 62, "eis_off": 58, "eis_def": 42, "nas": 48,
         "confidence": 0.78, "variance": 12, "tms_d4w": 3, "ccs_d4w": 5, "accel": False},
        {"id": "open-source-ai", "name": "Open Source AI", "tms": 88, "ccs": 35, "eis_off": 32, "eis_def": 28, "nas": 72,
         "confidence": 0.85, "variance": 10, "tms_d4w": 2, "ccs_d4w": 8, "accel": True},
    ]

    profiles = []
    for bucket in sample_buckets:
        # Determine lifecycle state based on scores
        tms, ccs, eis_off = bucket["tms"], bucket["ccs"], bucket["eis_off"]

        if tms > 70 and ccs < 50:
            state = LifecycleState.EMERGING
        elif tms > 60 and ccs > 50 and eis_off < 60:
            state = LifecycleState.VALIDATING
        elif eis_off > 70:
            state = LifecycleState.ESTABLISHING
        else:
            state = LifecycleState.MAINSTREAM

        # Calculate heat score
        heat = (bucket["tms"] * 0.35 + bucket["ccs"] * 0.25 +
                bucket["eis_off"] * 0.20 + bucket["nas"] * 0.20)

        profile = BucketProfile(
            bucket_id=bucket["id"],
            bucket_name=bucket["name"],
            week_start=week_start,
            tms=bucket["tms"],
            ccs=bucket["ccs"],
            eis_offensive=bucket["eis_off"],
            eis_defensive=bucket["eis_def"],
            nas=bucket["nas"],
            heat_score=heat,
            lifecycle_state=state,
            signal_confidence=bucket.get("confidence", 0.8),
            internal_variance=bucket.get("variance", 10),
            # Motion vectors (4-week momentum)
            tms_delta_4w=bucket.get("tms_d4w", 0),
            ccs_delta_4w=bucket.get("ccs_d4w", 0),
            velocity_accelerating=bucket.get("accel", False),
            top_technical_entities=["entity1", "entity2", "entity3"],
            top_capital_entities=["company1", "company2"],
            top_enterprise_entities=["enterprise1"],
            entity_count=np.random.randint(5, 50),
        )
        profiles.append(profile)

    return profiles


def load_weekly_history(weeks: int = 8) -> Dict[str, List[BucketProfile]]:
    """Load historical bucket profiles for heatmap visualization."""
    history = {}

    today = date.today()
    current_week_start = today - timedelta(days=today.weekday())

    for i in range(weeks):
        week_start = current_week_start - timedelta(weeks=i)
        profiles = load_bucket_profiles(week_start)

        for profile in profiles:
            if profile.bucket_id not in history:
                history[profile.bucket_id] = []
            history[profile.bucket_id].append(profile)

    return history


# =============================================================================
# VISUALIZATIONS
# =============================================================================

def create_tms_ccs_quadrant(
    profiles: List[BucketProfile],
    labels: Dict[str, str],
    alerts: Optional[List[BucketAlert]] = None
) -> go.Figure:
    """
    Create TMS vs CCS quadrant scatter plot.

    - X-axis: Technical Momentum Score (TMS)
    - Y-axis: Capital Conviction Score (CCS)
    - Color: Lifecycle state
    - Size: Heat score
    - Shape: Alert type (if any)
    """
    # Build alert lookup
    alert_map = {}
    if alerts:
        for alert in alerts:
            if alert.bucket_id not in alert_map:
                alert_map[alert.bucket_id] = alert

    fig = go.Figure()

    # Add quadrant zones
    # Alpha Zone (top-right of TMS axis, bottom of CCS)
    fig.add_shape(
        type="rect",
        x0=70, y0=0, x1=100, y1=40,
        fillcolor="rgba(46, 204, 113, 0.1)",
        line=dict(width=0),
        layer="below"
    )
    fig.add_annotation(
        x=85, y=20, text="Alpha Zone",
        font=dict(size=10, color="rgba(46, 204, 113, 0.7)"),
        showarrow=False
    )

    # Hype Zone (top-left of TMS, high CCS)
    fig.add_shape(
        type="rect",
        x0=0, y0=70, x1=40, y1=100,
        fillcolor="rgba(231, 76, 60, 0.1)",
        line=dict(width=0),
        layer="below"
    )
    fig.add_annotation(
        x=20, y=85, text="Hype Zone",
        font=dict(size=10, color="rgba(231, 76, 60, 0.7)"),
        showarrow=False
    )

    # Separate profiles with full data vs partial data FIRST
    full_data_profiles = [p for p in profiles if p.tms is not None and p.ccs is not None]
    partial_data_profiles = [p for p in profiles if p.tms is None or p.ccs is None]

    # First pass: Add confidence ellipses ONLY for full-data profiles with low confidence
    for p in full_data_profiles:
        # Only show ellipses for buckets with lower confidence or high variance
        if p.signal_confidence < 0.75 or p.internal_variance > 14:
            # Generate ellipse points - smaller ellipses
            variance = min(p.internal_variance, 12)  # Cap variance for visual cleanliness
            theta = np.linspace(0, 2*np.pi, 50)
            x_ellipse = p.tms + variance * np.cos(theta)
            y_ellipse = p.ccs + variance * 0.6 * np.sin(theta)  # More squashed

            # Lower opacity
            opacity = 0.08 + (1 - p.signal_confidence) * 0.12

            fig.add_trace(go.Scatter(
                x=x_ellipse,
                y=y_ellipse,
                mode="lines",
                line=dict(
                    color=LIFECYCLE_COLORS.get(p.lifecycle_state, "#888"),
                    width=1,
                    dash="dot"
                ),
                fill="toself",
                fillcolor=f"rgba(128, 128, 128, {opacity})",
                hoverinfo="skip",
                showlegend=False,
            ))

    # Plot full-data profiles grouped by lifecycle state
    for state in LifecycleState:
        state_profiles = [p for p in full_data_profiles if p.lifecycle_state == state]
        if not state_profiles:
            continue

        x_vals = [p.tms for p in state_profiles]
        y_vals = [p.ccs for p in state_profiles]
        # Size based on heat, but also factor in confidence (higher confidence = larger)
        sizes = [(p.heat_score or 50) / 3 * p.signal_confidence for p in state_profiles]
        names = [p.bucket_name for p in state_profiles]

        # Build hover text
        hover_texts = []
        for p in state_profiles:
            alert_info = ""
            if p.bucket_id in alert_map:
                alert = alert_map[p.bucket_id]
                alert_info = f"<br><b>Alert:</b> {alert.alert_type.value}"

            confidence_label = "High" if p.signal_confidence >= 0.85 else "Medium" if p.signal_confidence >= 0.75 else "Low"

            # Motion description
            tms_d = p.tms_delta_4w or 0
            ccs_d = p.ccs_delta_4w or 0
            if abs(tms_d) >= 3 or abs(ccs_d) >= 3:
                motion_dir = []
                if ccs_d > 3: motion_dir.append("UP")
                elif ccs_d < -3: motion_dir.append("DOWN")
                if tms_d > 3: motion_dir.append("RIGHT")
                elif tms_d < -3: motion_dir.append("LEFT")
                motion_str = "-".join(motion_dir) if motion_dir else "STABLE"
                accel_str = " (accelerating)" if p.velocity_accelerating else " (decelerating)"
                motion_info = f"<br><b>4W Motion:</b> {motion_str}{accel_str}"
            else:
                motion_info = "<br><b>4W Motion:</b> STABLE"

            hover_texts.append(
                f"<b>{p.bucket_name}</b><br>"
                f"TMS: {p.tms:.0f} ({tms_d:+.0f})<br>"
                f"CCS: {p.ccs:.0f} ({ccs_d:+.0f})<br>"
                f"Heat: {p.heat_score:.1f}<br>"
                f"Confidence: {confidence_label} ({p.signal_confidence:.0%})<br>"
                f"State: {state.value}{motion_info}{alert_info}"
            )

        fig.add_trace(go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="markers+text",
            marker=dict(
                size=sizes,
                color=LIFECYCLE_COLORS[state],
                opacity=0.7,
                line=dict(width=1, color="white"),
            ),
            text=names,
            textposition="top center",
            textfont=dict(size=9),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover_texts,
            name=LIFECYCLE_LABELS["en"][state],
        ))

    # For partial-data profiles: if they have at least CCS, plot them on the Y-axis
    # with X at a position based on available data. Otherwise, don't plot them on this chart.
    plottable_partial = [p for p in partial_data_profiles if p.ccs is not None]
    unplottable = [p for p in partial_data_profiles if p.ccs is None]

    if plottable_partial:
        # Plot at x=5 (left edge) with their actual CCS value on y-axis
        x_vals = [5 for _ in plottable_partial]
        y_vals = [p.ccs for p in plottable_partial]
        names = [p.bucket_name[:20] for p in plottable_partial]  # Truncate names
        sizes = [10 for _ in plottable_partial]

        hover_texts = []
        for p in plottable_partial:
            missing = []
            if p.tms is None: missing.append("TMS")
            if p.nas is None: missing.append("NAS")
            if p.eis_offensive is None: missing.append("EIS")

            hover_texts.append(
                f"<b>{p.bucket_name}</b><br>"
                f"⚠️ Missing: {', '.join(missing)}<br>"
                f"CCS: {p.ccs:.0f}<br>"
                f"Heat: {p.heat_score:.1f}<br>"
                f"<i>No TMS data - positioned by CCS only</i>"
            )

        fig.add_trace(go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="markers",
            marker=dict(
                size=sizes,
                color="#aaaaaa",
                opacity=0.6,
                symbol="diamond-open",
                line=dict(width=2, color="#666666"),
            ),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover_texts,
            name=f"No TMS Data ({len(plottable_partial)})",
            showlegend=True,
        ))

    # Note: unplottable profiles (no CCS) are not shown on this chart - they need more data

    # Third pass: Add motion vector arrows
    for p in profiles:
        # Only show arrows for buckets with significant motion
        tms_d = p.tms_delta_4w or 0
        ccs_d = p.ccs_delta_4w or 0
        magnitude = np.sqrt(tms_d**2 + ccs_d**2)

        if magnitude >= 5:  # Threshold for showing arrow
            x_start = p.tms or 0
            y_start = p.ccs or 0

            # Scale arrow length (cap at reasonable size)
            scale = min(1.0, magnitude / 15)  # Normalize to max ~15 point movement
            arrow_len = 8 * scale  # Max arrow length of 8 units

            # Calculate end point
            if magnitude > 0:
                x_end = x_start + (tms_d / magnitude) * arrow_len
                y_end = y_start + (ccs_d / magnitude) * arrow_len
            else:
                continue

            # Arrow color: green if accelerating, orange if decelerating
            arrow_color = "#27ae60" if p.velocity_accelerating else "#e67e22"

            # Draw arrow as annotation
            fig.add_annotation(
                x=x_end,
                y=y_end,
                ax=x_start,
                ay=y_start,
                xref="x",
                yref="y",
                axref="x",
                ayref="y",
                showarrow=True,
                arrowhead=2,
                arrowsize=1.2,
                arrowwidth=2,
                arrowcolor=arrow_color,
                opacity=0.7,
            )

    # Add reference lines at 50th percentile
    fig.add_hline(y=50, line_dash="dash", line_color="gray", opacity=0.5)
    fig.add_vline(x=50, line_dash="dash", line_color="gray", opacity=0.5)

    fig.update_layout(
        title=dict(
            text=labels["quadrant_title"],
            subtitle=dict(text=labels["quadrant_desc"], font=dict(size=12, color="gray"))
        ),
        xaxis=dict(
            title=labels["tms"],
            range=[0, 100],
            tickvals=[0, 25, 50, 75, 100],
        ),
        yaxis=dict(
            title=labels["ccs"],
            range=[0, 100],
            tickvals=[0, 25, 50, 75, 100],
        ),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        height=500,
        margin=dict(l=60, r=60, t=100, b=60),
    )

    return fig


def create_enhanced_quadrant(
    profiles: List[BucketProfile],
    labels: Dict[str, str],
    alerts: Optional[List[BucketAlert]] = None,
    view_mode: str = "lifecycle",  # "lifecycle", "cluster", "nas_overlay", "financial"
    show_pms_css: bool = True,
    show_nas_background: bool = False,
    show_alert_badges: bool = True,
    top_n_labels: int = 8,  # Only show labels for top N buckets by heat
) -> go.Figure:
    """
    Enhanced TMS vs CCS quadrant with additional visualizations.

    Features:
    - PMS/CSS rings around markers (financial signals)
    - NAS heatmap background overlay
    - Alert badges on bubbles
    - Cluster grouping mode
    - Motion arrows
    """
    # Build alert lookup
    alert_map = {}
    if alerts:
        for alert in alerts:
            if alert.bucket_id not in alert_map:
                alert_map[alert.bucket_id] = alert

    fig = go.Figure()

    # === NAS HEATMAP BACKGROUND (Feature 6) ===
    if show_nas_background and view_mode == "nas_overlay":
        # Create a grid for NAS intensity background
        # Buckets with high NAS create "hot spots"
        x_grid = np.linspace(0, 100, 20)
        y_grid = np.linspace(0, 100, 20)
        z_grid = np.zeros((20, 20))

        for p in profiles:
            if p.tms is not None and p.ccs is not None and p.nas is not None:
                # Add gaussian blob at bucket position based on NAS
                for i, x in enumerate(x_grid):
                    for j, y in enumerate(y_grid):
                        dist = np.sqrt((x - p.tms)**2 + (y - p.ccs)**2)
                        # NAS intensity falls off with distance
                        intensity = (p.nas / 100) * np.exp(-dist**2 / 400)
                        z_grid[j, i] += intensity * 0.3

        # Normalize
        z_grid = np.clip(z_grid, 0, 1)

        fig.add_trace(go.Heatmap(
            x=x_grid,
            y=y_grid,
            z=z_grid,
            colorscale=[[0, "rgba(255,255,255,0)"], [0.5, "rgba(255,165,0,0.15)"], [1, "rgba(255,69,0,0.3)"]],
            showscale=False,
            hoverinfo="skip",
        ))

    # === QUADRANT ZONES ===
    # Alpha Zone (high TMS, low CCS)
    fig.add_shape(
        type="rect", x0=70, y0=0, x1=100, y1=40,
        fillcolor="rgba(46, 204, 113, 0.1)", line=dict(width=0), layer="below"
    )
    fig.add_annotation(
        x=85, y=20, text="💎 Alpha Zone",
        font=dict(size=10, color="rgba(46, 204, 113, 0.8)"), showarrow=False
    )

    # Hype Zone (low TMS, high CCS)
    fig.add_shape(
        type="rect", x0=0, y0=70, x1=40, y1=100,
        fillcolor="rgba(231, 76, 60, 0.1)", line=dict(width=0), layer="below"
    )
    fig.add_annotation(
        x=20, y=85, text="⚠️ Hype Zone",
        font=dict(size=10, color="rgba(231, 76, 60, 0.8)"), showarrow=False
    )

    # Separate profiles
    full_data = [p for p in profiles if p.tms is not None and p.ccs is not None]
    partial_data = [p for p in profiles if p.tms is None or p.ccs is None]

    # === LABEL DECLUTTER: Only show labels for top N buckets by heat ===
    # Sort by heat to determine which get labels
    sorted_by_heat = sorted(full_data, key=lambda p: p.heat_score or 0, reverse=True)
    top_n_bucket_ids = {p.bucket_id for p in sorted_by_heat[:top_n_labels]}

    # Also show labels for buckets with active alerts (always important)
    alert_bucket_ids = set(alert_map.keys())
    labeled_bucket_ids = top_n_bucket_ids | alert_bucket_ids

    # === MAIN SCATTER PLOT ===
    if view_mode == "cluster":
        # Group by cluster instead of lifecycle
        clusters_used = set()
        for p in full_data:
            cluster = BUCKET_TO_CLUSTER.get(p.bucket_id, "Other")
            clusters_used.add(cluster)

        for cluster_name in sorted(clusters_used):
            cluster_profiles = [p for p in full_data if BUCKET_TO_CLUSTER.get(p.bucket_id, "Other") == cluster_name]
            if not cluster_profiles:
                continue

            color = CLUSTER_COLORS.get(cluster_name, "#888888")
            x_vals = [p.tms for p in cluster_profiles]
            y_vals = [p.ccs for p in cluster_profiles]
            sizes = [(p.heat_score or 50) / 3 for p in cluster_profiles]
            # Only show labels for top N buckets (declutter)
            names = [p.bucket_name if p.bucket_id in labeled_bucket_ids else "" for p in cluster_profiles]

            hover_texts = _build_hover_texts(cluster_profiles, alert_map, show_pms_css)

            fig.add_trace(go.Scatter(
                x=x_vals, y=y_vals,
                mode="markers+text",
                marker=dict(size=sizes, color=color, opacity=0.7, line=dict(width=1, color="white")),
                text=names, textposition="top center", textfont=dict(size=9),
                hovertemplate="%{customdata}<extra></extra>",
                customdata=hover_texts,
                name=cluster_name,
            ))
    else:
        # Default: lifecycle state grouping
        for state in LifecycleState:
            state_profiles = [p for p in full_data if p.lifecycle_state == state]
            if not state_profiles:
                continue

            x_vals = [p.tms for p in state_profiles]
            y_vals = [p.ccs for p in state_profiles]
            sizes = [(p.heat_score or 50) / 3 * p.signal_confidence for p in state_profiles]
            # Only show labels for top N buckets (declutter)
            names = [p.bucket_name if p.bucket_id in labeled_bucket_ids else "" for p in state_profiles]

            hover_texts = _build_hover_texts(state_profiles, alert_map, show_pms_css)

            fig.add_trace(go.Scatter(
                x=x_vals, y=y_vals,
                mode="markers+text",
                marker=dict(size=sizes, color=LIFECYCLE_COLORS[state], opacity=0.7, line=dict(width=1, color="white")),
                text=names, textposition="top center", textfont=dict(size=9),
                hovertemplate="%{customdata}<extra></extra>",
                customdata=hover_texts,
                name=LIFECYCLE_LABELS["en"][state],
            ))

    # === PMS/CSS FINANCIAL SIGNAL RINGS (Feature 1) ===
    if show_pms_css and view_mode == "financial":
        for p in full_data:
            pms = getattr(p, 'pms', None)
            css = getattr(p, 'css', None)

            if pms is not None and pms > 0:
                # Draw PMS ring (green for positive momentum)
                ring_size = 8 + (pms / 100) * 15  # 8-23 size range
                fig.add_trace(go.Scatter(
                    x=[p.tms], y=[p.ccs],
                    mode="markers",
                    marker=dict(
                        size=ring_size,
                        color="rgba(39, 174, 96, 0)",  # Transparent fill
                        line=dict(width=2, color="#27ae60")  # Green ring
                    ),
                    hoverinfo="skip",
                    showlegend=False,
                ))

            if css is not None and css > 0:
                # Draw CSS ring (orange for crypto signal)
                ring_size = 5 + (css / 100) * 12
                fig.add_trace(go.Scatter(
                    x=[p.tms], y=[p.ccs],
                    mode="markers",
                    marker=dict(
                        size=ring_size,
                        color="rgba(243, 156, 18, 0)",
                        line=dict(width=2, color="#f39c12", dash="dot")  # Orange dotted ring
                    ),
                    hoverinfo="skip",
                    showlegend=False,
                ))

    # === ALERT BADGES (Feature 5) ===
    if show_alert_badges and alerts:
        for alert in alerts:
            p = next((prof for prof in full_data if prof.bucket_id == alert.bucket_id), None)
            if p is None:
                continue

            badge_symbol = {
                AlertType.ALPHA_ZONE: "💎",
                AlertType.HYPE_ZONE: "⚠️",
                AlertType.ENTERPRISE_PULL: "🏢",
                AlertType.DISRUPTION_PRESSURE: "💥",
                AlertType.ROTATION: "🔄",
            }.get(alert.alert_type, "❗")

            # Position badge slightly above and to the right
            fig.add_annotation(
                x=p.tms + 3, y=p.ccs + 5,
                text=badge_symbol,
                showarrow=False,
                font=dict(size=12),
            )

    # === MOTION ARROWS (Feature 2 - already exists, kept) ===
    for p in full_data:
        tms_d = p.tms_delta_4w or 0
        ccs_d = p.ccs_delta_4w or 0
        magnitude = np.sqrt(tms_d**2 + ccs_d**2)

        if magnitude >= 5:
            scale = min(1.0, magnitude / 15)
            arrow_len = 8 * scale

            if magnitude > 0:
                x_end = p.tms + (tms_d / magnitude) * arrow_len
                y_end = p.ccs + (ccs_d / magnitude) * arrow_len

                arrow_color = "#27ae60" if p.velocity_accelerating else "#e67e22"

                fig.add_annotation(
                    x=x_end, y=y_end, ax=p.tms, ay=p.ccs,
                    xref="x", yref="y", axref="x", ayref="y",
                    showarrow=True, arrowhead=2, arrowsize=1.2, arrowwidth=2,
                    arrowcolor=arrow_color, opacity=0.7,
                )

    # === PARTIAL DATA MARKERS ===
    plottable_partial = [p for p in partial_data if p.ccs is not None]
    if plottable_partial:
        x_vals = [5 for _ in plottable_partial]
        y_vals = [p.ccs for p in plottable_partial]
        names = [p.bucket_name[:15] for p in plottable_partial]

        hover_texts = []
        for p in plottable_partial:
            missing = []
            if p.tms is None: missing.append("TMS")
            if p.nas is None: missing.append("NAS")
            hover_texts.append(f"<b>{p.bucket_name}</b><br>⚠️ Missing: {', '.join(missing)}<br>CCS: {p.ccs:.0f}")

        fig.add_trace(go.Scatter(
            x=x_vals, y=y_vals, mode="markers",
            marker=dict(size=10, color="#aaa", opacity=0.6, symbol="diamond-open", line=dict(width=2, color="#666")),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover_texts,
            name=f"Missing Data ({len(plottable_partial)})",
        ))

    # === LAYOUT ===
    fig.add_hline(y=50, line_dash="dash", line_color="gray", opacity=0.5)
    fig.add_vline(x=50, line_dash="dash", line_color="gray", opacity=0.5)

    view_subtitle = {
        "lifecycle": "Colored by lifecycle state",
        "cluster": "Colored by technology cluster",
        "nas_overlay": "NAS attention as background heat",
        "financial": "With PMS/CSS financial signal rings",
    }.get(view_mode, "")

    fig.update_layout(
        title=dict(
            text=labels["quadrant_title"],
            subtitle=dict(text=f"{labels['quadrant_desc']} | {view_subtitle}", font=dict(size=11, color="gray"))
        ),
        xaxis=dict(title=labels["tms"], range=[0, 100], tickvals=[0, 25, 50, 75, 100]),
        yaxis=dict(title=labels["ccs"], range=[0, 100], tickvals=[0, 25, 50, 75, 100]),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=550,
        margin=dict(l=60, r=60, t=100, b=60),
    )

    return fig


def _build_hover_texts(profiles: List[BucketProfile], alert_map: dict, show_financial: bool = True) -> List[str]:
    """Build hover text for a list of profiles."""
    hover_texts = []
    for p in profiles:
        alert_info = ""
        if p.bucket_id in alert_map:
            alert = alert_map[p.bucket_id]
            alert_info = f"<br>🚨 <b>Alert:</b> {alert.alert_type.value}"

        # Motion info
        tms_d = p.tms_delta_4w or 0
        ccs_d = p.ccs_delta_4w or 0
        motion_str = "STABLE"
        if abs(tms_d) >= 3 or abs(ccs_d) >= 3:
            dirs = []
            if ccs_d > 3: dirs.append("↑")
            elif ccs_d < -3: dirs.append("↓")
            if tms_d > 3: dirs.append("→")
            elif tms_d < -3: dirs.append("←")
            motion_str = "".join(dirs) if dirs else "STABLE"
            motion_str += " (accel)" if p.velocity_accelerating else " (decel)"

        # Financial signals
        financial_info = ""
        if show_financial:
            pms = getattr(p, 'pms', None)
            css = getattr(p, 'css', None)
            if pms is not None:
                financial_info += f"<br>📈 PMS: {pms:.0f}"
            if css is not None:
                financial_info += f"<br>🪙 CSS: {css:.0f}"

        nas_str = f"{p.nas:.0f}" if p.nas is not None else "N/A"
        hover_texts.append(
            f"<b>{p.bucket_name}</b><br>"
            f"TMS: {p.tms:.0f} | CCS: {p.ccs:.0f}<br>"
            f"NAS: {nas_str} | Heat: {p.heat_score:.1f}<br>"
            f"4W: {motion_str}"
            f"{financial_info}{alert_info}"
        )
    return hover_texts


def create_bucket_heatmap(
    profiles: List[BucketProfile],
    history: Optional[Dict[str, List[BucketProfile]]] = None,
    labels: Dict[str, str] = None,
    score_type: str = "heat"
) -> go.Figure:
    """
    Create bucket heatmap over time.

    - Rows: Bucket names
    - Columns: Weeks
    - Color: Score intensity (0-100)

    Args:
        profiles: Current week's profiles
        history: Historical profiles by bucket_id
        labels: Translation labels
        score_type: Which score to show ("heat", "tms", "ccs", "nas")
    """
    if labels is None:
        labels = get_labels("en")

    # If no history, just show current week
    if not history:
        # Create single-column heatmap
        bucket_names = [p.bucket_name for p in sorted(profiles, key=lambda x: x.heat_score, reverse=True)]

        if score_type == "heat":
            values = [[p.heat_score or 0] for p in sorted(profiles, key=lambda x: x.heat_score, reverse=True)]
        elif score_type == "tms":
            values = [[p.tms or 0] for p in sorted(profiles, key=lambda x: x.heat_score, reverse=True)]
        elif score_type == "ccs":
            values = [[p.ccs or 0] for p in sorted(profiles, key=lambda x: x.heat_score, reverse=True)]
        else:
            values = [[p.nas or 0] for p in sorted(profiles, key=lambda x: x.heat_score, reverse=True)]

        weeks = ["Current"]
    else:
        # Build time series matrix
        # Get all unique weeks
        all_weeks = set()
        for bucket_id, bucket_history in history.items():
            for p in bucket_history:
                all_weeks.add(p.week_start)

        weeks = sorted(all_weeks, reverse=True)[:8]  # Last 8 weeks
        week_labels = [w.strftime("%m/%d") for w in weeks]

        # Sort buckets by current heat score
        bucket_order = sorted(profiles, key=lambda x: x.heat_score, reverse=True)
        bucket_names = [p.bucket_name for p in bucket_order]
        bucket_ids = [p.bucket_id for p in bucket_order]

        # Build values matrix
        values = []
        for bucket_id in bucket_ids:
            row = []
            bucket_history = history.get(bucket_id, [])
            history_by_week = {p.week_start: p for p in bucket_history}

            for week in weeks:
                p = history_by_week.get(week)
                if p:
                    if score_type == "heat":
                        row.append(p.heat_score or 0)
                    elif score_type == "tms":
                        row.append(p.tms or 0)
                    elif score_type == "ccs":
                        row.append(p.ccs or 0)
                    else:
                        row.append(p.nas or 0)
                else:
                    row.append(0)

            values.append(row)

        weeks = week_labels

    # Create heatmap
    fig = go.Figure(data=go.Heatmap(
        z=values,
        x=weeks,
        y=bucket_names,
        colorscale="RdYlGn",
        zmin=0,
        zmax=100,
        text=[[f"{v:.0f}" for v in row] for row in values],
        texttemplate="%{text}",
        textfont={"size": 9},
        hovertemplate="Bucket: %{y}<br>Week: %{x}<br>Score: %{z:.0f}<extra></extra>",
        colorbar=dict(title="Score", tickvals=[0, 25, 50, 75, 100]),
    ))

    score_titles = {
        "heat": labels["heat"],
        "tms": labels["tms"],
        "ccs": labels["ccs"],
        "nas": labels["nas"],
    }

    fig.update_layout(
        title=dict(
            text=f"{labels['heatmap_title']} ({score_titles.get(score_type, score_type)})",
            subtitle=dict(text=labels["heatmap_desc"], font=dict(size=12, color="gray"))
        ),
        xaxis=dict(title="Week", tickangle=0),
        yaxis=dict(title="", autorange="reversed"),
        height=max(400, len(bucket_names) * 25),
        margin=dict(l=200, r=60, t=100, b=60),
    )

    return fig


def create_bucket_radar(profile: BucketProfile, labels: Dict[str, str]) -> go.Figure:
    """Create radar chart for a single bucket profile showing all 5 subscores."""
    categories = [
        labels["tms"],
        labels["ccs"],
        labels["eis_off"],
        labels["eis_def"],
        labels["nas"],
    ]

    values = [
        profile.tms or 0,
        profile.ccs or 0,
        profile.eis_offensive or 0,
        profile.eis_defensive or 0,
        profile.nas or 0,
    ]

    # Close the radar
    categories = categories + [categories[0]]
    values = values + [values[0]]

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        name=profile.bucket_name,
        line_color=LIFECYCLE_COLORS.get(profile.lifecycle_state, "#3498db"),
        fillcolor=f"rgba{tuple(list(int(LIFECYCLE_COLORS.get(profile.lifecycle_state, '#3498db')[i:i+2], 16) for i in (1, 3, 5)) + [0.3])}",
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickvals=[25, 50, 75, 100],
            ),
        ),
        showlegend=False,
        title=f"Signal Profile: {profile.bucket_name}",
        height=350,
        margin=dict(l=60, r=60, t=60, b=60),
    )

    return fig


# =============================================================================
# 5T INVESTMENT THESIS VISUALIZATION
# =============================================================================

def create_five_t_radar(five_t: FiveTScore, bucket_name: str) -> go.Figure:
    """
    Create radar chart for 5T Investment Thesis scoring.

    Shows Team, Technology, Market, Timing, Traction dimensions.
    """
    categories = ["Team", "Technology", "Market", "Timing", "Traction"]
    values = [five_t.team, five_t.technology, five_t.market, five_t.timing, five_t.traction]
    confidences = [
        five_t.team_confidence,
        five_t.technology_confidence,
        five_t.market_confidence,
        five_t.timing_confidence,
        five_t.traction_confidence
    ]

    # Close the radar
    categories = categories + [categories[0]]
    values = values + [values[0]]
    confidences = confidences + [confidences[0]]

    fig = go.Figure()

    # Main 5T radar
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        name='5T Score',
        line_color='#9b59b6',
        fillcolor='rgba(155, 89, 182, 0.3)',
    ))

    # Confidence band (lower bound)
    confidence_low = [max(0, v - (1 - c) * 20) for v, c in zip(values, confidences)]
    fig.add_trace(go.Scatterpolar(
        r=confidence_low,
        theta=categories,
        fill=None,
        name='Confidence Band',
        line=dict(color='rgba(155, 89, 182, 0.3)', dash='dot'),
        showlegend=False,
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickvals=[25, 50, 75, 100],
            ),
        ),
        showlegend=True,
        title=f"5T Investment Thesis: {bucket_name}",
        height=350,
        margin=dict(l=60, r=60, t=80, b=60),
    )

    return fig


def create_five_t_bar_chart(five_t: FiveTScore, bucket_name: str) -> go.Figure:
    """Create horizontal bar chart for 5T scores with confidence indicators."""
    dimensions = ["Team", "Technology", "Market", "Timing", "Traction"]
    scores = [five_t.team, five_t.technology, five_t.market, five_t.timing, five_t.traction]
    confidences = [
        five_t.team_confidence,
        five_t.technology_confidence,
        five_t.market_confidence,
        five_t.timing_confidence,
        five_t.traction_confidence
    ]

    # Color based on score
    colors = []
    for score in scores:
        if score >= 70:
            colors.append("#27ae60")  # Green
        elif score >= 50:
            colors.append("#f39c12")  # Orange
        else:
            colors.append("#e74c3c")  # Red

    fig = go.Figure()

    fig.add_trace(go.Bar(
        y=dimensions,
        x=scores,
        orientation='h',
        marker_color=colors,
        text=[f"{s:.0f}" for s in scores],
        textposition='inside',
        hovertemplate="<b>%{y}</b><br>Score: %{x:.0f}<br>Confidence: %{customdata:.0%}<extra></extra>",
        customdata=confidences,
    ))

    # Add confidence whiskers
    for i, (dim, score, conf) in enumerate(zip(dimensions, scores, confidences)):
        error = (1 - conf) * 15
        fig.add_shape(
            type="line",
            x0=max(0, score - error), x1=min(100, score + error),
            y0=i, y1=i,
            line=dict(color="rgba(0,0,0,0.3)", width=2),
        )

    fig.update_layout(
        xaxis=dict(range=[0, 100], title="Score"),
        yaxis=dict(title=""),
        title=f"5T Investment Thesis: {bucket_name}",
        height=250,
        margin=dict(l=100, r=40, t=60, b=40),
        showlegend=False,
    )

    return fig


# =============================================================================
# HYPE CYCLE VISUALIZATION
# =============================================================================

def create_hype_cycle_curve(profiles: List[BucketProfile] = None) -> go.Figure:
    """
    Create Gartner Hype Cycle curve visualization.

    Plots the classic hype cycle curve and positions buckets on it.
    """
    # Generate the classic hype cycle curve
    x_curve = np.linspace(0, 100, 100)
    y_curve = (
        30 +  # Base level
        60 * np.exp(-((x_curve - 30) ** 2) / 200) -  # Peak
        20 * np.exp(-((x_curve - 50) ** 2) / 100) +  # Trough
        30 * (1 / (1 + np.exp(-(x_curve - 70) / 10)))  # Plateau rise
    )

    fig = go.Figure()

    # Draw the hype cycle curve
    fig.add_trace(go.Scatter(
        x=x_curve,
        y=y_curve,
        mode='lines',
        name='Hype Cycle',
        line=dict(color='#bdc3c7', width=3),
        fill='tozeroy',
        fillcolor='rgba(189, 195, 199, 0.1)',
    ))

    # Add phase labels
    phase_positions = [
        (10, 35, "Innovation\nTrigger", "#3498db"),
        (30, 98, "Peak of Inflated\nExpectations", "#e74c3c"),
        (50, 20, "Trough of\nDisillusionment", "#95a5a6"),
        (70, 58, "Slope of\nEnlightenment", "#f39c12"),
        (90, 72, "Plateau of\nProductivity", "#27ae60"),
    ]

    for x, y, label, color in phase_positions:
        fig.add_annotation(
            x=x, y=y + 8,
            text=label,
            showarrow=False,
            font=dict(size=9, color=color),
            align="center",
        )

    # Plot bucket positions if provided
    if profiles:
        for profile in profiles:
            phase = profile.hype_cycle_phase
            if phase == HypeCyclePhase.UNKNOWN:
                continue

            x_pos, y_base = HYPE_CYCLE_POSITIONS.get(phase, (50, 50))
            # Add some jitter to avoid overlap
            x_pos += np.random.uniform(-5, 5)
            y_pos = y_base + np.random.uniform(-3, 3)

            color = HYPE_CYCLE_COLORS.get(phase, "#888")

            fig.add_trace(go.Scatter(
                x=[x_pos],
                y=[y_pos],
                mode='markers+text',
                marker=dict(
                    size=12,
                    color=color,
                    line=dict(width=1, color='white'),
                ),
                text=[profile.bucket_name[:15]],
                textposition='top center',
                textfont=dict(size=8),
                name=profile.bucket_name,
                hovertemplate=(
                    f"<b>{profile.bucket_name}</b><br>"
                    f"Phase: {HYPE_CYCLE_LABELS.get(phase, 'Unknown')}<br>"
                    f"Confidence: {profile.hype_cycle_confidence:.0%}<br>"
                    f"<i>{profile.hype_cycle_rationale}</i>"
                    "<extra></extra>"
                ),
                showlegend=False,
            ))

    fig.update_layout(
        xaxis=dict(
            title="Time / Maturity",
            showticklabels=False,
            range=[0, 100],
        ),
        yaxis=dict(
            title="Expectations",
            showticklabels=False,
            range=[0, 110],
        ),
        title="Gartner Hype Cycle Positioning",
        height=400,
        margin=dict(l=60, r=60, t=80, b=60),
        showlegend=False,
    )

    return fig


def render_hype_cycle_indicator(profile: BucketProfile):
    """Render a small hype cycle phase indicator for a bucket."""
    phase = profile.hype_cycle_phase
    label = HYPE_CYCLE_LABELS.get(phase, "Unknown")
    color = HYPE_CYCLE_COLORS.get(phase, "#888")

    st.markdown(
        f"""
        <div style="display: flex; align-items: center; gap: 8px; margin: 8px 0;">
            <div style="
                width: 12px; height: 12px;
                background-color: {color};
                border-radius: 50%;
            "></div>
            <span style="font-weight: 500;">Hype Cycle:</span>
            <span style="color: {color};">{label}</span>
            <span style="color: #666; font-size: 0.85em;">
                ({profile.hype_cycle_confidence:.0%} confidence)
            </span>
        </div>
        """,
        unsafe_allow_html=True
    )

    if profile.hype_cycle_rationale:
        st.caption(f"_{profile.hype_cycle_rationale}_")


# =============================================================================
# COVERAGE BADGE RENDERING
# =============================================================================

def render_coverage_badge(coverage: DataCoverage):
    """Render visual coverage badge in Streamlit."""
    if coverage is None:
        return

    badge = coverage.badge
    icon_name, color = COVERAGE_BADGE_ICONS.get(badge, ("circle", "#888"))

    # Map icon names to emoji
    icon_emoji = {
        "check-circle": "\u2705",
        "check": "\u2714\ufe0f",
        "alert-triangle": "\u26a0\ufe0f",
        "x-circle": "\u274c",
        "circle": "\u26ab",
    }.get(icon_name, "\u26ab")

    badge_html = f"""
    <div style="
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        background-color: {color}15;
        border: 1px solid {color}40;
        border-radius: 16px;
        margin: 4px 0;
    ">
        <span style="font-size: 14px;">{icon_emoji}</span>
        <span style="font-size: 12px; color: {color}; font-weight: 500;">
            {coverage.signal_count}/6 signals
        </span>
    </div>
    """
    st.markdown(badge_html, unsafe_allow_html=True)

    missing = coverage.get_missing_signals()
    if missing:
        st.caption(f"Missing: {', '.join(missing)}")


def render_coverage_inline(coverage: DataCoverage) -> str:
    """Return HTML for inline coverage badge."""
    if coverage is None:
        return ""

    badge = coverage.badge
    _, color = COVERAGE_BADGE_ICONS.get(badge, ("circle", "#888"))

    return f"""
    <span style="
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 2px 6px;
        background-color: {color}15;
        border-radius: 10px;
        font-size: 10px;
        color: {color};
    ">
        {coverage.signal_count}/6
    </span>
    """


# =============================================================================
# CONFIDENCE INTERVAL VISUALIZATION
# =============================================================================

def render_confidence_interval(ci: ConfidenceInterval, signal_name: str):
    """Render a confidence interval visualization."""
    if ci is None:
        return

    range_width = ci.high - ci.low
    reliability = "Reliable" if ci.is_reliable else "Wide range" if ci.is_wide else "Moderate"
    reliability_color = "#27ae60" if ci.is_reliable else "#e74c3c" if ci.is_wide else "#f39c12"

    st.markdown(
        f"""
        <div style="margin: 8px 0;">
            <div style="display: flex; justify-content: space-between; font-size: 12px;">
                <span><b>{signal_name}</b>: {ci.mid:.0f}</span>
                <span style="color: {reliability_color};">{reliability}</span>
            </div>
            <div style="
                position: relative;
                height: 20px;
                background: linear-gradient(to right, #eee 0%, #eee 100%);
                border-radius: 10px;
                margin: 4px 0;
            ">
                <div style="
                    position: absolute;
                    left: {ci.low}%;
                    width: {range_width}%;
                    height: 100%;
                    background: linear-gradient(to right, rgba(52, 152, 219, 0.3), rgba(52, 152, 219, 0.5), rgba(52, 152, 219, 0.3));
                    border-radius: 10px;
                "></div>
                <div style="
                    position: absolute;
                    left: {ci.mid}%;
                    width: 4px;
                    height: 100%;
                    background: #3498db;
                    border-radius: 2px;
                    transform: translateX(-50%);
                "></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 10px; color: #666;">
                <span>{ci.low:.0f}</span>
                <span>{ci.high:.0f}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


# =============================================================================
# ALERT RENDERING
# =============================================================================

def render_alerts_panel(alerts: List[BucketAlert], labels: Dict[str, str]):
    """Render enhanced divergence alerts panel with persistent storage."""
    if not alerts:
        st.info("No divergence alerts detected this week")
        return

    # Initialize components
    alert_store = AlertStore()
    renderer = AlertCardRenderer()

    try:
        # Group by interpretation
        opportunities = [a for a in alerts if a.interpretation == AlertInterpretation.OPPORTUNITY]
        risks = [a for a in alerts if a.interpretation == AlertInterpretation.RISK]
        signals = [a for a in alerts if a.interpretation in (AlertInterpretation.SIGNAL, AlertInterpretation.NEUTRAL)]

        # Summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Opportunities", len(opportunities))
        with col2:
            st.metric("Risks", len(risks))
        with col3:
            st.metric("Signals", len(signals))

        st.divider()

        # Opportunities
        st.markdown(f"### {labels['opportunities']}")
        if opportunities:
            for alert in opportunities[:5]:
                _render_enhanced_alert_card(alert, renderer, alert_store, labels)
        else:
            st.caption("No opportunity alerts")

        st.divider()

        # Risks
        st.markdown(f"### {labels['risks']}")
        if risks:
            for alert in risks[:5]:
                _render_enhanced_alert_card(alert, renderer, alert_store, labels)
        else:
            st.caption("No risk alerts")

        st.divider()

        # Signals
        st.markdown(f"### {labels['signals']}")
        if signals:
            for alert in signals[:5]:
                _render_enhanced_alert_card(alert, renderer, alert_store, labels)
        else:
            st.caption("No signal alerts")
    finally:
        alert_store.close()


def _render_enhanced_alert_card(
    alert: BucketAlert,
    renderer: AlertCardRenderer,
    alert_store: AlertStore,
    labels: Dict[str, str]
):
    """Render a single enhanced alert card with persistent storage lookup."""
    # Look up stored alert data from alert store
    stored_alerts = alert_store.get_active_alerts(bucket_id=alert.bucket_id)
    stored = None
    for sa in stored_alerts:
        if sa.alert_type == alert.alert_type.value:
            stored = sa
            break

    if stored:
        weeks_persistent = stored.weeks_persistent
        evidence_count = len(stored.evidence_payload.get("top_entities", [])) if stored.evidence_payload else 0
        card_data = build_alert_card_data(
            alert=stored,
            confidence=getattr(alert, 'signal_confidence', 0.5),
        )
    else:
        weeks_persistent = 0
        evidence_count = len(alert.supporting_entities or [])

        # Fallback: create card data manually for non-stored alerts
        severity = "WARN" if alert.interpretation == AlertInterpretation.OPPORTUNITY else "INFO"

        # Get alert name from labels
        alert_type_labels = {
            AlertType.ALPHA_ZONE: labels["alpha_zone"],
            AlertType.HYPE_ZONE: labels["hype_zone"],
            AlertType.ENTERPRISE_PULL: labels["enterprise_pull"],
            AlertType.DISRUPTION_PRESSURE: labels["disruption_pressure"],
            AlertType.ROTATION: labels["rotation"],
        }
        alert_name = alert_type_labels.get(alert.alert_type, alert.alert_type.value)

        card_data = AlertCardData(
            bucket_name=alert.bucket_name,
            alert_type=alert.alert_type.value,
            alert_name=alert_name,
            severity=severity,
            confidence=getattr(alert, 'signal_confidence', 0.5),
            evidence_text=f"{evidence_count} entities",
            persistence_text=format_persistence_text(weeks_persistent),
            action_hint=getattr(alert, 'action_hint', "Monitor this trend"),
            trigger_scores={
                "magnitude": alert.divergence_magnitude,
                "threshold": alert.threshold_used,
            },
        )

    html = renderer.render_card_html(card_data)
    st.markdown(html, unsafe_allow_html=True)

    # Expandable detail section
    with st.expander(f"Details: {alert.bucket_name}"):
        st.write(alert.rationale)
        if alert.supporting_entities:
            st.caption(f"**Related entities:** {', '.join(alert.supporting_entities[:5])}")


def _render_alert_card(alert: BucketAlert, labels: Dict[str, str], alert_type: str):
    """Render a single alert card (legacy version for backward compatibility)."""
    alert_type_labels = {
        AlertType.ALPHA_ZONE: labels["alpha_zone"],
        AlertType.HYPE_ZONE: labels["hype_zone"],
        AlertType.ENTERPRISE_PULL: labels["enterprise_pull"],
        AlertType.DISRUPTION_PRESSURE: labels["disruption_pressure"],
        AlertType.ROTATION: labels["rotation"],
    }

    icon = {
        "success": "[OK]",
        "error": "[!!]",
        "warning": "[!]",
    }.get(alert_type, "[i]")

    with st.expander(f"{icon} {alert.bucket_name} - {alert_type_labels.get(alert.alert_type, alert.alert_type.value)}"):
        st.caption(f"**Magnitude:** {alert.divergence_magnitude:.0f} | **Threshold:** {alert.threshold_used}")
        st.write(alert.rationale)

        if alert.supporting_entities:
            st.caption(f"**Related entities:** {', '.join(alert.supporting_entities[:5])}")


# =============================================================================
# BUCKET DETAIL VIEW (Enhanced with Explainability Drawer)
# =============================================================================

def render_bucket_detail(profile: BucketProfile, labels: Dict[str, str], alerts: Optional[List[BucketAlert]] = None):
    """
    Render enhanced detailed view for a single bucket.

    Includes:
    - Signal radar chart + 5T Investment Thesis radar
    - Hype Cycle positioning
    - Coverage badge
    - Per-signal confidence intervals
    - Top entities with evidence
    - Active alerts for this bucket
    - Data integrity warnings
    """
    # === HEADER WITH COVERAGE BADGE ===
    header_col1, header_col2 = st.columns([3, 1])
    with header_col1:
        st.markdown(f"### {profile.bucket_name}")
    with header_col2:
        if profile.data_coverage:
            render_coverage_badge(profile.data_coverage)

    # === HYPE CYCLE INDICATOR ===
    render_hype_cycle_indicator(profile)

    st.divider()

    # === DUAL RADAR CHARTS ===
    col_chart, col_5t = st.columns(2)

    with col_chart:
        fig = create_bucket_radar(profile, labels)
        st.plotly_chart(fig, use_container_width=True)

    with col_5t:
        if profile.five_t_score:
            fig_5t = create_five_t_radar(profile.five_t_score, profile.bucket_name)
            st.plotly_chart(fig_5t, use_container_width=True)

            # 5T Summary metrics
            five_t = profile.five_t_score
            st.markdown(f"""
            **5T Composite Score:** {five_t.composite:.0f}/100
            | **Strongest:** {five_t.get_strongest_dimension().title()}
            | **Weakest:** {five_t.get_weakest_dimension().title()}
            """)
        else:
            st.info("5T Investment Thesis scores not yet computed for this bucket.")

    # === CONFIDENCE INTERVALS SECTION ===
    if profile.confidence_intervals:
        with st.expander("**Confidence Intervals**", expanded=False):
            for signal_name, ci in profile.confidence_intervals.items():
                render_confidence_interval(ci, signal_name.upper())

    # === DETAIL PANEL ===
    col_details_left, col_details_right = st.columns([1, 1])

    with col_details_left:
        # Lifecycle badge with explanation
        state_label = LIFECYCLE_LABELS["en"].get(profile.lifecycle_state, profile.lifecycle_state.value)
        state_color = LIFECYCLE_COLORS.get(profile.lifecycle_state, "#888")

        # Lifecycle state explanation
        state_explanations = {
            LifecycleState.EMERGING: "High technical activity, limited capital/enterprise adoption",
            LifecycleState.VALIDATING: "Strong technical + capital signals, enterprise catching up",
            LifecycleState.ESTABLISHING: "Enterprise adoption underway, maturing market",
            LifecycleState.MAINSTREAM: "Stable, consolidated market position",
        }

        st.markdown(
            f"<span style='background-color:{state_color}; color:white; padding:4px 8px; border-radius:4px;'>{state_label}</span>",
            unsafe_allow_html=True
        )
        st.caption(f"_{state_explanations.get(profile.lifecycle_state, '')}_")

        st.markdown("---")

        # === SIGNAL SCORES WITH CONFIDENCE ===
        st.markdown("**Subscores** (with confidence)")

        signal_data = [
            ("tms", labels["tms"], profile.tms, "Technical"),
            ("ccs", labels["ccs"], profile.ccs, "Capital"),
            ("eis", labels["eis_off"], profile.eis_offensive, "Enterprise"),
            ("nas", labels["nas"], profile.nas, "Narrative"),
        ]

        for signal_key, name, score, signal_type in signal_data:
            if score is not None:
                # Get confidence from metadata if available
                meta = profile.signal_metadata.get(signal_key, {})
                confidence = meta.get("confidence", profile.signal_confidence)
                coverage = meta.get("coverage", 0.5)
                sources = meta.get("sources", [])

                # Color code confidence
                if confidence >= 0.7:
                    conf_color = "#27ae60"
                    conf_label = "high"
                elif confidence >= 0.4:
                    conf_color = "#f39c12"
                    conf_label = "medium"
                else:
                    conf_color = "#e74c3c"
                    conf_label = "low"

                # Show score with confidence indicator
                st.markdown(
                    f"**{name}:** {score:.0f} "
                    f"<span style='color:{conf_color}; font-size:0.8em;'>({conf_label} conf)</span>",
                    unsafe_allow_html=True
                )
                st.progress(score / 100)

                # Show sources if available
                if sources:
                    st.caption(f"  Sources: {', '.join(sources)}")
            else:
                st.caption(f"{name}: N/A (no data)")

        st.markdown(f"**{labels['heat']}:** {profile.heat_score:.1f}")

        # Overall confidence
        overall_conf = profile.get_overall_confidence() if hasattr(profile, 'get_overall_confidence') else profile.signal_confidence
        st.markdown(f"**Overall Confidence:** {overall_conf:.0%}")

    # === DATA INTEGRITY WARNINGS ===
    if profile.data_issues:
        st.warning("**Data Integrity Issues:**")
        for issue in profile.data_issues:
            st.caption(f"⚠️ {issue}")

    # === EXPLAINABILITY DRAWER (ENHANCED) ===
    with st.expander("📊 **Evidence & Explainability**", expanded=False):
        # Build signal history from available data
        signal_history = {}

        # Try to get historical data if available
        try:
            from utils.historical_baselines import HistoricalBaselineCalculator
            baseline_calc = HistoricalBaselineCalculator()

            for signal in ["tms", "ccs", "nas", "eis", "pms", "css"]:
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
                    "rationale": getattr(bucket_alerts[0], 'rationale', ''),
                }

        # Build profile dict for drawer
        profile_dict = {
            "bucket_id": profile.bucket_id,
            "bucket_name": profile.bucket_name,
            "tms": getattr(profile, 'tms', None),
            "ccs": getattr(profile, 'ccs', None),
            "nas": getattr(profile, 'nas', None),
            "eis": getattr(profile, 'eis_offensive', None),
            "pms": getattr(profile, 'pms', None),
            "css": getattr(profile, 'css', None),
            "signal_confidence": getattr(profile, 'signal_confidence', 0.5),
            "signal_metadata": getattr(profile, "signal_metadata", {}),
            "top_technical_entities": getattr(profile, 'top_technical_entities', []),
            "top_capital_entities": getattr(profile, 'top_capital_entities', []),
        }

        drawer_data = build_explain_drawer_data(profile_dict, signal_history, alert_info)
        drawer_renderer = ExplainDrawerRenderer()
        drawer_renderer.render(drawer_data, st)

    # === BUCKET ALERTS ===
    if alerts:
        bucket_alerts = [a for a in alerts if a.bucket_id == profile.bucket_id]
        if bucket_alerts:
            with st.expander(f"🚨 **Active Alerts ({len(bucket_alerts)})**", expanded=True):
                for alert in bucket_alerts:
                    # Severity badge
                    severity = getattr(alert, 'severity', None)
                    if severity:
                        sev_colors = {"info": "#3498db", "warn": "#f39c12", "crit": "#e74c3c"}
                        sev_color = sev_colors.get(severity.value, "#888")
                        sev_label = severity.value.upper()
                    else:
                        sev_color = "#888"
                        sev_label = "INFO"

                    st.markdown(
                        f"<span style='background-color:{sev_color}; color:white; padding:2px 6px; border-radius:3px; font-size:0.8em;'>{sev_label}</span> "
                        f"**{alert.alert_type.value}**",
                        unsafe_allow_html=True
                    )
                    st.caption(alert.rationale)

                    # Show evidence if available
                    if alert.supporting_entities:
                        st.caption(f"Evidence: {', '.join(alert.supporting_entities[:3])}")

                    # Show action hint if available
                    action_hint = getattr(alert, 'action_hint', None)
                    if action_hint:
                        st.info(f"💡 **Action:** {action_hint}")


# =============================================================================
# MAIN RENDER FUNCTION
# =============================================================================

def render_bucket_radar_tab(language: str = "en"):
    """
    Render the Bucket Trend Radar tab content.

    Args:
        language: Display language ("en" or "zh")
    """
    labels = get_labels(language)

    # Load data
    profiles = load_bucket_profiles()

    if not profiles:
        st.warning(labels["no_data"])
        st.info("Run: `python -m utils.bucket_scorers` to generate bucket scores")
        return

    # Detect alerts
    detector = BucketAlertDetector()
    # Run detection twice to satisfy persistence requirements for Alpha Zone
    detector.detect_alerts(profiles)  # First pass
    alerts = detector.detect_alerts(profiles)  # Second pass (for 2-week requirement)

    # Header
    st.header(f"[RADAR] {labels['title']}")
    st.caption(labels["subtitle"])

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(label=labels["buckets_count"], value=len(profiles))

    with col2:
        st.metric(label=labels["alerts_count"], value=len(alerts))

    with col3:
        avg_heat = sum(p.heat_score for p in profiles) / len(profiles) if profiles else 0
        st.metric(label=labels["avg_heat"], value=f"{avg_heat:.1f}")

    with col4:
        # Count by lifecycle
        emerging = sum(1 for p in profiles if p.lifecycle_state == LifecycleState.EMERGING)
        st.metric(label="Emerging Buckets", value=emerging)

    # === TOP ALERTS PANEL (Executive Takeaway) ===
    if alerts:
        st.markdown("---")
        st.markdown("### Top Alerts")

        # Build a lookup for profiles by bucket_id
        profile_lookup = {p.bucket_id: p for p in profiles}

        # Sort alerts by magnitude (most significant first)
        sorted_alerts = sorted(alerts, key=lambda a: a.divergence_magnitude, reverse=True)[:3]

        alert_cols = st.columns(len(sorted_alerts)) if sorted_alerts else []
        for i, alert in enumerate(sorted_alerts):
            with alert_cols[i]:
                # Get profile for motion/context
                p = profile_lookup.get(alert.bucket_id)

                # Icon based on alert type
                icon = {
                    AlertType.ALPHA_ZONE: "💎",
                    AlertType.HYPE_ZONE: "⚠️",
                    AlertType.ENTERPRISE_PULL: "🏢",
                    AlertType.DISRUPTION_PRESSURE: "💥",
                    AlertType.ROTATION: "🔄",
                }.get(alert.alert_type, "❗")

                # Color based on interpretation
                color = {
                    AlertInterpretation.OPPORTUNITY: "#27ae60",
                    AlertInterpretation.RISK: "#e74c3c",
                    AlertInterpretation.SIGNAL: "#f39c12",
                    AlertInterpretation.NEUTRAL: "#7f8c8d",
                }.get(alert.interpretation, "#888")

                # Build the insight line
                insight = ""
                if p:
                    tms_d = p.tms_delta_4w or 0
                    ccs_d = p.ccs_delta_4w or 0

                    if alert.alert_type == AlertType.ALPHA_ZONE:
                        insight = f"High TMS ({p.tms:.0f}), low capital attention"
                        if ccs_d > 5:
                            insight += f" — CCS ↑{ccs_d:.0f}% (capital catching up)"
                    elif alert.alert_type == AlertType.HYPE_ZONE:
                        insight = f"NAS high but TMS only {p.tms:.0f}"
                        if tms_d < -3:
                            insight += " — tech momentum fading"
                    elif alert.alert_type == AlertType.ENTERPRISE_PULL:
                        insight = f"EIS={p.eis_offensive:.0f} pulling adoption"
                    elif alert.alert_type == AlertType.DISRUPTION_PRESSURE:
                        insight = f"Defensive pressure ({p.eis_defensive:.0f})"
                    else:
                        insight = alert.rationale[:60] if alert.rationale else "Market signal"

                # Render the alert card
                st.markdown(
                    f"""
                    <div style="background-color: {color}15; border-left: 4px solid {color}; padding: 12px; border-radius: 4px; margin-bottom: 8px;">
                        <div style="font-size: 1.1em; font-weight: bold;">{icon} {alert.bucket_name}</div>
                        <div style="color: {color}; font-size: 0.9em; margin-top: 4px;">{insight}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    st.divider()

    # Main visualizations in tabs
    viz_tab1, viz_tab2, viz_tab3, viz_tab4 = st.tabs([
        f"[Q] {labels['quadrant_title']}",
        f"[H] {labels['heatmap_title']}",
        f"[!] {labels['alerts_title']}",
        "[G] Gartner Hype Cycle"
    ])

    with viz_tab1:
        # View mode selector
        col_mode, col_options = st.columns([3, 1])
        with col_mode:
            view_mode = st.radio(
                "View Mode",
                ["lifecycle", "cluster", "nas_overlay", "financial"],
                format_func=lambda x: {
                    "lifecycle": "🔄 Lifecycle State",
                    "cluster": "📊 Technology Cluster",
                    "nas_overlay": "🔥 NAS Heat Overlay",
                    "financial": "💹 Financial Signals",
                }.get(x, x),
                horizontal=True,
                key="quadrant_view_mode"
            )
        with col_options:
            show_badges = st.checkbox("Alert Badges", value=True, key="show_alert_badges")
            show_all_labels = st.checkbox("All Labels", value=False, key="show_all_labels",
                                          help="Show labels for all buckets (default: top 8 by heat + alerts)")

        # Use enhanced quadrant with selected view mode
        # If "All Labels" is checked, set top_n_labels very high
        fig_quadrant = create_enhanced_quadrant(
            profiles, labels, alerts,
            view_mode=view_mode,
            show_pms_css=True,
            show_nas_background=(view_mode == "nas_overlay"),
            show_alert_badges=show_badges,
            top_n_labels=100 if show_all_labels else 8,  # Toggle label declutter
        )
        st.plotly_chart(fig_quadrant, use_container_width=True, key="main_quadrant")

        # Legend for motion arrows and confidence
        with st.expander("Chart Legend & How to Read", expanded=False):
            col_legend1, col_legend2 = st.columns(2)

            with col_legend1:
                st.markdown("""
                **Motion Arrows (4-week momentum)**
                - 🟢 Green arrow = Accelerating momentum
                - 🟠 Orange arrow = Decelerating momentum
                - Arrow direction = Movement trajectory
                - Arrow length = Velocity magnitude

                **Zones**
                - 💎 Green area (bottom-right) = **Alpha Zone** - Hidden gems
                - ⚠️ Red area (top-left) = **Hype Zone** - Vaporware risk
                """)

            with col_legend2:
                st.markdown("""
                **View Modes**
                - 🔄 Lifecycle: Color by maturity stage
                - 📊 Cluster: Color by technology category
                - 🔥 NAS Overlay: Background heat = news attention
                - 💹 Financial: PMS/CSS signal rings

                **Financial Signal Rings (💹 mode)**
                - 🟢 Outer solid ring = PMS (equity proxy momentum)
                - 🟠 Inner dotted ring = CSS (crypto retail sentiment)
                - Ring size = signal percentile strength
                """)

        # Mode Integrity Indicator (Improvement 6)
        st.caption("✅ **Coordinates based on TMS/CCS only** — NAS, PMS, CSS are visual overlays and do not affect dot positions.")

    with viz_tab2:
        # Score type selector
        score_type = st.radio(
            "Score Type",
            ["heat", "tms", "ccs", "nas"],
            format_func=lambda x: {
                "heat": labels["heat"],
                "tms": labels["tms"],
                "ccs": labels["ccs"],
                "nas": labels["nas"],
            }.get(x, x),
            horizontal=True,
            key="heatmap_score_type"
        )

        # For now, show single week (history would require stored data)
        fig_heatmap = create_bucket_heatmap(profiles, labels=labels, score_type=score_type)
        st.plotly_chart(fig_heatmap, use_container_width=True)

    with viz_tab3:
        render_alerts_panel(alerts, labels)

    with viz_tab4:
        st.markdown("""
        ### Gartner Hype Cycle Positioning

        This view positions each AI trend bucket on the classic Gartner Hype Cycle curve,
        helping business analysts understand technology maturity and investment timing.
        """)

        # Create and display the hype cycle visualization
        fig_hype = create_hype_cycle_curve(profiles)
        st.plotly_chart(fig_hype, use_container_width=True)

        # Legend/explanation
        with st.expander("**Understanding the Hype Cycle Phases**", expanded=False):
            st.markdown("""
            | Phase | Characteristics | Investment Implication |
            |-------|----------------|----------------------|
            | **Innovation Trigger** | High technical activity, low capital/enterprise attention | Early-stage, high risk/reward |
            | **Peak of Expectations** | Maximum hype, capital flooding in, valuations stretched | Caution - may be overvalued |
            | **Trough of Disillusionment** | Declining attention, failing startups, market correction | Contrarian opportunity |
            | **Slope of Enlightenment** | Enterprise adoption, practical applications | Sweet spot for growth investment |
            | **Plateau of Productivity** | Mainstream, stable market | Lower risk, steady returns |
            """)

        # Phase distribution summary
        st.markdown("#### Phase Distribution")
        phase_counts = {}
        for p in profiles:
            phase = p.hype_cycle_phase
            phase_counts[phase] = phase_counts.get(phase, 0) + 1

        cols = st.columns(len(HypeCyclePhase))
        for i, phase in enumerate(HypeCyclePhase):
            count = phase_counts.get(phase, 0)
            color = HYPE_CYCLE_COLORS.get(phase, "#888")
            label = HYPE_CYCLE_LABELS.get(phase, "Unknown")
            with cols[i]:
                st.markdown(
                    f"""
                    <div style="text-align: center; padding: 8px;">
                        <div style="
                            font-size: 24px;
                            font-weight: bold;
                            color: {color};
                        ">{count}</div>
                        <div style="font-size: 10px; color: #666;">{label}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    st.divider()

    # Bucket detail section
    st.subheader(f"[D] {labels['bucket_detail']}")

    bucket_options = {p.bucket_name: p for p in sorted(profiles, key=lambda x: x.heat_score, reverse=True)}

    selected_bucket_name = st.selectbox(
        labels["select_bucket"],
        options=list(bucket_options.keys()),
        key="bucket_selector"
    )

    if selected_bucket_name:
        selected_profile = bucket_options[selected_bucket_name]
        render_bucket_detail(selected_profile, labels, alerts)


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    st.set_page_config(page_title="Bucket Radar Test", layout="wide")
    render_bucket_radar_tab("en")
