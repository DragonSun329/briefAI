#!/usr/bin/env python3
"""
Bloomberg-Style Terminal Dashboard for briefAI.

Multi-pane professional interface for AI market intelligence.
"""

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import json

def load_signal_profiles():
    """Load latest signal profiles."""
    conn = sqlite3.connect("data/signals.db")
    df = pd.read_sql("""
        SELECT 
            entity_name,
            media_score,
            technical_score,
            financial_score,
            composite_score,
            momentum_7d,
            momentum_30d,
            created_at
        FROM signal_profiles
        WHERE created_at = (SELECT MAX(created_at) FROM signal_profiles)
        ORDER BY composite_score DESC
    """, conn)
    conn.close()
    return df

def load_predictions():
    """Load prediction stats."""
    conn = sqlite3.connect("data/predictions.db")
    df = pd.read_sql("""
        SELECT 
            entity_name,
            predicted_outcome,
            confidence,
            horizon_days,
            status,
            predicted_at
        FROM predictions
        ORDER BY predicted_at DESC
        LIMIT 50
    """, conn)
    conn.close()
    return df

def load_alerts():
    """Load recent alerts."""
    conn = sqlite3.connect("data/alerts.db")
    try:
        df = pd.read_sql("""
            SELECT * FROM alerts
            ORDER BY first_detected DESC
            LIMIT 20
        """, conn)
    except:
        df = pd.DataFrame()
    conn.close()
    return df

def render_market_overview():
    """Render market overview panel."""
    st.markdown("### 📊 Market Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    df = load_signal_profiles()
    if len(df) > 0:
        with col1:
            avg_sentiment = df["media_score"].mean()
            st.metric("Avg Sentiment", f"{avg_sentiment:.1f}/10", 
                     delta=f"{avg_sentiment - 5:.1f}" if avg_sentiment != 5 else None)
        
        with col2:
            bullish = len(df[df["media_score"] >= 6])
            st.metric("Bullish Signals", f"{bullish}/{len(df)}")
        
        with col3:
            avg_momentum = df["momentum_7d"].mean() if "momentum_7d" in df else 0
            st.metric("Avg 7D Momentum", f"{avg_momentum:+.1f}%")
        
        with col4:
            st.metric("Entities Tracked", len(df))

def render_top_movers():
    """Render top movers panel."""
    st.markdown("### 🚀 Top Movers")
    
    df = load_signal_profiles()
    if len(df) > 0 and "momentum_7d" in df.columns:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📈 Gainers**")
            gainers = df.nlargest(5, "momentum_7d")[["entity_name", "momentum_7d", "media_score"]]
            gainers.columns = ["Entity", "7D Momentum", "Sentiment"]
            st.dataframe(gainers, hide_index=True, use_container_width=True)
        
        with col2:
            st.markdown("**📉 Losers**")
            losers = df.nsmallest(5, "momentum_7d")[["entity_name", "momentum_7d", "media_score"]]
            losers.columns = ["Entity", "7D Momentum", "Sentiment"]
            st.dataframe(losers, hide_index=True, use_container_width=True)

def render_signal_heatmap():
    """Render signal strength heatmap."""
    st.markdown("### 🔥 Signal Heatmap")
    
    df = load_signal_profiles()
    if len(df) > 0:
        # Create heatmap data
        heatmap_df = df[["entity_name", "media_score", "technical_score", "financial_score"]].head(15)
        heatmap_df = heatmap_df.set_index("entity_name")
        
        # Style with color gradient
        styled = heatmap_df.style.background_gradient(cmap="RdYlGn", vmin=0, vmax=10)
        st.dataframe(styled, use_container_width=True)

def render_predictions_panel():
    """Render predictions panel."""
    st.markdown("### 🎯 Active Predictions")
    
    df = load_predictions()
    if len(df) > 0:
        pending = df[df["status"] == "pending"]
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f"**{len(pending)} pending predictions**")
        with col2:
            resolved = df[df["status"] == "resolved"]
            if len(resolved) > 0:
                st.markdown(f"Resolved: {len(resolved)}")
        
        # Show recent predictions
        display_df = pending[["entity_name", "predicted_outcome", "confidence", "horizon_days"]].head(10)
        display_df.columns = ["Entity", "Prediction", "Confidence", "Horizon"]
        display_df["Confidence"] = display_df["Confidence"].apply(lambda x: f"{x:.0%}" if pd.notnull(x) else "-")
        display_df["Horizon"] = display_df["Horizon"].apply(lambda x: f"{x}d")
        st.dataframe(display_df, hide_index=True, use_container_width=True)

