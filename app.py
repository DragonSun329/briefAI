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
if "selected_briefing" not in st.session_state:
    st.session_state.selected_briefing = None
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

def parse_articles_from_markdown(content: str) -> List[Dict[str, str]]:
    """Parse articles from markdown briefing content"""
    articles = []
    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]
        # Look for article titles (numbered like "**1. Title**" or "**1. AI投资分析系统")
        if line.startswith('**') and line[2].isdigit() and '. ' in line:
            # Extract title - remove asterisks and number prefix
            title_raw = line.strip('*').strip()
            # Remove the number and dot prefix (e.g., "1. " or "10. ")
            if '. ' in title_raw:
                title = title_raw.split('. ', 1)[1]
            else:
                title = title_raw

            summary = ""
            url = ""
            source = ""

            i += 1
            # Collect lines until we hit next article or end
            while i < len(lines):
                current_line = lines[i].strip()

                # Stop if we hit the next article
                if current_line.startswith('**') and len(current_line) > 2 and current_line[2].isdigit():
                    break

                # Extract source - look for "**来源**: value" or "**来源**:" patterns
                if '**来源**' in current_line and ':' in current_line:
                    # Extract everything after the colon
                    source = current_line.split(':', 1)[1].strip()
                elif current_line.startswith('**来源'):
                    # Fallback pattern
                    parts = current_line.split(':', 1)
                    if len(parts) > 1:
                        source = parts[1].strip()

                # Extract URL - look for "**URL**: value" patterns
                elif '**URL**' in current_line and ':' in current_line:
                    url = current_line.split(':', 1)[1].strip()
                elif 'URL:' in current_line:
                    url = current_line.split(':', 1)[1].strip()

                # First non-empty non-metadata line is the summary
                elif summary == "" and current_line and not current_line.startswith('**'):
                    summary = current_line

                i += 1

            if title.strip():
                articles.append({
                    "title": title.strip(),
                    "summary": summary[:200] if summary else "无摘要",
                    "url": url if url else "",
                    "source": source if source else ""
                })
            continue

        i += 1

    return articles

def create_enriched_briefing_context(articles: List[Dict[str, str]]) -> str:
    """
    Create enriched context for LLM with full article information
    Includes article summaries, sources, URLs, and explanations
    """
    if not articles:
        return "No articles available."

    context_lines = []
    context_lines.append("# 本周精选文章\n")

    for idx, article in enumerate(articles, 1):
        context_lines.append(f"## {idx}. {article.get('title', 'Untitled')}")
        context_lines.append("")

        if article.get('summary'):
            context_lines.append(article['summary'])
            context_lines.append("")

        if article.get('source') or article.get('url'):
            meta_parts = []
            if article.get('source'):
                meta_parts.append(f"来源: {article['source']}")
            if article.get('url'):
                meta_parts.append(f"URL: {article['url']}")
            context_lines.append(" | ".join(meta_parts))
            context_lines.append("")

    context_lines.append("\n---\n")
    context_lines.append("使用说明:")
    context_lines.append("- 分析文章时，请参考完整内容")
    context_lines.append("- 找出每篇文章的中心论点（central argument）")
    context_lines.append("- 指出支撑论点的数据和证据（data and evidence）")
    context_lines.append("- 如果用户要求，可以从URL获取完整文章进行更深入分析")

    return "\n".join(context_lines)

def load_latest_briefing() -> Optional[Dict[str, Any]]:
    """Load the latest briefing from data/reports directory"""
    reports_dir = Path("./data/reports")
    if not reports_dir.exists():
        return None

    # Look for both briefing_*.md and ai_briefing_*.md patterns
    markdown_files = sorted(reports_dir.glob("*briefing_*.md"), reverse=True)
    if not markdown_files:
        return None

    latest_file = markdown_files[0]

    # Try to find corresponding JSON file
    json_file = reports_dir / latest_file.stem / "data.json"

    # If JSON doesn't exist, look for data.json
    data_files = list(reports_dir.glob("**/data.json"))
    if data_files:
        with open(data_files[0], 'r', encoding='utf-8') as f:
            return json.load(f)

    # Load markdown and parse articles
    content = latest_file.read_text(encoding='utf-8')
    articles = parse_articles_from_markdown(content)

    # Fallback: create structure from markdown
    return {
        "date": latest_file.stem.replace("ai_briefing_", "").replace("briefing_", ""),
        "title": "AI Industry Weekly Briefing",
        "content": content,
        "articles": articles
    }

def get_available_briefings() -> List[Dict[str, Any]]:
    """Get list of all available briefings (for archive)"""
    reports_dir = Path("./data/reports")
    if not reports_dir.exists():
        return []

    briefings = []
    markdown_files = sorted(reports_dir.glob("*briefing_*.md"), reverse=True)

    for file in markdown_files:
        date_str = file.stem.replace("ai_briefing_", "").replace("briefing_", "")
        briefings.append({
            "date": date_str,
            "filename": file.name,
            "path": file
        })

    return briefings

