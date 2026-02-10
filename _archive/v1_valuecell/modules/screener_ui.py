"""
Screener UI Module

Streamlit component for building, running, and managing custom screeners.
Provides intuitive drag-and-drop filter builder with real-time preview.

Features:
- Visual filter builder with field autocomplete
- Real-time entity count preview
- Preset screener gallery
- Save/load custom screeners
- Export results to CSV
"""

from __future__ import annotations

import io
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

import streamlit as st
import pandas as pd
from loguru import logger

# Import screener components
import sys
_utils_dir = Path(__file__).parent.parent / "utils"
if str(_utils_dir) not in sys.path:
    sys.path.insert(0, str(_utils_dir.parent))

from utils.screener_engine import (
    ScreenerEngine, Criterion, CriteriaGroup, Screener,
    FilterOperator, CriterionType, LogicalOperator,
    SCREENABLE_FIELDS, create_score_filter, create_momentum_filter,
    create_field_comparison, create_category_filter
)
from utils.screener_dsl import (
    parse_query, validate_query, explain_query, QueryBuilder, DSLParseError
)


# =============================================================================
# Constants
# =============================================================================

OPERATOR_LABELS = {
    FilterOperator.EQ: "equals (=)",
    FilterOperator.NEQ: "not equals (≠)",
    FilterOperator.GT: "greater than (>)",
    FilterOperator.GTE: "greater than or equal (≥)",
    FilterOperator.LT: "less than (<)",
    FilterOperator.LTE: "less than or equal (≤)",
    FilterOperator.IN: "is one of",
    FilterOperator.NOT_IN: "is not one of",
    FilterOperator.CONTAINS: "contains",
    FilterOperator.BETWEEN: "between",
    FilterOperator.FIELD_GT: "greater than field",
    FilterOperator.FIELD_LT: "less than field",
}

CRITERION_TYPE_ICONS = {
    CriterionType.SCORE: "📊",
    CriterionType.MOMENTUM: "📈",
    CriterionType.CATEGORY: "🏷️",
    CriterionType.SIGNAL: "🚦",
    CriterionType.DATE: "📅",
    CriterionType.COMPARISON: "⚖️",
}


# =============================================================================
# Session State Helpers
# =============================================================================

def init_screener_state():
    """Initialize session state for screener UI."""
    if "screener_criteria" not in st.session_state:
        st.session_state.screener_criteria = []
    if "screener_results" not in st.session_state:
        st.session_state.screener_results = None
    if "screener_name" not in st.session_state:
        st.session_state.screener_name = ""
    if "dsl_query" not in st.session_state:
        st.session_state.dsl_query = ""
    if "screener_engine" not in st.session_state:
        st.session_state.screener_engine = ScreenerEngine()


def get_engine() -> ScreenerEngine:
    """Get the screener engine from session state."""
    init_screener_state()
    return st.session_state.screener_engine


# =============================================================================
# Main UI Component
# =============================================================================

def render_screener_dashboard():
    """Render the complete screener dashboard."""
    init_screener_state()
    
    st.title("🔍 Custom Screener")
    st.markdown("Build custom filters to find entities matching your criteria.")
    
    # Create tabs for different modes
    tab1, tab2, tab3, tab4 = st.tabs([
        "📝 Filter Builder",
        "💻 DSL Query",
        "📋 Presets",
        "💾 Saved Screeners"
    ])
    
    with tab1:
        render_filter_builder()
    
    with tab2:
        render_dsl_mode()
    
    with tab3:
        render_preset_gallery()
    
    with tab4:
        render_saved_screeners()
    
    # Always show results if available
    if st.session_state.screener_results:
        st.divider()
        render_results()


def render_filter_builder():
    """Render the visual filter builder."""
    st.subheader("Build Your Filter")
    
    # Add criterion form
    with st.expander("➕ Add Filter Criterion", expanded=True):
        render_add_criterion_form()
    
    # Show current criteria
    if st.session_state.screener_criteria:
        st.subheader(f"Active Filters ({len(st.session_state.screener_criteria)})")
        render_criteria_list()
    
    # Run button
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        if st.button("🔎 Run Screener", type="primary", use_container_width=True):
            run_screener()
    
    with col2:
        if st.button("🔄 Clear All", use_container_width=True):
            st.session_state.screener_criteria = []
            st.session_state.screener_results = None
            st.rerun()
    
    with col3:
        if st.session_state.screener_criteria:
            if st.button("💾 Save", use_container_width=True):
                render_save_dialog()


