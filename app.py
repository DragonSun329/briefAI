"""
BriefAI Streamlit Web Application - Unified Chat+Search Interface v3

Provides a professional interface for CEO to:
- View weekly AI industry briefings on the left (30%)
- Search articles or ask questions using unified LLM interface on the right (70%)
- All powered by Kimi/Moonshot with OpenRouter fallback
- Fully bilingual (Chinese/English)

Runs on Streamlit Cloud with automatic provider switching and rate limit handling.
"""

import streamlit as st
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import os
from utils.provider_switcher import ProviderSwitcher

# ============================================================================
# TRANSLATIONS - UI TEXT IN ENGLISH AND MANDARIN CHINESE
# ============================================================================

TRANSLATIONS = {
    "page_title": {
        "en": "AI Industry Weekly Briefing",
        "zh": "AI行业周报"
    },
    "subtitle": {
        "en": "Executive Summary & Insights",
        "zh": "高管摘要与洞察"
    },
    "mode_search": {
        "en": "Search",
        "zh": "搜索"
    },
    "mode_ask": {
        "en": "Ask Question",
        "zh": "提问"
    },
    "unified_input_search": {
        "en": "Search articles...",
        "zh": "搜索文章..."
    },
    "unified_input_ask": {
        "en": "Ask a question about the briefing...",
        "zh": "提问关于简报..."
    },
    "search_help": {
        "en": "Company/Model/Topic search powered by LLM",
        "zh": "由LLM驱动的公司/模型/主题搜索"
    },
    "about_brief": {
        "en": "ℹ️ About This Brief",
        "zh": "ℹ️ 关于此简报"
    },
    "about_description": {
        "en": "This briefing features the top 10 AI industry articles this week, selected by impact and novelty.",
        "zh": "此简报展示本周按影响和新颖性选择的前10篇AI行业文章。"
    },
    "report_date": {
        "en": "Report Date",
        "zh": "报告日期"
    },
    "last_updated": {
        "en": "Last Updated",
        "zh": "最后更新"
    },
    "articles": {
        "en": "Articles",
        "zh": "文章"
    },
    "executive_summary": {
        "en": "📊 Executive Summary",
        "zh": "📊 高管摘要"
    },
    "language": {
        "en": "🌐 Language",
        "zh": "🌐 语言"
    },
    "download": {
        "en": "⬇️ Download as Markdown",
        "zh": "⬇️ 下载Markdown"
    },
    "briefing": {
        "en": "Briefing",
        "zh": "简报"
    },
    "download_tab": {
        "en": "Download",
        "zh": "下载"
    },
    "chat_error": {
        "en": "Error answering question",
        "zh": "回答问题时出错"
    },
    "search_results_title": {
        "en": "📄 Search Results",
        "zh": "📄 搜索结果"
    },
    "no_results": {
        "en": "No articles matched your search",
        "zh": "没有文章与您的搜索匹配"
    },
    "ai_response": {
        "en": "💬 AI Response",
        "zh": "💬 AI回复"
    },
    "your_question": {
        "en": "You",
        "zh": "你"
    },
    "ai_assistant": {
        "en": "Assistant",
        "zh": "助手"
    },
}

def t(key: str, lang: str = "en", **kwargs) -> str:
    """Get translated text"""
    text = TRANSLATIONS.get(key, {}).get(lang, TRANSLATIONS.get(key, {}).get("en", key))
    return text.format(**kwargs) if kwargs else text

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="AI Industry Weekly Briefing",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize session state for language and chat
if "language" not in st.session_state:
    st.session_state.language = "zh"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "current_mode" not in st.session_state:
    st.session_state.current_mode = "search"
if "search_query" not in st.session_state:
    st.session_state.search_query = ""
if "search_results" not in st.session_state:
    st.session_state.search_results = None
if "provider_switcher" not in st.session_state:
    try:
        st.session_state.provider_switcher = ProviderSwitcher()
    except Exception as e:
        st.error(f"Failed to initialize LLM provider: {e}")
        st.session_state.provider_switcher = None

# ============================================================================
# CUSTOM STYLING
# ============================================================================

