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
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import os
from utils.provider_switcher import ProviderSwitcher
from utils.context_retriever import ContextRetriever

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
    "multi_week_search": {
        "en": "Multi-Week Search",
        "zh": "多周搜索"
    },
    "entity_search": {
        "en": "Entity Search",
        "zh": "实体搜索"
    },
    "date_range": {
        "en": "Date Range",
        "zh": "日期范围"
    },
    "entity_type": {
        "en": "Entity Type",
        "zh": "实体类型"
    },
    "companies": {
        "en": "Companies/Models",
        "zh": "公司/模型"
    },
    "people": {
        "en": "People",
        "zh": "人物"
    },
    "locations": {
        "en": "Locations",
        "zh": "地点"
    },
    "other": {
        "en": "Other",
        "zh": "其他"
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
    """Parse articles from markdown briefing content
    Supports two formats:
    1. Old format: **1. Title** with numbered articles
    2. New format: ### 【Category】Title with section headers
    """
    articles = []
    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]

        # NEW FORMAT: Look for "### 【Category】Title" pattern
        if line.startswith('###') and '】' in line:
            # Extract title - everything after the 】
            if '】' in line:
                title = line.split('】', 1)[1].strip()
            else:
                title = line.replace('###', '').strip()

            summary = ""
            url = ""
            source = ""

            i += 1
            # Collect lines until we hit next article or end
            while i < len(lines):
                current_line = lines[i].strip()

                # Stop if we hit the next article (### marker)
                if current_line.startswith('###'):
                    break

                # Stop if we hit major sections like "## 🔍", "## 📈"
                if current_line.startswith('##'):
                    break

                # Extract source - look for "**来源**: value" or "**来源**:" patterns
                if '**来源**' in current_line and ':' in current_line:
                    # Extract everything after the colon
                    parts = current_line.split(':', 1)
                    if len(parts) > 1:
                        source = parts[1].strip()
                        # Clean up markdown formatting
                        source = source.split('|')[0].strip()
                elif current_line.startswith('**来源'):
                    # Fallback pattern
                    parts = current_line.split(':', 1)
                    if len(parts) > 1:
                        source = parts[1].strip()

                # Extract URL - look for patterns like "**来源链接**: [text](url)"
                elif '**来源链接**' in current_line or 'URL:' in current_line:
                    if '[' in current_line and '](http' in current_line:
                        # Extract URL from markdown link
                        try:
                            url = current_line.split('](')[1].split(')')[0]
                        except:
                            pass
                    else:
                        parts = current_line.split(':', 1)
                        if len(parts) > 1:
                            url = parts[1].strip()

                # Extract score/rating if present
                elif '**评分**' in current_line:
                    # Line like "**评分**: ⭐⭐⭐⭐⭐ **7.3/10** | ..."
                    pass  # Just skip for now

                # First non-empty non-metadata line is the summary
                elif summary == "" and current_line and not current_line.startswith('**') and not current_line.startswith('【'):
                    # Skip lines that are just emojis or metadata
                    if current_line and not current_line.startswith('⭐') and len(current_line) > 10:
                        summary = current_line[:200]  # Truncate to 200 chars

                i += 1

            if title.strip():
                articles.append({
                    "title": title.strip(),
                    "summary": summary if summary else "无摘要",
                    "url": url if url else "",
                    "source": source if source else ""
                })
            continue

        # OLD FORMAT: Look for article titles (numbered like "**1. Title**")
        elif line.startswith('**') and len(line) > 2 and line[2].isdigit() and '. ' in line:
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

                # Extract source
                if '**来源**' in current_line and ':' in current_line:
                    source = current_line.split(':', 1)[1].strip()
                elif current_line.startswith('**来源'):
                    parts = current_line.split(':', 1)
                    if len(parts) > 1:
                        source = parts[1].strip()

                # Extract URL
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