def render_add_criterion_form():
    """Render the form to add a new criterion."""
    col1, col2, col3 = st.columns([2, 1, 2])
    
    # Field selection
    with col1:
        fields = list(SCREENABLE_FIELDS.keys())
        field_options = {f: f"{SCREENABLE_FIELDS[f].get('description', f)} ({f})" for f in fields}
        
        selected_field = st.selectbox(
            "Field",
            options=fields,
            format_func=lambda x: field_options.get(x, x),
            key="add_criterion_field"
        )
        
        field_info = SCREENABLE_FIELDS.get(selected_field, {})
    
    # Operator selection
    with col2:
        field_type = field_info.get("type", "float")
        
        # Filter operators based on field type
        if field_type == "bool":
            available_ops = [FilterOperator.EQ, FilterOperator.NEQ]
        elif field_type == "str":
            available_ops = [FilterOperator.EQ, FilterOperator.NEQ, FilterOperator.IN, 
                           FilterOperator.NOT_IN, FilterOperator.CONTAINS]
        else:
            available_ops = [FilterOperator.GT, FilterOperator.GTE, FilterOperator.LT, 
                           FilterOperator.LTE, FilterOperator.EQ, FilterOperator.BETWEEN,
                           FilterOperator.FIELD_GT, FilterOperator.FIELD_LT]
        
        selected_op = st.selectbox(
            "Operator",
            options=available_ops,
            format_func=lambda x: OPERATOR_LABELS.get(x, str(x)),
            key="add_criterion_op"
        )
    
    # Value input
    with col3:
        value = render_value_input(selected_field, field_info, selected_op)
    
    # Add button
    if st.button("➕ Add Filter"):
        add_criterion(selected_field, selected_op, value, field_info)
        st.rerun()


def render_value_input(field: str, field_info: Dict, operator: FilterOperator) -> Any:
    """Render appropriate value input based on field type and operator."""
    field_type = field_info.get("type", "float")
    
    # Field comparison operators
    if operator in [FilterOperator.FIELD_GT, FilterOperator.FIELD_LT, 
                    FilterOperator.FIELD_GTE, FilterOperator.FIELD_LTE]:
        comparable_fields = [f for f in SCREENABLE_FIELDS if SCREENABLE_FIELDS[f].get("type") == field_type]
        return st.selectbox(
            "Compare to Field",
            options=[f for f in comparable_fields if f != field],
            key="add_criterion_compare_field"
        )
    
    # Boolean fields
    if field_type == "bool":
        return st.checkbox("Value", value=True, key="add_criterion_bool_value")
    
    # Enum/category fields
    if "values" in field_info:
        if operator == FilterOperator.IN:
            return st.multiselect(
                "Values",
                options=field_info["values"],
                key="add_criterion_multi_value"
            )
        return st.selectbox(
            "Value",
            options=field_info["values"],
            key="add_criterion_enum_value"
        )
    
    # Numeric fields
    if field_type in ("float", "int"):
        value_range = field_info.get("range", (0, 100))
        
        if operator == FilterOperator.BETWEEN:
            col_a, col_b = st.columns(2)
            with col_a:
                low = st.number_input("Min", value=float(value_range[0]), key="add_criterion_min")
            with col_b:
                high = st.number_input("Max", value=float(value_range[1]), key="add_criterion_max")
            return [low, high]
        
        # For momentum fields, show as percentage
        is_momentum = field_info.get("category") == "momentum"
        label = "Value (%)" if is_momentum else "Value"
        
        return st.number_input(
            label,
            min_value=float(value_range[0]),
            max_value=float(value_range[1]),
            value=float((value_range[0] + value_range[1]) / 2),
            key="add_criterion_num_value"
        )
    
    # Date fields
    if field_type == "date":
        col_a, col_b = st.columns(2)
        with col_a:
            days_ago = st.number_input("Days ago", min_value=1, value=7, key="add_criterion_days")
        with col_b:
            st.write("")  # Spacer
            st.write(f"Filter for dates > {days_ago} days ago")
        return f"{days_ago} days ago"
    
    # Default: text input
    return st.text_input("Value", key="add_criterion_text_value")


