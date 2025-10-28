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
from utils.semantic_search import SemanticSearch
from utils.cache_manager import CacheManager

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
            in_deep_analysis = False

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

                # Extract source - look for "**来源**: value" pattern (appears BEFORE deep analysis)
                if '**来源**' in current_line and ':' in current_line:
                    # Extract everything after "**来源**: "
                    if '**来源**:' in current_line:
                        parts = current_line.split('**来源**:', 1)
                        if len(parts) > 1:
                            source = parts[1].strip()
                            # Clean up - take text before pipe or other markers
                            source = source.split('|')[0].strip()

                # Check if we're entering the deep analysis section
                elif '**深度分析**' in current_line or '**深度分析**:' in current_line:
                    in_deep_analysis = True
                    i += 1
                    continue

                # Extract URL - look for patterns like "**来源链接**: [text](url)"
                elif '**来源链接**' in current_line:
                    if '[' in current_line and '](' in current_line:
                        # Extract URL from markdown link format [text](url)
                        try:
                            url = current_line.split('](')[1].split(')')[0]
                        except:
                            pass
                    # Stop collecting deep analysis when we hit the URL line
                    in_deep_analysis = False

                # Extract score/rating if present
                elif '**评分**' in current_line:
                    # Line like "**评分**: ⭐⭐⭐⭐⭐ **7.3/10** | ..."
                    pass  # Just skip for now

                # Collect deep analysis content if we're in that section
                elif in_deep_analysis:
                    # Include all non-empty lines (including **subsection headers** which are part of analysis)
                    # Only stop if we hit metadata like 评分, 来源, 来源链接
                    if current_line and not current_line.startswith('【'):
                        # Skip metadata lines (评分 will be caught by earlier elif)
                        if '**来源**' not in current_line and '**来源链接**' not in current_line:
                            summary += current_line + " "

                # Fallback: First non-empty non-metadata line is the summary (if no deep analysis found)
                elif not in_deep_analysis and summary == "" and current_line and not current_line.startswith('**') and not current_line.startswith('【'):
                    # Skip lines that are just emojis or short metadata
                    if current_line and not current_line.startswith('⭐') and len(current_line) > 10:
                        summary = current_line

                i += 1

            # Clean up summary (remove extra spaces)
            summary = " ".join(summary.split())

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