st.markdown("""
    <style>
    .main-title {
        font-size: 2.5em;
        font-weight: bold;
        margin-bottom: 0.3em;
        color: #1f77b4;
    }
    .subtitle-text {
        font-size: 1.1em;
        color: #555;
        margin-bottom: 1em;
    }
    .article-card {
        background-color: #f0f2f6;
        padding: 1.2em;
        border-radius: 0.5em;
        margin: 0.8em 0;
        border-left: 4px solid #1f77b4;
    }
    .article-title {
        font-size: 1.1em;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 0.5em;
    }
    .article-meta {
        font-size: 0.85em;
        color: #666;
        margin-bottom: 0.5em;
    }
    .article-summary {
        font-size: 0.95em;
        line-height: 1.5;
        color: #333;
    }
    .article-url {
        font-size: 0.85em;
        color: #1f77b4;
        text-decoration: none;
    }
    .chat-message {
        padding: 1em;
        border-radius: 0.5em;
        margin: 0.8em 0;
    }
    .chat-user {
        background-color: #e8f4f8;
        margin-left: 1em;
    }
    .chat-ai {
        background-color: #f0f0f0;
        margin-right: 1em;
    }
    .mode-selector {
        margin: 1em 0;
        padding: 1em;
        background-color: #f9f9f9;
        border-radius: 0.5em;
    }
    .search-result-item {
        background-color: #fafafa;
        padding: 1em;
        margin: 0.5em 0;
        border-left: 3px solid #1f77b4;
        border-radius: 0.3em;
    }
    .relevance-score {
        display: inline-block;
        background-color: #1f77b4;
        color: white;
        padding: 0.2em 0.5em;
        border-radius: 0.25em;
        font-size: 0.85em;
        margin-top: 0.5em;
    }
    </style>
""", unsafe_allow_html=True)

# ============================================================================
# LOAD BRIEFING DATA
# ============================================================================

def load_latest_briefing() -> Optional[Dict[str, Any]]:
    """Load the latest briefing from data/reports directory"""
    reports_dir = Path("./data/reports")
    if not reports_dir.exists():
        return None

    markdown_files = sorted(reports_dir.glob("briefing_*.md"), reverse=True)
    if not markdown_files:
        return None

    latest_file = markdown_files[0]

    # Try to find corresponding JSON file
    json_file = reports_dir / latest_file.stem.replace("briefing_", "briefing_") / ".json"

    # If JSON doesn't exist, look for data.json
    data_files = list(reports_dir.glob("**/data.json"))
    if data_files:
        with open(data_files[0], 'r', encoding='utf-8') as f:
            return json.load(f)

    # Fallback: create minimal structure from markdown
    return {
        "date": latest_file.stem.replace("briefing_", ""),
        "title": "AI Industry Weekly Briefing",
        "content": latest_file.read_text(encoding='utf-8'),
        "articles": []
    }

def search_articles_with_llm(query: str, briefing_content: str, lang: str = "en") -> str:
    """Use LLM to search and return matching articles"""
    if not st.session_state.provider_switcher:
        return t("chat_error", lang)

    try:
        system_prompt = f"""You are a helpful AI assistant that searches and retrieves relevant articles from a briefing.
The user wants to find articles related to their search query.
Return matching articles with the following format for each match:
**[Article Title]**
URL: [link]
Relevance: [High/Medium/Low]
Summary: [one sentence summary]

Always answer in {'Chinese' if lang == 'zh' else 'English'}.

BRIEFING CONTENT:
{briefing_content}"""

        response = st.session_state.provider_switcher.query(
            prompt=f"Search for articles related to: {query}",
            system_prompt=system_prompt,
            max_tokens=1024,
            temperature=0.7
        )
        return response
    except Exception as e:
        return f"{t('chat_error', lang)}: {str(e)}"

def answer_question_about_briefing(question: str, briefing_content: str, lang: str = "en") -> str:
    """Use LLM to answer questions about the briefing"""
    if not st.session_state.provider_switcher:
        return t("chat_error", lang)

    try:
        system_prompt = f"""You are a helpful assistant that answers questions about an AI industry briefing.
The user will ask questions about the briefing content.
Be concise, accurate, and reference specific articles when relevant.
Always answer in {'Chinese' if lang == 'zh' else 'English'}.

BRIEFING CONTENT:
{briefing_content}"""

        response = st.session_state.provider_switcher.query(
            prompt=question,
            system_prompt=system_prompt,
            max_tokens=1024,
            temperature=0.7
        )
        return response
    except Exception as e:
        return f"{t('chat_error', lang)}: {str(e)}"

# ============================================================================
# MAIN APP LAYOUT
# ============================================================================

# Header with title and language selector
col_title, col_lang = st.columns([0.85, 0.15])
with col_title:
    st.markdown(f"<div class='main-title'>{t('page_title', st.session_state.language)}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='subtitle-text'>{t('subtitle', st.session_state.language)}</div>", unsafe_allow_html=True)