def add_criterion(field: str, operator: FilterOperator, value: Any, field_info: Dict):
    """Add a criterion to the current filter set."""
    # Determine criterion type
    category = field_info.get("category", "scores")
    type_map = {
        "scores": CriterionType.SCORE,
        "momentum": CriterionType.MOMENTUM,
        "category": CriterionType.CATEGORY,
        "signals": CriterionType.SIGNAL,
        "dates": CriterionType.DATE,
    }
    criterion_type = type_map.get(category, CriterionType.SCORE)
    
    # Handle field comparison
    compare_field = None
    if operator in [FilterOperator.FIELD_GT, FilterOperator.FIELD_LT,
                    FilterOperator.FIELD_GTE, FilterOperator.FIELD_LTE]:
        compare_field = value
        value = None
        criterion_type = CriterionType.COMPARISON
    
    criterion = Criterion(
        field=field,
        operator=operator,
        value=value,
        criterion_type=criterion_type,
        compare_field=compare_field,
        label=f"{field} {operator.value} {compare_field or value}"
    )
    
    st.session_state.screener_criteria.append(criterion)
    st.success(f"Added filter: {criterion.label}")


def render_criteria_list():
    """Render the list of current criteria with delete buttons."""
    for i, criterion in enumerate(st.session_state.screener_criteria):
        col1, col2, col3 = st.columns([1, 6, 1])
        
        with col1:
            icon = CRITERION_TYPE_ICONS.get(CriterionType(criterion.criterion_type), "📊")
            st.write(icon)
        
        with col2:
            if criterion.compare_field:
                label = f"{criterion.field} {criterion.operator} {criterion.compare_field}"
            else:
                value_str = criterion.value
                if isinstance(value_str, list):
                    value_str = ", ".join(str(v) for v in value_str)
                label = f"{criterion.field} {criterion.operator} {value_str}"
            
            st.write(f"**{label}**")
        
        with col3:
            if st.button("🗑️", key=f"delete_criterion_{i}"):
                st.session_state.screener_criteria.pop(i)
                st.rerun()


def render_dsl_mode():
    """Render the DSL query mode."""
    st.subheader("Write Query (DSL)")
    st.markdown("""
    Write queries using a simple language:
    - `media_score > 7 AND momentum_7d > 10%`
    - `sector IN ("ai-foundation", "ai-infrastructure")`
    - `has_divergence = true AND divergence_strength > 0.5`
    - `media_score > technical_score`
    - `last_signal_date > 7 days ago`
    """)
    
    query = st.text_area(
        "Query",
        value=st.session_state.dsl_query,
        height=100,
        placeholder='media_score > 7 AND momentum_7d > 10%',
        key="dsl_query_input"
    )
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        if st.button("🔎 Run Query", type="primary", use_container_width=True):
            if query.strip():
                st.session_state.dsl_query = query
                run_dsl_query(query)
    
    with col2:
        if st.button("✅ Validate", use_container_width=True):
            if query.strip():
                is_valid, error = validate_query(query)
                if is_valid:
                    st.success("Query is valid!")
                else:
                    st.error(f"Invalid: {error}")
    
    with col3:
        if st.button("📖 Explain", use_container_width=True):
            if query.strip():
                render_query_explanation(query)


def render_query_explanation(query: str):
    """Show query explanation in an expander."""
    try:
        explanation = explain_query(query)
        
        if explanation["valid"]:
            st.json(explanation)
        else:
            st.error(explanation["error"])
    except Exception as e:
        st.error(f"Error explaining query: {e}")


def run_dsl_query(query: str):
    """Run a DSL query."""
    try:
        engine = get_engine()
        group = parse_query(query)
        result = engine.screen_with_group(group, limit=100)
        st.session_state.screener_results = result
        st.success(f"Found {result.matching_entities} matching entities")
    except DSLParseError as e:
        st.error(f"Parse error: {e}")
    except Exception as e:
        st.error(f"Error running query: {e}")