def render_alerts_panel():
    """Render alerts panel."""
    st.markdown("### 🚨 Recent Alerts")
    
    df = load_alerts()
    if len(df) > 0:
        for _, row in df.head(5).iterrows():
            severity = row.get("severity", "info")
            icon = "🔴" if severity == "critical" else "🟡" if severity == "high" else "🔵"
            st.markdown(f"{icon} **{row.get('bucket_name', 'Unknown')}**: {row.get('interpretation', 'Alert')}")
    else:
        st.info("No recent alerts")

def render_entity_search():
    """Render entity search panel."""
    st.markdown("### 🔍 Entity Lookup")
    
    entity = st.text_input("Search entity", placeholder="e.g., NVIDIA, OpenAI")
    
    if entity:
        df = load_signal_profiles()
        matches = df[df["entity_name"].str.contains(entity, case=False, na=False)]
        
        if len(matches) > 0:
            row = matches.iloc[0]
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Media Score", f"{row['media_score']:.1f}")
            with col2:
                st.metric("Technical Score", f"{row['technical_score']:.1f}")
            with col3:
                st.metric("7D Momentum", f"{row['momentum_7d']:+.1f}%")
            
            st.markdown(f"**Composite Score:** {row['composite_score']:.1f}/10")
        else:
            st.warning(f"No data found for '{entity}'")

def render_quick_stats():
    """Render quick statistics sidebar."""
    st.sidebar.markdown("## 📈 Quick Stats")
    
    # Load various stats
    try:
        conn = sqlite3.connect("data/signals.db")
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(DISTINCT entity_id) FROM signal_observations")
        entities = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM signal_observations")
        observations = cur.fetchone()[0]
        
        cur.execute("SELECT MAX(observed_at) FROM signal_observations")
        latest = cur.fetchone()[0]
        
        conn.close()
        
        st.sidebar.metric("Total Entities", f"{entities:,}")
        st.sidebar.metric("Total Signals", f"{observations:,}")
        st.sidebar.markdown(f"**Last Update:** {latest[:16] if latest else 'N/A'}")
        
    except Exception as e:
        st.sidebar.error(f"Error loading stats: {e}")
    
    # Data sources
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 📡 Data Sources")
    sources = [
        "ArXiv", "GitHub", "HuggingFace", "Polymarket",
        "Metaculus", "HackerNews", "Reddit", "PyPI"
    ]
    st.sidebar.markdown(f"**Active:** {len(sources)} sources")

def main():
    """Main terminal interface."""
    st.set_page_config(
        page_title="briefAI Terminal",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS for Bloomberg-like dark theme
    st.markdown("""
        <style>
        .stApp {
            background-color: #1a1a2e;
        }
        .stMetric {
            background-color: #16213e;
            padding: 10px;
            border-radius: 5px;
        }
        h3 {
            color: #00d4ff;
            border-bottom: 1px solid #00d4ff;
            padding-bottom: 5px;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown("# 📊 briefAI Terminal")
    st.markdown("*Bloomberg-Grade AI Market Intelligence*")
    st.markdown("---")
    
    # Sidebar
    render_quick_stats()
    
    # Main content - 2x2 grid
    col1, col2 = st.columns(2)
    
    with col1:
        render_market_overview()
        st.markdown("---")
        render_top_movers()
    
    with col2:
        render_signal_heatmap()
        st.markdown("---")
        render_predictions_panel()
    
    # Bottom row
    st.markdown("---")
    col3, col4 = st.columns(2)
    
    with col3:
        render_alerts_panel()
    
    with col4:
        render_entity_search()
    
    # Footer
    st.markdown("---")
    st.markdown(f"*Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")


if __name__ == "__main__":
    main()