def search_archive(
    query: str,
    weeks: int = 4,
    entity_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Smart unified archive search - supports both keyword and entity search

    Intelligently detects whether query is an entity (company/model) or keyword phrase.
    Searches across last N weeks (default 4 weeks for ~1 month coverage).

    Args:
        query: Search term (keyword phrase or entity name)
        weeks: Number of weeks to search (default: 4 for 1 month)
        entity_type: Optional entity type hint (companies, models, people, locations, other)
        date_from: Start date (YYYY-MM-DD) - optional, overrides weeks if specified
        date_to: End date (YYYY-MM-DD) - optional, overrides weeks if specified

    Returns:
        List of matching articles with report metadata
    """
    try:
        retriever = ContextRetriever()

        # If explicit dates provided, use them; otherwise use weeks param
        if date_from is None and date_to is None and weeks is not None:
            # Use weeks-based filtering
            results = retriever.search_by_keyword(
                keyword=query,
                weeks=weeks,
                search_fields=["title", "full_content"]
            )

            # Also try entity search if entity_type provided or if it looks like a company/model name
            if entity_type is None:
                # Auto-detect: if it's a short phrase (likely entity), also search by entity
                if len(query.split()) <= 3:  # Single/dual/triple word phrases
                    entity_results = retriever.search_by_entity(
                        entity_name=query,
                        weeks=weeks
                    )
                    # Merge entity results (avoiding duplicates)
                    existing_titles = {r.get('title') for r in results}
                    for r in entity_results:
                        if r.get('title') not in existing_titles:
                            results.append(r)
            else:
                # Search by specific entity type
                entity_results = retriever.search_by_entity(
                    entity_name=query,
                    entity_type=entity_type,
                    weeks=weeks
                )
                # Merge entity results
                existing_titles = {r.get('title') for r in results}
                for r in entity_results:
                    if r.get('title') not in existing_titles:
                        results.append(r)
        else:
            # Use explicit date range
            results = retriever.search_by_keyword(
                keyword=query,
                date_from=date_from,
                date_to=date_to,
                search_fields=["title", "full_content"]
            )

        return results
    except Exception as e:
        return []


def hybrid_search(
    query: str,
    articles: List[Dict[str, Any]],
    weeks: int = 4,
    semantic_weight: float = 0.3,
    keyword_weight: float = 0.7,
    lang: str = "zh"
) -> List[Dict[str, Any]]:
    """
    Hybrid search combining keyword and semantic similarity matching.

    Searches articles using both traditional keyword matching and semantic
    similarity, combining results with configurable weights.

    Args:
        query: Search query text
        articles: List of articles to search (from ContextRetriever or direct list)
        weeks: Number of weeks for date filtering (if articles come from search_archive)
        semantic_weight: Weight for semantic similarity (0.0-1.0)
        keyword_weight: Weight for keyword matching (0.0-1.0)
        lang: Language for output (zh/en)

    Returns:
        List of articles ranked by hybrid score (keyword + semantic)
    """
    if not articles:
        return []

    # Normalize weights
    total_weight = semantic_weight + keyword_weight
    if total_weight == 0:
        return articles

    semantic_norm = semantic_weight / total_weight
    keyword_norm = keyword_weight / total_weight

    # Initialize semantic search
    cache_mgr = CacheManager()
    semantic = SemanticSearch(cache_manager=cache_mgr)

    # If semantic search not available, fall back to keyword-only
    if not semantic.is_available():
        return search_archive(query=query, weeks=weeks)

    # Score all articles
    scored_articles = []

    for article in articles:
        # Keyword relevance score (0-1)
        keyword_score = 0.0
        query_lower = query.lower()
        title = article.get('title', '').lower()
        content = article.get('paraphrased_content', '') or article.get('full_content', '')
        content_lower = content.lower()

        if query_lower in title:
            keyword_score = 1.0
        elif any(word in title for word in query_lower.split()):
            keyword_score = 0.8
        elif query_lower in content_lower:
            keyword_score = 0.6
        elif any(word in content_lower for word in query_lower.split()):
            keyword_score = 0.4

        # Semantic similarity score (0-1)
        semantic_score = 0.0
        combined_text = f"{title} {content[:500]}"
        if combined_text.strip():
            emb = semantic.get_embedding(combined_text)
            query_emb = semantic.get_embedding(query)
            if emb is not None and query_emb is not None:
                semantic_score = semantic.cosine_similarity(emb, query_emb)
                semantic_score = max(0, min(1, semantic_score))  # Normalize to [0,1]

        # Combine scores
        hybrid_score = (keyword_norm * keyword_score) + (semantic_norm * semantic_score)

        article_scored = article.copy()
        article_scored['keyword_score'] = keyword_score
        article_scored['semantic_similarity'] = semantic_score
        article_scored['hybrid_score'] = hybrid_score

        scored_articles.append(article_scored)

    # Sort by hybrid score
    scored_articles.sort(key=lambda x: x['hybrid_score'], reverse=True)

    return scored_articles


def cluster_search_results(
    articles: List[Dict[str, Any]],
    similarity_threshold: float = 0.7
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Cluster search results by semantic similarity.

    Groups similar articles together for better organization and insights.

    Args:
        articles: Articles to cluster
        similarity_threshold: Threshold for grouping (0.7-0.95)

    Returns:
        Dict with clusters and metadata:
        {
            "clusters": [
                {"title": "Cluster topic", "articles": [...], "size": 5},
                ...
            ],
            "total_clusters": 3,
            "articles_per_cluster": [5, 3, 2]
        }
    """
    if not articles:
        return {"clusters": [], "total_clusters": 0, "articles_per_cluster": []}

    # Initialize semantic search
    cache_mgr = CacheManager()
    semantic = SemanticSearch(cache_manager=cache_mgr)

    if not semantic.is_available():
        # Fallback: each article is its own cluster
        clusters = [
            {
                "title": f"Article {i+1}: {article.get('title', 'Untitled')[:50]}",
                "articles": [article],
                "size": 1
            }
            for i, article in enumerate(articles)
        ]
        return {
            "clusters": clusters,
            "total_clusters": len(clusters),
            "articles_per_cluster": [1] * len(clusters)
        }

    # Use semantic clustering
    article_clusters = semantic.cluster_by_similarity(
        articles,
        similarity_threshold=similarity_threshold
    )

    # Format clusters with titles
    formatted_clusters = []
    for i, cluster in enumerate(article_clusters, 1):
        if cluster:
            # Use the first article's title as cluster title
            cluster_title = cluster[0].get('title', f'Cluster {i}')[:60]
            formatted_clusters.append({
                "title": f"Cluster {i}: {cluster_title}",
                "articles": cluster,
                "size": len(cluster)
            })

    return {
        "clusters": formatted_clusters,
        "total_clusters": len(formatted_clusters),
        "articles_per_cluster": [c["size"] for c in formatted_clusters]
    }


# Legacy function names - kept for backward compatibility
def search_multi_week_with_context_retriever(
    keyword: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    DEPRECATED: Use search_archive() instead.
    Search articles across multiple weeks using ContextRetriever
    """
    return search_archive(
        query=keyword,
        date_from=date_from,
        date_to=date_to,
        weeks=None if (date_from or date_to) else 4
    )

def search_by_entity_with_context_retriever(
    entity_name: str,
    entity_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    DEPRECATED: Use search_archive() instead.
    Search articles by entity (company, model, person, location)
    """
    return search_archive(
        query=entity_name,
        entity_type=entity_type,
        date_from=date_from,
        date_to=date_to,
        weeks=None if (date_from or date_to) else 4
    )

def filter_and_facet_results(
    results: List[Dict[str, Any]],
    source_filter: Optional[List[str]] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    lang: str = "zh"
) -> Dict[str, Any]:
    """
    Filter search results by various criteria and return faceting information

    Args:
        results: List of articles to filter
        source_filter: List of source names to include (if None, include all)
        min_score: Minimum weighted score (0-10)
        max_score: Maximum weighted score (0-10)
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        lang: Language for output

    Returns:
        Dict with 'filtered_results' and 'facets' (source counts, date range, etc.)
    """
    filtered = results[:]

    # Filter by source
    if source_filter:
        filtered = [r for r in filtered if r.get('source', '') in source_filter]

    # Filter by score range
    if min_score is not None:
        filtered = [r for r in filtered if r.get('weighted_score', 0) >= min_score]
    if max_score is not None:
        filtered = [r for r in filtered if r.get('weighted_score', 10) <= max_score]

    # Filter by date range
    if date_from:
        filtered = [r for r in filtered if r.get('report_date', '') >= date_from]
    if date_to:
        filtered = [r for r in filtered if r.get('report_date', '') <= date_to]

    # Collect faceting information from original results
    facets = {
        "total_original": len(results),
        "total_filtered": len(filtered),
        "sources": {},
        "score_range": {"min": 0, "max": 10},
        "date_range": {}
    }

    # Count by source
    for article in results:
        source = article.get('source', 'Unknown')
        facets["sources"][source] = facets["sources"].get(source, 0) + 1

    # Find date range
    if results:
        dates = [r.get('report_date', '') for r in results if r.get('report_date')]
        if dates:
            facets["date_range"] = {
                "earliest": min(dates),
                "latest": max(dates),
                "count": len(set(dates))
            }

    # Find actual score range
    if results:
        scores = [r.get('weighted_score', 0) for r in results if r.get('weighted_score')]
        if scores:
            facets["score_range"] = {
                "min": min(scores),
                "max": max(scores),
                "avg": sum(scores) / len(scores)
            }

    return {
        "filtered_results": filtered,
        "facets": facets
    }


def format_enhanced_search_results(
    results: List[Dict[str, Any]],
    lang: str = "zh",
    sort_by: str = "date",
    min_score: Optional[float] = None,
    show_paraphrase: bool = True
) -> str:
    """
    Enhanced formatting for search results with 5D scores, metadata, and visual hierarchy

    Args:
        results: List of articles from ContextRetriever or search_archive()
        lang: Language for display (zh/en)
        sort_by: Sort order - 'date' (newest first), 'score' (highest score first), 'relevance' (title match)
        min_score: Filter articles by minimum weighted score (0-10)
        show_paraphrase: Whether to show paraphrased content summary

    Returns:
        Formatted markdown string with enhanced styling
    """
    if not results:
        return "没有找到匹配的文章。" if lang == "zh" else "No articles found."

    # Filter by minimum score if provided
    if min_score is not None:
        results = [r for r in results if r.get('weighted_score', 0) >= min_score]
        if not results:
            return (f"没有找到符合最低评分 {min_score} 的文章。" if lang == "zh"
                    else f"No articles found with minimum score {min_score}.")

    # Sort results
    if sort_by == "score":
        results = sorted(results, key=lambda x: x.get('weighted_score', 0), reverse=True)
    elif sort_by == "relevance":
        # Already in search relevance order, keep as-is
        pass
    else:  # date (default)
        results = sorted(results, key=lambda x: x.get('report_date', ''), reverse=True)

    output_lines = []

    # Header with result count and filters info
    header_text = f"找到 {len(results)} 篇相关文章" if lang == "zh" else f"Found {len(results)} relevant articles"
    filter_info = []
    if sort_by == "score":
        filter_info.append(f"(按评分排序)" if lang == "zh" else "(sorted by score)")
    if min_score:
        filter_info.append(f"(最低分数: {min_score})" if lang == "zh" else f"(min score: {min_score})")

    if filter_info:
        header_text += " " + " ".join(filter_info)
    output_lines.append(f"## {header_text}\n")

    # Group by report date for better organization
    by_date = {}
    for article in results:
        date = article.get("report_date", "Unknown")
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(article)

    # Display articles grouped by date
    for date in sorted(by_date.keys(), reverse=True):
        output_lines.append(f"### 📅 {date}")
        output_lines.append("")

        for idx, article in enumerate(by_date[date], 1):
            # Article title with ranking indicator
            title = article.get('title', 'Untitled')
            rank_badge = ""
            if sort_by == "score" and article.get('weighted_score'):
                rank_badge = f" [{article.get('weighted_score'):.1f}/10]"
            output_lines.append(f"**{idx}. {title}{rank_badge}**")

            # Source and URL metadata
            meta_parts = []
            if article.get('source'):
                meta_parts.append(f"📰 {article['source']}" if lang == "zh" else f"📰 {article['source']}")
            if article.get('url'):
                meta_parts.append(f"[链接]({article['url']})" if lang == "zh" else f"[Link]({article['url']})")

            if meta_parts:
                output_lines.append(" | ".join(meta_parts))

            # 5D Scores if available
            if article.get('evaluation') and article.get('evaluation').get('scores'):
                scores = article['evaluation']['scores']
                score_line = ""
                if lang == "zh":
                    score_line = f"📊 评分 - 市场影响: {scores.get('market_impact', 0):.1f} | 竞争影响: {scores.get('competitive_impact', 0):.1f} | 战略相关性: {scores.get('strategic_relevance', 0):.1f}"
                else:
                    score_line = f"📊 Scores - Market: {scores.get('market_impact', 0):.1f} | Competitive: {scores.get('competitive_impact', 0):.1f} | Strategic: {scores.get('strategic_relevance', 0):.1f}"
                output_lines.append(score_line)

            # Credibility score
            if article.get('credibility_score'):
                cred_score = article.get('credibility_score')
                output_lines.append(f"✅ 可信度: {cred_score}/10" if lang == "zh" else f"✅ Credibility: {cred_score}/10")

            # Paraphrased content summary if available
            if show_paraphrase and article.get('paraphrased_content'):
                content = article['paraphrased_content']
                # Show first 300 characters as summary
                preview = content[:300] + ("..." if len(content) > 300 else "")
                output_lines.append("")
                output_lines.append(f"> {preview}")

            output_lines.append("")

    return "\n".join(output_lines)


def format_multi_week_results(results: List[Dict[str, Any]], lang: str = "zh") -> str:
    """
    Format multi-week search results for display (legacy - uses enhanced formatter)

    Args:
        results: List of articles from ContextRetriever
        lang: Language for display (zh/en)

    Returns:
        Formatted markdown string
    """
    # Use enhanced formatter with default settings
    return format_enhanced_search_results(results, lang=lang, sort_by="date", show_paraphrase=False)

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