def render_preset_gallery():
    """Render the preset screener gallery."""
    st.subheader("Preset Screeners")
    
    engine = get_engine()
    presets = engine.get_preset_screeners()
    
    if not presets:
        st.info("No preset screeners available.")
        return
    
    # Group by category
    categories = {}
    for preset in presets:
        cat = preset.category or "Other"
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(preset)
    
    # Render by category
    for category, cat_presets in categories.items():
        st.markdown(f"### {category.title()}")
        
        cols = st.columns(2)
        for i, preset in enumerate(cat_presets):
            with cols[i % 2]:
                with st.container(border=True):
                    st.markdown(f"**{preset.name}**")
                    st.caption(preset.description or "")
                    
                    if preset.tags:
                        st.write(" ".join(f"`{tag}`" for tag in preset.tags[:3]))
                    
                    if st.button("▶️ Run", key=f"run_preset_{preset.name}", use_container_width=True):
                        run_preset(preset.name)


def run_preset(name: str):
    """Run a preset screener."""
    try:
        engine = get_engine()
        result = engine.run_screener(name)
        st.session_state.screener_results = result
        st.success(f"Ran '{name}': {result.matching_entities} matches")
    except Exception as e:
        st.error(f"Error running preset: {e}")


def render_saved_screeners():
    """Render saved custom screeners."""
    st.subheader("Saved Screeners")
    
    engine = get_engine()
    screeners = engine.list_screeners(include_presets=False)
    
    if not screeners:
        st.info("No saved screeners yet. Build one in the Filter Builder tab!")
        return
    
    for screener in screeners:
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            
            with col1:
                st.markdown(f"**{screener['name']}**")
                st.caption(screener.get('description', ''))
                st.write(f"{screener['criteria_count']} criteria")
            
            with col2:
                if screener.get('last_match_count') is not None:
                    st.metric("Last", screener['last_match_count'])
            
            with col3:
                if st.button("▶️", key=f"run_saved_{screener['name']}"):
                    run_preset(screener['name'])
            
            with col4:
                if st.button("🗑️", key=f"delete_saved_{screener['name']}"):
                    engine.delete_screener(screener['name'])
                    st.rerun()


def run_screener():
    """Run the current criteria set."""
    if not st.session_state.screener_criteria:
        st.warning("Add at least one filter criterion.")
        return
    
    try:
        engine = get_engine()
        result = engine.screen(
            criteria=st.session_state.screener_criteria,
            limit=100,
            sort_by="composite_score",
            sort_order="desc"
        )
        st.session_state.screener_results = result
        st.success(f"Found {result.matching_entities} matching entities out of {result.total_entities}")
    except Exception as e:
        st.error(f"Error running screener: {e}")
        logger.exception("Screener error")


def render_save_dialog():
    """Render dialog to save current screener."""
    with st.form("save_screener_form"):
        name = st.text_input("Screener Name", value=st.session_state.screener_name)
        description = st.text_area("Description", placeholder="What does this screener find?")
        tags = st.text_input("Tags (comma-separated)", placeholder="ai, momentum, opportunities")
        
        if st.form_submit_button("💾 Save Screener"):
            if not name:
                st.error("Please enter a name.")
            else:
                engine = get_engine()
                tag_list = [t.strip() for t in tags.split(",") if t.strip()]
                
                screener = Screener(
                    name=name,
                    description=description,
                    criteria=st.session_state.screener_criteria,
                    tags=tag_list
                )
                
                engine.save_screener(name, st.session_state.screener_criteria, screener)
                st.session_state.screener_name = name
                st.success(f"Saved screener: {name}")


