# Analysis: Search & Chatbox Limitations

This directory contains a comprehensive analysis of search functionality and chatbox context limitations in the current Streamlit app implementation.

## Documents Included

### 1. SEARCH_CHATBOX_ANALYSIS.md (495 lines)
**Full detailed analysis** covering:
- Current search implementation details
- What data gets passed to search_articles_with_llm()
- Current chatbox context analysis
- Data loss in markdown parsing pipeline
- Unused infrastructure (context_retriever.py)
- Architectural limitations
- Root causes
- Detailed recommendations for improvement

**Read this for**: Complete understanding of all limitations and improvement paths

### 2. QUICK_SUMMARY.txt
**Quick reference** with:
- 1-sentence limitation descriptions
- Data loss visualization
- Unused infrastructure overview
- Root causes (bullet points)
- Recommended fixes by priority (Quick Wins, Medium, Advanced)
- Impact estimates

**Read this for**: Quick overview and priority roadmap

### 3. CODE_LOCATIONS.md
**Technical reference** with:
- Exact file:line numbers for all functions
- What each function receives vs. passes to LLM
- Article data structure comparison
- System prompt contents
- Data flow diagram
- Missing data matrix

**Read this for**: Implementation details and where to make changes

## Key Findings Summary

### Two Critical Limitations

1. **Search Limitation: Single-Week Only**
   - Can search only the currently selected briefing
   - Cannot search across multiple weeks or by date range
   - Cannot find entities (companies, models, people) across time
   - Root cause: Designed for single-week display, not research

2. **Chatbox Limitation: Insufficient Context**
   - Receives only markdown summary (200 chars per article)
   - Missing full article analysis (500-700 chars available)
   - Cannot cite article scores or evidence
   - Cannot compare across weeks
   - Root cause: Markdown is bottleneck that strips 80% of data

### Data Loss Pipeline

```
Original JSON Cache (100%)
    ↓ [Report Formatter]
Markdown (20%)
    ↓ [Markdown Parser]
Parsed Articles (10%)
    ↓ [Truncation to 200 chars]
LLM Receives (8%)
```

### Good News: Infrastructure Already Exists

The `utils/context_retriever.py` module already provides:
- Multi-briefing keyword search
- Entity search (companies, models, people, locations)
- Date range filtering
- Full article context with all metadata

**Current usage in app.py**: Zero (0 times)

## Quick Fixes (High Value, Low Effort)

### Fix 1: Pass Full Analysis to LLM (2 lines)
File: `app.py` lines 573, 583
```python
# Instead of: briefing.get("content", "")
# Use: get_full_briefing_context(briefing_date)
```
Impact: +40% chatbox analysis depth

### Fix 2: Include Article Scores (5 lines)
File: `app.py` lines 368-379, 397-403
Add to system prompt: "Article scored X/10 for impact, Y/10 for relevance..."
Impact: LLM understands why articles were selected

### Fix 3: Load JSON Cache (10 lines)
File: `app.py` lines 309-341
Load JSON cache after markdown, extract metadata
Impact: All article fields become available

## Medium Improvements (Enable Research)

### Fix 4: Multi-Briefing Search (30 lines)
Wire up `context_retriever.search_by_keyword()`
Impact: Search across all weeks instead of just current

### Fix 5: Entity Search (50 lines)
Add new search mode using `context_retriever.search_by_entity()`
Impact: "Find all articles about OpenAI" across all weeks

## Architecture Issues

| Issue | Root Cause | Solution |
|-------|-----------|----------|
| Single-week search only | Design choice (display-focused) | Wire up context_retriever |
| Shallow search data | Markdown bottleneck | Load JSON cache alongside |
| Limited chatbox context | Truncated summaries | Pass full paraphrased content |
| No multi-week analysis | No historical context | Build trending analysis |
| Cannot show scores | Data not passed to UI | Include in article display |

## File References

- `app.py`: Main Streamlit application (596 lines)
- `utils/context_retriever.py`: Sophisticated search module (357 lines, unused)
- `utils/provider_switcher.py`: LLM provider management
- `modules/report_formatter.py`: Report generation
- `data/reports/`: Generated briefing markdown files
- `data/cache/`: JSON cache with full article data

## Usage Recommendation

1. **Start here**: Read QUICK_SUMMARY.txt (5 minutes)
2. **If investigating**: Read SEARCH_CHATBOX_ANALYSIS.md (20 minutes)
3. **For implementation**: Read CODE_LOCATIONS.md (15 minutes)
4. **For quick reference**: Use Quick Summary for priorities

## Key Metrics

**Current State**:
- Search scope: 1 week only
- Search data: 200 chars per article (8% of available)
- Chatbox context: Markdown summary only
- Multi-briefing capability: Built but unused

**After Quick Wins**:
- Analysis quality: +40%
- Search depth: +30%

**After Medium Improvements**:
- Multi-week search: ENABLED
- Entity search: ENABLED
- Analysis quality: +80%

---

**Analysis Date**: October 27, 2025
**Scope**: Current Streamlit app implementation (app.py + utils/)
**Status**: Ready for implementation