def search_multi_week_with_context_retriever(
    keyword: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search articles across multiple weeks using ContextRetriever

    Args:
        keyword: Search term
        date_from: Start date (YYYY-MM-DD) - optional
        date_to: End date (YYYY-MM-DD) - optional

    Returns:
        List of matching articles with report metadata
    """
    try:
        retriever = ContextRetriever()
        results = retriever.search_by_keyword(
            keyword=keyword,
            date_from=date_from,
            date_to=date_to,
            search_fields=["title", "full_content"]
        )
        return results
    except Exception as e:
        return []

def search_by_entity_with_context_retriever(
    entity_name: str,
    entity_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search articles by entity (company, model, person, location)
    across multiple weeks using ContextRetriever

    Args:
        entity_name: Name of entity to search for
        entity_type: Type of entity (companies, models, people, locations, other)
        date_from: Start date (YYYY-MM-DD) - optional
        date_to: End date (YYYY-MM-DD) - optional

    Returns:
        List of articles mentioning the entity with report metadata
    """
    try:
        retriever = ContextRetriever()
        results = retriever.search_by_entity(
            entity_name=entity_name,
            entity_type=entity_type,
            date_from=date_from,
            date_to=date_to
        )
        return results
    except Exception as e:
        return []

def format_multi_week_results(results: List[Dict[str, Any]], lang: str = "zh") -> str:
    """
    Format multi-week search results for display

    Args:
        results: List of articles from ContextRetriever
        lang: Language for display (zh/en)

    Returns:
        Formatted markdown string
    """
    if not results:
        return "没有找到匹配的文章。" if lang == "zh" else "No articles found."

    output_lines = []
    output_lines.append(f"## 找到 {len(results)} 篇相关文章\n" if lang == "zh" else f"## Found {len(results)} relevant articles\n")

    # Group by date
    by_date = {}
    for article in results:
        date = article.get("report_date", "Unknown")
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(article)

    # Display grouped by date
    for date in sorted(by_date.keys(), reverse=True):
        output_lines.append(f"### 📅 {date}")
        output_lines.append("")

        for article in by_date[date]:
            output_lines.append(f"**{article.get('title', 'Untitled')}**")

            meta_parts = []
            if article.get('source'):
                meta_parts.append(f"来源: {article['source']}" if lang == "zh" else f"Source: {article['source']}")
            if article.get('url'):
                meta_parts.append(f"[URL]({article['url']})")

            if meta_parts:
                output_lines.append(" | ".join(meta_parts))

            if article.get('credibility_score'):
                score = article.get('credibility_score')
                output_lines.append(f"可信度: {score}/10" if lang == "zh" else f"Credibility: {score}/10")

            output_lines.append("")

    return "\n".join(output_lines)

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

    # Mode selector with support for three search types + ask
    st.markdown(f"<div class='mode-selector'>", unsafe_allow_html=True)
    mode_options = {
        "this_week": t('mode_search', st.session_state.language),
        "multi_week": t('multi_week_search', st.session_state.language),
        "entity": t('entity_search', st.session_state.language),
        "ask": t('mode_ask', st.session_state.language)
    }

    st.session_state.current_mode = st.radio(
        "Mode / 模式",
        list(mode_options.keys()),
        format_func=lambda x: mode_options[x],
        horizontal=True,
        label_visibility="collapsed",
        key="mode_selector"
    )
    st.markdown(f"</div>", unsafe_allow_html=True)

    # Additional inputs based on selected mode
    user_input = None
    search_params = {}

    if st.session_state.current_mode == "this_week":
        user_input = st.text_input(
            "Search / 搜索",
            placeholder=t('unified_input_search', st.session_state.language),
            key="search_input",
            label_visibility="collapsed"
        )
        st.caption(t('search_help', st.session_state.language))

    elif st.session_state.current_mode == "multi_week":
        col1, col2 = st.columns(2)
        with col1:
            # Default to last 4 weeks
            default_from = datetime.now() - timedelta(days=28)
            date_from = st.date_input(
                f"{t('date_range', st.session_state.language)} - {t('mode_search', st.session_state.language).split()[0]}",
                value=default_from,
                key="date_from",
                label_visibility="collapsed"
            )
        with col2:
            date_to = st.date_input(
                f"{t('date_range', st.session_state.language)} - {t('mode_ask', st.session_state.language)}",
                value=datetime.now(),
                key="date_to",
                label_visibility="collapsed"
            )

        user_input = st.text_input(
            "Multi-Week Search / 多周搜索",
            placeholder=t('unified_input_search', st.session_state.language),
            key="multiweek_search_input",
            label_visibility="collapsed"
        )
        st.caption(f"🔍 {t('search_help', st.session_state.language)}")
        search_params['date_from'] = date_from
        search_params['date_to'] = date_to

    elif st.session_state.current_mode == "entity":
        col1, col2 = st.columns(2)
        with col1:
            entity_type = st.selectbox(
                t('entity_type', st.session_state.language),
                ["companies", "models", "people", "locations", "other"],
                format_func=lambda x: {
                    "companies": t('companies', st.session_state.language),
                    "models": "Models",
                    "people": t('people', st.session_state.language),
                    "locations": t('locations', st.session_state.language),
                    "other": t('other', st.session_state.language)
                }[x],
                key="entity_type_selector",
                label_visibility="collapsed"
            )
        with col2:
            default_from = datetime.now() - timedelta(days=28)
            date_from = st.date_input(
                f"{t('date_range', st.session_state.language)} - From",
                value=default_from,
                key="entity_date_from",
                label_visibility="collapsed"
            )

        date_to = st.date_input(
            f"{t('date_range', st.session_state.language)} - To",
            value=datetime.now(),
            key="entity_date_to",
            label_visibility="collapsed"
        )

        user_input = st.text_input(
            "Entity Search / 实体搜索",
            placeholder="e.g., OpenAI, GPT-4, Yann LeCun / 例如：OpenAI、GPT-4、Yann LeCun",
            key="entity_search_input",
            label_visibility="collapsed"
        )
        st.caption(f"🔍 {t('search_help', st.session_state.language)}")
        search_params['entity_type'] = entity_type
        search_params['date_from'] = date_from
        search_params['date_to'] = date_to

    else:  # Ask mode
        user_input = st.text_input(
            "Ask / 提问",
            placeholder=t('unified_input_ask', st.session_state.language),
            key="ask_input",
            label_visibility="collapsed"
        )

    st.divider()

    # Process user input and display results
    if user_input:
        if st.session_state.current_mode == "ask":
            # Ask mode: Question answering using current briefing
            enriched_context = create_enriched_briefing_context(briefing.get("articles", []))
            with st.spinner(f"💭 {t('mode_ask', st.session_state.language)}..." if st.session_state.language == "zh" else "Thinking..."):
                response = answer_question_about_briefing(user_input, enriched_context, st.session_state.language)

            st.markdown(f"**{t('ai_response', st.session_state.language)}**")
            if response and "Error" not in response:
                st.markdown(response)
            else:
                st.error(response)

        elif st.session_state.current_mode == "this_week":
            # This week search: Current implementation (Phase A)
            enriched_context = create_enriched_briefing_context(briefing.get("articles", []))
            with st.spinner(f"🔍 {t('mode_search', st.session_state.language)}..."):
                response = search_articles_with_llm(user_input, enriched_context, st.session_state.language)

            st.markdown(f"**{t('search_results_title', st.session_state.language)}**")
            if response and "Error" not in response:
                st.markdown(response)
            else:
                st.warning(t('no_results', st.session_state.language))

        elif st.session_state.current_mode == "multi_week":
            # Multi-week search: Search across multiple briefings using ContextRetriever (Phase B)
            with st.spinner(f"🔍 {t('multi_week_search', st.session_state.language)}..."):
                results = search_multi_week_with_context_retriever(
                    keyword=user_input,
                    date_from=search_params['date_from'].strftime("%Y-%m-%d"),
                    date_to=search_params['date_to'].strftime("%Y-%m-%d")
                )

            st.markdown(f"**{t('search_results_title', st.session_state.language)}**")
            if results:
                # Format and display results grouped by date
                formatted_results = format_multi_week_results(results, st.session_state.language)
                st.markdown(formatted_results)
            else:
                st.warning(t('no_results', st.session_state.language))

        elif st.session_state.current_mode == "entity":
            # Entity search: Search for specific companies, people, models, locations (Phase B)
            with st.spinner(f"🔍 {t('entity_search', st.session_state.language)}..."):
                results = search_by_entity_with_context_retriever(
                    entity_name=user_input,
                    entity_type=search_params['entity_type'],
                    date_from=search_params['date_from'].strftime("%Y-%m-%d"),
                    date_to=search_params['date_to'].strftime("%Y-%m-%d")
                )

            st.markdown(f"**{t('entity_search', st.session_state.language)}: {user_input}**")
            if results:
                # Format and display results grouped by date
                formatted_results = format_multi_week_results(results, st.session_state.language)
                st.markdown(formatted_results)
            else:
                st.warning(t('no_results', st.session_state.language))

# ============================================================================
# FOOTER
# ============================================================================
st.divider()
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