def render_results():
    """Render screener results."""
    result = st.session_state.screener_results
    
    st.subheader(f"Results: {result.matching_entities} Matches")
    st.caption(f"Screener: {result.screener_name} | Executed in {result.execution_time_ms:.1f}ms")
    st.caption(f"Criteria: {result.criteria_summary}")
    
    if not result.results:
        st.info("No entities matched your criteria.")
        return
    
    # Convert to DataFrame
    df = pd.DataFrame(result.results)
    
    # Select display columns
    display_cols = [
        "entity_name", "entity_type", "composite_score",
        "technical_score", "media_score", "financial_score",
        "product_score", "momentum_7d", "momentum_30d"
    ]
    display_cols = [c for c in display_cols if c in df.columns]
    
    # Format scores
    df_display = df[display_cols].copy()
    score_cols = [c for c in display_cols if 'score' in c]
    for col in score_cols:
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "-")
    
    momentum_cols = [c for c in display_cols if 'momentum' in c]
    for col in momentum_cols:
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(
                lambda x: f"{x:+.1f}%" if pd.notna(x) else "-"
            )
    
    # Display with Streamlit
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "entity_name": st.column_config.TextColumn("Entity", width="medium"),
            "entity_type": st.column_config.TextColumn("Type", width="small"),
            "composite_score": st.column_config.TextColumn("Composite", width="small"),
            "technical_score": st.column_config.TextColumn("Technical", width="small"),
            "media_score": st.column_config.TextColumn("Media", width="small"),
            "financial_score": st.column_config.TextColumn("Financial", width="small"),
            "product_score": st.column_config.TextColumn("Product", width="small"),
            "momentum_7d": st.column_config.TextColumn("7d Mom.", width="small"),
            "momentum_30d": st.column_config.TextColumn("30d Mom.", width="small"),
        }
    )
    
    # Export buttons
    col1, col2 = st.columns(2)
    
    with col1:
        csv = df.to_csv(index=False)
        st.download_button(
            "📥 Download CSV",
            csv,
            file_name=f"screener_{result.screener_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col2:
        json_data = json.dumps(result.results, indent=2, default=str)
        st.download_button(
            "📥 Download JSON",
            json_data,
            file_name=f"screener_{result.screener_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            use_container_width=True
        )


# =============================================================================
# Widget Functions (for embedding in other pages)
# =============================================================================

def screener_widget(title: str = "Quick Screen", default_query: str = "") -> Optional[List[Dict]]:
    """
    Compact screener widget for embedding in other pages.
    
    Args:
        title: Widget title
        default_query: Default DSL query
        
    Returns:
        List of matching entities or None
    """
    init_screener_state()
    
    with st.expander(title, expanded=False):
        query = st.text_input(
            "Query",
            value=default_query,
            placeholder='media_score > 50 AND momentum_7d > 0',
            key=f"widget_query_{title}"
        )
        
        if st.button("Search", key=f"widget_run_{title}"):
            if query.strip():
                try:
                    engine = get_engine()
                    group = parse_query(query)
                    result = engine.screen_with_group(group, limit=20)
                    
                    st.write(f"**{result.matching_entities} matches**")
                    
                    if result.results:
                        df = pd.DataFrame(result.results)
                        cols = ["entity_name", "composite_score", "momentum_7d"]
                        cols = [c for c in cols if c in df.columns]
                        st.dataframe(df[cols].head(10), hide_index=True)
                    
                    return result.results
                    
                except Exception as e:
                    st.error(f"Error: {e}")
    
    return None


def preset_dropdown_widget(callback=None) -> Optional[str]:
    """
    Dropdown widget to select and run preset screeners.
    
    Args:
        callback: Optional callback function(result) after running
        
    Returns:
        Selected preset name or None
    """
    init_screener_state()
    engine = get_engine()
    presets = engine.get_preset_screeners()
    
    if not presets:
        return None
    
    preset_names = ["Select a preset..."] + [p.name for p in presets]
    
    selected = st.selectbox("Preset Screener", preset_names, key="preset_dropdown")
    
    if selected and selected != "Select a preset...":
        if st.button("Run", key="preset_dropdown_run"):
            result = engine.run_screener(selected)
            st.session_state.screener_results = result
            
            if callback:
                callback(result)
            
            return selected
    
    return None


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point for standalone screener page."""
    st.set_page_config(
        page_title="briefAI Screener",
        page_icon="🔍",
        layout="wide"
    )
    render_screener_dashboard()


if __name__ == "__main__":
    main()