with col_lang:
    st.session_state.language = st.selectbox(
        t('language', st.session_state.language),
        ["zh", "en"],
        format_func=lambda x: "中文" if x == "zh" else "English",
        index=0 if st.session_state.language == "zh" else 1,
        key="lang_selector",
        label_visibility="collapsed"
    )

# Load briefing data
briefing = load_latest_briefing()
if briefing is None:
    st.warning("No briefing data available. Please generate a briefing first.")
    st.stop()

# Main content: 30% briefing + 70% chat interface
left_col, right_col = st.columns([0.30, 0.70], gap="medium")

# ============================================================================
# LEFT COLUMN: BRIEFING DISPLAY
# ============================================================================
with left_col:
    # Executive summary section
    st.markdown(f"**{t('executive_summary', st.session_state.language)}**")

    if briefing.get("summary"):
        st.markdown(briefing["summary"])
    else:
        st.info(t('about_description', st.session_state.language))

    st.divider()

    # Briefing info
    if briefing.get("date"):
        st.caption(f"📅 {t('report_date', st.session_state.language)}: {briefing['date']}")

    st.divider()

    # Articles list
    st.markdown(f"**{t('articles', st.session_state.language)}**")

    if briefing.get("articles"):
        for idx, article in enumerate(briefing["articles"], 1):
            with st.container():
                st.markdown(f"<div class='article-card'>", unsafe_allow_html=True)
                st.markdown(f"**{idx}. {article.get('title', 'Untitled')}**")

                if article.get('source'):
                    st.caption(f"📌 {article['source']}")

                if article.get('summary'):
                    st.markdown(article['summary'])

                if article.get('url'):
                    st.markdown(f"[🔗 Read more]({article['url']})")

                st.markdown(f"</div>", unsafe_allow_html=True)
    else:
        st.info("No articles in this briefing")

    st.divider()

    # Download section
    if briefing.get("content"):
        briefing_text = briefing["content"]
        st.download_button(
            label=t('download', st.session_state.language),
            data=briefing_text,
            file_name=f"briefing_{briefing.get('date', 'report')}.md",
            mime="text/markdown"
        )

# ============================================================================
# RIGHT COLUMN: UNIFIED CHAT+SEARCH INTERFACE
# ============================================================================
with right_col:
    st.markdown("### 🤖 AI Assistant")

    # Mode selector as radio buttons
    st.markdown(f"<div class='mode-selector'>", unsafe_allow_html=True)
    st.session_state.current_mode = st.radio(
        "Mode / 模式",
        ["search", "ask"],
        format_func=lambda x: t('mode_search', st.session_state.language) if x == "search" else t('mode_ask', st.session_state.language),
        horizontal=True,
        label_visibility="collapsed",
        key="mode_selector"
    )
    st.markdown(f"</div>", unsafe_allow_html=True)

    # Input section
    if st.session_state.current_mode == "search":
        user_input = st.text_input(
            "Search / 搜索",
            placeholder=t('unified_input_search', st.session_state.language),
            key="search_input",
            label_visibility="collapsed"
        )
        st.caption(t('search_help', st.session_state.language))
    else:
        user_input = st.text_input(
            "Ask / 提问",
            placeholder=t('unified_input_ask', st.session_state.language),
            key="ask_input",
            label_visibility="collapsed"
        )

    st.divider()

    # Process user input and display results
    if user_input:
        if st.session_state.current_mode == "search":
            with st.spinner(f"🔍 {t('mode_search', st.session_state.language)}..." if st.session_state.language == "zh" else "Searching..."):
                response = search_articles_with_llm(user_input, briefing.get("content", ""), st.session_state.language)

            st.markdown(f"**{t('search_results_title', st.session_state.language)}**")
            if response and "Error" not in response:
                st.markdown(response)
            else:
                st.warning(t('no_results', st.session_state.language))

        else:  # Ask mode
            with st.spinner(f"💭 {t('mode_ask', st.session_state.language)}..." if st.session_state.language == "zh" else "Thinking..."):
                response = answer_question_about_briefing(user_input, briefing.get("content", ""), st.session_state.language)

            st.markdown(f"**{t('ai_response', st.session_state.language)}**")
            if response and "Error" not in response:
                st.markdown(response)
            else:
                st.error(response)

# ============================================================================
# FOOTER
# ============================================================================
st.divider()
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
