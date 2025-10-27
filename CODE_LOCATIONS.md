# Code Locations: Search & Chatbox Implementation Details

## File: app.py

### Search Function
**Location**: Lines 362-389
```python
def search_articles_with_llm(query: str, briefing_content: str, lang: str = "en") -> str:
    """Use LLM to search and return matching articles"""
```

**What it receives**:
- `query`: User's search query (e.g., "OpenAI")
- `briefing_content`: Full markdown briefing (from line 573)
- `lang`: Language preference

**What it passes to LLM**:
- System prompt with full markdown content (line 378-379)
- User message: "Search for articles related to: {query}" (line 382)

**Limitation**: Only searches content passed in `briefing_content` parameter (single briefing)

---

### Chatbox Question Function
**Location**: Lines 391-413
```python
def answer_question_about_briefing(question: str, briefing_content: str, lang: str = "en") -> str:
    """Use LLM to answer questions about the briefing"""
```

**What it receives**:
- `question`: User's question
- `briefing_content`: Full markdown briefing (from line 583)
- `lang`: Language preference

**What it passes to LLM**:
- System prompt with full markdown content (line 402-403)
- User message: The question itself (line 405)

**Limitation**: Only receives markdown, not full article data

---

### Briefing Load & Parse Functions
**Location**: Lines 309-342 (load_latest_briefing)
```python
def load_latest_briefing() -> Optional[Dict[str, Any]]:
    """Load the latest briefing from data/reports directory"""
    # Loads markdown file
    content = latest_file.read_text(encoding='utf-8')
    # Parses articles from markdown
    articles = parse_articles_from_markdown(content)
    # Returns structure with 'content' field
    return {
        "date": date_str,
        "title": "AI Industry Weekly Briefing",
        "content": content,  # <-- FULL MARKDOWN
        "articles": articles  # <-- PARSED ARTICLES (4 fields only)
    }
```

**Location**: Lines 243-307 (parse_articles_from_markdown)
```python
def parse_articles_from_markdown(content: str) -> List[Dict[str, str]]:
    """Parse articles from markdown briefing content"""
    # Extracts only:
    articles.append({
        "title": title.strip(),
        "summary": summary[:200],  # TRUNCATED!
        "url": url if url else "",
        "source": source if source else ""
    })
    return articles
```

**Data Loss**: 
- Extracts: title, summary (200 chars), url, source
- Discards: everything else from original articles

---

## Where Functions Are Called

### Search Function Called
**Location**: Line 573 (in "search" mode)
```python
response = search_articles_with_llm(
    user_input, 
    briefing.get("content", ""),  # <-- PASSES MARKDOWN
    st.session_state.language
)
```

### Chatbox Called
**Location**: Line 583 (in "ask" mode)
```python
response = answer_question_about_briefing(
    user_input, 
    briefing.get("content", ""),  # <-- PASSES MARKDOWN
    st.session_state.language
)
```

---

## Available But Unused Infrastructure

### context_retriever.py
**Location**: `/Users/dragonsun/briefAI/utils/context_retriever.py`

**Key Functions NOT used in app.py**:

```python
# Multi-briefing keyword search
def search_by_keyword(
    keyword: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search_fields: List[str] = None
) -> List[Dict[str, Any]]:
    """Search cached articles by keyword across all reports"""

# Entity search (companies, models, people, locations)
def search_by_entity(
    entity_name: str,
    entity_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search cached articles by entity across all reports"""

# Get full article with all fields
def get_article_by_id(date: str, article_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve full article with all data fields"""

# Load complete report
def load_report_by_date(date: str) -> Optional[Dict[str, Any]]:
    """Load full report with complete article data"""
```

**Current usage in app.py**: Not imported, not called (0 times)

---

## Article Data Structure Comparison

### What Original JSON Cache Contains
**Location**: `/data/cache/article_contexts/*.json`

```python
article = {
    'title': str,
    'url': str,
    'source': str,
    'content': str,                    # FULL HTML
    'summary': str,                    # Short summary
    'paraphrased_content': str,        # 500-700 char analysis
    'category': str,
    'date': str,
    'published_date': str,
    'source_id': str,
    'language': str,
    
    # Scoring
    'impact_score': float,
    'relevance_score': float,
    'recency_score': float,
    'credibility_score': float,
    'weighted_score': float,
    
    # Metadata
    'fact_check': str,
    'entities': {
        'companies': list,
        'models': list,
        'people': list,
        'locations': list,
        'other': list
    }
}
```

**Availability**: In JSON cache files (fully preserved)
**Access from app.py**: NOT ACCESSIBLE (would need context_retriever)

---

### What Markdown Contains
**Location**: `/data/reports/ai_briefing_*.md`

```
# Article Title (HTML markup)
Brief 200-300 character summary

**来源**: Source Name
**URL**: https://example.com
**发表时间**: Date

[...repeat for each article...]

## Executive Summary
[...summary text...]

## Key Insights
[...insights...]

## Statistics
[...tables...]
```

**Availability**: Full markdown file
**Access from app.py**: YES (passed to search/chatbox functions)
**Fields extracted**: title, summary (truncated to 200), url, source

---

### What App.py Actually Works With
**Briefing structure returned by load_latest_briefing()**:

```python
briefing = {
    "date": str,
    "title": str,
    "content": str,  # <-- FULL MARKDOWN (what's passed to LLM)
    "articles": [    # <-- PARSED ARTICLES (truncated)
        {
            "title": str,
            "summary": str[:200],  # TRUNCATED
            "url": str,
            "source": str
        }
    ]
}
```

---

## Provider Switcher

**Location**: `utils/provider_switcher.py`, line 394-433
```python
def query(
    self,
    prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.7
) -> str:
    """Execute a query with automatic fallback on rate limits"""
```

**Usage**:
- Called from both search and chatbox functions
- Receives system_prompt + user prompt
- Returns LLM response as string
- No visibility into article structure or scoring

---

## System Prompts

### Search System Prompt
**Location**: app.py, lines 368-379

```python
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
```

**What it doesn't include**:
- No instruction to use scores
- No instruction to search historical data
- No instruction to find entities
- No context about which articles are most important

### Chatbox System Prompt
**Location**: app.py, lines 397-403

```python
system_prompt = f"""You are a helpful assistant that answers questions about an AI industry briefing.
The user will ask questions about the briefing content.
Be concise, accurate, and reference specific articles when relevant.
Always answer in {'Chinese' if lang == 'zh' else 'English'}.

BRIEFING CONTENT:
{briefing_content}"""
```

**What it doesn't include**:
- No information about article scores
- No guidance on using detailed analysis
- No context about evidence/citations
- No instruction to compare across time periods

---

## Archive / Multi-Briefing Support

### get_available_briefings() Function
**Location**: Lines 343-360

```python
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
```

**Returns**: List of all available briefing dates/files
**But**: Search/chatbox functions still only use selected briefing (line 450-465)

**Location**: Lines 450-465 (archive selector)
```python
with st.sidebar:
    st.markdown("### 📚 Archive / 存档")
    available = get_available_briefings()

    if available:
        briefing_options = {b['date']: b['path'] for b in available}
        selected_date = st.selectbox(...)
        
        if selected_date:
            st.session_state.selected_briefing = briefing_options[selected_date]
```

**Current behavior**: Selecting archive changes briefing display, but search still only searches selected briefing (not all)

---

## Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│ JSON Cache (context_retriever can access)                   │
│ - Full content                                               │
│ - 5D scores                                                  │
│ - Entities (companies, models, people, locations)          │
│ - Fact-check status                                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ (NOT ACCESSED BY APP)
                       │
┌──────────────────────▼──────────────────────────────────────┐
│ Report Formatter (generates markdown)                        │
│ Outputs: /data/reports/ai_briefing_*.md                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ app.py loads markdown file
                       │ (read_text on line 332, 455)
                       │
┌──────────────────────▼──────────────────────────────────────┐
│ Markdown Content (100% of markdown, ~20% of original data)   │
│ - Article titles, sources, URLs                             │
│ - Brief summaries (already truncated from generation)       │
│ - Executive summary                                         │
│ - Key insights                                              │
│ - Statistics/metadata                                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ parse_articles_from_markdown
                       │ (lines 243-307)
                       │
┌──────────────────────▼──────────────────────────────────────┐
│ Parsed Articles (10% of original data)                       │
│ - Title                                                      │
│ - Summary (truncated to 200 chars) ← DATA LOSS             │
│ - URL                                                        │
│ - Source                                                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
            ┌──────────┴──────────┐
            │                     │
            │ Display (left 70%)   │ search/ask (right 30%)
            │ Shows articles       │
            │ (title, summary)     │
            │                     │
            └─────────────────────┘
            
But both functions use briefing.get("content"):
            │
┌───────────▼──────────────────────────────────────────────────┐
│ Search/Chatbox receives full markdown                        │
│ - All article text (but no scores or entities)              │
│ - No deep analysis (paraphrased content not in markdown)    │
│ - No multi-briefing context                                 │
│ - No historical data                                        │
└───────────────────────────────────────────────────────────────┘
            │
            │ search_articles_with_llm / answer_question_about_briefing
            │ (lines 362-413)
            │
┌───────────▼──────────────────────────────────────────────────┐
│ LLM Response                                                  │
│ (Limited by available context)                              │
└───────────────────────────────────────────────────────────────┘
```

---

## Summary: What's Missing

### For Search Function
| Data | Needed | Currently Available | Missing |
|------|--------|---------------------|---------|
| Titles | YES | YES (in markdown) | ✓ Have it |
| URLs | YES | YES (in markdown) | ✓ Have it |
| Full content | YES | YES (in JSON cache) | ✗ Not passed |
| Scores | YES | YES (in JSON cache) | ✗ Not passed |
| Entities | YES | YES (in JSON cache) | ✗ Not passed |
| Multiple weeks | YES | YES (files exist) | ✗ Not searched |
| Date range | YES | YES (available) | ✗ Not implemented |

### For Chatbox Function
| Data | Needed | Currently Available | Missing |
|------|--------|---------------------|---------|
| Full analysis | YES | YES (500-700 chars in JSON) | ✗ Not passed |
| Article scores | YES | YES (in JSON cache) | ✗ Not shown |
| Entities | YES | YES (in JSON cache) | ✗ Not shown |
| Fact-check | YES | YES (in JSON cache) | ✗ Not shown |
| Categories | YES | YES (in JSON cache) | ✗ Not shown |
| Historical comparison | NO | YES (exists) | ✗ Not available |

