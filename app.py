"""
BriefAI Streamlit Web Application

Provides a beautiful, user-friendly interface for CEO to:
- View latest AI industry weekly briefings
- Search articles by entities (companies, models, topics)
- Read detailed article paraphrases
- Download reports

Runs on Streamlit Cloud - no installation needed, just open URL in browser.
API key securely stored in Streamlit Secrets, hidden from users.
"""

import streamlit as st
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import os

# Page configuration
st.set_page_config(
    page_title="AI Industry Weekly Briefing",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom styling
st.markdown("""
    <style>
    .main-title {
        font-size: 2.5em;
        font-weight: bold;
        margin-bottom: 0.5em;
        color: #1f77b4;
    }
    .article-card {
        background-color: #f0f2f6;
        padding: 1.5em;
        border-radius: 0.5em;
        margin: 1em 0;
        border-left: 4px solid #1f77b4;
    }
    .score-badge {
        display: inline-block;
        background-color: #1f77b4;
        color: white;
        padding: 0.3em 0.6em;
        border-radius: 1em;
        font-weight: bold;
        font-size: 0.9em;
    }
    .source-badge {
        display: inline-block;
        background-color: #7f7f7f;
        color: white;
        padding: 0.2em 0.5em;
        border-radius: 0.25em;
        font-size: 0.85em;
        margin-left: 0.5em;
    }
    .entity-tag {
        display: inline-block;
        background-color: #e8f4f8;
        color: #1f77b4;
        padding: 0.2em 0.5em;
        border-radius: 0.25em;
        font-size: 0.85em;
        margin-right: 0.3em;
        margin-bottom: 0.3em;
    }
    </style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=3600)
def load_latest_report() -> Optional[Dict[str, Any]]:
    """Load the latest generated report from disk"""
    reports_dir = Path("data/reports")

    # Find all markdown report files
    reports = sorted(
        [f for f in reports_dir.glob("ai_briefing_*.md")],
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )

    if not reports:
        return None

    latest_report = reports[0]
    content = latest_report.read_text(encoding='utf-8')

    return {
        'filename': latest_report.name,
        'path': latest_report,
        'content': content,
        'modified': datetime.fromtimestamp(latest_report.stat().st_mtime)
    }


@st.cache_data(ttl=3600)
def load_articles_json() -> Optional[List[Dict[str, Any]]]:
    """Load cached articles with searchable entities"""
    cache_dir = Path("data/cache")

    # Try to load the latest article cache
    cache_files = sorted(
        [f for f in cache_dir.glob("*.json")],
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )

    if not cache_files:
        return None

    try:
        with open(cache_files[0], 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Failed to load articles: {e}")
        return None


def display_article_card(article: Dict[str, Any], show_entities: bool = True):
    """Display a single article as a styled card"""

    # Extract article data
    title = article.get('title', 'Untitled')
    paraphrased = article.get('paraphrased_content', article.get('content', 'No content'))
    source = article.get('source', 'Unknown')
    score = article.get('weighted_score', article.get('tier2_score', 0))
    novelty = article.get('novelty_score', None)
    url = article.get('url', '#')
    entities = article.get('searchable_entities', {})

    # Create article card
    with st.container():
        col1, col2 = st.columns([0.8, 0.2])

        with col1:
            # Title with link
            st.markdown(f"### [{title}]({url})")

        with col2:
            # Score badges
            score_text = f"**Score:** {score:.1f}/10" if score else "N/A"
            st.markdown(f"<div class='score-badge'>{score_text}</div>", unsafe_allow_html=True)
            if novelty is not None:
                novelty_text = f"**Novelty:** {novelty:.2f}"
                st.markdown(f"<div class='score-badge'>{novelty_text}</div>", unsafe_allow_html=True)

        # Source badge
        st.markdown(f"<div class='source-badge'>📰 {source}</div>", unsafe_allow_html=True)

        # Article content
        with st.expander("📖 Read Full Summary"):
            st.markdown(paraphrased)

        # Entities if available
        if show_entities and entities:
            entity_html = "<div style='margin-top: 0.5em;'>"

            # Companies
            if entities.get('companies'):
                entity_html += "<strong>Companies:</strong> "
                for company in entities['companies'][:5]:
                    entity_html += f"<span class='entity-tag'>{company}</span>"
                entity_html += "<br>"

            # Models
            if entities.get('models'):
                entity_html += "<strong>Models:</strong> "
                for model in entities['models'][:5]:
                    entity_html += f"<span class='entity-tag'>{model}</span>"
                entity_html += "<br>"

            # Topics
            if entities.get('topics'):
                entity_html += "<strong>Topics:</strong> "
                for topic in entities['topics'][:5]:
                    entity_html += f"<span class='entity-tag'>{topic}</span>"
                entity_html += "<br>"

            # Business models
            if entities.get('business_models'):
                entity_html += "<strong>Business Models:</strong> "
                for bm in entities['business_models'][:3]:
                    entity_html += f"<span class='entity-tag'>{bm}</span>"

            entity_html += "</div>"
            st.markdown(entity_html, unsafe_allow_html=True)

        st.divider()


def search_articles(articles: List[Dict[str, Any]], search_term: str, search_type: str) -> List[Dict[str, Any]]:
    """Search articles by entity or keyword"""

    if not search_term or not articles:
        return articles

    search_lower = search_term.lower()
    results = []

    for article in articles:
        match = False

        if search_type == "Entity":
            # Search in searchable entities
            entities = article.get('searchable_entities', {})
            for entity_type, entity_list in entities.items():
                for entity in entity_list:
                    if search_lower in entity.lower():
                        match = True
                        break
                if match:
                    break

        elif search_type == "Topic":
            # Search in topics and business models
            entities = article.get('searchable_entities', {})
            for entity_type in ['topics', 'business_models']:
                for entity in entities.get(entity_type, []):
                    if search_lower in entity.lower():
                        match = True
                        break
                if match:
                    break

        elif search_type == "Keyword":
            # Search in title and content
            title = article.get('title', '').lower()
            content = article.get('paraphrased_content', '').lower()
            if search_lower in title or search_lower in content:
                match = True

        if match:
            results.append(article)

    return results


# ============================================================================
# MAIN APP
# ============================================================================

# Header
st.markdown("<div class='main-title'>📊 AI Industry Weekly Briefing</div>", unsafe_allow_html=True)
st.markdown("*Curated insights for executive decision-making*")
st.divider()

# Load data
report = load_latest_report()
articles_json = load_articles_json()

if not report:
    st.error("❌ No reports available yet. Reports are generated weekly on Fridays at 11 AM.")
    st.info("Check back later, or contact the briefing team for the latest update.")
else:
    # Report metadata
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Report Date", report['modified'].strftime("%Y-%m-%d"))
    with col2:
        st.metric("Last Updated", report['modified'].strftime("%I:%M %p"))
    with col3:
        st.metric("Articles", len(articles_json) if articles_json else "0")

    st.divider()

    # Sidebar search
    with st.sidebar:
        st.header("🔍 Search Articles")

        search_type = st.selectbox(
            "Search by:",
            ["Entity", "Topic", "Keyword"],
            help="Entity: Companies/Models | Topic: AI research areas | Keyword: Text search"
        )

        search_term = st.text_input(
            "Enter search term:",
            placeholder="e.g., Claude, reasoning, pricing",
            help="Leave empty to see all articles"
        )

        st.divider()

        st.subheader("ℹ️ About This Brief")
        st.info(
            "This briefing features the top 10 AI industry articles this week, "
            "selected by impact and novelty. Each article includes entities (companies, models, topics) "
            "for easy searching."
        )

    # Main content tabs
    tab1, tab2, tab3 = st.tabs(["📰 Articles", "📊 Executive Summary", "📥 Download"])

    with tab1:
        st.header("Weekly Article Briefing")

        if articles_json:
            # Apply search filter
            displayed_articles = search_articles(articles_json, search_term, search_type)

            if displayed_articles:
                st.success(f"Found {len(displayed_articles)} article(s)")

                for i, article in enumerate(displayed_articles, 1):
                    st.markdown(f"#### Article {i} of {len(displayed_articles)}")
                    display_article_card(article, show_entities=True)
            else:
                st.warning(f"No articles found matching '{search_term}'. Try a different search term.")
        else:
            st.info("Articles data not available. Refresh page in a moment.")

    with tab2:
        st.header("Executive Summary & Key Insights")
        st.markdown(report['content'])

    with tab3:
        st.header("Download Report")
        st.markdown("### Markdown Report")
        st.download_button(
            label="📥 Download as Markdown",
            data=report['content'],
            file_name=f"briefing_{report['modified'].strftime('%Y%m%d')}.md",
            mime="text/markdown"
        )

        st.info(
            "The report is also available in the following locations:\n"
            f"- Generated: `{report['path']}`\n"
            "- Latest report accessible via web UI (this page)"
        )

# Footer
st.divider()
st.markdown(
    """
    <div style='text-align: center; color: #7f7f7f; font-size: 0.85em; margin-top: 2em;'>
        <p>🤖 <strong>BriefAI</strong> - Powered by Anthropic Claude | Weekly AI Industry Briefings</p>
        <p>Generated reports are updated every Friday at 11 AM</p>
    </div>
    """,
    unsafe_allow_html=True
)
