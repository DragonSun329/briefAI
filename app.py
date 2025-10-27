"""
BriefAI Streamlit Web Application - Enhanced Version

Provides a beautiful, bilingual (Chinese/English) interface for CEO to:
- View latest AI industry weekly briefings
- Ask questions about the briefing using AI chatbox
- Search articles by entities (companies, models, topics)
- Read detailed article paraphrases
- Download reports (Markdown or PDF)
- All in Mandarin Chinese or English

Runs on Streamlit Cloud - no installation needed.
API key securely stored in Streamlit Secrets.
"""

import streamlit as st
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import os
from anthropic import Anthropic

# Try to import PDF library for export
try:
    from fpdf import FPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# ============================================================================
# TRANSLATIONS - UI TEXT IN ENGLISH AND MANDARIN CHINESE
# ============================================================================

TRANSLATIONS = {
    "page_title": {
        "en": "AI Industry Weekly Briefing",
        "zh": "AI行业周报"
    },
    "subtitle": {
        "en": "Curated insights for executive decision-making",
        "zh": "为高管决策精心策划的见解"
    },
    "search_articles": {
        "en": "🔍 Search Articles",
        "zh": "🔍 搜索文章"
    },
    "search_by": {
        "en": "Search by:",
        "zh": "按以下搜索:"
    },
    "entity": {
        "en": "Entity",
        "zh": "实体"
    },
    "topic": {
        "en": "Topic",
        "zh": "主题"
    },
    "keyword": {
        "en": "Keyword",
        "zh": "关键词"
    },
    "enter_search_term": {
        "en": "Enter search term:",
        "zh": "输入搜索词:"
    },
    "placeholder_search": {
        "en": "e.g., Claude, reasoning, pricing",
        "zh": "例如：推理、定价、API"
    },
    "leave_empty": {
        "en": "Leave empty to see all articles",
        "zh": "留空查看所有文章"
    },
    "search_help": {
        "en": "Entity: Companies/Models | Topic: AI research areas | Keyword: Text search",
        "zh": "实体：公司/模型 | 主题：AI研究领域 | 关键词：文本搜索"
    },
    "ask_question": {
        "en": "💬 Ask Question About Briefing",
        "zh": "💬 提问关于简报"
    },
    "chat_placeholder": {
        "en": "Ask a question about the briefing...",
        "zh": "提问关于简报..."
    },
    "about_brief": {
        "en": "ℹ️ About This Brief",
        "zh": "ℹ️ 关于此简报"
    },
    "about_description": {
        "en": "This briefing features the top 10 AI industry articles this week, selected by impact and novelty. Each article includes entities (companies, models, topics) for easy searching.",
        "zh": "此简报展示本周按影响和新颖性选择的前10篇AI行业文章。每篇文章都包含实体（公司、模型、主题）以便于搜索。"
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
    "briefing": {
        "en": "📰 Briefing",
        "zh": "📰 简报"
    },
    "search": {
        "en": "🔎 Search",
        "zh": "🔎 搜索"
    },
    "download": {
        "en": "📥 Download",
        "zh": "📥 下载"
    },
    "executive_summary": {
        "en": "📊 Executive Summary & Key Insights",
        "zh": "📊 执行总结与关键见解"
    },
    "briefing_content": {
        "en": "Weekly Briefing",
        "zh": "周报内容"
    },
    "found_articles": {
        "en": "Found {} article(s)",
        "zh": "找到 {} 篇文章"
    },
    "article_n_of_m": {
        "en": "Article {} of {}",
        "zh": "文章 {} / {}"
    },
    "no_articles_found": {
        "en": "No articles found matching '{}'. Try a different search term.",
        "zh": "找不到匹配'{}'的文章。尝试不同的搜索词。"
    },
    "articles_unavailable": {
        "en": "Articles data not available. Refresh page in a moment.",
        "zh": "文章数据不可用。请稍后刷新页面。"
    },
    "download_report": {
        "en": "Download Report",
        "zh": "下载报告"
    },
    "download_markdown": {
        "en": "📥 Download as Markdown",
        "zh": "📥 下载为 Markdown"
    },
    "download_pdf": {
        "en": "📄 Download as PDF",
        "zh": "📄 下载为 PDF"
    },
    "download_note": {
        "en": "The report is also available at: {}",
        "zh": "报告也可在以下位置获得: {}"
    },
    "no_reports": {
        "en": "❌ No reports available yet. Reports are generated weekly on Fridays at 11 AM.",
        "zh": "❌ 尚无可用报告。报告在每周五上午11点生成。"
    },
    "check_back": {
        "en": "Check back later, or contact the briefing team for the latest update.",
        "zh": "请稍后再来，或联系简报团队了解最新信息。"
    },
    "companies": {
        "en": "Companies:",
        "zh": "公司:"
    },
    "models": {
        "en": "Models:",
        "zh": "模型:"
    },
    "topics": {
        "en": "Topics:",
        "zh": "主题:"
    },
    "business_models": {
        "en": "Business Models:",
        "zh": "商业模式:"
    },
    "read_full_summary": {
        "en": "📖 Read Full Summary",
        "zh": "📖 阅读完整摘要"
    },
    "language": {
        "en": "Language / 语言",
        "zh": "Language / 语言"
    },
    "english": {
        "en": "English",
        "zh": "中文"
    },
    "chinese": {
        "en": "中文",
        "zh": "中文"
    },
    "powered_by": {
        "en": "🤖 <strong>BriefAI</strong> - AI-Powered Weekly Industry Briefings",
        "zh": "🤖 <strong>BriefAI</strong> - AI驱动的周刊行业简报"
    },
    "generated_weekly": {
        "en": "Generated reports are updated every Friday at 11 AM",
        "zh": "生成的报告每周五上午11点更新"
    },
    "chat_thinking": {
        "en": "Analyzing briefing...",
        "zh": "分析简报中..."
    },
    "chat_error": {
        "en": "Error answering question. Please try again.",
        "zh": "回答问题时出错。请重试。"
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
    initial_sidebar_state="expanded"
)

# Initialize session state for language and chat
if "language" not in st.session_state:
    st.session_state.language = "zh"  # Default to Chinese since CEO can't read English
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "client" not in st.session_state:
    api_key = st.secrets.get("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY"))
    if api_key:
        st.session_state.client = Anthropic(api_key=api_key)
    else:
        st.session_state.client = None

# ============================================================================
# CUSTOM STYLING
# ============================================================================

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
        margin-right: 0.5em;
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
    .chat-message {
        padding: 1em;
        border-radius: 0.5em;
        margin: 0.5em 0;
    }
    .chat-user {
        background-color: #e8f4f8;
        margin-left: 1em;
    }
    .chat-ai {
        background-color: #f0f2f6;
        margin-right: 1em;
    }
    </style>
""", unsafe_allow_html=True)

# ============================================================================
# DATA LOADING FUNCTIONS
# ============================================================================

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
    try:
        content = latest_report.read_text(encoding='utf-8')
        return {
            'filename': latest_report.name,
            'path': latest_report,
            'content': content,
            'modified': datetime.fromtimestamp(latest_report.stat().st_mtime)
        }
    except Exception as e:
        st.error(f"Error loading report: {e}")
        return None


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
            articles = json.load(f)
            if isinstance(articles, list):
                return articles
            return None
    except Exception as e:
        st.error(f"Failed to load articles: {e}")
        return None


# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================

def display_article_card(article: Dict[str, Any], lang: str = "en", show_entities: bool = True):
    """Display a single article as a styled card"""

    title = article.get('title', 'Untitled')
    paraphrased = article.get('paraphrased_content', article.get('content', 'No content'))
    source = article.get('source', 'Unknown')
    score = article.get('weighted_score', article.get('tier2_score', 0))
    novelty = article.get('novelty_score', None)
    url = article.get('url', '#')
    entities = article.get('searchable_entities', {})

    with st.container():
        col1, col2 = st.columns([0.8, 0.2])

        with col1:
            st.markdown(f"### [{title}]({url})")

        with col2:
            score_text = f"{score:.1f}/10" if score else "N/A"
            st.markdown(f"<div class='score-badge'>{score_text}</div>", unsafe_allow_html=True)
            if novelty is not None:
                novelty_text = f"{novelty:.2f}"
                st.markdown(f"<div class='score-badge'>{novelty_text}</div>", unsafe_allow_html=True)

        st.markdown(f"<div class='source-badge'>📰 {source}</div>", unsafe_allow_html=True)

        with st.expander(t("read_full_summary", lang)):
            st.markdown(paraphrased)

        if show_entities and entities:
            entity_html = "<div style='margin-top: 0.5em;'>"

            if entities.get('companies'):
                entity_html += f"<strong>{t('companies', lang)}</strong> "
                for company in entities['companies'][:5]:
                    entity_html += f"<span class='entity-tag'>{company}</span>"
                entity_html += "<br>"

            if entities.get('models'):
                entity_html += f"<strong>{t('models', lang)}</strong> "
                for model in entities['models'][:5]:
                    entity_html += f"<span class='entity-tag'>{model}</span>"
                entity_html += "<br>"

            if entities.get('topics'):
                entity_html += f"<strong>{t('topics', lang)}</strong> "
                for topic in entities['topics'][:5]:
                    entity_html += f"<span class='entity-tag'>{topic}</span>"
                entity_html += "<br>"

            if entities.get('business_models'):
                entity_html += f"<strong>{t('business_models', lang)}</strong> "
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

    # Map search types to Chinese equivalents
    search_type_en = "Entity"
    if search_type in [t("topic", "zh"), "Topic"]:
        search_type_en = "Topic"
    elif search_type in [t("keyword", "zh"), "Keyword"]:
        search_type_en = "Keyword"

    for article in articles:
        match = False

        if search_type_en == "Entity":
            entities = article.get('searchable_entities', {})
            for entity_type, entity_list in entities.items():
                for entity in entity_list:
                    if search_lower in entity.lower():
                        match = True
                        break
                if match:
                    break

        elif search_type_en == "Topic":
            entities = article.get('searchable_entities', {})
            for entity_type in ['topics', 'business_models']:
                for entity in entities.get(entity_type, []):
                    if search_lower in entity.lower():
                        match = True
                        break
                if match:
                    break

        elif search_type_en == "Keyword":
            title = article.get('title', '').lower()
            content = article.get('paraphrased_content', '').lower()
            if search_lower in title or search_lower in content:
                match = True

        if match:
            results.append(article)

    return results


def generate_pdf(report_content: str, filename: str) -> bytes:
    """Generate PDF from report content"""
    if not PDF_AVAILABLE:
        return None

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)

    # Add title
    pdf.set_font("Helvetica", "B", size=16)
    pdf.cell(0, 10, "AI Industry Weekly Briefing", ln=True, align="C")
    pdf.ln(5)

    # Add content
    pdf.set_font("Helvetica", size=10)
    for line in report_content.split('\n'):
        if line.strip():
            # Handle markdown-style headers
            if line.startswith('##'):
                pdf.set_font("Helvetica", "B", size=12)
                pdf.multi_cell(0, 5, line.replace('##', '').strip())
                pdf.set_font("Helvetica", size=10)
            elif line.startswith('#'):
                pdf.set_font("Helvetica", "B", size=14)
                pdf.multi_cell(0, 5, line.replace('#', '').strip())
                pdf.set_font("Helvetica", size=10)
            else:
                pdf.multi_cell(0, 5, line)
        pdf.ln(2)

    return pdf.output()


def answer_question_about_briefing(question: str, briefing_content: str, lang: str = "en") -> str:
    """Use Claude to answer a question about the briefing"""
    if not st.session_state.client:
        return t("chat_error", lang)

    try:
        system_prompt = f"""You are a helpful assistant that answers questions about an AI industry briefing report.
The user will ask you questions about the briefing content provided below.
Always answer in the user's language. The briefing is in Chinese.
Be concise and accurate, referencing specific articles and details from the briefing when relevant.

BRIEFING CONTENT:
{briefing_content}

Always answer in {'Chinese' if lang == 'zh' else 'English'}."""

        response = st.session_state.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {"role": "user", "content": question}
            ]
        )
        return response.content[0].text
    except Exception as e:
        return f"{t('chat_error', lang)}: {str(e)}"


# ============================================================================
# MAIN APP
# ============================================================================

# Header with language selector
col_header_1, col_header_2 = st.columns([0.85, 0.15])
with col_header_1:
    st.markdown(f"<div class='main-title'>{t('page_title', st.session_state.language)}</div>", unsafe_allow_html=True)
    st.markdown(t('subtitle', st.session_state.language))

with col_header_2:
    st.session_state.language = st.selectbox(
        t('language', st.session_state.language),
        ["en", "zh"],
        format_func=lambda x: "English" if x == "en" else "中文",
        index=0 if st.session_state.language == "en" else 1,
        key="lang_selector"
    )

st.divider()

# Load data
report = load_latest_report()
articles_json = load_articles_json()

if not report:
    st.error(t('no_reports', st.session_state.language))
    st.info(t('check_back', st.session_state.language))
else:
    # Report metadata
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(t('report_date', st.session_state.language), report['modified'].strftime("%Y-%m-%d"))
    with col2:
        st.metric(t('last_updated', st.session_state.language), report['modified'].strftime("%I:%M %p"))
    with col3:
        st.metric(t('articles', st.session_state.language), len(articles_json) if articles_json else "0")

    st.divider()

    # Sidebar with search and chat
    with st.sidebar:
        # Language selector in sidebar
        st.session_state.language = st.radio(
            t('language', st.session_state.language),
            ["en", "zh"],
            format_func=lambda x: "English" if x == "en" else "中文",
            index=0 if st.session_state.language == "en" else 1,
            key="sidebar_lang"
        )

        st.divider()

        # Search section
        st.header(t('search_articles', st.session_state.language))

        search_type = st.selectbox(
            t('search_by', st.session_state.language),
            [t('entity', st.session_state.language), t('topic', st.session_state.language), t('keyword', st.session_state.language)],
            help=t('search_help', st.session_state.language)
        )

        search_term = st.text_input(
            t('enter_search_term', st.session_state.language),
            placeholder=t('placeholder_search', st.session_state.language),
            help=t('leave_empty', st.session_state.language)
        )

        st.divider()

        # Chat section
        st.subheader(t('ask_question', st.session_state.language))

        # Display chat history
        if st.session_state.chat_history:
            for msg in st.session_state.chat_history:
                role_class = "chat-user" if msg["role"] == "user" else "chat-ai"
                st.markdown(
                    f"<div class='chat-message {role_class}'>"
                    f"<strong>{'You' if msg['role'] == 'user' else 'Assistant'}:</strong> {msg['content']}"
                    f"</div>",
                    unsafe_allow_html=True
                )

        # Chat input
        question = st.chat_input(t('chat_placeholder', st.session_state.language))
        if question:
            # Add user message to history
            st.session_state.chat_history.append({"role": "user", "content": question})

            # Get AI response
            with st.spinner(t('chat_thinking', st.session_state.language)):
                response = answer_question_about_briefing(question, report['content'], st.session_state.language)

            # Add assistant message to history
            st.session_state.chat_history.append({"role": "assistant", "content": response})

            # Rerun to display new messages
            st.rerun()

        st.divider()

        # About section
        st.subheader(t('about_brief', st.session_state.language))
        st.info(t('about_description', st.session_state.language))

    # Main content tabs
    tab1, tab2, tab3 = st.tabs([
        t('briefing', st.session_state.language),
        t('search', st.session_state.language),
        t('download', st.session_state.language)
    ])

    with tab1:
        st.header(t('briefing_content', st.session_state.language))

        # Executive Summary first
        with st.expander(t('executive_summary', st.session_state.language), expanded=True):
            st.markdown(report['content'])

        st.divider()

        # Then articles
        st.subheader(t('articles', st.session_state.language))
        if articles_json:
            st.success(t('found_articles', st.session_state.language).format(len(articles_json)))
            for i, article in enumerate(articles_json, 1):
                st.markdown(f"#### {t('article_n_of_m', st.session_state.language).format(i, len(articles_json))}")
                display_article_card(article, st.session_state.language, show_entities=True)
        else:
            st.info(t('articles_unavailable', st.session_state.language))

    with tab2:
        st.header(t('search_articles', st.session_state.language))

        if articles_json:
            displayed_articles = search_articles(articles_json, search_term, search_type)

            if displayed_articles:
                st.success(t('found_articles', st.session_state.language).format(len(displayed_articles)))

                for i, article in enumerate(displayed_articles, 1):
                    st.markdown(f"#### {t('article_n_of_m', st.session_state.language).format(i, len(displayed_articles))}")
                    display_article_card(article, st.session_state.language, show_entities=True)
            else:
                st.warning(t('no_articles_found', st.session_state.language).format(search_term))
        else:
            st.info(t('articles_unavailable', st.session_state.language))

    with tab3:
        st.header(t('download_report', st.session_state.language))

        # Markdown download
        st.markdown("### Markdown")
        st.download_button(
            label=t('download_markdown', st.session_state.language),
            data=report['content'],
            file_name=f"briefing_{report['modified'].strftime('%Y%m%d')}.md",
            mime="text/markdown"
        )

        # PDF download (if available)
        if PDF_AVAILABLE:
            st.markdown("### PDF")
            pdf_data = generate_pdf(report['content'], f"briefing_{report['modified'].strftime('%Y%m%d')}.pdf")
            if pdf_data:
                st.download_button(
                    label=t('download_pdf', st.session_state.language),
                    data=pdf_data,
                    file_name=f"briefing_{report['modified'].strftime('%Y%m%d')}.pdf",
                    mime="application/pdf"
                )
        else:
            st.info("PDF export requires: pip install fpdf2")

        st.divider()
        st.info(
            t('download_note', st.session_state.language).format(f"`{report['path']}`")
        )

# Footer
st.divider()
st.markdown(
    f"""
    <div style='text-align: center; color: #7f7f7f; font-size: 0.85em; margin-top: 2em;'>
        <p>{t('powered_by', st.session_state.language)}</p>
        <p>{t('generated_weekly', st.session_state.language)}</p>
    </div>
    """,
    unsafe_allow_html=True
)