def search_articles_with_llm(query: str, briefing_content: str, lang: str = "en") -> str:
    """Use LLM to search and return matching articles with detailed analysis"""
    if not st.session_state.provider_switcher:
        return t("chat_error", lang)

    try:
        system_prompt = f"""你是一位AI行业搜索专家。用户需要找到与其查询相关的文章。

搜索要求:
1. 找到所有与用户查询相关的文章
2. 对每篇匹配的文章进行详细分析
3. 说明为什么这篇文章与查询相关
4. 提供具体的证据或摘录支持您的判断

返回格式（对每篇匹配的文章）:
**[文章标题]**
来源: [来源]
URL: [链接]
相关度: [高/中/低]
相关原因: [简要说明这篇文章为什么与查询相关，包括具体的数据或证据]

重要提示:
- 如果找不到相关文章，明确说明
- 不要编造不存在的文章
- 使用中文回答
- 深入分析而不仅仅返回标题

以下是本周的文章内容:

{briefing_content}"""

        response = st.session_state.provider_switcher.query(
            prompt=f"根据以下查询搜索文章: {query}",
            system_prompt=system_prompt,
            max_tokens=1024,
            temperature=0.7
        )
        return response
    except Exception as e:
        return f"{t('chat_error', lang)}: {str(e)}"

def answer_question_about_briefing(question: str, briefing_content: str, lang: str = "en") -> str:
    """Use LLM to answer questions about the briefing with deep analysis"""
    if not st.session_state.provider_switcher:
        return t("chat_error", lang)

    try:
        system_prompt = f"""你是一位AI行业分析专家。你需要回答关于AI行业周报的问题。

关键职责:
1. 分析文章内容，提取中心论点（Central Argument）
2. 识别并解释支撑论点的数据和证据（Data and Evidence）
3. 如果用户提问含混，应该提供多角度的分析
4. 引用具体的文章标题和来源
5. 深入分析而非仅重复摘要

回答要求:
- 准确引用文章内容
- 提供具体的数据、数字或事实
- 解释因果关系和逻辑
- 必要时可以从多篇文章综合分析
- 使用中文回答，保持专业且易懂的语气

以下是本周的文章内容:

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

# Archive section in sidebar
with st.sidebar:
    st.markdown("### 📚 Archive / 存档")
    available = get_available_briefings()

    if available:
        briefing_options = {b['date']: b['path'] for b in available}
        selected_date = st.selectbox(
            "Select briefing / 选择简报",
            options=list(briefing_options.keys()),
            index=0,
            label_visibility="collapsed"
        )

        if selected_date:
            st.session_state.selected_briefing = briefing_options[selected_date]

# Load briefing data - either from archive selection or latest
if st.session_state.selected_briefing:
    briefing_file = st.session_state.selected_briefing
    content = briefing_file.read_text(encoding='utf-8')
    articles = parse_articles_from_markdown(content)
    date_str = briefing_file.stem.replace("ai_briefing_", "").replace("briefing_", "")
    briefing = {
        "date": date_str,
        "title": "AI Industry Weekly Briefing",
        "content": content,
        "articles": articles
    }
else:
    briefing = load_latest_briefing()

if briefing is None:
    st.warning("No briefing data available. Please generate a briefing first.")
    st.stop()

# Main content: 70% briefing + 30% chat interface
left_col, right_col = st.columns([0.70, 0.30], gap="medium")

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
            # Article title
            st.markdown(f"**{idx}. {article.get('title', 'Untitled')}**")

            # Article summary
            if article.get('summary'):
                st.markdown(article['summary'])

            # Source and URL in one line
            meta_info = []
            if article.get('source'):
                meta_info.append(f"来源: {article['source']}")
            if article.get('url'):
                meta_info.append(f"[{article['url']}]({article['url']})")

            if meta_info:
                st.caption(" | ".join(meta_info))

            st.divider()
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
        # Create enriched context with full article details
        enriched_context = create_enriched_briefing_context(briefing.get("articles", []))

        if st.session_state.current_mode == "search":
            with st.spinner(f"🔍 {t('mode_search', st.session_state.language)}..." if st.session_state.language == "zh" else "Searching..."):
                response = search_articles_with_llm(user_input, enriched_context, st.session_state.language)

            st.markdown(f"**{t('search_results_title', st.session_state.language)}**")
            if response and "Error" not in response:
                st.markdown(response)
            else:
                st.warning(t('no_results', st.session_state.language))

        else:  # Ask mode
            with st.spinner(f"💭 {t('mode_ask', st.session_state.language)}..." if st.session_state.language == "zh" else "Thinking..."):
                response = answer_question_about_briefing(user_input, enriched_context, st.session_state.language)

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
